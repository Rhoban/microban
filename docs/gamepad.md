## Gamepad control (Xbox / Bluetooth)

The robot can be driven with a Bluetooth gamepad (Xbox or compatible). The gamepad
is paired with **the Pi** and read directly there via the Linux joystick API
(`/dev/input/js*`), in the same process as the control loop. This needs no extra
dependency and no compilation — events are parsed from raw bytes with `struct`.
`main.py` uses the gamepad automatically when one is connected and falls back to the
keyboard otherwise.

### Mapping

- **Left stick**: `vx` (up/down), `vy` (left/right)
- **Right stick** (left/right): `vtheta`
- **A**: toggle the `walk` move
- **B**: stop the scheduler (writes the stop flag)
- **View/Back** button: toggle the IMU/gyro display

Axis and button numbers vary between controllers (especially over Bluetooth) — if
something doesn't respond as expected, see [Remapping](#remapping-for-your-controller).

Every input source emits a **normalized** command in `[-1, 1]` per axis. The physical
limits are applied centrally by `scale_velocity()` (in the scheduler), so they are
identical for keyboard, gamepad and sim: `vx` ±0.7, `vy` ±0.3, `vtheta` ±3.0 when
turning in place (`vx = vy = 0`) and ±1.5 while translating. Tune these via
`VX_MAX` / `VY_MAX` / `VTHETA_MAX_STATIONARY` / `VTHETA_MAX_MOVING` in
[constants.py](../src/constants.py).

Signs, deadzone and button mapping are constants at the top of
[gamepad_input.py](../src/input/gamepad_input.py); the move/button mapping is set
via `GAMEPAD_BUTTON_MOVES` in [main.py](../src/main.py).

Force a source with the `MICROBAN_INPUT` environment variable
(`gamepad`, `keyboard`, or `auto`, the default).

### Pairing the controller on the Pi

On the Pi, put the Xbox controller in pairing mode (hold the pair button until the
Xbox light flashes fast), then:

```
bluetoothctl
[bluetooth]# power on
[bluetooth]# agent on
[bluetooth]# scan on        # wait for the "Xbox Wireless Controller" MAC to appear
[bluetooth]# pair  XX:XX:XX:XX:XX:XX
[bluetooth]# trust XX:XX:XX:XX:XX:XX    # auto-reconnect on next power-on
[bluetooth]# connect XX:XX:XX:XX:XX:XX
[bluetooth]# scan off
[bluetooth]# quit
```

Once paired and trusted, the controller reconnects automatically when powered on.

### Device permissions

Reading `/dev/input/js*` requires membership in the `input` group (otherwise you'd
need root):

```
sudo usermod -aG input $USER
```

Log out and back in (or reboot) for the group change to take effect.

### Verifying

Once paired, a device node appears:

```
ls /dev/input/js*        # e.g. /dev/input/js0
```

You can watch raw events with `jstest` (from the `joystick` package):

```
sudo apt install -y joystick
jstest /dev/input/js0
```

### Remapping for your controller

Xbox controllers don't all expose the same axis/button numbers — over Bluetooth the
kernel often uses a different layout than the wired `xpad` one. If a stick or button
doesn't behave as expected, find the real numbers and update the constants.

1. Run `jstest /dev/input/js0`, then move each stick and press each button one at a
   time, noting the `Axis N` / `Button N` that changes:

   | Action | Note the number |
   | :--- | :--- |
   | Left stick horizontal / vertical | `Axis` → `_AXIS_LX` / `_AXIS_LY` |
   | Right stick horizontal | `Axis` → `_AXIS_RX` (drives `vtheta`) |
   | A / B / Back / Start | `Button` → `XBOX_BUTTONS` |

2. Edit the constants at the top of
   [gamepad_input.py](../src/input/gamepad_input.py):
   - `_AXIS_LX`, `_AXIS_LY`, `_AXIS_RX` — the stick axis numbers.
   - `XBOX_BUTTONS` — the button name → number map (at least the ones you use).
   - `VX_SIGN`, `VY_SIGN`, `VTHETA_SIGN` — flip between `+1.0` / `-1.0` if a direction
     is reversed.

3. Which button does what is set by `GAMEPAD_BUTTON_MOVES` in
   [main.py](../src/main.py) (moves) and the `stop_button` / `imu_button` arguments of
   `GamepadInputSource` (defaults: stop = `B`, IMU = `BACK`).

The defaults shipped in the repo (A=0, B=1, Start=11; left stick = axes 0/1, right
stick horizontal = axis 2) are verified on an Xbox controller over Bluetooth.
