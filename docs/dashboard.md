# Live dashboard

## Starting it

**On the robot, once:** `make robot-service-enable HOST=<robot>` installs the robot service: the control loop
(`src/main.py`, what `make run` runs) starts at every boot. Torque off until a move is launched; a gamepad is used
whenever one connects; otherwise the moves are started from the dashboard. It is the robot's program itself, not an
extra one: it costs nothing more (the dashboard link sends only while a PC listens). It holds the motors' port: stop it
(`make robot-service-stop`, then `make robot-service-start`) before a tool that talks to the motors on the robot
(`tools/motor_ids.py`, `tools/motor_setup.py`); `make run` (a keyboard session) stops it for you. `make
robot-service-logs` follows its output; `make robot-service-disable` removes it.

**On the PC, when you want to watch:** `make dashboard HOST=<robot>`, the robot's bare host name or IP (no `user@`),
or choose the robot in the page (its address, saved under a name for next time; `CLIMB=1`: the climbing forearms and feet in
the 3D view) opens http://127.0.0.1:8780. Close it any time: the robot does not depend on it.

`make dashboard HOST=<robot>` opens, on the PC, a page with the robot in 3D, every motor (angle and error to its
target, current, temperature, hardware error, torque), the trunk orientation, plots of the last 10 s and the robot's
events. A motor in overheating / overload error can be rebooted from it (its torque stays off: **Torque on** puts it
back, after a confirmation), **⟳ Deploy code** sends your code to the robot
shown and restarts its program (it runs `make deploy HOST=radxa@<robot>`, see [moves.md](moves.md); it needs your SSH
key on the robot: `ssh-copy-id radxa@<robot>`), and a run can be recorded (`recordings/*.npz`) and replayed in the page (**Replay**: slowed down, frame by
frame, back and forth).

The robot only sends what its control loop already reads, in one UDP packet per tick (`src/telemetry.py`, port 7350),
and only while a dashboard listens: no extra bus traffic while nobody watches. While one listens, the loop also reads
the motors' health (torque, hardware error, voltage, temperature) once a second (two small sync reads, ~1.5 ms).
The page's commands run in the control loop between two ticks; a reboot takes 0.1 to 1.5 s, during which the control
loop pauses and the other motors hold their last target. Only this page may use the dashboard's server: another web
page or site is refused (its Host and Origin are checked). Everything else (kinematics, 3D, plots, recording) runs on the PC:
`src/humanoid_dashboard` (see its README), which does not depend on Microban and can serve other robots.

The input voltage error bit is always set at Microban's ~8 V (above the XL330's 7.0 V limit, Shutdown 52 does not cut
the torque for it): the page ignores it. `MICROBAN_DASHBOARD=0` turns the link off.

Without a robot: `PYTHONPATH=src uv run --group dashboard python -m humanoid_dashboard.fake_robot --model "$(uv run python -c 'import microban_model; print(microban_model.mjcf())')"`,
then `make dashboard HOST=127.0.0.1`.

## Torque, em and init

As on Rhoban's other robots, the motors have no torque until a move is launched (keyboard, gamepad, or this page's Moves list): the robot then
goes to the neutral pose in 2 s with the torque on, and the move starts. When no move runs any more, the torque goes
off again. The page has the two whole-robot commands:

* **⏻ Torque off (em)**: emergency stop, the moves stop and every motor goes limp at once;
* **Init (zero)**: the moves stop, every motor goes to its zero in 2 s (the shoulders: arm forward) and stays there.

After either, a move that was already asked does not restart by itself: launch it again (release its key or button
and press it) to leave em / init.
