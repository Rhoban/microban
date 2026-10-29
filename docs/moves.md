# Moves: write your own

A move is a Python class with a `step(obs)` method: every 20 ms it gets what the robot measures and returns the
targets of its joints. Put it in a file of `src/moves/` and the robot's program finds it by itself: it appears in the
dashboard's Moves list with Start / Stop. The same file runs in the simulators, on the robot's program in simulation
and on the real robot.

## The smallest move

```python
# src/moves/wave.py
import math


class WaveMove:
    """Wave the right arm."""

    def start(self, obs):
        self.t0 = obs["time"]

    def step(self, obs):
        t = obs["time"] - self.t0
        return {"right_shoulder_roll": -0.8 + 0.4 * math.sin(3 * t)}
```

That is all: no base class, nothing to register. Its name is the class name without "Move", in snake_case:
`WaveMove` -> `wave` (`RaiseArmMove` -> `raise_arm`; or set `name = "..."` in the class). Its docstring's first line
is its description in the dashboard. The joints it does not return keep their last target.
On the wall (the climber), this one lets go of the right hand's hold: add `variants = ("classic",)` to keep it for
the walking robot.

## Try it

```bash
make sim                       # the robot's program on the simulated classic robot (WALL=N2: the climber on the wall)
make dashboard HOST=127.0.0.1  # in another terminal: Moves -> wave -> Start / Stop
```

Then on the robot:

```bash
make deploy HOST=radxa@microban-1a2b.local    # sends your code and restarts the robot's program
```

Before sending, `make deploy` saves the robot's code as it was (`~/microban_backups/` on the robot, the last 5
kept): `make restore HOST=...` goes back to it if the new code does not do what you want.

Or, without typing anything: the **⟳ Deploy code** button of the dashboard runs the same command for the robot it
shows (a first click asks to confirm), its output in the page's Events. The program reads its moves when it starts:
after any change to a move's code, deploy again (only the options, below, change live without a restart). The
dashboard shows the new Moves list by itself a few seconds later. The torque goes off during the restart: hold the
robot or let it sit, never on the wall. A new Python dependency in `pyproject.toml` needs `make setup` first.

A file kept outside `src/moves/` runs too, for one session: `make run MOVES=path/to/my_moves.py` (on the robot, from
a terminal) or `make sim MOVES=path/to/my_moves.py`. `make run` sends that one file only: a move that needs other
files (a helper module, a network) belongs in `src/moves/`. A move of that file named as one of `src/moves/` replaces
it for the session (said in the Events).

## What a move gets: `obs`

`obs` is a dict, the same as the simulator's observation:

| Key | What |
|---|---|
| `q`, `dq` | the 19 joints' angles (rad) and velocities (rad/s), in the order `microban_model.JOINTS`; every zero at the motor's zero ([model.md](model.md)) |
| `gyro` | angular velocity (rad/s), trunk frame |
| `accel` | acceleration (m/s^2), trunk frame |
| `gravity` | the gravity's direction, unit vector in the trunk frame (`[0, 0, -1]` upright) |
| `quat` | the trunk's orientation, w x y z |
| `current` | the motors' currents (A) |
| `time` | seconds, steady (use differences: `obs["time"] - self.t0`) |

A sensor that gave nothing this tick reads NaN (`np.isnan(obs["gravity"]).any()`).

## What it returns

* A dict `{joint: angle}` (rad): only these joints; the others keep their last target (another move's, or the pose
  the robot had when the torque went on). Two moves can run together this way (the head and the walk); when both
  drive a joint, the later one in the Moves list wins.
* Or 19 angles (a list or a numpy array) in the order `JOINTS`: the whole pose.
* Or `None`: the move is over. It stops by itself (as if Stop was clicked) and stays off until asked anew (Start, or
  its key / button pressed again).

```python
from microban_model import JOINTS            # the joint names, in the order of q, dq and a 19-angle return

HEAD = JOINTS.index("head")


class HoldMove:
    def start(self, obs):
        self.pose = obs["q"].copy()          # the pose it starts in

    def step(self, obs):
        target = self.pose.copy()
        target[HEAD] = 0.3
        return target                        # 19 angles
```

## Start, step, stop

| Method | When |
|---|---|
| `start(self, obs)` | once, when it is launched (optional): reset what `step` uses |
| `step(self, obs)` | every 20 ms while it runs: returns the targets |
| `stopping(self, obs)` | after Stop (or after `step` returned None), every 20 ms until it returns None (optional): a smooth stop |

Without `stopping`, the move ends at once. `em` and `init` (dashboard) stop every move at once, without `stopping`.

A move that starts and stops smoothly, the head going from where it is to its target in half a second:

```python
from microban_model import JOINTS

HEAD = JOINTS.index("head")
LERP_S = 0.5


def lerp(a, b, t):
    """From a to b in LERP_S, t seconds after it began."""
    s = min(t / LERP_S, 1.0)
    return a + (b - a) * s


class NodMove:
    """Look down, then back up when stopped."""

    def start(self, obs):
        self.t0, self.from_angle = obs["time"], obs["q"][HEAD]
        self.stop_t0 = None

    def step(self, obs):
        return {"head": lerp(self.from_angle, 0.4, obs["time"] - self.t0)}

    def stopping(self, obs):
        if self.stop_t0 is None:                          # the first call after Stop
            self.stop_t0, self.from_angle = obs["time"], obs["q"][HEAD]
        t = obs["time"] - self.stop_t0
        return {"head": lerp(self.from_angle, 0.0, t)} if t < LERP_S else None
```

`src/moves/head.py` and `src/moves/squat.py` are written this way.

## Settings of the class

All optional:

| Attribute | Default | What |
|---|---|---|
| `description` | the docstring's first line | one line in the dashboard's Moves list |
| `name` | the class name without "Move", snake_case | its name in the dashboard and for the keys |
| `variants` | both | the robot versions it is for: `("classic",)` or `("climber",)` (below) |
| `start_pose` | `"current"` | when the torque is off at its launch: `"current"` turns it on where the robot is; `"neutral"` first brings the robot to the neutral standing pose in 2 s |
| `kp` | the robot's gain (400) | the servos' gain while it runs (the walk: 125, the gain its policy was trained with) |
| `options`, `option_docs` | none | variables edited live in the dashboard (below) |
| `sliders` | none | sliders shown while it runs (below) |
| `keys` | none | the keys it reads, shown in the dashboard's keyboard zone (below) |

**Which robot it is for.** `"classic"` is the walking hands and feet, `"climber"` the climbing forearms and feet
(plain strings: the file runs in the simulator too). The robot knows its version (the dashboard's **robot version** menu
changes it, saved on the robot in `robot_variant.txt`; classic until set; `make sim` is classic, `make sim WALL=N2`
climber): it runs a move only on the versions it is made for (the keyboard and the gamepad too), and the dashboard
lists only those. The walk, trained with the walking feet, is `("classic",)`.

**Where it starts.** The torque is off while no move runs. The first move launched turns it on: where the robot is
(`start_pose = "current"`, the default: a move may start with the robot hanging on the wall), or after a 2 s ramp to
the neutral standing pose (`"neutral"`: the walk and the squat; on the wall the robot would let go). When every move
has stopped, the torque goes off again.

**The servos' gain.** While moves with a `kp` run, the servos use it (the last one in the Moves list when several
set one); otherwise the robot's gain, 400.

## Variables to edit from the dashboard

A move chooses the variables it exposes (as RhIO's parameters): they get an editor in the dashboard (the move's ⚙).

```python
class WaveMove:
    options = {"amplitude": 0.4, "both_arms": False}     # the exposed variables: int / float / bool
    option_docs = {"amplitude": "arm swing (rad)", "both_arms": "wave with both arms"}

    def step(self, obs):
        amplitude = self.options["amplitude"]            # (a sketch: use it to compute the targets)
        ...

    def on_option(self, name, value):                    # optional: called when one changed (already set)
        print(f"{name} = {value}")
```

The move reads `self.options[...]` where it needs them; a change applies at once, the robot running (no restart).
**Save on robot** writes every move's variables to `move_options.json` (repo root on the robot), read again at the
next start over the defaults written in the code.

## Drive it live: sliders and keys

A move can also be driven while it runs, from the dashboard's Moves card: sliders (shown while the move runs), and a
keyboard zone (click it, then the keys you press go to the robot; click elsewhere and they are released).

```python
KEY_SPEED = 1.0                                         # rad/s while an arrow is held


class LookMove:                                         # abridged: src/moves/look.py is the full one
    sliders = {"head": (-0.8, 0.8, 0.0)}                # name -> (min, max, start value)
    keys = "← →: turn the head"                         # shown in the keyboard zone (the zone appears with it)

    def step(self, obs):
        if "ArrowLeft" in self.pressed:                 # the keys held now
            self.slider["head"] += KEY_SPEED * 0.02
        return {"head": self.slider["head"]}

    def on_key(self, key, down):                        # optional: once per press (down=True) and release
        if key == "space" and down:
            print("space!")
```

* `self.slider[name]`: the slider's value. It goes back to its start value at each launch of the move (the robot
  never starts with a speed left high); the move may change it too, and the page follows.
* `self.pressed`: the keys held. Their names are the browser's: `"a"` to `"z"` (lower case), `"0"` to `"9"`,
  `"space"`, `"ArrowUp"`, `"ArrowDown"`, `"ArrowLeft"`, `"ArrowRight"`, `"Enter"`, `"Shift"`...
* `on_key(key, down)` is called only while the move runs or stops (its `stopping`: the keyboard zone stays shown). If the page goes quiet (closed, network lost), the held keys
  are released after 0.6 s.

Variables (⚙) or sliders? A variable is a setting: it keeps its value from one launch to the next, can be saved on
the robot, and is edited in the ⚙ panel, even while the move is off. A slider is for driving: it shows only while the
move runs, has a min and a max, starts again from its start value at each launch, and is never saved.

**The velocity asked.** `self.velocity` is `{"vx": m/s, "vy": m/s, "vtheta": rad/s}`, from the gamepad's sticks or the
keyboard's arrows (`make run`), within the limits of [usage.md](usage.md#velocity-command); zero otherwise. The walk
reads it (and its own dashboard arrows, `src/moves/walk.py`).

A key or a gamepad button for a move, optional, in `src/constants.py` (a key toggles it in `make run`'s terminal and in
`make sim`'s viewer window):

```python
MOVE_KEYS = {..., "w": "wave"}
GAMEPAD_BUTTON_MOVES = {..., "LB": "wave"}
```

## The servos one by one: `self.robot`

Most moves need only `obs` and their targets. For more, every move has `self.robot` (set by the program, from
`start` on):

| | |
|---|---|
| `self.robot.set_torque(on, joints=None)` | torque off on these joints (names, or all): they go limp at once; back on: after this tick's targets, held where they are (no jump) |
| `self.robot.set_kp(kp, joints=None)` | the servos' gain (0 to 1000), of these joints or all, over the moves' `kp` (in the class: the whole move's), written after the tick |
| `self.robot.variant` | the robot's version, `"classic"` or `"climber"` (None in `run_move`) |
| `self.robot.state` | this tick's raw measurements (`observer.RobotState`: the IMU in its chip's frame, the motors' voltages, currents by joint name) |

When the move stops (Stop, over by itself, an error, em / init), the joints it turned off get their torque back (if
the robot is powered) and its gains go: the joints get the running moves' gains again (their `kp`, their `set_kp`),
or the robot's. `self.robot` is the program's: name your own objects differently (`self.model`, not `self.robot`).

```python
from microban_model import JOINTS

ELBOW = JOINTS.index("left_elbow")


class FeelMove:
    """Let the left elbow go limp for one second: move it by hand, read where it is."""

    def start(self, obs):
        self.t0 = obs["time"]
        self.robot.set_torque(False, ["left_elbow"])

    def step(self, obs):
        if obs["time"] - self.t0 > 1.0:
            self.robot.set_torque(True, ["left_elbow"])
            return None                                       # over
        self.angle = obs["q"][ELBOW]                          # where the hand put it
        return {}                                             # no target to change
```

In the simulators (`run_move`, and `make sim`), `self.robot` has the same `set_torque` and `set_kp`; the simulated
servos share one gain, the one most joints have (per-joint gains: on the robot only, a message says so); `state` is
None in `run_move`.

## Messages and errors

* `print()` in a move goes to the dashboard's Events (`wave: text`, at most 10 lines a second per move; the rest is
  counted there) and to the robot's log (`make robot-service-logs`, or the terminal with `make run`).
* A file that does not load (a Python error), a move that cannot be built (an error in `__init__`) or whose
  `variants` is wrong is skipped, and the robot starts anyway: the reason, with the line of your file, shows in the
  dashboard's Events (and in `make robot-service-logs`).
* An error in `start`, `step`, `stopping` or `on_key` stops that move at once (the others go on; its joints keep their
  last targets, and the torque goes off if no move runs any more): the error, with the line of your file, shows in
  the Events. It stays off until asked anew. An error in `on_option` is shown too (and stops the move if it runs).
  Try the move in simulation first.

## The same file in the simulator

The hackathon's simulator ([rock-climbing-robots/simulator](https://github.com/rock-climbing-robots/simulator), built
on Rhoban's [microban_sim](https://github.com/Rhoban/microban_sim)) runs the same class as fast as it computes, for
planning or learning:

```python
from climbing_sim import ClimbingSim, load_moves, run_move

sim = ClimbingSim("N2")
sim.reset_hanging()
moves = load_moves("../microban/src/moves/my_move.py")     # {name: move}
run_move(moves["my"], sim, seconds=30)
```

There, nobody edits the options and sliders: they keep their defaults (the sliders back to their start values at each
`run_move`), `self.pressed` is empty and `self.velocity` zero. `run_move` runs `step` until it returns None or the time
is over, then `stopping`; `kp` while it runs. It starts where the simulated robot is: `start_pose` is for the robot's
program only.

A move should therefore import only what both have: `numpy`, `microban_model` (`JOINTS`), and its own files, by name
(`import my_helper` for `src/moves/my_helper.py`: the move's folder is on the path on the robot and in `load_moves`; a
helper file with no move class in it is not a move). A file it needs (a network, a table) goes next to it in the
repository (`make deploy` sends it), loaded from the move's folder:

```python
from pathlib import Path

NET = Path(__file__).parent / "my_policy.onnx"
```

## Good practice

* Keep `step` fast: well under 20 ms on the robot's small computer, every tick. Load what is heavy (a network, a
  model) in `__init__`, which runs once when the program starts.
* Never block: no `time.sleep`, no waiting on input in `step`. Measure time with `obs["time"]`.
* Start and stop smoothly: go from where the joints are (`obs["q"]` in `start`) to where you want them over a fraction
  of a second; a `stopping` that brings them back.
* Return `None` when the move is done rather than holding forever.
* Check what you read: a NaN sensor, a fall (`obs["gravity"][2] > -0.5`): then hold (`return obs["q"]`) rather than
  push on.
* Try it in simulation first (`make sim`, `make sim WALL=N2`), then on the robot held in the hand or on the floor.
