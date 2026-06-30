# Using Microban

This guide covers day-to-day operation once the robot has been set up (see the
[Deployment Guide](deployment.md)). You drive the robot from your computer with the
`Makefile`, which talks to the Pi over SSH.

> [!IMPORTANT]
> Always run `make shutdown` before cutting power to the robot. This is **not**
> automatic — powering off the Pi without a clean shutdown can corrupt the SD card.

## Makefile commands

Run these from the repository root on your computer. They target the host `microban`
by default; add `HOST=microban-ext` to operate over the secondary network (see the
[Deployment Guide](deployment.md)).

| Command | What it does |
| :--- | :--- |
| `make run` | Sync the code and start the control loop on the robot (50 Hz). Stays attached to your terminal for live control. |
| `make stop` | Stop the control loop and disable torque on all motors. |
| `make shutdown` | Power off the Pi cleanly. |
| `make setup` | Sync the code and (re)install dependencies on the robot (`uv sync --frozen`). Run after changing dependencies. |
| `make sync` | Sync your local copy to the robot without touching dependencies. |
| `make imu` | Stream the robot's IMU/gyro readings to your terminal. |
| `make voltage` | Read the voltage of all motors. |
| `make voltage ID=<id>` | Read the voltage of motor `<id>`. |
| `make sim` | Run the MuJoCo simulation locally (no robot needed). |
| `make viewer` | Open the MuJoCo viewer locally (no robot needed). |

## Running the robot

1. Place the robot on a stable surface, or hold it securely — on start it enables
   torque and ramps to its neutral pose.
2. `make run` — the control loop starts at 50 Hz and stays attached to your terminal. Some latency is expected due to the SSH connection.
3. Toggle moves and drive the robot (see below).
4. `make stop` (or press `q`) to stop; `make shutdown` to power off.

## Controlling with the keyboard

| Key | Action |
| :--- | :--- |
| `v` | toggle the **walk** move |
| `h` | toggle the **head** move |
| `s` | toggle the **squat** move |
| arrows | `vx` (up/down), `vtheta` (left/right) |
| `x` | reset velocity to zero |
| `i` | toggle the IMU/gyro display |
| `q` | stop the control loop |

## Controlling with a gamepad

A Bluetooth Xbox controller can be used instead of the keyboard: the left stick
drives, the right stick turns, and **A** toggles the walk. See the
[Gamepad guide](gamepad.md) for pairing and the full mapping. `main.py` uses the
gamepad automatically when one is connected, and falls back to the keyboard otherwise.

## Headless gamepad mode (no SSH)

An optional service lets you run the robot **without any terminal**: once the
controller is connected to the Pi, **hold START for 2 s** to start the control loop,
and press **B** to stop it. It coexists with `make run` (only one control loop runs at a
time).

Enable it (opt-in) from your computer:
```bash
make gamepad-headless-enable     # installs + starts the service on the Pi
make gamepad-headless-disable    # removes it
```

Behavior while a headless session runs:
- **Wi‑Fi is turned off** to free the 2.4 GHz antenna for Bluetooth (fewer controller
  dropouts), and restored when the session stops. It uses `rfkill` (a soft block), so a
  reboot always brings Wi‑Fi back.
- If the **controller disconnects**, the robot's velocity is zeroed so it stops moving
  (torque stays on, holding its pose). Reconnect and press **B** — or `make stop` once
  Wi‑Fi is back, or power off — to end the session.

`make stop` won't reach the robot while Wi‑Fi is off, so use **B** to stop a headless
session.

## Moves

Moves are toggled independently and run on top of the neutral pose:

- **Walk** (`v` / gamepad **A**) — a reinforcement-learning policy. Once active, the
  velocity command drives it: `vx` (forward/back), `vy` (lateral), `vtheta` (turn),
  set from the arrow keys or the gamepad sticks.
- **Head** (`h`) — oscillates the head.
- **Squat** (`s`) — squat motion computed with inverse kinematics.

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
2. Register it in [src/main.py](../src/main.py): add it to the `moves` dict passed to
   the `Scheduler`, and add a trigger — a key in `MOVE_KEYS` (keyboard) and/or a button
   in `GAMEPAD_BUTTON_MOVES` (gamepad).
3. In `step()`, read the robot state from `obs.robot_state` (motor positions and
   velocities, IMU gyro, projected gravity) and write your targets into
   `command.target_angles`.

### Training your own walk (or other RL) policies

The walk move runs an ONNX policy trained in simulation. 
You can train your own walking — or other learned skills — and drop the resulting `.onnx` file into [src/agents/](../src/agents/) to use it on the robot. Check the repository [MarcDcls/mjlab_microban](https://github.com/MarcDcls/mjlab_microban) for the training pipeline. 

If you achieve some interesting results, don't hesitate to make a pull request to the repository as it is also a community-driven project!