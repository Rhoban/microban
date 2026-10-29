# SPDX-License-Identifier: GPL-3.0-or-later

KEY_SPEED = 1.0                   # rad/s while an arrow key is held


class LookMove:
    """Turn the head from the dashboard: with its slider, or with the arrow keys held in the keyboard zone.

    An example of the moves' live controls (docs/moves.md): `sliders` puts a slider in the dashboard's Moves card,
    read here in self.slider; `keys` shows the keyboard zone, whose held keys are in self.pressed. The keys move the
    slider itself, so the page shows where the head goes.
    """

    description = "Turn the head from the dashboard (slider, or the ← → keys)"
    sliders = {"head": (-0.8, 0.8, 0.0)}         # rad: min, max, start
    keys = "← →: turn the head"

    def start(self, obs) -> None:
        self.last_t = obs["time"]

    def step(self, obs):
        dt, self.last_t = obs["time"] - self.last_t, obs["time"]
        turn = ("ArrowLeft" in self.pressed) - ("ArrowRight" in self.pressed)
        low, high, _ = self.sliders["head"]
        self.slider["head"] = min(max(self.slider["head"] + turn * KEY_SPEED * dt, low), high)
        return {"head": self.slider["head"]}
