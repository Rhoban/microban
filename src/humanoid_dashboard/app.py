"""PC side of the dashboard: receives the robot's telemetry (humanoid_dashboard.link), computes the 3D pose of the robot
model with MuJoCo (forward kinematics from the joint angles and the trunk orientation), and serves a web page (three.js)
with the motors, the IMU, plots, the robot's events and its commands (reboot a motor, torque on/off). Records frames and replays them (any speed, frame
by frame, back and forth: the page asks for one frame at a time, its 3D pose computed here).

    python -m humanoid_dashboard.app --model path/to/robot.xml [--robot HOST] [--http 8780]
    python -m humanoid_dashboard.app --model Classic=robot.xml --model Climber=robot_climb.xml [--robot HOST]

The robot (host name or IP) can also be chosen, or changed, in the page; without --robot the page opens on its robot
picker. With several models (NAME=PATH), the page picks one per robot too, saved with the robot's name.

The model is a MuJoCo XML or a URDF; joint fields of the telemetry are matched to the model's joints by name.
"""
import argparse
import asyncio
import json
import math
import os
import pathlib
import socket
import struct
import time
import webbrowser
import zlib

import mujoco
import numpy as np
from aiohttp import web, WSMsgType

from .link import HEADER, MAGIC, PORT

WEB = pathlib.Path(__file__).parent / "web"
PUSH_HZ = 50                       # to the page, as the robot's telemetry (the latest frame only: nothing piles up)
ROBOTS_FILE = pathlib.Path.home() / ".config" / "humanoid_dashboard" / "robots.json"    # name -> {host, model}


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
        if getattr(self, "_scene", None) is None:
            self._scene = self._make_scene()
        return self._scene

    def _make_scene(self):
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
        if self.hub.robot_addr is None or addr[0] != self.hub.robot_addr[0]:    # an earlier robot still sending
            return
        if data[:4] == MAGIC:
            self.hub.frame(data)
            return
        try:
            msg = json.loads(data)
        except ValueError:
            return
        self.hub.message(msg, data)

    def send(self, msg):
        if self.transport and self.hub.robot_addr:
            self.transport.sendto(json.dumps(msg).encode(), self.hub.robot_addr)


def saved_robots() -> dict:
    """name -> {"host", "model"} (model: the version shown for it, None: as the robot says; a file of an older
    dashboard: name -> host)."""
    try:
        robots = json.loads(ROBOTS_FILE.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(robots, dict):
        return {}
    return {str(k): ({"host": v, "model": None} if isinstance(v, str) else
                     {"host": str(v.get("host", "")), "model": v.get("model")})
            for k, v in robots.items() if isinstance(v, (str, dict))}


def save_robots(robots: dict) -> None:
    ROBOTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROBOTS_FILE.write_text(json.dumps(robots, indent=1, sort_keys=True))


class Models:
    """The robot's models by name (e.g. Classic, Climber), loaded when first shown."""

    def __init__(self, paths: dict, visual_groups=None, motor_mesh="xl330"):
        self.paths, self.loaded = paths, {}
        self.visual_groups, self.motor_mesh = visual_groups, motor_mesh

    def get(self, name) -> Model:
        if name not in self.loaded:
            self.loaded[name] = Model(self.paths[name], self.visual_groups, motor_mesh=self.motor_mesh)
        return self.loaded[name]


class Hub:
    """Latest robot state, browsers, recording."""

    def __init__(self, models: Models, model_name: str):
        self.models, self.model_name = models, model_name
        self.model = models.get(model_name)
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
        self.robot_host, self.robot_addr = None, None
        self.deploy_cmd, self.deploy_dir, self.deploying = None, None, False
        self.rec_dir = pathlib.Path("recordings")

    async def connect(self, host, port, model=None):
        """Talk to another robot (host name or IP), shown with that model (a name of --model; None: the current one):
        the page starts over with its schema (and reloads for another model)."""
        try:
            info = await asyncio.get_running_loop().getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_DGRAM)
        except OSError as e:
            return f"{host}: {e}"
        if model in self.models.paths and model != self.model_name:
            self.model_name, self.model = model, await asyncio.to_thread(self.models.get, model)
        self.robot_host, self.robot_addr = host, info[0][4]
        self.schema, self.names, self.unpack, self.schema_id = None, {}, None, None
        self.values, self.robot_t, self.seq, self.rx_time, self.new, self.rates = {}, 0.0, 0, 0.0, False, []
        self.end_recording("another robot")
        self.events = []
        self.broadcast(self.robot_msg())
        self.link.send({"op": "hello"})
        return None

    def robot_msg(self):
        return {"type": "robot", "host": self.robot_host, "addr": self.robot_addr[0] if self.robot_addr else None,
                "saved": saved_robots(), "deploy": bool(self.deploy_cmd), "deploying": self.deploying,
                "model": self.model_name, "models": list(self.models.paths)}

    def event(self, text, level="info"):
        msg = {"type": "event", "level": level, "text": text, "pc_time": time.time()}
        self.events = (self.events + [msg])[-200:]
        self.broadcast(msg)

    async def deploy(self):
        """The page's Deploy button: runs --deploy's command (e.g. make deploy HOST={host}) for the robot shown, its
        output in the page's events. The robot restarts its program, so the page shows its new moves by itself."""
        if self.deploying or not self.deploy_cmd or not self.robot_host:
            return
        self.deploying = True
        self.broadcast(self.robot_msg())
        cmd = self.deploy_cmd.format(host=self.robot_host)
        self.event(f"deploy: {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd, cwd=self.deploy_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL, env={**os.environ, "SSH_ASKPASS_REQUIRE": "never"},
                start_new_session=True)                   # no terminal: SSH cannot ask a password
            async for line in proc.stdout:
                line = line.decode(errors="replace").rstrip()
                if line and not line.startswith(("sending incremental", "sent ", "total size")):
                    self.event(f"deploy: {line}")
            ok = await proc.wait() == 0
            self.event("deploy: done, the robot's program restarts with your code (a few seconds)" if ok else
                       "deploy: FAILED (above). SSH needs your key on the robot: ssh-copy-id <user>@<robot>",
                       "info" if ok else "error")
        finally:
            self.deploying = False
            self.broadcast(self.robot_msg())


    # robot -> PC
    def message(self, msg, raw=b""):
        op = msg.get("op")
        if op == "schema":
            # the frames carry the CRC of the schema they follow (the robot computes it on the same bytes): every
            # schema received sets it again, so a restarted robot is followed even with the same fields
            self.schema_id = zlib.crc32(raw)
            if msg != self.schema:
                if self.recording is not None and self.schema is not None:
                    self.end_recording("the robot restarted with other fields", restart=True)
                self.schema = msg
                self.names = {name: labels for name, labels in msg["fields"]}
                n = sum(len(labels) for _, labels in msg["fields"])
                self.unpack = struct.Struct(f"<{n}f").unpack_from
                self.broadcast({"type": "schema", "schema": msg})
            self.follow_variant(msg.get("meta") or {})
        elif op in ("ack", "event"):
            msg = {**msg, "type": op, "pc_time": time.time()}
            self.events = (self.events + [msg])[-200:]
            self.broadcast(msg)

    def follow_variant(self, meta):
        """A robot that knows its version (meta.variant, e.g. Microban's classic / climber; the page changes it with
        the command variant): the model of that name is shown (the page reloads its 3D view)."""
        v = meta.get("variant")
        if not v:
            return
        name = next((n for n in self.models.paths if n.lower() == v), None)
        if name and name != self.model_name:
            self.model_name, self.model = name, self.models.get(name)
            self.broadcast(self.robot_msg())

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

    def end_recording(self, why, restart=False):
        """A recording in progress is saved before the robot or its fields change (one schema per file); restart: a
        new recording goes on after it."""
        if self.recording is None:
            return
        out = self.stop_recording(self.rec_dir)
        self.broadcast({"type": "recording", "on": False, "file": str(out) if out else None})
        self.event(f"recording saved ({why})" + (": a new one goes on" if restart else ""))
        if restart:
            self.start_recording()
            self.broadcast({"type": "recording", "on": True})

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


class Recording:
    """A saved recording (Hub.stop_recording), for the replay: its plots' series at once, then frame by frame."""

    def __init__(self, path):
        with np.load(path, allow_pickle=False) as z:
            self.schema = json.loads(str(z["schema"]))
            self.arrays = {k: z[k] for k in z.files if k != "schema"}
        self.t = self.arrays["t"]
        self.names = {name: labels for name, labels in self.schema["fields"]}

    def __len__(self):
        return len(self.t)

    def values(self, i):
        return {name: [None if math.isnan(x) else round(float(x), 5) for x in self.arrays[name][i]]
                for name in self.names if name in self.arrays}

    def series(self):
        """What the page plots, for every frame: time, total current, trunk orientation, joint angles and targets."""
        def col(name):
            a = self.arrays.get(name)
            return None if a is None else np.where(np.isnan(a), None, a.round(5).astype(object)).tolist()
        cur = self.arrays.get("current")
        return {"schema": self.schema, "t": self.t.round(4).tolist(), "n": len(self),
                "cur": None if cur is None else np.nansum(np.abs(cur), axis=1).round(4).tolist(),
                "imu_quat": col("imu_quat"), "q": col("q"), "q_target": col("q_target")}


# ---------------------------------------------------------------------------------------------------- web server
@web.middleware
async def no_cache(request, handler):
    """The page and its scripts are revalidated at each load: an updated dashboard is never shown from a stale cache."""
    response = await handler(request)
    response.headers["Cache-Control"] = "no-cache"
    return response


def same_page_only(http_port):
    """Only this dashboard's own page may use it. The server listens on 127.0.0.1 only, but a browser lets any web
    page open a WebSocket to localhost, and a site whose name points to 127.0.0.1 (DNS rebinding) could load ours:
    the Host header must be this server, and a browser's Origin must be this page. A local program without Origin
    (a test script) is accepted: it can reach the robot anyway."""
    hosts = {f"127.0.0.1:{http_port}", f"localhost:{http_port}"}
    origins = {f"http://{h}" for h in hosts}

    @web.middleware
    async def check(request, handler):
        origin = request.headers.get("Origin")
        if request.host not in hosts or (origin is not None and origin not in origins):
            print(f"refused a request from {origin or request.host} (only this dashboard's page may use it)")
            raise web.HTTPForbidden(text="only the dashboard's own page may use this server")
        return await handler(request)
    return check


def make_app(hub, title, rec_dir, port=PORT, http_port=8780):
    app = web.Application(middlewares=[same_page_only(http_port), no_cache])

    async def index(request):
        return web.FileResponse(WEB / "index.html")

    async def api_scene(request):                     # the model shown now (the page reloads when it changes)
        return web.json_response({**hub.model.scene(), "title": title, "model": hub.model_name})

    async def api_mesh(request):
        return web.Response(body=hub.model.mesh(int(request.match_info["i"])), content_type="application/octet-stream")

    loaded = {}                                       # file name -> Recording (the last few replayed)

    def recording(name):
        path = rec_dir / pathlib.Path(name).name       # only the recordings folder
        if path.suffix != ".npz" or not path.is_file():
            raise web.HTTPNotFound(text=f"no recording {name}")
        if name not in loaded:
            while len(loaded) >= 3:
                loaded.pop(next(iter(loaded)))
            loaded[name] = Recording(path)
        return loaded[name]

    async def api_recordings(request):
        files = sorted(rec_dir.glob("*.npz"), key=lambda f: f.stat().st_mtime, reverse=True) if rec_dir.is_dir() else []
        return web.json_response([{"file": f.name, "size": f.stat().st_size} for f in files])

    async def api_replay(request):
        return web.json_response(recording(request.match_info["file"]).series())

    async def ws_handler(request):
        ws = web.WebSocketResponse(heartbeat=10)
        await ws.prepare(request)
        hub.browsers.add(ws)
        await ws.send_str(json.dumps(hub.robot_msg()))
        if hub.schema:
            await ws.send_str(json.dumps({"type": "schema", "schema": hub.schema}))
        for e in hub.events[-50:]:
            await ws.send_str(json.dumps(e))
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            req = json.loads(msg.data)
            if req.get("type") == "connect":
                err = await hub.connect(str(req.get("host", "")).strip(), port, req.get("model"))
                if err:
                    await ws.send_str(json.dumps({"type": "event", "level": "error", "text": f"connect {err}",
                                                  "pc_time": time.time()}))
            elif req.get("type") in ("save_robot", "forget_robot"):     # the page's saved robots: name -> host, model
                robots, name = saved_robots(), str(req.get("name", "")).strip()[:40]
                host = str(req.get("host", "")).strip()
                if req["type"] == "save_robot":
                    if not (name and host):
                        continue
                    robots[name] = {"host": host}
                else:
                    robots.pop(name, None)
                save_robots(robots)
                hub.broadcast(hub.robot_msg())
            elif req.get("type") == "deploy":
                asyncio.ensure_future(hub.deploy())
            elif req.get("type") == "cmd":
                hub.command(req["name"], req.get("args") or {})
            elif req.get("type") == "record":
                if req.get("on"):
                    hub.start_recording()
                    hub.broadcast({"type": "recording", "on": True})
                else:
                    out = hub.stop_recording(rec_dir)
                    hub.broadcast({"type": "recording", "on": False, "file": str(out) if out else None})
            elif req.get("type") == "replay_frame":           # one frame of a recording, to this page only
                try:
                    rec = recording(req["file"])
                except web.HTTPNotFound:
                    continue
                i = max(0, min(len(rec) - 1, int(req["i"])))
                values = rec.values(i)
                await ws.send_str(json.dumps({"type": "replay_frame", "file": req["file"], "i": i,
                                              "robot_t": float(rec.t[i]), "values": values,
                                              "poses": hub.model.poses({k: rec.arrays[k][i].tolist() for k in values},
                                                                   rec.names)}))
        hub.browsers.discard(ws)
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/api/scene", api_scene)
    app.router.add_get("/api/mesh/{i}", api_mesh)
    app.router.add_get("/api/recordings", api_recordings)
    app.router.add_get("/api/replay/{file}", api_replay)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static", WEB)
    return app


async def pusher(hub):
    """Frames to the browsers at PUSH_HZ at most, with the 3D poses (only the latest frame: nothing piles up)."""
    while True:
        await asyncio.sleep(1 / PUSH_HZ)
        if hub.browsers and (hub.new or hub.rx_time):
            msg = {"type": "frame", "seq": hub.seq, "robot_t": hub.robot_t, "age": time.time() - hub.rx_time,
                   "rate": len(hub.rates), "recording": hub.recording is not None}
            if hub.new:
                msg["values"] = {k: [None if math.isnan(x) else round(x, 5) for x in v] for k, v in hub.values.items()}
                msg["poses"] = hub.model.poses(hub.values, hub.names)
                hub.new = False
            hub.broadcast(msg)


async def hello(hub):
    while True:
        hub.link.send({"op": "hello"})
        await asyncio.sleep(1.0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--robot", default=None, help="robot host or IP (its link port: --port); else chosen in the page")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--model", required=True, action="append", metavar="[NAME=]PATH",
                    help="MuJoCo XML or URDF of the robot; repeat with names (Classic=robot.xml Climber=robot_climb.xml) "
                         "for a robot with several versions: chosen per robot in the page")
    ap.add_argument("--model-name", default=None, help="the model shown first (default: the first --model)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--motor-mesh", default="xl330", help="name part of the servo meshes (lit on a motor error)")
    ap.add_argument("--visual-groups", type=int, nargs="*", default=None,
                    help="geom groups to draw (default: the geoms that do not collide)")
    ap.add_argument("--http", type=int, default=8780)
    ap.add_argument("--recordings", default="recordings", help="folder of the recordings (npz)")
    ap.add_argument("--deploy", default=None, metavar="CMD",
                    help="the page's Deploy button runs this command for the robot shown ({host}), from the current "
                         "folder (Microban: make deploy HOST=radxa@{host}); no button without it")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    paths = dict(m.split("=", 1) if "=" in m else (pathlib.Path(m).stem, m) for m in a.model)
    first = a.model_name if a.model_name in paths else next(iter(paths))
    hub = Hub(Models(paths, a.visual_groups, a.motor_mesh), first)
    hub.deploy_cmd, hub.deploy_dir = a.deploy, os.getcwd()

    async def run():
        loop = asyncio.get_running_loop()
        _, hub.link = await loop.create_datagram_endpoint(lambda: RobotLink(hub), local_addr=("0.0.0.0", 0))
        if a.robot:
            saved = next((r for r in saved_robots().values() if r["host"] == a.robot), None)   # its saved model
            err = await hub.connect(a.robot, a.port, None if a.model_name else (saved or {}).get("model"))
            if err:
                print(f"robot {a.robot} not found ({err.split(': ', 1)[-1]}): check its name (microban-XXXX.local, "
                      f"XXXX: the end of its wifi MAC address) or choose it in the page")
        hub.rec_dir = pathlib.Path(a.recordings)
        app = make_app(hub, a.title or pathlib.Path(paths[first]).stem, hub.rec_dir, a.port, a.http)
        runner = web.AppRunner(app)
        await runner.setup()
        try:
            await web.TCPSite(runner, "127.0.0.1", a.http).start()
        except OSError:
            raise SystemExit(f"Port {a.http} is taken: a dashboard is probably running already (open "
                             f"http://127.0.0.1:{a.http}, or stop it), or choose another port with --http")
        url = f"http://127.0.0.1:{a.http}"
        print(f"{url}  (robot {a.robot or 'chosen in the page'}, port {a.port}; Ctrl+C to stop)")
        if not a.no_browser:
            webbrowser.open(url)
        await asyncio.gather(hello(hub), pusher(hub))

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
