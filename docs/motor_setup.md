# Motor setup tools (`tools/`)

Set the 19 XL330 (ID from `MOTOR_TO_ID`, 1 Mbps, Return Delay 0, PWM Slope 255, Shutdown 52, then a reboot that clears
the input-voltage error latched at power-on) with a U2D2 or on the robot's own port.

Without `--port`, the tools take the first USB serial adapter (the U2D2: Linux `/dev/ttyUSB*`, macOS
`/dev/cu.usbserial-*`; on Windows give `--port COMx`).

```bash
uv run tools/motor_setup.py auto       # plug one motor after the other: set as the next joint
uv run tools/motor_setup.py check      # the whole chain: every ID and setting
uv run tools/motor_setup.py scan       # who answers, at every rate
uv run tools/motor_ids.py              # assembled robot: each motor moves, click the joint on the page
uv run tools/split_same_id.py          # two motors on one ID: the warmer one gets another ID
```

On the robot (Radxa): `--port /dev/ttyS2`, the page through `ssh -L 8770:127.0.0.1:8770 <robot>`. `motor_ids.py` moves
a motor that holds an ID the robot needs out of the way first (ID 100 and up), then renumbers through free IDs.
