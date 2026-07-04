# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import threading
import time
from dataclasses import dataclass
import numpy as np

from ahrs.common.orientation import acc2q
from bmi088 import BMI088
import bmi088.bmi088 as _bmi_module
from constants import IMU_MOUNT_QUAT


# Python defaults: ACC=0x18, GYRO=0x69
# Our board according to the rust driver: ACC=0x19, GYRO=0x68
_bmi_module.ACC_ADDRESS = 0x19
_bmi_module.GYRO_ADDRESS = 0x68


@dataclass(frozen=True)
class IMUSnapshot:
    timestamp_s: float
    quat: tuple[float, float, float, float]
    gyro: tuple[float, float, float]
    acc: tuple[float, float, float]
    valid: bool
    error_count: int


def imu_quat_to_body(
    q: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Convert a quaternion measured in IMU frame to the trunk (body) frame.

    Applies q_body = q_imu * conjugate(IMU_MOUNT_QUAT).
    """
    w1, x1, y1, z1 = q
    w2, x2, y2, z2 = IMU_MOUNT_QUAT[0], -IMU_MOUNT_QUAT[1], -IMU_MOUNT_QUAT[2], -IMU_MOUNT_QUAT[3]
    return (
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
    )

def quat_apply_inverse(quat: list[float], vec: list[float]) -> list[float]:
    """Apply an inverse quaternion rotation to a vector.

    Args:
        quat: The quaternion in (w, x, y, z) format.
        vec: The vector in (x, y, z) format.

    Returns:
        The rotated vector in (x, y, z) format.
    """
    xyz = quat[1:]
    w = quat[0]
    t = 2 * np.cross(xyz, vec)
    return vec - w * t + np.cross(xyz, t)

class ThreadedIMUReader:
    """Reads BMI088 on a dedicated thread and exposes the latest sample snapshot."""

    def __init__(self, i2c_bus: int, frequency_hz: float = 200.0, warn_interval_s: float = 1.0) -> None:
        if frequency_hz <= 0:
            raise ValueError("frequency_hz must be > 0")

        self._imu = BMI088(i2c_bus=i2c_bus)
        self._period_s = 1.0 / frequency_hz
        self._warn_interval_s = warn_interval_s

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, name="imu-reader", daemon=True)

        now = time.perf_counter()
        self._snapshot = IMUSnapshot(
            timestamp_s=now,
            quat=(1.0, 0.0, 0.0, 0.0),
            gyro=(0.0, 0.0, 0.0),
            acc=(0.0, 0.0, 0.0),
            valid=False,
            error_count=0,
        )

        self._error_count = 0
        self._last_warn_s = 0.0

    def start(self) -> None:
        if not self._thread.is_alive():
            self._thread.start()

    def stop(self, timeout_s: float = 1.0) -> None:
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout_s)

    def get_latest(self) -> IMUSnapshot:
        with self._lock:
            return self._snapshot

    def get_status(self) -> dict[str, float | int | bool]:
        snap = self.get_latest()
        now = time.perf_counter()
        return {
            "valid": snap.valid,
            "age_s": max(0.0, now - snap.timestamp_s),
            "error_count": snap.error_count,
            "target_frequency_hz": 1.0 / self._period_s,
        }

    def _bootstrap_orientation(self, n_samples: int = 50) -> None:
        """Warm-start the Madgwick filter from a brief static accelerometer average.

        Reads *n_samples* at the normal loop rate, averages them, and uses
        acc2q to compute an initial quaternion (roll/pitch from gravity,yaw=0).
        """
        acc_sum = np.zeros(3)
        count = 0
        for _ in range(n_samples):
            try:
                ax, ay, az = self._imu.read_accelerometer()
                acc_sum += np.array([float(ax), float(ay), float(az)])
                count += 1
            except Exception:
                pass
            time.sleep(self._period_s)
        if count > 0:
            self._imu.q = list(acc2q(acc_sum / count))

    def _run_loop(self) -> None:
        self._bootstrap_orientation()
        next_tick = time.perf_counter()
        last_tick = next_tick

        while not self._stop_event.is_set():
            now = time.perf_counter()
            dt = max(1e-4, now - last_tick)
            last_tick = now

            try:
                w, x, y, z = self._imu.get_quat(dt)
                gx, gy, gz = self._imu.read_gyroscope()
                ax, ay, az = self._imu.read_accelerometer()
                with self._lock:
                    self._snapshot = IMUSnapshot(
                        timestamp_s=now,
                        quat=(float(w), float(x), float(y), float(z)),
                        gyro=(float(gx), float(gy), float(gz)),
                        acc=(float(ax), float(ay), float(az)),
                        valid=True,
                        error_count=self._error_count,
                    )
            except Exception as exc:
                self._error_count += 1
                if (now - self._last_warn_s) >= self._warn_interval_s:
                    print(f"Warning: IMU read failed ({self._error_count}): {exc}", end="\r\n", flush=True)
                    self._last_warn_s = now
                with self._lock:
                    prev = self._snapshot
                    self._snapshot = IMUSnapshot(
                        timestamp_s=prev.timestamp_s,
                        quat=prev.quat,
                        gyro=prev.gyro,
                        acc=prev.acc,
                        valid=prev.valid,
                        error_count=self._error_count,
                    )

            next_tick += self._period_s
            sleep_s = next_tick - time.perf_counter()
            if sleep_s > 0:
                time.sleep(sleep_s)
            else:
                # Reset cadence anchor when late to avoid accumulating drift.
                next_tick = time.perf_counter()