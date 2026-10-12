"""Galaxy transitions: the pure camera / promotion / morph model of dashboard.html, stepped at a fixed dt under Node.

No browser: the model block (from `const GALAXY_PALETTE` to `// ---- end of the galaxy model`) has no DOM access, so these tests run the
very code the flights run: they assert continuity (no particle teleports, camera monotone and smooth), that agent stars end exactly on
their slots, that no pull-back remains, and that a full round trip leaves every star where it was.

The cloud is a constant 11,700 particles that nothing thins out (no governor, no floor); it is painted by a WebGL2 painter (an
instanced draw per pass) with the canvas painter as the reference and the fallback. The painters run here against stubs of the
canvas and of WebGL2, so what is checked is the real code: the passes, their order, the uploads and every reason to fall back.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import JS_I18N

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
JS = re.search(r"<script>\n(.*?)</script>", HTML, re.S).group(1)
MODEL = JS[JS.index("const GALAXY_PALETTE"): JS.index("// ---- end of the galaxy model")]
# The painters of the cloud, in one piece from the sprites to the GPU painter (the layer of small stars, drawOrbSim, drawMist,
# drawCloudScene, glxInit, glxScene): they run against stubs of the canvas and of WebGL2, no DOM needed
PAINT = JS[JS.index("function glowSprite("): JS.index("function buildFlakes(")]

PRELUDE = """
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const HOME_PALETTE = ['#ffc861', '#ff6fb5', '#9a7bff', '#4fd6ff', '#fff1d6', '#6f9bff'];
// the page's store (aos.<key> in localStorage) and a canvas factory: a 2D context that draws nothing, and WebGL2 when a test sets GL
const store = { get: k => (globalThis.STORE && k in globalThis.STORE ? globalThis.STORE[k] : null) };
const document = { createElement: () => { const cv = { width: 0, height: 0, img: null, on: {}, addEventListener(n, f) { this.on[n] = f; } };
  cv.getContext = kind => kind === 'webgl2' ? (globalThis.GL || null) : ({ createRadialGradient: () => ({ addColorStop() {} }), fillRect() {}, beginPath() {}, arc() {}, fill() {},
    createImageData: (w, h) => ({ width: w, height: h, data: new Uint8ClampedArray(w * h * 4) }),
    putImageData(img) { cv.img = { width: img.width, height: img.height, data: Uint8ClampedArray.from(img.data) }; } });
  return cv; } };
"""

# Shared fixtures for the scenarios (JavaScript): a settled home galaxy, an agent set, and helpers.
FIXTURE = """
const N = GALAXY_N, cloud = buildCloud(N), DT = 1 / 60;
const W = 1440, H = 900, X0 = 520, Y0 = 430, CR0 = 190, T0 = 123.4;
const box = atlasMapBox(W, H), REST = atlasRestCR(box.w, box.h);
const sm = u => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };
const P = (t, ox, oy, CR) => ({ t, rot: homeRot(t), ox, oy, CR });
const maxDisp = (sim, prev, m) => { let d = 0; for (let i = 0; i < m; i++) d = Math.max(d, Math.hypot(sim.x[i] - prev.x[i], sim.y[i] - prev.y[i])); return d; };
const copy = (sim, prev, m) => { for (let i = 0; i < m; i++) { prev.x[i] = sim.x[i]; prev.y[i] = sim.y[i]; } };
const settle = (sim, m, t, ox, oy, CR, A, secs) => {
  const out = [0, 0, 0, 1];
  for (let f = 0; f < secs * 60; f++) { t += DT; stepOrbSim(sim, m, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(t, ox, oy, CR), A), null); }
  return t;
};
const home = makeOrbSim(N);
snapOrbSim(home, N, galaxyTarget(cloud, P(T0, X0, Y0, CR0), null));
const agentsFor = (n, t) => {
  const A = makeAgentSet(N, pickAgentStars(cloud, n, t));
  for (let k = 0; k < A.n; k++) A.ci[k] = k % 6;
  agentGeom(A, box.w, box.h, REST, 100);
  return A;
};
"""


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class GalaxyTransitionTests(unittest.TestCase):
    def _run(self, body: str, paint: bool = False):
        src = JS_I18N + PRELUDE + MODEL + (PAINT if paint else "") + FIXTURE + body
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # ---- budget and size -------------------------------------------------------------------------------------------------
    def test_budget_is_constant_and_the_galaxy_bigger(self):
        out = self._run("""
const a = buildCloud(GALAXY_N), onArm = a.filter(p => p.arm >= 0).length / a.length;
console.log(JSON.stringify({ n: GALAXY_N, len: a.length, stars: GALAXY_STARS, glow: GALAXY_GLOW_N, dust: GALAXY_DUST_N, cr: HOME_CR, pool: GALAXY_POOL, onArm,
  inside: a.every(p => Math.hypot(p.x, p.y, p.z) <= 1.0001), bright: a.filter((p, i) => isBrightOrb(i)).length }));
""")
        self.assertEqual(out["n"], 11700)                 # one fixed budget: 9000 stars, 1800 glow, 900 dust
        self.assertEqual((out["stars"], out["glow"], out["dust"]), (9000, 1800, 900))
        self.assertEqual(out["len"], out["n"])
        self.assertLessEqual(out["pool"], out["stars"])   # the agents are picked among the first stars
        self.assertGreaterEqual(out["cr"] / 0.43, 1.25)   # 25 to 35 percent larger than the previous round (0.43)
        self.assertLessEqual(out["cr"] / 0.43, 1.35)
        self.assertGreater(out["onArm"], 0.4)             # the arms and the clusters on them carry a good part of the stars
        self.assertTrue(out["inside"])
        self.assertEqual(out["bright"], 375)              # every 24th star is a cluster star

    # ---- the promotion: stars become agents ----------------------------------------------------------------------------------
    def test_agents_are_distinct_arm_stars_near_their_slots(self):
        out = self._run("""
const n = 40, t = T0, A = agentsFor(n, t), a2 = agentsFor(n, t);
const om = t * galaxySpeed(0.62), cs = Math.cos(om), sn = Math.sin(om), s = [0, 0, 0];
const dist = [];
for (let k = 0; k < A.n; k++) {
  const p = cloud[A.idx[k]], a = t * p.sp, x = p.x * Math.cos(a) + p.z * Math.sin(a), z = -p.x * Math.sin(a) + p.z * Math.cos(a);
  agentSlot(k, n, s);
  dist.push(Math.hypot(x - (s[0] * cs + s[2] * sn), z - (-s[0] * sn + s[2] * cs)));
}
console.log(JSON.stringify({ n: A.n, uniq: new Set(A.idx).size, same: Array.from(A.idx).join() === Array.from(a2.idx).join(),
  pool: Math.max(...A.idx) < GALAXY_POOL && GALAXY_POOL <= GALAXY_STARS, arm: Array.from(A.idx).every(i => cloud[i].arm >= 0 && cloud[i].r >= ATLAS_CORE_R),
  near: Math.max(...dist), at: Array.from(A.idx).every((i, k) => A.at[i] === k), others: A.at.filter(v => v >= 0).length }));
""")
        self.assertEqual(out["n"], 40)
        self.assertEqual(out["uniq"], 40)                 # one star per agent
        self.assertTrue(out["same"])                      # deterministic
        self.assertTrue(out["pool"])                      # inside the first GALAXY_POOL stars of the cloud
        self.assertTrue(out["arm"])                       # arm stars outside the bright center
        self.assertLess(out["near"], 0.15)                # a short glide to the slot
        self.assertTrue(out["at"])
        self.assertEqual(out["others"], 40)               # every other star stays a star

    def test_entry_flight_is_continuous_stars_become_agents_and_the_camera_never_pulls_back(self):
        out = self._run("""
const n = 30, A = agentsFor(n, T0), sim = makeOrbSim(N), prev = makeOrbSim(N);
for (let i = 0; i < N; i++) { sim.x[i] = home.x[i]; sim.y[i] = home.y[i]; sim.z[i] = home.z[i]; }
let t = settle(sim, N, T0, X0, Y0, CR0, null, 3);
const rig = entryRig(X0, Y0, CR0, W, H), cam = {}, DUR = 2.3;
const t0 = t, CRs = [], SZs = [], W1 = [], disp = [], dw = [];
copy(sim, prev, N);
let wPrev = Array.from(A.w), first = null, take = null;
for (let f = 0; f * DT / DUR <= 1.0000001; f++) {
  const u = f * DT / DUR; t = t0 + f * DT;
  entryFrame(rig, u, cam);
  promoStep(A, DT, k => promoGoal(k, A.n, u, true)); syncPromo(A, sim, N, DT);
  stepOrbSim(sim, N, DT, 44, orbDamp(44), galaxyTarget(cloud, P(t, cam.cx, cam.cy, cam.CR), A), null);
  CRs.push(cam.CR); SZs.push(cam.sz); disp.push(maxDisp(sim, prev, N)); copy(sim, prev, N);
  let d = 0; for (let k = 0; k < A.n; k++) d = Math.max(d, Math.abs(A.w[k] - wPrev[k])); dw.push(d); wPrev = Array.from(A.w);
  if (take === null && u >= ZOOM_TAKE) take = { w: Array.from(A.w), cr: cam.CR, u };
}
// the view keeps the framing: 3 more seconds with CR/sz fixed at the end of the flight; nothing may move the camera
const endCR = cam.CR, endSz = cam.sz, ox = cam.cx, oy = cam.cy;
const viewCR = [];
for (let f = 0; f < 180; f++) { t += DT; stepOrbSim(sim, N, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(t, ox, oy, endCR), A), null); viewCR.push(endCR); }
const inc = CRs.every((v, i) => i === 0 || v >= CRs[i - 1] - 1e-9), szInc = SZs.every((v, i) => i === 0 || v >= SZs[i - 1] - 1e-9);
const rel = CRs.map((v, i) => i === 0 ? 0 : Math.abs(v - CRs[i - 1]) / v);
const holdFrom = CRs.findIndex((v, i) => i * DT / DUR >= ZOOM_SPLIT);
console.log(JSON.stringify({ inc, szInc, maxRel: Math.max(...rel), start: CRs[0], end: CRs[CRs.length - 1], rig: rig.CR1, CR0: rig.CR0, rest: REST,
  held: CRs.slice(holdFrom).every(v => Math.abs(v - rig.CR1) < 1e-6), szEnd: SZs[SZs.length - 1], maxDisp: Math.max(...disp), maxDw: Math.max(...dw),
  wAtTake: take.w.every(w => w > 0.999), wEnd: Array.from(A.w).every(w => w === 1), pwEnd: Array.from(A.idx).every(i => sim.pw[i] === 1),
  pw0: Array.from(sim.pw).filter(v => v > 0).length, gc: Array.from(A.idx).map((i, k) => sim.gc[i] === k % 6).every(Boolean),
  dive: rig.CR1 / rig.CR0, ease0: (CRs[1] - CRs[0]) / (CRs[CRs.length >> 1] - CRs[(CRs.length >> 1) - 1]) }));
""")
        self.assertTrue(out["inc"])                       # monotone: one dive
        self.assertTrue(out["szInc"])
        self.assertLess(out["maxRel"], 0.03)              # no snap: at most a few percent of the radius per frame
        self.assertAlmostEqual(out["start"], out["CR0"], delta=1e-6)
        self.assertAlmostEqual(out["end"], out["rig"], delta=1e-6)
        self.assertTrue(out["held"])                      # from ZOOM_SPLIT on the camera holds: the view keeps it
        self.assertGreaterEqual(out["dive"], 2.0)         # it is a real dive ...
        self.assertLessEqual(out["dive"], 3.5)            # ... to a resting zoom, not an extreme one
        self.assertGreaterEqual(out["rig"], out["rest"] - 1e-6)
        self.assertLess(out["ease0"], 0.2)                # ease-in: the first frame hardly moves
        self.assertGreater(out["szEnd"], 1.4)
        self.assertLess(out["maxDisp"], 40)               # no star teleports (px per frame)
        self.assertLess(out["maxDw"], 4 / 60 + 1e-6)      # the promotion never jumps: bounded rate
        self.assertTrue(out["wAtTake"])                   # agents are complete when the view takes over
        self.assertTrue(out["wEnd"])
        self.assertTrue(out["pwEnd"])
        self.assertEqual(out["pw0"], 30)                  # only the agents are promoted
        self.assertTrue(out["gc"])                        # they carry their group color

    def test_agent_stars_end_exactly_on_their_slots(self):
        out = self._run("""
const n = 30, A = agentsFor(n, T0), sim = makeOrbSim(N);
for (let i = 0; i < N; i++) { sim.x[i] = home.x[i]; sim.y[i] = home.y[i]; sim.z[i] = home.z[i]; }
let t = settle(sim, N, T0, X0, Y0, CR0, null, 2);
const rig = entryRig(X0, Y0, CR0, W, H), cam = {}, DUR = 2.3, t0 = t;
for (let f = 0; f * DT / DUR <= 1; f++) {
  const u = f * DT / DUR; t = t0 + f * DT; entryFrame(rig, u, cam);
  promoStep(A, DT, k => promoGoal(k, A.n, u, true)); syncPromo(A, sim, N, DT);
  stepOrbSim(sim, N, DT, 44, orbDamp(44), galaxyTarget(cloud, P(t, cam.cx, cam.cy, cam.CR), A), null);
}
t = settle(sim, N, t, cam.cx, cam.cy, cam.CR, A, 4);
// slot computed independently of galaxyTarget: rigid rotation of u0, then the disc rotation, perspective, slot scale
const rot = homeRot(t), om = t * galaxySpeed(0.62), cs = Math.cos(om), sn = Math.sin(om);
const errT = [], errS = [], tg = galaxyTarget(cloud, P(t, cam.cx, cam.cy, cam.CR), A), o = [0, 0, 0, 1];
for (let k = 0; k < A.n; k++) {
  const i = A.idx[k], u0 = A.u0, ux = u0[3 * k] * cs + u0[3 * k + 2] * sn, uz = -u0[3 * k] * sn + u0[3 * k + 2] * cs;
  const q = rot([ux, u0[3 * k + 1], uz]), f = 1 / (1 - q[2] * 0.1);
  let dx = q[0] * A.S * f, dy = q[1] * A.S * f; const m = Math.hypot(dx, dy);
  if (m < A.hubClear) { dx *= A.hubClear / m; dy *= A.hubClear / m; }
  tg(i, o);
  errT.push(Math.hypot(o[0] - (cam.cx + dx), o[1] - (cam.cy + dy)));
  errS.push(Math.hypot(sim.x[i] - o[0], sim.y[i] - o[1]));
}
const inside = Array.from(A.idx).every(i => sim.x[i] > 30 && sim.x[i] < box.w + box.l && sim.y[i] > 30 && sim.y[i] < H - 30);
console.log(JSON.stringify({ errT: Math.max(...errT), errS: Math.max(...errS), S: A.S, CR: cam.CR, inside }));
""")
        self.assertLess(out["errT"], 1e-3)                # the slot is exactly where the rigid arm pattern puts it
        self.assertLess(out["errS"], 6)                   # the star sits on it (a spring following a slow target lags a few px)
        self.assertLessEqual(out["S"], out["CR"] + 1e-6)  # slots never outside the galaxy radius
        self.assertTrue(out["inside"])

    # ---- the return: the entry in reverse -----------------------------------------------------------------------------------
    def test_round_trip_home_atlas_home_restores_every_star(self):
        out = self._run("""
const n = 30, A = agentsFor(n, T0), sim = makeOrbSim(N), ctl = makeOrbSim(N), prev = makeOrbSim(N);
for (let i = 0; i < N; i++) { sim.x[i] = ctl.x[i] = home.x[i]; sim.y[i] = ctl.y[i] = home.y[i]; sim.z[i] = ctl.z[i] = home.z[i]; }
let t = settle(sim, N, T0, X0, Y0, CR0, null, 3); const tStart = t;
const rig = entryRig(X0, Y0, CR0, W, H), cam = {}, DUR = 2.3;
let t1 = t;
for (let f = 0; f * DT / DUR <= 1; f++) {
  const u = f * DT / DUR; t = t1 + f * DT; entryFrame(rig, u, cam);
  promoStep(A, DT, k => promoGoal(k, A.n, u, true)); syncPromo(A, sim, N, DT);
  stepOrbSim(sim, N, DT, 44, orbDamp(44), galaxyTarget(cloud, P(t, cam.cx, cam.cy, cam.CR), A), null);
}
const deep = { cx: cam.cx, cy: cam.cy, CR: cam.CR, sz: cam.sz };
t = settle(sim, N, t, deep.cx, deep.cy, deep.CR, A, 3);   // a while in Atlas, framing untouched
// return flight (stage geometry = home): same rig the code uses
const R = { cx0: deep.cx, cy0: deep.cy, CR0: deep.CR, sz0: deep.sz, gx: X0, gy: Y0, gCR: CR0 }, rc = {};
const CRs = [], szs = [], disp = [], w = [], dw = [];
copy(sim, prev, N); let wPrev = Array.from(A.w), t2 = t, last = null;
for (let f = 0; f * DT / DUR <= 0.86; f++) {   // the stage takes over at u = 0.86
  const u = f * DT / DUR; t = t2 + f * DT; returnFrame(R, u, rc);
  promoStep(A, DT, k => promoGoal(k, A.n, u, false)); syncPromo(A, sim, N, DT);
  stepOrbSim(sim, N, DT, 26, orbDamp(26), galaxyTarget(cloud, P(t, rc.cx, rc.cy, rc.CR), A), null);
  CRs.push(rc.CR); szs.push(rc.sz); disp.push(maxDisp(sim, prev, N)); copy(sim, prev, N);
  let d = 0; for (let k = 0; k < A.n; k++) d = Math.max(d, Math.abs(A.w[k] - wPrev[k])); dw.push(d); wPrev = Array.from(A.w); w.push(Math.max(...A.w));
  last = { u, cx: rc.cx, cy: rc.cy, CR: rc.CR };
}
const dec = CRs.every((v, i) => i === 0 || v <= CRs[i - 1] + 1e-9), szDec = szs.every((v, i) => i === 0 || v <= szs[i - 1] + 1e-9);
const rel = CRs.map((v, i) => i === 0 ? 0 : Math.abs(v - CRs[i - 1]) / v);
// home again: the stage physics, same clock, the control never left home
const tEnd = t;
for (let f = 0; f < 4 * 60; f++) {
  t += DT; stepOrbSim(sim, N, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(t, X0, Y0, CR0), null), null);
}
let tc = tStart; for (let f = 0; f < Math.round((t - tStart) / DT); f++) { tc += DT; stepOrbSim(ctl, N, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(tc, X0, Y0, CR0), null), null); }
let back = 0, ctlErr = 0, tgt = galaxyTarget(cloud, P(t, X0, Y0, CR0), null), o = [0, 0, 0, 1];
for (let i = 0; i < N; i++) { tgt(i, o); back = Math.max(back, Math.hypot(sim.x[i] - o[0], sim.y[i] - o[1])); }
const tg2 = galaxyTarget(cloud, P(tc, X0, Y0, CR0), null);
for (let i = 0; i < N; i++) { tg2(i, o); ctlErr = Math.max(ctlErr, Math.hypot(ctl.x[i] - o[0], ctl.y[i] - o[1])); }
let vsCtl = 0; for (let i = 0; i < N; i++) vsCtl = Math.max(vsCtl, Math.hypot(sim.x[i] - ctl.x[i], sim.y[i] - ctl.y[i]));
let lastW = Array.from(A.w);
console.log(JSON.stringify({ vsCtl, dec, szDec, maxRel: Math.max(...rel), startCR: CRs[0], deepCR: deep.CR, endCR: CRs[CRs.length - 1], gCR: CR0, endSz: szs[szs.length - 1],
  maxDisp: Math.max(...disp), maxDw: Math.max(...dw), wLeft: Math.max(...lastW), pw: Math.max(...sim.pw), back, ctlErr, lastU: last.u,
  ease: (CRs[0] - CRs[1]) / (CRs[(CRs.length >> 1) - 1] - CRs[CRs.length >> 1]), wStart: w[0] }));
""")
        self.assertTrue(out["dec"])                       # one smooth pull-out
        self.assertTrue(out["szDec"])
        self.assertLess(out["maxRel"], 0.03)              # ease-in-out, no linear snap
        self.assertAlmostEqual(out["startCR"], out["deepCR"], delta=1e-6)   # begins exactly where Atlas rested
        self.assertAlmostEqual(out["endCR"], out["gCR"], delta=0.5)          # ends at the stage radius
        self.assertAlmostEqual(out["endSz"], 1.0, delta=0.01)
        self.assertLess(out["maxDisp"], 40)               # no star teleports
        self.assertLess(out["maxDw"], 4 / 60 + 1e-6)      # demotion is rate-limited
        self.assertEqual(out["wLeft"], 0)                 # all agents are stars again before the stage takes over
        self.assertEqual(out["pw"], 0)                    # colour and size are back to the base star
        self.assertEqual(out["wStart"], 1)
        self.assertLess(out["back"], 6)                   # on its home orbit (a spring following the rotation lags a few px, as at rest)
        self.assertLess(out["ctlErr"], 6)
        self.assertLess(out["vsCtl"], 0.5)                # and exactly where a galaxy that never left home is
        self.assertLess(out["ease"], 0.25)                # ease-in at the start of the pull-out

    def test_return_camera_is_the_entry_curve_run_backwards(self):
        out = self._run("""
const rig = entryRig(X0, Y0, CR0, W, H), cam = {}, rc = {};
const R = { cx0: rig.X1, cy0: rig.Y1, CR0: rig.CR1, sz0: ATLAS_SZ, gx: X0, gy: Y0, gCR: CR0 };
// the dive in log space: p(u) = ln(CR / CR0) / ln(CR1 / CR0); the pull-out is the same curve of the zoom (camEase) from the other end
const lnA = Math.log(rig.CR1 / rig.CR0);
let maxDev = 0;
for (let i = 0; i <= 50; i++) {
  const x = i / 50;
  entryFrame(rig, x * ZOOM_SPLIT, cam); const pIn = Math.log(cam.CR / rig.CR0) / lnA;
  returnFrame(R, RET_ZOOM_A + (1 - x) * RET_ZOOM_D, rc); const pOut = Math.log(rc.CR / rig.CR0) / lnA;
  maxDev = Math.max(maxDev, Math.abs(pIn - pOut));
}
console.log(JSON.stringify({ maxDev, camEase0: [camEase(0), camEase(1), camEase(0.5)] }));
""")
        self.assertLess(out["maxDev"], 1e-9)              # the same ease-in-out curve, mirrored
        self.assertEqual(out["camEase0"], [0, 1, 0.5])

    # ---- Atlas <-> Second Brain ----------------------------------------------------------------------------------------------
    def test_second_brain_morph_and_back_are_continuous(self):
        out = self._run("""
const M = 2000, NODES = 37, nodeOf = i => Math.floor(((i * 0.6180339887) % 1) * NODES);
const NX = j => 300 + (j % 7) * 90, NY = j => 200 + Math.floor(j / 7) * 90;
const sim = makeOrbSim(N), prev = makeOrbSim(N), ctl = makeOrbSim(N);
for (let i = 0; i < N; i++) { sim.x[i] = ctl.x[i] = home.x[i]; sim.y[i] = ctl.y[i] = home.y[i]; sim.z[i] = ctl.z[i] = home.z[i]; }
let t = settle(sim, M, T0, X0, Y0, CR0, null, 3); const tS = t;
const DUR = OS_FLY_MS / 1000, mo = {}, wTrace = [], disp = [], dwMax = [], CRk = [];
let t1 = t; copy(sim, prev, M);
const wOf = (u, i, back) => morphW(u, i, back);
let wPrev = new Float32Array(M);
for (let f = 0; f * DT / DUR <= 1; f++) {
  const u = f * DT / DUR; t = t1 + f * DT; morphFrame(u, false, mo);
  const hm = galaxyTarget(cloud, P(t, X0, Y0, CR0 * mo.k), null);
  stepOrbSim(sim, M, DT, mo.K, orbDamp(mo.K), (i, o) => { hm(i, o); morphPoint(o, wOf(u, i, false), NX(nodeOf(i)), NY(nodeOf(i)), i); }, null);
  disp.push(maxDisp(sim, prev, M)); copy(sim, prev, M); CRk.push(mo.k);
  let d = 0; for (let i = 0; i < M; i++) { const w = wOf(u, i, false); d = Math.max(d, Math.abs(w - wPrev[i])); wPrev[i] = w; } dwMax.push(d);
}
let atNode = 0; for (let i = 0; i < M; i++) atNode = Math.max(atNode, Math.hypot(sim.x[i] - NX(nodeOf(i)), sim.y[i] - NY(nodeOf(i))));
const outDisp = Math.max(...disp), outDw = Math.max(...dwMax), kOut = CRk.every((v, i) => i === 0 || v <= CRk[i - 1] + 1e-9);
// a while in the Second Brain (the galaxy clock keeps running), then the return: starts exactly at the nodes
t += 5; for (let i = 0; i < M; i++) { sim.x[i] = NX(nodeOf(i)); sim.y[i] = NY(nodeOf(i)); sim.z[i] = 0; sim.vx[i] = sim.vy[i] = sim.vz[i] = 0; }
copy(sim, prev, M); const disp2 = [], dw2 = [], kBack = []; let t2 = t; wPrev.fill(1);
let end = null;
for (let f = 0; f * DT / DUR <= 0.86; f++) {
  const u = f * DT / DUR; t = t2 + f * DT; morphFrame(u, true, mo);
  const hm = galaxyTarget(cloud, P(t, X0, Y0, CR0 * mo.k), null);
  stepOrbSim(sim, M, DT, mo.K, orbDamp(mo.K), (i, o) => { hm(i, o); morphPoint(o, wOf(u, i, true), NX(nodeOf(i)), NY(nodeOf(i)), i); }, null);
  disp2.push(maxDisp(sim, prev, M)); copy(sim, prev, M); kBack.push(mo.k);
  let d = 0; for (let i = 0; i < M; i++) { const w = wOf(u, i, true); d = Math.max(d, Math.abs(w - wPrev[i])); wPrev[i] = w; } dw2.push(d);
}
for (let f = 0; f < 4 * 60; f++) { t += DT; stepOrbSim(sim, M, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(t, X0, Y0, CR0), null), null); }
let tc = tS; for (let f = 0; f < Math.round((t - tS) / DT); f++) { tc += DT; stepOrbSim(ctl, M, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(tc, X0, Y0, CR0), null), null); }
let back = 0; for (let i = 0; i < M; i++) back = Math.max(back, Math.hypot(sim.x[i] - ctl.x[i], sim.y[i] - ctl.y[i]));
console.log(JSON.stringify({ outDisp, outDw, atNode, kOut, kStart: CRk[0], kEnd: CRk[CRk.length - 1], backDisp: Math.max(...disp2), backDw: Math.max(...dw2),
  kBackStart: kBack[0], kBackEnd: kBack[kBack.length - 1], back, K0: [morphFrame(0, false, {}).K, morphFrame(1, true, {}).K], kMono: kBack.every((v, i) => i === 0 || v >= kBack[i - 1] - 1e-9) }));
""")
        self.assertLess(out["outDisp"], 60)               # px per frame: the arc flight is fast but no star jumps
        self.assertLess(out["outDw"], 0.05)               # the color mix moves smoothly
        self.assertLess(out["atNode"], 3)                 # every star ends on its node
        self.assertTrue(out["kOut"])
        self.assertAlmostEqual(out["kStart"], 1.0, delta=1e-9)   # starts at the stage radius ...
        self.assertAlmostEqual(out["K0"][0], 40, delta=1e-9)     # ... and the stage's spring stiffness: no jump at the start
        self.assertAlmostEqual(out["K0"][1], 40, delta=1e-9)     # the return ends on the stage's stiffness too
        self.assertLess(out["backDisp"], 60)
        self.assertLess(out["backDw"], 0.05)
        self.assertTrue(out["kMono"])
        self.assertAlmostEqual(out["kBackEnd"], 1.0, delta=1e-6)  # unfolds to exactly the stage radius
        self.assertLess(out["back"], 0.5)                 # every star is back exactly where a galaxy that never left is (same clock)

    def test_the_cloud_is_the_same_whenever_you_look(self):
        # nothing thins the mist out over time: after minutes, hours or days at rest the same number of glow and dust particles is
        # drawn, with the same light (the clock only turns the galaxy)
        out = self._run("""
const oc = makeOrbCloud([]), sim = oc.sim;
const calls = [], ctx = { globalAlpha: 1, drawImage(img, x, y, w, h) { calls.push({ a: this.globalAlpha, w }); } };
const frame = (t, dust) => { snapOrbSim(sim, N, galaxyTarget(cloud, P(t, X0, Y0, CR0), null)); calls.length = 0;
  drawMist(ctx, sim, oc, { CR: CR0, zCR: CR0, amul: 1, sz: 1, gr: CR0 }, dust); return [calls.length, calls.reduce((s, c) => s + c.a, 0), calls.reduce((s, c) => s + c.w, 0)]; };
const rows = [0, 60, 600, 3600, 6 * 3600, 86400, 3 * 86400].map(d => ({ d, glow: frame(T0 + d, false), dust: frame(T0 + d, true) }));
console.log(JSON.stringify(rows));
""", paint=True)
        g0, d0 = out[0]["glow"], out[0]["dust"]
        self.assertGreater(g0[0], 1500)                   # (a few very faint ones are skipped)
        self.assertGreater(d0[0], 700)
        for row in out[1:]:
            for k, base in (("glow", g0), ("dust", d0)):
                self.assertAlmostEqual(row[k][0] / base[0], 1.0, delta=0.03, msg=f"count {k} after {row['d']} s")
                self.assertAlmostEqual(row[k][1] / base[1], 1.0, delta=0.06, msg=f"light {k} after {row['d']} s")
                self.assertAlmostEqual(row[k][2] / base[2], 1.0, delta=0.03, msg=f"size {k} after {row['d']} s")

    # ---- the diffuse particles: glow (unresolved starlight) and dust, ordinary members of the cloud ---------------------------------
    def test_cloud_has_star_glow_and_dust_roles_in_a_representative_order(self):
        out = self._run("""
const a = cloud, S = GALAXY_STARS, idxOf = r => a.map((p, i) => i).filter(i => a[i].role === r);
const st = idxOf(ROLE_STAR), gl = idxOf(ROLE_GLOW), du = idxOf(ROLE_DUST);
const wrap = d => { d = ((d % TAU) + TAU) % TAU; return d > Math.PI ? d - TAU : d; };
const off = i => wrap(Math.atan2(a[i].z, a[i].x) - galaxyArmAngle(a[i].arm, Math.hypot(a[i].x, a[i].z)));
const share = (idx, f) => idx.filter(i => f(a[i])).length / idx.length;
const mean = (idx, f) => idx.reduce((s, i) => s + f(i), 0) / idx.length;
const laneDust = du.filter(i => a[i].arm >= 0), laneGlow = gl.filter(i => a[i].arm >= 0 && a[i].r > 0.3);
// prefixes of the diffuse tail: the first 300 (about a third of the drawn mist at the smallest star budget) against the whole
const tail = a.slice(S), t300 = a.slice(S, S + 300);
console.log(JSON.stringify({
  n: a.length, stars: st.length, glow: gl.length, dust: du.length, GN: GALAXY_GLOW_N, DN: GALAXY_DUST_N,
  roleOk: a.every((p, i) => p.role === galaxyRole(i)), starsFirst: a.slice(0, S).every(p => p.role === ROLE_STAR) && tail.every(p => p.role !== ROLE_STAR),
  dust300: t300.filter(p => p.role === ROLE_DUST).length, glow300: t300.filter(p => p.role === ROLE_GLOW).length,
  armAll: share(gl, p => p.arm >= 0), arm300: share(gl.filter(i => i < S + 450), p => p.arm >= 0),
  bulgeAll: share(gl, p => p.r < 0.3 && p.arm < 0), bulge300: share(gl.filter(i => i < S + 450), p => p.r < 0.3 && p.arm < 0),
  dArmAll: share(du, p => p.arm >= 0), dArm150: share(du.filter(i => i < S + 450), p => p.arm >= 0),
  innerEdge: mean(laneDust, off), glowCentered: mean(laneGlow, off),
  inside: tail.every(p => p.r <= 0.99 + 1e-9 && Math.hypot(p.x, p.y, p.z) <= 1.0001),
  rigid: tail.filter(p => p.arm >= 0).every(p => Math.abs(p.sp / GALAXY_PATTERN - 1) < 0.004),
  glowSz: [Math.min(...gl.map(i => a[i].sz)), Math.max(...gl.map(i => a[i].sz))], dustSz: [Math.min(...du.map(i => a[i].sz)), Math.max(...du.map(i => a[i].sz))],
  dustCore: mean(du.filter(i => a[i].r < 0.1), i => a[i].br) / mean(du.filter(i => a[i].r > 0.3), i => a[i].br),
  glowHalo: share(gl, p => p.r > 0.6), glowCore: share(gl, p => p.r < 0.15),
  starsSame: JSON.stringify(buildCloud(S)) === JSON.stringify(a.slice(0, S))
}));
""")
        self.assertEqual(out["n"], out["stars"] + out["glow"] + out["dust"])
        self.assertEqual((out["stars"], out["glow"], out["dust"]), (9000, out["GN"], out["DN"]))
        self.assertAlmostEqual(out["glow"] / out["dust"], 2.0, delta=0.01)   # glow : dust = 2 : 1
        self.assertTrue(out["roleOk"])
        self.assertTrue(out["starsFirst"])                # the stars are the first 9000: a prefix is a whole galaxy
        self.assertAlmostEqual(out["dust300"], 100, delta=1)   # the interleave holds for any prefix of the tail
        self.assertAlmostEqual(out["glow300"], 200, delta=1)
        self.assertAlmostEqual(out["armAll"], out["arm300"], delta=0.08)       # a prefix has the shares of the whole (low-discrepancy)
        self.assertAlmostEqual(out["bulgeAll"], out["bulge300"], delta=0.08)
        self.assertAlmostEqual(out["dArmAll"], out["dArm150"], delta=0.1)
        self.assertGreater(out["armAll"], 0.4)            # glow: on the arms, knots included ...
        self.assertGreater(out["bulgeAll"], 0.03)         # ... in the bulge and the bar ...
        self.assertGreater(out["glowHalo"], 0.05)         # ... out in the disc and the halo
        self.assertGreater(out["glowCore"], 0.03)
        self.assertGreater(out["dArmAll"], 0.6)           # dust: mostly lanes on the arms
        self.assertLess(out["innerEdge"], -0.07)          # ... on their inner edge (the stars there are dimmed the same way)
        self.assertLess(abs(out["glowCentered"]), 0.06)   # the glow follows the arm's centre line
        self.assertTrue(out["inside"])
        self.assertTrue(out["rigid"])                     # arms, bar, rift and knots turn with the pattern, like their stars
        self.assertGreater(out["glowSz"][0], 0.7)
        self.assertGreater(out["dustSz"][0], 0.4)
        self.assertLess(out["dustCore"], 0.5)             # no dark specks in the glare of the core
        self.assertTrue(out["starsSame"])                 # the stars are the same whatever the total

    def test_diffuse_particles_obey_the_same_physics_and_targets_as_stars(self):
        out = self._run("""
const S = GALAXY_STARS, sim = makeOrbSim(N), o = [0, 0, 0, 1];
for (let i = 0; i < N; i++) { sim.x[i] = home.x[i]; sim.y[i] = home.y[i]; sim.z[i] = home.z[i]; }
const err = (s, tg, a, b) => { let m = 0; for (let i = a; i < b; i++) { tg(i, o); m = Math.max(m, Math.hypot(s.x[i] - o[0], s.y[i] - o[1])); } return m; };
let t = settle(sim, N, T0, X0, Y0, CR0, null, 3);
let tg = galaxyTarget(cloud, P(t, X0, Y0, CR0), null);
const rest = [err(sim, tg, 0, S), err(sim, tg, S, N)];
// a kick: a seventh of all particles are shoved 60 px; they all come back like springs
for (let i = 0; i < N; i += 7) { sim.x[i] += 60; sim.y[i] -= 40; }
const kicked = [err(sim, tg, 0, S), err(sim, tg, S, N)];
t = settle(sim, N, t, X0, Y0, CR0, null, 4);
tg = galaxyTarget(cloud, P(t, X0, Y0, CR0), null);
const healed = [err(sim, tg, 0, S), err(sim, tg, S, N)];
// the pointer pushes them away like stars: 30 frames with and without the push from the same state
const clone = s => { const c = makeOrbSim(N); for (const k of ['x', 'y', 'z', 'vx', 'vy', 'vz']) c[k].set(s[k]); return c; };
const pa = clone(sim), pb = clone(sim), push = { x: X0, y: Y0, r: CR0, s: 1800 };
let tp = t;
for (let f = 0; f < 30; f++) {
  tp += DT; const g = galaxyTarget(cloud, P(tp, X0, Y0, CR0), null);
  stepOrbSim(pa, N, DT, ORB_K, orbDamp(ORB_K), g, push); stepOrbSim(pb, N, DT, ORB_K, orbDamp(ORB_K), g, null);
}
const away = (s, i) => Math.hypot(s.x[i] - push.x, s.y[i] - push.y);
const count = (a, b) => { let n = 0, moved = 0; for (let i = a; i < b; i++) { const d0 = away(pb, i); if (d0 > 5 && d0 < push.r * 0.6) { n++; if (away(pa, i) > d0 + 0.5) moved++; } } return [n, moved]; };
// the same spring: one step of a diffuse particle and of a star with the same offset and target are the same motion
console.log(JSON.stringify({ rest, kicked, healed, pushStars: count(0, S), pushTail: count(S, N), prog: Math.max(...Array.from(sim.pw)) }));
""")
        self.assertLess(out["rest"][1], 8)                # at rest the diffuse particles lag their targets like the stars (a few px) ...
        self.assertLess(abs(out["rest"][1] - out["rest"][0]), 4)
        self.assertGreater(out["kicked"][1], 40)          # (the kick is real)
        self.assertLess(out["healed"][1], 8)              # ... and come back from a kick like them
        self.assertLess(abs(out["healed"][1] - out["healed"][0]), 4)
        n, moved = out["pushTail"]
        self.assertGreater(n, 50)                         # a good number of them lies in the pointer's reach
        self.assertGreater(moved / n, 0.9)                # and the pointer pushes them away
        self.assertGreater(out["pushStars"][1] / out["pushStars"][0], 0.9)
        self.assertEqual(out["prog"], 0)                  # nothing is promoted without an agent set

    def test_diffuse_particles_are_continuous_through_every_transition_and_come_back(self):
        out = self._run("""
const S = GALAXY_STARS, A = agentsFor(30, T0);
const sim = makeOrbSim(N), prev = makeOrbSim(N), ctl = makeOrbSim(N);
for (let i = 0; i < N; i++) { sim.x[i] = home.x[i]; sim.y[i] = home.y[i]; sim.z[i] = home.z[i]; }
let t = settle(sim, N, T0, X0, Y0, CR0, null, 3);
const clone = s => { const c = makeOrbSim(N); for (const k of ['x', 'y', 'z', 'vx', 'vy', 'vz']) c[k].set(s[k]); return c; };
const part = (a, b) => { let d = 0; for (let i = a; i < b; i++) d = Math.max(d, Math.hypot(sim.x[i] - prev.x[i], sim.y[i] - prev.y[i])); return d; };
const gap = (s, c, a, b) => { let d = 0; for (let i = a; i < b; i++) d = Math.max(d, Math.hypot(s.x[i] - c.x[i], s.y[i] - c.y[i])); return d; };
let dS = 0, dT = 0;   // the largest per-frame displacement of the stars and of the diffuse tail
const track = () => { dS = Math.max(dS, part(0, S)); dT = Math.max(dT, part(S, N)); copy(sim, prev, N); };
const lap = () => { const r = [dS, dT]; dS = dT = 0; return r; };
const runHome = (s, t0, t1) => { let tt = t0; for (let f = 0; f < Math.round((t1 - t0) / DT); f++) { tt += DT; stepOrbSim(s, N, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(tt, X0, Y0, CR0), null), null); } return tt; };
const res = {};
const t00 = t, base = clone(sim);   // what a galaxy that never left would be
// 1. Atlas entry flight (stars -> agents, camera dive), a while in Atlas, return flight, home again
const rig = entryRig(X0, Y0, CR0, W, H), cam = {}, DUR = 2.3;
copy(sim, prev, N);
let t1 = t;
for (let f = 0; f * DT / DUR <= 1; f++) {
  const u = f * DT / DUR; t = t1 + f * DT; entryFrame(rig, u, cam);
  promoStep(A, DT, k => promoGoal(k, A.n, u, true)); syncPromo(A, sim, N, DT);
  stepOrbSim(sim, N, DT, 44, orbDamp(44), galaxyTarget(cloud, P(t, cam.cx, cam.cy, cam.CR), A), null);
  track();
}
res.entry = lap();
t = settle(sim, N, t, cam.cx, cam.cy, cam.CR, A, 3); copy(sim, prev, N); lap();
const tgA = galaxyTarget(cloud, P(t, cam.cx, cam.cy, cam.CR), A), oo = [0, 0, 0, 1], atlasErr = [0, 0];
for (let i = 0; i < N; i++) { tgA(i, oo); const k = i < S ? 0 : 1; atlasErr[k] = Math.max(atlasErr[k], Math.hypot(sim.x[i] - oo[0], sim.y[i] - oo[1])); }
res.atlasErr = atlasErr;
const R = { cx0: cam.cx, cy0: cam.cy, CR0: cam.CR, sz0: cam.sz, gx: X0, gy: Y0, gCR: CR0 }, rc = {};
let t2 = t;
for (let f = 0; f * DT / DUR <= 0.86; f++) {
  const u = f * DT / DUR; t = t2 + f * DT; returnFrame(R, u, rc);
  promoStep(A, DT, k => promoGoal(k, A.n, u, false)); syncPromo(A, sim, N, DT);
  stepOrbSim(sim, N, DT, 26, orbDamp(26), galaxyTarget(cloud, P(t, rc.cx, rc.cy, rc.CR), A), null);
  track();
}
res.ret = lap();
for (let f = 0; f < 4 * 60; f++) { t += DT; stepOrbSim(sim, N, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(t, X0, Y0, CR0), null), null); }
runHome(base, t00, t);
res.roundTrip = [gap(sim, base, 0, S), gap(sim, base, S, N)];
// 2. Second Brain morph (every particle seeks a node) and back
const NODES = 37, nodeOf = i => Math.floor(((i * 0.6180339887) % 1) * NODES), NX = j => 300 + (j % 7) * 90, NY = j => 200 + Math.floor(j / 7) * 90;
const mo = {}, DURM = OS_FLY_MS / 1000, tM = t, base2 = clone(sim);
copy(sim, prev, N);
let wd = 0, wPrev = new Float32Array(N), tm = tM;
for (let f = 0; f * DT / DURM <= 1; f++) {
  const u = f * DT / DURM; tm = tM + f * DT; morphFrame(u, false, mo);
  const hm = galaxyTarget(cloud, P(tm, X0, Y0, CR0 * mo.k), null);
  stepOrbSim(sim, N, DT, mo.K, orbDamp(mo.K), (i, o) => { hm(i, o); morphPoint(o, morphW(u, i, false), NX(nodeOf(i)), NY(nodeOf(i)), i); }, null);
  for (let i = S; i < N; i++) { const w = morphW(u, i, false); wd = Math.max(wd, Math.abs(w - wPrev[i])); wPrev[i] = w; }
  track();
}
res.morph = lap(); res.morphDw = wd;
let atNode = 0; for (let i = S; i < N; i++) atNode = Math.max(atNode, Math.hypot(sim.x[i] - NX(nodeOf(i)), sim.y[i] - NY(nodeOf(i))));
res.atNode = atNode;
tm += 5; for (let i = 0; i < N; i++) { sim.x[i] = NX(nodeOf(i)); sim.y[i] = NY(nodeOf(i)); sim.z[i] = 0; sim.vx[i] = sim.vy[i] = sim.vz[i] = 0; }
copy(sim, prev, N); wPrev.fill(1); wd = 0; const tB = tm;
for (let f = 0; f * DT / DURM <= 0.86; f++) {
  const u = f * DT / DURM; tm = tB + f * DT; morphFrame(u, true, mo);
  const hm = galaxyTarget(cloud, P(tm, X0, Y0, CR0 * mo.k), null);
  stepOrbSim(sim, N, DT, mo.K, orbDamp(mo.K), (i, o) => { hm(i, o); morphPoint(o, morphW(u, i, true), NX(nodeOf(i)), NY(nodeOf(i)), i); }, null);
  for (let i = S; i < N; i++) { const w = morphW(u, i, true); wd = Math.max(wd, Math.abs(w - wPrev[i])); wPrev[i] = w; }
  track();
}
res.morphBack = lap(); res.morphBackDw = wd;
for (let f = 0; f < 4 * 60; f++) { tm += DT; stepOrbSim(sim, N, DT, ORB_K, orbDamp(ORB_K), galaxyTarget(cloud, P(tm, X0, Y0, CR0), null), null); }
runHome(base2, tM, tm);
res.morphRoundTrip = [gap(sim, base2, 0, S), gap(sim, base2, S, N)];
console.log(JSON.stringify(res));
""")
        # the same per-frame displacement bound as the stars (px per frame), in every flight
        for key, bound in (("entry", 40), ("ret", 40), ("morph", 60), ("morphBack", 60)):
            stars, tail = out[key]
            self.assertLess(tail, bound, key)
            self.assertLessEqual(tail, stars * 1.25 + 2, key)
        stars, tail = out["atlasErr"]                     # in Atlas the diffuse particles sit on their targets like the stars
        self.assertLessEqual(tail, stars * 1.25 + 2)      # (a spring following the rotation lags by a few px, more on the outer arms)
        self.assertLess(tail, 16)
        self.assertLess(out["morphDw"], 0.05)             # the node mix moves smoothly
        self.assertLess(out["morphBackDw"], 0.05)
        self.assertLess(out["atNode"], 3)                 # on arrival every diffuse particle is on its node, too
        for key in ("roundTrip", "morphRoundTrip"):
            self.assertLess(out[key][1], 0.5, key)        # back exactly where a galaxy that never left is
            self.assertLess(out[key][0], 0.5, key)

    # ---- the budget never shrinks: no governor, no floor, no fade-out of the tail ----------------------------------------------
    def test_no_governor_or_budget_remains(self):
        for name in ("galaxyGovernor", "galaxyStepDown", "galaxyStepUp", "galaxyBudgetDown", "GALAXY_MIN", "GALAXY_KEEP", "GALAXY_FADE", "GALAXY_BUDGET"):
            self.assertNotIn(name, JS, name)
        for pat in (r"\bGOV\b", r"\.gov\b", r"\bmf\b", r"S\.ft\s*>", r"c\.ft\s*>"):
            self.assertNotRegex(JS, pat)
        # the whole cloud is the budget, fixed in the source; the size reference of the mist is the only shared state
        self.assertIn("const GALAXY_STARS = 9000, GALAXY_GLOW_N = 1800, GALAXY_DUST_N = 900;", JS)
        self.assertIn("const GALAXY_N = GALAXY_STARS + GALAXY_GLOW_N + GALAXY_DUST_N;", JS)
        self.assertIn("const GALAXY_LIVE = { gr: 0 };", JS)
        self.assertIn("function drawMist(ctx, sim, oc, o, dust)", JS)      # no budget argument: it draws every particle of its lists
        self.assertIn("const GALAXY_POOL = 680;", JS)

    def test_frames_are_capped_not_thinned(self):
        # what keeps the frame time down is the painter and the frame cap, never fewer particles: the stage and the Atlas view
        # run at most ~75 fps (144 Hz screens draw every other frame) and a hidden or scrolled-out stage does no work at all
        self.assertIn("if (now - S.last < 12.5) return;", JS)
        self.assertIn("if (now - c.last < 12.5) return;", JS)
        stage = JS[JS.index("  function frame(now) {\n    S.raf = requestAnimationFrame(frame);"):]
        stage = stage[: stage.index("S.raf = RM.matches ? 0 : requestAnimationFrame(frame);")]
        self.assertIn("document.hidden || !root.isConnected || !S.vis", stage)
        self.assertIn("stepOrbSim(sim, cloud.length, dt, ORB_K", stage)    # every particle is stepped, every frame
        self.assertNotRegex(stage, r"cloud\.length\s*[*/-]")              # ... of the whole cloud, never a fraction of it

    # ---- the per-particle targets: the same orbits, computed from typed arrays --------------------------------------------------
    def test_galaxy_target_equals_the_orbit_of_every_particle(self):
        out = self._run("""
const S1 = cloudSoA(cloud), S2 = cloudSoA(cloud), other = buildCloud(100), S3 = cloudSoA(other);
const o = [0, 0, 0, 1], ref = [0, 0, 0, 1];
const worst = t => { const rot = homeRot(t), tg = galaxyTarget(cloud, P(t, X0, Y0, CR0), null); let m = 0;
  for (let i = 0; i < N; i++) { tg(i, o); orbHome(cloud[i], t, rot, X0, Y0, CR0, ref); m = Math.max(m, Math.hypot(o[0] - ref[0], o[1] - ref[1], o[2] - ref[2])); }
  return m; };
console.log(JSON.stringify({ same: S1 === S2, distinct: S1 !== S3, n: [S1.x.length, S3.x.length], f64: S1.x instanceof Float64Array && S1.sp instanceof Float64Array,
  worst: [0, 1.5, T0, 3600, 86400, 3 * 86400].map(worst) }));
""")
        self.assertTrue(out["same"])                      # computed once per cloud
        self.assertTrue(out["distinct"])
        self.assertEqual(out["n"], [11700, 100])
        self.assertTrue(out["f64"])
        for w in out["worst"]:
            self.assertLess(w, 1e-6)                      # px: the angle-addition shortcut is the orbit to rounding, at any time

    # ---- the layer of small stars -----------------------------------------------------------------------------------------------
    DOT_SIM = """
const mkCtx = (w, h, k = 1.25) => ({ canvas: { width: w, height: h }, globalAlpha: 1, fillStyle: '', blits: [], rects: [],
  getTransform: () => ({ a: k, b: 0, c: 0, d: k, e: 0, f: 0 }), save() {}, restore() {}, setTransform() {},
  fillRect(x, y, w2, h2) { this.rects.push({ x, y, w: w2, h: h2, a: this.globalAlpha, c: this.fillStyle }); },
  drawImage(cv, sx, sy, sw, sh, dx, dy, dw, dh) { this.blits.push({ img: cv.img, sx, sy, sw, sh, dx, dy, dw, dh }); } });
const frame = (ctx, stars) => { const D = dotBegin(ctx); for (const s of stars) dotAdd(D, s.x, s.y, s.s, s.a, s.c === undefined ? 0 : s.c); dotFlush(ctx, D); return ctx.blits[ctx.blits.length - 1]; };
const alphaSum = b => { let t = 0; for (let i = 3; i < b.img.data.length; i += 4) t += b.img.data[i]; return t; };
// the light a star should put in the layer: alpha x area of its two squares, in device pixels, times 255
const light = (s, k = 1.25) => 255 * s.a * dotGain(s.s) * (DOT_CORE_A * (s.s * DOT_CORE * k) ** 2 + DOT_HALO_A * (s.s * DOT_HALO * k) ** 2);
"""

    def test_small_star_layer_carries_the_light_of_the_squares_and_is_clean_between_frames(self):
        out = self._run(self.DOT_SIM + """
const A = [], B = [];
for (let i = 0; i < 300; i++) { A.push({ x: 20 + (i * 37) % 300, y: 20 + (i * 53) % 200, s: 1 + (i % 6), a: 0.35 + (i % 4) * 0.15, c: i % 4 }); B.push({ x: 25 + (i * 41) % 290, y: 30 + (i * 29) % 210, s: 1.5 + (i % 5), a: 0.6, c: (i + 2) % 5 }); }
const ctx = mkCtx(500, 400);
const a1 = frame(ctx, A), copyA = Uint8ClampedArray.from(a1.img.data);
const b = frame(ctx, B);
const a2 = frame(ctx, A);
let same = a2.img.data.length === copyA.length; for (let i = 0; same && i < copyA.length; i++) if (a2.img.data[i] !== copyA[i]) same = false;
const expA = A.reduce((s, q) => s + light(q), 0), expB = B.reduce((s, q) => s + light(q), 0);
// one star: where is its light, where is the blit
const one = mkCtx(500, 400), o1 = frame(one, [{ x: 100, y: 80, s: 4, a: 1, c: 0 }]);
let sx = 0, sy = 0, sa = 0; const IW = o1.img.width;
for (let i = 0; i < o1.img.data.length; i += 4) { const a = o1.img.data[i + 3]; if (a) { const p = i / 4; sx += (p % IW + 0.5) * a; sy += (Math.floor(p / IW) + 0.5) * a; sa += a; } }
console.log(JSON.stringify({ same, ratioA: alphaSum(a1) / expA, ratioB: alphaSum(b) / expB, ratioA2: alphaSum(a2) / expA,
  cx: sx / sa + o1.dx, cy: sy / sa + o1.dy, wantX: 100 * 1.25, wantY: 80 * 1.25, blits: ctx.blits.length, noRects: ctx.rects.length,
  gain: [dotGain(1), dotGain(3), dotGain(STAR_DOT), dotGain(50)], starDot: STAR_DOT }));
""", paint=True)
        self.assertTrue(out["same"])                       # a frame leaves nothing behind: the same stars give the same layer
        for key in ("ratioA", "ratioB", "ratioA2"):
            self.assertAlmostEqual(out[key], 1.0, delta=0.04, msg=key)   # the layer holds the light of the squares (8-bit sums)
        self.assertAlmostEqual(out["cx"], out["wantX"], delta=0.25)      # at the right place, in device pixels
        self.assertAlmostEqual(out["cy"], out["wantY"], delta=0.25)
        self.assertEqual(out["blits"], 3)                  # one blit per frame (three frames)
        self.assertEqual(out["noRects"], 0)                # and no rectangle at all
        self.assertEqual(out["gain"][:2], [1, 1])
        self.assertAlmostEqual(out["gain"][2], 1.1, delta=0.011)         # the sprite of a bigger star holds a little more light
        self.assertLessEqual(out["gain"][3], 1.1)
        self.assertGreaterEqual(out["starDot"], 4.5)

    def test_small_stars_fall_back_to_rects_where_a_layer_would_be_too_big(self):
        out = self._run(self.DOT_SIM + """
const stars = [{ x: 10, y: 10, s: 3, a: 0.8, c: 0 }, { x: 1900, y: 1000, s: 3, a: 0.8, c: 1 }, { x: 900, y: 500, s: 2, a: 0.5, c: DOT_WHITE }];
const ctx = mkCtx(2600, 1500), r = frame(ctx, stars);
const area = ctx.rects.reduce((s, q) => s + q.a * q.w * q.h, 0);   // user-space area x alpha
const want = stars.reduce((s, q) => s + q.a * dotGain(q.s) * (DOT_CORE_A * (q.s * DOT_CORE) ** 2 + DOT_HALO_A * (q.s * DOT_HALO) ** 2), 0);
console.log(JSON.stringify({ blit: !!r, nRects: ctx.rects.length, ratio: area / want, colors: [...new Set(ctx.rects.map(q => q.c))].sort() }));
""", paint=True)
        self.assertFalse(out["blit"])                      # no layer of that size
        self.assertEqual(out["nRects"], 6)                 # a core and a halo per star
        self.assertAlmostEqual(out["ratio"], 1.0, delta=0.001)
        self.assertIn("rgb(255,255,255)", out["colors"])  # the white of the flakes and cluster cores
        self.assertEqual(len(out["colors"]), 3)

    def test_particle_painter_draws_sprites_per_role_sized_like_stars(self):
        out = self._run("""
const oc = makeOrbCloud([]), sim = oc.sim, S = GALAXY_STARS;
snapOrbSim(sim, N, galaxyTarget(cloud, P(T0, X0, Y0, CR0), null));
const calls = [];
const ctx = { globalAlpha: 1, drawImage(img, x, y, w, h) { calls.push({ img, x, y, w, h, a: this.globalAlpha }); } };
const run = (dust, o) => { calls.length = 0; drawMist(ctx, sim, oc, Object.assign({ CR: CR0, zCR: CR0, amul: 1, sz: 1, gr: CR0 }, o), dust); return calls.slice(); };
const mean = a => a.reduce((s, v) => s + v, 0) / a.length;
const g = run(false), d = run(true);
const all = [].concat(...Array.from(oc.glowBy, l => Array.from(l)));
const ascending = l => Array.from(l).every((v, k, a) => k === 0 || v > a[k - 1]);
// one soft sprite per glow colour and one dust sprite; the stars are not in these lists
const glowSet = new Set(oc.sprMist), parts = [oc.dustIdx, ...oc.glowBy];
// the same particles at another zoom: matched by their centre (the positions do not change), compared by size
const key = c => Math.round((c.x + c.w / 2) * 100) + ',' + Math.round((c.y + c.h / 2) * 100);
const ratio = (A, B) => { const mp = new Map(B.map(c => [key(c), c.w])), r = []; for (const c of A) { const w = mp.get(key(c)); if (w) r.push(c.w / w); } return mean(r); };
const dive = ratio(run(false, { CR: CR0 * 3 }), g), flat = ratio(run(false, { CR: CR0 * 3, gr: CR0 * 3 }), g);
const mix = new Float32Array(N).fill(1);
// a leftover budget field is ignored: every particle of the lists is drawn whatever else the caller passes
const extra = run(false, { mf: 700, n: 700 }).length;
console.log(JSON.stringify({ gl: g.length, du: d.length, GN: GALAXY_GLOW_N, DN: GALAXY_DUST_N, nGlowIdx: all.length, nDustIdx: oc.dustIdx.length,
  glowSprites: g.every(c => glowSet.has(c.img)) && new Set(g.map(c => c.img)).size > 3, dustSprite: d.every(c => c.img === oc.sprDust),
  ascending: parts.every(ascending), starsOut: all.every(i => i >= S) && Array.from(oc.dustIdx).every(i => i >= S), extra, dive, flat,
  gone: [run(false, { mix }).length, run(true, { mix }).length, run(false, { amul: 0 }).length, run(true, { amul: 0 }).length],
  alpha: g.every(c => c.a > 0 && c.a <= 1) && d.every(c => c.a > 0 && c.a <= 1), maxGlowA: Math.max(...g.map(c => c.a)), maxDustA: Math.max(...d.map(c => c.a)),
  big: mean(g.map(c => c.w)) / mean(d.map(c => c.w)), zs: MIST_ZS }));
""", paint=True)
        self.assertEqual(out["nGlowIdx"], out["GN"])
        self.assertEqual(out["nDustIdx"], out["DN"])
        self.assertTrue(out["ascending"])                 # per role and colour in index order
        self.assertTrue(out["starsOut"])
        self.assertTrue(out["glowSprites"])
        self.assertTrue(out["dustSprite"])
        self.assertGreater(out["gl"], 0.85 * out["GN"])   # (a few very faint ones are skipped)
        self.assertLessEqual(out["gl"], out["GN"])
        self.assertGreater(out["du"], 0.8 * out["DN"])
        self.assertLessEqual(out["du"], out["DN"])
        self.assertEqual(out["extra"], out["gl"])         # no budget anywhere: the lists are drawn in full
        self.assertAlmostEqual(out["dive"], 3 ** out["zs"], delta=0.02)   # 3x zoom, home radius as reference: sizes grow by the mild factor only ...
        self.assertAlmostEqual(out["flat"], 3.0, delta=0.05)              # ... and follow the reference radius when that changes
        self.assertEqual(out["gone"], [0, 0, 0, 0])       # on arrival at the nodes / faded out: nothing is left to draw
        self.assertTrue(out["alpha"])
        self.assertLess(out["maxGlowA"], 0.3)             # faint, many: never a hard disc
        self.assertGreater(out["big"], 1.5)               # glow is the big role, dust the medium one

    def test_no_bitmap_layers_remain_and_the_passes_are_ordered(self):
        for name in ("buildGalaxyTexture", "drawDiscLayer", "galaxyTextures", "GALAXY_TEX", "GALAXY_GLOW_A", "GALAXY_DUST_A", "mixOff"):
            self.assertNotIn(name, JS)
        scene = JS[JS.index("function drawCloudScene("): JS.index("// ---- The GPU painter of the cloud")]
        mist = JS[JS.index("function drawMist("): JS.index("// One frame of the cloud, bottom to top")]
        # the GPU painter comes first and, when it paints, the canvas painter does not run at all
        gpu = scene.index("if (glxScene(ctx, oc, o, amul, fade)) return;")
        # glow under the stars (additive), then the stars, then the dust over them (source-over): two passes over the same arrays
        a, b, c = scene.index("drawMist(ctx, sim, oc, mist, false)"), scene.index("drawOrbSim("), scene.index("drawMist(ctx, sim, oc, mist, true)")
        self.assertLess(gpu, a)
        self.assertLess(a, b)
        self.assertLess(b, c)
        self.assertLess(scene.index("'source-over'"), c)
        # no per-particle gradient, canvas or image data anywhere in the painters of the diffuse particles
        for banned in ("createRadialGradient", "createLinearGradient", "createElement", "getImageData", "putImageData", "ImageData"):
            self.assertNotIn(banned, mist + scene)
        self.assertEqual(mist.count("drawImage("), 1)      # one sprite blit per particle, nothing else

    # ---- the GPU painter ----------------------------------------------------------------------------------------------------------
    # A stand-in for WebGL2 that records every call: constants are their own names, locations are the names of what they locate.
    GL_SIM = """
const glCalls = [];
const mkGL = () => new Proxy({}, { get(t, k) {
  if (typeof k !== 'string') return undefined;
  if (k === 'getError') return () => 'NO_ERROR';
  if (k === 'getParameter') return () => 8192;
  if (k === 'getShaderParameter' || k === 'getProgramParameter') return () => true;
  if (k === 'getAttribLocation' || k === 'getUniformLocation') return (p, n) => n;
  if (/^[A-Z][A-Z0-9_]+$/.test(k)) return k;
  if (k.startsWith('create')) return () => { glCalls.push([k]); return { made: k }; };
  return (...a) => { glCalls.push([k, ...a]); };
} });
const gctx = (w, h, T) => ({ canvas: { width: w, height: h }, globalAlpha: 1, globalCompositeOperation: 'lighter', draws: [], rects: 0,
  getTransform: () => T || { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }, save() {}, restore() {}, setTransform() {}, fillRect() { this.rects++; },
  drawImage(img, ...a) { this.draws.push({ img, op: this.globalCompositeOperation, a }); } });
const scene = o => Object.assign({ ox: X0, oy: Y0, CR: CR0, t: T0, rot: homeRot(T0), glow: 1, fa: 0.6, sz: 1 }, o);
const calls = name => glCalls.filter(c => c[0] === name);
const passes = () => calls('uniform1f').filter(c => c[1] === 'uPass').map(c => c[2]);
const insts = () => calls('drawArraysInstanced').map(c => c[4]);
globalThis.GL = mkGL();
const oc = makeOrbCloud([]), sim = oc.sim;
snapOrbSim(sim, N, galaxyTarget(cloud, P(T0, X0, Y0, CR0), null));
"""

    def test_gpu_painter_paints_the_cloud_in_three_instanced_passes(self):
        out = self._run(self.GL_SIM + """
const c1 = gctx(1440, 800);
drawCloudScene(c1, oc, scene());
const res = { passes: passes(), inst: insts(), N, bright: oc.bright.length, ops: c1.draws.map(d => d.op), box: c1.draws[0].a, same: c1.draws.every(d => d.img === GLX.cv),
  blends: calls('blendFunc').map(c => c[1] + '>' + c[2]), rects: c1.rects, state: GLX.state,
  up: ['x', 'y', 'z', 'pw'].map(k => calls('bufferSubData').some(c => c[3] === sim[k])) };
// the next frame: no new program, no new texture, the same three passes
glCalls.length = 0;
const c2 = gctx(1440, 800);
drawCloudScene(c2, oc, scene({ t: T0 + 1 }));
res.again = { passes: passes(), inst: insts(), creates: glCalls.filter(c => /^(create|compile|link|texStorage)/.test(c[0])).length, draws: c2.draws.length };
// a device-pixel scale and an offset in the transform reach the shader; the destination only ever grows
glCalls.length = 0;
const T = { a: 1.25, b: 0, c: 0, d: 1.25, e: 10, f: 20 }, c3 = gctx(1800, 1000, T);
drawCloudScene(c3, oc, scene());
res.xf = calls('uniform4f').filter(c => c[1] === 'uXf').map(c => c.slice(2));
res.res = calls('uniform2f').filter(c => c[1] === 'uRes').map(c => c.slice(2));
res.grown = [GLX.w, GLX.h];
drawCloudScene(gctx(1440, 800), oc, scene());
res.kept = [GLX.w, GLX.h];
console.log(JSON.stringify(res));
""", paint=True)
        self.assertEqual(out["state"], 1)
        self.assertEqual(out["passes"], [0, 1, 3])        # glow, stars, dust (pass 2 is the Second Brain's colour mix)
        # the small list (cluster stars: two entries each) and then one instanced draw per pass over the whole cloud
        self.assertEqual(out["inst"], [2 * out["bright"], out["N"], out["N"], out["N"]])
        self.assertEqual(out["blends"], ["ONE>ONE", "ONE>ONE_MINUS_SRC_ALPHA"])   # additive, then the dust over everything
        self.assertEqual(out["ops"], ["lighter", "source-over"])                   # composited the way the canvas path draws
        self.assertTrue(out["same"])
        self.assertEqual(out["box"], [0, 0, 1440, 800, 0, 0, 1440, 800])
        self.assertEqual(out["rects"], 0)                 # nothing is drawn by the 2D canvas, particle by particle
        self.assertEqual(out["up"], [True] * 4)           # the simulation's own arrays are what is uploaded
        self.assertEqual(out["again"]["passes"], [0, 1, 3])
        self.assertEqual(out["again"]["inst"], out["inst"])
        self.assertEqual(out["again"]["creates"], 0)
        self.assertEqual(out["again"]["draws"], 2)
        self.assertEqual(out["xf"][0], [1.25, 1.25, 10, 20])
        self.assertEqual(out["res"][0], [1800, 1000])
        self.assertEqual(out["grown"], [1800, 1000])
        self.assertEqual(out["kept"], [1800, 1000])       # a smaller destination reuses the buffer

    def test_gpu_painter_agents_and_the_second_brain_colours(self):
        out = self._run(self.GL_SIM + """
const res = {};
drawCloudScene(gctx(1440, 800), oc, scene());   // init
// two stars on their way to being agents: four entries each in the small list, and the pass over all stars skips them
sim.pw[5] = 0.6; sim.gc[5] = 2; sim.pw[9] = 0.2; sim.gc[9] = 1;
glCalls.length = 0;
drawCloudScene(gctx(1440, 800), oc, scene());
res.nq = GLX.nq / 8; res.bright = oc.bright.length;
// a cluster star beyond the half of its promotion is an agent: four entries instead of its two
const b = oc.bright[0]; sim.pw[b] = 0.9;
drawCloudScene(gctx(1440, 800), oc, scene());
res.nq2 = GLX.nq / 8;
sim.pw.fill(0);
// the flight into the Second Brain: every particle carries the colour of its node (an atlas cell, uploaded once)
const mix = new Float32Array(N).fill(0.4), alt = new Array(N).fill(oc.sprG[0]);
glCalls.length = 0;
drawCloudScene(gctx(1440, 800), oc, scene({ mix, alt }));
res.mixPasses = passes(); res.mixUploads = calls('texSubImage2D').length; res.mixSub = calls('bufferSubData').filter(c => c[3] === mix).length;
glCalls.length = 0;
drawCloudScene(gctx(1440, 800), oc, scene({ mix, alt }));
res.mixUploads2 = calls('texSubImage2D').length;
console.log(JSON.stringify(res));
""", paint=True)
        self.assertEqual(out["nq"], 4 * 2 + 2 * out["bright"])
        self.assertEqual(out["nq2"], 4 * 3 + 2 * (out["bright"] - 1))
        self.assertEqual(out["mixPasses"], [0, 1, 2, 3])
        self.assertEqual(out["mixUploads"], 1)            # the node colour goes into the atlas ...
        self.assertEqual(out["mixUploads2"], 0)           # ... once
        self.assertEqual(out["mixSub"], 1)

    def test_gpu_painter_falls_back_to_the_canvas_painter(self):
        out = self._run(self.GL_SIM + """
const res = {};
const ok = () => glxScene(gctx(1440, 800), oc, scene(), 1, 1);
res.ok = ok();
res.rotated = glxScene(gctx(1440, 800, { a: 1, b: 0.2, c: -0.2, d: 1, e: 0, f: 0 }), oc, scene(), 1, 1);
res.flipped = glxScene(gctx(1440, 800, { a: -1, b: 0, c: 0, d: 1, e: 0, f: 0 }), oc, scene(), 1, 1);
res.big = glxScene(gctx(9000, 800), oc, scene(), 1, 1);
res.foreign = glxScene(gctx(1440, 800), Object.assign({}, oc, { cloud: buildCloud(N) }), scene(), 1, 1);
res.short = glxScene(gctx(1440, 800), Object.assign({}, oc, { sim: makeOrbSim(100) }), scene(), 1, 1);
res.empty = glxScene(gctx(0, 0), oc, scene(), 1, 1);
res.stillOk = ok();
// a lost context: the canvas painter takes over at once, with the same scene
GLX.cv.on.webglcontextlost({ preventDefault() {} });
res.lostState = GLX.state; res.lost = ok();
const c = gctx(1440, 800); glCalls.length = 0;
drawCloudScene(c, oc, scene());
res.lostDraws = c.draws.length; res.lostGl = insts().length;
// the opt-out of the page (aos.gl = "0"): no WebGL context is even asked for
GLX.state = 0; globalThis.STORE = { gl: '0' }; globalThis.GL = null;
const c2 = gctx(1440, 800);
drawCloudScene(c2, oc, scene());
res.optOut = GLX.state; res.optDraws = c2.draws.length;
// no WebGL2 at all (a software renderer refuses it): the same fallback, silently
GLX.state = 0; globalThis.STORE = {}; globalThis.GL = null;
const c3 = gctx(1440, 800);
drawCloudScene(c3, oc, scene());
res.noGL = GLX.state; res.noGLDraws = c3.draws.length;
// a shader that does not compile: the same
GLX.state = 0; globalThis.GL = new Proxy(mkGL(), { get(t, k) { return k === 'getShaderParameter' ? () => false : t[k]; } });
res.badShader = glxScene(gctx(1440, 800), oc, scene(), 1, 1); res.badState = GLX.state;
console.log(JSON.stringify(res));
""", paint=True)
        self.assertTrue(out["ok"])
        for k in ("rotated", "flipped", "big", "foreign", "short", "empty"):
            self.assertFalse(out[k], k)                   # each of them is left to the canvas painter ...
        self.assertTrue(out["stillOk"])                   # ... without costing the GPU painter its state
        self.assertEqual(out["lostState"], -1)
        self.assertFalse(out["lost"])
        self.assertEqual(out["lostGl"], 0)                # no GL call after the loss
        self.assertGreater(out["lostDraws"], 1000)        # the canvas painter: a sprite per particle (and the layer of small stars)
        self.assertEqual(out["optOut"], -1)
        self.assertGreater(out["optDraws"], 1000)
        self.assertEqual(out["noGL"], -1)
        self.assertGreater(out["noGLDraws"], 1000)
        self.assertFalse(out["badShader"])
        self.assertEqual(out["badState"], -1)

    def test_gpu_painter_source_contract(self):
        gpu = JS[JS.index("// ---- The GPU painter of the cloud"): JS.index("function buildFlakes(")]
        # WebGL2 only, and only a real GPU: a software renderer takes the canvas path
        self.assertGreaterEqual(gpu.count("#version 300 es"), 2)
        self.assertIn("failIfMajorPerformanceCaveat: true", gpu)
        self.assertIn("getContext('webgl2'", gpu)
        # the opt-out goes through the page's store (aos.gl), nowhere else
        self.assertIn("store.get('gl') === '0'", gpu)
        self.assertNotIn("localStorage.", gpu)           # (the comment may name it; the code does not touch it)
        # every reason not to paint is a plain `return false` before anything is touched
        sc = gpu[gpu.index("function glxScene("):]
        for cond in ("GLX.state < 0", "oc.cloud !== GALAXY", "T.b || T.c", "W > GLX.max", "sim.n !== N"):
            self.assertIn(cond, sc)
        self.assertIn("webglcontextlost", gpu)
        self.assertIn("GLX.state = -1", gpu)
        # the instanced draws: the small list, then glow, stars, (morph colours), dust: one draw per pass, never one per particle
        self.assertEqual(gpu.count("drawArraysInstanced("), 5)
        self.assertNotIn("drawArrays(", gpu.replace("drawArraysInstanced(", ""))
        self.assertLess(sc.index("gl.blendFunc(gl.ONE, gl.ONE)"), sc.index("gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)"))
        self.assertLess(sc.index("'lighter'"), sc.index("ctx.globalCompositeOperation = 'source-over'"))
        # the shaders take their numbers from the same constants as the canvas painter, so the two cannot drift apart
        for const in ("DOT_CORE_A", "DOT_HALO_A", "STAR_DOT", "STAR_A"):
            self.assertRegex(gpu, r"\${glxF\(" + const + r"\)}", const)
        self.assertRegex(gpu, r"\${glxF\(DOT_CORE \* 0\.5\)}")
        self.assertRegex(gpu, r"\${glxF\(DOT_HALO \* 0\.5\)}")
        # ... and the same formulas of depth, size, alpha and twinkle as drawOrbSim / drawMist
        vs = gpu[gpu.index("const GLX_VS_P"): gpu.index("const GLX_VS_Q")]
        orb = JS[JS.index("function drawOrbSim("): JS.index("// The diffuse particles of one role")]
        mist = JS[JS.index("function drawMist("): JS.index("// One frame of the cloud, bottom to top")]
        for text in (orb, mist, vs):
            self.assertIn("2.6 / (2.6 - zz)", text)       # perspective of the depth
        self.assertIn("(0.3 + 0.65 * dz) * tw * amul * p.br", orb)
        self.assertIn("(0.3 + 0.65 * dz) * tw * uAmul * aS.x", vs)
        self.assertIn("(1 - 0.35 * w)", orb)
        self.assertIn("(1.0 - 0.35 * w)", vs)
        self.assertIn("p.sz * 2.5 * per * sz", orb)
        self.assertIn("aS.y * 2.5 * per * uSz", vs)
        self.assertIn("(0.45 + 0.55 * dz) * (1 - w) * (1 - w)", mist)
        self.assertIn("(0.45 + 0.55 * dz) * (1.0 - w) * (1.0 - w)", vs)
        self.assertIn("a < 0.002", mist)
        self.assertIn("< 0.002) a = 0.0", vs)
        # agent stars are taken out of the pass over all stars: they are in the small list with their own look
        self.assertIn("aPw <= 0.003", vs)
        self.assertIn("if (!(g > 0.003)) continue;", sc)


if __name__ == "__main__":
    unittest.main()
