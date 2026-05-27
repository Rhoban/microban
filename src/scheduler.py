import time
from pathlib import Path
from typing import Optional

from constants import MOTOR_TO_ID
from controller import ControllerProtocol
from battery import BATTERY_WARN_V, BATTERY_CRITICAL_V, BATTERY_PROBE_IDS
from observer import Observer, Observation
from input.input_source import InputSource, UserInput
from moves.move import MotorCommand, Move, MoveState
from moves.rotate_head import RotateHeadMove
from moves.squat import SquatMove
from moves.walk import WalkMove


class Scheduler:
    def __init__(
        self,
        frequency_hz: float = 50.0,
        controller: ControllerProtocol = None,
        stop_flag_path: str = "/tmp/microban_scheduler.stop",
        input_source: Optional[InputSource] = None,
        moves: Optional[dict[str, Move]] = None,
    ):
        self.dt = 1.0 / frequency_hz
        self.controller = controller
        self.stop_flag_path = Path(stop_flag_path)
        self._cleanup_done = False
        self.input_source = input_source

        self.observer = Observer(self.controller)

        # All moves are registered here. They only run when activated via user_input.active_moves.
        self.registered_moves: dict[str, Move] = moves if moves is not None else {
            "head": RotateHeadMove(),
            "squat": SquatMove(),
            "walk": WalkMove(),
        }

        self.loop_start_time = time.perf_counter()
        self._battery_tick = 0
        self._battery_check_every = max(1, round(frequency_hz * 10))  # once every 10 seconds

    def run(self):
        print(f"Starting control loop at {1 / self.dt:.1f} Hz", end="\r\n", flush=True)
        if self.stop_flag_path.exists():
            self.stop_flag_path.unlink()

        if self.input_source:
            self.input_source.start()

        try:
            while True:
                if self.stop_flag_path.exists():
                    print("Stop requested through stop flag", end="\r\n", flush=True)
                    break

                start_time = time.perf_counter()

                # Read robot observations and user input
                robot_state = self.observer.read_state()
                robot_state.time_s = start_time - self.loop_start_time
                user_input = self.input_source.read() if self.input_source else UserInput()
                obs = Observation(robot_state=robot_state, user_input=user_input)

                # Update move states and dispatch one call per move per tick
                command = MotorCommand()
                for name, move in self.registered_moves.items():
                    in_active = name in obs.user_input.active_moves

                    if in_active and move.state == MoveState.INACTIVE:
                        move.state = MoveState.STARTING
                    elif not in_active and move.state in (MoveState.STARTING, MoveState.ACTIVE):
                        move.state = MoveState.STOPPING

                    if move.state == MoveState.STARTING:
                        move.on_start(obs, command)
                    elif move.state == MoveState.ACTIVE:
                        move.step(obs, command)
                    elif move.state == MoveState.STOPPING:
                        move.on_stop(obs, command)

                # Send command to motors
                self._send_to_motors(command)

                # Battery voltage check
                self._battery_tick += 1
                if self._battery_tick >= self._battery_check_every:
                    self._battery_tick = 0
                    voltage = self.observer.read_battery_voltage(BATTERY_PROBE_IDS)
                    if voltage < BATTERY_CRITICAL_V:
                        print(f"CRITICAL: battery voltage {voltage:.2f} V < {BATTERY_CRITICAL_V} V — shutting down", end="\r\n", flush=True)
                        break
                    elif voltage < BATTERY_WARN_V:
                        print(f"Warning: battery voltage {voltage:.2f} V < {BATTERY_WARN_V} V", end="\r\n", flush=True)

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

    def _cleanup(self) -> None:
        """Disable torque, stop input source, and clear stop artifacts."""
        if self._cleanup_done:
            return

        self._cleanup_done = True

        if self.input_source:
            self.input_source.stop()

        motor_ids = list(MOTOR_TO_ID.values())
        self.controller.sync_write_torque_enable(motor_ids, [False] * len(motor_ids))
        print("Torque disabled on all motors", end="\r\n", flush=True)

        if self.stop_flag_path.exists():
            self.stop_flag_path.unlink()

    def _send_to_motors(self, command: MotorCommand):
        """Send one batched goal position command from the composed command dict."""
        if not command.target_angles:
            return

        motor_ids = [MOTOR_TO_ID[name] for name in command.target_angles]
        target_positions = list(command.target_angles.values())

        self.controller.sync_write_goal_position(motor_ids, target_positions)
