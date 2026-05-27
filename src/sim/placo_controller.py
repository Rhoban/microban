"""MeshCat viewer controller using placo kinematics — never deployed to the robot."""

import numpy as np
import placo
from placo_utils.visualization import robot_viz

from constants import ID_TO_MOTOR, NEUTRAL_POSE, KP_DEFAULT


class PlacoViewerController:
    """Physics-free controller that displays the robot in a MeshCat browser window."""

    def __init__(self, model_path: str) -> None:

        # Load robot and set neutral pose
        self._robot = placo.RobotWrapper(model_path, placo.Flags.mjcf)

        for name, angle in NEUTRAL_POSE.items():
            self._robot.set_joint(name, angle)

        T_left_foot = np.eye(4)
        self._robot.set_T_world_frame("left_foot", T_left_foot)
        self._robot.update_kinematics()

        # Open MeshCat viewer
        self._viz = robot_viz(self._robot)
        self._viz.display(self._robot.state.q)

        # Track commanded angles
        self._current_angles: dict[str, float] = dict(NEUTRAL_POSE)

    def sync_write_goal_position(self, ids: list[int], positions: list[float]) -> None:
        for motor_id, pos in zip(ids, positions):
            self._current_angles[ID_TO_MOTOR[motor_id]] = pos
            self._robot.set_joint(ID_TO_MOTOR[motor_id], pos)

        self._robot.set_T_world_frame("left_foot", np.eye(4))
        self._robot.update_kinematics()

        self._viz.display(self._robot.state.q)

    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        return [self._current_angles.get(ID_TO_MOTOR.get(mid, ""), 0.0) for mid in ids]

    def read_present_position(self, motor_id: int) -> float:
        name = ID_TO_MOTOR.get(motor_id, "")
        return self._current_angles.get(name, 0.0)

    def read_present_input_voltage(self, motor_id: int) -> float:  # noqa: ARG002
        return 80.0

    def sync_read_kp(self, ids: list[int]) -> list[int]:
        return [KP_DEFAULT] * len(ids)

    def sync_write_kp(self, ids: list[int], gains: list[int]) -> None:
        pass

    def sync_write_torque_enable(self, ids: list[int], values: list[bool]) -> None:
        pass

    def sync_write_status_return_level(self, ids: list[int], levels: list[int]) -> None:
        pass
