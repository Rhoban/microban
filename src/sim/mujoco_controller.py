import math
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import mujoco
import mujoco.viewer

if TYPE_CHECKING:
    from sim.mujoco_input import MuJoCoInputSource

from constants import MOTOR_TO_ID, ID_TO_MOTOR, NEUTRAL_POSE, KP_GAIN_PRM


class MuJoCoController:
    """MuJoCo-backed controller."""

    def __init__(
        self,
        mjcf_path: str,
        key_callback: Callable[[int, int, int, int], None] | None = None,
        stop_flag_path: str = "/tmp/microban_scheduler.stop",
        reset_source: "MuJoCoInputSource | None" = None,
    ) -> None:
        self._stop_flag_path = Path(stop_flag_path)
        self._reset_source = reset_source
        self._model = mujoco.MjModel.from_xml_path(mjcf_path)
        self._data = mujoco.MjData(self._model)

        self._name_to_actuator_idx: dict[str, int] = {}
        self._name_to_qpos_idx: dict[str, int] = {}
        self._name_to_qvel_idx: dict[str, int] = {}
        for name in MOTOR_TO_ID:
            actuator_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if actuator_id < 0:
                raise ValueError(f"Actuator '{name}' not found in MJCF model {mjcf_path!r}")
            if joint_id < 0:
                raise ValueError(f"Joint '{name}' not found in MJCF model {mjcf_path!r}")
            self._name_to_actuator_idx[name] = actuator_id
            self._name_to_qpos_idx[name] = self._model.jnt_qposadr[joint_id]
            self._name_to_qvel_idx[name] = self._model.jnt_dofadr[joint_id]
        # Number of physics sub-steps per scheduler tick (scheduler runs at 50 Hz)
        self._steps_per_tick = max(1, round(0.02 / self._model.opt.timestep))
        self._torque_interval = 0.1
        self._last_torque_print = 0.0

        # Set initial pose to neutral so the robot starts upright
        self._data.qpos[2] = 0.165 
        for name, angle in NEUTRAL_POSE.items():
            if name in self._name_to_qpos_idx:
                self._data.qpos[self._name_to_qpos_idx[name]] = angle
            if name in self._name_to_actuator_idx:
                self._data.ctrl[self._name_to_actuator_idx[name]] = angle
        mujoco.mj_forward(self._model, self._data)

        self._viewer = mujoco.viewer.launch_passive(
            self._model, self._data, key_callback=key_callback
        )

        # Sensor indices for IMU readout
        self._sensor_orientation = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SENSOR, "orientation")
        self._sensor_gyro = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_SENSOR, "angular-velocity")

    @property
    def viewer_opt(self) -> mujoco.MjvOption:
        return self._viewer.opt

    def set_kp(self, kp: float) -> None:
        """Set the same Kp on all actuators at once.
        This function take Kp in register units and converts it in Nm/rad."""
        kp_si = kp * KP_GAIN_PRM
        self._model.actuator_gainprm[:, 0] = kp_si
        self._model.actuator_biasprm[:, 1] = -kp_si

    def sync_read_kp(self, ids: list[int]) -> list[int]:
        return [
            self._kp_to_register(int(float(self._model.actuator_gainprm[self._name_to_actuator_idx[ID_TO_MOTOR[motor_id]], 0]) / KP_GAIN_PRM))
            for motor_id in ids
        ]

    def sync_write_kp(self, ids: list[int], gains: list[int]) -> None:
        for motor_id, gain in zip(ids, gains):
            kp_si = gain * KP_GAIN_PRM
            idx = self._name_to_actuator_idx[ID_TO_MOTOR[motor_id]]
            self._model.actuator_gainprm[idx, 0] = kp_si
            self._model.actuator_biasprm[idx, 1] = -kp_si

    def sync_write_torque_enable(self, ids: list[int], values: list[bool]) -> None:
        pass

    def sync_write_status_return_level(self, ids: list[int], levels: list[int]) -> None:
        pass

    def sync_write_goal_position(self, ids: list[int], positions: list[float]) -> None:
        if not self._viewer.is_running():
            self._stop_flag_path.write_text("stop\n", encoding="ascii")
            return

        for motor_id, pos in zip(ids, positions):
            name = ID_TO_MOTOR[motor_id]
            self._data.ctrl[self._name_to_actuator_idx[name]] = pos

        for _ in range(self._steps_per_tick):
            mujoco.mj_step(self._model, self._data)

        if self._reset_source is not None and self._reset_source.consume_reset():
            self.reset()
            return

        if self._reset_source is not None and self._reset_source.show_torque:
            now = time.monotonic()
            if now - self._last_torque_print >= self._torque_interval:
                total = float(sum(abs(f) for f in self._data.actuator_force))
                print(f"Torque sum: {total:.3f} Nm")
                self._last_torque_print = now

        self._viewer.sync()

    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        return [self._data.qpos[self._name_to_qpos_idx[ID_TO_MOTOR[motor_id]]] for motor_id in ids]

    def read_present_position(self, motor_id: int) -> float:
        name = ID_TO_MOTOR[motor_id]
        return float(self._data.qpos[self._name_to_qpos_idx[name]])

    def sync_read_present_velocity(self, ids: list[int]) -> list[float]:
        return [self._data.qvel[self._name_to_qvel_idx[ID_TO_MOTOR[motor_id]]] for motor_id in ids]

    def read_present_velocity(self, motor_id: int) -> float:
        name = ID_TO_MOTOR[motor_id]
        return float(self._data.qvel[self._name_to_qvel_idx[name]])

    def sync_read_present_input_voltage(self, ids: list[int]) -> list[float]:
        return [80.0] * len(ids)
    
    def read_present_input_voltage(self, motor_id: int) -> float:
        return 80.0

    def read_acc(self) -> tuple[float, float, float]:
        """Return pseudo-accelerometer (ax, ay, az) in g from the 'orientation' sensor."""
        if self._sensor_orientation < 0:
            return 0.0, 0.0, -1.0
        adr = self._model.sensor_adr[self._sensor_orientation]
        w, x, y, z = self._data.sensordata[adr:adr + 4]
        # Gravity in world is (0, 0, -1) g; rotate into IMU frame using conjugate quat
        gx = 2 * (x * z - w * y)
        gy = 2 * (y * z + w * x)
        gz = w * w - x * x - y * y + z * z
        return float(gx), float(gy), float(-gz)

    def read_gyro(self) -> tuple[float, float, float]:
        """Return (gx, gy, gz) in rad/s from the 'angular-velocity' gyro sensor."""
        if self._sensor_gyro < 0:
            return 0.0, 0.0, 0.0
        adr = self._model.sensor_adr[self._sensor_gyro]
        gx, gy, gz = self._data.sensordata[adr:adr + 3]
        return float(gx), float(gy), float(gz)

    def read_quat(self, dt: float) -> tuple[float, float, float, float]:
        """Return orientation quaternion (w, x, y, z) from the 'orientation' framequat sensor."""
        if self._sensor_orientation < 0:
            return 1.0, 0.0, 0.0, 0.0
        adr = self._model.sensor_adr[self._sensor_orientation]
        w, x, y, z = self._data.sensordata[adr:adr + 4]
        return float(w), float(x), float(y), float(z)

    def reset(self) -> None:
        """Reset the simulation to the initial neutral standing pose."""
        self._data.qpos[:] = 0.0
        self._data.qvel[:] = 0.0
        self._data.ctrl[:] = 0.0
        self._data.qpos[2] = 0.165
        for name, angle in NEUTRAL_POSE.items():
            if name in self._name_to_qpos_idx:
                self._data.qpos[self._name_to_qpos_idx[name]] = angle
            if name in self._name_to_actuator_idx:
                self._data.ctrl[self._name_to_actuator_idx[name]] = angle
        mujoco.mj_forward(self._model, self._data)
        self._viewer.sync()
