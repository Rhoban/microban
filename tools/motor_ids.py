# /// script
# requires-python = ">=3.10"
# dependencies = ["rustypot==1.13.1"]
# ///
"""Find which motor is which on the assembled robot, by clicking: each motor of the chain moves a little (and lights
its LED), you click on the robot's picture where it moved; at the end every motor gets its ID (src/constants.py
MOTOR_TO_ID), the settings of docs/assembly.md and the new baud rate (1 Mbps by default, as src/robot_controller.py).

    uv run tools/motor_ids.py [--port /dev/ttyUSB0] [--baud 1000000]     # opens http://127.0.0.1:8770

Two ways:
* "Scan": motors that already have distinct IDs (any), on the chain.
* "New motors": brand-new motors (all ID 1, 57600 bps) plugged into the chain ONE AT A TIME, from the board
  outwards: each one gets a temporary ID as soon as it answers, moves, and you click it; then plug the next one.

Each motor moves +-8 deg around where it is, slowly, then its torque is released: lay the robot down or hold it.
"""
import argparse
import json
import pathlib
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from motor_setup import BAUDS, MOTORS, SETTINGS, default_port, open_bus

HERE = pathlib.Path(__file__).parent
ASSETS = HERE / "motor_ids_assets"
WIGGLE_TICKS = 90            # +-7.9 deg (4096 ticks per turn)
WIGGLE_SPEED = 30            # profile velocity, x 0.229 rpm: ~41 deg/s
TEMP_ID0 = 200               # temporary IDs while renumbering (no clash with the final ones)
NEW_ID0 = 150                # temporary IDs of the brand-new motors, as they are plugged
PARK_ID0 = 100               # unclicked motors holding an ID the renumbering needs go to 100-149
FACTORY_ID, FACTORY_BAUD = 1, 57600


class Robot:
    """The chain: which IDs answer at which rate, which joint each one is (from the clicks)."""

    def __init__(self, port, target_baud):
        self.bus = open_bus(port, target_baud)
        self.target = target_baud
        self.lock = threading.Lock()
        self.found = {}          # id -> baud rate
        self.joint = {}          # id -> joint name, from the clicks
        self.log = []
        self.progress = None     # {"task", "done", "total", "text"} while scanning / moving / writing (the page polls it)

    def step(self, task, done, total, text=""):
        self.progress = {"task": task, "done": done, "total": total, "text": text}

    def say(self, msg):
        self.log.append(time.strftime("%H:%M:%S ") + msg)
        print(msg)

    def scan(self):
        with self.lock:
            self.found = {}
            bauds = sorted(BAUDS, reverse=True)
            for k, baud in enumerate(bauds):
                self.step("Scanning", k, len(bauds), f"{baud} bps")
                self.bus.set_baudrate(baud)
                time.sleep(0.02)
                for mid in self.bus.broadcast_scan():
                    self.found.setdefault(mid, baud)
            self.joint = {i: j for i, j in self.joint.items() if i in self.found}
            self.progress = None
            self.say(f"scan: {len(self.found)} motors: " + ", ".join(f"ID {i} @ {b}" for i, b in sorted(self.found.items())))

    def new_motor(self):
        """A brand-new motor just plugged (ID 1, 57600 bps): give it the next temporary ID, so that the next new motor
        can answer as ID 1 too. Returns its ID, or None when no new motor answers."""
        with self.lock:
            b = self.bus
            b.set_baudrate(FACTORY_BAUD)
            time.sleep(0.02)
            if not b.ping(FACTORY_ID):
                return None
            try:                                           # two motors at ID 1 answer on top of each other
                for _ in range(5):
                    b.read_register(FACTORY_ID, "present_position")
            except Exception as e:
                raise RuntimeError(f"ID 1 answers badly ({e}): several new motors plugged at once? Plug one at a time")
            used = set(self.found)
            new = next(i for i in range(NEW_ID0, TEMP_ID0) if i not in used)
            b.write_torque_enable(FACTORY_ID, False)
            b.write_id(FACTORY_ID, new)
            time.sleep(0.02)
            if not b.ping(new):
                raise RuntimeError(f"the new motor does not answer at its temporary ID {new}")
            self.found[new] = FACTORY_BAUD
            self.say(f"new motor: ID 1 -> temporary ID {new}")
            return new

    def wiggle(self, mid):
        with self.lock:
            b = self.bus
            b.set_baudrate(self.found[mid])
            time.sleep(0.02)
            p = b.read_register(mid, "present_position")
            b.write_register(mid, "goal_position", p)            # torque on where it is: no jump
            b.write_register(mid, "profile_velocity", WIGGLE_SPEED)
            b.write_register(mid, "led", 1)
            b.write_torque_enable(mid, True)
            try:
                for k, goal in enumerate((p + WIGGLE_TICKS, p - WIGGLE_TICKS, p + WIGGLE_TICKS, p)):
                    self.step(f"ID {mid} is moving", k, 4)
                    b.write_register(mid, "goal_position", goal)
                    time.sleep(0.55)
            finally:
                self.progress = None
                b.write_torque_enable(mid, False)
                b.write_register(mid, "led", 0)
            self.say(f"ID {mid} moved")

    def apply(self):
        """Renumber (through temporary IDs), write the settings, then the baud rate; check every motor. A motor not
        clicked that holds an ID the renumbering needs is first moved to a free ID from 100 (out of the robot's range)."""
        with self.lock:
            b = self.bus
            plan = sorted(self.joint.items())
            others = set(self.found) - set(self.joint)
            free = (i for i in range(TEMP_ID0, 253) if i not in self.found)      # temporary IDs nobody holds
            temp = {mid: next(free) for mid, name in plan if mid != MOTORS[name]}
            needed = {MOTORS[n] for _, n in plan} | set(temp.values())
            parked = sorted(others & needed)
            total, done = len(parked) + 4 * len(plan), 0

            def tick(text):
                nonlocal done
                self.step("Writing", done, total, text)
                done += 1
            for mid in parked:                                     # 0) unclicked motors in the way: out of the robot's range
                tick(f"ID {mid} (not clicked) out of the way")
                park = next(i for i in range(PARK_ID0, NEW_ID0) if i not in self.found and i not in needed)
                b.set_baudrate(self.found[mid])
                time.sleep(0.02)
                b.write_torque_enable(mid, False)
                b.write_id(mid, park)
                time.sleep(0.02)
                if not b.ping(park):
                    raise RuntimeError(f"ID {mid} (not clicked) did not answer at its new ID {park}: nothing else written")
                self.found[park] = self.found.pop(mid)
                self.say(f"ID {mid} was not clicked and is needed: moved to ID {park}")
            for mid, _ in plan:                                    # 1) temporary IDs
                tick(f"ID {mid}: temporary ID")
                b.set_baudrate(self.found[mid])
                time.sleep(0.02)
                b.write_torque_enable(mid, False)
                if mid in temp:
                    b.write_id(mid, temp[mid])
            for mid, name in plan:                                 # 2) final IDs, settings, baud rate (last)
                b.set_baudrate(self.found[mid])
                time.sleep(0.02)
                cur = temp.get(mid, mid)
                new = MOTORS[name]
                tick(f"{name}: ID {new} and settings")
                if cur != new:
                    b.write_id(cur, new)
                b.write_return_delay_time(new, SETTINGS["return_delay_time"])
                b.write_pwm_slope(new, SETTINGS["pwm_slope"])
                b.write_shutdown(new, SETTINGS["shutdown"])
                if self.found[mid] != self.target:
                    b.write_baud_rate(new, BAUDS[self.target])
                    time.sleep(0.05)
            b.set_baudrate(self.target)
            time.sleep(0.05)
            for _, name in plan:                                   # clears an input voltage error latched at boot
                tick(f"{name}: reboot")
                b.reboot(MOTORS[name])
            time.sleep(0.5)
            bad = []
            for _, name in plan:
                new = MOTORS[name]
                tick(f"{name}: check")
                try:
                    got = {k: b.read_register(new, k) for k in ("id", "baud_rate", *SETTINGS)}
                    if got != {"id": new, "baud_rate": BAUDS[self.target], **SETTINGS}:
                        bad.append(f"{name} {got}")
                except Exception as e:
                    bad.append(f"{name}: {e}")
            self.found = {MOTORS[n]: self.target for _, n in plan} | {i: bd for i, bd in self.found.items()
                                                                     if i not in self.joint}
            self.joint = {MOTORS[n]: n for _, n in plan}
            self.progress = None
            self.say("applied: " + (f"{len(plan)} motors OK at {self.target} bps" if not bad else "PROBLEMS: " + "; ".join(bad)))
            return not bad

    def state(self):
        return {"found": self.found, "joint": self.joint, "target": self.target, "motors": MOTORS,
                "log": self.log[-12:], "progress": self.progress}


def handler(robot):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(200, (ASSETS / "index.html").read_bytes(), "text/html; charset=utf-8")
            if self.path.startswith("/assets/"):
                f = ASSETS / pathlib.Path(self.path).name
                if f.is_file():
                    ctype = {".png": "image/png", ".json": "application/json"}.get(f.suffix, "text/plain")
                    return self.send(200, f.read_bytes(), ctype)
            if self.path == "/api/state":
                return self.send(200, robot.state())
            self.send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            try:
                if self.path == "/api/scan":
                    robot.scan()
                elif self.path == "/api/new":
                    new = robot.new_motor()
                    return self.send(200, {**robot.state(), "new": new})
                elif self.path == "/api/wiggle":
                    robot.wiggle(int(req["id"]))
                elif self.path == "/api/assign":
                    mid, name = int(req["id"]), req["joint"]
                    if name not in MOTORS:
                        raise ValueError(f"unknown joint {name}")
                    robot.joint = {i: j for i, j in robot.joint.items() if j != name}   # one motor per joint
                    robot.joint[mid] = name
                    robot.say(f"ID {mid} = {name} (will become ID {MOTORS[name]})")
                elif self.path == "/api/unassign":
                    robot.joint.pop(int(req["id"]), None)
                elif self.path == "/api/apply":
                    robot.apply()
                else:
                    return self.send(404, {"error": "not found"})
            except Exception as e:                                   # rustypot raises on communication errors
                robot.say(f"ERROR {self.path}: {e}")
                robot.progress = None
                return self.send(500, {"error": str(e), **robot.state()})
            self.send(200, robot.state())
    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=default_port(), help="serial port (default: the first USB serial adapter found; U2D2 Linux /dev/ttyUSB0, macOS /dev/cu.usbserial-..., Windows COMx)")
    ap.add_argument("--baud", type=int, default=1_000_000, choices=sorted(BAUDS), help="baud rate to set at the end")
    ap.add_argument("--http", type=int, default=8770, help="port of the page (this computer only)")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    robot = Robot(a.port, a.baud)
    srv = ThreadingHTTPServer(("127.0.0.1", a.http), handler(robot))
    url = f"http://127.0.0.1:{a.http}"
    print(f"{url}  (Ctrl+C to stop)")
    if not a.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
