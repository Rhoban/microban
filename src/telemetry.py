# SPDX-License-Identifier: GPL-3.0-or-later
"""The robot's side of the live dashboard (humanoid-dashboard, run on the PC: `make dashboard`).

Once per tick, after the motors were commanded, sends what the loop already read (positions, velocities, currents,
targets, IMU, tick time) in one UDP packet, only while a PC listens. While one listens, it also reads the motors'
health about once a second (torque, hardware error, voltage, temperature: two small sync reads) and runs the page's
commands between two ticks: `reboot` a motor (clears overheating / overload; its torque stays off), `torque` on/off for
one motor or all of them (`torque_all`, the emergency button), `zero_pose` (every motor to its zero, the shoulders' arm
forward, in ZERO_RAMP_S, then held: the page's targets replace the moves' until `release`).
Without the humanoid_dashboard package, or with MICROBAN_DASHBOARD=0, it does nothing.
"""
import math
import os
import time

from constants import MOTOR_TO_ID, MOTOR_OFFSET

try:
    from humanoid_dashboard.link import Link
except ImportError:
    Link = None

HEALTH_EVERY = 50                  # ticks (1 s at 50 Hz)
CURRENT_LIMIT_A = 1.75             # XL330 at 5-8 V (BAM max_current)
TEMPERATURE_LIMIT_C = 70           # XL330 factory Temperature Limit
VOLTAGE_BIT = 1                    # always set above 7 V (the robot runs at ~8 V): not an error for Microban
ZERO_RAMP_S = 2.0                  # zero_pose: from where the robot is to every motor's zero


class Telemetry:
    def __init__(self, controller):
        self.controller = controller
        self.link = None
        if Link is None or os.environ.get("MICROBAN_DASHBOARD", "1") == "0":
            return
        self.names = list(MOTOR_TO_ID)
        self.ids = [MOTOR_TO_ID[n] for n in self.names]
        n = len(self.names)
        self.torque, self.error = [math.nan] * n, [math.nan] * n
        self.voltage, self.temperature = [math.nan] * n, [math.nan] * n
        self.health = getattr(controller, "sync_read_health", None)       # the real robot only
        cmds = (["reboot", "torque"] if hasattr(controller, "reboot") else []) + ["torque_all", "zero_pose", "release"]
        self.pose = None              # zero_pose in progress / held: {t0, start, target}
        self.last_q = {}
        try:
            self.link = Link("Microban", fields={
                "q": self.names, "q_target": self.names, "dq": self.names, "current": self.names,
                "torque": self.names, "hw_error": self.names, "voltage": self.names, "temperature": self.names,
                "imu_quat": ["w", "x", "y", "z"], "gyro": ["x", "y", "z"], "acc": ["x", "y", "z"],
                "tick_ms": ["tick"], "safety_est_A": ["total"], "pose_hold": ["on"]},
                meta={"motor_ids": MOTOR_TO_ID, "limits": {"current": CURRENT_LIMIT_A, "temperature": TEMPERATURE_LIMIT_C},
                      "hw_error_bits": {"0": "input voltage", "2": "overheating", "3": "motor encoder",
                                        "4": "electrical shock", "5": "overload"},
                      "hw_error_ignore": VOLTAGE_BIT, "commands": cmds})
        except OSError as e:          # port taken (another session): the robot runs without the dashboard
            print(f"Warning: dashboard link off ({e})", end="\r\n", flush=True)
        self.tick_count = 0

    def apply(self, command) -> None:
        """Before the motors are commanded: while a zero_pose runs or is held, its targets replace the moves'."""
        if self.link is None or self.pose is None:
            return
        p = self.pose
        a = min(1.0, (time.perf_counter() - p["t0"]) / ZERO_RAMP_S)
        a = a * a * (3 - 2 * a)       # smooth start and stop
        command.target_angles = {n: p["start"][n] + a * (p["target"][n] - p["start"][n]) for n in self.names}

    def tick(self, state, target_angles: dict, tick_ms: float, total_current: float | None = None) -> None:
        """Call once per tick, after the motors were commanded (the bus is free)."""
        if self.link is None:
            return
        self.tick_count += 1
        if self.health and self.link.listening and self.tick_count % HEALTH_EVERY == 0:
            self._read_health()
        names = self.names
        self.last_q = state.motor_positions
        self.link.publish(
            q=[state.motor_positions.get(n, math.nan) for n in names],
            q_target=[target_angles.get(n, math.nan) for n in names],
            dq=[state.motor_velocities.get(n, math.nan) for n in names],
            current=[state.measured_currents.get(n, math.nan) for n in names] if state.measured_currents else None,
            torque=self.torque, hw_error=self.error, voltage=self.voltage, temperature=self.temperature,
            imu_quat=state.body_quat or None, gyro=state.gyro or None, acc=state.acc or None,
            tick_ms=tick_ms, safety_est_A=total_current, pose_hold=0 if self.pose is None else 1)
        for cmd in self.link.commands():
            self._run(cmd)

    def _read_health(self) -> None:
        try:
            torque, error, voltage, temperature = self.health(self.ids)
        except RuntimeError:          # a motor missing: keep the last values
            return
        for i, n in enumerate(self.names):
            new = error[i] & ~VOLTAGE_BIT
            old = 0 if math.isnan(self.error[i]) else int(self.error[i]) & ~VOLTAGE_BIT
            if new & ~old:            # a new error bit: say it once
                self.link.event(f"{n} (ID {self.ids[i]}): hardware error {error[i]:#04x}, torque off", "error")
        self.torque, self.error, self.voltage, self.temperature = torque, error, voltage, temperature

    def _run_all(self, cmd: dict) -> None:
        name, ids, n = cmd["name"], self.ids, len(self.ids)
        try:
            if name == "torque_all":
                on = bool(cmd["args"].get("on"))
                if not on:
                    self.pose = None
                self.controller.sync_write_torque_enable(ids, [on] * n)
                self.torque = [int(on)] * n
                self.link.ack(cmd, True, f"torque {'on' if on else 'off'} on every motor")
                self.link.event(f"torque {'on' if on else 'OFF'} on every motor (dashboard)", "warn")
            elif name == "zero_pose":
                if len(self.last_q) < n:
                    raise RuntimeError("no position read yet")
                start = {k: self.last_q[k] for k in self.names}
                self.controller.sync_write_goal_position(ids, [start[k] for k in self.names])   # torque on: no jump
                self.controller.sync_write_torque_enable(ids, [True] * n)
                self.torque = [1] * n
                self.pose = {"t0": time.perf_counter(), "start": start,
                             "target": {k: -MOTOR_OFFSET.get(k, 0.0) for k in self.names}}      # the motors' zero
                self.link.ack(cmd, True, f"to every motor's zero in {ZERO_RAMP_S:.0f} s, then held (release: back to the moves)")
            elif name == "release":
                self.pose = None
                self.link.ack(cmd, True, "the moves command the motors again")
        except (RuntimeError, AttributeError) as e:
            self.link.ack(cmd, False, f"{name}: {e}")

    def _run(self, cmd: dict) -> None:
        if cmd["name"] in ("torque_all", "zero_pose", "release"):
            self._run_all(cmd)
            return
        name, joint = cmd["name"], cmd["args"].get("joint")
        if joint not in MOTOR_TO_ID:
            self.link.ack(cmd, False, f"unknown joint {joint}")
            return
        mid, i = MOTOR_TO_ID[joint], self.names.index(joint)
        try:
            if name == "reboot":
                took = self.controller.reboot(mid)
                self.torque[i], self.error[i] = 0, math.nan
                self.link.ack(cmd, True, f"{joint} (ID {mid}) rebooted in {took:.2f} s, torque off")
            elif name == "torque":
                on = bool(cmd["args"].get("on"))
                self.controller.write_torque_enable(mid, on)
                self.torque[i] = int(on)
                self.link.ack(cmd, True, f"{joint} (ID {mid}) torque {'on' if on else 'off'}")
            else:
                self.link.ack(cmd, False, f"unknown command {name}")
        except (RuntimeError, AttributeError) as e:
            self.link.ack(cmd, False, f"{name} {joint}: {e}")
        if self.health:
            self._read_health()

    def close(self) -> None:
        if self.link is not None:
            self.link.close()
