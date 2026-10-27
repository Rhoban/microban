"""PC side of the dashboard: receives the robot's telemetry (humanoid_dashboard.link), computes the 3D pose of the robot
model with MuJoCo (forward kinematics from the joint angles and the trunk orientation), and serves a web page (three.js)
with the motors, the IMU, plots, the robot's events and its commands (reboot a motor, torque on/off). Records frames.

    python -m humanoid_dashboard.app --robot HOST --model path/to/robot.xml [--http 8780]

The model is a MuJoCo XML or a URDF; joint fields of the telemetry are matched to the model's joints by name.
"""
import argparse
import asyncio
import json
import math
import pathlib
import struct
import time
import webbrowser
import zlib

import mujoco
import numpy as np
from aiohttp import web, WSMsgType

from .link import HEADER, MAGIC, PORT

WEB = pathlib.Path(__file__).parent / "web"
PUSH_HZ = 30


# ---------------------------------------------------------------------------------------------------- robot model
class Model:
    """The robot model: visual geoms for the page, forward kinematics from telemetry values."""

    def __init__(self, path, visual_groups=None, quat_field="imu_quat", joint_fields=("q",), motor_mesh="xl330"):
        self.motor_mesh = motor_mesh
        self.m = mujoco.MjModel.from_xml_path(str(path))
        self.d = mujoco.MjData(self.m)
        self.quat_field, self.joint_fields = quat_field, joint_fields
        m = self.m
        if visual_groups:
            vis = [g for g in range(m.ngeom) if m.geom_group[g] in visual_groups]
        else:
            vis = [g for g in range(m.ngeom) if m.geom_contype[g] == 0 and m.geom_conaffinity[g] == 0]
            vis = vis or list(range(m.ngeom))
        self.geoms = [g for g in vis if m.geom_bodyid[g] != 0 and m.geom_rgba[g][3] > 0]   # the robot, not the world
        self.bodies = sorted({int(m.geom_bodyid[g]) for g in self.geoms})
        self.free = next((j for j in range(m.njnt) if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_FREE), None)
        moving = (int(mujoco.mjtJoint.mjJNT_HINGE), int(mujoco.mjtJoint.mjJNT_SLIDE))   # (a numpy int is never `in` enums)
        self.joints = {m.joint(j).name: j for j in range(m.njnt) if int(m.jnt_type[j]) in moving}
        self.height = 0.0                         # trunk height that puts the lowest body on the floor at rest
        if self.free is not None:
            self.d.qpos[:] = m.qpos0
            self.d.qpos[m.jnt_qposadr[self.free]:m.jnt_qposadr[self.free] + 3] = 0
            mujoco.mj_kinematics(m, self.d)
            self.height = float(-self.d.xpos[self.bodies][:, 2].min())

    def scene(self):
        m = self.m
        geoms = []
        for g in self.geoms:
            rgba = m.mat_rgba[m.geom_matid[g]] if m.geom_matid[g] >= 0 else m.geom_rgba[g]
            geoms.append({"body": self.bodies.index(int(m.geom_bodyid[g])), "type": int(m.geom_type[g]),
                          "size": m.geom_size[g].tolist(), "pos": m.geom_pos[g].tolist(), "quat": m.geom_quat[g].tolist(),
                          "rgba": [float(x) for x in rgba], "mesh": int(m.geom_dataid[g]) if m.geom_type[g] == 7 else -1})
        joint_body = {name: self.bodies.index(int(m.jnt_bodyid[j])) for name, j in self.joints.items()
                      if int(m.jnt_bodyid[j]) in self.bodies}
        return {"bodies": [m.body(b).name for b in self.bodies], "geoms": geoms, "joint_body": joint_body,
                "joint_motor": self.motor_geoms(),
                "joints": {name: [float(x) for x in m.jnt_range[j]] for name, j in self.joints.items()}}

    def motor_geoms(self):
        """joint -> index (in the page's geoms) of the servo that drives it: the visual mesh whose name contains
        motor_mesh and whose centre lies closest to the joint's axis (the servo's output axis is the joint's)."""
        m, d = self.m, mujoco.MjData(self.m)
        mujoco.mj_forward(m, d)
        cases = [k for k, g in enumerate(self.geoms) if m.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH
                 and self.motor_mesh and self.motor_mesh in m.mesh(m.geom_dataid[g]).name]
        out, taken = {}, set()
        for name, j in self.joints.items():
            if not cases:
                break
            v = d.geom_xpos[[self.geoms[k] for k in cases]] - d.xanchor[j]
            along = v @ d.xaxis[j]
            off = np.linalg.norm(v - along[:, None] * d.xaxis[j], axis=1) + 0.2 * np.abs(along)
            for i in np.argsort(off):
                if cases[i] not in taken and off[i] < 0.05:
                    out[name] = cases[i]
                    taken.add(cases[i])
                    break
        return out

    def mesh(self, i):
        m = self.m
        va, nv, fa, nf = m.mesh_vertadr[i], m.mesh_vertnum[i], m.mesh_faceadr[i], m.mesh_facenum[i]
        v = m.mesh_vert[va:va + nv].astype(np.float32)
        f = m.mesh_face[fa:fa + nf].astype(np.uint32)
        return struct.pack("<II", nv, nf) + v.tobytes() + f.tobytes()

    def poses(self, values, names):
        """Body poses [x y z qw qx qy qz] from a frame; joints the frame lacks stay at 0."""
        m, d = self.m, self.d
        d.qpos[:] = m.qpos0
        for field in self.joint_fields:
            for name, v in zip(names.get(field, []), values.get(field, [])):
                j = self.joints.get(name)
                if j is not None and not math.isnan(v):
                    d.qpos[m.jnt_qposadr[j]] = v
        if self.free is not None:
            a = m.jnt_qposadr[self.free]
            d.qpos[a:a + 3] = [0, 0, self.height]
            q = values.get(self.quat_field)
            if q and not any(math.isnan(x) for x in q) and sum(x * x for x in q) > 0.5:
                d.qpos[a + 3:a + 7] = q
        mujoco.mj_kinematics(m, d)
        return np.hstack([d.xpos[self.bodies], d.xquat[self.bodies]]).round(5).ravel().tolist()


# ---------------------------------------------------------------------------------------------------- robot link
class RobotLink(asyncio.DatagramProtocol):
    def __init__(self, hub):
        self.hub, self.transport = hub, None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        if data[:4] == MAGIC:
            self.hub.frame(data)
            return
        try:
            msg = json.loads(data)
        except ValueError:
            return
        self.hub.message(msg, data)

    def send(self, msg):
        if self.transport:
            self.transport.sendto(json.dumps(msg).encode())


class Hub:
    """Latest robot state, browsers, recording."""

    def __init__(self, model):
        self.model = model
        self.schema = None
        self.names, self.unpack, self.schema_id = {}, None, None
        self.values, self.robot_t, self.seq, self.rx_time = {}, 0.0, 0, 0.0
        self.new = False
        self.rates = []
        self.browsers = set()
        self.link = None
        self.cmd_seq = 0
        self.recording = None
        self.events = []

    # robot -> PC
    def message(self, msg, raw=b""):
        op = msg.get("op")
        if op == "schema":
            # the frames carry the CRC of the schema they follow (the robot computes it on the same bytes): every
            # schema received sets it again, so a restarted robot is followed even with the same fields
            self.schema_id = zlib.crc32(raw)
            if msg != self.schema:
                self.schema = msg
                self.names = {name: labels for name, labels in msg["fields"]}
                n = sum(len(labels) for _, labels in msg["fields"])
                self.unpack = struct.Struct(f"<{n}f").unpack_from
                self.broadcast({"type": "schema", "schema": msg})
        elif op in ("ack", "event"):
            msg = {**msg, "type": op, "pc_time": time.time()}
            self.events = (self.events + [msg])[-200:]
            self.broadcast(msg)

    def frame(self, data):
        if self.unpack is None:
            return
        magic, sid, seq, t = HEADER.unpack_from(data)
        if sid != self.schema_id:          # frames of another schema (the robot restarted): wait for its schema
            return
        flat = self.unpack(data, HEADER.size)
        vals, k = {}, 0
        for name, labels in self.schema["fields"]:
            vals[name] = list(flat[k:k + len(labels)])
            k += len(labels)
        now = time.time()
        self.rates = [x for x in self.rates if now - x < 1.0] + [now]
        self.values, self.robot_t, self.seq, self.rx_time, self.new = vals, t, seq, now, True
        if self.recording is not None:
            self.recording["t"].append(t)
            self.recording["frames"].append(flat)

    # PC -> robot
    def command(self, name, args):
        self.cmd_seq += 1
        self.link.send({"op": "cmd", "seq": self.cmd_seq, "name": name, "args": args})
        return self.cmd_seq

    # browsers
    def broadcast(self, msg):
        data = json.dumps(msg)
        for ws in list(self.browsers):
            asyncio.ensure_future(self._send(ws, data))

    async def _send(self, ws, data):
        try:
            await ws.send_str(data)
        except (ConnectionError, RuntimeError):
            self.browsers.discard(ws)

    def start_recording(self):
        self.recording = {"t": [], "frames": [], "schema": self.schema, "start": time.strftime("%Y%m%d_%H%M%S")}

    def stop_recording(self, folder):
        rec, self.recording = self.recording, None
        if not rec or not rec["frames"]:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        out = folder / f"{(rec['schema'] or {}).get('robot', 'robot')}_{rec['start']}.npz"
        frames = np.asarray(rec["frames"], np.float32)
        arrays, k = {"t": np.asarray(rec["t"])}, 0
        for name, labels in rec["schema"]["fields"]:
            arrays[name] = frames[:, k:k + len(labels)]
            k += len(labels)
        np.savez_compressed(out, schema=json.dumps(rec["schema"]), **arrays)
        return out


# ---------------------------------------------------------------------------------------------------- web server
def make_app(hub, model, title, rec_dir):
    app = web.Application()
    scene = model.scene()

    async def index(request):
        return web.FileResponse(WEB / "index.html")

    async def api_scene(request):
        return web.json_response({**scene, "title": title})

    async def api_mesh(request):
        return web.Response(body=model.mesh(int(request.match_info["i"])), content_type="application/octet-stream")

    async def ws_handler(request):
        ws = web.WebSocketResponse(heartbeat=10)
        await ws.prepare(request)
        hub.browsers.add(ws)
        if hub.schema:
            await ws.send_str(json.dumps({"type": "schema", "schema": hub.schema}))
        for e in hub.events[-50:]:
            await ws.send_str(json.dumps(e))
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            req = json.loads(msg.data)
            if req.get("type") == "cmd":
                hub.command(req["name"], req.get("args") or {})
            elif req.get("type") == "record":
                if req.get("on"):
                    hub.start_recording()
                    hub.broadcast({"type": "recording", "on": True})
                else:
                    out = hub.stop_recording(rec_dir)
                    hub.broadcast({"type": "recording", "on": False, "file": str(out) if out else None})
        hub.browsers.discard(ws)
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/api/scene", api_scene)
    app.router.add_get("/api/mesh/{i}", api_mesh)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", WEB)
    return app


async def pusher(hub, model):
    """Frames to the browsers at PUSH_HZ at most, with the 3D poses (only the latest frame: nothing piles up)."""
    while True:
        await asyncio.sleep(1 / PUSH_HZ)
        if hub.browsers and (hub.new or hub.rx_time):
            msg = {"type": "frame", "seq": hub.seq, "robot_t": hub.robot_t, "age": time.time() - hub.rx_time,
                   "rate": len(hub.rates), "recording": hub.recording is not None}
            if hub.new:
                msg["values"] = {k: [None if math.isnan(x) else round(x, 5) for x in v] for k, v in hub.values.items()}
                msg["poses"] = model.poses(hub.values, hub.names)
                hub.new = False
            hub.broadcast(msg)


async def hello(hub):
    while True:
        hub.link.send({"op": "hello"})
        await asyncio.sleep(1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robot", required=True, help="robot host or IP (its link port: --port)")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--model", required=True, help="MuJoCo XML or URDF of the robot")
    ap.add_argument("--title", default=None)
    ap.add_argument("--motor-mesh", default="xl330", help="name part of the servo meshes (lit on a motor error)")
    ap.add_argument("--visual-groups", type=int, nargs="*", default=None,
                    help="geom groups to draw (default: the geoms that do not collide)")
    ap.add_argument("--http", type=int, default=8780)
    ap.add_argument("--recordings", default="recordings", help="folder of the recordings (npz)")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    model = Model(a.model, a.visual_groups, motor_mesh=a.motor_mesh)
    hub = Hub(model)

    async def run():
        loop = asyncio.get_running_loop()
        _, hub.link = await loop.create_datagram_endpoint(lambda: RobotLink(hub), remote_addr=(a.robot, a.port))
        app = make_app(hub, model, a.title or pathlib.Path(a.model).stem, pathlib.Path(a.recordings))
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, "127.0.0.1", a.http).start()
        url = f"http://127.0.0.1:{a.http}"
        print(f"{url}  (robot {a.robot}:{a.port}; Ctrl+C to stop)")
        if not a.no_browser:
            webbrowser.open(url)
        await asyncio.gather(hello(hub), pusher(hub, model))

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
