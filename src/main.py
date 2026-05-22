import time
import numpy as np
import os
from pathlib import Path

from rustypot import Xl330PyController

from constants import motor_id, neutral_pose, motor_sign
from scheduler import Scheduler

PID_FILE = Path("/tmp/microban_scheduler.pid")


def ramp_to_neutral(controller: Xl330PyController, duration_s: float = 2.0) -> None:
    """Ramp all motors smoothly to neutral position before starting the control loop."""
    motor_ids = list(motor_id.values())
    initial_positions = np.array(controller.sync_read_present_position(motor_ids))
    target_neutral = np.array([neutral_pose[name] * motor_sign[name] for name in motor_id])

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

    controller = Xl330PyController(serial_port="/dev/ttyAMA0", baudrate=1000000, timeout=0.1)
    motor_ids = list(motor_id.values())
    controller.sync_write_torque_enable(motor_ids, [True] * len(motor_ids))
    controller.sync_write_status_return_level(motor_ids, [1] * len(motor_ids))

    try:
        ramp_to_neutral(controller)
        time.sleep(0.5)

        scheduler = Scheduler(frequency_hz=50.0, controller=controller)
        scheduler.run()
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


if __name__ == "__main__":
    main()