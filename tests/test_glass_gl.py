"""The liquid glass of the home panes, painted by the graphics card: the pure model under Node, and what the shader, the page and
the style sheet have to agree on.

No browser and no GPU in the suite: the maths (what the see-through slider means for the shader, the shape of the bend) lives in the
"homescreen model" block and runs as it is; the shader source, the wiring into the stage and the CSS are checked as text. How it looks
and what it costs on a given graphics card is checked by eye and by measurement; the numbers are in docs/design.md.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
SCRIPT = re.search(r"<script>\n(.*?)</script>", HTML, re.S).group(1)
MODEL = SCRIPT[SCRIPT.index("// ---- homescreen model"): SCRIPT.index("// ---- end of the homescreen model")]
PASS = SCRIPT[SCRIPT.index("const GLG_VS = `"): SCRIPT.index("function createHomeStage(view) {")]
STAGE = SCRIPT[SCRIPT.index("function createHomeStage(view) {"): SCRIPT.index("/* Return flight:")]
VS = re.search(r"const GLG_VS = `(.*?)`;", PASS, re.S).group(1)
FS = re.search(r"const GLG_FS = `(.*?)`;", PASS, re.S).group(1)
CSS = HTML[HTML.index("<style>"): HTML.index("</style>")]
RENDER = PASS[PASS.index("  function render(S) {"):]


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class GlassModelTests(unittest.TestCase):
    def _run(self, body: str):
        src = f"""
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const STORE = {{}};
const store = {{ get: k => (k in STORE ? STORE[k] : null), set: (k, v) => {{ STORE[k] = v; }} }};
{MODEL}
{body}
"""
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_the_slider_drives_every_strength(self):
        out = self._run("""
          const rows = [];
          for (let v = 0; v <= 100; v += 5) rows.push([v, glassGl(v, 1)]);
          console.log(JSON.stringify(rows));
        """)
        by = {v: g for v, g in out}
        self.assertFalse(by[0]["on"])                                # matte: opaque panes, nothing to paint
        self.assertTrue(by[5]["on"])
        self.assertTrue(by[100]["on"])
        for key in ("refr", "disp", "sat", "rim"):                   # more see-through: more bend, more dispersion, more colour, more edge light
            vals = [g[key] for v, g in out if v >= 5]
            self.assertEqual(vals, sorted(vals), key)
            self.assertGreater(vals[-1], vals[0], key)
        self.assertGreaterEqual(by[5]["refr"], 0.3)
        self.assertEqual(by[100]["refr"], 1)
        self.assertEqual(by[100]["disp"], 1)

    def test_the_blur_follows_the_glass_tokens_and_the_screen_density(self):
        out = self._run("""
          console.log(JSON.stringify({ blur: [0, 60, 100].map(v => glassTokens(v).blur), d1: glassGl(60, 1).lod, d2: glassGl(60, 2).lod,
            clear: glassGl(100, 1).lod, matte: glassGl(0, 1).lod }));
        """)
        self.assertEqual(out["blur"], [0, 11, 5])
        self.assertAlmostEqual(out["d2"] - out["d1"], 1.0, places=2)   # twice the pixels, one more mip level for the same blur
        self.assertLess(out["clear"], out["d1"])                      # liquid is clearer than the default
        self.assertEqual(out["matte"], 0)
        self.assertGreater(out["d1"], 3)

    def test_out_of_range_values_are_clamped_like_the_slider(self):
        out = self._run("console.log(JSON.stringify([glassGl(-20, 1), glassGl(500, 1), glassGl('x', 1), glassGl(60, 1), glassGl(100, 1)]));")
        self.assertFalse(out[0]["on"])
        self.assertEqual(out[1], out[4])                              # above 100 is 100
        self.assertEqual(out[2], out[3])                              # not a number: the default look

    def test_the_bezel_never_exceeds_its_pane(self):
        out = self._run("""
          const cases = [[400, 300, 26, 1], [400, 300, 52, 2], [40, 20, 26, 1], [30, 400, 18, 1.25], [4, 4, 0, 1], [900, 900, 200, 1]];
          console.log(JSON.stringify(cases.map(c => glassBezel(...c))));
        """)
        self.assertAlmostEqual(out[0], 23.4, places=1)                # 0.9 of the corner radius
        self.assertAlmostEqual(out[1], 46.8, places=1)                # the same pane at twice the density
        self.assertAlmostEqual(out[2], 6.0, places=1)                 # a thin pane: 0.3 of its short side
        self.assertAlmostEqual(out[3], 9.0, places=1)
        self.assertEqual(out[4], 2)                                   # never thinner than 2 px
        self.assertEqual(out[5], 30)                                  # and never wider than 30 css px

    def test_the_bend_is_flat_inside_and_strongest_at_the_edge(self):
        out = self._run("""
          const ts = Array.from({ length: 101 }, (_, i) => i / 100);
          console.log(JSON.stringify({ at: ts.map(t => glassShift(t)), n1: glassShift(0.3, 1.0), n2: glassShift(0.3, 2.0), n15: glassShift(0.3) }));
        """)
        at = out["at"]
        self.assertAlmostEqual(at[100], 0.0, places=6)                # the flat middle bends nothing
        self.assertAlmostEqual(at[0], 1.0, delta=0.06)                # the wall of the bezel: about one bezel width
        for i in range(1, 101):
            self.assertLessEqual(at[i], at[i - 1] + 1e-9, i)          # the steeper the slope, the bigger the shift
        self.assertGreaterEqual(min(at), -1e-9)
        # the sampled depth t + shift folds back near the rim: the image there is inverted, as it is in a glass bead
        depth = [t / 100 + s for t, s in enumerate(at)]
        self.assertTrue(any(depth[i + 1] < depth[i] - 1e-6 for i in range(100)))
        self.assertLess(out["n1"], 1e-9)                              # no glass (index 1): no bend
        self.assertLess(out["n15"], out["n2"])                        # denser glass bends more

    def test_the_shader_has_the_same_lines_as_the_model(self):
        # glassShift and the fragment shader are one formula written twice
        self.assertIn("float s = u3 / pow(max(1.0 - u4, 0.001), 0.75), th = atan(s * 0.9);", FS)
        self.assertIn("Math.pow(Math.max(1 - u4, 0.001), 0.75)", MODEL)
        self.assertIn("Math.atan(slope * 0.9)", MODEL)
        self.assertIn("tan(th - asin(sin(th) / 1.5)) * 0.9", FS)
        self.assertIn("Math.tan(th - Math.asin(Math.sin(th) / n)) * 0.9", MODEL)
        self.assertIn("function glassShift(t, n = 1.5)", MODEL)


class GlassShaderTests(unittest.TestCase):
    def test_both_stages_are_es_300(self):
        for src in (VS, FS):
            self.assertTrue(src.startswith("#version 300 es\n"))
            self.assertIn("precision highp float;", src)
            self.assertEqual(src.count("{"), src.count("}"))
            self.assertEqual(src.count("("), src.count(")"))

    def test_what_the_vertex_stage_hands_over_the_fragment_stage_takes(self):
        outs = set(re.findall(r"^(?:flat )?out (?:vec\d|float) (\w+);", VS, re.M))
        ins = set(re.findall(r"^(?:flat )?in (?:vec\d|float) (\w+);", FS, re.M))
        self.assertEqual(outs, ins)
        self.assertEqual(outs, {"vP", "vRect", "vMisc", "vCol"})
        for name in ("vRect", "vMisc", "vCol"):                       # a flat varying is flat on both sides
            self.assertRegex(VS, r"flat out vec\d " + name)
            self.assertRegex(FS, r"flat in vec\d " + name)

    def test_the_uniforms_the_script_sets_are_declared(self):
        listed = re.search(r"\[('uTex'[^\]]*)\]\.forEach", PASS).group(1)
        names = re.findall(r"'(u\w+)'", listed)
        self.assertEqual(names, ["uTex", "uRes", "uA", "uB", "uL"])
        self.assertEqual(set(names), set(re.findall(r"uniform \w+ (u\w+);", VS + FS)))
        for n in names:
            self.assertRegex(RENDER, r"\bu\." + n + r"\b", n)         # and each one is set

    def test_the_attributes_and_the_instance_layout_agree(self):
        self.assertEqual(re.findall(r"^in vec\d (a\w+);", VS, re.M), ["aC", "aRect", "aMisc", "aCol"])
        # 12 floats per pane: three vec4 at byte 0, 16 and 32, stride 48
        self.assertIn("[['aRect', 0], ['aMisc', 16], ['aCol', 32]]", PASS)
        self.assertIn("gl.vertexAttribPointer(l, 4, gl.FLOAT, false, 48, at)", PASS)
        self.assertIn("gl.vertexAttribDivisor(l, 1)", PASS)
        self.assertIn("buf: new Float32Array(12 * 64)", PASS)
        self.assertIn("const o = n * 12", PASS)

    def test_only_what_is_inside_the_pane_is_drawn_and_every_pixel_costs_the_same(self):
        self.assertIn("if (cov <= 0.0) discard;", FS)
        self.assertIn("* (cov * vMisc.z)", FS)                        # edge anti-aliasing and the pane's opacity
        self.assertIn("textureLod(", FS)                              # the blur is a mip level, not a kernel of many taps
        self.assertNotIn("for (", FS)


class GlassWiringTests(unittest.TestCase):
    def test_the_stage_owns_one_pass_and_draws_it_last(self):
        self.assertIn("const glass = createGlassPass(view, surf, root, () => touch(60));", STAGE)
        draw = STAGE[STAGE.index("  function draw() {"): STAGE.index("  // Redraws for a while although the loop is off")]
        self.assertLess(draw.index("drawCloudScene(ctx, orb,"), draw.index("glass.render(S);"))
        # the flight draws the cloud full screen: the early return leaves the glass of the last frame under the fading tiles
        self.assertLess(draw.index("if (S.flying)"), draw.index("glass.render(S);"))
        self.assertIn("glass.destroy();", STAGE)
        self.assertIn("glass: glass.active", STAGE)
        self.assertIn("    touch,\n", STAGE)

    def test_the_copy_is_taken_before_the_holes_are_cut(self):
        up, cut, draw = RENDER.index("gl.texSubImage2D("), RENDER.index("destination-out"), RENDER.index("gl.drawArraysInstanced(")
        self.assertLess(up, cut)
        self.assertLess(cut, draw)
        self.assertIn("gl.generateMipmap(gl.TEXTURE_2D);", RENDER)
        self.assertIn("gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);", PASS)   # the canvas is premultiplied already

    def test_the_slider_and_the_glass_switch_decide_whether_it_runs(self):
        self.assertIn("LG.mode !== 'lens'", RENDER)                   # Frost and Flat are other steps of the same switch
        self.assertIn("!(view.glass > GLASS_MATTE)", RENDER)          # the matte end has opaque panes: nothing to do
        self.assertIn("!view.wide", RENDER)                           # below the wide layout the tiles sit under the stage, not over it
        self.assertIn("glassGl(view.glass,", RENDER)
        self.assertIn("if (v.stage && v.stage.touch) v.stage.touch(300);", SCRIPT)   # the slider redraws a stage whose loop is off

    def test_without_the_graphics_card_nothing_changes(self):
        sup = PASS[PASS.index("const glassGlSupported"): PASS.index("// The pass of one home stage.")]
        self.assertIn("store.get('gl') === '0'", sup)                 # the same switch as the galaxy painter
        self.assertIn("failIfMajorPerformanceCaveat: true", sup)
        self.assertIn("webglcontextlost", PASS)
        self.assertIn("e.preventDefault();", PASS)
        off = PASS[PASS.index("  function off() {"): PASS.index("  // \"#rrggbb\"")]
        self.assertIn("classList.remove('hs-glx')", off)
        self.assertIn("cv.hidden = true", off)

    def test_the_panes_lose_their_backdrop_filter_only_while_the_pass_runs(self):
        m = re.search(r"html:root body \.hs-grid\.hs-glx :is\(\.card, \.kpi, \.deadline, \.hero\) \{([^}]*)\}", CSS)
        self.assertTrue(m)
        self.assertIn("backdrop-filter: none", m.group(1))
        self.assertIn("--lg-rim: transparent", m.group(1))            # the lit edge is the pass's
        self.assertEqual(len(re.findall(r"classList\.add\('hs-glx'\)", SCRIPT)), 1)   # the pass is the only one that sets the class

    def test_small_controls_keep_their_svg_lens_and_panes_are_left_to_the_pass(self):
        eng = SCRIPT[SCRIPT.index("const LG = (() => {"): SCRIPT.index("function sparkline(")]
        self.assertIn("el.closest('.hs-glx') && (el.matches('.kpi') || el.parentElement.closest('.card, .kpi, .deadline, .hero'))", eng)
        self.assertIn("LG.refresh();", PASS)                          # the lens plan is made again when the pass turns on or off

    def test_the_pass_reads_layout_in_one_sweep_and_builds_no_html(self):
        body = PASS[PASS.index("  function collect("): PASS.index("  // Paints the glass of this frame.")]
        self.assertNotIn(".style.", body)                             # no DOM writes between the reads: no layout thrash
        self.assertIn("getBoundingClientRect()", body)
        self.assertIn("getComputedStyle(tile).opacity", body)         # a tile that fades out takes its glass with it
        for bad in (".innerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write", "<script"):
            self.assertNotIn(bad, PASS)

    def test_a_canvas_the_card_cannot_hold_or_a_lost_context_falls_back_cleanly(self):
        build = PASS[PASS.index("  function build() {"): PASS.index("  function on(grid) {")]
        self.assertIn("failIfMajorPerformanceCaveat: true", build)    # the real context asks for hardware, as the probe did
        self.assertIn("gl.getParameter(gl.MAX_TEXTURE_SIZE)", build)
        self.assertIn("Math.max(W, H) > G.max", RENDER)               # too large for a texture: DOM frost, not black panes
        self.assertIn("gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);", RENDER)
        self.assertIn("WEBGL_lose_context", build)                    # a shader that does not build lets its context go
        self.assertIn("off(); again(); });", PASS)                    # lost: the stage is repainted (reduced motion has no loop)
        self.assertIn("webglcontextrestored", PASS)

    def test_the_glass_fades_with_the_panes_during_a_flight(self):
        self.assertIn("body.is-zooming :is(.hs-grid, .hs-dots, .hs-glass) { opacity: 0; transition: opacity .3s ease; }", CSS)
        self.assertIn("cv.className = 'hs-glass'", PASS)

    def test_the_shader_writes_valid_premultiplied_colour(self):
        self.assertIn("vec3 rgb = min(col.rgb + mix(vec3(1.0), vCol, 0.3) * light, vec3(1.0));", FS)
        self.assertIn("max(rgb.r, max(rgb.g, rgb.b))", FS)             # no channel above alpha
        self.assertIn("o = vec4(rgb, a) * (cov * vMisc.z);", FS)


if __name__ == "__main__":
    unittest.main()
