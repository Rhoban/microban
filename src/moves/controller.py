# SPDX-License-Identifier: GPL-3.0-or-later
"""Your own controller as a move: the same file runs in Rhoban's robot simulator (microban_sim.run_controller, or the
hackathon's climbing_sim built on it) and here, on the robot or in its simulation (make sim).

    make run CONTROLLER=path/to/my_controller.py            (robot)      keyboard [c] / gamepad [Y]: start / stop it
    make sim WALL=N2 CONTROLLER=path/to/my_controller.py    (the robot's program on the simulated wall)

The file defines ``class Controller`` with:

* ``step(obs) -> targets``: the 19 joint targets (rad, in the order of ``microban_model.JOINTS``), or None to keep the
  last ones; called every 20 ms;
* optionally ``reset(obs)`` (called when it starts) and ``kp_fw`` (the servos' gain while it runs; default 125).

``obs`` is what the simulator's ``observation()`` returns, built from what the robot measures: ``q``, ``dq`` (joints, order
JOINTS, every zero at the motor's zero), ``gyro`` (rad/s), ``accel`` (m/s^2), ``gravity`` (unit vector) in the trunk
frame, ``quat`` (trunk orientation w x y z), ``current`` (A), ``time`` (s). When it starts, the torque goes on where
the robot is (no move to the neutral pose first), so it may start hanging on the wall.
"""
import importlib.util
import math
from pathlib import Path

import microban_model
import numpy as np

from constants import IMU_MOUNT_QUAT, KP_DEFAULT, MOTOR_TO_ID
from moves.move import CLIMBER, MotorCommand, Move, MoveState
from observer import Observation

JOINTS = list(microban_model.JOINTS)
G = 9.81
KP_CONTROLLER = 125


def _quat_mat(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


R_TRUNK_IMU = _quat_mat(IMU_MOUNT_QUAT)          # IMU vectors -> trunk frame


def observation(obs: Observation) -> dict:
    """The robot's measurements in the simulator's format (microban_sim's MicrobanSim.observation())."""
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


def load_controller(path: str):
    spec = importlib.util.spec_from_file_location("user_controller", Path(path).expanduser())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Controller()


class ControllerMove(Move):
    description = "Your Controller file (CONTROLLER=...), the same as in the simulator"
    variants = (CLIMBER,)         # the climbing simulator's robot
    power_up = "current"          # the torque goes on where the robot is (see Scheduler)

    def __init__(self, path: str, controller=None):
        super().__init__()
        self.path = path
        self.ctrl = load_controller(path)
        self._controller = controller
        self._last = None
        print(f"Controller loaded from {path} (start / stop it like a move)", end="\r\n", flush=True)

    def _kp(self, kp) -> None:
        if self._controller is not None:
            ids = list(MOTOR_TO_ID.values())
            self._controller.sync_write_kp(ids, [int(kp)] * len(ids))

    def on_start(self, obs: Observation, command: MotorCommand) -> None:
        self._kp(getattr(self.ctrl, "kp_fw", KP_CONTROLLER))
        o = observation(obs)
        self._last = o["q"].copy()
        if hasattr(self.ctrl, "reset"):
            self.ctrl.reset(o)
        self.state = MoveState.ACTIVE
        self.step(obs, command)

    def step(self, obs: Observation, command: MotorCommand) -> None:
        targets = self.ctrl.step(observation(obs))
        if targets is not None:
            targets = np.asarray(targets, float)
            if targets.shape != (len(JOINTS),):
                raise ValueError(f"Controller.step must return {len(JOINTS)} targets (order JOINTS), got {targets.shape}")
            self._last = targets
        command.target_angles.update(zip(JOINTS, self._last))

    def on_stop(self, obs: Observation, command: MotorCommand) -> None:
        self._kp(KP_DEFAULT)
        command.target_angles.update(zip(JOINTS, self._last))
        self.state = MoveState.INACTIVE
