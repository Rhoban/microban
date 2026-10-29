# Simulation

Your code runs in simulation as on the robot: the same program (`src/main.py`'s scheduler), your moves of
`src/moves/` and the dashboard; the keys are typed in the viewer's window (no gamepad in simulation). Only the motors and the sensors are simulated, by Rhoban's
robot simulator, [microban_sim](https://github.com/Rhoban/microban_sim) (the servos simulated by BAM, the sensors with
the robot's delays).

| | |
|---|---|
| `make sim` | The classic robot on the floor; `VARIANT=climber`: the climbing one. |
| `make sim WALL=N2` | The climbing robot on the hackathon's wall: `N1`, `N2`, `N3` or a wall JSON file (from the simulator's wall editor). It starts hanging on the wall's start holds; `START=floor`: standing in front of the wall. |
| `MOVES=my_moves.py` | Also the moves of a file kept outside `src/moves/` ([moves.md](moves.md)). |

In the viewer (click it first): the keys listed in the terminal start / stop the program's moves made for this robot,
[r] puts the robot back at the start, [q] (or Ctrl+C in the terminal) quits. Your own moves have no key: start them
from the dashboard, `make dashboard HOST=127.0.0.1` in another terminal (or give them one in `MOVE_KEYS`,
`src/constants.py`). On macOS, MuJoCo's viewer needs `mjpython`: `make sim PYTHON=mjpython WALL=N2`.

As on the real robot:

* the robot's program starts with the torque off: the robot is held where it starts until a move is launched (the
  torque goes on), as someone holds the real robot;
* a move turns the torque on where the robot is (`start_pose = "current"`, the default), so it may start hanging on
  the wall; one with `start_pose = "neutral"` (the walk, the squat) first brings the robot to the neutral standing
  pose in 2 s: on the wall, the robot then lets go;
* the moves are those made for the robot's version ([moves.md](moves.md)): the wall's robot is a climber.

`src/sim/sim_controller.py` connects the robot's program to the simulator: it gives the program what the real robot
gives it (joint angles and velocities, motor currents, the IMU in its chip's frame, with the robot's delays) and
sends the joint targets, the servos' gain and torque to the simulation.

## Fast simulation, without the robot's program

For planning, learning or evaluating many runs, use the simulator directly in Python: `sim.step(target)` as fast as
it computes, no real time (see [microban_sim](https://github.com/Rhoban/microban_sim)). A move written there
([moves.md](moves.md#the-same-file-in-the-simulator), `run_move`) runs unchanged here and on the robot.

## The wall: the hackathon's simulator

The wall, its holds, the cameras and their tools come from the hackathon's simulator,
[rock-climbing-robots/simulator](https://github.com/rock-climbing-robots/simulator) (the `climbing_sim` package, built
on microban_sim). Clone it **next to this folder**; `make sim WALL=...` uses it from there, so what you change in it
applies at once:

```bash
hackathon/
  microban/       # this repository: the robot's program, your moves (make sim, make deploy)
  simulator/      # git clone https://github.com/rock-climbing-robots/simulator
```

(Elsewhere: `make sim WALL=N2 SIMULATOR=path/to/simulator`.) The simulator also works on its own, for your planning,
learning and camera scripts: see its README.
