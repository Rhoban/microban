# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud
"""A move: a class with ``step(obs) -> targets``, no base class, the same file in the simulator and on the robot.

The robot's program finds every move of src/moves/ by itself (moves/discover.py) and runs it through a
:class:`Runner`; the simulators run the same class with ``run_move`` (microban_sim, climbing_sim)::

    class WaveMove:
        description = "..."                    # one line for the dashboard (default: the docstring's first line)
        variants = ("climber",)                # the robot versions it is for (default: both)
        start_pose = "current"                 # torque on where the robot is; "neutral": the standing pose first (2 s)
        kp = 125                               # the servos' gain while it runs (default: the robot's, KP_DEFAULT)
        options = {"amplitude": 0.3}           # variables the dashboard edits live (int / float / bool)
        option_docs = {"amplitude": "rad"}
        sliders = {"speed": (0.0, 1.0, 0.5)}   # name -> (min, max, start), shown while it runs
        keys = "arrows: ..."                   # the keys it reads in the dashboard's keyboard zone

        def start(self, obs): ...              # when it starts
        def step(self, obs):                   # every 20 ms
            ... self.options["amplitude"], self.slider["speed"], self.pressed, self.velocity ...
            return targets                     # 19 angles (order JOINTS) or {joint: angle}; None: it is over
        def stopping(self, obs): ...           # once stopped, every 20 ms until it returns None (a smooth stop)
        def on_key(self, key, down): ...
        def on_option(self, name, value): ...

Everything but step is optional. ``obs`` is the simulator's observation (microban_sim's observation()), built here from
what the robot measures (:func:`observation`).
"""
import inspect
import math
from dataclasses import dataclass, field
from enum import Enum, auto

import microban_model
import numpy as np

from constants import IMU_MOUNT_QUAT, MOTOR_TO_ID, NEUTRAL_POSE
from observer import Observation

# The versions of the robot: walking hands and feet (classic), or the climbing forearms and feet (climber). A move may
# say which ones it is made for: variants = ALL (the default), (CLASSIC,) or (CLIMBER,); the dashboard lists it only
# for those.
CLASSIC, CLIMBER = "classic", "climber"
ALL = (CLASSIC, CLIMBER)

JOINTS = list(microban_model.JOINTS)
G = 9.81
NO_VELOCITY = {"vx": 0.0, "vy": 0.0, "vtheta": 0.0}


class MoveState(Enum):
    INACTIVE = auto()
    ACTIVE = auto()
    STOPPING = auto()


@dataclass
class MotorCommand:
    """The joints' targets sent this tick (joint name -> rad)."""

    target_angles: dict[str, float] = field(default_factory=lambda: dict(NEUTRAL_POSE))


def _quat_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


R_TRUNK_IMU = _quat_mat(IMU_MOUNT_QUAT)          # IMU vectors -> trunk frame


def observation(obs: Observation) -> dict:
    """The robot's measurements in the simulator's format: q, dq (order JOINTS, every zero at the motor's zero), gyro
    (rad/s), accel (m/s^2), gravity (unit vector) in the trunk frame, quat (trunk orientation w x y z), current (A),
    time (s); NaN where a sensor gave nothing this tick."""
    s = obs.robot_state
    nan3 = [math.nan] * 3
    current = s.measured_currents or s.motor_currents
    return {"q": np.array([s.motor_positions[n] for n in JOINTS]),
            "dq": np.array([s.motor_velocities[n] for n in JOINTS]),
            "gyro": R_TRUNK_IMU @ np.array(s.gyro or nan3),
            "accel": R_TRUNK_IMU @ np.array(s.acc or nan3) * G,              # the IMU reads g
            "gravity": np.array(s.projected_gravity or nan3),
            "quat": np.array(s.body_quat or [math.nan] * 4),
            "current": np.array([abs(current.get(n, math.nan)) for n in JOINTS]) if current else np.full(19, math.nan),
            "time": s.time_s}


def is_move(cls) -> bool:
    """A move: a class with a step(self, obs)."""
    if not inspect.isclass(cls) or inspect.isabstract(cls) or not callable(getattr(cls, "step", None)):
        return False
    try:
        params = list(inspect.signature(cls.step).parameters.values())
    except (TypeError, ValueError):
        return False
    return len(params) == 2 and all(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params)


def targets_dict(targets) -> dict[str, float]:
    """A move's targets as joint name -> rad: 19 angles in the order JOINTS, or a dict of some joints."""
    if isinstance(targets, dict):
        unknown = set(targets) - set(JOINTS)
        if unknown:
            raise ValueError(f"unknown joints {sorted(unknown)} (microban_model.JOINTS)")
        return {n: float(v) for n, v in targets.items()}
    targets = np.asarray(targets, float)
    if targets.shape != (len(JOINTS),):
        raise ValueError(f"step must return {len(JOINTS)} targets (order JOINTS) or a dict, got shape {targets.shape}")
    return dict(zip(JOINTS, targets.tolist()))


class Robot:
    """``self.robot`` of a move: the robot's raw measurements and its servos one by one, for the moves that need more
    than obs and targets (the simulators give the same methods: microban_sim's run_move).

    * ``variant``: the robot's version, "classic" or "climber" (None in the simulators).
    * ``state``: this tick's raw measurements (observer.RobotState: the IMU in its chip's frame, the motors' voltages,
      currents by joint name...); None in the simulators.
    * ``set_kp(kp, joints=None)``: the servos' gain, of these joints (names) or all of them, written by the program
      after this tick (over the moves' ``kp``); back to the robot's when the move stops (in the simulators: every joint
      at once only).
    * ``set_torque(on, joints=None)``: torque off (the joint goes limp at once) or back on. Back on: after this tick's
      targets, held where the joint is (no jump). Back on by itself when the move stops.
    """

    def __init__(self, controller=None) -> None:
        self.controller = controller                              # set by the scheduler
        self.variant = None                                       # the robot's version (classic / climber)
        self.state = None
        self.kp: dict[str, int] = {}                             # the gains this move set (joint -> kp)
        self.limp: set[str] = set()                               # joints this move turned off
        self.to_enable: set[str] = set()                          # back on after this tick's targets

    @staticmethod
    def _joints(joints) -> list[str]:
        names = list(JOINTS) if joints is None else [joints] if isinstance(joints, str) else list(joints)
        unknown = set(names) - set(JOINTS)
        if unknown:
            raise ValueError(f"unknown joints {sorted(unknown)} (microban_model.JOINTS)")
        return names

    def set_kp(self, kp, joints=None) -> None:
        kp = int(kp)
        if not 0 <= kp <= 1000:
            raise ValueError(f"kp {kp}: the servos take 0 to 1000 (the robot runs 400, learned policies 125)")
        self.kp.update(dict.fromkeys(self._joints(joints), kp))

    def set_torque(self, on: bool, joints=None) -> None:
        names = set(self._joints(joints))
        if on:
            self.to_enable |= names & self.limp
            self.limp -= names
        else:
            ids = [MOTOR_TO_ID[n] for n in sorted(names)]
            self.controller.sync_write_torque_enable(ids, [False] * len(ids))
            self.limp |= names
            self.to_enable -= names


class Runner:
    """A move in the robot's program: its state, what the dashboard sets (options, sliders, keys) and the velocity
    asked (sticks / arrows), given to the move as attributes, and its calls."""

    def __init__(self, move) -> None:
        cls = type(move)
        self.move = move
        self.file = inspect.getsourcefile(cls)                    # where its errors are (the dashboard's events)
        self.description = getattr(move, "description", "") or (cls.__doc__ or "").strip().split("\n")[0]
        self.variants = tuple(getattr(move, "variants", None) or ALL)
        self.start_pose = getattr(move, "start_pose", "current")
        if self.start_pose not in ("current", "neutral"):
            raise ValueError(f"start_pose must be 'current' or 'neutral', not {self.start_pose!r}")
        self.kp = getattr(move, "kp", None)
        if self.kp is not None and not (isinstance(self.kp, (int, float)) and 0 <= self.kp <= 1000):
            raise ValueError(f"kp must be a number from 0 to 1000, not {self.kp!r}")
        if "robot" in vars(move):
            raise ValueError("self.robot is the program's (the servos one by one): name yours differently "
                             "(e.g. self.model)")
        # the class's attributes, or the instance's when its __init__ set them
        self.option_docs = dict(getattr(move, "option_docs", {}) or {})
        self.sliders = dict(getattr(move, "sliders", {}) or {})
        self.keys = getattr(move, "keys", "") or ""
        self.state = MoveState.INACTIVE
        # the move reads them as its own attributes: the same objects
        move.options = self.options = dict(getattr(move, "options", {}) or {})
        move.slider = self.slider = {n: float(s[2]) for n, s in self.sliders.items()}
        move.pressed = set()
        move.velocity = dict(NO_VELOCITY)
        move.robot = self.robot = Robot()

    def set_inputs(self, pressed: set[str], velocity: dict[str, float], state=None) -> None:
        self.move.pressed, self.move.velocity = set(pressed), dict(velocity)
        if state is not None:
            self.robot.state = state

    def start(self, obs: Observation) -> None:
        """Asked: its sliders back to their start values, then its start()."""
        self.slider.update({n: float(s[2]) for n, s in self.sliders.items()})
        self.state = MoveState.ACTIVE
        if callable(getattr(self.move, "start", None)):
            self.move.start(observation(obs))

    def tick(self, obs: Observation) -> dict[str, float]:
        """Its targets this tick (step while it runs, stopping once stopped); {} when it has nothing more to say."""
        if self.state == MoveState.ACTIVE:
            targets = self.move.step(observation(obs))
            if targets is not None:
                return targets_dict(targets)
            self.state = MoveState.STOPPING                       # over by itself
        if self.state == MoveState.STOPPING:
            stopping = getattr(self.move, "stopping", None)
            targets = stopping(observation(obs)) if callable(stopping) else None
            if targets is not None:
                return targets_dict(targets)
            self.state = MoveState.INACTIVE
        return {}

    def on_option(self, name, value) -> None:
        if callable(getattr(self.move, "on_option", None)):
            self.move.on_option(name, value)

    def on_key(self, key, down) -> None:
        if callable(getattr(self.move, "on_key", None)):
            self.move.on_key(key, down)
