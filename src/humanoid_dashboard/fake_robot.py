"""A fake robot for trying the dashboard without hardware: the model's joints move slowly, the trunk sways, one motor
overheats after a while (hardware error, torque off) until it is rebooted from the page.

    python -m humanoid_dashboard.fake_robot --model path/to/robot.xml       # then: python -m humanoid_dashboard.app --robot 127.0.0.1 ...
"""
import argparse
import math
import pathlib
import random
import time

from .link import Link, PORT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--hz", type=float, default=50.0)
    ap.add_argument("--overheat-after", type=float, default=15.0, help="s before one motor overheats (0: never)")
    a = ap.parse_args()
    import mujoco
    m = mujoco.MjModel.from_xml_path(a.model)
    joints = [m.joint(j).name for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_HINGE]
    rng = [tuple(m.jnt_range[m.joint(n).id]) if m.jnt_limited[m.joint(n).id] else (-1.0, 1.0) for n in joints]
    ids = {n: 10 + i for i, n in enumerate(joints)}
    link = Link("fake " + pathlib.Path(a.model).stem, {
        "q": joints, "q_target": joints, "dq": joints, "current": joints, "temperature": joints, "voltage": joints,
        "hw_error": joints, "torque": joints, "imu_quat": ["w", "x", "y", "z"], "gyro": ["x", "y", "z"],
        "acc": ["x", "y", "z"], "tick_ms": ["tick"], "bus_ms": ["bus"]},
        meta={"motor_ids": ids, "limits": {"current": 1.75, "temperature": 70.0},
              "hw_error_bits": {"0": "input voltage", "2": "overheating", "3": "motor encoder", "4": "electrical shock",
                                "5": "overload"}, "hw_error_ignore": 1, "commands": ["reboot", "torque"]}, port=a.port)
    print(f"fake robot: {len(joints)} joints, link on UDP {a.port}")
    temp = {n: 30.0 + random.random() * 5 for n in joints}
    err = {n: 1 for n in joints}            # input voltage bit, as on Microban at 8 V
    torque = {n: 1 for n in joints}
    hot = random.choice(joints)
    t0, dt = time.monotonic(), 1.0 / a.hz
    q = {n: 0.0 for n in joints}
    while True:
        tick = time.monotonic()
        t = tick - t0
        for cmd in link.commands():
            n = cmd["args"].get("joint")
            if n not in ids:
                link.ack(cmd, False, f"unknown joint {n}")
            elif cmd["name"] == "reboot":
                err[n], torque[n], temp[n] = 1, 0, min(temp[n], 60.0)
                link.ack(cmd, True, f"{n} (ID {ids[n]}) rebooted, torque off")
                link.event(f"{n} rebooted")
            elif cmd["name"] == "torque":
                torque[n] = 1 if cmd["args"].get("on") else 0
                link.ack(cmd, True, f"{n} torque {'on' if torque[n] else 'off'}")
            else:
                link.ack(cmd, False, f"unknown command {cmd['name']}")
        target, cur, dq = {}, {}, {}
        for i, (n, (lo, hi)) in enumerate(zip(joints, rng)):
            mid, amp = (lo + hi) / 2, min(0.4, (hi - lo) / 3)
            target[n] = mid + amp * math.sin(0.5 * t + i)
            if torque[n] and not err[n] & ~1:
                new = q[n] + 0.2 * (target[n] - q[n])
            else:
                new = q[n]
            dq[n] = (new - q[n]) / dt
            q[n] = new
            cur[n] = 0.05 + 0.4 * abs(target[n] - q[n]) * torque[n] + 0.02 * random.random()
            temp[n] += (0.002 if n != hot else (0.15 if a.overheat_after and t > a.overheat_after and torque[n] else -0.01))
            if temp[n] > 70.0 and not err[n] & 4:
                err[n] |= 4
                torque[n] = 0
                link.event(f"{n} (ID {ids[n]}): overheating, torque off", "error")
        roll, pitch = 0.1 * math.sin(0.3 * t), 0.08 * math.sin(0.23 * t)
        cr, sr, cp, sp = math.cos(roll / 2), math.sin(roll / 2), math.cos(pitch / 2), math.sin(pitch / 2)
        link.publish(q=[q[n] for n in joints], q_target=[target[n] for n in joints], dq=[dq[n] for n in joints],
                     current=[cur[n] for n in joints], temperature=[round(temp[n]) for n in joints],
                     voltage=[8.1 - 0.05 * sum(cur.values()) / len(cur)] * len(joints),
                     hw_error=[err[n] for n in joints], torque=[torque[n] for n in joints],
                     imu_quat=[cr * cp, sr * cp, cr * sp, -sr * sp], gyro=[0.03 * math.cos(0.3 * t), 0.02, 0.0],
                     acc=[0.0, 0.0, 1.0], tick_ms=1.2 + 0.3 * random.random(), bus_ms=4.0)
        time.sleep(max(0.0, dt - (time.monotonic() - tick)))


if __name__ == "__main__":
    main()
