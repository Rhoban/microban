# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import math
from pathlib import Path

import numpy as np
import onnxruntime as ort
from microban_model import JOINTS

from constants import KP_RL, OBSERVATION_DOF_ORDER
from input.input_source import scale_velocity
from moves.move import R_TRUNK_IMU, _quat_mat

AGENTS = Path(__file__).parents[1] / "agents"
POLICY_FILES = {"classic": AGENTS / "walk.onnx", "climber": AGENTS / "walk_climber.onnx"}   # one per robot version
WALK_V1_SHOULDER_OFFSET = {"left_shoulder_pitch": math.pi / 2, "right_shoulder_pitch": math.pi / 2}
V1_IMU_QUAT = (0.5, -0.5, -0.5, 0.5)    # Microban v1's IMU site (w x y z): a v1 policy's gyro frame
FALLEN_GRAVITY_Z = -0.5           # projected gravity's z above this: fallen, no policy step
PHASE_STEPS = 20                  # the reference phase's period (ticks), for the policies that take it
ARROWS = {"ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"}


class Policy:
    """A walking policy (ONNX, exported by mjlab with its joint names and default pose). Trained on Microban v1
    (shoulder pitch 0 with the arm down, default 0 there) or on the v2 model (every zero at the motor's: default pi/2):
    a v1 policy gets the quarter turn of the shoulders and its gyro in v1's IMU frame."""

    def __init__(self, path: Path) -> None:
        self.session = ort.InferenceSession(str(path))
        self.input = self.session.get_inputs()[0]
        meta = self.session.get_modelmeta().custom_metadata_map
        default = dict(zip(meta["joint_names"].split(","), map(float, meta["default_joint_pos"].split(","))))
        self.v1 = abs(default["left_shoulder_pitch"]) < 0.5
        if self.v1:     # its inputs (angle - default) and outputs (default + action) stay the same
            default = {n: p + WALK_V1_SHOULDER_OFFSET.get(n, 0.0) for n, p in default.items()}
        self.default = np.array([default[n] for n in OBSERVATION_DOF_ORDER])
        self.r_imu_trunk = (_quat_mat(V1_IMU_QUAT) if self.v1 else R_TRUNK_IMU).T     # trunk -> its gyro frame
        # gyro(3) + gravity(3) + q, dq, last action (N each) + command(3) [+ the reference phase's cos, sin]
        self.use_phase = self.input.shape[1] > 3 + 3 + 3 * len(OBSERVATION_DOF_ORDER) + 3


class WalkMove:
    """Walk using a RL policy trained in simulation."""

    description = "Walk (learned policy): the velocity from the sticks / arrows"
    start_pose = "neutral"
    kp = KP_RL                     # the gain it was trained with
    # the dashboard: the arrows held in its keyboard zone walk at the slider's speed (a fraction of the maximum)
    sliders = {"speed": (0.0, 1.0, 0.5)}
    keys = "↑ ↓: forward / backward, ← →: turn (at the speed slider)"

    def __init__(self) -> None:
        # the robot versions it walks on: those with a policy (trained with their feet)
        self._policies = {v: Policy(f) for v, f in POLICY_FILES.items() if f.exists()}
        self.variants = tuple(self._policies)
        self._index = [JOINTS.index(n) for n in OBSERVATION_DOF_ORDER]

    def start(self, obs) -> None:
        self._p = self._policies[self.robot.variant or "classic"]
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
        if self._p.use_phase:
            self._phase_step = self._phase_step + 1 if np.mean(np.abs(cmd)) > 0.01 else 0

        # fallen (or no IMU reading this tick): no policy step, the joints hold where they are
        gravity = obs["gravity"]
        if np.isnan(gravity).any() or gravity[2] > FALLEN_GRAVITY_Z:
            return obs["q"]

        policy_obs = [
            self._p.r_imu_trunk @ obs["gyro"],     # the gyro in the IMU frame of the model it was trained on
            gravity,
            obs["q"][self._index] - self._p.default,
            obs["dq"][self._index],
            self._last_action,
            cmd,
        ]
        if self._p.use_phase:
            phase = (self._phase_step % PHASE_STEPS) / PHASE_STEPS * 2 * np.pi
            policy_obs.append([np.cos(phase), np.sin(phase)])
        x = np.concatenate([np.asarray(o, np.float32) for o in policy_obs])
        self._last_action = self._p.session.run(None, {self._p.input.name: [x]})[0][0].astype(float)
        return dict(zip(OBSERVATION_DOF_ORDER, (self._p.default + self._last_action).tolist()))
