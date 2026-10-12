"""OS home page: wiring (static) and pure functions (with Node, if installed)."""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.helpers import JS_I18N

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "aos" / "web" / "dashboard.html"


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _script() -> str:
    return re.search(r"<script>\n(.*?)</script>", _html(), re.S).group(1)


def _home_block(js: str) -> str:
    return js[js.index("const MODEL_COLOR = {"): js.index("const VIEW_MODS = {")]


class HomeStaticTests(unittest.TestCase):
    def test_tabs_and_default_theme(self):
        js = _script()
        self.assertIn("{ id: 'today', label: 'OS' }", js)
        self.assertIn("document.documentElement.getAttribute('data-theme') || 'dark'", js)

    def test_default_sides_cover_the_reference_layout(self):
        js = _script()
        region = js[js.index("const WIDGETS = ["): js.index("const LAYOUT_V")]
        sides = dict(re.findall(r"id: '([\w-]+)'.*?side: '([lr])'", region))
        # the greeting and the key figures on the left, the calendar and what needs doing on the right; the rest spread evenly
        for left in ("hero", "k-notes", "k-needs", "k-routines", "k-reach", "goals", "health", "upcoming", "apps"):
            self.assertEqual(sides[left], "l", left)
        for right in ("calendar", "deadlines", "needs", "skills", "routines", "artifacts", "recent", "runs"):
            self.assertEqual(sides[right], "r", right)
        self.assertRegex(region, r"id: 'costs'.*off: true")   # costs are not on the home page by default
        self.assertIn("off: true, build: clockCard", region)   # the old clocks card now lives in the calendar
        # every widget has S / M / L sizes as [columns, rows] and a default size that exists
        checked = 0
        for line in region.splitlines():
            m = re.search(r"id: '([\w-]+)'.*sizes: \[(.*?)\]\](?:, min: \[(\d+), (\d+)\])?, size: (\d)", line)
            if m:
                n = len(re.findall(r"\[\d+, \d+\]", m.group(2) + "]"))
                self.assertTrue(1 <= n <= 3 and int(m.group(5)) < n, m.group(1))
                if m.group(3):   # the smallest size a widget is dragged to is never larger than its S size
                    first = re.match(r"\[(\d+), (\d+)", m.group(2))
                    self.assertLessEqual(int(m.group(3)), int(first.group(1)), m.group(1))
                    self.assertLessEqual(int(m.group(4)), int(first.group(2)) + 2, m.group(1))
                checked += 1
        self.assertEqual(checked, len(sides))

    def test_reduced_motion_hidden_tab_and_no_html_injection(self):
        block = _home_block(_script())
        self.assertIn("RM.matches", block)
        self.assertIn("document.hidden", block)
        for bad in (".innerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write"):
            self.assertNotIn(bad, block)

    def test_stage_core_is_a_real_button_with_label(self):
        block = _home_block(_script())
        self.assertIn("class: 'hs-core', 'aria-label': tr('Open Second Brain')", block)
        self.assertNotIn("role: 'listitem'", block)   # balls stay real buttons (do not override the role)
        self.assertIn("el.inert = true", block)       # filtered-out balls are neither readable nor operable
        self.assertIn("'Home', 'End'", block)         # arrow keys instead of 60 tab stops
        self.assertIn("'aria-live': 'polite'", block)  # search hit count

    def test_edit_mode_has_keyboard_size_and_page_controls(self):
        js = _script()
        for needle in ("hs-sizes", "hs-rz", "hs-flowbtns", "hs-dots", "ArrowLeft", "e.key === 'Delete'",
                       "e.key === 'PageUp' || e.key === 'PageDown'", "'aria-label': tr('Size of {widget}'", "'aria-label': tr('Pages')",
                       "'aria-live': 'polite'", "Reset layout"):
            self.assertIn(needle, js)
        # without a pointer a widget is moved and resized with the arrow keys (Shift = size), one cell per press
        self.assertIn("view.nudge(id, d[0], d[1], e.shiftKey)", js)

    def test_seamless_shell_without_sidebar(self):
        html = _html()
        self.assertIn("body.is-home header.top", html)          # corner buttons only, no bar
        self.assertNotIn("border-top: 1px solid var(--line-strong); backdrop-filter: blur(8px)", html)
        self.assertIn("body.is-home { overflow: hidden; height: 100vh; }", html)   # no scrolling on the home page
        # the panes float: tiles on a snap grid with a gap between them, no hairlines and no shared surface any more
        self.assertIn(".hs-tile { position: absolute; left: 0; top: 0;", html)
        self.assertIn("body.is-home .hs-wrap { position: fixed; inset: 0;", html)   # the stage is the whole screen
        self.assertNotIn(".hcol", html)                          # the column layout is gone
        self.assertNotIn(".w-grip", html)
        self.assertNotIn("body.is-home .card { background: transparent; border: 0;", html)
        self.assertIn("document.body.classList.toggle('is-home', id === 'today')", html)
        self.assertIn("main.wrap, .notice.wrap { padding-left: var(--gutter); }", html)   # no sidebar any more

    def test_balls_are_matt_grey_on_a_square_grid_with_a_faint_track(self):
        js = _script()
        stage = js[js.index("function createHomeStage("): js.index("// --- Home page widgets")]
        self.assertRegex(stage, r"BALL_C = \{ html: BALL_GREY, md: BALL_GREY, job: BALL_GREY, skill: BALL_GREY \}")
        self.assertNotIn("bgCanvas", stage)                      # no hexagon grid of its own any more
        self.assertNotIn("Math.PI / 6 + i * TAU / 6", stage)
        self.assertNotIn("rgba(255,255,255,.018)", stage)        # no band along the ring any more
        self.assertIn("dot(sprGrey, st.x, st.y", stage)          # the glow follows every ball
        self.assertNotIn("R + S.D * 0.65", stage)                # no rim lines
        self.assertIn("length: 190", stage)                      # dot field across the full width
        html = _html()
        self.assertRegex(html, r"\.ball \{[^}]*border: 1\.5px solid var\(--ball-edge\)")
        self.assertNotIn(".ball.k-html { --c: #5aa9ff; }", html)  # no colourful ball colours

    def test_styles_for_home(self):
        html = _html()
        self.assertRegex(html, r"\.hs \{[^}]*background: var\(--void\)")
        self.assertIn(".editing .hs-tile > .widget { pointer-events: none; outline: 1.5px dashed", html)
        self.assertIn("@media (min-width: 1180px) and (min-height: 620px) {", html)
        self.assertIn(".hs-head", html)


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class HomePureFunctionTests(unittest.TestCase):
    def _run(self, body: str):
        js = _script()
        widgets = js[js.index("const WIDGETS = ["): js.index("const TodayView = {")]
        stubs = "".join(f"const {n} = () => null;\n" for n in sorted(set(re.findall(r"build: (\w+)", widgets))))
        prelude = f"""
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const STORE = {{}};
const store = {{ get(k) {{ return Object.prototype.hasOwnProperty.call(STORE, k) ? STORE[k] : null; }}, set(k, v) {{ STORE[k] = v; }} }};
{stubs}
"""
        geometry = js[js.index("const GALAXY_PALETTE"): js.index("function glowSprite(")]
        iso = js[js.index("function isoWeek(d)"): js.index("function analogClock(")]
        folder = js[js.index("const OS_FOLDER_PAL"): js.index("// Model: nodes + edges")]
        src = JS_I18N + prelude + "const HOME_PALETTE = ['#1','#2','#3','#4','#5','#6'];\n" + geometry + iso + folder + widgets + "\n" + body
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_iso_week(self):
        out = self._run("""
const wk = (y, m, d) => isoWeek(new Date(y, m - 1, d));
console.log(JSON.stringify({ a: wk(2026, 10, 10), b: wk(2021, 1, 3), c: wk(2024, 12, 30), d: wk(2026, 1, 1) }));
""")
        self.assertEqual(out, {"a": 41, "b": 53, "c": 1, "d": 1})

    def test_stage_has_no_cage_around_the_cloud(self):
        js = _script()
        self.assertNotIn("buildPolyhedron", js)
        self.assertNotIn("poly.edges", js)

    def test_galaxy_is_deterministic_and_inside_the_unit_ball(self):
        out = self._run("""
const a = buildCloud(400), b = buildCloud(400), f = buildCloud(GALAXY_N), g = buildCloud(GALAXY_N);
console.log(JSON.stringify({ n: a.length, same: JSON.stringify(a) === JSON.stringify(b),
  inside: a.every(p => Math.hypot(p.x, p.y, p.z) <= 1.0001), ci: a.every(p => p.ci >= 0 && p.ci < GALAXY_PALETTE.length),
  colors: new Set(a.map(p => p.ci)).size, pal: GALAXY_PALETTE.length, sz: a.every(p => p.sz > 0.5 && p.sz < 3), br: a.every(p => p.br > 0 && p.br <= 1),
  fullSame: JSON.stringify(f) === JSON.stringify(g), fullLen: f.length,
  fullInside: f.every(p => Math.hypot(p.x, p.y, p.z) <= 1.0001 && p.r <= 0.99 + 1e-9), fullCi: f.every(p => p.ci >= 0 && p.ci < GALAXY_PALETTE.length),
  fullSz: f.every(p => p.sz > 0.4 && p.sz <= 3.01), fullBr: f.every(p => p.br > 0 && p.br <= 1),
  // the stars are the same whatever the total (the mist has its own generators)
  prefix: JSON.stringify(f.slice(0, 400)) === JSON.stringify(a) }));
""")
        self.assertEqual(out["n"], 400)
        self.assertTrue(out["same"])
        self.assertTrue(out["inside"])
        self.assertTrue(out["ci"])
        self.assertTrue(out["sz"])
        self.assertTrue(out["br"])
        self.assertEqual(out["colors"], out["pal"])
        self.assertTrue(out["fullSame"])                  # the whole cloud, stars and diffuse particles, is deterministic ...
        self.assertTrue(out["prefix"])                    # ... and a smaller cloud is a prefix of a bigger one
        self.assertGreater(out["fullLen"], 9000)
        self.assertTrue(out["fullInside"])
        self.assertTrue(out["fullCi"])
        self.assertTrue(out["fullSz"])
        self.assertTrue(out["fullBr"])

    def test_galaxy_has_bulge_thin_disc_and_spiral_arms(self):
        out = self._run("""
const a = buildCloud(GALAXY_STARS), disc = a.filter(p => p.arm >= 0), n = a.length;   // the stars: the diffuse particles are tested in test_galaxy_transitions
const wrap = d => { d = ((d % TAU) + TAU) % TAU; return d > Math.PI ? d - TAU : d; };
const armErr = disc.map(p => Math.abs(wrap(Math.atan2(p.z, p.x) - galaxyArmAngle(p.arm, Math.hypot(p.x, p.z)))));
const bins = new Array(24).fill(0);   // angular density of the outer disc, in the frame of the spiral: N peaks per turn
disc.filter(p => p.r > 0.5).forEach(p => { bins[Math.floor(((Math.atan2(p.z, p.x) - GALAXY_WIND * Math.log(Math.hypot(p.x, p.z) / GALAXY_R0)) % TAU + TAU) % TAU / TAU * 24)]++; });
let re = 0, im = 0; bins.forEach((v, b) => { re += v * Math.cos(TAU * GALAXY_ARMS * (b + 0.5) / 24); im += v * Math.sin(TAU * GALAXY_ARMS * (b + 0.5) / 24); });
console.log(JSON.stringify({
  arms: new Set(disc.map(p => p.arm)).size, bulge: a.filter(p => p.r < ATLAS_CORE_R_T && p.arm < 0).length / n,
  onArm: armErr.filter(e => e < 1).length / armErr.length,
  flat: disc.every(p => Math.abs(p.y) <= 0.1) && disc.reduce((s, p) => s + Math.abs(p.y), 0) / disc.length < 0.04,
  warmCore: a.filter(p => p.r < 0.15 && [0, 1, 7].includes(p.ci)).length / a.filter(p => p.r < 0.15).length,
  modulation: Math.hypot(re, im) / bins.reduce((x, y) => x + y, 0),
  inner: a.filter(p => p.r < 0.2).reduce((s, p) => s + p.sp, 0) / a.filter(p => p.r < 0.2).length, outer: a.filter(p => p.r > 0.8).reduce((s, p) => s + p.sp, 0) / a.filter(p => p.r > 0.8).length,
  bar: a.filter(p => p.ci !== 6 && Math.abs(Math.cos(GALAXY_BAR) * p.z - Math.sin(GALAXY_BAR) * p.x) < 0.06 && Math.hypot(p.x, p.z) < 0.2 && p.arm < 0).length,
  barAcross: a.filter(p => p.ci !== 6 && Math.abs(Math.sin(GALAXY_BAR) * p.z + Math.cos(GALAXY_BAR) * p.x) < 0.06 && Math.hypot(p.x, p.z) < 0.2 && p.arm < 0).length,
  major: a.filter(p => p.arm === 0 || p.arm === 2).length, minor: a.filter(p => p.arm === 1 || p.arm === 3).length,
  dim: a.filter(p => p.r > 0.25 && p.sz < 1.1 && p.arm < 0).length / n,
  bright: a.filter((p, i) => i % 24 === 7).every(p => p.arm >= 0 && p.r >= 0.39),
  hii: a.some(p => p.ci === 6),
}));
""".replace("ATLAS_CORE_R_T", "0.32"))
        self.assertEqual(out["arms"], 4)                  # two major and two minor arms
        self.assertGreater(out["bulge"], 0.15)            # bright bulge (bulge, bar and the dense inner disc)
        self.assertGreater(out["onArm"], 0.8)             # arm stars follow the logarithmic spiral
        self.assertTrue(out["flat"])                      # thin disc
        self.assertGreater(out["warmCore"], 0.95)        # warm white, yellow and amber core
        self.assertGreater(out["modulation"], 0.3)        # angular density modulation with N arms
        self.assertGreater(out["inner"], out["outer"])    # differential rotation: inner faster than outer (on average)
        self.assertGreater(out["bar"], 1.08 * out["barAcross"])   # the bar is elongated along GALAXY_BAR (on top of the round bulge)
        self.assertGreater(out["major"], 1.4 * out["minor"])     # two dominant arms, two weaker ones
        self.assertGreater(out["dim"], 0.12)              # many faint disc stars: the milky band
        self.assertTrue(out["bright"])                    # cluster stars sit in the arms, never in the bulge
        self.assertTrue(out["hii"])

    def test_palette_is_derived_from_the_galaxy_and_text_is_readable(self):
        html = _html()
        css = html[: html.index("</style>")]
        self.assertNotIn("#ff6a1a", css)                  # the old orange accent is gone
        def tok(block_start, name):
            blk = css[css.index(block_start):]
            return re.search(r"--" + name + r": (#[0-9a-fA-F]{6})", blk).group(1)
        def lum(h):
            c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            c = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
            return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        def ratio(a, b):
            la, lb = sorted([lum(a), lum(b)], reverse=True)
            return (la + 0.05) / (lb + 0.05)
        for block in (':root[data-theme="dark"] {', ":root {" + chr(10) + "  --bg: #f5f2fb"):
            bg = tok(block, "bg")
            for name, need in (("ink", 7), ("ink-2", 7), ("muted", 4.5), ("accent", 4.5)):
                self.assertGreaterEqual(ratio(tok(block, name), bg), need, (block, name))
        self.assertIn("--void: #060712", css)             # deep space with a blue-violet tint
        self.assertIn('<meta name="color-scheme" content="light dark">', html)

    def test_agents_slots_lie_on_the_arms_in_angle_order(self):
        out = self._run("""
const wrap = d => { d = ((d % TAU) + TAU) % TAU; return d > Math.PI ? d - TAU : d; };
const rs = [], errs = [];
for (let k = 0; k < 42; k++) {
  const az = TAU * (k + 0.5) / 42, r = galaxyArmRadius(az, 0.62);
  rs.push(r); errs.push(Math.abs(wrap(az - galaxyArmAngle(Math.round((az - GALAXY_WIND * Math.log(r / GALAXY_R0)) / (TAU / GALAXY_ARMS)) % GALAXY_ARMS, r))));
}
console.log(JSON.stringify({ min: Math.min(...rs), max: Math.max(...rs), err: Math.max(...errs) }));
""")
        self.assertGreater(out["min"], 0.38)
        self.assertLess(out["max"], 1.0)
        self.assertLess(out["err"], 1e-6)

    def test_folder_color_and_name(self):
        out = self._run("""
console.log(JSON.stringify({ a: osFolderOf('Projects/Garden/Beds/Note.md'), b: osFolderOf('CLAUDE.md'), c: osFolderOf('Areas/Plan.md'),
  stable: osFolderColor('Projects/Garden') === osFolderColor('Projects/Garden'), inPal: OS_FOLDER_PAL.includes(osFolderColor('x/y')) }));
""")
        self.assertEqual(out["a"], "Projects/Garden")
        self.assertEqual(out["b"], "(root)")
        self.assertEqual(out["c"], "Areas")
        self.assertTrue(out["stable"])
        self.assertTrue(out["inPal"])

    def test_layout_load_validates_and_migrates(self):
        out = self._run("""
const res = {};
const d = defaultLayout();
res.def = { v: d.v, hidden: d.hidden, tiles: d.tiles, legacy: d.legacy, flow: d.flow };
// v4 and older: a list per column. Kept as `legacy` (arranged once), your hiding stays, what is off by default is added
STORE.widgets = JSON.stringify({ order: ['costs', 'needs', 'does-not-exist'], size: { costs: 'l', x: 'm' }, hidden: ['needs', 'nope'], col: { apps: 'r', skills: 'zz' } });
let l = loadLayout();
res.old = { v: l.v, hidden: l.hidden.slice().sort(), tiles: l.tiles, legacy: l.legacy, flow: l.flow };
// an old layout nobody changed has nothing to carry over
STORE.widgets = JSON.stringify({ v: 4, order: [], col: {}, size: {}, hidden: ['health'] });
l = loadLayout();
res.plain = { legacy: l.legacy, hidden: l.hidden.slice().sort() };
// v5: tiles are validated one by one, the flow order loses unknown and repeated ids
STORE.widgets = JSON.stringify({ v: LAYOUT_V, hidden: ['costs', 'zz'], flow: ['goals', 'zz', 'hero', 'goals'], tiles: {
  hero: { p: 1.4, a: 'r', x: 2, y: 3, w: 6, h: 4 }, calendar: { p: -1, a: 'l', x: 0, y: 0, w: 6, h: 6 },
  skills: { p: 0, a: 'q', x: 1, y: 1, w: 0, h: 2.6 }, nope: { p: 0, a: 'l', x: 0, y: 0, w: 1, h: 1 }, goals: 'x', apps: { p: 0, a: 'l', x: 0, y: 0, w: 6 } } });
l = loadLayout();
res.v5 = { hidden: l.hidden, tiles: l.tiles, flow: l.flow };
STORE.widgets = JSON.stringify({ v: LAYOUT_V, tiles: { hero: { p: 0, a: 'l', x: 0, y: 0, w: 6, h: 4 } } });
res.noFlow = loadLayout().flow;
STORE.widgets = '{broken';
res.broken = JSON.stringify(loadLayout()) === JSON.stringify(defaultLayout());
STORE.widgets = 'null';
res.nul = JSON.stringify(loadLayout()) === JSON.stringify(defaultLayout());
res.version = LAYOUT_V;
console.log(JSON.stringify(res));
""")
        self.assertEqual(out["version"], 5)
        self.assertEqual(out["def"], {"v": 5, "hidden": ["costs", "clocks"], "tiles": None, "legacy": None, "flow": None})
        old = out["old"]
        self.assertEqual((old["v"], old["tiles"], old["flow"]), (5, None, None))
        self.assertEqual(old["hidden"], ["clocks", "costs", "needs"])   # your own hiding stays, the new default-off is added
        self.assertEqual(old["legacy"], {"order": ["costs", "needs"], "col": {"apps": "r"}, "size": {"costs": "l"}})
        self.assertEqual(out["plain"], {"legacy": None, "hidden": ["clocks", "costs", "health"]})
        v5 = out["v5"]
        self.assertEqual(v5["hidden"], ["costs"])
        self.assertEqual(v5["tiles"], {
            "hero": {"p": 1, "a": "r", "x": 2, "y": 3, "w": 6, "h": 4},
            "skills": {"p": 0, "a": "l", "x": 1, "y": 1, "w": 1, "h": 3},   # a width of 0 becomes 1, the anchor falls back to the left
        })   # negative page, unknown id, not an object and a missing height are dropped
        self.assertEqual(v5["flow"], ["goals", "hero"])
        self.assertIsNone(out["noFlow"])
        self.assertTrue(out["broken"])
        self.assertTrue(out["nul"])


if __name__ == "__main__":
    unittest.main()
