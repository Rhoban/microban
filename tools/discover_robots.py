# SPDX-License-Identifier: GPL-3.0-or-later
"""The Microban robots on this network (make discover-robots): their name, address, and whether their program runs.

Two ways, merged by address:
* mDNS: every robot announces its SSH service under its name (microban-XXXX, see docs/sd_image.md): all the robots
  switched on;
* the dashboard's link (UDP 7350): a "hello" sent to the whole network, which a robot answers while its program runs,
  with its version (classic / climber) and whether its torque is on.

    uv run --group dashboard python tools/discover_robots.py [--wait 2]
"""
import argparse
import json
import socket
import struct
import time

PORT = 7350                 # humanoid_dashboard.link.PORT
MAGIC = b"HDT1"
HEADER = struct.Struct("<4sIId")


def mdns_robots(wait: float) -> dict:
    """address -> name, of the SSH services named microban-* announced on the network."""
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
    except ImportError:
        print("(zeroconf missing: uv run --group dashboard ...; only the robots whose program runs are listed)")
        return {}
    found = {}

    class Listener(ServiceListener):
        def add_service(self, zc, type_, name):
            if not name.lower().startswith("microban-"):
                return
            info = zc.get_service_info(type_, name, timeout=1500)
            if info:
                for addr in info.parsed_addresses():
                    if ":" not in addr:                 # IPv4
                        found[addr] = name.split(".")[0]

        def update_service(self, zc, type_, name):
            self.add_service(zc, type_, name)

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, "_ssh._tcp.local.", Listener())
        time.sleep(wait)
    finally:
        zc.close()
    return found


def running_robots(wait: float) -> dict:
    """address -> {robot, host, variant, torque}, of the robots whose program answers the dashboard's hello."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.settimeout(0.2)
    s.bind(("0.0.0.0", 0))
    hello = json.dumps({"op": "hello"}).encode()
    found, schemas = {}, {}
    end = time.monotonic() + wait
    sent = 0.0
    while time.monotonic() < end:
        if time.monotonic() - sent > 0.7:             # a few times: UDP may lose one
            for dest in ("255.255.255.255", "<broadcast>"):
                try:
                    s.sendto(hello, (dest, PORT))
                except OSError:
                    pass
            sent = time.monotonic()
        try:
            data, (addr, _) = s.recvfrom(65536)
        except (socket.timeout, OSError):
            continue
        if data[:4] == MAGIC:                         # a frame: the torque, from the schema's "powered" field
            sch = schemas.get(addr)
            if sch and addr in found:
                k = 0
                for name, labels in sch["fields"]:
                    if name == "powered":
                        (v,) = struct.unpack_from("<f", data, HEADER.size + 4 * k)
                        found[addr]["torque"] = "on" if v == 1 else "off"
                    k += len(labels)
            continue
        try:
            msg = json.loads(data)
        except ValueError:
            continue
        if msg.get("op") == "schema":
            meta = msg.get("meta") or {}
            schemas[addr] = msg
            found.setdefault(addr, {}).update(robot=msg.get("robot", "?"), host=meta.get("host"),
                                              variant=meta.get("variant", "?"))
    s.close()
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=2.0, help="seconds to listen (default 2)")
    a = ap.parse_args()
    names = mdns_robots(a.wait)
    running = running_robots(a.wait)
    rows = {}
    for addr, name in names.items():
        rows[addr] = {"name": name}
    for addr, r in running.items():
        rows.setdefault(addr, {}).update(r)
        rows[addr].setdefault("name", r.get("host") or "?")
    if not rows:
        print("No robot found. Is it switched on, on the same wifi network as this computer (the hackathon's router)?")
        return
    print(f"{'robot':<16} {'address':<16} {'program':<12} {'version':<9} torque")
    for addr, r in sorted(rows.items(), key=lambda kv: kv[1]["name"]):
        program = "running" if "robot" in r else "not running"
        print(f"{r['name']:<16} {addr:<16} {program:<12} {r.get('variant', '-'):<9} {r.get('torque', '-')}")
    first = next(iter(sorted(rows.values(), key=lambda r: r["name"])))["name"]
    if first != "?":
        print(f"\nmake dashboard HOST={first}.local      make deploy HOST=radxa@{first}.local")


if __name__ == "__main__":
    main()
