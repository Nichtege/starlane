"""The iOS 27 language of dashboard.html: tints, label and status contrast, app icons, the controls of the kit (switch, slider,
radii), type and the glass material. Every contrast claim in the stylesheet is recomputed here (WCAG 2.x relative luminance),
with translucent colours composited over the surface they sit on. Static checks, no browser needed."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
CSS = HTML[: HTML.index("</style>")]
JS = re.search(r"<script>\n(.*?)</script>", HTML, re.S).group(1)

TINT_IDS = ["blue", "purple", "pink", "red", "orange", "yellow", "green", "indigo", "graphite"]
WHITE, GROUPED, BLACK, DARK_1, DARK_2 = (255, 255, 255), (242, 242, 247), (0, 0, 0), (28, 28, 30), (44, 44, 46)


def rgb(text: str):
    """'#rrggbb' or 'rgba(r,g,b,a)' -> ((r, g, b), alpha)."""
    text = text.strip()
    if text.startswith("#"):
        return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5)), 1.0
    nums = [float(x) for x in re.match(r"rgba?\(([^)]*)\)", text).group(1).split(",")]
    return tuple(nums[:3]), (nums[3] if len(nums) > 3 else 1.0)


def over(colour: str, base):
    """The colour as it is seen on an opaque base."""
    c, a = rgb(colour)
    return tuple(f * a + b * (1 - a) for f, b in zip(c, base))


def lum(c):
    lin = [v / 255 for v in c]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in lin]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a, b) -> float:
    la, lb = sorted([lum(a), lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def block(start: str) -> str:
    i = CSS.index(start)
    return CSS[i: CSS.index("\n}", i)]


def tok(blk: str, name: str) -> str:
    m = re.search(r"--" + re.escape(name) + r": (#[0-9a-fA-F]{6}|rgba?\([^)]*\))", blk)
    assert m, name
    return m.group(1)


LIGHT = block(":root {\n  color-scheme: light;")
DARKS = {"explicit dark": block(':root[data-theme="dark"] {'),
         "system dark": block('@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {'),
         "stage": block("body.is-home, body.is-brain, body.is-atlas {")}


def tints() -> dict:
    out = {}
    for m in re.finditer(r'^:root(?:, :root)?\[data-tint="(\w+)"\] \{([^}]*)\}', CSS, re.M):
        out[m.group(1)] = dict(re.findall(r"--(tint-[\w-]+): (#[0-9a-f]{6})", m.group(2)))
    return out


class TintTests(unittest.TestCase):
    def test_the_nine_tints_of_ios_each_with_every_token(self):
        t = tints()
        self.assertEqual(list(t), TINT_IDS)
        for name, toks in t.items():
            self.assertEqual(sorted(toks), ["tint-btn", "tint-d", "tint-ink", "tint-ink-d", "tint-l", "tint-on"], name)
        self.assertIn(':root, :root[data-tint="blue"] {', CSS)            # blue is the default: no attribute needed
        self.assertEqual(t["blue"]["tint-l"], "#0088ff")                   # the system blue of iOS 27

    def test_tinted_text_and_labels_on_tinted_fills_are_readable(self):
        for name, k in tints().items():
            ink, ink_d = rgb(k["tint-ink"])[0], rgb(k["tint-ink-d"])[0]
            for bg in (WHITE, GROUPED):
                self.assertGreaterEqual(ratio(ink, bg), 4.5, (name, "ink", bg))
            for bg in (BLACK, DARK_1, DARK_2):
                self.assertGreaterEqual(ratio(ink_d, bg), 4.5, (name, "ink-d", bg))
            self.assertGreaterEqual(ratio(rgb(k["tint-btn"])[0], rgb(k["tint-on"])[0]), 4.5, (name, "button label"))

    def test_the_tint_tokens_are_wired_to_the_accent_roles(self):
        self.assertIn("--accent: var(--tint-l); --accent-ink: var(--tint-ink); --accent-2: var(--tint-ink); --accent-btn: var(--tint-btn); --on-accent: var(--tint-on);", LIGHT)
        for where, blk in DARKS.items():
            self.assertIn("--accent: var(--tint-d); --accent-ink: var(--tint-ink-d);", blk, where)

    def test_script_css_and_swatches_know_the_same_tints(self):
        js_ids = re.findall(r"\['(\w+)', tr\('\w+'\)\]", re.search(r"const TINTS = \[(.*?)\];", JS).group(1))
        self.assertEqual(js_ids, TINT_IDS)
        swatches = dict(re.findall(r'\.w-tint\[data-tint="(\w+)"\] \{ --sw: (#[0-9a-f]{6}); \}', CSS))
        self.assertEqual(sorted(swatches), sorted(TINT_IDS))
        for name, k in tints().items():
            self.assertEqual(swatches[name], k["tint-l"], name)           # the swatch shows the tint itself

    def test_the_tint_is_a_radio_group_stored_in_this_browser_and_applied_first(self):
        picker = JS[JS.index("function tintPicker(lab) {"): JS.index("function applyTheme(mode) {")]
        for needle in ("role: 'radiogroup'", "role: 'radio'", "'aria-checked': String(tintOn(id))", "ArrowRight: 1", "ArrowLeft: -1"):
            self.assertIn(needle, picker, needle)
        self.assertIn("store.set('tint', state.tint);", JS)
        self.assertIn("const tintOn = id => !LOOK.accent && id === state.tint;", JS)   # no swatch is chosen while an own colour is
        self.assertIn("readPalette();\n  bus.emit('theme');\n}", JS[JS.index("function applyTint(t) {"):])   # canvases follow the tint
        init = JS[JS.index("function init() {"):]
        self.assertLess(init.index("applyTint(store.get('tint') || 'blue');"), init.index("LG.init();"))
        bar = JS[JS.index("function homeBar(view) {"):]
        self.assertLess(bar.index("tintPicker({ 'aria-labelledby': 'w-tint-h' })"), bar.index("'Widgets'"))   # in the Customise menu, before the widgets


class LabelContrastTests(unittest.TestCase):
    def test_secondary_labels_keep_four_and_a_half_to_one(self):
        for name in ("ink", "ink-2", "muted"):
            for bg in (WHITE, GROUPED):
                self.assertGreaterEqual(ratio(over(tok(LIGHT, name), bg), bg), 4.5, ("light", name, bg))
            for where, blk in DARKS.items():
                for bg in (BLACK, DARK_1, DARK_2):
                    self.assertGreaterEqual(ratio(over(tok(blk, name), bg), bg), 4.5, (where, name, bg))

    def test_status_text_is_readable_on_its_own_tinted_fill(self):
        for kind in ("good", "warn", "crit"):
            for bg in (WHITE, GROUPED):
                fill = over(tok(LIGHT, kind + "-bg"), bg)
                self.assertGreaterEqual(ratio(rgb(tok(LIGHT, kind + "-ink"))[0], fill), 4.5, ("light", kind, bg))
            for where, blk in DARKS.items():
                for bg in (DARK_1, DARK_2):
                    fill = over(tok(blk, kind + "-bg"), bg)
                    self.assertGreaterEqual(ratio(rgb(tok(blk, kind + "-ink"))[0], fill), 4.5, (where, kind, bg))

    def test_light_and_dark_are_the_system_backgrounds(self):
        self.assertIn("--bg: #f2f2f7; --surface: #ffffff;", LIGHT)          # grouped background, as in Settings
        for where, blk in DARKS.items():
            self.assertIn("--bg: #000000; --surface: #1c1c1e;", blk, where)


class AppIconTests(unittest.TestCase):
    def test_every_app_has_its_colour_and_the_white_glyph_keeps_three_to_one(self):
        views = re.findall(r"id: '(\w+)'", re.search(r"const VIEWS = \[(.*?)\];", JS, re.S).group(1))
        colours = dict(re.findall(r'\.app-ico\[data-app="(\w+)"\] \{ --app: (#[0-9a-f]{6}); \}', CSS))
        self.assertEqual(sorted(colours), sorted(views))
        for app, colour in colours.items():
            self.assertGreaterEqual(ratio(rgb(colour)[0], WHITE), 3, app)
        self.assertEqual(JS.count("h('span', { class: 'app-ico', 'data-app': v.id, 'aria-hidden': 'true' }, tabIcon(v.id))"), 2)
        self.assertIn("@supports (corner-shape: squircle) { .app-ico { border-radius: 32%; corner-shape: squircle; } }", CSS)


class ControlTests(unittest.TestCase):
    def test_every_on_off_checkbox_is_a_switch_of_the_kit(self):
        boxes = re.findall(r"type: 'checkbox'(, role: 'switch')?", JS)
        self.assertGreaterEqual(len(boxes), 3)
        self.assertTrue(all(boxes), "a scripted checkbox without role: 'switch'")
        self.assertNotIn('type="checkbox"', HTML[HTML.index("</style>"):])   # none in the markup either
        sw = re.search(r'^input\[type="checkbox"\]\[role="switch"\] \{([^}]*)\}', CSS, re.M).group(1)
        self.assertIn("width: 64px; height: 28px;", sw)                     # the switch of iOS 27
        knob = re.search(r'input\[type="checkbox"\]\[role="switch"\]::before \{([^}]*)\}', CSS).group(1)
        self.assertIn("width: 38px; height: 24px;", knob)
        self.assertIn('input[type="checkbox"][role="switch"]:checked { background: var(--green); }', CSS)
        self.assertRegex(CSS, r'@media \(forced-colors: active\) \{[^\n]*input\[type="checkbox"\]\[role="switch"\] \{ -webkit-appearance: auto; appearance: auto;')
        self.assertIn("@media (prefers-contrast: more) {", CSS)             # on/off labels

    def test_sliders_fill_their_track_up_to_the_knob(self):
        self.assertIn("::-webkit-slider-runnable-track { height: 6px; border-radius: 3px; background: linear-gradient(90deg, var(--accent) 0 calc(19px + (100% - 38px) * var(--f)), var(--fill-1) 0); }", CSS)
        self.assertIn(":is(.hs-glass-range, .os-range)::-moz-range-progress", CSS)
        self.assertRegex(CSS, r"::-webkit-slider-thumb \{ -webkit-appearance: none; width: 38px; height: 24px;")
        self.assertIn("function rangeFill(el) {", JS)
        self.assertIn("rangeFill(range);", JS)                               # the see-through slider when it is made
        self.assertIn("r.disabled = flat; rangeFill(r);", JS)                # ... and when it is set from elsewhere
        self.assertIn("rangeFill(inp);", JS)                                 # the sliders of the Second brain
        self.assertIn("document.addEventListener('input', e => { if (e.target.matches && e.target.matches('.hs-glass-range, .os-range')) rangeFill(e.target); }, true);", JS)

    def test_radii_follow_the_kit(self):
        root = block(":root {\n  --lg-r: 28px;")
        for needle in ("--lg-r: 28px;", "--lg-r-menu: 34px;", "--lg-r-sheet: 38px;"):
            self.assertIn(needle, root, needle)
        self.assertIn("html:root body :is(.w-pop, .results) { border-radius: var(--lg-r-menu); }", CSS)
        self.assertIn("@media (max-width: 720px) { html:root body .detail { border-radius: var(--lg-r-sheet); } }", CSS)
        self.assertIn("html:root body .agx-box { border-radius: 32px; }", CSS)   # the form sheet

    def test_the_tab_bar_floats_and_stays_in_reach(self):
        self.assertIn("html:root body .tabs-wrap { position: sticky; top: 10px;", CSS)
        tabs = re.search(r"html:root body \.tabs \{([^}]*)\}", CSS).group(1)
        self.assertIn("backdrop-filter: blur(var(--lg-blur)) saturate(var(--lg-sat))", tabs)


class TypeTests(unittest.TestCase):
    def test_system_fonts_and_rounded_numerals(self):
        self.assertIn('--font: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text"', LIGHT)
        self.assertIn('--font-round: ui-rounded, "SF Pro Rounded"', LIGHT)
        self.assertNotIn("Geist", HTML)
        self.assertGreaterEqual(CSS.count("var(--font-round)"), 5)          # big figures: KPIs, clocks, health tiles

    def test_labels_are_sentence_case_and_mono_is_only_for_code_and_paths(self):
        self.assertNotIn("text-transform: uppercase", CSS)
        for m in re.finditer(r"([^{}\n]+)\{[^{}]*var\(--mono\)[^{}]*\}", CSS):
            sel = m.group(1)
            if sel.strip().startswith("--") or ":root" in sel:
                continue
            self.assertRegex(sel, r"path|code|pre|cli|mono|refs|cat|box", sel)


class GlassMaterialTests(unittest.TestCase):
    def test_the_default_stop_is_the_regular_glass_of_the_kit(self):
        stops = {k: [float(x) for x in v.split(",")] for k, v in re.findall(r"(\w+): \[([^\]]*)\]", re.search(r"const GLASS_STOPS = \{(.*?)\};", JS).group(1))}
        self.assertEqual(stops["blur"][1], 16)                               # frost
        self.assertEqual(stops["sat"][1], 1.8)
        self.assertEqual(stops["refr"][1], 0.7)                              # refraction
        self.assertEqual(stops["disp"][1], 0.2)                              # dispersion
        self.assertIn("refr: t.refr, disp: t.disp, rim: t.rim };", JS)       # the shader of the panes uses them

    def test_hairline_and_drop_of_the_kit(self):
        for where, blk in DARKS.items():
            self.assertIn("--lg-hair: rgba(166,166,166,.34); --lg-drop: rgba(0,0,0,.45);", blk, where)
        self.assertIn("--lg-hair: rgba(0,0,0,.09); --lg-drop: rgba(0,0,0,.16);", CSS)
        self.assertIn("--shadow-lg: 0 8px 48px rgba(0,0,0,.25);", LIGHT)     # 0 8 48 at .25 (light) ...
        for where, blk in DARKS.items():
            self.assertIn("--shadow-lg: 0 8px 48px rgba(0,0,0,.45);", blk, where)   # ... and .45 (dark)

    def test_page_cards_are_solid_and_the_lens_skips_what_is_flat(self):
        card = re.search(r"\n\.card \{([^}]*)\}", CSS).group(1)
        self.assertIn("background: var(--surface);", card)
        self.assertNotIn("backdrop-filter", card)
        self.assertRegex(CSS, r"html:root body:not\(\.is-page\) :is\(\.card, \.kpi")   # glass only over the stage
        self.assertIn("if ((cs.backdropFilter || cs.webkitBackdropFilter || 'none') === 'none') return;", JS)
        self.assertNotIn(".pill", re.search(r"const LG_LENS = \[(.*?)\];", JS).group(1))


class ProvenanceTests(unittest.TestCase):
    def test_values_not_assets(self):
        self.assertIn("no Apple asset, font or symbol is used", CSS)
        doc = (ROOT / "docs" / "design.md").read_text(encoding="utf-8")
        self.assertIn("iOS 27", doc)
        self.assertIn("No Apple asset", doc)


class LayoutRegressionTests(unittest.TestCase):
    """Found by looking at every view in a browser (desktop and a 390 px phone, light and dark): each is pinned here."""

    def test_an_empty_artifact_count_does_not_push_the_list_down(self):
        self.assertIn(".art-count:empty { margin-bottom: 0; }", CSS)

    def test_the_rings_hub_label_is_measured_against_its_hexagon(self):
        # The system font is wider than Geist was: "CLAUDE.md" ran out of the hexagon. It is measured and breaks into two lines.
        self.assertIn("ctx.measureText('CLAUDE.md').width <= room", JS)
        self.assertIn("ctx.fillText('CLAUDE', cx, cy - fs * 0.55); ctx.fillText('.md', cx, cy + fs * 0.6);", JS)

    def test_atlas_shows_one_pane_at_a_time_on_a_phone(self):
        # Stacked, the list took half the screen and the answers got a sliver: the conversation fills the screen, "Agents" leads to the list
        phone = re.search(r"@media \(max-width: 720px\) \{\n  /\* A phone shows one pane at a time.*?\n\}", CSS, re.S).group(0)
        self.assertIn(".atl:not(.atl-list-open) .atl-rail, .atl.atl-list-open .atl-chat { display: none; }", phone)
        self.assertIn(".atl-ch-main p, .atl-tags, .atl-note { display: none; }", phone)
        self.assertIn(".atl-ag .job-res { padding: 0; background: none; }", phone)
        self.assertIn(".atl-chips { flex-wrap: nowrap; overflow-x: auto;", phone)
        self.assertIn(".atl-new { grid-row: 1; grid-column: 3;", phone)
        self.assertIn(".atl-back, .atl-nc-s { display: none; }", CSS)   # wider screens keep both panes and the long label
        self.assertIn("v.showList(true)", JS)
        self.assertEqual(JS.count("v.showList(false);"), 2)   # picking an agent and opening a conversation lead back to it
        self.assertIn("if (!COARSE.matches) v.input.focus();", JS)   # no keyboard over the answers of an opened conversation

    def test_menus_are_a_bottom_sheet_on_a_phone(self):
        sheet = re.search(r"@media \(max-width: 720px\) \{\n  html:root body \.w-pop \{([^}]*)\}", CSS).group(1)
        for decl in ("position: fixed;", "left: 10px;", "right: 10px;", "top: auto;", "width: auto;", "border-radius: var(--lg-r-sheet);"):
            self.assertIn(decl, sheet)
        self.assertIn(".hs-head:has(.w-menu[open]) { z-index: 31; }", CSS)   # above the corner buttons (30)
        self.assertIn("body.is-home header.top {\n  position: fixed; z-index: 30;", CSS)

    def test_all_nine_tints_share_one_row(self):
        self.assertIn(".w-tints { display: grid; grid-template-columns: repeat(9, minmax(0, 28px));", CSS)
        self.assertEqual(len(TINT_IDS), 9)


class CheapFrameTests(unittest.TestCase):
    """The optimisation pass: same pixels, less work per frame and at load (measurements in docs/design.md)."""

    def test_the_aurora_steps_ten_times_a_second(self):
        self.assertIn("a.pause(); live.add(a);", JS)
        self.assertIn("id = setInterval(step, 100);", JS)
        self.assertIn("if (a.playState === 'idle') live.delete(a);", JS)
        self.assertIn("  LG.init();\n  driftAurora();\n", JS)
        self.assertIn("@media (prefers-reduced-motion: reduce) { .bg i { animation: none; } }", CSS)

    def test_the_glass_pass_reads_layout_before_the_frame_writes(self):
        loop = JS[JS.index("    glass.measure();"):]
        self.assertLess(loop.index("glass.measure();"), loop.index("moveBalls(dt);"))
        self.assertIn("rr = fresh ? G.rr : host.getBoundingClientRect()", JS)

    def test_the_atlas_orbit_turns_an_html_box(self):
        self.assertIn(".hs-atlas-sat { display: block; width: 28px; height: 28px; animation: hs-atlas-orbit 16s linear infinite; }", CSS)
        self.assertIn("h('span', { class: 'hs-atlas-sat' }, sat)", JS)
        self.assertRegex(CSS, r"prefers-reduced-motion: reduce\) \{ \.hs-atlas-sat[ ,{]")
        self.assertNotRegex(CSS, r"\.hs-atlas svg[^{]*\{[^}]*animation")


if __name__ == "__main__":
    unittest.main()
