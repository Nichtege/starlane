import re
import unittest
from pathlib import Path

from aos.dashboard import render_html
from aos.server import make_handler  # noqa: F401  (CSP lives in server.py)

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "aos" / "web" / "dashboard.html"


def _tpl() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _script(tpl: str) -> str:
    return re.search(r"<script>\n(.*?)</script>", tpl, re.S).group(1)


class FrontendTests(unittest.TestCase):
    def test_system_fonts_only(self):
        # the system font of each platform (SF Pro on Apple devices), nothing downloaded or embedded, so the CSP needs no font-src
        html = render_html({"nodes": []})
        self.assertNotIn("@font-face", html)
        self.assertNotIn("woff2", html)
        self.assertFalse((ROOT / "aos" / "web" / "fonts").exists())
        self.assertNotIn("font-src", (ROOT / "aos" / "server.py").read_text(encoding="utf-8"))
        self.assertRegex(_tpl(), r"--font: system-ui, -apple-system, BlinkMacSystemFont,")

    def test_template_has_no_external_urls(self):
        tpl = _tpl()
        for needle in ("https://", "http://", "//cdn"):
            self.assertNotIn(needle, tpl.replace("http://www.w3.org/2000/svg", ""))

    def test_placeholders_present_exactly_once(self):
        tpl = _tpl()
        self.assertEqual(tpl.count("__AOS_DATA__"), 1)
        self.assertNotIn("__AOS_FONTS__", tpl)

    def test_new_views_are_wired(self):
        js = _script(_tpl())
        views = re.search(r"const VIEWS = \[(.*?)\];", js, re.S).group(1)
        mods = re.search(r"const VIEW_MODS = \{(.*?)\};", js, re.S).group(1)
        icons = re.search(r"const TAB_ICONS = \{(.*?)\n\};", js, re.S).group(1)
        for vid in ("today", "agents", "skills", "artifacts"):
            self.assertIn(f"id: '{vid}'", views)
            self.assertRegex(mods, rf"\b{vid}:")
            self.assertRegex(icons, rf"\b{vid}:")

    def test_no_inline_event_handlers_or_html_injection(self):
        tpl = _tpl()
        # CSP only allows scripts with a nonce: no on*="..." attributes in markup or strings
        self.assertIsNone(re.search(r"""\son[a-z]+\s*=\s*["']""", tpl))
        js = _script(tpl)
        for bad in (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write(", "eval(", "new Function("):
            self.assertNotIn(bad, js)

    def test_iframes_are_fully_sandboxed(self):
        js = _script(_tpl())
        calls = re.findall(r"h\('iframe',\s*\{([^}]*)\}", js)
        self.assertTrue(calls, "artifact preview uses an iframe")
        for props in calls:
            self.assertIn("sandbox: ''", props)  # empty sandbox = no scripts, opaque origin
            self.assertIn("srcdoc: safeSrcdoc(", props)
        self.assertNotIn("allow-scripts", js)
        self.assertNotIn("allow-same-origin", js)

    def test_srcdoc_strips_meta_refresh(self):
        js = _script(_tpl())
        body = re.search(r"function safeSrcdoc\(html\) \{(.*?)\n\}", js, re.S).group(1)
        self.assertIn("http-equiv", body)
        self.assertIn("refresh", body)
        self.assertIn("/gi", body)  # case-insensitive
        # same rules rebuilt in Python: the redirect must disappear
        rx = [(m.group(1), m.group(2)) for m in re.finditer(r"\.replace\(/(.+?)/gi, '([^']*)'\)", body)]
        self.assertEqual(len(rx), 2)
        sample = '<META HTTP-EQUIV="Refresh" content="0;url=x"><meta content="a>b" http-equiv=refresh><p>ok</p>'
        out = sample
        for pat, rep in rx:
            out = re.sub(pat, rep, out, flags=re.I)
        self.assertNotRegex(out.lower(), r"http-equiv")
        self.assertIn("<p>ok</p>", out)

    def test_api_paths_used_exist_in_contract(self):
        js = _script(_tpl())
        server = (ROOT / "aos" / "server.py").read_text(encoding="utf-8")
        used = set(re.findall(r"G\.api\.([a-z]+)", js)) - {"token"}
        self.assertTrue({"skills", "artifact", "jobs"} <= used)
        for key in used:
            self.assertIn(f'"{key}":', server, f"G.api.{key} missing from the server contract")
        self.assertIn('"/api/skills/"', server)
        self.assertIn('"/api/artifact/"', server)

    def test_layout_prefs_only_via_guarded_store(self):
        js = _script(_tpl())
        # localStorage only inside the store helper (with try/catch), never directly
        self.assertEqual(len(re.findall(r"localStorage\.", js)), 2)
        self.assertIn("store.set('widgets'", js)
        self.assertIn("store.set('clocks'", js)

    def test_render_escapes_untrusted_titles(self):
        evil = "</script><img src=x onerror=alert(1)>"
        html = render_html({"nodes": [], "skills": [{"id": "x", "name": evil}], "artifacts": [{"id": "f-000000000000", "title": evil, "kind": "html"}]})
        self.assertNotIn(evil, html)


if __name__ == "__main__":
    unittest.main()
