// Robot dashboard page: 3D robot (three.js, poses computed by the PC server), motors, plots, events, commands.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const $ = id => document.getElementById(id);
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const DEG = 180 / Math.PI, HISTORY_S = 10;
let scene3d = null, schema = null, names = {}, meta = {}, last = null, selected = null, recording = false;
let liveSchema = null, replay = null;  // replay: {file, data (its plots' series), i, playing, speed, cursor (robot s)}
const hist = [];                      // [{t, cur, sel: [q, target], roll, pitch}]

// ------------------------------------------------------------------------------------------------ 3D view
let builtModel = null;               // the model the 3D view shows (the page reloads when the robot's is another)
async function build3d() {
  const sc = await (await fetch("/api/scene")).json();
  builtModel = sc.model;
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
function button(label, cls, onClick, confirmText, j) {
  const b = document.createElement("button"); b.className = "small " + (cls || ""); b.textContent = label;
  b.dataset.j = j;
  if (confirmText && confirmKey[label + j] === true) { b.textContent = confirmText; b.classList.add("confirm"); }  // redrawn while asking
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
  const lim = meta.limits || {}, cmds = replay ? [] : meta.commands || [];      // a replay: nothing to command
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
      if (want.includes("R")) { const b = button("Reboot", "danger", () => cmd("reboot", { joint: j }), "Confirm reboot", j); r.cells[7].appendChild(b); }
      if (want.includes("T1")) {
        const b = button("Torque on", "", () => cmd("torque", { joint: j, on: true }), "It will move: sure?", j); r.cells[7].appendChild(b);
      } else if (want.includes("T0")) {
        const b = button("Torque off", "", () => cmd("torque", { joint: j, on: false }), "Goes limp: sure?", j); r.cells[7].appendChild(b);
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
  if (replay) replayPlots(replay.i);
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
    if (m.type === "schema") { liveSchema = m.schema; if (!replay) applySchema(liveSchema); robotCmdsKey = ""; renderRobotCmds(); }
    else if (m.type === "replay_frame") onReplayFrame(m);
    else if (m.type === "robot") onRobot(m);
    else if (m.type === "frame") onFrame(m);
    else if (m.type === "ack" || m.type === "event") log(m);
    else if (m.type === "recording") {
      recording = m.on; $("rec").classList.toggle("on", m.on); $("rec").textContent = m.on ? "■ Stop" : "● Record";
      if (m.file) { log({ level: "info", text: `saved ${m.file}` }); listRecordings(); }
    }
  };
  ws.onclose = () => { $("link").className = "pill"; $("link").textContent = "dashboard server stopped"; setTimeout(connect, 1500); };
}
// the robot watched: chosen here (the server talks to it); named robots are saved on this PC (the server's file)
let robot = { host: null, saved: {}, model: null, models: [] };
function onRobot(m) {
  if (builtModel && m.model && m.model !== builtModel) { location.reload(); return; }   // another model: a new 3D view
  const d = $("deploy");                                  // Deploy button: only when the dashboard got --deploy
  d.hidden = !m.deploy || !m.host; d.disabled = !!m.deploying;
  if (m.deploying) { d.textContent = "⟳ Deploying…"; d.classList.remove("confirm"); }
  else if (!d.classList.contains("confirm")) d.textContent = "⟳ Deploy code";
  const changed = m.host !== robot.host || !m.host;
  robot = { host: m.host, addr: m.addr, saved: m.saved || {}, model: m.model, models: m.models || [] };
  const name = Object.keys(robot.saved).find(k => robot.saved[k].host === m.host);
  $("robotbtn").textContent = !m.host ? "choose a robot ▾" : (name ? `${name} · ${m.host} ▾` : `${m.host} ▾`);
  renderSaved();
  if (!changed) return;
  if (replay) closeReplay();
  $("link").className = "pill"; $("link").textContent = m.host ? "waiting for the robot" : "no robot";
  liveSchema = schema = null; names = {}; meta = {}; last = null; hist.length = 0;
  tableKey = ""; $("table").innerHTML = ""; $("empty").style.display = "";
  robotCmdsKey = movesKey = ""; $("robotcmds").innerHTML = ""; renderMoves(); renderVariant();
  $("scalars").innerHTML = "";
  if (!m.host) $("robotbox").classList.add("show");
}
function connectTo(host, name) {
  if (name) send({ type: "save_robot", name, host });
  send({ type: "connect", host });
  $("robotbox").classList.remove("show");
  log({ level: "info", text: `→ connect to ${name ? name + " (" + host + ")" : host}` });
}
// the robot's version (meta.variant, e.g. classic / climber: the moves made for it, the 3D model), shown in the
// header; another one chosen there is sent to the robot, which keeps it (its moves for the other version stop)
function renderVariant() {
  const list = meta.variants || [], box = $("variantbox"), sel = $("variant");
  box.hidden = !list.length || !meta.variant;
  if (box.hidden) return;
  if ([...sel.options].map(o => o.value).join() !== list.join())
    sel.innerHTML = list.map(v => `<option value="${v}">${v[0].toUpperCase() + v.slice(1)}</option>`).join("");
  if (document.activeElement !== sel && !askedVariant) sel.value = meta.variant;
  sel.disabled = !!replay || !(meta.commands || []).includes("variant");
}
// changing it changes the robot itself (saved there, for every PC): said and confirmed first
let variantTimer = null, askedVariant = null;
function closeVariantAsk() {
  clearTimeout(variantTimer); askedVariant = null; $("variantask").hidden = true; $("variant").value = meta.variant;
}
$("variant").onchange = () => {
  const v = $("variant").value, cap = s => s[0].toUpperCase() + s.slice(1);
  if (v === meta.variant) { closeVariantAsk(); return; }
  const others = (meta.moves || []).filter(m => m.variants && !m.variants.includes(v)).map(m => m.name);
  $("variantmsg").textContent = `Change the robot ${robot.host} into a ${cap(v)}? Saved on the robot itself (for every ` +
    `PC); it then runs only the moves made for a ${v}` + (others.length ? ` (stops and hides: ${others.join(", ")})` : "") + ".";
  $("variantgo").textContent = `Make ${robot.host} a ${cap(v)}`;
  askedVariant = v; $("variantask").hidden = false;
  clearTimeout(variantTimer); variantTimer = setTimeout(closeVariantAsk, 15000);
};
$("variantgo").onclick = () => {
  const v = askedVariant; closeVariantAsk();
  if (v) { $("variant").value = v; cmd("variant", { variant: v }); }
};
$("variantno").onclick = closeVariantAsk;
function renderSaved() {
  const box = $("saved"); box.innerHTML = "";
  $("savedsec").style.display = Object.keys(robot.saved).length ? "" : "none";
  for (const [name, { host }] of Object.entries(robot.saved).sort()) {
    const row = document.createElement("div"); row.className = "saved";
    const go = document.createElement("button"); go.type = "button"; go.className = host === robot.host ? "cur" : "";
    go.innerHTML = "<b></b><small></small>"; go.querySelector("b").textContent = name; go.querySelector("small").textContent = host;
    go.onclick = () => connectTo(host);
    const del = document.createElement("button"); del.type = "button"; del.className = "small"; del.textContent = "✕";
    del.title = `forget ${name}`; del.onclick = () => send({ type: "forget_robot", name });
    row.append(go, del); box.appendChild(row);
  }
}
$("robotbtn").onclick = ev => {
  ev.stopPropagation();
  const box = $("robotbox"); box.classList.toggle("show");
  if (box.classList.contains("show")) {
    $("host").value = ""; $("rname").value = ""; $("hostgo").textContent = "Connect";
  }
};
$("robotbox").onclick = ev => ev.stopPropagation();
$("rname").oninput = () => { $("hostgo").textContent = $("rname").value.trim() ? "Save and connect" : "Connect"; };
document.addEventListener("click", () => $("robotbox").classList.remove("show"));
$("robotbox").onsubmit = ev => {
  ev.preventDefault();
  const h = $("host").value.trim();
  if (h) connectTo(h, $("rname").value.trim());
};
let shownWarnings = "";
function applySchema(s) {          // the live robot's, or a recording's while it is replayed
  const w = (s.meta || {}).warnings || [];               // e.g. a move file that does not load: shown once per change
  if (!replay && w.join("\n") !== shownWarnings) { shownWarnings = w.join("\n"); w.forEach(t => log({ level: "error", text: t })); }
  schema = s; names = Object.fromEntries(schema.fields); meta = schema.meta || {}; tableKey = ""; renderTable(true);
  $("title").textContent = schema.robot + (replay ? " · replay" : ""); document.title = schema.robot + " · dashboard";
  movesKey = ""; renderMoves(); controlsKey = ""; renderControls(); renderEditor(false); renderVariant();
}
function onFrame(m) {
  const pill = $("link");
  if (m.age > 1.0 || !m.rate) { pill.className = "pill"; pill.textContent = m.seq ? `no data for ${m.age.toFixed(0)} s` : "no robot"; }
  else { pill.className = "pill " + (m.rate < 20 ? "warn" : "ok"); pill.textContent = `${m.rate} Hz`; }
  if (!m.values || replay) return;
  showFrame(m);
  hist.push({ t: m.robot_t, ...plotPoint(m.values) });
  while (hist.length && hist[0].t < m.robot_t - HISTORY_S) hist.shift();
}
function plotPoint(values) {
  const cur = values.current ? values.current.reduce((a, b) => a + Math.abs(b || 0), 0) : null;
  const [roll, pitch] = quatRollPitch(values.imu_quat);
  const sel = selected ? [val("q", selected), val("q_target", selected)].map(v => v === null ? null : v * DEG) : null;
  return { cur, roll, pitch, sel };
}
function showFrame(m) {
  last = m;
  if (scene3d && m.poses) scene3d.pose(m.poses);
  // scalar fields (one value each) in the header
  // one-value fields: as the robot describes them (meta.scalars: label + unit, or a flag's texts), else name = value
  const desc = meta.scalars || {};
  const sc = Object.entries(names).filter(([k, l]) => l.length === 1 && k !== "moves" && k !== "sliders").map(([k]) => {
    const v = m.values[k][0], d = desc[k] || {};
    if (d.flag) { const t = d.flag[v ? 1 : 0]; return t ? `<span class="pill ${v ? "ok" : "warn"}">${t}</span>` : ""; }
    return `${d.label || k} <b>${v === null ? "–" : (+v).toFixed(1)}</b>${d.unit ? " " + d.unit : ""}`;
  }).filter(Boolean);
  $("scalars").innerHTML = sc.join(" · ");
  if (scene3d) { const st = {}; for (const j of jointsList()) st[j] = j === selected ? "sel" : motorState(j); scene3d.tint(st); }
  renderTable();
  renderRobotCmds();
  renderMoves();
  renderControls();
}
// whole-robot commands (the ones the robot lists), as em / init on Rhoban's robots
let robotCmdsKey = "";
function renderRobotCmds() {
  const cmds = (liveSchema && liveSchema.meta || {}).commands || [];          // the live robot's, even in a replay
  const key = cmds.join();
  if (key === robotCmdsKey) return;
  robotCmdsKey = key;
  const box = $("robotcmds"); box.innerHTML = "";
  if (cmds.includes("init")) {
    const b = button("Init (zero)", "", () => cmd("init", {}), "Robot held? Go to zero", "*");
    b.classList.remove("small");
    b.title = "stop the moves, every motor to its zero (2 s), held until a move is launched"; box.appendChild(b);
  }
  if (cmds.includes("em")) {
    const b = document.createElement("button"); b.className = "stop"; b.textContent = "⏻ Torque off (em)";
    b.title = "emergency: stop the moves, torque off on every motor"; b.onclick = () => cmd("em", {}); box.appendChild(b);
  }
}
// the robot's moves (meta.moves; their states in the field "moves": 0 off, 2 on, 3 stopping; 1 starting and the
// switches (dashed) in older recordings)
let movesKey = "";
function renderMoves() {
  const list = meta.moves || [], card = $("moves");
  card.classList.toggle("show", list.length > 0 && (replay || (meta.commands || []).includes("move_start")));
  const vals = last && last.values && last.values.moves ? last.values.moves : [];
  const key = JSON.stringify(list.map(m => [m.name, m.options, m.available])) + robot.model + vals.join() + JSON.stringify(Object.values(confirmKey)) + !!replay;
  if (key === movesKey) return;
  movesKey = key;
  const box = $("movelist"); box.innerHTML = "";
  list.forEach((m, i) => {
    if (!madeFor(m)) return;                                         // made for another version of the robot
    const st = vals[i] ?? 0, el = document.createElement("span");
    el.className = "mv" + (m.kind === "switch" ? " switch" : "") + (st === 2 ? " on" : st === 1 || st === 3 ? " busy" : "");
    el.title = m.doc || m.name;
    el.innerHTML = `<b>${m.name}</b><small>${["off", "starting", "on", "stopping"][st] || ""}</small>`;
    if (replay) { box.appendChild(el); return; }                     // a replay shows the states only
    const b = st === 0 ? button("Start", "", () => cmd("move_start", { move: m.name }), m.kind === "move" ? "Robot ready? Start" : null, "move:" + m.name)
                       : button("Stop", "", () => cmd("move_stop", { move: m.name }), null, "move:" + m.name);
    el.appendChild(b);
    if (Object.keys(m.options || {}).length) {                       // the variables the move exposes: its editor
      const e = document.createElement("button"); e.className = "small"; e.textContent = "⚙"; e.title = "edit its variables";
      e.onclick = ev => { ev.stopPropagation(); openEditor(m.name); }; el.appendChild(e);
    }
    box.appendChild(el);
  });
}
// the moves' live controls (a move's sliders and keys), shown while their move runs (starting or on): a slider starts
// at its start value (the robot resets it at each launch) and sends its value while dragged (the frames show the
// robot's); the keyboard zone, once clicked, sends the keys held
let controlsKey = "";
function renderControls() {
  const list = meta.moves || [], vals = last && last.values && last.values.moves ? last.values.moves : [];
  const running = list.filter((m, i) => vals[i] === 1 || vals[i] === 2);
  const withSliders = running.filter(m => Object.keys(m.sliders || {}).length), withKeys = list.filter((m, i) => vals[i] >= 1 && m.keys && !replay);   // stopping too
  const key = JSON.stringify(withSliders.map(m => [m.name, m.sliders])) + withKeys.map(m => m.name + m.keys).join() + !!replay;
  if (key !== controlsKey) {
    controlsKey = key;
    const box = $("sliders"); box.innerHTML = "";
    for (const m of withSliders) for (const [n, [lo, hi, start]] of Object.entries(m.sliders)) {
      const row = document.createElement("div"); row.className = "slrow"; row.dataset.label = `${m.name}.${n}`;
      row.innerHTML = `<span>${n} <small>${m.name}</small></span>`;
      const inp = document.createElement("input"); inp.type = "range"; inp.min = lo; inp.max = hi; inp.step = (hi - lo) / 200;
      inp.value = start; inp.disabled = !!replay; inp.title = `${lo} to ${hi}, starts at ${start}`;
      let sent = 0;
      inp.oninput = () => {                       // at most 20 values a second while dragged, and the last one
        const now = performance.now(); clearTimeout(inp.timer);
        const go = () => { sent = performance.now(); cmdQuiet("slider", { move: m.name, slider: n, value: +inp.value }); };
        if (now - sent > 50) go(); else inp.timer = setTimeout(go, 50);
        num.value = fmt(+inp.value);
      };
      const num = document.createElement("input"); num.type = "number"; num.className = "slval"; num.value = fmt(start);
      num.step = "any"; num.title = "click to type a value (Enter)";
      num.onchange = () => {                      // a value typed by hand: within min / max
        const v = Math.min(Math.max(+num.value, lo), hi);
        if (!Number.isFinite(v)) return;
        inp.value = v; num.value = fmt(v); cmdQuiet("slider", { move: m.name, slider: n, value: v });
      };
      num.onkeydown = e => { if (e.key === "Enter") num.blur(); };
      row.appendChild(inp); row.appendChild(num); box.appendChild(row);
    }
    const kz = $("keyzone");
    kz.classList.toggle("show", withKeys.length > 0);
    kz.innerHTML = "<b>Keyboard</b>: click here, then the keys go to the robot (click elsewhere: released) · " +
      withKeys.map(m => `<kbd>${m.name}</kbd> ${m.keys}`).join(" · ");
    if (!withKeys.length) kz.blur();                         // its move stopped: the keys are released
  }
  $("controls").classList.toggle("show", withSliders.length > 0 || withKeys.length > 0);
  const lab = names.sliders || [], sv = last && last.values && last.values.sliders ? last.values.sliders : [];
  for (const row of $("sliders").children) {
    const i = lab.indexOf(row.dataset.label), [inp, num] = row.querySelectorAll("input");
    if (i < 0 || sv[i] === null || sv[i] === undefined || row.contains(document.activeElement)) continue;   // not while edited
    inp.value = sv[i]; num.value = fmt(sv[i]);
  }
}
const fmt = v => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2));
function cmdQuiet(name, args) { send({ type: "cmd", name, args }); }           // not in the events (many a second)
const held = new Set();
const keyName = e => e.key === " " ? "space" : e.key.length === 1 ? e.key.toLowerCase() : e.key;
function sendKeys() { cmdQuiet("keys", { held: [...held] }); }
setInterval(() => { if (held.size) sendKeys(); }, 200);     // repeated: the robot releases them without news
$("keyzone").addEventListener("keydown", e => {
  if (e.ctrlKey || e.metaKey || e.altKey || e.key === "Tab" || e.key === "Escape") { if (e.key === "Escape") $("keyzone").blur(); return; }
  e.preventDefault();                                        // arrows and space do not scroll the page
  if (e.repeat) return;
  held.add(keyName(e)); sendKeys();
});
$("keyzone").addEventListener("keyup", e => { if (held.delete(keyName(e))) sendKeys(); });
$("keyzone").addEventListener("blur", () => { if (held.size) { held.clear(); sendKeys(); } });
window.addEventListener("blur", () => { if (held.size) { held.clear(); sendKeys(); } });
// a move lists the versions of the robot it is made for (e.g. classic, climber): shown only for the robot's version
// (meta.variant, set from the robot picker), or the version chosen there for a robot that does not know it (a
// running move is still shown, to stop it)
function madeFor(m) {
  const st = last && last.values && last.values.moves ? last.values.moves[(meta.moves || []).indexOf(m)] : 0;
  if ((st ?? 0) !== 0) return true;                       // running: shown, to stop it
  if (m.available !== undefined) return m.available;      // the robot knows its version
  if (!m.variants || robot.models.length < 2 || !robot.model) return true;
  return m.variants.includes(robot.model.toLowerCase());
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
// Deploy (as make deploy): a first click asks to confirm, the torque goes off while the robot's program restarts
let deployTimer = null;
$("deploy").onclick = () => {
  const d = $("deploy");
  if (!d.classList.contains("confirm")) {
    d.classList.add("confirm"); d.textContent = "Robot held? Deploy";
    deployTimer = setTimeout(() => { d.classList.remove("confirm"); d.textContent = "⟳ Deploy code"; }, 3000);
    return;
  }
  clearTimeout(deployTimer); d.classList.remove("confirm");
  send({ type: "deploy" });
};

// ------------------------------------------------------------------------------------------------ replay
// The page holds a recording's plotted series; the server sends one frame at a time (values + 3D pose) where the
// cursor is, so it plays at any speed, back and forth. The live robot keeps running: em still acts on it.
const SPEEDS = [0.1, 0.25, 0.5, 1, 2];
let pending = false;
async function listRecordings() {
  const files = await (await fetch("/api/recordings")).json(), sel = $("rp_file"), cur = sel.value;
  sel.innerHTML = `<option value="">${files.length ? "choose a recording…" : "no recording yet"}</option>` +
    files.map(f => `<option>${f.file}</option>`).join("");
  if (files.some(f => f.file === cur)) sel.value = cur;
}
async function openReplay(file) {
  if (!file) return;
  const r = await fetch("/api/replay/" + encodeURIComponent(file));
  if (!r.ok) { log({ level: "error", text: `replay ${file}: ${await r.text()}` }); return; }
  const data = await r.json();
  replay = { file, data, i: 0, playing: false, speed: replay ? replay.speed : 1, cursor: data.t[0] };
  applySchema(data.schema);
  $("rp_seek").max = data.n - 1; seek(0);
}
function closeReplay() {
  replay = null; $("replaybar").classList.remove("show"); $("replay").classList.remove("on"); hist.length = 0;
  if (liveSchema) applySchema(liveSchema);
}
function seek(i) {                   // show frame i (asks the server for it; one request at a time)
  if (!replay) return;
  const d = replay.data; i = Math.max(0, Math.min(d.n - 1, i));
  replay.i = i; if (!replay.playing) replay.cursor = d.t[i];
  $("rp_seek").value = i;
  $("rp_time").textContent = `${(d.t[i] - d.t[0]).toFixed(2)} / ${(d.t[d.n - 1] - d.t[0]).toFixed(2)} s · frame ${i + 1}/${d.n}`;
  if (!pending) { pending = true; send({ type: "replay_frame", file: replay.file, i }); }
}
function onReplayFrame(m) {
  pending = false;
  if (!replay || m.file !== replay.file) return;
  if (m.i !== replay.i) { seek(replay.i); }                         // the cursor moved meanwhile: catch up
  showFrame(m); replayPlots(m.i);
}
function replayPlots(i) {            // the plots: the HISTORY_S before the cursor, from the recording's series
  const d = replay.data, ji = selected ? (names.q || []).indexOf(selected) : -1;
  hist.length = 0;
  for (let k = i; k >= 0 && d.t[k] >= d.t[i] - HISTORY_S; k--) {
    const [roll, pitch] = quatRollPitch(d.imu_quat && d.imu_quat[k]);
    const sel = ji < 0 || !d.q ? null : [d.q[k][ji], d.q_target ? d.q_target[k][ji] : null].map(v => v === null ? null : v * DEG);
    hist.unshift({ t: d.t[k], cur: d.cur ? d.cur[k] : null, roll, pitch, sel });
  }
}
function frameAt(t) {                // the last frame at or before robot time t
  const d = replay.data; let lo = 0, hi = d.n - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (d.t[mid] <= t) lo = mid; else hi = mid - 1; }
  return lo;
}
function play(on) {
  if (!replay) return;
  const d = replay.data;
  if (on && replay.i >= d.n - 1) { replay.i = 0; replay.cursor = d.t[0]; }
  replay.playing = on; $("rp_play").textContent = on ? "⏸" : "▶";
}
let lastTick = performance.now();
setInterval(() => {
  const now = performance.now(), dt = (now - lastTick) / 1000; lastTick = now;
  if (!replay || !replay.playing) return;
  const d = replay.data;
  replay.cursor += dt * replay.speed;
  const i = frameAt(replay.cursor);
  if (i !== replay.i) seek(i);
  if (replay.cursor >= d.t[d.n - 1]) play(false);
}, 1000 / 30);
$("rp_speed").innerHTML = SPEEDS.map(v => `<option value="${v}"${v === 1 ? " selected" : ""}>×${v}</option>`).join("");
$("rp_speed").onchange = e => { if (replay) replay.speed = +e.target.value; };
$("rp_file").onchange = e => openReplay(e.target.value);
$("rp_play").onclick = () => play(!(replay && replay.playing));
$("rp_back").onclick = () => { play(false); seek(replay.i - 1); };
$("rp_fwd").onclick = () => { play(false); seek(replay.i + 1); };
$("rp_seek").oninput = e => { if (replay) { replay.cursor = replay.data.t[+e.target.value]; seek(+e.target.value); } };
$("rp_live").onclick = closeReplay;
$("replay").onclick = () => {
  if (replay || $("replaybar").classList.contains("show")) { closeReplay(); return; }
  $("replaybar").classList.add("show"); $("replay").classList.add("on"); listRecordings();
};
document.addEventListener("keydown", e => {   // space: play / pause; arrows: one frame (shift: one second)
  if (!replay || e.target.closest("input, select, textarea")) return;
  if (e.key === " ") { e.preventDefault(); play(!replay.playing); }
  else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    e.preventDefault(); play(false);
    const s = e.key === "ArrowLeft" ? -1 : 1;
    if (e.shiftKey) { replay.cursor = replay.data.t[replay.i] + s; seek(frameAt(replay.cursor)); } else seek(replay.i + s);
  }
});
setInterval(drawPlots, 100);
build3d().then(s => { scene3d = s; }).catch(e => log({ level: "error", text: "3D view: " + e }));
connect();
