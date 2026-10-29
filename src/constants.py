# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

import numpy as np

MOTOR_TO_ID = {
    "left_hip_yaw": 11,
    "left_hip_roll": 12,
    "left_hip_pitch": 13,
    "left_knee": 14,
    "left_ankle_pitch": 15,
    "left_ankle_roll": 16,
    "right_hip_yaw": 21,
    "right_hip_roll": 22,
    "right_hip_pitch": 23,
    "right_knee": 24,
    "right_ankle_pitch": 25,
    "right_ankle_roll": 26,
    "left_shoulder_pitch": 31,
    "left_shoulder_roll": 32,
    "left_elbow": 33,
    "right_shoulder_pitch": 41,
    "right_shoulder_roll": 42,
    "right_elbow": 43,
    "head": 51,
}

ID_TO_MOTOR = {v: k for k, v in MOTOR_TO_ID.items()}

# Joint angles: every zero is its motor's zero (microban_model). The shoulder pitch holds the arm forward at 0,
# along the body at +90 deg.
NEUTRAL_POSE = {
    "left_hip_yaw": float(np.deg2rad(0.0)),
    "left_hip_roll": float(np.deg2rad(5.0)),
    "left_hip_pitch": float(np.deg2rad(-10.0)),
    "left_knee": float(np.deg2rad(0.0)),
    "left_ankle_pitch": float(np.deg2rad(0.0)),
    "left_ankle_roll": float(np.deg2rad(-5.0)),
    "right_hip_yaw": float(np.deg2rad(0.0)),
    "right_hip_roll": float(np.deg2rad(-5.0)),
    "right_hip_pitch": float(np.deg2rad(-10.0)),
    "right_knee": float(np.deg2rad(0.0)),
    "right_ankle_pitch": float(np.deg2rad(0.0)),
    "right_ankle_roll": float(np.deg2rad(5.0)),
    "left_shoulder_pitch": float(np.deg2rad(100.0)),
    "left_shoulder_roll": float(np.deg2rad(10.0)),
    "left_elbow": float(np.deg2rad(-20.0)),
    "right_shoulder_pitch": float(np.deg2rad(100.0)),
    "right_shoulder_roll": float(np.deg2rad(-10.0)),
    "right_elbow": float(np.deg2rad(-20.0)),
    "head": float(np.deg2rad(0.0)),
}

MOTOR_SIGN = {
    "left_hip_yaw": -1.0,
    "left_hip_roll": 1.0,
    "left_hip_pitch": -1.0,
    "left_knee": 1.0,
    "left_ankle_pitch": 1.0,
    "left_ankle_roll": -1.0,
    "right_hip_yaw": -1.0,
    "right_hip_roll": 1.0,
    "right_hip_pitch": 1.0,
    "right_knee": -1.0,
    "right_ankle_pitch": -1.0,
    "right_ankle_roll": -1.0,
    "left_shoulder_pitch": 1.0,
    "left_shoulder_roll": -1.0,
    "left_elbow": 1.0,
    "right_shoulder_pitch": -1.0,
    "right_shoulder_roll": -1.0,
    "right_elbow": -1.0,
    "head": 1.0,
}

# Position P Gain (Dynamixel register value)
KP_DEFAULT: int = 400        # ~0.886 Nm/rad in MuJoCo
KP_RL: int = 125             # ~0.277 Nm/rad in MuJoCo
KP_GAIN_PRM: float = 0.0022  # Nm/rad per register unit (for Xl330)

# BAM motor model (bam package, XL330 m6)
# The robot runs on a bench power supply (no battery for now): 8.4 V, then 5 m of 16 AWG cable (~13.2 mOhm/m, 10 m
# of conductor: 0.13 Ohm) and the robot's own wiring. At rest (~1 A) the motors read 8.1-8.2 V: ~0.25 Ohm in all
# (estimate; to measure: motor voltage at rest and under load, e.g. on the dashboard)
BAM_VIN: float = 8.4
BAM_VIN_MIN: float = 6.0
BAM_VIN_DROP_RESISTANCE: float = 0.25   # [Ohm]: vin drops by R * sum(|torque|) / kt (BAM >= 1.0.2)
BAM_MAX_CURRENT: float = 1.75 # XL330 firmware current limit [A]: clips motor torque to ±BAM_MAX_CURRENT * kt

# Overcurrent safety: emergency torque-off when the summed |present_current| of all
# motors stays above OVERCURRENT_CUTOFF_A for OVERCURRENT_DEBOUNCE_TICKS consecutive ticks.
# Goal: cut the robot before a current spike (e.g. all motors snapping during a fall) trips the BMS.
PRESENT_CURRENT_UNIT_A: float = 0.001   # XL330 present_current register unit (1.0 mA/LSB)
# No BMS for now (bench power supply, 2026-10-27): the safety is off. With a battery and its BMS, set it again
# (15 A was the threshold: below the BMS trip, above the normal walk peak).
OVERCURRENT_CUTOFF_A: float | None = None   # total pack current threshold [A]; None: no overcurrent safety
OVERCURRENT_DEBOUNCE_TICKS: int = 2     # consecutive over-threshold ticks before cutting

# Current proxy used when present_current is NOT read (Observer.observe_current = False), so the
# safety needs no extra bus transaction. Reproduces the bam XL330 m6 voltage-controlled model from
# data already read (present_position, present_velocity) and the command target:
#   duty = clip(PROXY_KP * PROXY_ERROR_GAIN * (target - q), ±PROXY_MAX_PWM)
#   I    = (PROXY_VIN * duty - PROXY_KT * dq) / PROXY_R      then |I| capped at BAM_MAX_CURRENT
PROXY_KT: float = 0.366                  # XL330 m6 torque constant [Nm/A]
PROXY_R: float = 2.811                   # XL330 m6 motor resistance [Ohm]
PROXY_VIN: float = BAM_VIN               # supply voltage [V]
PROXY_ERROR_GAIN: float = 0.0028773775   # duty cycle per (kp * rad), XL330 encoder/gain scaling
PROXY_MAX_PWM: float = 1.0               # max duty cycle magnitude
PROXY_KP: int = KP_RL                    # firmware P gain assumed by the proxy (walking regime)
OVERCURRENT_PROXY_DELAY_TICKS: int = 3   # number of ticks to delay the proxy current estimate

# Velocity command limits [m/s, m/s, rad/s], applied centrally to every input source.
# Input sources emit normalized commands in [-1, 1]; scale_velocity() maps them to these.
# Rotation gets a wider range when turning in place (vx = vy = 0) than while translating.
VX_MAX: float = 0.7
VX_MAX_BACKWARD: float = 0.5  # backward (vx < 0) is capped lower than forward
VY_MAX: float = 0.3
VTHETA_MAX_STATIONARY: float = 3.0
VTHETA_MAX_MOVING: float = 1.5

# The board, from the device tree: the Raspberry Pi Zero 2 W (Microban v1) or the Radxa ROCK 3C (Microban v2)
# (UART2 and I2C3 overlays: motors on /dev/ttyS2, BMI088 on i2c-3; checked 2026-10-27)
def _board_model() -> str:
    try:
        with open("/proc/device-tree/model") as f:
            return f.read().strip("\x00\n")
    except OSError:
        return ""


BOARD_MODEL: str = _board_model()
IS_RADXA: bool = "Radxa" in BOARD_MODEL

# Dynamixel bus (UART, 1 Mbps) and IMU (BMI088) I2C bus number
MOTOR_SERIAL_PORT: str = "/dev/ttyS2" if IS_RADXA else "/dev/ttyAMA0"
IMU_I2C_BUS: int = 3 if IS_RADXA else 1

# Rotation from trunk frame (body) to IMU sensor frame
IMU_MOUNT_QUAT: tuple[float, float, float, float] = (0.5, 0.5, 0.5, 0.5)   # Microban v2 (Radxa board): the model's imu site

# Observation DoF ordering
OBSERVATION_DOF_ORDER = [
    "right_shoulder_pitch",
    "right_shoulder_roll",
    "right_elbow",
    "right_hip_yaw",
    "right_hip_roll",
    "right_hip_pitch",
    "right_knee",
    "right_ankle_pitch",
    "right_ankle_roll",
    "left_shoulder_pitch",
    "left_shoulder_roll",
    "left_elbow",
    "left_hip_yaw",
    "left_hip_roll",
    "left_hip_pitch",
    "left_knee",
    "left_ankle_pitch",
    "left_ankle_roll"
]

# The moves a key (make run's terminal, make sim's viewer) or a gamepad button toggles: add yours here
MOVE_KEYS: dict[str, str] = {"h": "head", "s": "squat", "v": "walk"}
GAMEPAD_BUTTON_MOVES: dict[str, str] = {"A": "walk"}   # B is the gamepad's stop button (input/gamepad_input.py)
