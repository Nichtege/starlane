"""Model/effort picker (modelled on Claude Desktop) and home page ball animations: wiring in the dashboard (static)."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTML = (ROOT / "aos" / "web" / "dashboard.html").read_text(encoding="utf-8")
JS = re.search(r"<script>\n(.*?)</script>", HTML, re.S).group(1)


def _picker() -> str:
    return JS[JS.index("function modelEffortPicker(o)"): JS.index("function pickerChoices()")]


class ModelEffortPickerTests(unittest.TestCase):
    def test_matrix_is_gone_and_both_places_use_the_picker(self):
        self.assertNotIn("modelMatrix", JS)
        self.assertNotIn(".mx-grid", HTML)
        skill_card = JS[JS.index("function skillCard("): JS.index("function skillOut(")]
        deck = JS[JS.index("function skillsDeck()"): JS.index("const VIEW_MODS")]
        self.assertIn("modelEffortPicker({", skill_card)
        self.assertNotIn("class: 'select'", skill_card)          # no more two select lists
        self.assertIn("picker.setDisabled(running)", skill_card)  # locked while running
        self.assertIn("modelEffortPicker({ inline: true", deck)

    def test_picker_is_accessible_and_keyboard_operable(self):
        src = _picker()
        for needle in ("role: 'radiogroup'", "role: 'radio'", "type: 'range'", "'aria-haspopup': 'dialog'", "'aria-expanded'",
                       "aria-valuetext", "e.key === 'Escape'", "'ArrowDown'", "pointerdown"):
            self.assertIn(needle, src)
        for bad in (".innerHTML", "insertAdjacentHTML", "eval("):
            self.assertNotIn(bad, src)

    def test_effort_ladder_starts_with_auto_and_uses_server_options(self):
        src = _picker()
        self.assertIn("levels = [''].concat(o.efforts || [])", src)   # "Auto" = the skill's default, leftmost
        self.assertIn("modelEffortPicker({ models, efforts: G.options.efforts", JS)
        for lvl in ("low", "medium", "high", "xhigh", "max"):
            self.assertRegex(JS, r"EFFORT_NAME = \{[^}]*\b" + lvl + r":")

    def test_styles_have_slider_notches_and_reduced_motion(self):
        for sel in (".mp-btn", ".mp-pop", ".mp-opt", ".mp-range::-webkit-slider-thumb", ".mp-tick.on", ".mp-fill"):
            self.assertIn(sel, HTML)
        self.assertRegex(HTML, r"prefers-reduced-motion: reduce\) \{ \.mp-pop")


class BallAnimationTests(unittest.TestCase):
    def test_ball_motion_has_idle_float_and_pointer_pull_but_no_click_animation(self):
        stage = JS[JS.index("function createHomeStage("): JS.index("// --- Home page widgets")]
        self.assertIn("const idle = RM.matches || !dt ? 0", stage)       # floating, off with "reduced motion"
        self.assertIn("S.ptr = { x: e.clientX - r.left", stage)          # pointer for the magnetic pull
        self.assertIn("pullX", stage)
        for gone in ("function ping(", "flipCard", "@keyframes ball-ping", ".ball:active { scale"):
            self.assertNotIn(gone, stage + HTML if gone.startswith(("@", ".")) else stage)
        self.assertNotIn("animation: hs-pop", HTML)


if __name__ == "__main__":
    unittest.main()
