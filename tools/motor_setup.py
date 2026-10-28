# /// script
# requires-python = ">=3.10"
# dependencies = ["rustypot==1.13.1"]
# ///
"""Set up the robot's XL330 motors with a U2D2 (or the robot's bus): ID, baud rate and the settings of
docs/assembly.md, one motor at a time.

    uv run tools/motor_setup.py auto  [--port /dev/ttyUSB0]    # hands-free: plug a motor, it is done, unplug, next
    uv run tools/motor_setup.py setup [--port /dev/ttyUSB0]    # one motor plugged at a time, you pick which
    uv run tools/motor_setup.py check [--port ...]              # the whole chain: all 19 IDs and their settings
    uv run tools/motor_setup.py scan  [--port ...]              # who answers, at every baud rate

`setup` finds the plugged motor whatever its ID and baud rate, writes: the ID of the chosen motor (table below,
the robot's MOTOR_TO_ID), Return Delay Time 0, PWM Slope 255, Shutdown 52 (no input voltage error), then the baud
rate (1 Mbps by default, as src/robot_controller.py; --baud to choose), and reads everything back at the new rate. --factory-reset first
restores the factory settings (as Dynamixel Wizard's "Recovery") for a used motor.
"""
import argparse
import sys
import time

from rustypot import Xl330PyController

# the robot's motors and their IDs (src/constants.py MOTOR_TO_ID)
MOTORS = {
    "left_hip_yaw": 11, "left_hip_roll": 12, "left_hip_pitch": 13, "left_knee": 14, "left_ankle_pitch": 15,
    "left_ankle_roll": 16,
    "right_hip_yaw": 21, "right_hip_roll": 22, "right_hip_pitch": 23, "right_knee": 24, "right_ankle_pitch": 25,
    "right_ankle_roll": 26,
    "left_shoulder_pitch": 31, "left_shoulder_roll": 32, "left_elbow": 33,
    "right_shoulder_pitch": 41, "right_shoulder_roll": 42, "right_elbow": 43,
    "head": 51,
}
# the settings every motor gets (register -> value), from docs/assembly.md
SETTINGS = {"return_delay_time": 0, "pwm_slope": 255, "shutdown": 52}
XL330_M288 = 1200                      # model number
BAUDS = Xl330PyController.baudrates()  # {baud rate: register value}


def default_port():
    """The U2D2's serial port: the first USB serial adapter found (Linux /dev/ttyUSB*, macOS /dev/cu.usbserial-*),
    else COM3 (Windows: see the Device Manager)."""
    import glob
    found = sorted(glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/cu.usbserial-*"))
    return found[0] if found else ("COM3" if sys.platform.startswith("win") else None)


def open_port(port, baud, timeout):
    if not port:
        sys.exit("No USB serial adapter found (is the U2D2 plugged in?): give it with --port "
                 "(Linux /dev/ttyUSB0, macOS /dev/cu.usbserial-..., Windows COMx)")
    try:
        return Xl330PyController(serial_port=port, baudrate=baud, timeout=timeout)
    except OSError as e:
        sys.exit(f"Cannot open {port} ({e}): check the U2D2 and give its port with --port "
                 "(Linux /dev/ttyUSB0, macOS /dev/cu.usbserial-..., Windows COMx)")


def open_bus(port, baud):
    return open_port(port, baud, 0.05)


def find(bus, first_baud, bauds=None):
    """Every motor that answers, as (baud rate, {id: model number}) for each rate that has some, the given rate
    first (all the rates the servo has, or `bauds`)."""
    found = []
    rest = sorted(BAUDS, reverse=True) if bauds is None else bauds
    for baud in [first_baud] + [b for b in rest if b != first_baud]:
        bus.set_baudrate(baud)
        time.sleep(0.02)
        ids = bus.broadcast_scan()
        if ids:
            found.append((baud, ids))
    return found


def settings_of(bus, mid):
    return {name: bus.read_register(mid, name) for name in ("id", "baud_rate", *SETTINGS)}


def configure(bus, baud, old_id, new_id, target_baud, factory_reset):
    """Configure the one motor (at `baud`, id `old_id`) and check it at the target rate."""
    bus.set_baudrate(baud)                                 # the scan left the port at the last rate it tried
    time.sleep(0.02)
    if factory_reset:
        print("  factory reset ...")
        bus.factory_reset(old_id, conserve_id_only=False, conserve_id_and_baudrate=False)
        time.sleep(1.0)                                    # the motor reboots at ID 1, 57600 bps
        baud, old_id = 57600, 1
        bus.set_baudrate(baud)
        time.sleep(0.05)
        if not bus.ping(old_id):
            raise RuntimeError("no answer after the factory reset (expected ID 1 at 57600 bps)")
    bus.write_torque_enable(old_id, False)                 # the EEPROM registers only take writes torque off
    if old_id != new_id:
        bus.write_id(old_id, new_id)
        time.sleep(0.02)
        if not bus.ping(new_id):
            raise RuntimeError(f"no answer at the new ID {new_id}")
    bus.write_return_delay_time(new_id, SETTINGS["return_delay_time"])
    bus.write_pwm_slope(new_id, SETTINGS["pwm_slope"])
    bus.write_shutdown(new_id, SETTINGS["shutdown"])
    if baud != target_baud:                                # last: the motor stops answering at the old rate
        bus.write_baud_rate(new_id, BAUDS[target_baud])
        time.sleep(0.05)
        bus.set_baudrate(target_baud)
        time.sleep(0.05)
    if not bus.ping(new_id):
        raise RuntimeError(f"no answer at ID {new_id}, {target_baud} bps")
    got = settings_of(bus, new_id)
    want = {"id": new_id, "baud_rate": BAUDS[target_baud], **SETTINGS}
    bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
    if bad:
        raise RuntimeError("read back differs (got, wanted): " + ", ".join(f"{k} {g} != {w}" for k, (g, w) in bad.items()))
    # a new motor booted with Shutdown 53: above 7 V its input voltage error is latched until a reboot
    bus.reboot(new_id)
    time.sleep(0.5)
    if not bus.ping(new_id):
        raise RuntimeError(f"no answer after the reboot (ID {new_id}, {target_baud} bps)")
    err = bus.read_register(new_id, "hardware_error_status")
    if err & SETTINGS["shutdown"]:                         # an error that still turns the torque off
        raise RuntimeError(f"hardware error {err:#04x} after the reboot")
    got["hardware_error_status"] = err                     # bit 0 (input voltage) may show: it no longer shuts down
    return got


def ask_motor(done, default):
    names = list(MOTORS)
    print()
    for i, n in enumerate(names, 1):
        mark = "done" if n in done else ""
        print(f"  {i:2d}. {n:22s} ID {MOTORS[n]:2d}  {mark}")
    ans = input(f"Motor to set up (number or name, Enter = {default}, q = quit): ").strip().lower()
    if ans in ("q", "quit", "exit"):
        return None
    if not ans:
        return default
    if ans.isdigit() and 1 <= int(ans) <= len(names):
        return names[int(ans) - 1]
    if ans in MOTORS:
        return ans
    print(f"  unknown motor '{ans}'")
    return ask_motor(done, default)


def cmd_setup(args):
    bus = open_bus(args.port, args.baud)
    done = []
    while True:
        todo = [n for n in MOTORS if n not in done]
        if not todo:
            print("\nAll 19 motors are set up. Chain them and run: uv run tools/motor_setup.py check")
            return
        name = ask_motor(done, todo[0])
        if name is None:
            return
        input(f"Plug ONLY the motor for {name} (ID {MOTORS[name]}), then press Enter ...")
        found = find(bus, args.baud)
        motors = [(b, i, m) for b, ids in found for i, m in ids.items()]
        if not motors:
            print("  no motor answers: check the cable, the U2D2 power and the port")
            continue
        if len(motors) > 1:
            print("  more than one motor answers: " + ", ".join(f"ID {i} at {b} bps" for b, i, _ in motors)
                  + ". Plug one motor at a time.")
            continue
        baud, mid, model = motors[0]
        print(f"  found ID {mid} at {baud} bps (model {model})")
        if model != XL330_M288:
            if input(f"  model {model} is not an XL330-M288 ({XL330_M288}). Go on anyway? [y/N] ").lower() != "y":
                continue
        try:
            got = configure(bus, baud, mid, MOTORS[name], args.baud, args.factory_reset)
        except Exception as e:                             # rustypot raises on communication errors
            print(f"  FAILED: {e}")
            continue
        print(f"  OK {name}: " + ", ".join(f"{k} {v}" for k, v in got.items()))
        done.append(name)


def shout(text):
    bar = "=" * (len(text) + 4)
    print(f"\a\n  {bar}\n  | {text} |\n  {bar}\n", flush=True)


def collided(bus):
    """Two brand-new motors plugged together answer as ID 1 on top of each other: a ping gets through, reads fail."""
    bus.set_baudrate(57600)
    time.sleep(0.02)
    if not bus.ping(1):
        return False
    try:
        bus.read_register(1, "model_number")
        return False
    except Exception:
        return True


def cmd_auto(args):
    """Plug a motor: it gets the next ID of the table, everything is written and checked, its name is shown; unplug
    it, plug the next one. Nothing to type."""
    bus = open_bus(args.port, args.baud)
    names = list(MOTORS)
    start = names.index(args.start) if args.start else 0
    todo = names[start:] + names[:start]
    done = set()
    likely = [57600, 1_000_000, 2_000_000]                  # factory rate first; every 5th scan tries every rate
    print(f"Plug the motors one at a time. First: {todo[0]} (ID {MOTORS[todo[0]]}). Ctrl+C to stop.\n")
    n = 0
    while True:
        left = [m for m in todo if m not in done]
        if not left:
            shout("All 19 motors done. Chain them and run: uv run tools/motor_setup.py check")
            return
        n += 1
        found = new_motor(bus) or find(bus, 57600, None if n % 5 == 0 else likely)
        motors = [(b, i, mo) for b, ids in found for i, mo in ids.items()]
        if not motors:
            if collided(bus):
                print("  several brand-new motors (ID 1) are plugged together: keep only one", flush=True)
                time.sleep(1.0)
            time.sleep(0.3)
            continue
        if len(motors) > 1:
            print("  more than one motor answers: " + ", ".join(f"ID {i} at {b} bps" for b, i, _ in motors)
                  + ": keep only one", flush=True)
            time.sleep(1.0)
            continue
        baud, mid, model = motors[0]
        name = {v: k for k, v in MOTORS.items()}.get(mid)
        if name and baud == args.baud:                      # already set up (this run or earlier): say which one
            bus.set_baudrate(baud)
            ok = all(bus.read_register(mid, k) == v for k, v in SETTINGS.items())
            if ok:
                done.add(name)
                shout(f"already set up: {name} (ID {mid}), unplug it")
                wait_unplugged(bus, mid, baud)
                continue
        if model != XL330_M288:
            print(f"  ID {mid} at {baud} bps is model {model}, not an XL330-M288 ({XL330_M288}): skipped, unplug it")
            wait_unplugged(bus, mid, baud)
            continue
        # a motor with a table ID not set up yet keeps it (renumbering it could make two motors share an ID)
        target = name if name and name not in done else left[0]
        print(f"  found ID {mid} at {baud} bps: setting it up as {target} ...", flush=True)
        try:
            configure(bus, baud, mid, MOTORS[target], args.baud, args.factory_reset)
        except Exception as e:
            print(f"  FAILED ({e}): unplug it and plug it again", flush=True)
            wait_unplugged(bus, None, None)
            continue
        done.add(target)
        nxt = [m for m in todo if m not in done]
        shout(f"{target} = ID {MOTORS[target]}: done, label it and unplug it"
              + (f"   (next: {nxt[0]})" if nxt else ""))
        wait_unplugged(bus, MOTORS[target], args.baud)


def new_motor(bus):
    """The quick check: a brand-new motor (ID 1 at 57600 bps) alone on the bus, as find() would report it."""
    bus.set_baudrate(57600)
    time.sleep(0.02)
    try:
        if bus.ping(1):
            return [(57600, {1: bus.read_register(1, "model_number")})]
    except Exception:                                       # two at ID 1 (reads collide): left to find()
        pass
    return []


def wait_unplugged(bus, mid, baud):
    """Until the motor stops answering (mid None: until nothing answers at any likely rate)."""
    while True:
        if mid is not None:
            bus.set_baudrate(baud)
            time.sleep(0.02)
            if not bus.ping(mid):
                return
        elif not find(bus, 57600, [57600, 1_000_000, 2_000_000]):
            return
        time.sleep(0.3)


def cmd_check(args):
    bus = open_bus(args.port, args.baud)
    ids = bus.broadcast_scan()
    ok = True
    for name, mid in MOTORS.items():
        if mid not in ids:
            print(f"  MISSING  {name:22s} ID {mid}")
            ok = False
            continue
        got = settings_of(bus, mid)
        bad = [f"{k} {got[k]} (want {v})" for k, v in SETTINGS.items() if got[k] != v]
        print(f"  {'OK' if not bad else 'WRONG':7s}  {name:22s} ID {mid}" + ("" if not bad else "  " + ", ".join(bad)))
        ok &= not bad
    for mid in sorted(set(ids) - set(MOTORS.values())):
        print(f"  UNKNOWN  ID {mid} answers but is not in the robot's table")
        ok = False
    others = [(b, sorted(i)) for b, i in find(bus, args.baud) if b != args.baud]
    for b, i in others:
        print(f"  NOTE     at {b} bps (not {args.baud}): IDs {i}")
        ok = False
    print("\nall 19 motors OK" if ok else "\nsome motors need attention (see above)")
    return 0 if ok else 1


def cmd_scan(args):
    bus = open_bus(args.port, args.baud)
    found = find(bus, args.baud)
    if not found:
        print("no motor answers at any baud rate")
    for baud, ids in found:
        names = {v: k for k, v in MOTORS.items()}
        print(f"{baud:>8d} bps: " + ", ".join(f"ID {i}" + (f" ({names[i]})" if i in names else "") for i in sorted(ids)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["auto", "setup", "check", "scan"])
    ap.add_argument("--port", default=default_port(),
                    help="serial port of the U2D2 (default: the first USB serial adapter found; Linux /dev/ttyUSB0, macOS /dev/cu.usbserial-..., Windows COMx)")
    ap.add_argument("--baud", type=int, default=1_000_000, choices=sorted(BAUDS),
                    help="baud rate to set (setup) or to check at (check); 1 Mbps by default")
    ap.add_argument("--factory-reset", action="store_true", help="auto/setup: factory reset each motor first")
    ap.add_argument("--start", choices=list(MOTORS), help="auto: the first motor (then the table order)")
    args = ap.parse_args()
    try:
        sys.exit({"auto": cmd_auto, "setup": cmd_setup, "check": cmd_check, "scan": cmd_scan}[args.command](args) or 0)
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
