// Robot dashboard page: 3D robot (three.js, poses computed by the PC server), motors, plots, events, commands.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const DEG = 180 / Math.PI, HISTORY_S = 10;
let scene3d = null, schema = null, names = {}, meta = {}, last = null, selected = null, recording = false;
const hist = [];                      // [{t, cur, sel: [q, target], roll, pitch}]

// ------------------------------------------------------------------------------------------------ 3D view
async function build3d() {
  const sc = await (await fetch("/api/scene")).json();
  if (!schema) { $("title").textContent = sc.title; document.title = sc.title + " · dashboard"; }
  const el = $("view");
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(window.devicePixelRatio);
  el.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 50);
  camera.up.set(0, 0, 1);
  camera.position.set(0.9, -1.1, 0.6);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0, 0.18);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x888888, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6); sun.position.set(1, -1.5, 2.5); scene.add(sun);
  const grid = new THREE.GridHelper(2, 40); grid.rotation.x = Math.PI / 2; scene.add(grid);

  const bodies = sc.bodies.map(() => { const g = new THREE.Group(); scene.add(g); return g; });
  let framed = false;
  const mats = sc.bodies.map(() => []);
  const meshCache = {};
  async function meshGeometry(i) {
    if (!meshCache[i]) meshCache[i] = (async () => {
      const buf = await (await fetch(`/api/mesh/${i}`)).arrayBuffer();
      const [nv, nf] = new Uint32Array(buf, 0, 2);
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(buf, 8, nv * 3), 3));
      g.setIndex(new THREE.BufferAttribute(new Uint32Array(buf, 8 + nv * 12, nf * 3), 1));
      g.computeVertexNormals();
      return g;
    })();
    return meshCache[i];
  }
  const geomMats = [];
  const geoms = await Promise.all(sc.geoms.map(async (gm, gi) => {
    let geo, s = gm.size;
    if (gm.type === 7) geo = await meshGeometry(gm.mesh);
    else if (gm.type === 6) geo = new THREE.BoxGeometry(2 * s[0], 2 * s[1], 2 * s[2]);
    else if (gm.type === 2) geo = new THREE.SphereGeometry(s[0], 24, 16);
    else if (gm.type === 5) { geo = new THREE.CylinderGeometry(s[0], s[0], 2 * s[1], 24); geo.rotateX(Math.PI / 2); }
    else if (gm.type === 3) { geo = new THREE.CapsuleGeometry(s[0], 2 * s[1], 8, 16); geo.rotateX(Math.PI / 2); }
    else return null;
    const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(gm.rgba[0], gm.rgba[1], gm.rgba[2]),
      transparent: gm.rgba[3] < 1, opacity: gm.rgba[3], roughness: 0.65, metalness: 0.05 });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(...gm.pos);
    mesh.quaternion.set(gm.quat[1], gm.quat[2], gm.quat[3], gm.quat[0]);
    mesh.userData.body = gm.body; mesh.userData.geom = gi;
    bodies[gm.body].add(mesh); mats[gm.body].push(mat); geomMats[gi] = mat;
    return mesh;
  }));
  const pickable = geoms.filter(Boolean);
  const bodyJoint = {}, motorJoint = {};
  for (const [j, b] of Object.entries(sc.joint_body)) bodyJoint[b] = j;
  for (const [j, g] of Object.entries(sc.joint_motor || {})) motorJoint[g] = j;

  function resize() {
    const w = el.clientWidth, h = el.clientHeight;
    renderer.setSize(w, h, false); camera.aspect = w / Math.max(h, 1); camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(el); resize();
  const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
  let down = null;
  renderer.domElement.addEventListener("pointerdown", e => down = [e.clientX, e.clientY]);
  renderer.domElement.addEventListener("pointerup", e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    const r = renderer.domElement.getBoundingClientRect();
    mouse.set((e.clientX - r.left) / r.width * 2 - 1, -(e.clientY - r.top) / r.height * 2 + 1);
    ray.setFromCamera(mouse, camera);
    const hit = ray.intersectObjects(pickable, false)[0];
    const j = hit && (motorJoint[hit.object.userData.geom] || bodyJoint[hit.object.userData.body]);
    if (j) select(j);
  });
  (function loop() { requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); })();
  function theme() { scene.background = new THREE.Color(css("--scene")); }
  theme(); matchMedia("(prefers-color-scheme: dark)").addEventListener("change", theme);
  return {
    jointBody: sc.joint_body,
    pose(p) {
      for (let i = 0; i < bodies.length; i++) {
        const k = 7 * i; bodies[i].position.set(p[k], p[k + 1], p[k + 2]);
        bodies[i].quaternion.set(p[k + 4], p[k + 5], p[k + 6], p[k + 3]);
      }
      if (!framed) {             // first pose: look at the whole robot
        framed = true;
        const box = new THREE.Box3(); bodies.forEach(b => box.expandByObject(b));
        const c = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3()).length();
        controls.target.copy(c);
        camera.position.copy(c).add(new THREE.Vector3(0.75, -1.0, 0.45).normalize().multiplyScalar(1.9 * size));
        camera.near = size / 100; camera.far = size * 100; camera.updateProjectionMatrix();
      }
    },
    tint(state) {   // joint -> "bad" | "warn" | "sel" | null : its servo glows (or the part it moves, without one)
      const col = { bad: 0xc63b2f, warn: 0xc27a12, sel: 0xd9622b };
      const want = new Map();
      for (const [j, s] of Object.entries(state)) {
        if (!s) continue;
        const g = (sc.joint_motor || {})[j];
        if (g !== undefined) want.set(geomMats[g], col[s]);
        else if (sc.joint_body[j] !== undefined) mats[sc.joint_body[j]].forEach(m => want.set(m, col[s]));
      }
      geomMats.forEach(m => { if (m) { const c = want.get(m); m.emissive.setHex(c || 0); m.emissiveIntensity = c ? 0.9 : 0; } });
    },
  };
}

// ------------------------------------------------------------------------------------------------ motors
const errBits = v => {
  const bits = meta.hw_error_bits || {}, ignore = meta.hw_error_ignore || 0;
  const out = [];
  for (const [b, n] of Object.entries(bits)) if ((v & ~ignore) & (1 << +b)) out.push(n);
  return out;
};
function jointsList() { return names.q || names.current || []; }
function val(field, j) { const i = (names[field] || []).indexOf(j); return i < 0 || !last || !last.values ? null : last.values[field][i]; }
function motorState(j) {
  const e = val("hw_error", j), t = val("temperature", j), tq = val("torque", j);
  const lim = (meta.limits || {});
  if (e !== null && errBits(e).length) return "bad";
  if (t !== null && lim.temperature && t >= lim.temperature - 10) return "warn";
  return null;                  // torque off: shown in the table, not in 3D (often every motor at once)
}
const confirmKey = {};
function button(label, cls, onClick, confirmText) {
  const b = document.createElement("button"); b.className = "small " + (cls || ""); b.textContent = label;
  b.onclick = ev => {
    ev.stopPropagation();
    if (confirmText && confirmKey[label + b.dataset.j] !== true) {
      confirmKey[label + b.dataset.j] = true; b.textContent = confirmText; b.classList.add("confirm");
      setTimeout(() => { confirmKey[label + b.dataset.j] = false; renderTable(true); robotCmdsKey = ""; renderRobotCmds(); movesKey = ""; renderMoves(); }, 3000);
      return;
    }
    confirmKey[label + b.dataset.j] = false; onClick();
  };
  return b;
}
function cmd(name, args) { send({ type: "cmd", name, args }); log({ level: "info", text: `→ ${name} ${JSON.stringify(args)}` }); }
let tableKey = "";
function renderTable(force) {
  const js = jointsList(), t = $("table");
  $("empty").style.display = js.length ? "none" : "";
  if (!js.length) return;
  const ids = meta.motor_ids || {};
  const order = [...js].sort((a, b) => (ids[a] ?? 999) - (ids[b] ?? 999));
  const key = order.join() + JSON.stringify(Object.values(confirmKey));
  if (force || key !== tableKey) {
    tableKey = key; t.innerHTML = "";
    const h = t.createTHead().insertRow();
    for (const c of ["ID", "Joint", "Angle °", "Err °", "Current A", "°C", "State", ""]) { const th = document.createElement("th"); th.textContent = c; h.appendChild(th); }
    const body = t.createTBody();
    for (const j of order) {
      const r = body.insertRow(); r.dataset.j = j; r.onclick = () => select(j);
      for (let i = 0; i < 8; i++) r.insertCell();
      r.cells[0].textContent = ids[j] ?? ""; r.cells[1].textContent = j;
      r.cells[2].className = r.cells[3].className = r.cells[5].className = "num";
      r.cells[4].innerHTML = `<span class="bar"><i></i></span> <span class="cv"></span>`;
    }
  }
  const lim = meta.limits || {}, cmds = meta.commands || [];
  for (const r of t.tBodies[0].rows) {
    const j = r.dataset.j, q = val("q", j), qt = val("q_target", j), c = val("current", j), T = val("temperature", j);
    const e = val("hw_error", j), tq = val("torque", j), bad = e !== null ? errBits(e) : [];
    r.className = (j === selected ? "sel " : "") + (bad.length ? "err" : "");
    r.cells[2].textContent = q === null ? "–" : (q * DEG).toFixed(1);
    r.cells[3].textContent = q === null || qt === null ? "–" : ((qt - q) * DEG).toFixed(1);
    const frac = c === null || !lim.current ? 0 : Math.min(1, Math.abs(c) / lim.current);
    const bar = r.cells[4].querySelector("i"); bar.style.width = (100 * frac) + "%"; bar.className = frac > 0.8 ? "bad" : frac > 0.5 ? "warn" : "";
    r.cells[4].querySelector(".cv").textContent = c === null ? "–" : Math.abs(c).toFixed(2);
    r.cells[5].textContent = T === null ? "–" : T.toFixed(0);
    r.cells[5].className = "num " + (T !== null && lim.temperature ? (T >= lim.temperature - 5 ? "vhot" : T >= lim.temperature - 15 ? "hot" : "") : "");
    const st = bad.length ? `<span class="st bad">${bad.join(", ")}</span>` : tq === 0 ? `<span class="st warn">torque off</span>` : `<span class="st muted">ok</span>`;
    if (r.cells[6].innerHTML !== st) r.cells[6].innerHTML = st;
    const show = j === selected || bad.length || tq === 0;     // buttons only where they are wanted: keeps the table narrow
    const want = !show ? "" : (cmds.includes("reboot") && (bad.length || j === selected) ? "R" : "") + (cmds.includes("torque") ? (tq === 0 ? "T1" : tq === 1 ? "T0" : "") : "");
    if (r.cells[7].dataset.want !== want || force) {
      r.cells[7].dataset.want = want; r.cells[7].innerHTML = "";
      if (want.includes("R")) { const b = button("Reboot", "danger", () => cmd("reboot", { joint: j }), "Confirm reboot"); b.dataset.j = j; r.cells[7].appendChild(b); }
      if (want.includes("T1")) {
        const b = button("Torque on", "", () => cmd("torque", { joint: j, on: true }), "It will move: sure?"); b.dataset.j = j; r.cells[7].appendChild(b);
      } else if (want.includes("T0")) {
        const b = button("Torque off", "", () => cmd("torque", { joint: j, on: false }), "Goes limp: sure?"); b.dataset.j = j; r.cells[7].appendChild(b);
      }
    }
  }
  const nbad = order.filter(j => motorState(j) === "bad").length, noff = order.filter(j => val("torque", j) === 0).length;
  $("summary").innerHTML = `${order.length} motors` + (nbad ? ` · <b style="color:var(--bad)">${nbad} in error</b>` : "") + (noff ? ` · ${noff} torque off` : "");
}
function select(j) {
  selected = selected === j ? null : j;
  $("p_sel_title").firstChild.textContent = selected ? `${selected} ` : "Motor ";
  for (const h of hist) h.sel = null;
  renderTable();
}

// ------------------------------------------------------------------------------------------------ plots
function quatRollPitch(q) {
  if (!q || q.some(x => x === null)) return [null, null];
  const [w, x, y, z] = q;
  return [Math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y)) * DEG, Math.asin(Math.max(-1, Math.min(1, 2 * (w * y - z * x)))) * DEG];
}
function plot(id, series) {   // series: [{get: h => number|null, color}]
  const c = $(id), r = c.getBoundingClientRect(), dpr = devicePixelRatio;
  if (c.width !== Math.round(r.width * dpr) || c.height !== Math.round(r.height * dpr)) { c.width = r.width * dpr; c.height = r.height * dpr; }
  const x = c.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0); x.clearRect(0, 0, r.width, r.height);
  if (hist.length < 2) return;
  const t1 = hist[hist.length - 1].t, t0 = t1 - HISTORY_S;
  let lo = Infinity, hi = -Infinity;
  for (const h of hist) for (const s of series) { const v = s.get(h); if (v !== null && v !== undefined && isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }
  if (!isFinite(lo)) return;
  if (hi - lo < 1e-3) { hi += 0.5; lo -= 0.5; }
  const pad = (hi - lo) * 0.1; lo -= pad; hi += pad;
  const L = 38, W = r.width - L - 6, H = r.height - 16;
  x.font = "11px system-ui"; x.fillStyle = css("--muted"); x.strokeStyle = css("--grid"); x.lineWidth = 1;
  for (let k = 0; k <= 3; k++) {
    const v = lo + (hi - lo) * k / 3, y = 6 + H - H * k / 3;
    const dec = Math.max(0, Math.min(3, Math.ceil(-Math.log10((hi - lo) / 3)) + 1));
    x.beginPath(); x.moveTo(L, y); x.lineTo(L + W, y); x.stroke(); x.fillText(v.toFixed(dec), 2, y + 4);
  }
  for (const s of series) {
    x.strokeStyle = s.color; x.lineWidth = 1.8; x.beginPath(); let pen = false;
    for (const h of hist) {
      const v = s.get(h); if (v === null || v === undefined || !isFinite(v)) { pen = false; continue; }
      const px = L + W * (h.t - t0) / HISTORY_S, py = 6 + H - H * (v - lo) / (hi - lo);
      pen ? x.lineTo(px, py) : x.moveTo(px, py); pen = true;
    }
    x.stroke();
  }
}
function drawPlots() {
  const acc = css("--accent"), mut = css("--muted");
  plot("p_cur", [{ get: h => h.cur, color: acc }]);
  plot("p_sel", [{ get: h => h.sel && h.sel[1], color: mut }, { get: h => h.sel && h.sel[0], color: acc }]);
  plot("p_imu", [{ get: h => h.roll, color: acc }, { get: h => h.pitch, color: "#3d7fd9" }]);
}

// ------------------------------------------------------------------------------------------------ events
function log(e) {
  const div = document.createElement("div");
  const lvl = e.type === "ack" ? (e.ok ? "ack" : "nack") : (e.level || "info");
  div.className = lvl;
  const when = new Date((e.pc_time ? e.pc_time * 1000 : Date.now())).toLocaleTimeString();
  div.innerHTML = `<small>${when}</small> `;
  div.appendChild(document.createTextNode(e.type === "ack" ? `${e.ok ? "✓" : "✗"} ${e.name}: ${e.text}` : e.text));
  const box = $("events"); box.appendChild(div);
  while (box.children.length > 200) box.firstChild.remove();
  box.scrollTop = box.scrollHeight;
}

// ------------------------------------------------------------------------------------------------ link
let ws = null;
function send(m) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(m)); }
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === "schema") {
      schema = m.schema; names = Object.fromEntries(schema.fields); meta = schema.meta || {}; tableKey = ""; renderTable(true);
      $("title").textContent = schema.robot; document.title = schema.robot + " · dashboard"; robotCmdsKey = ""; renderRobotCmds();
      movesKey = ""; renderMoves(); renderEditor(false);
    }
    else if (m.type === "frame") onFrame(m);
    else if (m.type === "ack" || m.type === "event") log(m);
    else if (m.type === "recording") { recording = m.on; $("rec").classList.toggle("on", m.on); $("rec").textContent = m.on ? "■ Stop" : "● Record"; if (m.file) log({ level: "info", text: `saved ${m.file}` }); }
  };
  ws.onclose = () => { $("link").className = "pill"; $("link").textContent = "dashboard server stopped"; setTimeout(connect, 1500); };
}
function onFrame(m) {
  const pill = $("link");
  if (m.age > 1.0 || !m.rate) { pill.className = "pill"; pill.textContent = m.seq ? `no data for ${m.age.toFixed(0)} s` : "no robot"; }
  else { pill.className = "pill " + (m.rate < 20 ? "warn" : "ok"); pill.textContent = `${m.rate} Hz`; }
  if (!m.values) return;
  last = m;
  if (scene3d && m.poses) scene3d.pose(m.poses);
  // scalar fields (one value each) in the header
  // one-value fields: as the robot describes them (meta.scalars: label + unit, or a flag's texts), else name = value
  const desc = meta.scalars || {};
  const sc = Object.entries(names).filter(([k, l]) => l.length === 1 && k !== "moves").map(([k]) => {
    const v = m.values[k][0], d = desc[k] || {};
    if (d.flag) { const t = d.flag[v ? 1 : 0]; return t ? `<span class="pill ${v ? "ok" : "warn"}">${t}</span>` : ""; }
    return `${d.label || k} <b>${v === null ? "–" : (+v).toFixed(1)}</b>${d.unit ? " " + d.unit : ""}`;
  }).filter(Boolean);
  $("scalars").innerHTML = sc.join(" · ");
  const cur = m.values.current ? m.values.current.reduce((a, b) => a + Math.abs(b || 0), 0) : null;
  const [roll, pitch] = quatRollPitch(m.values.imu_quat);
  const sel = selected ? [val("q", selected), val("q_target", selected)].map(v => v === null ? null : v * DEG) : null;
  hist.push({ t: m.robot_t, cur, roll, pitch, sel });
  while (hist.length && hist[0].t < m.robot_t - HISTORY_S) hist.shift();
  if (scene3d) { const st = {}; for (const j of jointsList()) st[j] = j === selected ? "sel" : motorState(j); scene3d.tint(st); }
  renderTable();
  renderRobotCmds();
  renderMoves();
}
// whole-robot commands (the ones the robot lists), as em / init on Rhoban's robots
let robotCmdsKey = "";
function renderRobotCmds() {
  const cmds = meta.commands || [];
  const key = cmds.join();
  if (key === robotCmdsKey) return;
  robotCmdsKey = key;
  const box = $("robotcmds"); box.innerHTML = "";
  if (cmds.includes("init")) {
    const b = button("Init (zero)", "", () => cmd("init", {}), "Robot held? Go to zero");
    b.dataset.j = "*"; b.classList.remove("small");
    b.title = "stop the moves, every motor to its zero (2 s), held until a move is launched"; box.appendChild(b);
  }
  if (cmds.includes("em")) {
    const b = document.createElement("button"); b.className = "stop"; b.textContent = "⏻ Torque off (em)";
    b.title = "emergency: stop the moves, torque off on every motor"; b.onclick = () => cmd("em", {}); box.appendChild(b);
  }
}
// the robot's moves and switches (meta.moves; their states in the field "moves": 0 off, 1 starting, 2 on, 3 stopping)
let movesKey = "";
function renderMoves() {
  const list = meta.moves || [], card = $("moves");
  card.classList.toggle("show", list.length > 0 && (meta.commands || []).includes("move_start"));
  const vals = last && last.values && last.values.moves ? last.values.moves : [];
  const key = JSON.stringify(list.map(m => [m.name, m.options])) + vals.join() + JSON.stringify(Object.values(confirmKey));
  if (key === movesKey) return;
  movesKey = key;
  const box = $("movelist"); box.innerHTML = "";
  list.forEach((m, i) => {
    const st = vals[i] ?? 0, el = document.createElement("span");
    el.className = "mv" + (m.kind === "switch" ? " switch" : "") + (st === 2 ? " on" : st === 1 || st === 3 ? " busy" : "");
    el.title = m.doc || m.name;
    el.innerHTML = `<b>${m.name}</b><small>${["off", "starting", "on", "stopping"][st] || ""}</small>`;
    const b = st === 0 ? button("Start", "", () => cmd("move_start", { move: m.name }), m.kind === "move" ? "Robot ready? Start" : null)
                       : button("Stop", "", () => cmd("move_stop", { move: m.name }));
    b.dataset.j = "move:" + m.name; el.appendChild(b);
    if (Object.keys(m.options || {}).length) {                       // the variables the move exposes: its editor
      const e = document.createElement("button"); e.className = "small"; e.textContent = "⚙"; e.title = "edit its variables";
      e.onclick = ev => { ev.stopPropagation(); openEditor(m.name); }; el.appendChild(e);
    }
    box.appendChild(el);
  });
}
// the editor of a move's variables (as RhIO's parameters): applied at once on the robot, Save keeps them there
let editing = null;
function openEditor(name) { editing = name; renderEditor(true); $("editor").classList.add("show"); }
function renderEditor(force) {
  if (!editing) return;
  const m = (meta.moves || []).find(x => x.name === editing);
  if (!m) return;
  const box = $("edrows");
  if (!force && box.contains(document.activeElement)) return;      // do not redraw under the cursor
  $("edtitle").textContent = m.name; $("eddoc").textContent = m.doc || "";
  box.innerHTML = "";
  for (const [opt, v] of Object.entries(m.options || {})) {
    const row = document.createElement("div"); row.className = "edrow";
    const inp = document.createElement("input");
    if (typeof v === "boolean") { inp.type = "checkbox"; inp.checked = v; }
    else { inp.type = "number"; inp.value = v; inp.step = Number.isInteger(v) ? "1" : "any"; }
    inp.onchange = () => cmd("move_option", { move: m.name, option: opt,
                                              value: inp.type === "checkbox" ? inp.checked : Number(inp.value) });
    row.innerHTML = `<div><b>${opt}</b><small>${(m.option_docs || {})[opt] || ""}</small></div>`;
    row.appendChild(inp); box.appendChild(row);
  }
}
$("edclose").onclick = () => { editing = null; $("editor").classList.remove("show"); };
$("edsave").onclick = () => cmd("save_options", {});
$("rec").onclick = () => send({ type: "record", on: !recording });
setInterval(drawPlots, 100);
build3d().then(s => { scene3d = s; }).catch(e => log({ level: "error", text: "3D view: " + e }));
connect();
