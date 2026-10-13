"""Appearance: the forms of the galaxy, its colours, the sky, the scenery and the icons (openLookSheet, applyLook, aos.look).

The forms and the look model are pure, so they run here under Node, as the galaxy tests do: every form must be a galaxy the painters,
the flights and Atlas take unchanged, the spiral must stay exactly what it was, and the standard look must change nothing at all.
"""

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest

from tests import test_galaxy_transitions as G   # a module import: the class imported by name would run its tests a second time here
from tests.test_galaxy_transitions import FIXTURE, HTML, JS, MODEL, PAINT, PRELUDE

LOOK = JS[JS.index("// ---- The look:"): JS.index("// ---- end of the look model")]
# the painter of the backdrop (it draws on whatever 2D context it is given)
BACKDROP = JS[JS.index("const BACKDROP_TINTS"): JS.index("// A preview of a backdrop for the sheet")]
FORMS = ["spiral", "swirl", "whirlpool", "ring", "cartwheel", "elliptical", "sombrero", "antennae", "irregular", "cluster",
         "cloud", "hourglass", "supernova", "blackhole", "quasar", "comet", "planet", "solar", "atom", "helix", "wormhole"]
# buildCloud(GALAXY_N) as it was before the other forms existed (every field to 9 decimals, sha256): the standard galaxy is untouched
SPIRAL_SHA = "f31c1631fe31c2ff8045896cc9addbb7b9f989c360868ecfcce5c2f88f7c5ad1"


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class AppearanceModelTests(unittest.TestCase):
    def _run(self, body: str, paint: bool = False, raw: bool = False):
        src = PRELUDE + MODEL + (PAINT if paint else "") + LOOK + FIXTURE + body
        with tempfile.TemporaryDirectory() as d:
            f = f"{d}/t.js"
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(src)
            r = subprocess.run(["node", f], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip() if raw else json.loads(r.stdout)

    # ---- the forms ---------------------------------------------------------------------------------------------------------------
    def test_the_spiral_is_exactly_what_it_was(self):
        out = self._run("""
console.log(buildCloud(GALAXY_N).map(p => [p.x, p.y, p.z, p.r, p.ci, p.sp, p.sz, p.ph, p.br, p.arm, p.role].map(v => (+v).toFixed(9)).join(',')).join(';'));
""", raw=True)
        self.assertEqual(hashlib.sha256(out.encode()).hexdigest(), SPIRAL_SHA)
        same = self._run("""
const key = a => JSON.stringify(a);
console.log(JSON.stringify({ spiral: key(buildCloud(GALAXY_N, 'spiral')) === key(buildCloud(GALAXY_N)),
  unknown: key(buildCloud(GALAXY_N, 'blob')) === key(buildCloud(GALAXY_N)), forms: GALAXY_FORMS }));
""")
        self.assertTrue(same["spiral"])
        self.assertTrue(same["unknown"])                  # a form the page does not know is the spiral
        self.assertEqual(same["forms"], FORMS)

    def test_every_form_is_a_whole_galaxy(self):
        out = self._run("""
const res = {};
for (const form of GALAXY_FORMS) {
  const a = buildCloud(GALAXY_N, form), b = buildCloud(GALAXY_N, form);
  const picks = pickAgentStars(a, 40, T0).map(q => q.i), ci = new Set(a.map(p => p.ci));
  res[form] = { n: a.length, same: JSON.stringify(a) === JSON.stringify(b),
    roles: a.every((p, i) => p.role === galaxyRole(i)),
    inside: a.every(p => Math.hypot(p.x, p.y, p.z) <= 0.9901 && Math.abs(p.r - Math.hypot(p.x, p.y, p.z)) < 1e-9),
    fields: a.every(p => Number.isInteger(p.ci) && p.ci >= 0 && p.ci < 8 && p.br > 0 && p.br <= 1 && p.sz > 0 && isFinite(p.sp) && Math.abs(p.sp) <= 0.6 && isFinite(p.ph)),
    bright: a.filter((p, i) => isBrightOrb(i)).every(p => p.r >= 0.4 - 1e-9 && p.arm >= 0),
    agents: new Set(picks).size, agentsOk: picks.every(i => i < GALAXY_POOL && a[i].arm >= 0), colours: ci.size,
    flat: a.slice(0, GALAXY_STARS).reduce((t, p) => t + Math.abs(p.y), 0) / GALAXY_STARS };
}
console.log(JSON.stringify(res));
""")
        for form in FORMS:
            o = out[form]
            with self.subTest(form=form):
                self.assertEqual(o["n"], 11700)
                self.assertTrue(o["same"])                # seeded: the same galaxy every time
                self.assertTrue(o["roles"])               # stars, glow and dust at the indices the painters expect
                self.assertTrue(o["inside"])
                self.assertTrue(o["fields"])
                self.assertTrue(o["bright"])              # the cluster stars lie outside the centre and can become agents
                self.assertEqual(o["agents"], 40)         # Atlas finds its agents in every form
                self.assertTrue(o["agentsOk"])
                self.assertGreaterEqual(o["colours"], 4)
        # they really are different shapes: the ring and the swirl are flat discs, the cloud and the elliptical are thick
        self.assertLess(out["ring"]["flat"], out["cloud"]["flat"])
        self.assertLess(out["swirl"]["flat"], out["elliptical"]["flat"])
        self.assertEqual(len({round(out[f]["flat"], 4) for f in FORMS}), len(FORMS))

    def test_the_black_hole_keeps_its_shadow_and_faces_the_viewer(self):
        out = self._run("""
const a = buildCloud(GALAXY_N, 'blackhole'), o = [0, 0, 0], q = [0, 0, 0];
// as the home page shows it at two moments 10 s apart (the inner edge of the disc goes round in about forty seconds): positions on the screen in units of the radius
const screen = t => { const rot = homeRot(t); return a.map(p => { orbPoint(p, t, o); rotInto(rot, o[0], o[1], o[2], q); return [q[0], q[1]]; }); };
const s1 = screen(T0), s2 = screen(T0 + 10), d = (s, i) => Math.hypot(s[i][0], s[i][1]);
const inShadow = s => a.filter((p, i) => p.role !== ROLE_DUST && d(s, i) < 0.14).length;
const ring = a.map((p, i) => i).filter(i => a[i].role === ROLE_STAR && a[i].sp === -HOME_SPIN && Math.abs(d(s1, i) - 0.2) < 0.02);
const moved = Math.max(...ring.map(i => Math.hypot(s1[i][0] - s2[i][0], s1[i][1] - s2[i][1])));
const disc = a.map((p, i) => i).filter(i => a[i].role === ROLE_STAR && a[i].sp > 0 && a[i].r < 0.5);
const discMoved = disc.filter(i => Math.hypot(s1[i][0] - s2[i][0], s1[i][1] - s2[i][1]) > 0.1).length / disc.length;
console.log(JSON.stringify({ shadow: [inShadow(s1), inShadow(s2)], dark: a.filter((p, i) => p.role === ROLE_DUST && d(s1, i) < 0.12).length,
  ring: ring.length, moved, discMoved }));
""")
        self.assertEqual(out["shadow"], [0, 0])           # nothing bright in front of the shadow, whenever you look
        self.assertGreater(out["dark"], 500)              # and it is filled with dust, so it is darker than the space round it
        self.assertGreater(out["ring"], 500)              # the photon ring ...
        self.assertLess(out["moved"], 0.05)               # ... stays where it is (only the small wobble of every particle) ...
        self.assertGreater(out["discMoved"], 0.9)         # ... while the inner disc turns

    # ---- the look model ----------------------------------------------------------------------------------------------------------
    def test_the_standard_look_changes_nothing(self):
        out = self._run("""
const std = lookNorm(null);
console.log(JSON.stringify({ css: lookCss(std), isStd: lookIsStd(std), parts: Object.keys(LOOK_PARTS).every(p => lookIsStd(std, p)),
  preset: lookPreset(std), std, keys: Object.keys(LOOK_STD).sort(), partKeys: [].concat(...Object.values(LOOK_PARTS)).sort(),
  pal: JSON.stringify(GALAXY_PALETTE) === JSON.stringify(GALAXY_PALETTE_STD), dust: GALAXY_LOOK.dust === LOOK_STD.dust, form: GALAXY_LOOK.form }));
""")
        self.assertEqual(out["css"], "")                  # no style at all for the standard look
        self.assertTrue(out["isStd"])
        self.assertTrue(out["parts"])
        self.assertEqual(out["preset"], "milky")
        self.assertEqual(out["keys"], out["partKeys"])    # every field of a look belongs to exactly one part of the sheet
        self.assertTrue(out["pal"])
        self.assertTrue(out["dust"])
        self.assertEqual(out["form"], "spiral")
        self.assertEqual(out["std"]["sky"], "#000000")
        self.assertEqual(out["std"]["icons"], "default")

    def test_anything_stored_becomes_a_valid_look(self):
        out = self._run("""
const bad = [null, 7, 'x', [], { form: 'blob', stars: ['red', 3], dust: '#12', sky: 'javascript:1', glow: [1, '#ABCDEF'], icons: 'huge', iconTint: '</style>', ball: {} }];
const res = bad.map(o => lookNorm(o));
console.log(JSON.stringify({ res, parsed: [lookParse('{bad'), lookParse(''), lookParse(null), lookParse('{"form":"ring","sky":"#102030"}')],
  std: lookNorm(null) }));
""")
        std = out["std"]
        for L in out["res"][:4]:
            self.assertEqual(L, std)
        L = out["res"][4]
        self.assertEqual(L["form"], "spiral")
        self.assertEqual(L["stars"], std["stars"])
        self.assertEqual((L["dust"], L["sky"], L["icons"], L["iconTint"], L["ball"]), (std["dust"], std["sky"], "default", "", std["ball"]))
        self.assertEqual(L["glow"], [std["glow"][0], "#abcdef", std["glow"][2]])   # what is valid survives, lower-cased
        self.assertEqual(out["parsed"][0], std)
        self.assertEqual(out["parsed"][1], std)
        self.assertEqual(out["parsed"][2], std)
        self.assertEqual((out["parsed"][3]["form"], out["parsed"][3]["sky"]), ("ring", "#102030"))
        # nothing but #rrggbb ever reaches the CSS
        hexes = [c for L in out["res"] for c in L["stars"] + L["glow"] + [L["dust"], L["sky"], L["ball"]]]
        self.assertTrue(all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in hexes))

    def test_a_changed_look_writes_only_what_changed(self):
        out = self._run("""
const L = o => Object.assign(lookNorm(null), o);
console.log(JSON.stringify({
  sky: lookCss(L({ sky: '#102030' })), ball: lookCss(L({ ball: '#ff0000' })),
  glow: lookCss(L({ glow: ['#5a3fd0', '#2a4fd0', '#33ff99'] })),
  tintOff: lookCss(L({ iconTint: '#00ff00' })), tintOn: lookCss(L({ icons: 'tinted', iconTint: '#00ff00' })),
  space: lookSpace(LOOK_NEB), lum: [lookLum('#000000'), lookLum('#ffffff')], light: LOOK_LIGHT,
  partly: [lookIsStd(L({ sky: '#102030' }), 'scenery'), lookIsStd(L({ sky: '#102030' }), 'galaxy'), lookIsStd(L({ form: 'ring' }), 'form')] }));
""")
        self.assertEqual(out["sky"], ":root, body { --void: #102030 !important; }\nbody:is(.is-home, .is-brain, .is-atlas) { --sky: #102030 !important; }")
        self.assertEqual(out["ball"], ":root, body { --ball: #ff0000 !important; }")
        self.assertEqual(out["tintOff"], "")              # a tint is only written while the icons are tinted
        self.assertEqual(out["tintOn"], ":root, body { --icon-tint: #00ff00 !important; }")
        g = out["glow"]
        self.assertIn("--aurora-3: #33ff99 !important;", g)
        self.assertNotIn("--aurora-1", g)
        # the new --space, in each place a theme sets one, with the changed glow bottom left and the others as the CSS has them
        self.assertEqual(g.count("--space: "), 3)
        for sel in (':root[data-theme="dark"] {', '@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {', "body:is(.is-home, .is-brain, .is-atlas) {"):
            self.assertIn(sel, g)
        self.assertIn("rgba(51,255,153,.07)", g)
        self.assertIn("rgba(80,60,180,.2)", g)
        # lookSpace of the standard glows is, character for character, the --space of the CSS (so a changed glow changes only itself)
        css_space = re.findall(r"--space: (radial-gradient\(ellipse 55%.*?);", HTML)
        self.assertEqual(len(css_space), 3)
        for s in css_space:
            self.assertEqual(" ".join(s.split()), out["space"])
        self.assertEqual(out["lum"], [0, 1])
        self.assertAlmostEqual(out["light"], 1.05 / 4.5 - 0.05)
        self.assertEqual(out["partly"], [False, True, False])

    def test_presets_are_whole_palettes(self):
        out = self._run("""
console.log(JSON.stringify({ presets: LOOK_PRESETS.map(p => [p[0], p[1], p[2], p[3]]), std: GALAXY_PALETTE_STD, dust: LOOK_STD.dust,
  wells: LOOK_WELLS.map(w => w[0]), found: LOOK_PRESETS.map(p => lookPreset(Object.assign(lookNorm(null), { stars: p[2].slice(), dust: p[3] }))) }));
""")
        ps = out["presets"]
        self.assertEqual(ps[0][2], out["std"])            # the first is the standard
        self.assertEqual(ps[0][3], out["dust"])
        self.assertEqual(len({p[0] for p in ps}), len(ps))
        for pid, _, stars, dust in ps:
            with self.subTest(preset=pid):
                self.assertEqual(len(stars), 8)
                self.assertTrue(all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in stars + [dust]))
        self.assertEqual(out["found"], [p[0] for p in ps])  # each is recognised as itself, so its chip shows as chosen
        self.assertEqual(sorted(w for w in out["wells"] if w != "dust"), list(range(8)))   # a well for each colour, and the dust

    # ---- the accent ----------------------------------------------------------------------------------------------------------------
    def test_an_own_accent_is_a_whole_tint_that_keeps_its_contrast(self):
        out = self._run("""
const L = o => Object.assign(lookNorm(null), o);
const cols = ['#0088ff', '#ffee00', '#fffbe0', '#000000', '#ffffff', '#1a1a6e', '#00ff00', '#ff2d55', '#808080', '#7f7f7f', '#3cd3fe', '#5e2b00'];
const cr = (a, b) => { const x = lookLum(a), y = lookLum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
console.log(JSON.stringify({ std: LOOK_STD.accent, css: lookCss(L({ accent: '#ffee00' })),
  norm: ['#ABCDEF', 'red', 7, null, '</style>', '#12'].map(a => lookNorm({ accent: a }).accent),
  part: [lookIsStd(L({ accent: '#ff0000' }), 'accent'), lookIsStd(L({ accent: '#ff0000' }), 'icons'), lookIsStd(L({ accent: '#ff0000' }))],
  checks: cols.map(c => { const a = lookAccent(c); return { c, a, ink: cr(a.ink, '#f2f2f7'), inkWhite: cr(a.ink, '#ffffff'), inkD: cr(a.inkD, '#2c2c2e'), inkBlack: cr(a.inkD, '#000000'), btn: cr(a.btn, a.on) }; }) }));
""")
        self.assertEqual(out["std"], "")                  # the standard: no own colour, the tint (blue unless one is picked)
        self.assertEqual(out["norm"], ["#abcdef", "", "", "", "", ""])
        self.assertEqual(out["part"], [False, True, False])
        # an own colour writes the six tokens of a tint and nothing else; --accent, --focus and the rest follow from them
        css = out["css"]
        self.assertTrue(css.startswith(":root, body { --tint-l: #ffee00 !important; --tint-d: #ffee00 !important; --tint-ink: #"), css)
        for t in ("--tint-ink-d: #", "--tint-btn: #", "--tint-on: #000000"):   # a yellow button carries a black label, as the yellow tint
            self.assertIn(t, css)
        self.assertNotIn("--accent", css)
        for r in out["checks"]:
            with self.subTest(colour=r["c"]):
                a = r["a"]
                self.assertTrue(all(re.fullmatch(r"#[0-9a-f]{6}", a[k]) for k in ("l", "ink", "inkD", "btn", "on")))
                self.assertEqual(a["l"], r["c"])          # graphics show the very colour picked
                for k in ("ink", "inkWhite", "inkD", "inkBlack", "btn"):
                    self.assertGreaterEqual(r[k], 4.5, k)  # text and labelled buttons stay readable in both themes
                self.assertIn(a["on"], ("#ffffff", "#000000"))
        byc = {r["c"]: r["a"] for r in out["checks"]}
        self.assertEqual((byc["#1a1a6e"]["btn"], byc["#1a1a6e"]["on"]), ("#1a1a6e", "#ffffff"))   # a colour that works stays itself
        self.assertEqual(byc["#0088ff"]["l"], "#0088ff")

    # ---- the backdrop -----------------------------------------------------------------------------------------------------------
    def test_the_backdrop_is_a_choice_of_the_look_and_writes_no_css(self):
        out = self._run("""
const L = o => Object.assign(lookNorm(null), o);
console.log(JSON.stringify({ std: LOOK_STD.backdrop, kinds: LOOK_BACKDROPS, names: Object.keys(LOOK_BACKDROP_NAMES),
  norm: ['deep', 'blob', 7, null, '</style>'].map(b => lookNorm({ backdrop: b }).backdrop), parsed: lookParse('{"backdrop":"milkyway"}').backdrop,
  css: LOOK_BACKDROPS.map(b => lookCss(L({ backdrop: b }))),
  part: [lookIsStd(L({ backdrop: 'deep' }), 'backdrop'), lookIsStd(L({ backdrop: 'deep' }), 'scenery'), lookIsStd(L({ backdrop: 'deep' }))],
  groups: LOOK_FORM_GROUPS, forms: GALAXY_FORMS, unnamed: GALAXY_FORMS.filter(f => !LOOK_FORM_NAMES[f]) }));
""")
        self.assertEqual(out["std"], "quiet")
        self.assertEqual(out["kinds"][0], "quiet")        # the first choice in the sheet is the standard
        self.assertEqual(out["names"], out["kinds"])
        self.assertEqual(out["norm"], ["deep", "quiet", "quiet", "quiet", "quiet"])
        self.assertEqual(out["parsed"], "milkyway")
        self.assertEqual(set(out["css"]), {""})           # a backdrop is painted, never written into the page's CSS
        self.assertEqual(out["part"], [False, True, False])
        self.assertEqual(out["unnamed"], [])
        # the sheet's headings: the galaxies from the first form, the rest after the last galaxy
        firsts = [out["forms"].index(g[1]) for g in out["groups"]]
        self.assertEqual(firsts[0], 0)
        self.assertEqual(firsts, sorted(firsts))
        self.assertEqual([g[0] for g in out["groups"]], ["Galaxies", "Beyond"])

    def test_every_backdrop_paints_its_sky_once_and_cheaply(self):
        out = self._run(BACKDROP + """
// a 2D context that counts what is drawn and checks every alpha
const fake = () => {
  const c = { ops: 0, bad: 0, save() {}, restore() {}, translate() {}, rotate() {}, scale() {}, setTransform() {}, beginPath() {}, moveTo() {}, lineTo() {}, arc() {},
    fill() { this.ops++; }, stroke() { this.ops++; }, fillRect() { this.ops++; },
    createRadialGradient: () => ({ addColorStop(o, col) { if (!/^#[0-9a-f]{6}([0-9a-f]{2})?$/.test(col)) c.bad++; } }),
    createLinearGradient: () => ({ addColorStop(o, col) { if (!/^#[0-9a-f]{6}([0-9a-f]{2})?$/.test(col)) c.bad++; } }), globalCompositeOperation: 'source-over' };
  let a = 1;
  Object.defineProperty(c, 'globalAlpha', { get: () => a, set: v => { if (!(v >= 0 && v <= 1)) c.bad++; a = v; } });
  return c;
};
const glow = LOOK_STD.glow, res = {};
for (const kind of LOOK_BACKDROPS) {
  const a = fake(), b = fake(), t = fake(), t0 = Date.now();
  paintBackdrop(a, 1920, 1080, kind, 1, glow);
  const ms = Date.now() - t0;
  paintBackdrop(b, 1920, 1080, kind, 1, glow);
  paintBackdrop(t, 100, 66, kind, 0.4, glow);
  res[kind] = { ops: a.ops, same: a.ops === b.ops, thumb: t.ops, bad: a.bad + t.bad, end: [a.globalCompositeOperation, a.globalAlpha], ms };
}
console.log(JSON.stringify(res));
""")
        for kind, o in out.items():
            with self.subTest(kind=kind):
                self.assertEqual(o["bad"], 0)             # every colour a #rrggbb(aa), every alpha in 0..1
                self.assertTrue(o["same"])                # seeded: the same sky every time
                self.assertEqual(o["end"], ["source-over", 1])
                self.assertGreater(o["thumb"], 4 if kind == "quiet" else 15)   # the preview shows something (the quiet one a few stars)
                if kind != "quiet":
                    self.assertGreater(o["ops"], 1000)    # a full sky on a 1920 x 1080 window ...
                    self.assertLess(o["ops"], 20000)      # ... in one paint of bounded cost
        self.assertEqual(out["meteors"]["ops"], out["stars"]["ops"])   # on the page the shooting stars are elements, over the starfield

    # ---- the painters follow a change of form or colour ---------------------------------------------------------------------------
    def test_painters_rebuild_on_a_new_form_and_new_colours(self):
        out = self._run(G.GalaxyTransitionTests.GL_SIM + """
const res = {};
drawCloudScene(gctx(1440, 800), oc, scene());
glCalls.length = 0;
drawCloudScene(gctx(1440, 800), oc, scene({ t: T0 + 1 }));
res.idle = { tex: calls('texSubImage2D').length, stat: calls('bufferSubData').filter(c => c[3] && c[3].length === N * 4).length };
// a new form: the cloud is rewritten in place and the counter moves on
const ring = buildCloud(N, 'ring');
ring.forEach((p, i) => Object.assign(oc.cloud[i], p)); GALAXY_LOOK.shape++;
glCalls.length = 0;
drawCloudScene(gctx(1440, 800), oc, scene());
const st = calls('bufferSubData').find(c => c[3] && c[3].length === N * 4);
res.shape = { stat: !!st, codes: st ? Array.from(st[3]).filter((v, i) => i % 4 === 3).every((v, i) => v === oc.cloud[i].ci + 16 * oc.cloud[i].role + (isBrightOrb(i) ? 64 : 0)) : false,
  lists: oc.shape === GALAXY_LOOK.shape, dust: oc.dustIdx.every(i => oc.cloud[i].role === ROLE_DUST), tex: calls('texSubImage2D').length };
// new colours: the star, mist and dust sprites go up again and the palette of the small stars follows
GALAXY_PALETTE[3] = '#00ff00'; DOT_PAL[3] = [0, 255, 0]; GALAXY_LOOK.colour++;
glCalls.length = 0;
drawCloudScene(gctx(1440, 800), oc, scene());
res.colour = { tex: calls('texSubImage2D').length, pal: Array.from(GLX.pal.slice(9, 12)), stat: calls('bufferSubData').filter(c => c[3] && c[3].length === N * 4).length };
console.log(JSON.stringify(res));
""", paint=True)
        self.assertEqual(out["idle"], {"tex": 0, "stat": 0})   # nothing is uploaded again while the look stays
        self.assertTrue(out["shape"]["stat"])
        self.assertTrue(out["shape"]["codes"])
        self.assertTrue(out["shape"]["lists"])
        self.assertTrue(out["shape"]["dust"])
        self.assertEqual(out["shape"]["tex"], 0)
        self.assertEqual(out["colour"]["tex"], 8 + 8 + 1)  # eight star sprites, eight mist sprites, the dust
        self.assertEqual(out["colour"]["pal"], [0, 1, 0])
        self.assertEqual(out["colour"]["stat"], 0)


class AppearanceWiringTests(unittest.TestCase):
    def test_the_sheet_is_reachable_and_restored_at_start(self):
        self.assertIn("class: 'w-opt w-look'", JS)
        self.assertIn("openLookSheet(menu.querySelector('summary'))", JS)
        # and from the pen: while arranging, the bar has Appearance next to Reset layout (as Customize in the edit mode of iOS)
        self.assertRegex(JS, r"view\.editing \? h\('button', \{[^}]*'data-fk': 'bar:look'[^}]*onclick: e => openLookSheet\(e\.currentTarget\)")
        self.assertLess(JS.index("'data-fk': 'bar:look'"), JS.index("'data-fk': 'bar:reset'"))
        self.assertIn("function openLookSheet(opener)", JS)
        self.assertIn("applyLook(lookParse(store.get('look')), false);", JS)
        self.assertIn("store.set('look', lookIsStd(LOOK) ? '' : JSON.stringify(LOOK));", JS)   # the standard look stores nothing
        self.assertIn("Back to the standard look", JS)

    def test_the_css_hooks_exist(self):
        for mode in ("dark", "clear", "tinted"):
            self.assertIn(f'html[data-icons="{mode}"] .app-ico', HTML)
        self.assertIn("var(--icon-tint, var(--accent))", HTML)
        self.assertIn("background-color: var(--sky, var(--bg));", HTML)   # the sky of the space views, the theme's background without one
        self.assertNotIn("--neb-", HTML)                  # the standard --space is the original rgba() one

    def test_the_backdrop_is_wired(self):
        self.assertIn("head('Backdrop', 'backdrop'), backs", JS)
        self.assertIn("set({ backdrop: id }, true)", JS)
        self.assertIn("if (LOOK.backdrop !== prev.backdrop) syncBackdrop();", JS)
        # shown in the space views only, never on the light pages
        self.assertIn(".bg-sky { position: absolute; inset: 0; width: 100%; height: 100%; display: none; }", HTML)
        self.assertIn("body:is(.is-home, .is-brain, .is-atlas) .bg-sky { display: block; }", HTML)
        # the shooting stars move only for those who allow motion, and the aurora's 10 Hz timer leaves them alone
        self.assertIn("@media (prefers-reduced-motion: no-preference) {\n  .bg-meteor { animation: meteor ", HTML)
        self.assertIn("if (!bg || RM.matches || document.hidden", JS)
        self.assertIn("if (e.target.tagName !== 'I') return;", JS)
        # the sheet's radio groups step over their headings
        self.assertIn("g.querySelectorAll('[role=\"radio\"]')", JS)


    def test_the_accent_is_wired(self):
        # one colour everywhere: the filled buttons, the hero's words and the focus ring all come from the tint's tokens
        self.assertIn(".btn.primary { background: var(--accent-btn); color: var(--on-accent);", HTML)
        self.assertIn(".hero-title .w.grad { color: var(--accent-ink); }", HTML)
        self.assertIn("--accent: var(--tint-l); --accent-ink: var(--tint-ink); --accent-2: var(--tint-ink); --accent-btn: var(--tint-btn); --on-accent: var(--tint-on);", HTML)
        # the sheet has the nine tints and an own colour; a swatch ends an own colour, Standard and the whole reset go back to blue
        self.assertIn("head('Accent colour', 'accent', () => pickTint('blue'))", JS)
        self.assertIn("tintPicker({ 'aria-label': 'Accent colour' }), accentWells", JS)
        self.assertIn("well('Own colour', () => LOOK.accent || accentHex(), v => ({ accent: v }))", JS)
        self.assertIn("if (LOOK.accent) applyLook(Object.assign({}, LOOK, { accent: '' }), true);", JS)
        self.assertIn("onclick: () => { set(lookNorm(null), true); applyTint('blue'); }", JS)
        self.assertIn("if (LOOK.accent !== prev.accent) { syncTints(); readPalette(); bus.emit('theme'); }", JS)
        # the start restores the tint before the look, so a stored own colour is laid over it and never cleared by it
        self.assertLess(JS.index("applyTint(store.get('tint') || 'blue');"), JS.index("applyLook(lookParse(store.get('look')), false);"))
        self.assertNotIn("applyLook", JS[JS.index("function applyTint(t)"): JS.index("const tintOn =")])

    def test_the_ring_of_balls_keeps_clear_of_the_bar(self):
        # the room above the ring is measured from the title and the bar (they wrap, and grow a row while arranging), not guessed
        self.assertIn("const head = view.barEl && view.barEl.closest('.hs-head'), hr = head ? head.getBoundingClientRect() : null;", JS)
        self.assertIn("if (hb + 12 + 0.6 * S.D > top) top = fit(hb + 12 + 0.6 * S.D);", JS)
        self.assertIn("if (v.stage) v.stage.refit();", JS)   # a new bar (arranging on and off) lays the ring out again

if __name__ == "__main__":
    unittest.main()
