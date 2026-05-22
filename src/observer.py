from dataclasses import dataclass, field
import time

from input.input_source import UserInput
from battery import BATTERY_VOLTAGE_OFFSET


@dataclass
class RobotState:
    """Hardware sensor readings for one scheduler iteration."""

    time_s: float = 0.0
    imu: list[float] = field(default_factory=list)
    gyro: list[float] = field(default_factory=list)
    motor_angles: dict[str, float] = field(default_factory=dict)


@dataclass
class Observation:
    """Full observation passed through the move pipeline each tick."""

    robot_state: RobotState = field(default_factory=RobotState)
    user_input: UserInput = field(default_factory=UserInput)


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

    def read_battery_voltage(self, probe_ids: list[int]) -> float:
        """Return the average bus voltage in volts across all *probe_ids*."""
        readings = []
        for probe_id in probe_ids:
            raw = self.controller.read_present_input_voltage(probe_id)
            voltage_raw = raw[0] if isinstance(raw, (list, tuple)) else raw
            readings.append(voltage_raw * 0.1)
        return sum(readings) / len(readings) + BATTERY_VOLTAGE_OFFSET