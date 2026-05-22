from dataclasses import dataclass, field
import time

@dataclass
class RobotState:
    """Snapshot of robot observations for one scheduler iteration."""

    time_s: float = 0.0
    imu: list[float] = field(default_factory=list)
    gyro: list[float] = field(default_factory=list)
    motor_angles: dict[str, float] = field(default_factory=dict)

class Observer:
    def __init__(self, controller, motor_name_to_id: dict[str, int]):
        self.controller = controller
        self.motor_name_to_id = motor_name_to_id

    def read_state(self) -> RobotState:
        """Read current motor positions from the controller."""
        state = RobotState(time_s=time.perf_counter())

        for motor_name, motor_id in self.motor_name_to_id.items():
            state.motor_angles[motor_name] = self.controller.read_present_position(motor_id)

        return state