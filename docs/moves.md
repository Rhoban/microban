# Moves: write your own

A move is a class that gives the 19 servos their targets every tick (50 Hz). The robot's program runs the moves that
are asked (the dashboard's Moves list, keyboard, gamepad) and sends their targets to the motors. There are two ways
to write one: a **simple move** (start here: the same file runs in the simulator and on the robot) and an
**advanced move** (the robot's program's own class, for full control).

## A simple move

```python
# src/moves/hold.py
import math
from microban_model import JOINTS

HEAD = JOINTS.index("head")


class HoldMove:                                 # no base class
    description = "Hold the pose, turn the head" # shown in the dashboard's Moves list (optional)
    options = {"amplitude": 0.3}                # variables edited live in the dashboard (optional, see below)
    sliders = {"speed": (0.0, 2.0, 0.5)}        # name -> (min, max, start), shown while it runs (optional)

    def reset(self, obs):                       # when it starts (optional)
        self.start, self.phase = obs["q"].copy(), 0.0

    def step(self, obs):                        # every 20 ms: the observation in, the 19 targets out
        self.phase += 0.02 * self.slider["speed"]
        target = self.start.copy()
        target[HEAD] += self.options["amplitude"] * math.sin(self.phase)
        return target                           # rad, in the order JOINTS; or None: keep the last ones
```

* `obs` is the simulator's observation, built on the robot from what it measures: `q`, `dq` (joints, order `JOINTS`,
  every zero at the motor's zero), `gyro` (rad/s), `accel` (m/s^2), `gravity` (unit vector) in the trunk frame,
  `quat` (trunk orientation w x y z), `current` (A), `time` (s).
* The same file runs in the fast simulator, as fast as it computes, for planning or learning:
  `run_move(HoldMove(), sim, seconds)` in [microban_sim](https://github.com/Rhoban/microban_sim) or the hackathon's
  [climbing simulator](https://github.com/rock-climbing-robots/simulator) (`load_moves(path)` loads a file's moves).
  There, nobody edits the options and sliders: they keep their defaults.
* It starts where the robot is: the torque goes on with no move to the neutral pose first, so it may start hanging on
  the wall. While it runs the servos' gain is `kp_fw` (a class attribute, 125 by default), back to normal after.
* Optional too: `variants` (the robot versions it is for, both by default, see below), `option_docs`, `keys`,
  `on_key(key, down)`, `on_option(name, value)`, `name`: as an advanced move's, below.
* A file it needs (a network) goes in the repository with it (`make deploy` sends it), loaded from a path relative
  to the move's file (`pathlib.Path(__file__).parent / "net.onnx"`).

A file kept outside `src/moves/` runs too: `make run CONTROLLER=path/to/file.py` (or `make sim ...
CONTROLLER=...`) adds its simple moves for that session; a class named `Controller` is the move `controller`,
started and stopped with [c] (gamepad: Y).

## An advanced move

A class derived from `Move` gets the robot's program's own view: its states (starting, stopping), the robot's raw
measurements by joint name, the user's input, the servos (`controller`). The walk, the squat and the head are written
this way.

```python
# src/moves/wave.py
import math
from moves.move import ALL, Move, MoveState, MotorCommand
from observer import Observation


class WaveMove(Move):
    description = "Wave the right arm"     # shown in the dashboard's Moves list
    variants = ALL                          # the robots it is for: ALL, (CLASSIC,) or (CLIMBER,) (required)
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

## Found by itself

Nothing to register: every move class (simple or advanced) of a file in `src/moves/` is found by itself when the robot's program (or the
simulation) starts (`src/moves/discover.py`). Its name is the class name without "Move", in snake_case
(`WaveMove` -> `wave`; or set `name = "..."` in the class). Its constructor gets `controller=` if it takes one. It
appears in the dashboard's Moves list (`make dashboard`), with Start / Stop.

**Which robot it is for.** `variants` is required for an advanced move (a simple move is for both unless it sets it): `ALL` for any version of the robot, `(CLASSIC,)` for the walking
hands and feet only, `(CLIMBER,)` for the climbing forearms and feet only (`from moves.move import ALL, CLASSIC,
CLIMBER`). The robot knows its version (the dashboard's **robot version** menu changes it, saved on the robot in
`robot_variant.txt`; classic until set; the simulation: `make sim` classic, `make sim WALL=N2` climber): it runs a move only on
the versions it is made for (the keyboard and the gamepad too), and the dashboard lists only those. The walk, trained
with the walking feet, is `(CLASSIC,)`: a climber does not walk.

A file that does not load (a Python error), a move class that cannot be built or does not say its `variants` is skipped, and
the robot starts anyway: the reason, with the line of your file, shows in the dashboard's Events (and in
`make robot-service-logs`).

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

## What an advanced move gets and gives

* `obs.robot_state`: `motor_positions`, `motor_velocities` (joint name -> rad, rad/s; every zero at the motor's zero,
  see docs/model.md), `measured_currents`, `gyro`, `acc` (IMU frame), `body_quat`, `projected_gravity` (trunk
  frame), `time_s`. `obs.user_input`: `active_moves`, `velocity` (sticks / arrows).
* `command.target_angles`: joint name -> target (rad). It starts each tick at `NEUTRAL_POSE`; a move overwrites the
  joints it drives. Several moves may run together (the head and the walk); the later one in `moves` wins a joint.
* `print()` in a move (simple or advanced) goes to the dashboard's Events (`wave: text`, at most 10 lines a second per move; the rest is
  counted there) and to the robot's log as before (`make robot-service-logs`, or the terminal with `make run`).
* `preload()`: called once before the loop (load a network there). A move that needs the controller (the servos'
  gain, `sync_write_kp`) takes it in its constructor, as `WalkMove(controller=controller)`.

## The life of an advanced move

* INACTIVE -> STARTING when it is asked (its key, button or the dashboard), -> ACTIVE when `on_start` says so;
  ACTIVE -> STOPPING when it is no longer asked, -> INACTIVE when `on_stop` says so.
* Torque: off while no move runs. The first move launched turns it on (`power_up`: ramp to `NEUTRAL_POSE` in 2 s, or
  hold where the robot is), and it goes off again when every move is INACTIVE.
* `em` (dashboard) stops every move at once and cuts the torque; `init` stops them and holds every motor at zero.
  After either, a move still asked by a key stays off until it is asked again.
* Switches: a name a key toggles that is not a move (a move reads it in `obs.user_input.active_moves`, e.g. a
  "go" for a move that waits): pass it as `Scheduler(..., switches=["name"])` and it is listed in the dashboard too.

## Variables to edit from the dashboard

The same for a simple move and an advanced one (the examples are advanced moves; a simple move sets the same class
attributes and reads `self.options`, `self.slider`, `self.pressed` in its `step(obs)`). A move chooses the variables it exposes (as RhIO's parameters): they get an editor in the dashboard (the move's ⚙).

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

A move can also be driven while it runs, from the dashboard's Moves card: sliders (shown while the move runs), and a
keyboard zone (click it, then the keys you press go to the robot; click elsewhere and they are released).

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

Variables (⚙) or sliders? A variable is a setting: it keeps its value from one launch to the next, can be saved on
the robot, and is edited in the ⚙ panel, even while the move is off. A slider is for driving: it shows only while the
move runs, has a min and a max, starts again from its start value at each launch, and is never saved.

## Simple or advanced?

| | Simple move | Advanced move (`Move`) |
|---|---|---|
| Written as | `step(obs)` returns the 19 targets (or None) | `on_start` / `step(obs, command)` / `on_stop` fill `command.target_angles` |
| What it reads | the simulator's observation (numpy, order `JOINTS`) | `obs.robot_state` by joint name, `obs.user_input` |
| Runs in the fast simulator (`run_move`) | yes, the same file | no (the robot's program only: the robot, `make sim`) |
| Starts | where the robot is | `power_up`: the neutral pose first by default |
| Servos' gain | `kp_fw`, set for it | its own (`controller.sync_write_kp`) |
| Ends | when it is stopped | it may end by itself |
| `variants` | optional (both) | required |
| Options, sliders, keys, prints, dashboard | the same | the same |

Write a simple move unless it needs what only an advanced one has: developed and tried in the simulator, then
`make sim WALL=N2`, then the robot, with no change.
