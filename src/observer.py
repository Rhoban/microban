# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright 2026 Marc Duclusaud

from dataclasses import dataclass, field
import time

from controller import ControllerProtocol
from input.input_source import UserInput
from constants import MOTOR_TO_ID
from imu_reader import imu_quat_to_body, quat_apply_inverse


@dataclass
class RobotState:
    """Hardware sensor readings for one scheduler iteration."""

    time_s: float = 0.0

    # IMU data
    acc: list[float] = field(default_factory=list) # accelerometer readings in g (ax, ay, az)
    gyro: list[float] = field(default_factory=list) # gyroscope readings in rad/s (gx, gy, gz)
    quat: list[float] = field(default_factory=list) # IMU orientation as a quaternion (w, x, y, z)
    body_quat: list[float] = field(default_factory=list) # body frame orientation as a quaternion (w, x, y, z)
    projected_gravity: list[float] = field(default_factory=list) # gravity vector projected in body frame
    
    # Motor states
    motor_positions: dict[str, float] = field(default_factory=dict)
    motor_velocities: dict[str, float] = field(default_factory=dict)
    motor_currents: dict[str, float] = field(default_factory=dict)  # Amps, signed (overcurrent safety)
    measured_currents: dict[str, float] = field(default_factory=dict)  # Amps, whenever read (dashboard)

    # Logging
    motor_voltages: dict[str, float] = field(default_factory=dict)


@dataclass
class Observation:
    """Full observation passed through the move pipeline each tick."""

    robot_state: RobotState = field(default_factory=RobotState)
    user_input: UserInput = field(default_factory=UserInput)


class Observer:
    def __init__(self, controller: ControllerProtocol):
        self.controller = controller
        self._last_imu_warn_s: float = 0.0
        self._imu_warn_interval_s: float = 1.0

        self.observe_voltage: bool = False
        
        # When True, the overcurrent safety uses the measured present_current. When False (default), it
        # falls back to the position-error proxy in the scheduler. On the real robot the current comes with
        # position and velocity in the same bus read (RobotController.sync_read_state), so this costs nothing;
        # other controllers (simulation) read it separately, only when True.
        self.observe_current: bool = False

    def read_state(self, dt: float) -> RobotState:
        """Read current motor positions from the controller."""
        state = RobotState(time_s=time.perf_counter())

        motor_names = list(MOTOR_TO_ID.keys())
        motor_ids = list(MOTOR_TO_ID.values())
        read_all = getattr(self.controller, "sync_read_state", None)    # the real robot: one bus transaction
        if read_all is not None:
            angles, velocities, currents = read_all(motor_ids)
        else:
            angles = self.controller.sync_read_present_position(motor_ids)
            velocities = self.controller.sync_read_present_velocity(motor_ids)
            currents = self.controller.sync_read_present_current(motor_ids) if self.observe_current else None
        state.motor_positions = dict(zip(motor_names, angles))
        state.motor_velocities = dict(zip(motor_names, velocities))
        if currents is not None:
            state.measured_currents = dict(zip(motor_names, currents))

        if self.observe_current:
            state.motor_currents = dict(zip(motor_names, currents))

        if self.observe_voltage:
            voltages = self.controller.sync_read_present_input_voltage(motor_ids)
            state.motor_voltages = dict(zip(motor_names, voltages))

        try:
            state.acc = list(self.controller.read_acc())
            state.gyro = list(self.controller.read_gyro())
            state.quat = list(self.controller.read_quat(dt))

            # Project gravity vector into body frame
            state.body_quat = list(imu_quat_to_body(state.quat))
            state.projected_gravity = list(quat_apply_inverse(state.body_quat, [0.0, 0.0, -1.0]))

        except Exception as exc:
            now = time.perf_counter()
            if (now - self._last_imu_warn_s) >= self._imu_warn_interval_s:
                print(f"Warning: observer IMU read failed: {exc}", end="\r\n", flush=True)
                self._last_imu_warn_s = now

        return state