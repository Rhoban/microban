import mujoco
import mujoco.viewer
from collections.abc import Callable
from pathlib import Path

from constants import MOTOR_ID, NEUTRAL_POSE


_ID_TO_NAME: dict[int, str] = {v: k for k, v in MOTOR_ID.items()}


class MuJoCoController:
    """MuJoCo-backed controller."""

    def __init__(
        self,
        mjcf_path: str,
        key_callback: Callable[[int, int, int, int], None] | None = None,
        stop_flag_path: str = "/tmp/microban_scheduler.stop",
    ) -> None:
        self._stop_flag_path = Path(stop_flag_path)
        self._model = mujoco.MjModel.from_xml_path(mjcf_path)
        self._data = mujoco.MjData(self._model)

        self._name_to_actuator_idx: dict[str, int] = {}
        self._name_to_qpos_idx: dict[str, int] = {}
        for name in MOTOR_ID:
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
        for name, angle in NEUTRAL_POSE.items():
            if name in self._name_to_qpos_idx:
                self._data.qpos[self._name_to_qpos_idx[name]] = angle
            if name in self._name_to_actuator_idx:
                self._data.ctrl[self._name_to_actuator_idx[name]] = angle
        mujoco.mj_forward(self._model, self._data)

        self._viewer = mujoco.viewer.launch_passive(
            self._model, self._data, key_callback=key_callback
        )

    def sync_write_torque_enable(self, ids: list[int], values: list[bool]) -> None:
        pass

    def sync_write_status_return_level(self, ids: list[int], levels: list[int]) -> None:
        pass

    def sync_write_goal_position(self, ids: list[int], positions: list[float]) -> None:
        if not self._viewer.is_running():
            self._stop_flag_path.write_text("stop\n", encoding="ascii")
            return

        for motor_id, pos in zip(ids, positions):
            name = _ID_TO_NAME[motor_id]
            self._data.ctrl[self._name_to_actuator_idx[name]] = pos

        for _ in range(self._steps_per_tick):
            mujoco.mj_step(self._model, self._data)

        self._viewer.sync()

    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        return [self._data.qpos[self._name_to_qpos_idx[_ID_TO_NAME[motor_id]]] for motor_id in ids]

    def read_present_position(self, motor_id: int) -> float:
        name = _ID_TO_NAME[motor_id]
        return float(self._data.qpos[self._name_to_qpos_idx[name]])

    def read_present_input_voltage(self, motor_id: int) -> float:
        return 80.0
