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

Nothing to register: every move class of a file in `src/moves/` is found by itself when the robot's program (or the
simulation) starts (`src/moves/discover.py`). Its name is the class name without "Move", in snake_case
(`WaveMove` -> `wave`; or set `name = "..."` in the class). Its constructor gets `controller=` if it takes one. It
appears in the dashboard's Moves list (`make dashboard`), with Start / Stop.

A file that does not load (a Python error) or a class that lacks `step` is skipped, and the robot starts anyway: the
reason, with the line of your file, shows in the dashboard's Events (and in `make robot-service-logs`).

A key or a gamepad button for it, optional, in `src/main.py`:

```python
MOVE_KEYS = {..., "w": "wave"}                    # a key toggles it (make run)
GAMEPAD_BUTTON_MOVES = {..., "LB": "wave"}
```

## Put it on the robot

```bash
make deploy HOST=radxa@microban-1a2b.local    # sends your code and restarts the robot's program
```

Or, without typing anything: the **⟳ Deploy code** button of the dashboard (`make dashboard`) runs the same command
for the robot it shows (a first click asks to confirm), its output in the page's Events.

That is all: the robot's program (the service started at boot) reads its moves when it starts, so `make deploy`
restarts it with your code, and a dashboard page already open shows the new Moves list by itself a few seconds later
(nothing to reload or type). The same command after **any change to a move's code**: the running program keeps the
code it started with until it restarts. Only the variables of the ⚙ editor change live, without a restart (see below).

The torque goes off during the restart (the old program stops the motors, the new one starts with no torque until a
move is launched): hold the robot or let it sit, never on the wall. Check the
program's messages with `make robot-service-logs`. A new Python dependency in `pyproject.toml` needs `make setup`
first. To try a move from a terminal instead (keyboard keys, its prints), `make run` stops the service for the session.

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

## Variables to edit from the dashboard

A move chooses the variables it exposes (as RhIO's parameters): they get an editor in the dashboard (the move's ⚙).

```python
class WaveMove(Move):
    options = {"amplitude": 0.4, "both_arms": False}     # the exposed variables: int / float / bool
    option_docs = {"amplitude": "arm swing (rad)", "both_arms": "wave with both arms"}

    def on_option(self, name, value):                    # called when one changed (self.options[name] already set)
        print(f"wave: {name} = {value}")
```

The move reads `self.options[...]` where it needs them; a change applies at once, the robot running (no restart).
**Save on robot** writes every move's variables to `move_options.json` (repo root on the robot), read again at the
next start over the defaults written in the code.

## Drive it live: sliders and keys

A move can also be driven while it runs, from the dashboard's Moves card: sliders, and a keyboard zone (click it, then
the keys you press go to the robot; click elsewhere and they are released).

```python
class LookMove(Move):                                   # src/moves/look.py, the full example
    sliders = {"head": (-0.8, 0.8, 0.0)}                # name -> (min, max, start value)
    keys = "← →: turn the head"                         # shown in the keyboard zone (the zone appears with it)

    def step(self, obs, command):
        if "ArrowLeft" in self.pressed:                 # the keys held now
            self.slider["head"] += 0.02
        command.target_angles["head"] = self.slider["head"]

    def on_key(self, key, down):                        # optional: once per press (down=True) and release
        if key == "space" and down:
            print("space!")
```

* `self.slider[name]`: the slider's value. It goes back to its start value at each launch of the move (the robot
  never starts with a speed left high); the move may change it too, and the page follows.
* `self.pressed`: the keys held. Their names are the browser's: `"a"` to `"z"` (lower case), `"0"` to `"9"`,
  `"space"`, `"ArrowUp"`, `"ArrowDown"`, `"ArrowLeft"`, `"ArrowRight"`, `"Enter"`, `"Shift"`...
* `on_key(key, down)` is called only while the move runs. If the page goes quiet (closed, network lost), the held keys
  are released after 0.6 s.

Unlike the variables above, sliders and keys are not saved: they are for driving, not for settings.

Your own controller written for the climbing simulator runs as a move with no code here: docs/controller.md.
