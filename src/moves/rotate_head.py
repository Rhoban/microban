import math

from observer import RobotState
from move import MotorCommand, Move

class RotateHeadMove(Move):
    """Generate a sinusoidal head rotation between -45 and +45 degrees."""

    def __init__(self, frequency_hz: float = 0.35, amplitude_rad: float = math.pi / 4) -> None:
        self.frequency_hz = frequency_hz
        self.amplitude_rad = amplitude_rad

    def apply(self, state: RobotState, command: MotorCommand) -> None:
        head_angle = self.amplitude_rad * math.sin(2.0 * math.pi * self.frequency_hz * state.time_s)
        command.target_angles["head"] = head_angle 