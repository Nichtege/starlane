"""Atlas view: wiring (static) and pure functions (with Node, if installed)."""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
JS = re.search(r"<script>\n(.*?)</script>", HTML, re.S).group(1)


def _view() -> str:
    return JS[JS.index("const AGENT_GROUPS = ["): JS.index("   12d. View: Skills")]


class AtlasStaticTests(unittest.TestCase):
    def test_fullscreen_like_the_second_brain_and_reachable_from_the_stage(self):
        self.assertIn("document.body.classList.toggle('is-atlas', id === 'agents')", JS)
        self.assertIn("body.is-atlas header.top", HTML)
        self.assertIn("class: 'hs-atlas'", JS)                                   # button on the home page
        self.assertIn("atlasBtn.addEventListener('click', takeoff('atlas'))", JS)
        self.assertIn("document.querySelector('.hs-atlas')", JS)            # key A triggers the same zoom

    def test_atlas_click_flies_into_the_cloud_fullscreen_and_holds_the_deepest_zoom(self):
        stage = JS[JS.index("function createHomeStage("): JS.index("// --- Home page widgets")]
        self.assertIn("function flyTo(kind)", stage)
        self.assertIn(".hs-fly { position: fixed; inset: 0", HTML)           # fullscreen: no stage edge in view
        self.assertIn("entryFrame(rig, u, cam);", stage)                     # one ease-in-out dive to the framing Atlas keeps
        self.assertNotIn("CRz", stage)
        for gone in ("fitCR", "ZOOM_K", "c.CR += (fit - c.CR)"):             # no pull-back once Atlas appears
            self.assertNotIn(gone, JS)
        self.assertIn("atlasEmerge = 'hold'; showView('agents'", stage)      # Atlas builds up under the black
        self.assertIn("AgentsView.takeover(fs, t, CR, sz, amul,", stage)  # at the end of the dive the view takes over the cloud
        self.assertIn("drawCloudScene(ctx, fo,", stage)                      # the same painter as the stage
        self.assertIn("drawCloudScene(ctx, oc,", _view())                    # and in the Atlas view
        self.assertIn(".hs.hs-zoom .ball", HTML)                             # ring and widgets fade out
        self.assertIn("body.is-zooming :is(.hs-grid, .hs-dots, .hs-glass)", HTML)                  # the tiles fade out with the flight

    def test_cloud_click_turns_the_orbs_into_the_knots_of_the_brain(self):
        stage = JS[JS.index("function createHomeStage("): JS.index("// --- Home page widgets")]
        self.assertIn("core.addEventListener('click', () => takeoff('os')())", stage)
        self.assertIn("showView('os', { focus: true });   // builds up under the black", stage)
        self.assertIn("OsView.scr(nodes[j])", stage)                         # the particles follow the real node positions
        self.assertIn("osColor(all[j])", stage)                              # and take on the color of their node
        self.assertIn("stepOrbSim(fs, m, dt, K, orbDamp(K), target, null)", stage)

    def test_atlas_bright_middle_is_atlas_and_some_orbs_are_the_agents(self):
        view = _view()
        self.assertIn("makeOrbCloud()", view)                                # the same stars as the home page (one shared galaxy)
        self.assertIn("pickAgents(", view)                                   # some stars outside the center become agents
        self.assertIn("p.r < ATLAS_CORE_R", JS)                              # the bright center is Atlas, never an agent
        self.assertIn("galaxyTarget(oc.cloud, hp, A)", view)                 # promoted stars glide to their slot, all others keep floating
        self.assertIn("HOME_PALETTE[p.ci]", view)                            # agents carry the colors of the orbs
        self.assertIn("ctx.moveTo(c.cx, c.cy); ctx.lineTo(p.x, p.y)", view)  # connected to the center
        for gone in ("assignAgents", "ATLAS_REL", "ZOOM_REVEAL"):
            self.assertNotIn(gone, JS)

    def test_atlas_core_has_no_ring(self):
        paint = _view()
        paint = paint[paint.index("// the cloud itself (additive)"): paint.index("// Depth: smaller and darker at the back")]
        self.assertNotIn("ctx.stroke()", paint)
        self.assertNotIn("ctx.arc(", paint)
        self.assertNotIn("createRadialGradient", paint)                      # the glow of the center is bulge particles, not a gradient behind the cloud

    def test_agents_are_3d_and_active_ones_fire_like_neurons(self):
        view = _view()
        self.assertIn("function galaxyTarget(cloud, P, A)", JS)              # slots on the arms of the rotated galaxy disc
        self.assertIn("1 / (1 - q[2] * 0.1)", JS)                            # perspective
        self.assertIn("a.dep - b.dep", view)                                 # drawn back to front
        self.assertIn("links(pts) {", view)                                  # request, source, handoff only for running jobs
        self.assertIn("add(c.hubPt, A, 'req', A, seed)", view)
        self.assertIn("c.src[A.a.web ? 'web' : 'vault']", view)
        self.assertIn("add(by.get(String(prev.agent)), A, 'hand', A, seed + 0.25)", view)
        self.assertIn("if (s0 < 0.32) {", view)                              # arrival: receiver flashes, neighbours spark
        self.assertIn("ctx.globalCompositeOperation = 'lighter';", view)

    def test_atlas_page_has_recent_conversations_and_model_and_effort(self):
        view = _view()
        self.assertIn("recentMenu() {", view)                                # recent conversations as a menu in the header
        self.assertIn("atlasThreads(v.list()).slice(0, 8)", view)
        self.assertIn("modelEffortPicker({ models, efforts: ch.efforts", view)   # the same picker as for skills
        self.assertIn("autoModel: true", view)                               # "Default" = the agent's model
        self.assertIn("if (v.pickM && ch.models.includes(v.pickM)) body.model = v.pickM;", view)
        self.assertIn("if (v.pickE && ch.efforts.includes(v.pickE)) body.effort = v.pickE;", view)
        # both popups open inside the chat pane (overflow: hidden): they are fitted into it, not cut off
        self.assertIn("pop.hidden = false; btn.setAttribute('aria-expanded', 'true'); fitPop(pop);", view)
        self.assertIn("trigger.setAttribute('aria-expanded', String(on)); if (on) fitPop(pop);", JS)
        self.assertNotIn("max-height: 60vh", HTML[HTML.index(".atl-recent-pop {"):][:300])

    def test_going_home_flies_back_and_the_ring_emerges_from_the_middle(self):
        self.assertIn("function returnHome(kind, focus)", JS)
        self.assertIn("returnHome(current, !!(opts && opts.focus));", JS)    # showView reroutes a return to the home page
        self.assertIn("stage.adopt(fs, t); stage.release();", JS)         # the stage takes over the particles
        self.assertIn("c.leave = performance.now();", JS)                    # Atlas fades out its agents, the flight takes over
        stage = JS[JS.index("function createHomeStage("): JS.index("/* Return flight:")]
        self.assertIn("st.t0 = Math.max(now, S.emergeAt) + i * gap;", stage)   # one after another
        self.assertIn("const r = R * (0.1 + 0.9 * eo)", stage)               # from the center outwards

    def test_sidebars_glide_in_after_the_return_flight_and_a_missing_model_is_explained(self):
        self.assertIn("body.is-arriving .hs-tile.a-l { animation: side-in-l", HTML)
        self.assertIn("body.is-arriving .hs-tile.a-r { animation: side-in-r", HTML)
        self.assertIn("document.body.classList.add('is-arriving')", JS)
        self.assertIn("/usage credits|requires usage/i.test(String(j.note || ''))", JS)   # e.g. a model without usage credits

    def test_landing_cloud_is_a_physics_simulation(self):
        stage = JS[JS.index("function createHomeStage("): JS.index("// --- Home page widgets")]
        self.assertIn("stepOrbSim(sim, cloud.length, dt, ORB_K", stage)
        self.assertIn("{ x: S.ptr.x, y: S.ptr.y,", stage)                    # the pointer pushes particles away

    def test_chat_replaces_normal_chat(self):
        src = _view()
        self.assertIn("body.thread = v.thread", src)               # follow-up questions carry the thread id
        self.assertIn("e.key === 'Enter' && !e.shiftKey", src)     # Enter sends, as in a chat
        self.assertIn("role: 'log', 'aria-live': 'polite'", src)
        self.assertIn("searching the web", src)                    # hint that a web search is running
        for bad in (".innerHTML", "insertAdjacentHTML", "eval("):
            self.assertNotIn(bad, src)

    def test_web_sources_are_safe_links(self):
        body = JS[JS.index("function extLink("): JS.index("const MD_LIST")]
        self.assertIn("rel: 'noopener noreferrer'", body)
        self.assertIn("target: '_blank'", body)
        self.assertIn(r"/^https?:\/\//i.test(m[10])", JS)          # javascript: and data: never become links

    def test_back_glow_follows_each_ball(self):
        stage = JS[JS.index("function createHomeStage("): JS.index("// --- Home page widgets")]
        self.assertNotIn("ctx.arc(cx, cy, R, 0, TAU); ctx.stroke()", stage)   # no band along the ring
        self.assertIn("dot(sprGrey, st.x, st.y", stage)


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class PopupFitTests(unittest.TestCase):
    """fitPop on a fake DOM: the Atlas chat pane is [778, 16, 1086, 636] in a 1102 x 652 window (the size where the
    history menu used to be cut off on the left and the model picker at the top and on the right)."""

    def fit(self, case: dict) -> dict:
        fn = JS[JS.index("function fitPop(pop) {"): JS.index("\naddEventListener('resize'")]
        body = """
const BODY = { cs: {} };
const document = { body: BODY };
const innerWidth = 1102, innerHeight = 652;
const getComputedStyle = el => ({ overflowX: 'visible', overflowY: 'visible', ...el.cs });
const o = CASE;
const pane = { cs: { overflowX: 'hidden', overflowY: 'hidden' }, parentElement: BODY, getBoundingClientRect: () => o.pane };
const anchor = { cs: {}, parentElement: pane, getBoundingClientRect: () => o.anchor };
const style = {};
const num = v => parseFloat(v) || 0;
const pop = { style, parentElement: anchor, getBoundingClientRect() {
  const w = Math.min(o.width, num(style.maxWidth) || Infinity), h = Math.min(o.content, num(style.maxHeight) || Infinity);
  const x = (o.right ? o.anchor.right - w : o.anchor.left) + num(style.translate);
  const y = o.up ? o.anchor.top - 8 - h : o.anchor.bottom + 6;
  return { left: x, right: x + w, top: y, bottom: y + h, width: w, height: h };
} };
fitPop(pop);
console.log(JSON.stringify({ rect: pop.getBoundingClientRect(), style }));
""".replace("CASE", json.dumps(case))
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(fn + "\n" + body, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    PANE = {"left": 778, "top": 16, "right": 1086, "bottom": 636}

    def test_history_menu_moves_back_into_the_pane_and_shows_every_row(self):
        got = self.fit({"pane": self.PANE, "anchor": {"left": 990, "top": 30, "right": 1070, "bottom": 60},
                        "right": True, "width": 340, "content": 532})
        r = got["rect"]
        self.assertGreaterEqual(r["left"], 786)
        self.assertLessEqual(r["right"], 1078)
        self.assertEqual(r["height"], 532)             # everything visible, no inner scrolling
        self.assertEqual(got["style"]["maxHeight"], "")

    def test_a_menu_taller_than_the_pane_scrolls_inside_it(self):
        got = self.fit({"pane": self.PANE, "anchor": {"left": 990, "top": 30, "right": 1070, "bottom": 60},
                        "right": True, "width": 340, "content": 900})
        self.assertLessEqual(got["rect"]["bottom"], 628)
        self.assertEqual(got["style"]["overflowY"], "auto")

    def test_model_picker_opening_upwards_stays_inside_at_the_top_and_right(self):
        got = self.fit({"pane": self.PANE, "anchor": {"left": 798, "top": 590, "right": 960, "bottom": 632},
                        "up": True, "width": 330, "content": 600})
        r = got["rect"]
        self.assertGreaterEqual(r["top"], 24)
        self.assertLessEqual(r["right"], 1078)
        self.assertGreaterEqual(r["left"], 786)

    def test_a_popup_with_room_is_left_as_it_is(self):
        got = self.fit({"pane": {"left": 0, "top": 0, "right": 1102, "bottom": 652},
                        "anchor": {"left": 500, "top": 30, "right": 900, "bottom": 60}, "right": True, "width": 340, "content": 300})
        self.assertEqual((got["style"]["translate"], got["style"]["maxHeight"]), ("", ""))


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class AtlasPureFunctionTests(unittest.TestCase):
    def _run(self, body: str):
        v = _view()
        head = v[v.index("const AGENT_GROUPS"): v.index("const AGENT_EXAMPLES")]
        funcs = v[v.index("// Fields: filtered"): v.index("// Soft glow")]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(head + funcs + "\n" + body, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def _sim(self, body: str):
        a = JS.index("const GALAXY_PALETTE")
        b = JS.index("// ---- end of the galaxy model")
        pre = "const TAU = Math.PI * 2;\nconst clamp = (v, a, b) => Math.max(a, Math.min(b, v));\nconst HOME_PALETTE = ['#1', '#2', '#3', '#4', '#5', '#6'];"
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text("\n".join([pre, JS[a:b], body]), encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_particles_settle_on_their_target_and_the_pointer_pushes_them(self):
        out = self._sim("""
const sim = makeOrbSim(3), tgt = (i, o) => { o[0] = 100 + i; o[1] = 50; o[2] = 0; };
for (let s = 0; s < 200; s++) stepOrbSim(sim, 3, 1 / 60, ORB_K, orbDamp(ORB_K), tgt, null);
const settled = [sim.x[0], sim.y[0], sim.x[2]];
const calm = [sim.vx[0], sim.vy[0]];
let near = 0;
for (let s = 0; s < 30; s++) stepOrbSim(sim, 3, 1 / 60, ORB_K, orbDamp(ORB_K), tgt, { x: 95, y: 50, r: 60, s: 4000 });
console.log(JSON.stringify({ settled, calm, pushed: sim.x[0] > 100.5 }));
""")
        self.assertAlmostEqual(out["settled"][0], 100, delta=0.05)
        self.assertAlmostEqual(out["settled"][1], 50, delta=0.05)
        self.assertAlmostEqual(out["settled"][2], 102, delta=0.05)
        self.assertLess(abs(out["calm"][0]) + abs(out["calm"][1]), 0.01)
        self.assertTrue(out["pushed"])                                       # pushed right by the pointer on its left

    def test_groups_are_ordered_and_filtered(self):
        out = self._run("""
const ags = [
  { id: 'a', name: 'Doctor', group: 'Health', description: 'Symptoms', keywords: ['fever'] },
  { id: 'b', name: 'Coder', group: 'Code', description: 'Programs' },
  { id: 'c', name: 'Research', group: 'Vault', description: 'Notes' },
  { id: 'd', name: 'Misc', description: 'no group' },
];
console.log(JSON.stringify({
  order: atlasGroups(ags, '', '').map(g => g.name),
  q: atlasGroups(ags, 'FEVER', '').map(g => g.agents[0].id),
  only: atlasGroups(ags, '', 'Code').map(g => g.name),
  none: atlasGroups(ags, 'nosuchthing', '').length,
}));
""")
        self.assertEqual(out["order"], ["Vault", "Health", "Code", "Other"])
        self.assertEqual(out["q"], ["a"])
        self.assertEqual(out["only"], ["Code"])
        self.assertEqual(out["none"], 0)

    def test_threads_group_by_thread_and_skip_skills_and_refused(self):
        out = self._run("""
const jobs = [
  { id: 'a1', thread: 'a1', agent: 'doctor', instruction: 'Question', started: '2026-10-10T10:00:00', status: 'ok' },
  { id: 'a2', thread: 'a1', agent: 'doctor', instruction: 'And then', started: '2026-10-10T10:05:00', status: 'running' },
  { id: 'b1', agent: 'coder', instruction: 'No thread', started: '2026-10-10T11:00:00', status: 'ok' },
  { id: 's1', agent: 'skill-x', instruction: 'Skill', started: '2026-10-10T12:00:00', status: 'ok' },
  { id: 'r1', agent: 'doctor', instruction: 'refused', started: '2026-10-10T13:00:00', status: 'refused' },
];
const t = atlasThreads(jobs);
console.log(JSON.stringify({ ids: t.map(x => x.id), n: t[1].jobs.length, live: t[1].live, title: t[1].title, agent: t[1].agent }));
""")
        self.assertEqual(out["ids"], ["b1", "a1"])      # newest first
        self.assertEqual((out["n"], out["live"], out["title"], out["agent"]), (2, True, "Question", "doctor"))


if __name__ == "__main__":
    unittest.main()
