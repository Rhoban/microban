# Your own controller

A controller written for the hackathon's simulator ([rock-climbing-robots/simulator](https://github.com/rock-climbing-robots/simulator):
`examples/controller.py`, `climbing_sim.run_controller`) runs unchanged on the robot:

```bash
make run HOST=radxa@<robot> CONTROLLER=path/to/my_controller.py   # the robot; keyboard [c] / gamepad [Y]: start / stop
make sim WALL=N2 CONTROLLER=path/to/my_controller.py          # the robot's program on the simulated wall ([c])
```

The file defines `class Controller` with `step(obs) -> targets` (the 19 joint targets, rad, in the order of
`microban_model.JOINTS`, or None to keep the last ones; every 20 ms), and optionally `reset(obs)` (when it starts) and
`kp_fw` (the servos' gain while it runs, 125 by default). `obs` is the simulator's observation, built from what the
robot measures: `q`, `dq`, `gyro`, `accel` (m/s^2), `gravity` (unit vector) in the trunk frame, `quat`, `current`,
`time` (`src/moves/controller.py`). A file it needs (a network) goes next to it on the robot by hand, or is loaded from
a path the robot has.

It starts like any move: the torque goes on where the robot is (no move to the neutral pose first: it may start
hanging on the wall), em and init stop it, the dashboard shows it.
