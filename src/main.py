# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import os
import signal
import sys
from pathlib import Path

from constants import GAMEPAD_BUTTON_MOVES, KP_DEFAULT, MOTOR_TO_ID, MOVE_KEYS
from robot_controller import RobotController
from scheduler import Scheduler
from telemetry import Telemetry
from input.input_source import InputSource
from input.keyboard_input import KeyboardInputSource
from moves.discover import all_moves

PID_FILE = Path("/tmp/microban_scheduler.pid")


def _another_session_running() -> bool:
    """True if a live control loop already owns the PID file (e.g. launched by the
    gamepad daemon). Avoids two instances fighting over the motor bus."""
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="ascii").strip())
        os.kill(pid, 0)
    except (ValueError, OSError):
        return False
    return True



def _stop_like_ctrl_c(signum, frame) -> None:
    raise KeyboardInterrupt


def moves() -> dict:
    """The moves of src/moves/, and those of MICROBAN_MOVES=path/to/file.py (make run MOVES=...): a file kept
    elsewhere."""
    return all_moves(os.environ.get("MICROBAN_MOVES"))


def build_input_source() -> InputSource:
    """Use the gamepad when one is connected, otherwise fall back to the keyboard.

    Without a terminal (the robot service): a gamepad whenever one connects, else none (the dashboard drives).
    Override with MICROBAN_INPUT=keyboard|gamepad.
    """
    requested = os.environ.get("MICROBAN_INPUT", "auto").lower()

    if requested == "auto" and not sys.stdin.isatty():
        # the robot service (no terminal): a gamepad whenever one connects, else the dashboard alone
        from input.hotplug_input import HotplugGamepadInputSource
        print("No terminal: gamepad when connected, moves from the dashboard otherwise.")
        return HotplugGamepadInputSource(button_moves=GAMEPAD_BUTTON_MOVES)

    if requested in ("auto", "gamepad"):
        from input.gamepad_input import GamepadInputSource, find_gamepad_path

        if find_gamepad_path() is not None:
            return GamepadInputSource(button_moves=GAMEPAD_BUTTON_MOVES)
        if requested == "gamepad":
            raise RuntimeError("MICROBAN_INPUT=gamepad but no gamepad was found.")
        print("No gamepad detected; using keyboard input.")

    return KeyboardInputSource(move_keys=MOVE_KEYS)


def main() -> None:
    if _another_session_running():
        print("A control loop is already running (see the PID file); aborting.")
        return

    PID_FILE.write_text(f"{os.getpid()}\n", encoding="ascii")
    # systemctl stop / restart (make deploy, the dashboard's Deploy, make robot-service-stop) sends SIGTERM: handled as
    # Ctrl+C, so the scheduler's cleanup runs (torque off on every motor, the IMU thread stopped, the PID file removed)
    signal.signal(signal.SIGTERM, _stop_like_ctrl_c)

    controller = RobotController()
    motor_ids = list(MOTOR_TO_ID.values())
    # torque off until a move is launched (then on where the robot is, or a ramp to the neutral pose: its start_pose)
    controller.sync_write_torque_enable(motor_ids, [False] * len(motor_ids))
    controller.sync_write_status_return_level(motor_ids, [1] * len(motor_ids))
    controller.sync_write_kp(motor_ids, [KP_DEFAULT] * len(motor_ids))

    try:
        scheduler = Scheduler(
            frequency_hz=50.0,
            controller=controller,
            input_source=build_input_source(),
            moves=moves(),
            telemetry=Telemetry(controller),
        )

        # Flush stale UART bytes accumulated while the moves loaded
        for _ in range(10):
            try:
                controller.sync_read_present_position(motor_ids)
            except RuntimeError:
                pass

        scheduler.run()

    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


if __name__ == "__main__":
    main()