# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import math

from microban_model import JOINTS

HEAD = JOINTS.index("head")
LERP_S = 0.5                      # the head goes to 0 (and back at the end) in this time


def _lerp(start: float, t: float) -> float:
    """From start to 0 in LERP_S, t seconds after it began."""
    return start * (1.0 - min(t / LERP_S, 1.0))


class HeadMove:
    """Turn the head left and right: a sine between +/- amplitude, frequency Hz; it reaches 0 smoothly first, and goes
    back there when stopped."""

    description = "Turn the head left and right"
    options = {"frequency": 0.35, "amplitude": math.pi / 4}
    option_docs = {"frequency": "turns per second (Hz)", "amplitude": "half the swing (rad)"}

    def start(self, obs) -> None:
        self.t0, self.from_angle = obs["time"], obs["q"][HEAD]
        self.stop_t0 = None

    def step(self, obs):
        t = obs["time"] - self.t0
        if t < LERP_S:
            return {"head": _lerp(self.from_angle, t)}
        t -= LERP_S
        return {"head": self.options["amplitude"] * math.sin(2.0 * math.pi * self.options["frequency"] * t)}

    def stopping(self, obs):
        if self.stop_t0 is None:
            self.stop_t0, self.from_angle = obs["time"], obs["q"][HEAD]
        t = obs["time"] - self.stop_t0
        return {"head": _lerp(self.from_angle, t)} if t < LERP_S else None

