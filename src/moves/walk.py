import onnxruntime as ort
import numpy as np

from constants import MOTOR_TO_ID, KP_DEFAULT, KP_RL, OBSERVATION_DOF_ORDER
from controller import ControllerProtocol
from observer import Observation
from moves.move import MotorCommand, Move, MoveState


# Set to True if the policy use a reference phase for the gait cycle
USE_REFERENCE_PHASE = True

# Set to True to log motor positions and voltages during the walk move
# Note: requires to set observe_voltage = True in the Observer to log voltages
LOGGING = False


class WalkMove(Move):
    """Walk using a RL policy trained in simulation."""

    def __init__(self, controller: ControllerProtocol | None = None) -> None:
        super().__init__()
        self._controller = controller
        self._last_action = [0.0] * len(OBSERVATION_DOF_ORDER)

        # Load ONNX policy
        self._ort_session = ort.InferenceSession("src/agents/walk.onnx")

        # Reference pose: read from ONNX metadata
        meta = self._ort_session.get_modelmeta().custom_metadata_map
        names = meta["joint_names"].split(",")
        positions = [float(v) for v in meta["default_joint_pos"].split(",")]
        self._default_pose: dict[str, float] = dict(zip(names, positions))

        # Reference phase for gait cycle
        self._phase_step = 0
        self._phase_total_steps = 20

        # Safety parameters
        self._projected_gravity_z_threshold = -0.5  # Threshold for detecting a fall based on projected gravity

        # Logging
        self.position = {
            "head": [],
            "left_hip_yaw": [],
            "left_hip_roll": [],
            "left_hip_pitch": [],
            "left_knee": [],
            "left_ankle_pitch": [],
            "left_ankle_roll": [],
            "right_hip_yaw": [],
            "right_hip_roll": [],
            "right_hip_pitch": [],
            "right_knee": [],
            "right_ankle_pitch": [],
            "right_ankle_roll": [],
            "left_shoulder_pitch": [],
            "left_shoulder_roll": [],
            "left_elbow": [],
            "right_shoulder_pitch": [],
            "right_shoulder_roll": [],
            "right_elbow": [],
        }
        self.voltage = {
            "head": [],
            "left_hip_yaw": [],
            "left_hip_roll": [],
            "left_hip_pitch": [],
            "left_knee": [],
            "left_ankle_pitch": [],
            "left_ankle_roll": [],
            "right_hip_yaw": [],
            "right_hip_roll": [],
            "right_hip_pitch": [],
            "right_knee": [],
            "right_ankle_pitch": [],
            "right_ankle_roll": [],
            "left_shoulder_pitch": [],
            "left_shoulder_roll": [],
            "left_elbow": [],
            "right_shoulder_pitch": [],
            "right_shoulder_roll": [],
            "right_elbow": [],
        }
        
    def on_start(self, obs: Observation, command: MotorCommand) -> None:
        if self._controller is not None:
            ids = list(MOTOR_TO_ID.values())
            self._controller.sync_write_kp(ids, [KP_RL] * len(ids))
        self.state = MoveState.ACTIVE

    def step(self, obs: Observation, command: MotorCommand) -> None:
        # Update reference phase
        if USE_REFERENCE_PHASE:
            commanded_vel = np.mean([np.abs(obs.user_input.velocity["vx"]), np.abs(obs.user_input.velocity["vy"]), np.abs(obs.user_input.velocity["vtheta"])])
            if commanded_vel > 0.01:
                self._phase_step += 1
            else:
                self._phase_step = 0

        # Safety check: if the robot is fallen, stop the policy
        if obs.robot_state.projected_gravity[2] > self._projected_gravity_z_threshold:
            return
        
        # Run policy
        input_obs = self.build_observation(obs)
        ort_inputs = {self._ort_session.get_inputs()[0].name: [input_obs]}
        ort_outs = self._ort_session.run(None, ort_inputs)
        action = ort_outs[0][0]
        self._last_action = action.tolist()

        # Update command
        for i, name in enumerate(OBSERVATION_DOF_ORDER):
            command.target_angles[name] = self._default_pose[name] + action[i]

        # Log positions and voltages
        if LOGGING:
            for name in MOTOR_TO_ID.keys():
                self.position[name].append(obs.robot_state.motor_positions[name])
                self.voltage[name].append(obs.robot_state.motor_voltages[name])

    def build_observation(self, obs: Observation) -> list[float]:
        """Build policy observation from robot state."""
        input_obs = []
        
        # IMU data: gyroscope and projected gravity in body frame
        input_obs.extend(obs.robot_state.gyro)
        input_obs.extend(obs.robot_state.projected_gravity)
        
        # Motor positions
        for name in OBSERVATION_DOF_ORDER:
            input_obs.append(obs.robot_state.motor_positions[name] - self._default_pose[name])
        
        # Motor velocities
        for name in OBSERVATION_DOF_ORDER:
            input_obs.append(obs.robot_state.motor_velocities[name])
        
        # Last action
        input_obs.extend(self._last_action)

        # Command
        input_obs.append(obs.user_input.velocity["vx"])
        input_obs.append(obs.user_input.velocity["vy"])
        input_obs.append(obs.user_input.velocity["vtheta"])

        # Reference phase
        if USE_REFERENCE_PHASE:
            reference_phase = (self._phase_step % self._phase_total_steps) / self._phase_total_steps * 2 * np.pi
            input_obs.append(np.cos(reference_phase))
            input_obs.append(np.sin(reference_phase))

        return input_obs

    def on_stop(self, obs: Observation, command: MotorCommand) -> None:
        if self._controller is not None:
            ids = list(MOTOR_TO_ID.values())
            self._controller.sync_write_kp(ids, [KP_DEFAULT] * len(ids))
        self.state = MoveState.INACTIVE

        # Save json logs
        if LOGGING:
            import json
            with open("walk_log.json", "w") as f:
                json.dump({
                    "position": self.position,
                    "voltage": self.voltage,
                }, f, indent=4)
