# SPDX-License-Identifier: GPL-3.0-or-later
"""The robot's side of the live dashboard (humanoid-dashboard, run on the PC: `make dashboard`).

Once per tick, after the motors were commanded, sends what the loop already read (positions, velocities, currents,
targets, IMU, tick time) and the moves' states in one UDP packet, only while a PC listens. While one listens, it also
reads the motors' health about once a second (torque, hardware error, voltage, temperature: two small sync reads) and
runs the page's commands between two ticks: `reboot` a motor (clears overheating / overload; its torque stays off),
`torque` on/off for one motor; and passes the scheduler's to it: `em` (stop the moves, torque off), `init` (stop the
moves, every motor to its zero, held until a move is launched), `move_start` / `move_stop` (a registered move, as its
key would). The moves' live controls: `slider` sets a move's slider (its sliders), `keys` the keys held in the page's
keyboard zone (the move's pressed, on_key; the page repeats it while keys are held: without news
for KEYS_TIMEOUT_S, e.g. the PC's link lost, they are released). `variant` says which version the robot is (classic /
climber: the moves made for it, their variants), saved on the robot by the scheduler.
Without the humanoid_dashboard package, or with MICROBAN_DASHBOARD=0, it does nothing.
"""
import math
import os
import socket
import time

from constants import MOTOR_TO_ID
from moves.move import ALL, CLASSIC

try:
    from humanoid_dashboard.link import Link
except ImportError:
    Link = None

HEALTH_EVERY = 50                  # ticks (1 s at 50 Hz)
CURRENT_LIMIT_A = 1.75             # XL330 at 5-8 V (BAM max_current)
TEMPERATURE_LIMIT_C = 70           # XL330 factory Temperature Limit
VOLTAGE_BIT = 1                    # always set above 7 V (the robot runs at ~8 V): not an error for Microban
KEYS_TIMEOUT_S = 0.6               # the page repeats the held keys every 0.2 s
MOVE_STATE = {"INACTIVE": 0, "ACTIVE": 2, "STOPPING": 3}   # the page's codes


def _move_problems() -> list[str]:
    """Why moves of src/moves/ were skipped at start (moves/discover.py): the page shows them in its events."""
    try:
        from moves.discover import PROBLEMS
        return list(PROBLEMS)
    except ImportError:
        return []


class Telemetry:
    def __init__(self, controller):
        self.controller = controller
        self.link = None
        self.enabled = Link is not None and os.environ.get("MICROBAN_DASHBOARD", "1") != "0"
        self.names = list(MOTOR_TO_ID)
        self.ids = [MOTOR_TO_ID[n] for n in self.names]
        n = len(self.names)
        self.torque, self.error = [math.nan] * n, [math.nan] * n
        self.voltage, self.temperature = [math.nan] * n, [math.nan] * n
        self.health = getattr(controller, "sync_read_health", None)       # the real robot only
        self.requests: list[tuple[str, str | None]] = []                  # for the scheduler (take_requests)
        self.moves: dict = {}                                             # name -> moves.move.Runner
        self.variant = CLASSIC
        self.sliders: list[tuple[str, str]] = []                          # (move, slider) in the field's order
        self.tick_count = 0
        self._keys: set[str] = set()
        self._keys_t = 0.0

    def configure(self, moves: dict, variant: str = CLASSIC) -> None:
        """The scheduler's moves (name -> Runner): the page lists them, with each move's description and the versions
        of the robot it is made for, and can start / stop them. variant: the robot's version (classic / climber)."""
        if not self.enabled or self.link is not None:
            return
        self.moves, self.variant = moves, variant
        listed = self._listing()
        self.sliders = [(k, n) for k, m in moves.items() for n in m.sliders]
        cmds = (["reboot", "torque"] if hasattr(self.controller, "reboot") else []) + ["em", "init", "move_start", "move_stop",
                                                                                     "move_option", "save_options",
                                                                                     "slider", "keys", "variant"]
        sliders = {"sliders": [f"{k}.{n}" for k, n in self.sliders]} if self.sliders else {}
        try:
            self.link = Link("Microban", fields={
                "q": self.names, "q_target": self.names, "dq": self.names, "current": self.names,
                "torque": self.names, "hw_error": self.names, "voltage": self.names, "temperature": self.names,
                "imu_quat": ["w", "x", "y", "z"], "gyro": ["x", "y", "z"], "acc": ["x", "y", "z"],
                "tick_ms": ["tick"], "powered": ["on"], "init": ["on"],
                "moves": [m["name"] for m in listed], **sliders},
                meta={"motor_ids": MOTOR_TO_ID, "limits": {"current": CURRENT_LIMIT_A, "temperature": TEMPERATURE_LIMIT_C},
                      "hw_error_bits": {"0": "input voltage", "2": "overheating", "3": "motor encoder",
                                        "4": "electrical shock", "5": "overload"},
                      "hw_error_ignore": VOLTAGE_BIT, "commands": cmds, "moves": listed,
                      "warnings": _move_problems(), "variant": variant, "variants": list(ALL),
                      "host": socket.gethostname(),       # its name on the network (make discover-robots)
                      # how the page shows the one-value fields: a label and unit, or a flag's texts (on / off)
                      "scalars": {"tick_ms": {"label": "loop", "unit": "ms"},
                                  "powered": {"flag": ["torque off", "torque on"]},
                                  "init": {"flag": ["", "init: zero pose held"]}}})
        except OSError as e:          # port taken (another session): the robot runs without the dashboard
            print(f"Warning: dashboard link off ({e})", end="\r\n", flush=True)
            self.enabled = False

    def _listing(self) -> list[dict]:
        return [{"name": k, "kind": "move", "options": dict(m.options), "option_docs": m.option_docs,
                 "sliders": {n: list(v) for n, v in m.sliders.items()}, "keys": m.keys,
                 "variants": list(m.variants),                           # the page lists it for those only
                 "available": self.variant in m.variants, "doc": m.description}
                for k, m in self.moves.items()]

    def event(self, text: str, level: str = "info") -> None:
        if self.link is not None:
            self.link.event(text, level)

    def options_changed(self) -> None:
        """A move's options changed: the page gets the new values."""
        if self.link is not None:
            self.link.set_meta({**self.link.meta, "moves": self._listing()})

    def take_requests(self) -> list[tuple]:
        """The scheduler asks once per tick: [("em" | "init" | "start" | "stop" | "option" | "save_options" | "variant",
        move, version or None[, (option, value)]), ...]."""
        out, self.requests = self.requests, []
        return out

    def set_variant(self, variant: str) -> None:
        """The robot's version changed (the scheduler saved it): the page gets it, and which moves are available."""
        self.variant = variant
        if self.link is not None:
            self.link.set_meta({**self.link.meta, "variant": variant, "moves": self._listing()})

    def keys_held(self) -> set[str]:
        """The keys held in the page's keyboard zone (none once the page stopped repeating them)."""
        if self._keys and time.monotonic() - self._keys_t > KEYS_TIMEOUT_S:
            self._keys = set()
        return set(self._keys)

    def torque_changed(self, on: bool) -> None:
        self.torque = [int(on)] * len(self.ids)

    def tick(self, state, target_angles: dict, tick_ms: float, status: dict | None = None) -> None:
        """Call once per tick, after the motors were commanded (the bus is free)."""
        if self.link is None:
            self.configure({})
            if self.link is None:
                return
        self.tick_count += 1
        if self.health and self.link.listening and self.tick_count % HEALTH_EVERY == 0:
            self._read_health()
        names = self.names
        status = status or {}
        moves = [MOVE_STATE.get(m.state.name, 0) for m in self.moves.values()]
        self.link.publish(
            q=[state.motor_positions.get(n, math.nan) for n in names],
            q_target=[target_angles.get(n, math.nan) for n in names],
            dq=[state.motor_velocities.get(n, math.nan) for n in names],
            current=[state.measured_currents.get(n, math.nan) for n in names] if state.measured_currents else None,
            torque=self.torque, hw_error=self.error, voltage=self.voltage, temperature=self.temperature,
            imu_quat=state.body_quat or None, gyro=state.gyro or None, acc=state.acc or None,
            tick_ms=tick_ms, powered=status.get("powered"), init=status.get("init"),
            moves=moves, sliders=[self.moves[k].slider[n] for k, n in self.sliders])
        for cmd in self.link.commands():
            self._run(cmd)

    def _read_health(self) -> None:
        try:
            torque, error, voltage, temperature = self.health(self.ids)
        except RuntimeError:          # a motor missing: keep the last values
            return
        for i, n in enumerate(self.names):
            new = error[i] & ~VOLTAGE_BIT
            old = 0 if math.isnan(self.error[i]) else int(self.error[i]) & ~VOLTAGE_BIT
            if new & ~old:            # a new error bit: say it once
                self.link.event(f"{n} (ID {self.ids[i]}): hardware error {error[i]:#04x}, torque off", "error")
        self.torque, self.error, self.voltage, self.temperature = torque, error, voltage, temperature

    def _run(self, cmd: dict) -> None:
        name = cmd["name"]
        if name == "keys":                            # no answer: sent at each key and repeated while keys are held
            held = cmd["args"].get("held")
            if isinstance(held, list):
                self._keys = {str(k)[:20] for k in held[:10]}
                self._keys_t = time.monotonic()
            return
        if name == "slider":                          # no answer either (many while dragged): the frames show it
            m = self.moves.get(cmd["args"].get("move"))
            sl = cmd["args"].get("slider")
            spec = m.sliders.get(sl) if m is not None else None
            value = cmd["args"].get("value")
            if spec is not None and isinstance(value, (int, float)) and math.isfinite(value):
                m.slider[sl] = min(max(float(value), spec[0]), spec[1])
            return
        if name in ("em", "init"):                    # run by the scheduler at its next tick
            self.requests.append((name, None))
            self.link.ack(cmd, True, "emergency stop: moves stopped, torque off" if name == "em" else
                          "init: moves stopped, every motor to its zero (held until a move is launched)")
            return
        if name == "variant":                         # set and saved by the scheduler
            v = cmd["args"].get("variant")
            if v not in ALL:
                self.link.ack(cmd, False, f"{v!r} is not a version of the robot ({', '.join(ALL)})")
                return
            self.requests.append(("variant", v))
            self.link.ack(cmd, True, f"this robot is a {v}")
            return
        if name == "save_options":                    # written by the scheduler (it owns the moves)
            self.requests.append(("save_options", None))
            self.link.ack(cmd, True, "saving the move options")
            return
        if name == "move_option":
            move, opt, value = cmd["args"].get("move"), cmd["args"].get("option"), cmd["args"].get("value")
            m = self.moves.get(move)
            if m is None or opt not in m.options:
                self.link.ack(cmd, False, f"{move} has no option {opt}")
                return
            old = m.options[opt]
            try:
                value = type(old)(value) if not isinstance(old, bool) else bool(value)
            except (TypeError, ValueError):
                self.link.ack(cmd, False, f"{move}.{opt}: {value!r} is not a {type(old).__name__}")
                return
            self.requests.append(("option", move, (opt, value)))
            self.link.ack(cmd, True, f"{move}.{opt} = {value}")
            return
        if name in ("move_start", "move_stop"):
            move = cmd["args"].get("move")
            if move not in self.moves:
                self.link.ack(cmd, False, f"unknown move {move}")
                return
            self.requests.append(("start" if name == "move_start" else "stop", move))
            self.link.ack(cmd, True, f"{move}: {'start' if name == 'move_start' else 'stop'}")
            return
        joint = cmd["args"].get("joint")
        if joint not in MOTOR_TO_ID:
            self.link.ack(cmd, False, f"unknown joint {joint}")
            return
        mid, i = MOTOR_TO_ID[joint], self.names.index(joint)
        try:
            # a reboot waits for the motor (0.1 to 1.5 s): the control loop pauses meanwhile (one motor is in error)
            if name == "reboot":
                took = self.controller.reboot(mid)
                self.torque[i], self.error[i] = 0, math.nan
                self.link.ack(cmd, True, f"{joint} (ID {mid}) rebooted in {took:.2f} s, torque off")
            elif name == "torque":
                on = bool(cmd["args"].get("on"))
                self.controller.write_torque_enable(mid, on)
                self.torque[i] = int(on)
                self.link.ack(cmd, True, f"{joint} (ID {mid}) torque {'on' if on else 'off'}")
            else:
                self.link.ack(cmd, False, f"unknown command {name}")
        except (RuntimeError, AttributeError) as e:
            self.link.ack(cmd, False, f"{name} {joint}: {e}")
        if self.health:
            self._read_health()

    def close(self) -> None:
        if self.link is not None:
            self.link.close()
