from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from observer import RobotState

@dataclass
class MotorCommand:
    """Final motor command built by the scheduler pipeline."""
    target_angles: dict[str, float] = field(default_factory=dict)

class Move(ABC):
    """Base class for all motion behaviors."""

    @abstractmethod
    def apply(self, state: RobotState, command: MotorCommand) -> None:
        """Read state and update the motor command in place."""
