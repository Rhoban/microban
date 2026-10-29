# Your own controller

A controller is a file with a `class Controller`, written in the simulator's format: the same file runs in Rhoban's
robot simulator ([microban_sim](https://github.com/Rhoban/microban_sim), or the hackathon's climbing simulator built on
it, [rock-climbing-robots/simulator](https://github.com/rock-climbing-robots/simulator): `run_controller(controller,
sim, seconds)`, as fast as it computes), in the robot's program on the simulated robot, and on the robot:

```bash
make run HOST=radxa@<robot> CONTROLLER=path/to/my_controller.py   # the robot; keyboard [c] / gamepad [Y]: start / stop
make sim WALL=N2 CONTROLLER=path/to/my_controller.py          # the robot's program on the simulated wall ([c])
```

The file defines `class Controller` with `step(obs) -> targets` (the 19 joint targets, rad, in the order of
`microban_model.JOINTS`, or None to keep the last ones; every 20 ms), and optionally `reset(obs)` (when it starts) and
`kp_fw` (the servos' gain while it runs, 125 by default). `obs` is the simulator's observation, built from what the
robot measures: `q`, `dq`, `gyro`, `accel` (m/s^2), `gravity` (unit vector) in the trunk frame, `quat`, `current`,
`time` (`src/moves/controller.py`). A file it needs (a network) goes next to it on the robot by hand, or is loaded from
a path the robot has. The simulator's `examples/controller.py` has the shape.

It starts like any move: the torque goes on where the robot is (no move to the neutral pose first: it may start
hanging on the wall), em and init stop it, the dashboard shows it. It is made for the climbing robot.

## Controller or move?

Both read what the robot measures and give the 19 servos their targets every 20 ms.

| | Controller | Move ([moves.md](moves.md)) |
|---|---|---|
| Written for | the simulator (numpy arrays in the order `JOINTS`) | the robot's program (joint name -> angle) |
| Runs in the fast simulation (Python, planning, learning) | yes | no |
| Runs in `make sim` and on the robot | yes, as the move `controller` | yes |
| Dashboard | Start / Stop | Start / Stop, its variables, sliders and keys |

The climbing itself is best a Controller: one file, developed and trained in the simulator, then tried in the
robot's program on the simulated wall, then run on the robot. Moves are for the rest: gestures, demonstrations,
tools driven from the dashboard.
