"""Second-brain (OS) view: wiring (static) and pure functions (with Node, if installed)."""

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


def _script() -> str:
    return re.search(r"<script>\n(.*?)</script>", TEMPLATE.read_text(encoding="utf-8"), re.S).group(1)


def _os_block(js: str) -> str:
    return js[js.index("const OS_C = {"): js.index("const OsView = {")]


class OsViewStaticTests(unittest.TestCase):
    def test_view_is_registered_everywhere(self):
        js = _script()
        self.assertIn("{ id: 'os', label: tr('Second brain') }", js)
        self.assertRegex(re.search(r"const VIEW_MODS = \{(.*?)\};", js, re.S).group(1), r"\bos: OsView\b")
        self.assertRegex(re.search(r"const TAB_ICONS = \{(.*?)\n\};", js, re.S).group(1), r"\bos:")

    def test_all_four_layouts_and_controls_exist(self):
        js = _script()
        for name in ("rings", "force", "circle", "hex"):
            self.assertIn(f"['{name}',", js)
        for needle in ("Ring rotation", "Link springs", "Node size", "Collapse", "Expand", "Search"):
            self.assertIn(needle, js)

    def test_respects_reduced_motion_and_hidden_tab(self):
        js = _script()
        os_src = js[js.index("const OsView = {"):]
        self.assertIn("RM.matches", os_src)
        self.assertIn("document.hidden", os_src)

    def test_no_html_injection_in_os_view(self):
        js = _script()
        os_src = js[js.index("const OS_C = {"): js.index("const VIEW_MODS")]
        for bad in (".innerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write"):
            self.assertNotIn(bad, os_src)

    def test_stage_is_dark_independent_of_theme_and_has_mobile_rule(self):
        tpl = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(tpl, r"\.os-stage \{[^}]*background: var\(--void\)")
        self.assertIn("@media (max-width: 720px) {\n  .os-stage", tpl)

    def test_second_brain_has_no_home_scene_left(self):
        # The home page lives in the "OS" view (HomeStage); the network view starts straight as a network.
        js = _script()
        os_src = js[js.index("const OsView = {"): js.index("const MODEL_COLOR")]
        for gone in ("drawHome", "homeItems", "homeHit", "setScene", "OS_FLASH_S", "makeSphere"):
            self.assertNotIn(gone, os_src)
        for needed in ("buildBar()", "buildLegend()", "Back to OS", "setGroup(", "Areas", "Folders"):
            self.assertIn(needed, js)

    def test_second_brain_is_fullscreen_without_page_chrome(self):
        tpl = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("document.body.classList.toggle('is-brain', id === 'os')", tpl)
        self.assertIn("body.is-brain header.top, body.is-brain .tabs-wrap", tpl)
        self.assertIn("body.is-brain .os-stage { height: 100vh;", tpl)

    def test_second_brain_has_no_window_boxes_or_own_background(self):
        tpl = TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(tpl, r"body\.is-brain \.os-stage \{ background: radial-gradient\(")   # haze via CSS, no base color
        # menu, legend, preview and hover card are floating glass panes now (see "Liquid glass"), not boxes of the old chrome
        self.assertRegex(tpl, r"html:root body\.is-brain \.os-controls \{[^}]*right: var\(--lg-gap\)")
        self.assertRegex(tpl, r"html:root body :is\(\.detail, \.results, \.w-pop, \.hs-card, \.os-card, \.os-preview, \.os-controls, \.os-legendbox[^)]*\) \{[^}]*border-radius: var\(--lg-r-m\)")
        self.assertIn("html:root body.is-brain .os-legendbox {", tpl)
        js = _script()
        self.assertNotIn("background(ctx, w, hh)", js)       # no fullscreen blit per frame
        self.assertNotIn("v.bg", js)

    def test_per_frame_costs_are_bounded(self):
        js = _script()
        self.assertEqual(js.count("getComputedStyle(document.body).fontFamily"), 2)   # fontFam() and once on mount
        self.assertIn("Math.ceil(LK.length / (v.layout === 'force' ? 900 : 500))", js)            # links are thinned out
        self.assertIn("if (now - S.last < 12.5) return;", js)       # home page: at most every second frame of a 144 Hz screen, never more than ~80 fps
        self.assertIn("v.layout !== 'force' && v.drag == null && !v.camTo ? 31 : 15", js)   # second brain: 60, rotating 30
        self.assertIn("if (st.tf !== tf)", js)                     # balls: only write changed styles

    def test_wheel_zooms_and_hub_is_the_claude_code_squid(self):
        js = _script()
        self.assertIn("hd.wheelZoom", js)                          # the wheel alone zooms (fullscreen, no page scroll)
        self.assertIn("wheelZoom: true,", js)
        self.assertIn("const OS_SQUID = [", js)
        self.assertIn("n.k === 'hub') {   // CLAUDE.md: the Claude Code mascot", js)

    def test_keyboard_alternative_for_every_application(self):
        # The stage is a canvas: every application also has a real button (os-navbtn).
        js = _script()
        self.assertIn("os-navbtn", js)
        self.assertIn("showView(x.id, { focus: true })", js)


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class OsViewPureFunctionTests(unittest.TestCase):
    def _run(self, body: str):
        prelude = """
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const store = { get() { return null; }, set() {} };
const VIEWS = [{ id: 'today', label: 'Today' }, { id: 'os', label: 'Second brain' }, { id: 'rings', label: 'Rings' }];
const AREAS_SEEN = {};
const area = k => (AREAS_SEEN[k] = AREAS_SEEN[k] || { key: k, label: k });
"""
        src = JS_I18N + prelude + _os_block(_script()) + "\n" + body
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_build_and_targets(self):
        out = self._run("""
const nodes = [];
for (let i = 0; i < 300; i++) nodes.push({ id: 'n' + i + '.md', label: 'n' + i, areaDef: area(['Areas', 'Projects', 'AI'][i % 3]), deg: i % 7 });
nodes.push({ id: 'CLAUDE.md', label: 'CLAUDE.md', areaDef: area('(root)'), deg: 9 });
const g = { nodes, byDeg: nodes.map((_, i) => i).sort((a, b) => nodes[b].deg - nodes[a].deg),
  es: Int32Array.from([0, 1, 2]), et: Int32Array.from([3, 4, 5]),
  skills: [{ id: 'study-plan', name: 'Study plan' }], routines: [{ id: 'study-plan-weekly', description: '' }, { id: 'git-pull' }] };
const m = osBuild(g);
const res = { notes: m.notes.length, apps: m.apps.length, skills: m.skills.length, routines: m.routines.length, areas: m.areas.length,
  hubIsClaude: m.hub.label === 'CLAUDE.md', noOsApp: m.apps.every(a => a.view !== 'os'),
  skillLinked: m.links.some(l => m.nodes[l.a].k === 'skill' && m.nodes[l.b].k === 'routine'),
  sym: m.nodes.every(n => n.nb.every(j => m.nodes[j].nb.includes(n.i))) };
const R = 300, fin = {};
for (const name of ['rings', 'circle', 'hex']) {
  osTargets(m, name, R, true);
  fin[name] = m.nodes.every(n => Number.isFinite(n.bx) && Number.isFinite(n.by) && Math.hypot(n.bx, n.by) <= R * 1.001);
}
osTargets(m, 'hex', R, true);
const keys = new Set(m.nodes.map(n => Math.round(n.bx) + ':' + Math.round(n.by)));
res.hexDistinct = keys.size === m.nodes.length;
res.fin = fin;
res.hexSpiral = osHexSpiral(37).length === 37 && new Set(osHexSpiral(37).map(c => c.join(','))).size === 37;
console.log(JSON.stringify(res));
""")
        self.assertEqual(out["notes"], 300)  # below OS_MAX_NOTES (600): every note except CLAUDE.md
        self.assertEqual((out["apps"], out["skills"], out["routines"], out["areas"]), (2, 1, 2, 3))
        self.assertTrue(out["hubIsClaude"])
        self.assertTrue(out["noOsApp"])
        self.assertTrue(out["skillLinked"])
        self.assertTrue(out["sym"])
        self.assertTrue(out["hexSpiral"])
        self.assertTrue(out["hexDistinct"])
        self.assertEqual(out["fin"], {"rings": True, "circle": True, "hex": True})

    def test_big_vault_keeps_best_connected_notes(self):
        out = self._run("""
const nodes = [];
for (let i = 0; i < 900; i++) nodes.push({ id: 'n' + i + '.md', label: 'n' + i, areaDef: area('AI'), deg: i % 50 });
const g = { nodes, byDeg: nodes.map((_, i) => i).sort((a, b) => nodes[b].deg - nodes[a].deg),
  es: new Int32Array(0), et: new Int32Array(0), skills: [], routines: [] };
const m = osBuild(g);
console.log(JSON.stringify({ n: m.notes.length, minDeg: Math.min(...m.notes.map(n => n.deg)) }));
""")
        self.assertEqual(out["n"], 600)
        self.assertGreaterEqual(out["minDeg"], 16)   # the 300 weakest (degree 0-15 ...) are dropped

    def test_force_clusters_are_separated_blobs(self):
        out = self._run("""
const nodes = [];
for (let i = 0; i < 260; i++) nodes.push({ id: 'n' + i + '.md', label: 'n' + i, areaDef: area(['AI', 'AI', 'Projects', 'Journal'][i % 4]), deg: i % 9 });
const g = { nodes, byDeg: nodes.map((_, i) => i), es: new Int32Array(0), et: new Int32Array(0),
  skills: [{ id: 's1', name: 'S1' }, { id: 's2', name: 'S2' }], routines: [{ id: 'r1' }, { id: 'r2' }, { id: 'r3' }] };
const m = osBuild(g);
osTargets(m, 'force', 300, true);
const cs = m.clusters;
let overlap = false;
for (let i = 0; i < cs.length; i++) for (let j = i + 1; j < cs.length; j++)
  if (Math.hypot(cs[i].x - cs[j].x, cs[i].y - cs[j].y) < cs[i].r + cs[j].r - 1) overlap = true;
const inside = m.nodes.every(n => n.k === 'hub' || Math.hypot(n.bx - cs[n.cl].x, n.by - cs[n.cl].y) <= cs[n.cl].r + 0.01);
const kinds = cs.map(c => c.kind).sort().join(',');
const fit = osFit(m, 1200, 700);
console.log(JSON.stringify({ overlap, inside, kinds, clOk: m.nodes.every(n => n.k === 'hub' ? n.cl === -1 : cs[n.cl].nodes.includes(n)),
  fin: m.nodes.every(n => Number.isFinite(n.bx) && Number.isFinite(n.by)), hub: [m.hub.bx, m.hub.by],
  fitOk: fit.k >= 0.5 && fit.k <= 2.4 && Number.isFinite(fit.x) && Number.isFinite(fit.y),
  ease: [osArriveEase(0, 1), osArriveEase(0.5, 1) > 0.5, osArriveEase(5, 1)] }));
""")
        self.assertFalse(out["overlap"])
        self.assertTrue(out["inside"])
        self.assertTrue(out["clOk"])
        self.assertTrue(out["fin"])
        self.assertEqual(out["hub"], [0, 0])
        self.assertEqual(out["kinds"], "app,area,area,area,routine,skill")
        self.assertTrue(out["fitOk"])
        self.assertEqual(out["ease"], [0, True, 1])

    def test_empty_vault_does_not_crash(self):
        out = self._run("""
const g = { nodes: [], byDeg: [], es: new Int32Array(0), et: new Int32Array(0), skills: [], routines: [] };
const m = osBuild(g);
for (const name of ['rings', 'circle', 'hex', 'force']) osTargets(m, name, 200, true);
const fit = osFit(m, 800, 500);
console.log(JSON.stringify({ n: m.nodes.length, ok: Number.isFinite(m.hub.bx) && m.nodes.every(n => Number.isFinite(n.bx)) && Number.isFinite(fit.k) }));
""")
        self.assertEqual(out["n"], 3)  # hub + 2 applications (os does not count)
        self.assertTrue(out["ok"])


if __name__ == "__main__":
    unittest.main()
