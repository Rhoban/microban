# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto

from observer import Observation
from constants import NEUTRAL_POSE


class MoveState(Enum):
    INACTIVE = auto()
    STARTING = auto()
    ACTIVE = auto()
    STOPPING = auto()


@dataclass
class MotorCommand:
    """
    Final motor command built by the scheduler pipeline.
    
    Initialized with the neutral pose.
    """

    target_angles: dict[str, float] = field(default_factory=lambda: dict(NEUTRAL_POSE))


class Move(ABC):
    """Base class for all motion behaviors (docs/moves.md)."""

    description: str = ""         # one line for the dashboard's Moves list (default: the class docstring's first line)
    power_up: str = "neutral"     # launched with the torque off: "neutral" ramps to NEUTRAL_POSE first (2 s),
                                  # "current" holds where the robot is (e.g. a move that may start on the wall)

    options: dict = {}            # settings the dashboard can change while the robot runs: name -> int / float / bool
    option_docs: dict = {}        # name -> one line, shown in the dashboard's editor

    sliders: dict = {}            # live controls in the dashboard's Moves card: name -> (min, max, start value);
                                  # read self.slider[name] in step(); back to its start value at each launch
    keys: str = ""                # the keys it reads, shown by the dashboard's keyboard zone, e.g. "arrows: turn the head"

    def __init__(self) -> None:
        self.state: MoveState = MoveState.INACTIVE
        self.options = dict(type(self).options)
        self.slider: dict[str, float] = {name: float(s[2]) for name, s in type(self).sliders.items()}
        self.pressed: set[str] = set()     # the keys held in the dashboard's keyboard zone ("a", "space", "ArrowUp"...)

    def on_option(self, name: str, value) -> None:
        """Called when the dashboard changed self.options[name] (already set), between two ticks."""

    def on_key(self, key: str, down: bool) -> None:
        """Called while the move runs (starting or on), between two ticks, when a key of the dashboard's keyboard zone
        is pressed (down=True) or released: "a" to "z", "0" to "9", "space", "ArrowUp", "Enter"... (self.pressed:
        the keys held now)."""

    def reset(self) -> None:
        """Called when em or init stops the move at once (on_stop is not called then): forget any transition in
        progress, so that the next launch starts cleanly. Override when on_start / on_stop keep state."""

    def preload(self) -> None:
        """Called before the control loop starts. Override to load heavy resources."""

    def on_start(self, obs: Observation, command: MotorCommand) -> None:
        """Called each tick while state is STARTING.
        Must set self.state = MoveState.ACTIVE when the transition is done."""
        self.state = MoveState.ACTIVE

    @abstractmethod
    def step(self, obs: Observation, command: MotorCommand) -> None:
        """Called each tick while state is ACTIVE."""

    def on_stop(self, obs: Observation, command: MotorCommand) -> None:
        """Called each tick while state is STOPPING.
        Must set self.state = MoveState.INACTIVE when the transition is done."""
        self.state = MoveState.INACTIVE