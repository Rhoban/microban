# humanoid_dashboard

A live dashboard for a humanoid robot, as light as possible on the robot: the robot's control loop sends, once per
tick, what it already read (motors, IMU, timing) in one UDP packet, and runs the few commands the page sends (reboot a
motor, torque on/off). Everything else runs on the PC it is connected to: the robot model's forward kinematics
(MuJoCo), the 3D view (three.js, in the browser), the plots, the recordings.

```
robot: its control loop + link.py  ──UDP 7350──►  PC: app.py (MuJoCo kinematics)  ──WebSocket──►  browser (three.js)
                                   ◄── commands ──                                 ◄── clicks ──
```

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

Every `publish()` sends a frame (Microban: 50 Hz, ~50 kB/s); `Link(..., max_hz=...)` caps the rate if needed. Nothing is sent while no PC listens (a PC subscribes for 3 s with every hello it sends, once a second); `publish` and
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
| any one-value field | its name | in the header: `meta.scalars[name]` = `{label, unit}`, or `{flag: [off text, on text]}` for a 0 / 1 |

Other fields are recorded. Joint labels are matched to the model's joints by name.

### Commands the page sends

`reboot {joint}` (shown on a motor in error) and `torque {joint, on}`, each with a confirmation click, and two
whole-robot buttons in the header: `em` (emergency: torque off on every motor, no confirmation) and `init` (every motor
to its zero, confirmed). With the robot's moves listed in `meta.moves`: `move_start {move}` and `move_stop {move}` (a
start is confirmed), `move_option {move, option, value}` (the ⚙ editor) and `save_options`; a move's live controls
(`meta.moves[i].sliders` {name: [min, max, start]}, `keys` a text), unanswered: `slider {move, slider, value}` while
dragged (the field `sliders`, labels `move.slider`, gives the robot's values) and `keys {held: [...]}` at each key and
every 0.2 s while keys are held in the keyboard zone. A robot with several versions says its own (`meta.variant`,
among `meta.variants`; each move's `variants` and `available`): the page shows the model of that name (`--model
NAME=...`), lists the moves available, and `variant {variant}` (its header menu, after a confirmation) changes it on the
robot. The **⟳ Deploy code**
button runs a command on the PC (`--deploy`), not on the robot. The robot answers each with `ack` (shown in Events) and decides what is safe; it lists the
ones it accepts in `meta.commands`, and the page shows only those.

## On the PC

```bash
PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app --robot ROBOT_HOST --model path/to/robot.xml
PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app --model Classic=robot.xml --model Climber=climb.xml
# Microban: make dashboard HOST=ROBOT_HOST                     # opens http://127.0.0.1:8780
```

`--robot` is optional: the robot's address is chosen in the page too (the button next to the link state), and can be
changed there at any time; give it a name to keep it in `~/.config/humanoid_dashboard/robots.json`, listed there next
time. The PC asks the robot (UDP `hello` once a second to its port 7350) and the robot answers to that PC only while
it asks: no SSH, nothing to start on the robot beyond its program.

The model is a MuJoCo XML or a URDF. The page: the robot in 3D (a motor in error glows red, a hot or limp one orange; click a part to select its motor),
the motor table (angle, error to target, current, temperature, state, Reboot / Torque buttons), plots of the last 10 s
(total current, the selected motor's angle and target, trunk roll and pitch), the robot's events, and **Record**
(a `recordings/ROBOT_DATE.npz` with one array per field and the robot's time).
`--deploy CMD` adds a **⟳ Deploy code** button that runs CMD (`{host}`: the robot shown) from the current folder,
its output in the events (Microban: `make deploy HOST=radxa@{host}`). **Replay** plays a recording back in the same page (3D, table, moves' states, plots): play / pause (space), speed
×0.1 to ×2, one frame back or forward (← →; with shift: one second), the slider to jump anywhere, **Live** to come
back. The live robot keeps running meanwhile (its commands are hidden in the replay, except em in the header).

Options: `--port` (link port, 7350), `--http` (page port, 8780), `--visual-groups` (geom groups to draw; default: the
geoms that do not collide), `--motor-mesh` (name part of the servo meshes, lit on a motor error; `xl330`),
`--deploy CMD`, `--recordings`, `--title`, `--no-browser`. Only the page served here may use the server (its Host and
Origin are checked): no other web page can drive the robot through it. A recording in progress is saved when the robot
changes, or restarts with other fields (a new one goes on).

Without a robot:

```bash
PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.fake_robot --model path/to/robot.xml   # overheats a motor after 15 s
PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.app --robot 127.0.0.1 --model path/to/robot.xml
```
