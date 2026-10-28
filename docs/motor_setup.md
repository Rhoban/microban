# Motor setup tools (`tools/`)

Set the 19 XL330 (ID from `MOTOR_TO_ID`, 1 Mbps, Return Delay 0, PWM Slope 255, Shutdown 52, then a reboot that clears
the input-voltage error latched at power-on) with a U2D2 or on the robot's own port.

Dependencies: the tools only need [rustypot](https://pypi.org/project/rustypot/) 1.13.1 (Python >= 3.10), not the rest
of microban. Each script lists it in its header, so `uv run` installs it by itself on any PC (Linux, Windows, macOS);
with an old uv that does not, `uv self update`, or force it with `uv run --script tools/motor_setup.py ...`. Without
uv: `pip install rustypot==1.13.1`, then `python tools/motor_setup.py ...`.

```bash
uv run tools/motor_setup.py auto --port /dev/ttyUSB0      # plug one motor after the other: set as the next joint
uv run tools/motor_setup.py check --port /dev/ttyUSB0     # the whole chain: every ID and setting
uv run tools/motor_setup.py scan --port /dev/ttyUSB0      # who answers, at every rate
uv run tools/motor_ids.py --port /dev/ttyUSB0             # assembled robot: each motor moves, click the joint on the page
uv run tools/split_same_id.py --port /dev/ttyUSB0         # two motors on one ID: the warmer one gets another ID
```

On the robot (Radxa): `--port /dev/ttyS2`, the page through `ssh -L 8770:127.0.0.1:8770 <robot>`. `motor_ids.py` moves
a motor that holds an ID the robot needs out of the way first (ID 100 and up), then renumbers through free IDs.
