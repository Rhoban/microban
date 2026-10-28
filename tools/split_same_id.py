# /// script
# requires-python = ">=3.10"
# dependencies = ["rustypot==1.13.1"]
# ///
"""Two XL330 answering on the same ID (e.g. two brand-new motors, ID 1 at 57600 bps): move the WARMER one to another
ID, without unplugging anything.

How: both get a temperature limit lowered one degree at a time, torque on. When the limit falls below the warmer
motor's temperature, that motor alone goes into an overheating error, which turns its torque off. An ID write sent
to both is then taken by that motor only (the ID is in EEPROM, writable with the torque off). Nothing moves. If the
two read the same temperature, both reach the limit together: the script puts them back as they were.
At the end both get the factory temperature limit back (70 degC) and are rebooted (clears the error).

    uv run tools/split_same_id.py [--port /dev/ttyUSB0] [--id 1] [--new 2] [--baud 57600]
"""
import argparse
import sys
import time

from rustypot import Xl330PyController

DEFAULT_LIMIT = 70           # XL330 factory Temperature Limit (degC)


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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=default_port(), help="serial port of the U2D2 (default: the first USB serial adapter found; Linux /dev/ttyUSB0, macOS /dev/cu.usbserial-..., Windows COMx)")
    ap.add_argument("--baud", type=int, default=57600)
    ap.add_argument("--id", type=int, default=1, help="the ID both motors answer on")
    ap.add_argument("--new", type=int, default=2, help="the ID to give the warmer motor")
    a = ap.parse_args()
    c = open_port(a.port, a.baud, 0.1)

    def quiet(f, *args):     # both motors execute a write to the shared ID; their status packets collide
        try:
            f(*args)
        except Exception:
            pass

    def alone(mid):          # a read succeeds only when exactly one motor answers
        try:
            for _ in range(3):
                c.read_register(mid, "present_temperature")
            return True
        except Exception:
            return False

    if alone(a.id):
        raise SystemExit(f"only one motor answers at ID {a.id}: nothing to separate")
    if alone(a.new):
        raise SystemExit(f"a motor already answers at ID {a.new}")
    done = None
    for limit in range(60, 9, -1):
        quiet(c.write_torque_enable, a.id, False)
        quiet(c.write_register, a.id, "temperature_limit", limit)
        quiet(c.write_torque_enable, a.id, True)       # a motor above the limit stays in error, torque off
        time.sleep(0.3)
        quiet(c.write_id, a.id, a.new)                 # only a motor with its torque off takes it
        time.sleep(0.05)
        one, two = alone(a.id), alone(a.new)
        if one and two:
            done = limit
            break
        if not one and not two and c.ping(a.new):      # both reached the limit and both moved: put them back
            quiet(c.write_id, a.new, a.id)
            print(f"limit {limit} degC: both motors reached it together (same temperature): undone")
            break
    print(f"separated: the warmer motor is now ID {a.new} (limit {done} degC)" if done else "not separated")
    for mid in (a.id, a.new):
        quiet(c.write_torque_enable, mid, False)
        quiet(c.write_register, mid, "temperature_limit", DEFAULT_LIMIT)
        quiet(c.reboot, mid)
    time.sleep(1.0)
    for mid in (a.id, a.new):
        if alone(mid):
            print(f"ID {mid}: {c.read_register(mid, 'present_temperature')} degC, temperature limit "
                  f"{c.read_register(mid, 'temperature_limit')}, error status {c.read_register(mid, 'hardware_error_status')}")
        else:
            print(f"ID {mid}: no single answer")


if __name__ == "__main__":
    main()
