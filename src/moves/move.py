from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from observer import Observation


@dataclass
class MotorCommand:
    """Final motor command built by the scheduler pipeline."""

    target_angles: dict[str, float] = field(default_factory=dict)


class Move(ABC):
    """Base class for all motion behaviors."""

    @abstractmethod
    def apply(self, obs: Observation, command: MotorCommand) -> None:
        """Read the observation and update the motor command in place."""
