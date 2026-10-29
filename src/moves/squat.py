# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import math
import microban_model
import placo

import numpy as np

from microban_model import JOINTS

from constants import NEUTRAL_POSE

_LOWER_JOINTS = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch",
    "left_knee", "left_ankle_pitch", "left_ankle_roll",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch",
    "right_knee", "right_ankle_pitch", "right_ankle_roll",
]

_UPPER_JOINTS = [
    "left_shoulder_pitch", "left_shoulder_roll", "left_elbow",
    "right_shoulder_pitch", "right_shoulder_roll", "right_elbow",
]


_JOINTS = _LOWER_JOINTS + _UPPER_JOINTS
_INDEX = [JOINTS.index(n) for n in _JOINTS]
LERP_S = 1.0                      # to the squat's start pose, and back to the neutral pose when stopped


class SquatMove:
    """Squat up and down: the centre of mass goes down and up (inverse kinematics, placo), the feet flat."""

    description = "Squat up and down (inverse kinematics)"
    variants = ("classic",)          # its inverse kinematics uses the walking feet
    start_pose = "neutral"
    options = {"frequency": 0.3, "amplitude": 0.02}
    option_docs = {"frequency": "squats per second (Hz)", "amplitude": "how far the centre of mass goes down (m)"}

    def __init__(self) -> None:
        self._robot = placo.RobotWrapper(str(microban_model.URDF_DIR))
        self._solver = placo.KinematicsSolver(self._robot)

        for name, angle in NEUTRAL_POSE.items():
            self._robot.set_joint(name, angle)
        self._T_left_foot = np.eye(4)
        self._robot.set_T_world_frame("left_foot", self._T_left_foot)
        self._robot.update_kinematics()

        self._com_initial = self._robot.com_world()
        T_right_foot = self._robot.get_T_world_frame("right_foot").copy()
        T_right_foot[2, 3] = 0.0

        self._left_foot_task = self._solver.add_frame_task("left_foot", self._T_left_foot)
        self._left_foot_task.configure("left_foot", "hard", 1.0)
        self._right_foot_task = self._solver.add_frame_task("right_foot", T_right_foot)
        self._right_foot_task.configure("right_foot", "hard", 1.0)

        self._com_task = self._solver.add_com_task(self._com_initial)
        self._com_task.configure("com", "soft", 100.0)

        trunk_task = self._solver.add_orientation_task("trunk", np.eye(3))
        trunk_task.configure("trunk_orient", "soft", 1.0)

        joints_task = self._solver.add_joints_task()
        joints_task.set_joints({name: NEUTRAL_POSE[name] for name in _UPPER_JOINTS})
        joints_task.configure("upper_body", "soft", 1.0)

        joints_task = self._solver.add_joints_task()
        joints_task.set_joints({name: NEUTRAL_POSE[name] for name in _LOWER_JOINTS})
        joints_task.configure("lower_body", "soft", 1e-3)

        self._solver.add_regularization_task(1e-6)

        for _ in range(50):
            self._solver.solve(True)
            self._robot.update_kinematics()

        self._start_target_angles = [self._robot.get_joint(name) for name in _LOWER_JOINTS + _UPPER_JOINTS]
        self._start_angles = [self._robot.get_joint(name) for name in _JOINTS]

    def start(self, obs) -> None:
        self.t0, self.from_angles = obs["time"], obs["q"][_INDEX].tolist()
        self.stop_t0 = None
        for name, angle in zip(_JOINTS, self._start_angles):
            self._robot.set_joint(name, angle)
        self._robot.set_T_world_frame("left_foot", self._T_left_foot)
        self._robot.update_kinematics()
        self._com_task.target_world = self._com_initial.copy()

    def step(self, obs):
        t = obs["time"] - self.t0
        if t < LERP_S:                                    # to the squat's start pose first
            return _lerp(self.from_angles, self._start_angles, t)
        t -= LERP_S
        p_com = self._com_initial.copy()
        p_com[2] -= self.options["amplitude"] * (1.0 - math.cos(2.0 * math.pi * self.options["frequency"] * t))
        self._com_task.target_world = p_com
        self._solver.solve(True)
        self._robot.update_kinematics()
        return {name: self._robot.get_joint(name) for name in _JOINTS}

    def stopping(self, obs):
        if self.stop_t0 is None:                          # back to the neutral pose
            self.stop_t0, self.from_angles = obs["time"], obs["q"][_INDEX].tolist()
        t = obs["time"] - self.stop_t0
        return _lerp(self.from_angles, [NEUTRAL_POSE[n] for n in _JOINTS], t) if t < LERP_S else None


def _lerp(start: list[float], end: list[float], t: float) -> dict[str, float]:
    a = min(t / LERP_S, 1.0)
    return {n: s * (1.0 - a) + e * a for n, s, e in zip(_JOINTS, start, end)}
