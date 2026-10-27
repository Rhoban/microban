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

    def __init__(self) -> None:
        self.state: MoveState = MoveState.INACTIVE
        self.options = dict(type(self).options)

    def on_option(self, name: str, value) -> None:
        """Called when the dashboard changed self.options[name] (already set), between two ticks."""

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