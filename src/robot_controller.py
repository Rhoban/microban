# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import time

from rustypot import Xl330PyController
import numpy as np

from constants import MOTOR_TO_ID, MOTOR_SIGN, IMU_I2C_BUS, MOTOR_SERIAL_PORT, PRESENT_CURRENT_UNIT_A
from imu_reader import ThreadedIMUReader


class RobotController:
    """Wraps Xl330PyController."""

    def __init__(self, serial_port: str = MOTOR_SERIAL_PORT, baudrate: int = 1_000_000, timeout: float = 0.1) -> None:
        self._controller = Xl330PyController(serial_port=serial_port, baudrate=baudrate, timeout=timeout)
        # Fast Sync Read (protocol 2.0): every motor answers a sync read in one status packet (one header instead of
        # one per motor): sync_read_state takes 3.7 ms for 18 motors at 1 Mbps (Radxa, 2026-10-27)
        self._controller.set_fast_sync_read(True)
        self._kp: dict[int, int] = {}              # last position gain written to each motor
        self._id_to_sign: dict[int, float] = {MOTOR_TO_ID[name]: MOTOR_SIGN[name] for name in MOTOR_TO_ID}
        self._imu_reader = ThreadedIMUReader(i2c_bus=IMU_I2C_BUS, frequency_hz=200.0)
        self._imu_reader.start()

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
            positions.append((int.from_bytes(b[6:10], "little", signed=True) - 2048) * 2 * np.pi / 4096 * sign)
        return positions, velocities, currents

    def read_present_position(self, motor_id: int) -> float:
        raw = self._controller.read_present_position(motor_id)[0]        # rustypot answers a list
        return raw * self._id_to_sign[motor_id]

    def sync_read_present_velocity(self, ids: list[int]) -> list[float]:
        raw = np.array(self._controller.sync_read_present_velocity(ids)) * 0.229 * np.pi / 30
        return [r * self._id_to_sign[motor_id] for motor_id, r in zip(ids, raw)]
    
    def read_present_velocity(self, motor_id: int) -> float:
        raw = self._controller.read_present_velocity(motor_id)[0] * 0.229 * np.pi / 30   # rustypot: a list
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
        self._kp.update(zip(ids, gains))           # a reboot loses it (RAM): reboot() writes it back

    def sync_read_health(self, ids: list[int]) -> tuple[list[int], list[int], list[float], list[int]]:
        """Torque enable (64), hardware error status (70), input voltage (144, V) and temperature (146, degC): two
        small sync reads, for the dashboard about once a second."""
        torque, error, voltage, temperature = [], [], [], []
        for raw in self._controller.sync_read_raw_data(ids, 64, 7):
            b = bytes(raw)
            torque.append(b[0])
            error.append(b[6])
        for raw in self._controller.sync_read_raw_data(ids, 144, 3):
            b = bytes(raw)
            voltage.append(int.from_bytes(b[0:2], "little") / 10)
            temperature.append(b[2])
        return torque, error, voltage, temperature

    def reboot(self, motor_id: int, timeout_s: float = 1.5) -> float:
        """Reboot one motor (clears a hardware error: overheating, overload...), wait until it answers again, write
        back its position gain. Its torque stays off. Returns the time it took (s); raises if it does not come back."""
        t0 = time.perf_counter()
        self._controller.reboot(motor_id)
        time.sleep(0.1)
        while not self._ping(motor_id):
            if time.perf_counter() - t0 > timeout_s:
                raise RuntimeError(f"motor {motor_id} does not answer after its reboot")
            time.sleep(0.02)
        if motor_id in self._kp:
            self._controller.write_position_p_gain(motor_id, self._kp[motor_id])
        return time.perf_counter() - t0

    def _ping(self, motor_id: int) -> bool:
        try:
            return bool(self._controller.ping(motor_id))
        except RuntimeError:
            return False

    def write_torque_enable(self, motor_id: int, on: bool) -> None:
        self._controller.write_torque_enable(motor_id, on)

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