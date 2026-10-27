# humanoid_dashboard

A live dashboard for a humanoid robot, as light as possible on the robot: the robot's control loop sends, once per
tick, what it already read (motors, IMU, timing) in one UDP packet, and runs the few commands the page sends (reboot a
motor, torque on/off). Everything else runs on the PC it is connected to: the robot model's forward kinematics
(MuJoCo), the 3D view (three.js, in the browser), the plots, the recordings.

![parts](docs/architecture.svg)

## On the robot: `humanoid_dashboard.link` (standard library only)

```python
from humanoid_dashboard.link import Link

link = Link("Microban", fields={"q": joints, "q_target": joints, "current": joints, "imu_quat": ["w", "x", "y", "z"]},
            meta={"motor_ids": {...}, "limits": {"current": 1.75, "temperature": 70}, "commands": ["reboot", "torque"]})

# once per tick, after the motors were read and commanded:
link.publish(q=positions, q_target=targets, current=currents, imu_quat=quat)
for cmd in link.commands():                     # {"name": "reboot", "args": {"joint": "left_knee"}}
    ...                                         # run it between two bus transactions of the loop
    link.ack(cmd, ok=True, text="rebooted, torque off")
link.event("overcurrent safety: torque off", level="error")
```

Nothing is sent while no PC listens (a PC subscribes for 3 s with every hello it sends, once a second); `publish` and
`commands` never block. A frame is a 20-byte header and one float32 per value (NaN when not given): ~1 kB at most for
a 20-motor robot, ~50 kB/s at 50 Hz.

### Fields the page knows

| field | labels | shown as |
|---|---|---|
| `q`, `q_target` | joint names | angle and its error to the target (rad); `q` also drives the 3D model |
| `dq` | joint names | (recorded) |
| `current` | joint names | bar against `meta.limits.current` (A); their sum is plotted |
| `temperature`, `voltage` | joint names | °C (warning 15 °C, alarm 5 °C below `meta.limits.temperature`), V |
| `hw_error` | joint names | the bits named by `meta.hw_error_bits`, minus `meta.hw_error_ignore` |
| `torque` | joint names | 1 / 0; "torque off" and the torque button |
| `imu_quat` | w x y z | trunk orientation in the world (3D view, roll / pitch plot) |
| any one-value field | its name | in the header (e.g. `tick_ms`) |

Other fields are recorded. Joint labels are matched to the model's joints by name.

### Commands the page sends

`reboot {joint}` (shown on a motor in error) and `torque {joint, on}`, each with a confirmation click; the robot answers
each with `ack` (shown in Events) and decides what is safe. List the ones it accepts in `meta.commands`.

## On the PC

```bash
PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app --robot ROBOT_HOST --model path/to/robot.xml
# Microban: make dashboard HOST=ROBOT_HOST                     # opens http://127.0.0.1:8780
```

The model is a MuJoCo XML or a URDF. The page: the robot in 3D (a motor in error glows red, a hot or limp one orange; click a part to select its motor),
the motor table (angle, error to target, current, temperature, state, Reboot / Torque buttons), plots of the last 10 s
(total current, the selected motor's angle and target, trunk roll and pitch), the robot's events, and **Record**
(a `recordings/ROBOT_DATE.npz` with one array per field and the robot's time).

Options: `--port` (link port, 7350), `--http` (page port, 8780), `--visual-groups` (geom groups to draw; default: the
geoms that do not collide), `--recordings`, `--title`, `--no-browser`.

Without a robot:

```bash
PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.fake_robot --model path/to/robot.xml   # overheats a motor after 15 s
PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app --robot 127.0.0.1 --model path/to/robot.xml
```
