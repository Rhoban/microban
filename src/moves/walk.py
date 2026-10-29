# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import math
from pathlib import Path

import numpy as np
import onnxruntime as ort
from microban_model import JOINTS

from constants import KP_RL, OBSERVATION_DOF_ORDER
from input.input_source import scale_velocity
from moves.move import R_TRUNK_IMU

AGENT = Path(__file__).parents[1] / "agents" / "walk.onnx"
WALK_V1_SHOULDER_OFFSET = {"left_shoulder_pitch": math.pi / 2, "right_shoulder_pitch": math.pi / 2}
FALLEN_GRAVITY_Z = -0.5           # projected gravity's z above this: fallen, no policy step
PHASE_STEPS = 20                  # the reference phase's period (ticks), for the policies that take it
ARROWS = {"ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}


class WalkMove:
    """Walk using a RL policy trained in simulation."""

    description = "Walk (learned policy): the velocity from the sticks / arrows"
    variants = ("classic",)          # its policy was trained with the walking feet
    start_pose = "neutral"
    kp = KP_RL                     # the gain it was trained with
    # the dashboard: the arrows held in its keyboard zone walk at the slider's speed (a fraction of the maximum)
    sliders = {"speed": (0.0, 1.0, 0.5)}
    keys = "↑ ↓: forward / backward, ← →: turn (at the speed slider)"

    def __init__(self) -> None:
        self._session = ort.InferenceSession(str(AGENT))
        self._input = self._session.get_inputs()[0]
        meta = self._session.get_modelmeta().custom_metadata_map
        names = meta["joint_names"].split(",")
        positions = [float(v) for v in meta["default_joint_pos"].split(",")]
        # The policy was trained on Microban v1, whose shoulder pitch is 0 with the arm down: a quarter turn from the
        # motors' zero used here. Its inputs (angle - default) and outputs (default + action) stay the same.
        default = {n: p + WALK_V1_SHOULDER_OFFSET.get(n, 0.0) for n, p in zip(names, positions)}
        self._index = [JOINTS.index(n) for n in OBSERVATION_DOF_ORDER]
        self._default = np.array([default[n] for n in OBSERVATION_DOF_ORDER])
        # gyro(3) + gravity(3) + q, dq, last action (N each) + command(3) [+ the reference phase's cos, sin]
        self._use_phase = self._input.shape[1] > 3 + 3 + 3 * len(OBSERVATION_DOF_ORDER) + 3

    def start(self, obs) -> None:
        self._last_action = np.zeros(len(OBSERVATION_DOF_ORDER))      # a new walk
        self._phase_step = 0

    def command(self) -> dict[str, float]:
        """The velocity to walk at: the dashboard's arrows while some are held, else the gamepad's / keyboard's."""
        arrows = ARROWS & self.pressed
        if not arrows:
            return self.velocity
        speed = self.slider["speed"]
        forward = ("ArrowUp" in arrows) - ("ArrowDown" in arrows)
        left = ("ArrowLeft" in arrows) - ("ArrowRight" in arrows)
        return scale_velocity({"vx": forward * speed, "vy": 0.0, "vtheta": left * speed})

    def step(self, obs):
        v = self.command()
        cmd = [v["vx"], v["vy"], v["vtheta"]]
        if self._use_phase:
            self._phase_step = self._phase_step + 1 if np.mean(np.abs(cmd)) > 0.01 else 0

        # fallen (or no IMU reading this tick): no policy step, the joints hold where they are
        gravity = obs["gravity"]
        if np.isnan(gravity).any() or gravity[2] > FALLEN_GRAVITY_Z:
            return obs["q"]

        policy_obs = [
            R_TRUNK_IMU.T @ obs["gyro"],      # the policy was trained with the gyro in the IMU's frame
            gravity,
            obs["q"][self._index] - self._default,
            obs["dq"][self._index],
            self._last_action,
            cmd,
        ]
        if self._use_phase:
            phase = (self._phase_step % PHASE_STEPS) / PHASE_STEPS * 2 * np.pi
            policy_obs.append([np.cos(phase), np.sin(phase)])
        x = np.concatenate([np.asarray(o, np.float32) for o in policy_obs])
        self._last_action = self._session.run(None, {self._input.name: [x]})[0][0].astype(float)
        return dict(zip(OBSERVATION_DOF_ORDER, (self._default + self._last_action).tolist()))
