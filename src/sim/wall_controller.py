# SPDX-License-Identifier: GPL-3.0-or-later
"""The robot on the climbing wall, simulated by the hackathon's simulator (``make sim WALL=N2``) — never deployed.

The simulator is the ``climbing_sim`` package of github.com/rock-climbing-robots/simulator, cloned next to this
folder (``../simulator``, see docs/simulation.md): ``make sim WALL=...`` runs it from there, so a change made in it
applies at once. This controller gives the robot's program what the real robot gives it (the protocol of
src/controller.py): it writes the joint targets and the servos' gain and torque to ``ClimbingSim``, which simulates
the wall, the holds and the 19 servos (BAM), and reads back the joints, the motor currents and the IMU, with the
robot's sensor delays. The moves, the keyboard, the gamepad and the dashboard work as on the robot.

The robot starts hanging on the wall's start holds (``start="hang"``) or standing in front of it (``"floor"``), held
there until the torque first goes on (on the real robot, someone holds it until a move is launched).
"""
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import mujoco
import mujoco.viewer
import numpy as np

from constants import ID_TO_MOTOR, KP_DEFAULT, MOTOR_TO_ID
from sim.mujoco_controller import _DelayBuffer

if TYPE_CHECKING:
    from sim.mujoco_input import MuJoCoInputSource

try:
    import climbing_sim
except ImportError as e:
    raise SystemExit("The climbing simulator is not found: clone it next to this folder "
                     "(git clone https://github.com/rock-climbing-robots/simulator ../simulator), "
                     "see docs/simulation.md") from e


class WallController:
    """The robot's program on ClimbingSim (same methods as RobotController / MuJoCoController)."""

    def __init__(
        self,
        wall: str = "N2",
        start: str = "hang",
        key_callback: Callable[[int, int, int, int], None] | None = None,
        stop_flag_path: str = "/tmp/microban_scheduler.stop",
        reset_source: "MuJoCoInputSource | None" = None,
        # sensor delays (motor / IMU -> program), in ticks of 20 ms: as make sim's defaults
        delay_pos_ticks: int = 0,
        delay_vel_ticks: int = 1,
        delay_gyro_ticks: int = 3,
        delay_quat_ticks: int = 4,
    ) -> None:
        self._stop_flag_path = Path(stop_flag_path)
        self._reset_source = reset_source
        self._start = start
        self.sim = climbing_sim.ClimbingSim(wall, cameras=[], kp_fw=KP_DEFAULT)
        self._model, self._data = self.sim.model, self.sim.data
        self._index = {mid: climbing_sim.JOINTS.index(name) for mid, name in ID_TO_MOTOR.items()}
        self._delays = (delay_pos_ticks, delay_vel_ticks, delay_gyro_ticks, delay_quat_ticks)
        self._sensor_quat = self._model.sensor("orientation").id
        self._sensor_gyro = self._model.sensor("angular-velocity").id
        self.reset(sync=False)
        self._viewer = mujoco.viewer.launch_passive(self._model, self._data, key_callback=key_callback)
        self._viewer.cam.lookat[:] = [0.4, 0.0, 0.5]
        self._viewer.cam.distance, self._viewer.cam.azimuth, self._viewer.cam.elevation = 1.9, -90, -10

    @property
    def viewer_opt(self) -> mujoco.MjvOption:
        return self._viewer.opt

    def reset(self, sync: bool = True) -> None:
        """Back to the start (key [r]): hanging on the start holds, or standing in front of the wall."""
        if self._start == "floor":
            self.sim.reset()
        else:
            self.sim.reset_hanging()
        self.sim.set_torque(False)                     # as the robot's program starts: torque off...
        self._held = True                              # ...held where it is until the torque first goes on
        q = self.sim.joint_positions()
        pos, vel, gyro, quat = self._delays
        self._delay_pos = _DelayBuffer(q, pos)
        self._delay_vel = _DelayBuffer(np.zeros_like(q), vel)
        self._delay_gyro = _DelayBuffer((0.0, 0.0, 0.0), gyro)
        self._delay_quat = _DelayBuffer(self._quat_now(), quat)
        self._target = q.copy()
        self._q, self._dq = self._delay_pos.push_and_read(q), self._delay_vel.push_and_read(np.zeros_like(q))
        if sync:
            self._viewer.sync()

    # ---- writes ------------------------------------------------------------------------------------------
    def sync_write_kp(self, ids: list[int], gains: list[int]) -> None:
        self.sim.servos.ctrl.model.actuator.kp = float(gains[0])

    def sync_read_kp(self, ids: list[int]) -> list[int]:
        return [int(self.sim.servos.ctrl.model.actuator.kp)] * len(ids)

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
        """The targets of this tick, then 20 ms of simulation (the scheduler calls it once per tick)."""
        if not self._viewer.is_running():
            self._stop_flag_path.write_text("stop\n", encoding="ascii")
            return
        for mid, p in zip(ids, positions):
            self._target[self._index[mid]] = p
        if not self._held:
            self.sim.step(self._target)
        if self._reset_source is not None and self._reset_source.consume_reset():
            self.reset()
            return
        q = self.sim.joint_positions()
        self._q, self._dq = self._delay_pos.push_and_read(q), self._delay_vel.push_and_read(self.sim.joint_velocities())
        self._viewer.sync()

    # ---- reads (what the real robot measures, with its delays) ------------------------------------------
    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        return [float(self._q[self._index[mid]]) for mid in ids]

    def read_present_position(self, motor_id: int) -> float:
        return float(self._q[self._index[motor_id]])

    def sync_read_present_velocity(self, ids: list[int]) -> list[float]:
        return [float(self._dq[self._index[mid]]) for mid in ids]

    def read_present_velocity(self, motor_id: int) -> float:
        return float(self._dq[self._index[motor_id]])

    def sync_read_present_current(self, ids: list[int]) -> list[float]:
        current = self.sim.currents()
        return [float(current[self._index[mid]]) for mid in ids]

    def sync_read_present_input_voltage(self, ids: list[int]) -> list[float]:
        return [80.0] * len(ids)

    def read_present_input_voltage(self, motor_id: int) -> float:
        return 80.0

    def _quat_now(self) -> tuple[float, float, float, float]:
        adr = self._model.sensor_adr[self._sensor_quat]
        return tuple(float(v) for v in self._data.sensordata[adr:adr + 4])

    def read_acc(self) -> tuple[float, float, float]:
        """What an accelerometer at rest reads, in g, in the IMU frame (as MuJoCoController)."""
        w, x, y, z = self._quat_now()
        return 2 * (x * z - w * y), 2 * (y * z + w * x), w * w - x * x - y * y + z * z

    def read_gyro(self) -> tuple[float, float, float]:
        adr = self._model.sensor_adr[self._sensor_gyro]
        return self._delay_gyro.push_and_read(tuple(float(v) for v in self._data.sensordata[adr:adr + 3]))

    def read_quat(self, dt: float) -> tuple[float, float, float, float]:
        return self._delay_quat.push_and_read(self._quat_now())
