import time
import numpy as np
import os
from pathlib import Path

from constants import MOTOR_TO_ID, NEUTRAL_POSE
from robot_controller import RobotController
from scheduler import Scheduler
from input.keyboard_input import KeyboardInputSource
from moves.rotate_head import RotateHeadMove
from moves.walk import WalkMove

PID_FILE = Path("/tmp/microban_scheduler.pid")


def ramp_to_neutral(controller: RobotController, duration_s: float = 2.0) -> None:
    """Ramp all motors smoothly to neutral position before starting the control loop."""
    motor_ids = list(MOTOR_TO_ID.values())
    initial_positions = np.array(controller.sync_read_present_position(motor_ids))
    target_neutral = np.array([NEUTRAL_POSE[name] for name in MOTOR_TO_ID])

    print("Ramping all motors to neutral position...")
    start_time = time.perf_counter()
    elapsed_time = 0.0

    while elapsed_time < duration_s:
        elapsed_time = time.perf_counter() - start_time
        progress = min(elapsed_time / duration_s, 1.0)
        target_positions = initial_positions + progress * (target_neutral - initial_positions)
        controller.sync_write_goal_position(motor_ids, target_positions.flatten().tolist())

    controller.sync_write_goal_position(motor_ids, target_neutral.tolist())
    print("All motors reached neutral position.")


def main() -> None:
    PID_FILE.write_text(f"{os.getpid()}\n", encoding="ascii")

    controller = RobotController()
    motor_ids = list(MOTOR_TO_ID.values())
    controller.sync_write_torque_enable(motor_ids, [True] * len(motor_ids))
    print(controller.sync_read_kp(motor_ids))

    try:
        ramp_to_neutral(controller)
        time.sleep(0.5)

        scheduler = Scheduler(
            frequency_hz=50.0,
            controller=controller,
            input_source=KeyboardInputSource(move_keys={"h": "head", "w": "walk"}),
            moves={
                "head": RotateHeadMove(),
                "walk": WalkMove(controller=controller),
            },
        )
        scheduler.run()
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


if __name__ == "__main__":
    main()