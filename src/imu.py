"""Standalone IMU reader — prints roll, pitch and yaw at 2 Hz.

Usage:
    uv run src/imu.py
    make imu
"""

import math
import time

from bmi088 import BMI088
import bmi088.bmi088 as _bmi_module
from constants import IMU_I2C_BUS

# The library default gyro address is 0x69, on our board it's 0x68
_bmi_module.GYRO_ADDRESS = 0x68

imu = BMI088(i2c_bus=IMU_I2C_BUS)

print("IMU (BMI088) — roll/pitch/yaw. Ctrl-C to stop.")
print(f"{'roll':>10}  {'pitch':>10}  {'yaw':>10}")

dt = 0.5
while True:
    w, x, y, z = imu.get_quat(dt)
    roll = math.degrees(math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x)))))
    yaw = math.degrees(math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))
    print(f"{roll:>+9.1f}°  {pitch:>+9.1f}°  {yaw:>+9.1f}°", flush=True)
    time.sleep(dt)
