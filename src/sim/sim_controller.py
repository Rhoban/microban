# SPDX-License-Identifier: GPL-3.0-or-later
"""The robot's program on a simulated robot (``make sim``) — never deployed to the robot.

The simulation is Rhoban's robot simulator, ``microban_sim`` (github.com/Rhoban/microban_sim): the robot on the
floor (``MicrobanSim``, classic or climbing version), or the hackathon's climbing wall (``climbing_sim.ClimbingSim``,
github.com/rock-climbing-robots/simulator, built on it). This controller gives the robot's program what the real
robot gives it (the protocol of src/controller.py): it writes the joint targets and the servos' gain and torque to the
simulation, and reads back what the robot's sensors read, with their delays (the joints, the motor currents, the IMU
in its chip's frame). The moves and the dashboard work as on the robot; the keys are typed in the viewer's window
(no gamepad here).

The robot is held where it starts until the torque first goes on (on the real robot, someone holds it until a move
is launched).
"""
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from microban_sim import JOINTS

from constants import ID_TO_MOTOR, KP_DEFAULT

if TYPE_CHECKING:
    from sim.mujoco_input import MuJoCoInputSource

G = 9.81


class SimController:
    """The robot's program on a ``microban_sim.MicrobanSim`` (same methods as RobotController). ``start``: called to
    put the robot back at its start (key [r]), e.g. ``sim.reset`` or ``sim.reset_hanging``."""

    def __init__(
        self,
        sim,
        start: Callable[[], object],
        key_callback: Callable[[int], None] | None = None,
        stop_flag_path: str = "/tmp/microban_scheduler.stop",
        reset_source: "MuJoCoInputSource | None" = None,
    ) -> None:
        self.sim = sim
        self._start = start
        self._stop_flag_path = Path(stop_flag_path)
        self._reset_source = reset_source
        self._index = {mid: JOINTS.index(name) for mid, name in ID_TO_MOTOR.items()}   # motor ID -> sim order
        self.sim.servos.kp = KP_DEFAULT
        self._kp = dict.fromkeys(ID_TO_MOTOR, KP_DEFAULT)                     # motor ID -> the gain written
        self._kp_warned = False
        self._torque_t = 0.0
        self.reset(sync=False)
        self._viewer = sim.view(realtime=False, key_callback=key_callback)   # the scheduler keeps the pace

    def close(self) -> None:
        """Close MuJoCo's viewer window."""
        self._viewer.close()

    @property
    def viewer_opt(self):
        return self._viewer.opt

    def reset(self, sync: bool = True) -> None:
        """Back to the start: as the robot's program starts, torque off, held there until the torque goes on."""
        self._start()
        self._torque_t = 0.0
        self.sim.set_torque(False)
        self._held = True
        self._obs, self._imu = self.sim.observation(), self.sim.imu_raw()
        self._target = self.sim.joint_positions()
        if sync:
            self._viewer.sync()

    # ---- writes ------------------------------------------------------------------------------------------
    def sync_write_kp(self, ids: list[int], gains: list[int]) -> None:
        """The simulated servos share one gain: the one most joints have (a per-joint set_kp is the robot's only)."""
        for mid, g in zip(ids, gains):
            self._kp[mid] = int(g)
        values = list(self._kp.values())
        self.sim.servos.kp = max(set(values), key=values.count)
        if len(set(values)) > 1 and not self._kp_warned:
            print("Simulation: per-joint servo gains are the robot's only; the simulated servos keep one gain "
                  f"({self.sim.servos.kp:g})", end="\r\n", flush=True)
            self._kp_warned = True

    def sync_read_kp(self, ids: list[int]) -> list[int]:
        return [self._kp[mid] for mid in ids]

    def sync_write_torque_enable(self, ids: list[int], values: list[bool]) -> None:
        on = self.sim.servos.torque.copy()
        for mid, v in zip(ids, values):
            on[self._index[mid]] = bool(v)
        if on.any():
            self._held = False
        self.sim.set_torque(on)

    def sync_write_status_return_level(self, ids: list[int], levels: list[int]) -> None:
        pass

    def sync_write_goal_position(self, ids: list[int], positions: list[float]) -> None:
        """The targets of this tick, then one control step of simulation (the scheduler calls it once per tick)."""
        if not self._viewer.is_running():
            self._stop_flag_path.write_text("stop\n", encoding="ascii")
            return
        for mid, p in zip(ids, positions):
            self._target[self._index[mid]] = p
        if self._held:
            self._viewer.sync()
        else:
            self.sim.step(self._target)
        if self._reset_source is not None and self._reset_source.consume_reset():
            self.reset()
            return
        if self._reset_source is not None and self._reset_source.show_torque and self.sim.data.time >= self._torque_t:
            self._torque_t = self.sim.data.time + 0.5          # twice a second ([t] in the viewer: off)
            print(f"Torque sum: {float(np.abs(self.sim.data.actuator_force).sum()):.3f} Nm ([t] in the viewer: off)")
        self._obs, self._imu = self.sim.observation(), self.sim.imu_raw()

    # ---- reads (what the robot's sensors read, with their delays) ---------------------------------------
    def sync_read_state(self, ids: list[int]) -> tuple[list[float], list[float], list[float]]:
        """Positions (rad), velocities (rad/s) and currents (A) at once, as the real robot reads them (the observer
        then gives the moves the motor currents, and the dashboard shows them)."""
        return (self.sync_read_present_position(ids), self.sync_read_present_velocity(ids),
                self.sync_read_present_current(ids))

    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        return [float(self._obs["q"][self._index[mid]]) for mid in ids]

    def read_present_position(self, motor_id: int) -> float:
        return float(self._obs["q"][self._index[motor_id]])

    def sync_read_present_velocity(self, ids: list[int]) -> list[float]:
        return [float(self._obs["dq"][self._index[mid]]) for mid in ids]

    def read_present_velocity(self, motor_id: int) -> float:
        return float(self._obs["dq"][self._index[motor_id]])

    def sync_read_present_current(self, ids: list[int]) -> list[float]:
        return [float(self._obs["current"][self._index[mid]]) for mid in ids]

    def sync_read_present_input_voltage(self, ids: list[int]) -> list[float]:
        return [80.0] * len(ids)

    def read_present_input_voltage(self, motor_id: int) -> float:
        return 80.0

    def read_acc(self) -> tuple[float, float, float]:
        """The accelerometer in g, in the IMU chip's frame (+1 g along the axis that points up at rest)."""
        return tuple(float(v) / G for v in self._imu["accel"])

    def read_gyro(self) -> tuple[float, float, float]:
        return tuple(float(v) for v in self._imu["gyro"])

    def read_quat(self, dt: float) -> tuple[float, float, float, float]:
        return tuple(float(v) for v in self._imu["quat"])

