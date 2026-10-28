# Using Microban

This guide covers day-to-day operation once the robot has been set up (see the
[Deployment Guide](deployment.md)). You drive the robot from your computer with the
`Makefile`, which talks to the robot's board (Raspberry Pi on v1, Radxa ROCK 3C on v2) over SSH. You can use the
keyboard or a Bluetooth gamepad to control it, and optionally run it headless ([gamepad.md](gamepad.md)) or as a
service started at boot, driven from the live dashboard ([dashboard.md](dashboard.md)).

> [!IMPORTANT]
> Always run `make shutdown` before cutting power to the robot. This is **not**
> automatic — powering off the Pi without a clean shutdown can corrupt the SD card.
> Wait 10-15 s after the command before flipping the power switch off, to give the
> Pi time to actually halt.

## Makefile commands

Run these from the repository root on your computer. They target the host `microban`
by default (an SSH alias, see the [Deployment Guide](deployment.md)). A robot flashed from the SD card image
([sd_image.md](sd_image.md)) is `HOST=radxa@microban-XXXX.local`, or an SSH alias with `User radxa`. `make dashboard`
takes the bare name instead (`HOST=microban-XXXX.local`): the page adds the user itself (`ROBOT_USER`, `radxa`).

| Command | What it does |
| :--- | :--- |
| `make run` | Sync the code and start the control loop on the robot (50 Hz). Stays attached to your terminal for live control (it stops the robot service for the session). `CONTROLLER=path.py`: your own controller ([controller.md](controller.md)). |
| `make deploy` | Sync the code and restart the robot service: your moves run, the dashboard shows them by itself ([moves.md](moves.md)). |
| `make stop` | Stop the control loop and disable torque on all motors. The robot service stays stopped (until `make robot-service-start` or a reboot). |
| `make shutdown` | Power off the Pi cleanly. |
| `make setup` | Sync the code and (re)install dependencies on the robot (`uv sync`, from `pyproject.toml`). Run after changing dependencies. |
| `make sync` | Sync your local copy to the robot without touching dependencies. |
| `make imu` | Stream the robot's IMU/gyro readings to your terminal. |
| `make voltage` | Read the voltage of all motors. |
| `make voltage ID=<id>` | Read the voltage of motor `<id>`. |
| `make sim` | Run the MuJoCo simulation locally (no robot needed). `CONTROLLER=path.py` as `make run`. |
| `make viewer` | Open the PlaCo / MeshCat kinematic viewer locally (no physics, no robot needed). |
| `make dashboard` | The live dashboard on this PC ([dashboard.md](dashboard.md)); `CLIMB=1` for the climbing forearms and feet. |
| `make robot-service-enable` / `-disable` | Install (or remove) the robot service: the control loop starts at every boot. |
| `make robot-service-start` / `-stop` / `-logs` | Start, stop the robot service, or follow its output. |

## Running the robot

1. Place the robot on a stable surface, or hold it securely. The torque is off until a move is launched: the
   robot then ramps to its neutral pose in 2 s with the torque on, and the move starts. When no move runs, the
   torque goes off again.
2. `make run` — the control loop starts at 50 Hz and stays attached to your terminal. Some latency is expected due to the SSH connection.
   With the robot service (`make robot-service-enable`, [dashboard.md](dashboard.md)) the loop already runs from boot:
   start moves from the dashboard or a gamepad instead, or `make run` for the keyboard (it stops the service).
3. Toggle moves and drive the robot (see below).
4. `make stop` (or press `q`) to stop; `make shutdown` to power off.

## Controlling with the keyboard

| Key | Action |
| :--- | :--- |
| `v` | toggle the **walk** move |
| `h` | toggle the **head** move |
| `s` | toggle the **squat** move |
| `c` | toggle your own **controller** (`make run CONTROLLER=...`) |
| arrows | `vx` (up/down), `vtheta` (left/right) |
| `x` | reset velocity to zero |
| `i` | toggle the IMU/gyro display |
| `q` | stop the control loop |

## Controlling with a gamepad

A Bluetooth Xbox controller can be used instead of the keyboard. The detailed explanation of the gamepad usage is in [Gamepad Guide](gamepad.md). 

Using a gamepad allows to drive the robot through two different modes: with a terminal (SSH) or fully headless (no SSH, no terminal). The second mode is particularly useful for demonstration purposes, due to the fact that it allows to drive the robot without any computer connected to it.

## Moves

Moves are toggled independently (keys, gamepad, or the dashboard's Moves list: [dashboard.md](dashboard.md)) and run
on top of the neutral pose:

- **Walk** (`v` / gamepad **A**) — a reinforcement-learning policy. Once active, the
  velocity command drives it: `vx` (forward/back), `vy` (lateral), `vtheta` (turn),
  set from the arrow keys or the gamepad sticks.
- **Head** (`h`) — oscillates the head.
- **Squat** (`s`) — squat motion computed with inverse kinematics.
- **Controller** (`c` / gamepad **Y**) — your own controller file (`make run CONTROLLER=...`,
  [controller.md](controller.md)).

### Velocity command

Every input source emits a **normalized** command in `[-1, 1]` per axis; the scheduler
maps it to physical limits with `scale_velocity()`, so the behavior is identical for
keyboard, gamepad and sim. Defaults (in [constants.py](../src/constants.py)):

| Axis | Max |
| :--- | :--- |
| `vx` (forward) | +0.7 |
| `vx` (backward) | -0.5 |
| `vy` (lateral) | ±0.3 |
| `vtheta` (turning in place, `vx = vy = 0`) | ±3.0 |
| `vtheta` (while translating) | ±1.5 |

## Developing: adding your own moves

The full guide, with an example: [moves.md](moves.md).

Each behavior is a subclass of `Move` ([src/moves/move.py](../src/moves/move.py)) with
a simple lifecycle driven by the scheduler:

- `preload()` — optional, called once before the loop starts (load heavy resources).
- `on_start(obs, command)` — called each tick while *starting*; set
  `self.state = MoveState.ACTIVE` when ready (e.g. after ramping in).
- `step(obs, command)` — called each tick while *active*; write your target joint
  angles into `command.target_angles`.
- `on_stop(obs, command)` — called each tick while *stopping*; set
  `self.state = MoveState.INACTIVE` when done (e.g. after ramping back to neutral).

To add a move:

1. Create a new file in [src/moves/](../src/moves/) with a class subclassing `Move`.
   Use [rotate_head.py](../src/moves/rotate_head.py) (a simple oscillation) or
   [squat.py](../src/moves/squat.py) (inverse kinematics with placo) as a template.
2. Nothing to register: every `Move` class of `src/moves/` is found when the program starts ([moves.md](moves.md)).
   A key in `MOVE_KEYS` (keyboard) or a button in `GAMEPAD_BUTTON_MOVES` (gamepad), in
   [src/main.py](../src/main.py), is optional.
3. In `step()`, read the robot state from `obs.robot_state` (motor positions and
   velocities, IMU gyro, projected gravity) and write your targets into
   `command.target_angles`.

### Training your own walk (or other RL) policies

The walk move runs an ONNX policy trained in simulation. 
You can train your own walking — or other learned skills — and drop the resulting `.onnx` file into [src/agents/](../src/agents/) to use it on the robot. Check the repository [MarcDcls/mjlab_microban](https://github.com/MarcDcls/mjlab_microban) for the training pipeline. 

If you achieve some interesting results, don't hesitate to make a pull request to the repository as it is also a community-driven project!