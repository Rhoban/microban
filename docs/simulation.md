# Simulation

Your code runs in simulation as on the robot: the same program (`src/main.py`'s scheduler), your moves of
`src/moves/`, the keyboard, the gamepad and the dashboard. Only the motors and the IMU are simulated.

| | |
|---|---|
| `make sim` | The walking robot on the floor (MuJoCo, `src/sim/`). |
| `make sim WALL=N2` | The climbing robot on the hackathon's wall: `N1`, `N2`, `N3` or a wall JSON file (from the simulator's wall editor). It starts hanging on the wall's start holds; `START=floor`: standing in front of the wall. |
| `CONTROLLER=my_controller.py` | Your Controller as the move `controller` ([controller.md](controller.md)). |

In the viewer: [c] starts / stops the controller (and the other moves' keys, listed in the terminal), [r] puts the
robot back at the start, [q] quits. The dashboard works on it: `make dashboard HOST=127.0.0.1`.

## The wall: the hackathon's simulator

The wall, its holds and the climbing robot come from the hackathon's simulator,
[rock-climbing-robots/simulator](https://github.com/rock-climbing-robots/simulator) (the `climbing_sim` package). Clone
it **next to this folder**; `make sim WALL=...` uses it from there, so what you change in it applies at once:

```bash
hackathon/
  microban/       # this repository: the robot's program, your moves (make sim, make deploy)
  simulator/      # git clone https://github.com/rock-climbing-robots/simulator
```

(Elsewhere: `make sim WALL=N2 SIMULATOR=path/to/simulator`.) The simulator also works on its own, for your planning,
learning and camera scripts: see its README.

`src/sim/wall_controller.py` connects the two: it gives the robot's program what the real robot gives it (joint
angles and velocities, motor currents, the IMU, with the robot's sensor delays) and sends the joint targets, the
servos' gain and torque to `ClimbingSim`.

As on the real robot:

* the robot's program starts with the torque off: the robot is held where it starts until a move is launched (the
  torque goes on), as someone holds the real robot;
* a move launched with `power_up = "neutral"` (the default) first brings the robot to the neutral standing pose in
  2 s: on the wall, the robot then lets go. A move meant to start on the wall sets `power_up = "current"` (the
  Controller does);
* the moves made for the classic robot (the walk, the squat) are not offered: the wall's robot is a climber
  ([moves.md](moves.md)).
