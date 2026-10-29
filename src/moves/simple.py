# SPDX-License-Identifier: GPL-3.0-or-later
"""Simple moves: a class with ``step(obs) -> targets``, the same file in the simulator and on the robot.

A simple move needs no base class, so the hackathon's simulator (``climbing_sim.run_move``, ``microban_sim``) runs it
as it is, and so does the robot's program (src/moves/, found by moves/discover.py, or ``CONTROLLER=file.py``)::

    from microban_model import JOINTS

    class WaveMove:
        description = "..."                    # optional, one line for the dashboard
        variants = ("climber",)                # optional: the robot versions it is for (default: both)
        kp_fw = 125                            # optional: the servos' gain while it runs (default 125)
        options = {"amplitude": 0.3}           # optional: variables the dashboard edits live (int / float / bool)
        option_docs = {"amplitude": "rad"}
        sliders = {"speed": (0.0, 1.0, 0.5)}   # optional: name -> (min, max, start), shown while it runs
        keys = "arrows: ..."                   # optional: the keys it reads in the dashboard's keyboard zone

        def reset(self, obs): ...              # optional, when it starts
        def step(self, obs):                   # every 20 ms
            ... self.options["amplitude"], self.slider["speed"], self.pressed ...
            return targets                     # 19 angles (rad, order JOINTS), or None: keep the last ones
        def on_key(self, key, down): ...       # optional
        def on_option(self, name, value): ... # optional

``obs`` is what the simulator's ``observation()`` returns, built here from what the robot measures: ``q``, ``dq``
(joints, order JOINTS, every zero at the motor's zero), ``gyro`` (rad/s), ``accel`` (m/s^2), ``gravity`` (unit
vector) in the trunk frame, ``quat`` (trunk orientation w x y z), ``current`` (A), ``time`` (s). When it starts, the
torque goes on where the robot is (no move to the neutral pose first), so it may start hanging on the wall.

On the robot it is wrapped in a Move (:func:`wrap`): its options, sliders and keys are those of the advanced moves
(docs/moves.md), live in the dashboard; in the simulator nobody edits them and they keep their defaults.
"""
import importlib.util
import inspect
import math
import sys
from pathlib import Path

import microban_model
import numpy as np

from constants import IMU_MOUNT_QUAT, KP_DEFAULT, MOTOR_TO_ID
from moves.move import ALL, MotorCommand, Move, MoveState
from observer import Observation

JOINTS = list(microban_model.JOINTS)
G = 9.81
KP_SIMPLE = 125


def _quat_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


R_TRUNK_IMU = _quat_mat(IMU_MOUNT_QUAT)          # IMU vectors -> trunk frame


def observation(obs: Observation) -> dict:
    """The robot's measurements in the simulator's format (microban_sim's observation())."""
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


def is_simple(cls) -> bool:
    """A simple move: not a Move, with a step(self, obs) of its own."""
    if not inspect.isclass(cls) or issubclass(cls, Move) or not callable(getattr(cls, "step", None)):
        return False
    try:
        params = list(inspect.signature(cls.step).parameters.values())
    except (TypeError, ValueError):
        return False
    return len(params) == 2 and not inspect.isabstract(cls) and \
        all(p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params)


class SimpleMove(Move):
    """A simple move on the robot: its step(obs) every tick, its targets for the 19 joints; its options, sliders
    and keys as a Move's (set on the subclass :func:`wrap` makes, so the dashboard and the scheduler find them)."""
    power_up = "current"          # the torque goes on where the robot is (see Scheduler)

    def __init__(self, inner, controller=None):
        super().__init__()
        self.inner = inner
        self._controller = controller
        self._last = None
        self._share()

    def _share(self) -> None:
        """The move reads the values the dashboard sets: the same dicts, and the keys held now."""
        self.inner.options, self.inner.slider, self.inner.pressed = self.options, self.slider, self.pressed

    def _kp(self, kp) -> None:
        if self._controller is not None:
            ids = list(MOTOR_TO_ID.values())
            self._controller.sync_write_kp(ids, [int(kp)] * len(ids))

    def on_option(self, name, value) -> None:
        f = getattr(self.inner, "on_option", None)
        if callable(f):
            f(name, value)

    def on_key(self, key, down) -> None:
        self._share()
        f = getattr(self.inner, "on_key", None)
        if callable(f):
            f(key, down)

    def on_start(self, obs: Observation, command: MotorCommand) -> None:
        self._kp(getattr(self.inner, "kp_fw", KP_SIMPLE))
        o = observation(obs)
        self._last = o["q"].copy()
        self._share()
        if callable(getattr(self.inner, "reset", None)):
            self.inner.reset(o)
        self.state = MoveState.ACTIVE
        self.step(obs, command)

    def step(self, obs: Observation, command: MotorCommand) -> None:
        self._share()
        targets = self.inner.step(observation(obs))
        if targets is not None:
            targets = np.asarray(targets, float)
            if targets.shape != (len(JOINTS),):
                raise ValueError(f"{type(self.inner).__name__}.step must return {len(JOINTS)} targets "
                                 f"(order JOINTS), got {targets.shape}")
            self._last = targets
        command.target_angles.update(zip(JOINTS, self._last))

    def on_stop(self, obs: Observation, command: MotorCommand) -> None:
        self._kp(KP_DEFAULT)
        command.target_angles.update(zip(JOINTS, self._last))
        self.state = MoveState.INACTIVE


def wrap(inner, controller=None) -> SimpleMove:
    """The Move that runs the simple move ``inner`` on the robot, with its class's description, versions, options,
    sliders and keys."""
    cls = type(inner)
    attrs = {
        "description": getattr(cls, "description", "") or (cls.__doc__ or "").strip().split("\n")[0],
        "variants": tuple(getattr(cls, "variants", None) or ALL),
        "options": dict(getattr(cls, "options", {}) or {}),
        "option_docs": dict(getattr(cls, "option_docs", {}) or {}),
        "sliders": dict(getattr(cls, "sliders", {}) or {}),
        "keys": getattr(cls, "keys", "") or "",
        "__module__": __name__,
    }
    return type(cls.__name__, (SimpleMove,), attrs)(inner, controller)


def load_file(path: str, controller=None) -> dict:
    """The simple moves of a file anywhere (CONTROLLER=...), as {name: Move}; a class named Controller is
    "controller"."""
    from moves.discover import move_name
    path = Path(path).expanduser()
    spec = importlib.util.spec_from_file_location(f"user_moves_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    out = {}
    for _, cls in inspect.getmembers(module, inspect.isclass):
        if cls.__module__ == module.__name__ and is_simple(cls):
            name = "controller" if cls.__name__ == "Controller" else move_name(cls)
            out[name] = wrap(cls(), controller)
            print(f"Move {name} loaded from {path}", end="\r\n", flush=True)
    return out
