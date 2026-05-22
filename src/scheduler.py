import time
from pathlib import Path
from typing import Optional
from rustypot import Xl330PyController

from constants import motor_id, motor_sign
from observer import Observer
from moves.move import MotorCommand
from moves.rotate_head import RotateHeadMove

class Scheduler:
    def __init__(
        self,
        frequency_hz: float = 50.0,
        serial_port: str = "/dev/ttyAMA0",
        controller: Optional[Xl330PyController] = None,
        stop_flag_path: str = "/tmp/microban_scheduler.stop",
    ):
        self.dt = 1.0 / frequency_hz
        self.controller = controller or Xl330PyController(serial_port=serial_port, baudrate=1000000, timeout=0.1)
        self.stop_flag_path = Path(stop_flag_path)
        self._cleanup_done = False

        self.motor_name_to_id = dict(motor_id)
        all_motor_ids = list(self.motor_name_to_id.values())
        if controller is None:
            self.controller.sync_write_torque_enable(all_motor_ids, [True] * len(all_motor_ids))
            self.controller.sync_write_status_return_level(all_motor_ids, [1] * len(all_motor_ids))

        self.observer = Observer(self.controller, self.motor_name_to_id)
        self.moves = [RotateHeadMove()]
        self.loop_start_time = time.perf_counter()

    def run(self):
        print(f"Starting control loop at {1 / self.dt:.1f} Hz")
        if self.stop_flag_path.exists():
            self.stop_flag_path.unlink()

        try:
            while True:
                if self.stop_flag_path.exists():
                    print("Stop requested through stop flag")
                    break

                start_time = time.perf_counter()

                # 1. Read robot observations
                state = self.observer.read_state()
                state.time_s = start_time - self.loop_start_time

                # 2. Build command through move pipeline
                command = MotorCommand()

                for move in self.moves:
                    move.apply(state, command)

                # 3. Send command to motors
                self._send_to_motors(command)

                # 4. Sleep to keep a fixed control frequency
                elapsed_time = time.perf_counter() - start_time
                sleep_time = self.dt - elapsed_time

                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    ms_late = -sleep_time * 1000
                    print(f"Warning: control loop overrun by {ms_late:.2f} ms")

        except KeyboardInterrupt:
            print("Control loop interrupted by user")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Disable torque once and clear stop artifacts before exiting."""
        if self._cleanup_done:
            return

        self._cleanup_done = True
        all_motor_ids = list(self.motor_name_to_id.values())
        self.controller.sync_write_torque_enable(all_motor_ids, [False] * len(all_motor_ids))
        print("Torque disabled on all motors")

        if self.stop_flag_path.exists():
            self.stop_flag_path.unlink()

    def _send_to_motors(self, command: MotorCommand):
        """Send one batched goal position command from the composed command dict."""
        if not command.target_angles:
            return

        motor_ids = []
        target_positions = []
        for motor_name, target_angle in command.target_angles.items():
            motor_ids.append(self.motor_name_to_id[motor_name])
            target_positions.append(target_angle * motor_sign[motor_name])

        self.controller.sync_write_goal_position(motor_ids, target_positions)

if __name__ == "__main__":
    robot_loop = Scheduler(frequency_hz=50.0)
    robot_loop.run()