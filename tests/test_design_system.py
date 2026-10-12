"""Design contract of dashboard.html: the liquid-glass panes are one language on every tab, everything that moves
respects "reduced motion", and the glass degrades (flat, reduced transparency, no backdrop-filter).
Static checks on the template (no browser needed). The lens maths and the engine are in test_liquid_glass.py."""

import re
import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
MARK = "Liquid glass: rounded panes that float over deep space."
MOTION = "@media (prefers-reduced-motion: no-preference) {"
# the glass block sits last in <style>; its keyframes are the g* ones and the lg* entrances
OWN_KEYFRAMES = ("lgRise", "lgIn", "lgInR", "gRow", "gStar", "gSweep", "gDue", "gRing")
ENTRANCES = ("lgRise", "lgIn", "lgInR", "side-in-l", "side-in-r")


def _glass_css() -> str:
    start = HTML.index(MARK)
    return HTML[start: HTML.index("</style>", start)]


def _script() -> str:
    return re.search(r"<script>\n(.*?)</script>", HTML, re.S).group(1)


def _keyframes(css: str, name: str) -> str:
    """The entrance keyframes are one-liners."""
    m = re.search(r"@keyframes " + re.escape(name) + r" \{[^\n]*", css)
    assert m, name + " not found"
    return m.group(0)


class GlassCssTests(unittest.TestCase):
    def test_nothing_moves_outside_the_no_preference_block(self):
        css = _glass_css()
        self.assertEqual(css.count(MOTION), 1)
        calm, moving = css[: css.index(MOTION)], css[css.index(MOTION):]
        self.assertNotIn("@keyframes", calm)
        self.assertNotRegex(calm, r"animation\s*:")      # hover colours and rails are transitions, never animations
        self.assertNotRegex(calm, r"animation-name\s*:")
        for name in OWN_KEYFRAMES + ("side-in-l", "side-in-r"):
            self.assertIn("@keyframes " + name, moving)

    def test_every_keyframe_is_used(self):
        css = _glass_css()
        for name in OWN_KEYFRAMES:
            uses = re.findall(r"animation(?:-name)?\s*:[^;}]*\b" + name + r"\b", css)
            self.assertTrue(uses, name + " is declared but never used")

    def test_entrances_never_blur(self):
        # a filter (or opacity < 1 for long) makes the element its own backdrop root: the glass inside it
        # would see only itself while it enters. The entrances are opacity + transform and nothing else.
        css = _glass_css()
        for name in ENTRANCES:
            self.assertNotIn("filter", _keyframes(css, name), name)

    def test_widget_colour_is_a_token_not_a_literal(self):
        css = _glass_css()
        decls = re.findall(r"--wc\s*:\s*([^;}]+)", css)
        self.assertGreaterEqual(len(decls), 6)
        for decl in decls:
            self.assertRegex(decl.strip(), r"^var\(--(accent|cyan|violet|pink)\)$")

    def test_primary_button_stays_readable(self):
        css = _glass_css()
        m = re.search(r"html:root body :is\(\.btn\.primary, \.os-btn\.solid\) \{([^}]*)\}", css)
        self.assertTrue(m, "primary button rule missing")
        self.assertIn("color: var(--on-accent)", m.group(1))
        self.assertIn("var(--accent)", m.group(1))
        # ... also inside a pane, where the flat inset rule would otherwise grey it out
        self.assertRegex(css, r"\.btn\.primary, \.os-btn\.solid, \.chip\[aria-pressed=\"true\"\][^{]*\{[^}]*color: var\(--on-accent\)")

    def test_panes_and_controls_share_one_surface_recipe(self):
        css = _glass_css()
        pane = re.search(r"html:root body :is\(\.card, \.kpi, \.deadline, \.ag-card, \.hero\) \{([^}]*)\}", css)
        self.assertTrue(pane)
        ctl = re.search(r"html:root body :is\(\.btn, \.icon-btn, \.os-ibtn, \.os-btn, \.hs-atlas, \.chip, \.pill, \.search input, \.os-seg\) \{([^}]*)\}", css)
        self.assertTrue(ctl)
        for body in (pane.group(1), ctl.group(1)):
            # the lens is an optional first layer of the backdrop; without it the same line is a plain frost
            self.assertIn("backdrop-filter: var(--lg-f, blur(0px))", body)
            self.assertIn("saturate(var(--lg-sat))", body)
            self.assertIn("var(--lg-rim)", body)             # the lit edge
            self.assertIn("var(--lg-a", body)                # transparency comes from the token
        self.assertIn("border-radius: var(--lg-r)", pane.group(1))
        self.assertIn("border-radius: 999px", ctl.group(1))

    def test_stage_cards_chips_and_popups_are_covered(self):
        css = _glass_css()
        for sel in (".stage", ".chip", ".results", ".w-pop", ".hs-card", ".os-controls", ".os-legendbox", ".atl-rail", ".atl-chat", ".agx-box", ".tab-ind"):
            self.assertIn(sel, css, sel)

    def test_nested_glass_is_flat(self):
        # a control inside a pane would only ever see the pane: it is drawn as a flat inset instead of a second blur
        css = _glass_css()
        m = re.search(r"\.atl-rail, \.atl-chat[^{]*\{[^}]*-webkit-backdrop-filter: none; backdrop-filter: none;", css)
        self.assertTrue(m, "controls inside panes keep their own backdrop-filter")

    def test_every_new_rule_beats_the_old_page_rules(self):
        # specificity strategy: "html:root body" in front (0,2,2) is stronger than body.is-home .card (0,2,1) and the like
        css = _glass_css()
        calm = css[: css.index(MOTION)]
        for rule in re.findall(r"^(html:root body[^{\n]*)\{", calm, re.M):
            self.assertTrue(rule.startswith("html:root body"))
        self.assertGreater(len(re.findall(r"^html:root body", calm, re.M)), 50)


class GlassFallbackTests(unittest.TestCase):
    def test_the_three_steps_exist_in_css(self):
        css = _glass_css()
        self.assertIn('html[data-glass="flat"]', css)
        self.assertRegex(css, r'html\[data-glass="flat"\] \*[^{]*\{ -webkit-backdrop-filter: none !important; backdrop-filter: none !important; \}')

    def test_reduced_transparency_and_missing_backdrop_filter_are_handled(self):
        css = _glass_css()
        rt = css[css.index("@media (prefers-reduced-transparency: reduce)"):]
        rt = rt[: rt.index("\n}") + 2]
        self.assertIn("--lg-a: 94%", rt)
        self.assertIn("backdrop-filter: none !important", rt)
        # a stored choice wins over the media query: the rule only applies while html has no data-glass
        self.assertIn("html:not([data-glass])", rt)
        self.assertIn("@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))", css)

    def test_tokens_exist_for_light_and_the_three_dark_places(self):
        css = _glass_css()
        for tok in ("--lg-r:", "--lg-r-m:", "--lg-r-s:", "--lg-gap:", "--lg-blur:", "--lg-sat:", "--lg-a:", "--lg-a-pop:", "--lg-a-ctl:", "--lg-rim:", "--lg-sheen:"):
            self.assertIn(tok, css, tok)
        # dark: explicit theme, system dark, and the OS stage (home, brain, atlas stay dark in every theme)
        self.assertEqual(HTML.count("--lg-a: 34%; --lg-a-pop: 64%; --lg-a-ctl: 26%;"), 2)   # explicit dark, system dark
        # the stage itself (deep space) is more see-through than the dark theme: stars and nebula show through the panes
        self.assertEqual(HTML.count("--lg-a: 22%; --lg-a-pop: 62%; --lg-a-ctl: 20%;"), 1)
        self.assertIn("--lg-blur: 11px; --lg-sat: 1.9;", HTML)

    def test_popups_are_denser_and_never_use_the_lens(self):
        # text on a popup must not depend on what happens to be behind it: denser tint token, plain blur, no lens layer
        css = _glass_css()
        m = re.search(r"html:root body :is\(\.detail, \.results, \.w-pop, \.hs-card[^)]*\) \{([^}]*)\}", css)
        self.assertTrue(m, "popup rule missing")
        self.assertIn("var(--lg-a-pop)", m.group(1))
        self.assertNotIn("--lg-f", m.group(1))
        # the ones that open inside another pane are opaque: their backdrop would only be that pane, showing through
        m = re.search(r"html:root body :is\(\.mp-pop, \.atl-recent-pop, \.agx-box\) \{([^}]*)\}", css)
        self.assertTrue(m)
        self.assertRegex(m.group(1), r"rgba\(255,255,255,0\) 50%\), var\(--surface\);")


class TabWiringTests(unittest.TestCase):
    def test_page_class_covers_exactly_the_non_os_tabs(self):
        js = _script()
        self.assertIn("classList.toggle('is-page', id !== 'today' && id !== 'os' && id !== 'agents')", js)
        ids = re.findall(r"\{ id: '(\w+)', label: '[^']+' \}", js[js.index("const VIEWS = ["): js.index("// Areas (top-level folder)")])
        self.assertEqual(set(ids) - {"today", "os", "agents"}, {"skills", "artifacts", "rings", "links", "timeline", "health"})

    def test_health_view_markup(self):
        js = _script()
        view = js[js.index("const HealthView = {"): js.index("12b. View: Brain-OS")]
        for needle in ("h-tile", "'tbl issues sev-' + k", "h-clean"):
            self.assertIn(needle, view)
        for bad in (".innerHTML", "insertAdjacentHTML", "eval("):
            self.assertNotIn(bad, view)
        # the counts still say what they count, singular and plural
        self.assertIn("'error' : 'errors'", view)
        self.assertIn("'warning' : 'warnings'", view)

    def test_view_switch_refreshes_the_lenses(self):
        js = _script()
        self.assertRegex(js, r"moveInd\(\);\s*LG\.refresh\(0\);")


if __name__ == "__main__":
    unittest.main()
