# Live dashboard

`make dashboard HOST=<robot>` opens, on the PC, a page with the robot in 3D, every motor (angle and error to its
target, current, temperature, hardware error, torque), the trunk orientation, plots of the last 10 s and the robot's
events. A motor in overheating / overload error can be rebooted from it (its torque stays off: **Torque on** puts it
back, after a confirmation), and a run can be recorded (`recordings/*.npz`).

The robot only sends what its control loop already reads, in one UDP packet per tick (`src/telemetry.py`, port 7350),
and only while a dashboard listens: no extra bus traffic while nobody watches. While one listens, the loop also reads
the motors' health (torque, hardware error, voltage, temperature) once a second (two small sync reads, ~1.5 ms).
The page's commands run in the control loop between two ticks; a reboot takes ~0.3 s, during which the other motors
hold their last target. Everything else (kinematics, 3D, plots, recording) runs on the PC:
`src/humanoid_dashboard` (see its README), which does not depend on Microban and can serve other robots.

The input voltage error bit is always set at Microban's ~8 V (above the XL330's 7.0 V limit, Shutdown 52 does not cut
the torque for it): the page ignores it. `MICROBAN_DASHBOARD=0` turns the link off.

Without a robot: `PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.fake_robot --model "$(python -c 'import microban_model; print(microban_model.mjcf())')"`,
then `make dashboard HOST=127.0.0.1`.

## Torque, em and init

As on Rhoban's other robots, the motors have no torque until a move is launched (keyboard, gamepad): the robot then
goes to the neutral pose in 2 s with the torque on, and the move starts. When no move runs any more, the torque goes
off again. The page has the two whole-robot commands:

* **⏻ Torque off (em)**: emergency stop, the moves stop and every motor goes limp at once;
* **Init (zero)**: the moves stop, every motor goes to its zero in 2 s (the shoulders: arm forward) and stays there.

After either, a move that was already asked does not restart by itself: launch it again (release its key or button
and press it) to leave em / init.
