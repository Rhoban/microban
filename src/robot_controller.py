# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

from rustypot import Xl330PyController
import numpy as np

from constants import MOTOR_TO_ID, MOTOR_SIGN, MOTOR_OFFSET, IMU_I2C_BUS, MOTOR_SERIAL_PORT, PRESENT_CURRENT_UNIT_A
from imu_reader import ThreadedIMUReader


class RobotController:
    """Wraps Xl330PyController."""

    def __init__(self, serial_port: str = MOTOR_SERIAL_PORT, baudrate: int = 1_000_000, timeout: float = 0.1) -> None:
        self._controller = Xl330PyController(serial_port=serial_port, baudrate=baudrate, timeout=timeout)
        # Fast Sync Read (protocol 2.0): every motor answers a sync read in one status packet (one header instead of
        # one per motor): sync_read_state takes 3.7 ms for 18 motors at 1 Mbps (Radxa, 2026-10-27)
        self._controller.set_fast_sync_read(True)
        self._id_to_sign: dict[int, float] = {MOTOR_TO_ID[name]: MOTOR_SIGN[name] for name in MOTOR_TO_ID}
        self._id_to_offset: dict[int, float] = {MOTOR_TO_ID[name]: MOTOR_OFFSET.get(name, 0.0) for name in MOTOR_TO_ID}
        self._imu_reader = ThreadedIMUReader(i2c_bus=IMU_I2C_BUS, frequency_hz=200.0)
        self._imu_reader.start()

    def sync_write_torque_enable(self, ids: list[int], values: list[bool]) -> None:
        self._controller.sync_write_torque_enable(ids, values)

    def sync_write_status_return_level(self, ids: list[int], levels: list[int]) -> None:
        self._controller.sync_write_status_return_level(ids, levels)

    def sync_write_goal_position(self, ids: list[int], positions: list[float]) -> None:
        hw_positions = [(pos + self._id_to_offset[motor_id]) * self._id_to_sign[motor_id]
                        for motor_id, pos in zip(ids, positions)]
        self._controller.sync_write_goal_position(ids, hw_positions)

    def sync_read_present_position(self, ids: list[int]) -> list[float]:
        raw = self._controller.sync_read_present_position(ids)
        return [r * self._id_to_sign[motor_id] - self._id_to_offset[motor_id] for motor_id, r in zip(ids, raw)]

    def sync_read_state(self, ids: list[int]) -> tuple[list[float], list[float], list[float]]:
        """Present position (rad), velocity (rad/s) and current (A) in one sync read: the XL330 keeps them side by side
        (Present Current 126, Present Velocity 128, Present Position 132), so 10 bytes per motor in a single bus
        transaction instead of one sync read each (3.7 ms instead of 10.3 ms for 18 motors at 1 Mbps). Same values and
        conventions as sync_read_present_position / _velocity / _current."""
        positions, velocities, currents = [], [], []
        for motor_id, raw in zip(ids, self._controller.sync_read_raw_data(ids, 126, 10)):
            b = bytes(raw)
            sign = self._id_to_sign[motor_id]
            currents.append(int.from_bytes(b[0:2], "little", signed=True) * PRESENT_CURRENT_UNIT_A)
            velocities.append(int.from_bytes(b[2:6], "little", signed=True) * 0.229 * np.pi / 30 * sign)
            positions.append((int.from_bytes(b[6:10], "little", signed=True) - 2048) * 2 * np.pi / 4096 * sign
                             - self._id_to_offset[motor_id])
        return positions, velocities, currents

    def read_present_position(self, motor_id: int) -> float:
        raw = self._controller.read_present_position(motor_id)
        return raw * self._id_to_sign[motor_id] - self._id_to_offset[motor_id]

    def sync_read_present_velocity(self, ids: list[int]) -> list[float]:
        raw = np.array(self._controller.sync_read_present_velocity(ids)) * 0.229 * np.pi / 30
        return [r * self._id_to_sign[motor_id] for motor_id, r in zip(ids, raw)]
    
    def read_present_velocity(self, motor_id: int) -> float:
        raw = self._controller.read_present_velocity(motor_id) * 0.229 * np.pi / 30
        return raw * self._id_to_sign[motor_id]

    def sync_read_present_current(self, ids: list[int]) -> list[float]:
        """Present current per motor, in Amps (signed). Magnitude is what matters for the BMS budget."""
        raw = self._controller.sync_read_present_current(ids)
        return [
            (r[0] if isinstance(r, (list, tuple)) else float(r)) * PRESENT_CURRENT_UNIT_A
            for r in raw
        ]

    def sync_read_present_input_voltage(self, ids: list[int]) -> list[float]:
        raw = self._controller.sync_read_present_input_voltage(ids)
        return [r[0] if isinstance(r, (list, tuple)) else float(r) for r in raw]

    def read_present_input_voltage(self, motor_id: int) -> float:
        raw = self._controller.read_present_input_voltage(motor_id)
        return raw[0] if isinstance(raw, (list, tuple)) else float(raw)

    def sync_read_kp(self, ids: list[int]) -> list[int]:
        return [int(v) for v in self._controller.sync_read_position_p_gain(ids)]

    def sync_write_kp(self, ids: list[int], gains: list[int]) -> None:
        self._controller.sync_write_position_p_gain(ids, gains)

    def read_acc(self) -> tuple[float, float, float]:
        """Return raw accelerometer (ax, ay, az) in g."""
        return self._imu_reader.get_latest().acc

    def read_gyro(self) -> tuple[float, float, float]:
        """Return (gx, gy, gz) in rad/s."""
        return self._imu_reader.get_latest().gyro

    def read_quat(self, dt: float) -> tuple[float, float, float, float]:
        """Return orientation quaternion (w, x, y, z)."""
        _ = dt
        return self._imu_reader.get_latest().quat

    def get_imu_status(self) -> dict[str, float | int | bool]:
        return self._imu_reader.get_status()

    def shutdown(self) -> None:
        self._imu_reader.stop()

    def close(self) -> None:
        self.shutdown()