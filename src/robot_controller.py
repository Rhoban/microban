from rustypot import Xl330PyController

from constants import MOTOR_ID, MOTOR_SIGN


class RobotController:
    """Wraps Xl330PyController and centralises all MOTOR_SIGN conversions."""

    def __init__(self, serial_port: str = "/dev/ttyAMA0", baudrate: int = 1_000_000, timeout: float = 0.1) -> None:
        self._controller = Xl330PyController(serial_port=serial_port, baudrate=baudrate, timeout=timeout)
        self._id_to_sign: dict[int, float] = {MOTOR_ID[name]: MOTOR_SIGN[name] for name in MOTOR_ID}

    def sync_write_torque_enable(self, ids: list[int], values: list[bool]) -> None:
        self._controller.sync_write_torque_enable(ids, values)

    def sync_write_status_return_level(self, ids: list[int], levels: list[int]) -> None:
        self._controller.sync_write_status_return_level(ids, levels)

    def sync_write_goal_position(self, ids: list[int], positions: list[float]) -> None:
        hw_positions = [pos * self._id_to_sign[motor_id] for motor_id, pos in zip(ids, positions)]
        self._controller.sync_write_goal_position(ids, hw_positions)

    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        raw = self._controller.sync_read_present_position(ids)
        return [r * self._id_to_sign[motor_id] for motor_id, r in zip(ids, raw)]

    def read_present_position(self, motor_id: int) -> float:
        raw = self._controller.read_present_position(motor_id)
        value = raw[0] if isinstance(raw, (list, tuple)) else float(raw)
        return value * self._id_to_sign[motor_id]

    def read_present_input_voltage(self, motor_id: int) -> float:
        raw = self._controller.read_present_input_voltage(motor_id)
        return raw[0] if isinstance(raw, (list, tuple)) else float(raw)
