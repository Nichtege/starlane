"""Liquid glass: the pure model of dashboard.html (lens map, bezel, budget plan, mode choice) run under Node, plus static
checks that the engine and the CSS agree on what they exchange.

No browser: the block between `// ---- liquid glass model` and `// ---- end of the liquid glass model` has no DOM access, so
these tests run the very code the page runs. What no unit test can show (how the lens looks, what it costs on a given GPU) is
checked by eye and by measurement; the numbers are in docs/design.md.
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
START = "// ---- liquid glass model"
END = "// ---- end of the liquid glass model"
MODEL = JS[JS.index(START): JS.index(END)]
ENGINE = JS[JS.index(END): JS.index("function sparkline(")]
PRELUDE = "const clamp = (v, a, b) => Math.max(a, Math.min(b, v));\n"


def _css() -> str:
    return HTML[HTML.index("<style>"): HTML.index("</style>")]


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class LensModelTests(unittest.TestCase):
    def _run(self, body: str):
        src = JS_I18N + PRELUDE + MODEL + "\n" + body
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    # ---- the displacement map ------------------------------------------------------------------------------------------
    def test_map_is_neutral_inside_and_outside_the_rim(self):
        out = self._run("""
          const w = 120, h = 60, r = 18, b = lgBezel(w, h), m = lgLensMap(w, h, r, b);
          const at = (x, y) => [m[(y * w + x) * 4], m[(y * w + x) * 4 + 1], m[(y * w + x) * 4 + 2], m[(y * w + x) * 4 + 3]];
          // depth of a pixel inside the rounded rectangle; the rim is the outermost b pixels
          console.log(JSON.stringify({ b, len: m.length, centre: at(60, 30), deep: at(60, 30 - Math.floor(b) - 2),
            corner: at(0, 0), corner2: at(w - 1, h - 1) }));
        """)
        self.assertEqual(out["len"], 120 * 60 * 4)
        self.assertEqual(out["centre"], [128, 128, 128, 255])
        self.assertEqual(out["deep"], [128, 128, 128, 255])
        # the pixel outside the corner arc moves nothing (it is never visible anyway)
        self.assertEqual(out["corner"], [128, 128, 128, 255])
        self.assertEqual(out["corner2"], [128, 128, 128, 255])

    def test_rim_leans_along_the_outward_normal(self):
        out = self._run("""
          const w = 120, h = 60, r = 18, b = lgBezel(w, h), m = lgLensMap(w, h, r, b);
          const R = (x, y) => m[(y * w + x) * 4], G = (x, y) => m[(y * w + x) * 4 + 1];
          console.log(JSON.stringify({ left: R(0, 30), right: R(w - 1, 30), top: G(60, 0), bottom: G(60, h - 1),
            leftG: G(0, 30), topR: R(60, 0),
            // on the corner arc, 1.7 px inside the edge: both channels lean (towards the top left here)
            diagR: R(6, 6), diagG: G(6, 6) }));
        """)
        self.assertLess(out["left"], 128)           # the left edge looks further left (outwards)
        self.assertGreater(out["right"], 128)
        self.assertLess(out["top"], 128)
        self.assertGreater(out["bottom"], 128)
        self.assertEqual(out["leftG"], 128)         # a vertical edge shifts only horizontally
        self.assertEqual(out["topR"], 128)
        self.assertLess(out["diagR"], 128)
        self.assertLess(out["diagG"], 128)

    def test_map_is_mirror_symmetric(self):
        out = self._run("""
          const w = 90, h = 50, r = 14, b = lgBezel(w, h), m = lgLensMap(w, h, r, b);
          let worst = 0;
          const P = (x, y, c) => m[(y * w + x) * 4 + c];
          for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
            // left/right: R mirrors around 128, G is equal. top/bottom: G mirrors, R equal.
            worst = Math.max(worst, Math.abs((P(x, y, 0) - 128) + (P(w - 1 - x, y, 0) - 128)), Math.abs(P(x, y, 1) - P(w - 1 - x, y, 1)));
            worst = Math.max(worst, Math.abs((P(x, y, 1) - 128) + (P(x, h - 1 - y, 1) - 128)), Math.abs(P(x, y, 0) - P(x, h - 1 - y, 0)));
          }
          console.log(JSON.stringify({ worst }));
        """)
        self.assertLessEqual(out["worst"], 1)       # byte rounding only

    def test_strength_falls_off_monotonically_from_the_edge(self):
        out = self._run("""
          const w = 160, h = 80, r = 24, b = lgBezel(w, h), m = lgLensMap(w, h, r, b);
          const mag = [];
          for (let x = 0; x < Math.ceil(b) + 4; x++) mag.push(128 - m[(40 * w + x) * 4]);
          console.log(JSON.stringify({ b, mag }));
        """)
        mag = out["mag"]
        self.assertGreater(mag[0], 100)             # nearly full strength at the very edge
        self.assertLessEqual(mag[0], 127)           # ... and never beyond the byte range
        for a, b in zip(mag, mag[1:]):
            self.assertGreaterEqual(a, b)
        self.assertEqual(mag[-1], 0)                # nothing left past the bezel

    def test_tiny_and_extreme_shapes_do_not_break(self):
        out = self._run("""
          const res = [];
          for (const [w, h, r] of [[8, 8, 99], [9, 200, 0], [200, 9, 4.5], [1, 1, 0], [64, 64, 32]]) {
            const m = lgLensMap(w, h, r, lgBezel(w, h));
            let bad = 0;
            for (let i = 0; i < m.length; i += 4) if (m[i + 3] !== 255 || m[i + 2] !== 128) bad++;
            res.push({ w, h, n: m.length / 4, bad });
          }
          console.log(JSON.stringify(res));
        """)
        for item in out:
            self.assertEqual(item["n"], item["w"] * item["h"])
            self.assertEqual(item["bad"], 0)        # alpha always opaque, blue always neutral

    # ---- sizes ---------------------------------------------------------------------------------------------------------
    def test_bezel_scale_and_radius_clamps(self):
        out = self._run("""
          console.log(JSON.stringify({
            b: [lgBezel(10, 10), lgBezel(40, 30), lgBezel(100, 100), lgBezel(1000, 1000), lgBezel(200, 6)],
            s: [lgScale(3), lgScale(8), lgScale(14), lgScale(40)],
            r: [lgRadius(100, 40, 999), lgRadius(100, 40, 10), lgRadius(100, 40, -5), lgRadius(0, 0, 10)] }));
        """)
        self.assertEqual(out["b"], [3, 9, 14, 14, 3])
        for got, want in zip(out["s"], [8, 17.6, 30.8, 32]):
            self.assertAlmostEqual(got, want, places=6)
        self.assertEqual(out["r"], [20, 10, 0, 0])

    def test_chroma_only_pays_for_tiny_pieces(self):
        out = self._run("console.log(JSON.stringify([lgChroma(90, 100), lgChroma(91, 100), lgChroma(40, 40), lgChroma(300, 200)]));")
        self.assertEqual(out, [True, False, True, False])

    # ---- the budget ----------------------------------------------------------------------------------------------------
    def test_plan_respects_priority_then_size(self):
        out = self._run("""
          const items = [{ w: 100, h: 100, p: 1 }, { w: 20, h: 20, p: 0 }, { w: 50, h: 50, p: 0 }];
          // costs at dpr 1: 10000 (no chroma), 400 * 2 = 800, 2500 * 2 = 5000
          console.log(JSON.stringify({
            tight: [...lgPlan(items, 6000, 1)].sort(), exact: [...lgPlan(items, 15800, 1)].sort(), under: [...lgPlan(items, 15799, 1)].sort(),
            none: [...lgPlan(items, 0, 1)], all: [...lgPlan(items, 1e9, 1)].sort() }));
        """)
        self.assertEqual(out["tight"], [1, 2])
        self.assertEqual(out["exact"], [0, 1, 2])
        self.assertEqual(out["under"], [1, 2])
        self.assertEqual(out["none"], [])
        self.assertEqual(out["all"], [0, 1, 2])

    def test_plan_skips_what_does_not_fit_but_keeps_looking(self):
        out = self._run("""
          const items = [{ w: 300, h: 300, p: 0 }, { w: 30, h: 30, p: 1 }, { w: 0, h: 40, p: 1 }];
          console.log(JSON.stringify([...lgPlan(items, 5000, 1)]));
        """)
        self.assertEqual(out, [1])                  # the big first-priority piece does not fit; the small one still does; zero area never

    def test_plan_cost_grows_with_the_square_of_the_pixel_ratio(self):
        out = self._run("""
          const items = [{ w: 100, h: 50, p: 0 }];     // 5000 css px², chroma: 10000 device px² at dpr 1, 40000 at dpr 2
          console.log(JSON.stringify({ d1: [...lgPlan(items, 20000, 1)], d2: [...lgPlan(items, 20000, 2)], d2big: [...lgPlan(items, 40000, 2)] }));
        """)
        self.assertEqual(out, {"d1": [0], "d2": [], "d2big": [0]})

    def test_default_budget_is_what_was_measured(self):
        out = self._run("console.log(JSON.stringify(LG_BUDGET));")
        self.assertEqual(out, 150000)

    # ---- the mode ------------------------------------------------------------------------------------------------------
    def test_mode_matrix(self):
        out = self._run("""
          const res = [];
          for (const pref of [null, 'flat', 'frost', 'lens', 'bogus', undefined])
            for (const sup of [true, false]) for (const red of [true, false])
              res.push([String(pref), sup, red, lgMode(pref, sup, red)]);
          console.log(JSON.stringify(res));
        """)

        def expect(pref, sup, red):
            want = pref if pref in ("flat", "frost", "lens") else ("flat" if red else "lens")
            return "frost" if want == "lens" and not sup else want

        self.assertEqual(len(out), 24)
        for pref, sup, red, got in out:
            self.assertEqual(got, expect(pref, sup, red), (pref, sup, red))

    def test_stored_choice_wins_over_reduced_transparency(self):
        out = self._run("console.log(JSON.stringify([lgMode('lens', true, true), lgMode('frost', true, true), lgMode(null, true, true)]));")
        self.assertEqual(out, ["lens", "frost", "flat"])


class EngineContractTests(unittest.TestCase):
    """The script and the style sheet exchange three custom properties and one attribute; these keep both sides honest."""

    def test_engine_only_writes_what_the_css_reads(self):
        props = re.search(r"const LG_PROPS = \[([^\]]*)\]", ENGINE).group(1)
        names = re.findall(r"'(--lg-[\w-]+)'", props)
        self.assertEqual(names, ["--lg-f", "--lg-bc", "--lg-blur"])
        css = _css()
        for n in names:
            self.assertRegex(css, r"var\(" + re.escape(n) + r"[,)]", n + " is set by the engine but never read")
        # everything the engine sets, it also removes again when a piece loses its lens
        for n in names:
            self.assertIn("setProperty('" + n + "'", ENGINE)
        self.assertIn("LG_PROPS.forEach(p => el.style.removeProperty(p))", ENGINE)

    def test_every_lens_candidate_has_a_glass_rule_that_reads_the_lens(self):
        sels = re.search(r"const LG_LENS = \[(.*?)\];", ENGINE, re.S).group(1)
        classes = set(re.findall(r"\.[\w-]+", " ".join(re.findall(r"'([^']*)'", sels))))
        self.assertGreaterEqual(len(classes), 10)
        css = _css()
        heads = []
        for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            if "var(--lg-f" in m.group(2):
                heads.append(m.group(1))
        glass = " ".join(heads)
        for cls in sorted(classes):
            self.assertIn(cls, glass, cls + " gets a lens from the script but no glass rule reads it")

    def test_header_button_sits_between_refresh_and_theme(self):
        m = re.search(r'<button id="refresh"[^>]*>.*?</button>\s*<button id="glass" class="btn" type="button"></button>\s*<button id="theme"', HTML, re.S)
        self.assertTrue(m, "the glass switch is missing from the header")
        self.assertIn("LG.init();", JS)
        self.assertRegex(JS, r"moveInd\(\);\s*LG\.refresh\(0\);")

    def test_choice_is_stored_under_documented_keys(self):
        self.assertIn("store.set('glass', next)", ENGINE)
        self.assertIn("store.get('glassBudget')", ENGINE)
        # a budget of 0 is allowed (frost only), a negative or non-numeric knob is ignored
        self.assertIn("Number.isFinite(+kb) && +kb >= 0", ENGINE)

    def test_lens_only_where_chromium_can_draw_it(self):
        self.assertIn("CSS.supports('backdrop-filter', 'url(#a) blur(1px)')", ENGINE)
        self.assertIn("/\\b(Chrome|Edg|OPR)\\/\\d/.test(UA)", ENGINE)
        # the lens step exists where the SVG lens (Chromium) or the glass of the panes (WebGL2) can run; without either the cycle
        # skips it instead of offering a switch that does nothing
        self.assertIn("const lensOK = () => supported || glassGlSupported();", ENGINE)
        self.assertIn("lensOK() ? ['lens', 'frost', 'flat'] : ['frost', 'flat']", ENGINE)
        self.assertIn("if (mode === 'lens' && supported) {", ENGINE)       # the SVG lens of small controls stays Chromium only

    def test_pieces_inside_other_glass_and_off_screen_get_nothing(self):
        self.assertIn("if (nested(el)) return;", ENGINE)
        self.assertIn("q.bottom < 0 || q.top > vh || q.right < 0 || q.left > vw", ENGINE)
        self.assertIn("if (w < 8 || h < 8) return;", ENGINE)
        # the filter is built in the element's own (unzoomed) pixels: offsetWidth, not getBoundingClientRect
        self.assertIn("el.offsetWidth, h = el.offsetHeight", ENGINE)

    def test_filter_cache_is_bounded(self):
        self.assertIn("made.size > 160", ENGINE)
        self.assertIn("old.remove()", ENGINE)

    def test_engine_builds_dom_without_html_strings(self):
        for bad in (".innerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write"):
            self.assertNotIn(bad, ENGINE + MODEL)

    def test_script_has_no_literal_script_tag(self):
        # the server stamps a nonce onto every "<script" it finds in the template: a literal in a string or comment would be stamped too
        self.assertEqual(HTML.count("<script"), 3)             # the language and data islands and the script itself, nothing else
        self.assertNotIn("<script", ENGINE + MODEL)
        self.assertNotIn("</script", ENGINE + MODEL)

    def test_filter_primitives_are_the_supported_set(self):
        for prim in ("feImage", "feDisplacementMap", "feColorMatrix", "feBlend"):
            self.assertIn(prim, ENGINE)
        # the map is a data: URL (the page CSP allows img-src data:, never a network source)
        self.assertIn("toDataURL('image/png')", ENGINE)
        self.assertNotIn("http://", ENGINE.replace("http://www.w3.org", ""))


class DesignNoteTests(unittest.TestCase):
    DOC = (ROOT / "docs" / "design.md").read_text(encoding="utf-8")

    def test_reference_is_credited_and_the_other_one_is_explained(self):
        self.assertIn("https://github.com/callstack/liquid-glass", self.DOC)
        self.assertIn("(MIT)", self.DOC)
        self.assertIn("no code is shared", self.DOC)
        self.assertIn("https://github.com/ybouane/liquidglass", self.DOC)
        self.assertIn("not adopted", self.DOC)

    def test_documented_constants_are_the_ones_in_the_code(self):
        budget = re.search(r"const LG_BUDGET = (\d+);", MODEL).group(1)
        chroma = re.search(r"const LG_CHROMA = (\d+);", MODEL).group(1)
        cache = re.search(r"made\.size > (\d+)", ENGINE).group(1)
        self.assertIn("**" + budget + " device px²**", self.DOC)
        self.assertIn("up to " + chroma + " css px²", self.DOC)
        self.assertIn("LRU, " + cache + " entries", self.DOC)
        for key in ("aos.glass", "aos.glassBudget"):
            self.assertIn("`" + key + "`", self.DOC)

    def test_note_is_linked_from_the_entry_points(self):
        for rel in ("README.md", "CONTRIBUTING.md", "docs/architecture.md"):
            self.assertIn("design.md", (ROOT / rel).read_text(encoding="utf-8"), rel)

    def test_every_token_in_the_note_exists(self):
        css = _css()
        for tok in re.findall(r"--lg-[\w-]+", self.DOC):
            if tok in ("--lg-f", "--lg-bc", "--lg-blur"):
                continue
            self.assertIn(tok, css, tok)


if __name__ == "__main__":
    unittest.main()
