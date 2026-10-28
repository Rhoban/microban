# SPDX-License-Identifier: GPL-3.0-or-later

from observer import Observation
from moves.move import MotorCommand, Move

KEY_SPEED = 1.0                   # rad/s while an arrow key is held


class LookMove(Move):
    """Turn the head from the dashboard: with its slider, or with the arrow keys held in the keyboard zone.

    An example of the moves' live controls (docs/moves.md): `sliders` puts a slider in the dashboard's Moves card,
    read here in self.slider; `keys` shows the keyboard zone, whose held keys are in self.pressed. The keys move the
    slider itself, so the page shows where the head goes.
    """

    description = "Turn the head from the dashboard (slider, or the ← → keys)"
    sliders = {"head": (-0.8, 0.8, 0.0)}         # rad: min, max, start
    keys = "← →: turn the head"

    def __init__(self) -> None:
        super().__init__()
        self._last_t = None

    def on_start(self, obs: Observation, command: MotorCommand) -> None:
        self._last_t = obs.robot_state.time_s
        super().on_start(obs, command)

    def step(self, obs: Observation, command: MotorCommand) -> None:
        t = obs.robot_state.time_s
        dt, self._last_t = t - self._last_t, t
        turn = ("ArrowLeft" in self.pressed) - ("ArrowRight" in self.pressed)
        low, high, _ = self.sliders["head"]
        self.slider["head"] = min(max(self.slider["head"] + turn * KEY_SPEED * dt, low), high)
        command.target_angles["head"] = self.slider["head"]
