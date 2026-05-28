import math
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import mujoco
import mujoco.viewer

if TYPE_CHECKING:
    from sim.mujoco_input import MuJoCoInputSource

from constants import MOTOR_TO_ID, ID_TO_MOTOR, NEUTRAL_POSE


class MuJoCoController:
    """MuJoCo-backed controller."""

    # kp [Nm/rad] = (KPP_TBL / 128) × (PULSES_PER_REV / 2 * pi) / PWM_MAX × STALL_TORQUE
    # with PWM_MAX = 885, STALL_TORQUE = 0.60 Nm, and PULSES_PER_REV = 4096, this gives:
    SIM_KP_DEFAULT: float = 1.38  # [Nm/rad]
    SIM_KP_RL: float = 0.43       # [Nm/rad]

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
        for name in MOTOR_TO_ID:
            actuator_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if actuator_id < 0:
                raise ValueError(f"Actuator '{name}' not found in MJCF model {mjcf_path!r}")
            if joint_id < 0:
                raise ValueError(f"Joint '{name}' not found in MJCF model {mjcf_path!r}")
            self._name_to_actuator_idx[name] = actuator_id
            self._name_to_qpos_idx[name] = self._model.jnt_qposadr[joint_id]

        # Number of physics sub-steps per scheduler tick (scheduler runs at 50 Hz)
        self._steps_per_tick = max(1, round(0.02 / self._model.opt.timestep))

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

    @staticmethod
    def _register_to_kp(register_val: int) -> float:
        """Convert Dynamixel Position P Gain register value to MuJoCo kp [Nm/rad]."""
        return (
            (register_val / 128)
            * (MuJoCoController._PULSES_PER_REV / (2 * math.pi))
            / MuJoCoController._PWM_MAX
            * MuJoCoController._STALL_TORQUE_NM
        )

    @staticmethod
    def _kp_to_register(kp: float) -> int:
        """Convert MuJoCo kp [Nm/rad] to Dynamixel Position P Gain register value."""
        return round(
            kp
            * 128
            * MuJoCoController._PWM_MAX
            / (MuJoCoController._PULSES_PER_REV / (2 * math.pi))
            / MuJoCoController._STALL_TORQUE_NM
        )

    def set_kp(self, kp: float) -> None:
        """Set the same Kp [Nm/rad] on all actuators at once."""
        self._model.actuator_gainprm[:, 0] = kp
        self._model.actuator_biasprm[:, 1] = -kp

    def sync_read_kp(self, ids: list[int]) -> list[int]:
        return [
            self._kp_to_register(float(self._model.actuator_gainprm[self._name_to_actuator_idx[ID_TO_MOTOR[motor_id]], 0]))
            for motor_id in ids
        ]

    def sync_write_kp(self, ids: list[int], gains: list[int]) -> None:
        for motor_id, gain in zip(ids, gains):
            kp = self._register_to_kp(gain)
            idx = self._name_to_actuator_idx[ID_TO_MOTOR[motor_id]]
            self._model.actuator_gainprm[idx, 0] = kp
            self._model.actuator_biasprm[idx, 1] = -kp

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

        self._viewer.sync()

    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        return [self._data.qpos[self._name_to_qpos_idx[ID_TO_MOTOR[motor_id]]] for motor_id in ids]

    def read_present_position(self, motor_id: int) -> float:
        name = ID_TO_MOTOR[motor_id]
        return float(self._data.qpos[self._name_to_qpos_idx[name]])

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

    def read_quat(self) -> tuple[float, float, float, float]:
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
