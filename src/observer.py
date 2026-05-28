from dataclasses import dataclass, field
import time

from controller import ControllerProtocol
from input.input_source import UserInput
from constants import MOTOR_TO_ID


@dataclass
class RobotState:
    """Hardware sensor readings for one scheduler iteration."""

    time_s: float = 0.0
    acc: list[float] = field(default_factory=list)
    gyro: list[float] = field(default_factory=list)
    quat: list[float] = field(default_factory=list)
    motor_angles: dict[str, float] = field(default_factory=dict)


@dataclass
class Observation:
    """Full observation passed through the move pipeline each tick."""

    robot_state: RobotState = field(default_factory=RobotState)
    user_input: UserInput = field(default_factory=UserInput)


class Observer:
    def __init__(self, controller: ControllerProtocol):
        self.controller = controller

    def read_state(self) -> RobotState:
        """Read current motor positions from the controller."""
        state = RobotState(time_s=time.perf_counter())

        motor_names = list(MOTOR_TO_ID.keys())
        motor_ids = list(MOTOR_TO_ID.values())
        angles = self.controller.sync_read_present_position(motor_ids)
        state.motor_angles = dict(zip(motor_names, angles))

        try:
            state.acc = list(self.controller.read_acc())
            state.gyro = list(self.controller.read_gyro())
            state.quat = list(self.controller.read_quat())
        except Exception:
            pass

        return state

