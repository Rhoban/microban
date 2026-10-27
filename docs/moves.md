# Moves: write your own

A move is a class that writes joint targets every tick (50 Hz). The scheduler runs the moves that are asked (keyboard,
gamepad, or the dashboard's Moves list) and sends their targets to the motors.

```python
# src/moves/wave.py
import math
from moves.move import Move, MoveState, MotorCommand
from observer import Observation


class WaveMove(Move):
    description = "Wave the right arm"     # shown in the dashboard's Moves list
    power_up = "neutral"                    # torque off when launched: ramp to NEUTRAL_POSE first ("current": stay)

    def on_start(self, obs: Observation, command: MotorCommand) -> None:
        self.t0 = obs.robot_state.time_s    # called each tick while STARTING: set ACTIVE when the transition is done
        self.state = MoveState.ACTIVE

    def step(self, obs: Observation, command: MotorCommand) -> None:
        t = obs.robot_state.time_s - self.t0
        command.target_angles["right_shoulder_roll"] = -0.3 - 0.4 * (1 + math.sin(3 * t))

    def on_stop(self, obs: Observation, command: MotorCommand) -> None:
        self.state = MoveState.INACTIVE     # called each tick while STOPPING: set INACTIVE when done
```

Register it in `src/main.py` (and `src/sim/sim_main.py` for the simulation):

```python
MOVE_KEYS = {..., "w": "wave"}                    # a key toggles it
GAMEPAD_BUTTON_MOVES = {..., "LB": "wave"}        # optional
moves={..., "wave": WaveMove()},
```

It then appears in the dashboard's Moves list (`make dashboard HOST=...`), with Start / Stop.

## What a move gets and gives

* `obs.robot_state`: `motor_positions`, `motor_velocities` (joint name -> rad, rad/s; every zero at the motor's zero,
  see docs/model.md), `measured_currents`, `gyro`, `acc` (IMU frame), `body_quat`, `projected_gravity` (trunk
  frame), `time_s`. `obs.user_input`: `active_moves`, `velocity` (sticks / arrows).
* `command.target_angles`: joint name -> target (rad). It starts each tick at `NEUTRAL_POSE`; a move overwrites the
  joints it drives. Several moves may run together (the head and the walk); the later one in `moves` wins a joint.
* `preload()`: called once before the loop (load a network there). A move that needs the controller (the servos'
  gain, `sync_write_kp`) takes it in its constructor, as `WalkMove(controller=controller)`.

## The life of a move

* INACTIVE -> STARTING when it is asked (its key, button or the dashboard), -> ACTIVE when `on_start` says so;
  ACTIVE -> STOPPING when it is no longer asked, -> INACTIVE when `on_stop` says so.
* Torque: off while no move runs. The first move launched turns it on (`power_up`: ramp to `NEUTRAL_POSE` in 2 s, or
  hold where the robot is), and it goes off again when every move is INACTIVE.
* `em` (dashboard) stops every move at once and cuts the torque; `init` stops them and holds every motor at zero.
  After either, a move still asked by a key stays off until it is asked again.
* Switches: a name a key toggles that is not a move (a move reads it in `obs.user_input.active_moves`, e.g. a
  "go" for a move that waits): pass it as `Scheduler(..., switches=["name"])` and it is listed in the dashboard too.

Your own controller written for the climbing simulator runs as a move with no code here: docs/controller.md.
