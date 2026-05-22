import math
import onnxruntime as ort

from observer import RobotState
from move import MotorCommand, Move

class WalkMove(Move):
    """Walk using a RL policy trained in simulation."""

    def __init__(self) -> None:
        return