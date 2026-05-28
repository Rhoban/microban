from rustypot import Xl330PyController

from constants import MOTOR_TO_ID, MOTOR_SIGN, IMU_I2C_BUS

from bmi088 import BMI088
import bmi088.bmi088 as _bmi_module

# The library default gyro address is 0x69, on our board it's 0x68
_bmi_module.GYRO_ADDRESS = 0x68


class RobotController:
    """Wraps Xl330PyController."""

    def __init__(self, serial_port: str = "/dev/ttyAMA0", baudrate: int = 1_000_000, timeout: float = 0.1) -> None:
        self._controller = Xl330PyController(serial_port=serial_port, baudrate=baudrate, timeout=timeout)
        self._id_to_sign: dict[int, float] = {MOTOR_TO_ID[name]: MOTOR_SIGN[name] for name in MOTOR_TO_ID}
        self._imu: BMI088 = BMI088(i2c_bus=IMU_I2C_BUS)

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

    def sync_read_kp(self, ids: list[int]) -> list[int]:
        return [int(v) for v in self._controller.sync_read_position_p_gain(ids)]

    def sync_write_kp(self, ids: list[int], gains: list[int]) -> None:
        self._controller.sync_write_position_p_gain(ids, gains)

    def read_acc(self) -> tuple[float, float, float]:
        """Return raw accelerometer (ax, ay, az) in g."""
        ax, ay, az = self._imu.read_accelerometer()
        return float(ax), float(ay), float(az)

    def read_gyro(self) -> tuple[float, float, float]:
        """Return (gx, gy, gz) in rad/s."""
        gx, gy, gz = self._imu.read_gyroscope()
        return float(gx), float(gy), float(gz)

    def read_quat(self) -> tuple[float, float, float, float]:
        """Return orientation quaternion (w, x, y, z)."""
        dt = 0.02  # nominal 50 Hz
        w, x, y, z = self._imu.get_quat(dt)
        return float(w), float(x), float(y), float(z)
