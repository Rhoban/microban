# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import json
import time
import math
from collections import deque
from pathlib import Path
from typing import Optional


from constants import (
    MOTOR_TO_ID,
    NEUTRAL_POSE,
    KP_DEFAULT,
    BAM_MAX_CURRENT,
    OVERCURRENT_CUTOFF_A,
    OVERCURRENT_DEBOUNCE_TICKS,
    OVERCURRENT_PROXY_DELAY_TICKS,
    PROXY_KT,
    PROXY_R,
    PROXY_VIN,
    PROXY_ERROR_GAIN,
    PROXY_MAX_PWM,
    PROXY_KP,
)
from controller import ControllerProtocol
from imu_reader import imu_quat_to_body
from observer import Observer, Observation
from input.input_source import InputSource, UserInput, scale_velocity
from moves.move import MotorCommand, Move, MoveState
from moves.rotate_head import RotateHeadMove
from moves.squat import SquatMove
from moves.walk import WalkMove

OPTIONS_FILE = Path("move_options.json")   # the moves' options saved from the dashboard (repo root on the robot)
POWER_UP_S = 2.0      # a move launched with the torque off (or from the zero pose): ramp to the neutral pose first
INIT_S = 2.0          # init: ramp to every motor's zero


class Scheduler:
    def __init__(
        self,
        frequency_hz: float = 50.0,
        controller: ControllerProtocol = None,
        stop_flag_path: str = "/tmp/microban_scheduler.stop",
        input_source: Optional[InputSource] = None,
        moves: Optional[dict[str, Move]] = None,
        telemetry=None,
        switches: Optional[list[str]] = None,
    ):
        self.dt = 1.0 / frequency_hz
        self.controller = controller
        self.stop_flag_path = Path(stop_flag_path)
        self._cleanup_done = False
        self.input_source = input_source

        self.observer = Observer(self.controller)
        self.telemetry = telemetry          # live dashboard (telemetry.Telemetry), or None
        self._last_total_current: Optional[float] = None

        # All moves are registered here. They only run when activated via user_input.active_moves.
        self.registered_moves: dict[str, Move] = moves if moves is not None else {
            "head": RotateHeadMove(),
            "squat": SquatMove(),
            "walk": WalkMove(),
        }

        self.loop_start_time = time.perf_counter()
        self._serial_errors = 0
        self._last_imu_print_s: float = 0.0
        self._last_imu_stale_warn_s: float = 0.0
        self._overcurrent_ticks = 0
        # History of sent target_angles, to align the current proxy with the delayed feedback:
        # the oldest entry is the command issued OVERCURRENT_PROXY_DELAY_TICKS ticks ago.
        self._cmd_history: deque[dict[str, float]] = deque(maxlen=OVERCURRENT_PROXY_DELAY_TICKS + 1)

        # Torque and modes (as em / init on Rhoban's robots): the torque is off until a move is launched; it goes off
        # again when no move runs. "em" (emergency) cuts it and stops the moves; "init" stops the moves and brings
        # every motor to its zero, held until a move is launched again (a move asked before em / init stays off until
        # it is asked anew: the keyboard or gamepad still lists it).
        self.powered = False
        self._pose: Optional[dict] = None           # a ramp: {t0, duration, start, target, hold}
        self._locked = False
        self._prev_requested: set[str] = set()
        # names a key toggles that are not moves (a move reads them in user_input.active_moves); the dashboard can
        # toggle them as well as the moves: what it asks is added to what the keyboard / gamepad asks
        self.switches = list(switches or [])
        self._dash_requested: set[str] = set()
        self._keys: set[str] = set()                # held in the dashboard's keyboard zone (Move.pressed, on_key)
        self._load_options()
        if self.telemetry is not None:
            self.telemetry.configure(self.registered_moves, self.switches)

    def run(self):
        print(f"Starting control loop at {1 / self.dt:.1f} Hz", end="\r\n", flush=True)
        if self.stop_flag_path.exists():
            self.stop_flag_path.unlink()

        if self.input_source:
            self.input_source.start()
        if self.telemetry is not None:          # the moves are loaded now (preload may expose more variables)
            self.telemetry.options_changed()

        try:
            while True:
                if self.stop_flag_path.exists():
                    print("Stop requested through stop flag", end="\r\n", flush=True)
                    break

                start_time = time.perf_counter()

                # Read robot observations and user input
                try:
                    robot_state = self.observer.read_state(self.dt)
                except RuntimeError as e:
                    self._serial_errors += 1
                    if self._serial_errors >= 3:
                        print(f"Serial communication error: {e}", end="\r\n", flush=True)
                        break
                    print(f"Warning: serial read error (attempt {self._serial_errors}/3): {e}", end="\r\n", flush=True)
                    time.sleep(self.dt)                      # retry at the next tick, not at once
                    continue
                self._serial_errors = 0

                robot_state.time_s = start_time - self.loop_start_time
                user_input = self.input_source.read() if self.input_source else UserInput()
                user_input.velocity = scale_velocity(user_input.velocity)
                obs = Observation(robot_state=robot_state, user_input=user_input)

                imu_status_getter = getattr(self.controller, "get_imu_status", None)
                if callable(imu_status_getter):
                    imu_status = imu_status_getter()
                    age_s = float(imu_status.get("age_s", 0.0))
                    if age_s > self.dt and (start_time - self._last_imu_stale_warn_s) >= 1.0:
                        print(f"Warning: stale IMU data ({age_s * 1000.0:.1f} ms old)", end="\r\n", flush=True)
                        self._last_imu_stale_warn_s = start_time

                requested = self._requested_moves(obs)
                self._dispatch_keys()

                # Update move states and dispatch one call per move per tick
                command = MotorCommand()
                for name, move in self.registered_moves.items():
                    in_active = name in requested

                    if in_active and move.state == MoveState.INACTIVE:
                        move.state = MoveState.STARTING
                        move.slider.update({n: float(sl[2]) for n, sl in type(move).sliders.items()})
                    elif not in_active and move.state in (MoveState.STARTING, MoveState.ACTIVE):
                        move.state = MoveState.STOPPING

                    if move.state == MoveState.STARTING:
                        move.on_start(obs, command)
                    elif move.state == MoveState.ACTIVE:
                        move.step(obs, command)
                    elif move.state == MoveState.STOPPING:
                        move.on_stop(obs, command)

                # Overcurrent safety: estimate the current from the command that was actually
                # active when the (delayed) position/velocity feedback was sampled — the oldest
                # buffered command (== DELAY_TICKS old once full). This reconstructs the real
                # (delayed) current instead of pairing a fresh target with stale feedback, which
                # would inflate the error term and false-trigger at gait start.
                aligned_targets = self._cmd_history[0] if self._cmd_history else command.target_angles
                if self._check_overcurrent(robot_state, aligned_targets):
                    break

                # A power-up or init ramp replaces the moves' targets; no move running: torque off
                self._apply_pose(command)
                asked = self._prev_requested & set(self.registered_moves)
                if (self.powered and self._pose is None and (self._locked or not asked)
                        and all(m.state == MoveState.INACTIVE for m in self.registered_moves.values())):
                    self._set_torque(False)

                # Send command to motors
                self._cmd_history.append(dict(command.target_angles))
                self._send_to_motors(command)

                # Live dashboard: what was just read and sent, and its commands (the bus is free here)
                if self.telemetry is not None:
                    self.telemetry.tick(robot_state, command.target_angles, (time.perf_counter() - start_time) * 1000,
                                        status={"powered": int(self.powered),
                                                "init": int(self._pose is not None and self._pose["hold"])},
                                        requested=self._prev_requested)

                # IMU / gyro terminal display
                if obs.user_input.show_imu and (start_time - self._last_imu_print_s) >= 0.5:
                    acc = obs.robot_state.acc
                    gyro = obs.robot_state.gyro
                    quat = obs.robot_state.quat
                    print("--------------------------------------------", end="\r\n", flush=True)
                    if gyro:
                        gx, gy, gz = gyro
                        print(f"Gyro: gx={gx:+.3f}  gy={gy:+.3f}  gz={gz:+.3f} rad/s", end="\r\n", flush=True)
                    if acc:
                        ax, ay, az = acc
                        print(f"Acc:  ax={ax:+.3f}  ay={ay:+.3f}  az={az:+.3f} g", end="\r\n", flush=True)
                    if quat:
                        w, x, y, z = quat
                        roll = math.degrees(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
                        pitch = math.degrees(math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x)))))
                        yaw = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
                        print(f"IMU:  roll={roll:+.1f}°  pitch={pitch:+.1f}°  yaw={yaw:+.1f}°", end="\r\n", flush=True)
                        bw, bx, by, bz = imu_quat_to_body((w, x, y, z))
                        b_roll = math.degrees(math.atan2(2 * (bw * bx + by * bz), 1 - 2 * (bx * bx + by * by)))
                        b_pitch = math.degrees(math.asin(max(-1.0, min(1.0, 2 * (bw * by - bz * bx)))))
                        b_yaw = math.degrees(math.atan2(2 * (bw * bz + bx * by), 1 - 2 * (by * by + bz * bz)))
                        print(f"Body: roll={b_roll:+.1f}°  pitch={b_pitch:+.1f}°  yaw={b_yaw:+.1f}°", end="\r\n", flush=True)
                    self._last_imu_print_s = start_time

                # Sleep to keep a fixed control frequency
                elapsed_time = time.perf_counter() - start_time
                sleep_time = self.dt - elapsed_time

                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    ms_late = -sleep_time * 1000
                    print(f"Warning: control loop overrun by {ms_late:.2f} ms", end="\r\n", flush=True)

        except KeyboardInterrupt:
            print("Control loop interrupted by user", end="\r\n", flush=True)
        finally:
            self._cleanup()

    # ---- torque, em, init ---------------------------------------------------------------------------------
    def _requested_moves(self, obs: Observation) -> set[str]:
        """The moves to run this tick, after the dashboard's requests (em, init, start / stop a move or switch) and the
        torque power-up. user_input.active_moves gets what the dashboard asks too (moves read their switches there)."""
        for op, name, *extra in (self.telemetry.take_requests() if self.telemetry is not None else []):
            if op == "option":
                opt, value = extra[0]
                move = self.registered_moves[name]
                move.options[opt] = value
                move.on_option(opt, value)
                self.telemetry.options_changed()
            elif op == "save_options":
                self.telemetry.event(self._save_options())
            elif op == "start":
                self._dash_requested.add(name)
            elif op == "stop":
                self._dash_requested.discard(name)
            elif op == "em":
                self._dash_requested.clear()
                self._stop_moves()
                self._pose = None
                self._set_torque(False)
                self._locked = True
                print("Emergency stop: torque off on every motor", end="\r\n", flush=True)
            elif op == "init":
                self._dash_requested.clear()
                self._stop_moves()
                self._start_pose(obs.robot_state, {n: 0.0 for n in MOTOR_TO_ID}, INIT_S, hold=True)
                self._locked = True
        requested = set(obs.user_input.active_moves) | self._dash_requested
        obs.user_input.active_moves = set(requested)
        launched = requested - self._prev_requested
        self._prev_requested = set(requested)
        launched &= set(self.registered_moves)        # a switch that is not a move (a move's own) launches nothing
        if self._locked:
            if not launched:
                return set()
            self._locked = False                       # a move launched again: it leaves em / init
        moves = requested & set(self.registered_moves)
        if moves and (not self.powered or (self._pose is not None and self._pose["hold"])):
            if all(getattr(self.registered_moves[n], "power_up", "neutral") == "current" for n in moves):
                # moves that start where the robot is (a user's controller, maybe hanging on the wall)
                here = {n: obs.robot_state.motor_positions.get(n, NEUTRAL_POSE[n]) for n in MOTOR_TO_ID}
                self._start_pose(obs.robot_state, here, 0.1, hold=False)
            else:
                self._start_pose(obs.robot_state, dict(NEUTRAL_POSE), POWER_UP_S, hold=False)
        if self._pose is not None and not self._pose["hold"]:
            return set()                               # the moves start once at the neutral pose
        return requested

    def _dispatch_keys(self) -> None:
        """The keys pressed / released in the dashboard's keyboard zone since the last tick: Move.pressed for every
        move, Move.on_key for the running ones."""
        if self.telemetry is None:
            return
        held = self.telemetry.keys_held()
        if held == self._keys:
            return
        changes = [(k, False) for k in sorted(self._keys - held)] + [(k, True) for k in sorted(held - self._keys)]
        self._keys = held
        for move in self.registered_moves.values():
            move.pressed = set(held)
            if move.state in (MoveState.STARTING, MoveState.ACTIVE):
                for key, down in changes:
                    move.on_key(key, down)

    # ---- the moves' options (dashboard) -----------------------------------------------------------------------
    def _load_options(self) -> None:
        """The values saved from the dashboard (OPTIONS_FILE), over the moves' defaults: known options only, same type."""
        if not OPTIONS_FILE.exists():
            return
        try:
            saved = json.loads(OPTIONS_FILE.read_text())
        except ValueError as e:
            print(f"Warning: {OPTIONS_FILE} unreadable ({e}): the moves' defaults", end="\r\n", flush=True)
            return
        if not isinstance(saved, dict):
            print(f"Warning: {OPTIONS_FILE} is not a {{move: {{option: value}}}} object: the moves' defaults",
                  end="\r\n", flush=True)
            return
        for name, values in saved.items():
            move = self.registered_moves.get(name)
            if move is None or not isinstance(values, dict):
                continue
            for opt, value in values.items():
                if opt not in move.options:
                    continue
                old = move.options[opt]
                try:
                    new = bool(value) if isinstance(old, bool) else type(old)(value)
                    move.on_option(opt, new)
                    move.options[opt] = new
                except (TypeError, ValueError) as e:      # a value edited by hand: that option keeps its default
                    print(f"Warning: {OPTIONS_FILE}: {name}.{opt} = {value!r} skipped ({e})", end="\r\n", flush=True)
        print(f"Move options from {OPTIONS_FILE}", end="\r\n", flush=True)

    def _save_options(self) -> str:
        data = {name: dict(m.options) for name, m in self.registered_moves.items() if m.options}
        OPTIONS_FILE.write_text(json.dumps(data, indent=1) + "\n")
        return f"move options saved to {OPTIONS_FILE.resolve()}"

    def _stop_moves(self) -> None:
        """em / init: every move stops at once (no on_stop): each forgets its own transition (Move.reset)."""
        for move in self.registered_moves.values():
            if move.state != MoveState.INACTIVE:
                move.reset()
            move.state = MoveState.INACTIVE
        write_kp = getattr(self.controller, "sync_write_kp", None)
        if callable(write_kp):                         # a move may have changed the gain (the walk: KP_RL)
            ids = list(MOTOR_TO_ID.values())
            write_kp(ids, [KP_DEFAULT] * len(ids))

    def _set_torque(self, on: bool) -> None:
        ids = list(MOTOR_TO_ID.values())
        self.controller.sync_write_torque_enable(ids, [on] * len(ids))
        self.powered = on
        if self.telemetry is not None:
            self.telemetry.torque_changed(on)

    def _start_pose(self, robot_state, target: dict[str, float], duration: float, hold: bool) -> None:
        """Ramp from where the motors are to target; the torque goes on without a jump (goal = present first)."""
        start = {n: robot_state.motor_positions.get(n, target[n]) for n in MOTOR_TO_ID}
        if not self.powered:
            self.controller.sync_write_goal_position(list(MOTOR_TO_ID.values()), [start[n] for n in MOTOR_TO_ID])
            self._set_torque(True)
        self._pose = {"t0": time.perf_counter(), "duration": duration, "start": start, "target": target, "hold": hold}

    def _apply_pose(self, command: MotorCommand) -> None:
        p = self._pose
        if p is None:
            return
        a = min(1.0, (time.perf_counter() - p["t0"]) / p["duration"])
        s = a * a * (3 - 2 * a)
        command.target_angles = {n: p["start"][n] + s * (p["target"][n] - p["start"][n]) for n in MOTOR_TO_ID}
        if a >= 1.0 and not p["hold"]:
            self._pose = None                          # at the neutral pose: the launched moves start next tick

    def _cleanup(self) -> None:
        """Disable torque, stop input source, and clear stop artifacts."""
        if self._cleanup_done:
            return

        self._cleanup_done = True

        if self.input_source:
            self.input_source.stop()

        if self.telemetry is not None:
            self.telemetry.close()

        shutdown = getattr(self.controller, "shutdown", None)
        if callable(shutdown):
            shutdown()

        motor_ids = list(MOTOR_TO_ID.values())
        self.controller.sync_write_torque_enable(motor_ids, [False] * len(motor_ids))
        print("Torque disabled on all motors", end="\r\n", flush=True)

        if self.stop_flag_path.exists():
            self.stop_flag_path.unlink()

    def _estimate_total_current(self, robot_state, target_angles: dict[str, float]) -> float:
        """Estimate the total pack current [A] from whichever signal is available.

        - If present_current was read (Observer.observe_current = True), use the measured
          sum of |current| over all motors.
        - Otherwise, fall back to the bam XL330 m6 current proxy (no extra bus read), from
          the (delay-aligned) command target, present_position and present_velocity:
            duty = clip(PROXY_KP * PROXY_ERROR_GAIN * (target - q), ±PROXY_MAX_PWM)
            I    = (PROXY_VIN * duty - PROXY_KT * dq) / PROXY_R, |I| capped at BAM_MAX_CURRENT
          The back-EMF term (PROXY_KT * dq) keeps the estimate low when the motor is moving
          toward an overshot RL target, while still flagging stalled motors (low dq, high error).
        """
        currents = robot_state.motor_currents
        if currents:
            return sum(abs(c) for c in currents.values())

        positions = robot_state.motor_positions
        velocities = robot_state.motor_velocities
        total = 0.0
        for name, target in target_angles.items():
            pos = positions.get(name)
            if pos is None:
                continue
            dq = velocities.get(name, 0.0)
            duty = PROXY_KP * PROXY_ERROR_GAIN * (target - pos)
            duty = max(-PROXY_MAX_PWM, min(PROXY_MAX_PWM, duty))
            current = (PROXY_VIN * duty - PROXY_KT * dq) / PROXY_R
            total += min(abs(current), BAM_MAX_CURRENT)
        return total

    def _check_overcurrent(self, robot_state, target_angles: dict[str, float]) -> bool:
        """Report when the estimated total pack current stays above OVERCURRENT_CUTOFF_A
        for OVERCURRENT_DEBOUNCE_TICKS consecutive ticks.

        When True, the run loop breaks and _cleanup() disables torque on every motor,
        leaving the robot compliant so the BMS does not trip on the current spike.
        """
        if not self.powered:                      # torque off: no current, and the targets mean nothing
            self._overcurrent_ticks = 0
            self._cmd_history.clear()
            self._last_total_current = None
            return False
        total_current = self._estimate_total_current(robot_state, target_angles)
        self._last_total_current = total_current
        if OVERCURRENT_CUTOFF_A is None:          # no BMS to protect: no safety cut (the estimate is still shown)
            return False
        if total_current >= OVERCURRENT_CUTOFF_A:
            self._overcurrent_ticks += 1
        else:
            self._overcurrent_ticks = 0

        if self._overcurrent_ticks >= OVERCURRENT_DEBOUNCE_TICKS:
            print(
                f"Overcurrent safety triggered: {total_current:.2f} A (threshold "
                f"{OVERCURRENT_CUTOFF_A:.2f} A) — disabling torque",
                end="\r\n",
                flush=True,
            )
            return True
        return False

    def _send_to_motors(self, command: MotorCommand):
        """Send one batched goal position command from the composed command dict."""
        if not command.target_angles:
            return

        motor_ids = [MOTOR_TO_ID[name] for name in command.target_angles]
        target_positions = list(command.target_angles.values())

        self.controller.sync_write_goal_position(motor_ids, target_positions)