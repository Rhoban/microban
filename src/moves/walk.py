import onnxruntime as ort

from observer import Observation
from moves.move import MotorCommand, Move


class WalkMove(Move):
    """Walk using a RL policy trained in simulation."""

    def __init__(self) -> None:
        pass

    def apply(self, obs: Observation, command: MotorCommand) -> None:
        pass