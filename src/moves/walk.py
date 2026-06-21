import onnxruntime as ort

from constants import MOTOR_TO_ID, KP_DEFAULT, KP_RL, OBSERVATION_DOF_ORDER, NEUTRAL_POSE
from controller import ControllerProtocol
from observer import Observation
from moves.move import MotorCommand, Move, MoveState


class WalkMove(Move):
    """Walk using a RL policy trained in simulation."""

    def __init__(self, controller: ControllerProtocol | None = None) -> None:
        super().__init__()
        self._controller = controller
        self._last_action = [0.0] * len(OBSERVATION_DOF_ORDER)

        # Load ONNX policy
        self._ort_session = ort.InferenceSession("src/agents/walk.onnx")

        # Safety parameters
        self._projected_gravity_z_threshold = -0.5  # Threshold for detecting a fall based on projected gravity

        # Logging
        # self.position = {
        #     "head": [],
        #     "left_hip_yaw": [],
        #     "left_hip_roll": [],
        #     "left_hip_pitch": [],
        #     "left_knee": [],
        #     "left_ankle_pitch": [],
        #     "left_ankle_roll": [],
        #     "right_hip_yaw": [],
        #     "right_hip_roll": [],
        #     "right_hip_pitch": [],
        #     "right_knee": [],
        #     "right_ankle_pitch": [],
        #     "right_ankle_roll": [],
        #     "left_shoulder_pitch": [],
        #     "left_shoulder_roll": [],
        #     "left_elbow": [],
        #     "right_shoulder_pitch": [],
        #     "right_shoulder_roll": [],
        #     "right_elbow": [],
        # }
        # self.voltage = {
        #     "head": [],
        #     "left_hip_yaw": [],
        #     "left_hip_roll": [],
        #     "left_hip_pitch": [],
        #     "left_knee": [],
        #     "left_ankle_pitch": [],
        #     "left_ankle_roll": [],
        #     "right_hip_yaw": [],
        #     "right_hip_roll": [],
        #     "right_hip_pitch": [],
        #     "right_knee": [],
        #     "right_ankle_pitch": [],
        #     "right_ankle_roll": [],
        #     "left_shoulder_pitch": [],
        #     "left_shoulder_roll": [],
        #     "left_elbow": [],
        #     "right_shoulder_pitch": [],
        #     "right_shoulder_roll": [],
        #     "right_elbow": [],
        # }
        
    def on_start(self, obs: Observation, command: MotorCommand) -> None:
        if self._controller is not None:
            ids = list(MOTOR_TO_ID.values())
            self._controller.sync_write_kp(ids, [KP_RL] * len(ids))
        self.state = MoveState.ACTIVE

    def step(self, obs: Observation, command: MotorCommand) -> None:
        input_obs = self.build_observation(obs)

        # Safety check: if the robot is fallen, stop the policy
        if obs.robot_state.projected_gravity[2] > self._projected_gravity_z_threshold:
            return
        
        # Run policy
        ort_inputs = {self._ort_session.get_inputs()[0].name: [input_obs]}
        ort_outs = self._ort_session.run(None, ort_inputs)
        action = ort_outs[0][0]
        self._last_action = action.tolist()

        # Update command
        for i, name in enumerate(OBSERVATION_DOF_ORDER):
            command.target_angles[name] = NEUTRAL_POSE[name] + action[i]

        # Log positions and voltages
        # for name in MOTOR_TO_ID.keys():
        #     self.position[name].append(obs.robot_state.motor_positions[name])
        #     self.voltage[name].append(obs.robot_state.motor_voltages[name])

    def build_observation(self, obs: Observation) -> list[float]:
        """Build policy observation from robot state."""
        input_obs = []
        
        # IMU data: gyroscope and projected gravity in body frame
        input_obs.extend(obs.robot_state.gyro)
        input_obs.extend(obs.robot_state.projected_gravity)
        
        # Motor positions
        for name in OBSERVATION_DOF_ORDER:
            input_obs.append(obs.robot_state.motor_positions[name] - NEUTRAL_POSE[name])
        
        # Motor velocities
        for name in OBSERVATION_DOF_ORDER:
            input_obs.append(obs.robot_state.motor_velocities[name])
        
        # Last action
        input_obs.extend(self._last_action)

        # Command
        input_obs.append(obs.user_input.velocity["vx"])
        input_obs.append(obs.user_input.velocity["vy"])
        input_obs.append(obs.user_input.velocity["vtheta"])

        return input_obs

    def on_stop(self, obs: Observation, command: MotorCommand) -> None:
        if self._controller is not None:
            ids = list(MOTOR_TO_ID.values())
            self._controller.sync_write_kp(ids, [KP_DEFAULT] * len(ids))
        self.state = MoveState.INACTIVE

        # Save json logs
        # import json
        # with open("walk_log.json", "w") as f:
        #     json.dump({
        #         "position": self.position,
        #         "voltage": self.voltage,
        #     }, f, indent=4)
