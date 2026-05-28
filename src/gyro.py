"""Standalone gyroscope reader — prints angular velocity at 2 Hz.

Usage:
    uv run src/gyro.py
    make gyro
"""

import time

from bmi088 import BMI088
import bmi088.bmi088 as _bmi_module
from constants import IMU_I2C_BUS

# The library default gyro address is 0x69, on our board it's 0x68
_bmi_module.GYRO_ADDRESS = 0x68

imu = BMI088(i2c_bus=IMU_I2C_BUS)

print("Gyro (BMI088) — angular velocity in rad/s. Ctrl-C to stop.")
print(f"{'gx':>10}  {'gy':>10}  {'gz':>10}")

while True:
    gx, gy, gz = imu.read_gyroscope()
    print(f"{gx:>+9.4f}  {gy:>+9.4f}  {gz:>+9.4f}", flush=True)
    time.sleep(0.5)
