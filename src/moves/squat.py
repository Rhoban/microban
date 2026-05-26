import math

from observer import Observation
from moves.move import MotorCommand, Move, MoveState
from constants import MOTOR_ID


class SquatMove(Move):
    """
    Generate a squat motion of frequency *frequency* starting from the neutral pose and lowering the body DoFs by *amplitude*.
    
    Transitions (on_start / on_stop) lerp the body DoFs to 0 over *lerp_duration* seconds
    so the move starts and stops smoothly.

    :param frequency: Frequency of the squat motion in Hz.
    :param amplitude: Amplitude of the squat motion in meters.
    :param lerp_duration: Duration of the transition to/from the squat motion in seconds.
    """

    def __init__(
        self,
        frequency: float = 1.0,
        amplitude: float = 0.1,
        lerp_duration: float = 0.5,
    ) -> None:
        super().__init__()
        self.frequency = frequency
        self.amplitude = amplitude
        self.lerp_duration = lerp_duration

        self._lerp_start_time_s: float | None = None
        self._lerp_start_angle: list[float] = [0.0] * 18
        self._active_start_time_s: float = 0.0

    def step(self, obs: Observation, command: MotorCommand) -> None:
        pass

    # def on_start(self, obs: Observation, command: MotorCommand) -> None:
    #     if self._lerp_start_time_s is None:
    #         self._lerp_start_time_s = obs.robot_state.time_s
    #         for 
    #         self._lerp_start_angle = obs.robot_state.motor_angles.get("head", 0.0)

    #     t = (obs.robot_state.time_s - self._lerp_start_time_s) / self.lerp_duration
    #     t = min(t, 1.0)
    #     command.target_angles["head"] = self._lerp_start_angle * (1.0 - t)

    #     if t >= 1.0:
    #         self._lerp_start_time_s = None
    #         self._active_start_time_s = obs.robot_state.time_s
    #         self.state = MoveState.ACTIVE

    # def step(self, obs: Observation, command: MotorCommand) -> None:
    #     t = obs.robot_state.time_s - self._active_start_time_s
    #     head_angle = self.amplitude_rad * math.sin(2.0 * math.pi * self.frequency_hz * t)
    #     command.target_angles["head"] = head_angle

    # def on_stop(self, obs: Observation, command: MotorCommand) -> None:
    #     if self._lerp_start_time_s is None:
    #         self._lerp_start_time_s = obs.robot_state.time_s
    #         self._lerp_start_angle = obs.robot_state.motor_angles.get("head", 0.0)

    #     t = (obs.robot_state.time_s - self._lerp_start_time_s) / self.lerp_duration
    #     t = min(t, 1.0)
    #     command.target_angles["head"] = self._lerp_start_angle * (1.0 - t)

    #     if t >= 1.0:
    #         self._lerp_start_time_s = None
    #         self.state = MoveState.INACTIVE