"""The language layer (aos/i18n.py) and the shipped locales.

Every text a person reads is marked in the code: tr / trc / trn / tr_mark in Python, tr / trc / trn / trm and
{{t:...}} in the dashboard. These tests collect every marked text straight from the source and hold each locale to it:
nothing missing, nothing stale, the same placeholders, commands and code spans unchanged.
"""

from __future__ import annotations

import ast
import contextlib
import html as _html
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from aos import cli, i18n
from aos.config import PROJECT_ROOT, load_config, peek_ui_language
from aos.dashboard import build_data, render_html
from tests.helpers import JS_I18N, TempVaultCase

AOS = PROJECT_ROOT / "aos"
DASHBOARD = AOS / "web" / "dashboard.html"
PY_FUNCS = {"tr", "trc", "trn", "tr_mark"}


# --- collecting the marked texts --------------------------------------------------------------
def _const(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def python_keys() -> tuple[dict[str, str], list[str]]:
    """{key: "file:line"} of every literal text marked in aos/*.py, plus problems (f-strings, non-literal marks)."""
    keys: dict[str, str] = {}
    problems: list[str] = []
    for path in sorted(AOS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in PY_FUNCS):
                continue
            fn, args, where = node.func.id, node.args, f"{path.name}:{node.lineno}"
            if any(isinstance(a, ast.JoinedStr) for a in args):
                problems.append(f"{where}: f-string passed to {fn}() (use placeholders)")
            texts: list[str | None] = []
            if fn == "tr" and args:
                texts = [_const(args[0])]
            elif fn == "trn" and len(args) >= 3:
                texts = [_const(args[1]), _const(args[2])]
            elif fn == "trc" and len(args) >= 2:
                ctx, msg = _const(args[0]), _const(args[1])
                texts = [f"@{ctx} {msg}" if ctx and msg is not None else None]
            elif fn == "tr_mark" and args:
                ctx = _const(args[1]) if len(args) > 1 else next((_const(k.value) for k in node.keywords if k.arg == "context"), "")
                msg = _const(args[0])
                if msg is None:
                    problems.append(f"{where}: tr_mark() needs a literal")
                texts = [(f"@{ctx} {msg}" if ctx else msg) if msg is not None else None]
            for t in texts:
                if t is not None:
                    keys.setdefault(t, where)
    return keys, problems


_JS_STR = r"""'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*\""""
_JS_CALL = re.compile(r"(?<![\w$.])(tr|trn|trc|trm)\(\s*(" + _JS_STR + r"|(?:[^,()]|\((?:[^()]|\([^()]*\))*\))+?)\s*(?=[,)])(?:,\s*(" + _JS_STR + r"))?\s*(?:,\s*(" + _JS_STR + r"))?")
_HTML_MARK = re.compile(r"\{\{t:(.+?)\}\}")


def _js_unquote(lit: str) -> str:
    """A JS string literal -> its value (the escapes the dashboard uses: \\' \\" \\\\ \\n \\t \\uXXXX \\xXX)."""
    return re.sub(r"\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|.)", lambda m: (
        chr(int(m.group(1)[1:], 16)) if m.group(1)[0] in "ux" and len(m.group(1)) > 1
        else {"n": "\n", "t": "\t", "r": "\r"}.get(m.group(1), m.group(1))), lit[1:-1])


def _is_lit(s: str | None) -> bool:
    return bool(s) and len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]


def web_keys() -> tuple[dict[str, str], list[str]]:
    """{key: "dashboard.html:line"} of every text marked in the dashboard (script and static HTML), plus problems."""
    text = DASHBOARD.read_text(encoding="utf-8")
    keys: dict[str, str] = {}
    problems: list[str] = []

    def add(key: str, pos: int) -> None:
        keys.setdefault(key, f"dashboard.html:{text.count(chr(10), 0, pos) + 1}")

    for m in _JS_CALL.finditer(text):
        fn, a, b, c = m.group(1), m.group(2), m.group(3), m.group(4)
        if fn in ("tr", "trm"):
            if _is_lit(a):
                add(_js_unquote(a), m.start())
            elif fn == "trm":
                problems.append(f"dashboard.html:{text.count(chr(10), 0, m.start()) + 1}: trm() needs a literal")
        elif fn == "trn":
            if _is_lit(b) and _is_lit(c):
                add(_js_unquote(b), m.start())
                add(_js_unquote(c), m.start())
            else:
                problems.append(f"dashboard.html:{text.count(chr(10), 0, m.start()) + 1}: trn() needs two literal forms")
        elif fn == "trc" and _is_lit(a) and _is_lit(b):
            add(f"@{_js_unquote(a)} {_js_unquote(b)}", m.start())
    for m in _HTML_MARK.finditer(text):
        add(_html.unescape(m.group(1)), m.start())
    return keys, problems


# --- checks a translation must pass ----------------------------------------------------------------
_CODE = re.compile(r"`[^`\n]+`")
_PERCENT = re.compile(r"%\(\w+\)[sdr]|%[sdr]")
DATE_PARTS = {"wd", "d", "m", "mon", "y"}  # dates.date_parts (the dashboard's dateParts gives the same)


def translation_problems(key: str, value) -> list[str]:
    source = key.split(" ", 1)[1] if key.startswith("@") else key
    if not isinstance(value, str) or not value.strip():
        return ["empty translation"]
    out = []
    if key.startswith("@date "):  # a date pattern may pick any of the parts (German writes the month as a number)
        if not i18n.placeholders(value) or not i18n.placeholders(value) <= DATE_PARTS:
            out.append(f"date pattern may only use {sorted(DATE_PARTS)}")
    elif i18n.placeholders(source) != i18n.placeholders(value):
        out.append(f"placeholders differ: {sorted(i18n.placeholders(source))} vs {sorted(i18n.placeholders(value))}")
    if sorted(_PERCENT.findall(source)) != sorted(_PERCENT.findall(value)):
        out.append("%-placeholders differ")
    # commands and code stay verbatim; only a quoted argument inside them (an example question) may be translated
    unquote = lambda s: re.sub(r'"[^"`]*"', '""', s)  # noqa: E731
    shown = {unquote(s) for s in _CODE.findall(value)}
    for span in _CODE.findall(source):
        if unquote(span) not in shown:
            out.append(f"code span {span} changed or missing")
    if source.endswith("\n") != value.endswith("\n"):
        out.append("trailing line break differs")
    return out


class CatalogTests(unittest.TestCase):
    def test_no_dynamic_texts(self):
        self.assertEqual(python_keys()[1], [])
        self.assertEqual(web_keys()[1], [])

    def test_every_locale_is_complete_and_has_nothing_stale(self):
        py, web = python_keys()[0], web_keys()[0]
        for lang in i18n.available()[1:]:
            cat = i18n.catalog(lang)
            for part, keys in (("py", py), ("web", web)):
                with self.subTest(lang=lang, part=part):
                    self.assertEqual(sorted(k for k in keys if k not in cat[part]), [], "missing")
                    self.assertEqual(sorted(k for k in cat[part] if k not in keys), [], "stale")

    def test_translations_keep_placeholders_and_code(self):
        for lang in i18n.available()[1:]:
            cat = i18n.catalog(lang)
            for part in ("py", "web"):
                for key, value in cat[part].items():
                    with self.subTest(lang=lang, part=part, key=key[:60]):
                        self.assertEqual(translation_problems(key, value), [])

    def test_locale_files_are_well_formed(self):
        for path in sorted((AOS / "locales").glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["lang"], path.stem)
            for key in ("name", "locale", "reply_language"):
                self.assertTrue(isinstance(data.get(key), str) and data[key], key)
            self.assertEqual(set(data) - {"lang", "name", "locale", "reply_language", "py", "web"}, set())


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(i18n.use, i18n.SOURCE)

    def test_english_is_the_identity(self):
        i18n.use("en")
        self.assertEqual(i18n.tr("Vault check: {errors} errors", errors=2), "Vault check: 2 errors")
        self.assertEqual(i18n.trn(1, "{n} agent", "{n} agents"), "1 agent")
        self.assertEqual(i18n.trn(3, "{n} agent", "{n} agents"), "3 agents")
        self.assertEqual(i18n.trc("routine", "due"), "due")
        self.assertEqual(i18n.tr_mark("Monday"), "Monday")

    def test_german(self):
        i18n.use("de")
        self.assertEqual(i18n.tr("today"), "heute")
        self.assertEqual(i18n.trc("routine", "failed"), "fehlgeschlagen")
        self.assertEqual(i18n.trn(2, "{n} agent", "{n} agents"), "2 Agenten")
        self.assertEqual(i18n.trn(1, "{n} agent", "{n} agents"), "1 Agent")

    def test_unknown_text_and_placeholders_fall_back(self):
        i18n.use("de")
        self.assertEqual(i18n.tr("Not in any catalog {x}", x=1), "Not in any catalog 1")
        self.assertEqual(i18n.fill("{a} and {b}", {"a": 1}), "1 and {b}")  # an unknown name never raises

    def test_normalize(self):
        for code in ("de", "DE", "de-DE", "de_AT", " de "):
            self.assertEqual(i18n.normalize(code), "de")
        self.assertEqual(i18n.normalize("en-GB"), "en")
        with self.assertRaisesRegex(ValueError, "ui_language must be one of"):
            i18n.normalize("xx")

    def test_web_catalog(self):
        cat = i18n.web_catalog("de")
        self.assertEqual((cat["lang"], cat["locale"]), ("de", "de-DE"))
        self.assertEqual(i18n.web_catalog("en"), {"lang": "en", "locale": "en-US", "strings": {}})

    def test_reply_language(self):
        self.assertEqual(i18n.reply_language("de"), "Deutsch")
        self.assertEqual(i18n.reply_language("en"), "English")


class ExtractorTests(unittest.TestCase):
    def test_js_unquote(self):
        self.assertEqual(_js_unquote(r"'it\'s'"), "it's")
        self.assertEqual(_js_unquote(r'"a \"b\" \\ \n ä"'), 'a "b" \\ \n ä')

    def test_js_calls_are_found(self):
        sample = "x = tr('Hello {name}', { name }); y = trn(n, 'one', 'many'); z = trc('ctx', 'Word'); a.tr('no'); trm('Mark')"
        found = {m.group(1) + ":" + str(m.group(2)) for m in _JS_CALL.finditer(sample)}
        self.assertEqual(found, {"tr:'Hello {name}'", "trn:n", "trc:'ctx'", "trm:'Mark'"})

    def test_translation_checks(self):
        self.assertEqual(translation_problems("Run `aos doctor` for {n}", "Starte `aos doctor` für {n}"), [])
        self.assertTrue(translation_problems("Run `aos doctor`", "Starte `aos arzt`"))
        self.assertTrue(translation_problems("{n} items", "{count} Einträge"))
        self.assertTrue(translation_problems("usage: %s", "Aufruf:"))


class GermanEndToEndTests(TempVaultCase):
    """A German install end to end: terminal, generated notes and the dashboard page, all from `[user] ui_language`."""

    def setUp(self):
        env = mock.patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        for name in ("AOS_UI_LANGUAGE", "AOS_LANGUAGE"):
            os.environ.pop(name, None)
        super().setUp()
        self.addCleanup(i18n.use, i18n.SOURCE)
        self.cfg_path.write_text(self.cfg_path.read_text(encoding="utf-8") + '[user]\nui_language = "de"\n', encoding="utf-8")
        self.cfg = load_config(self.cfg_path)
        self.de = i18n.catalog("de")["py"]

    def run_cli(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            try:
                code = cli.main(["--config", str(self.cfg_path), *args])
            except SystemExit as e:  # argparse --help
                code = e.code
        return code, out.getvalue()

    def test_config(self):
        self.assertEqual(self.cfg.ui_language, "de")
        self.assertEqual(self.cfg.language, "Deutsch")  # agents reply in the interface language unless [user] language says otherwise
        self.assertEqual(peek_ui_language(self.cfg_path), "de")
        os.environ["AOS_UI_LANGUAGE"] = "en"  # the shell wins over the file
        self.assertEqual(load_config(self.cfg_path).ui_language, "en")
        self.assertEqual(peek_ui_language(self.cfg_path), "en")

    def test_unknown_language_is_refused(self):
        self.cfg_path.write_text(self.cfg_path.read_text(encoding="utf-8").replace('"de"', '"xx"'), encoding="utf-8")
        with self.assertRaisesRegex(Exception, "ui_language"):
            load_config(self.cfg_path)

    def test_help_and_doctor_are_german(self):
        code, out = self.run_cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("Aufruf:", out)
        self.assertNotIn("usage:", out)
        _, out = self.run_cli("doctor")
        self.assertIn(self.de["Vault exists"], out)

    def test_skill_list_is_german(self):
        folder = self.root / "skills" / "plan"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text("---\nname: Plan\ndescription: Plant die Woche\n---\n# Plan\n", encoding="utf-8")
        code, out = self.run_cli("skills")
        self.assertEqual(code, 0, out)
        line = next(ln for ln in out.splitlines() if ln.lstrip().startswith("plan "))
        self.assertIn("sonnet/Standard", line)  # no effort set: the default, in German
        self.assertIn("Projekt", line)
        self.assertNotIn("project", line)

    def test_digest_and_vault_check_are_german(self):
        code, out = self.run_cli("digest")
        self.assertEqual(code, 0, out)
        digest = (self.vault_dir / "AI" / "Digest" / "latest.md").read_text(encoding="utf-8")
        for heading in ("Deadlines", "Needs you", "Vault health"):
            self.assertIn("## " + self.de[heading], digest)
            self.assertNotIn("## " + heading + "\n", digest)
        check = (self.vault_dir / "AI" / "Digest" / "vault-check.md").read_text(encoding="utf-8")
        self.assertIn("# " + self.de["Vault check"], check)

    def test_dashboard_page(self):
        data = build_data(self.cfg)
        for lang, skip in (("de", "Zum Inhalt springen"), ("en", "Skip to content")):
            with self.subTest(lang=lang):
                page = render_html(data, lang=lang)
                self.assertIn(f'<html lang="{lang}">', page)
                self.assertIn(skip, page)
                self.assertNotIn("{{t:", page)
                self.assertNotIn("__AOS_I18N__", page)
                island = re.search(r'<script id="aos-i18n" type="application/json">(.*?)</script>', page, re.S).group(1)
                self.assertEqual(json.loads(island), i18n.web_catalog(lang))


@unittest.skipUnless(shutil.which("node"), "Node not installed")
class DashboardRuntimeTests(unittest.TestCase):
    """The dashboard's tr / trc / trn / trm, run as they ship (cut from the page) against the German catalog."""

    def run_js(self, island, body: str):
        src = (f"const ISLAND = {json.dumps(island)};\n"
               "const document = { getElementById: id => (id === 'aos-i18n' && ISLAND !== null ? { textContent: ISLAND } : null) };\n"
               + JS_I18N + "const fmtNum = n => Number(n || 0).toLocaleString(LOCALE);\n"
               + f"console.log(JSON.stringify({body}));\n")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "t.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run(["node", str(f)], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    PROBE = ("{ lang: I18N.lang, locale: LOCALE, today: tr('today'), failed: trc('routine', 'failed'), one: trn(1, '{n} agent', '{n} agents'),"
             " many: trn(1234, '{n} agent', '{n} agents'), name: tr('Remove {name}', { name: 'X' }), gap: tr('Page {n} of {total}', { n: 1 }),"
             " unknown: tr('Not in any catalog {x}', { x: 2 }), mark: trm('Archive'), shown: tr(trm('Archive')) }")

    def test_german(self):
        got = self.run_js(json.dumps(i18n.web_catalog("de")), self.PROBE)
        self.assertEqual(got, {"lang": "de", "locale": "de-DE", "today": "heute", "failed": "fehlgeschlagen", "one": "1 Agent",
                               "many": "1.234 Agenten", "name": "X entfernen", "gap": "Seite 1 von {total}",
                               "unknown": "Not in any catalog 2", "mark": "Archive", "shown": "Archiv"})

    def test_without_a_catalog_the_page_stays_english(self):
        for island in (None, "{broken", '{"lang": "de", "strings": "not an object"}', json.dumps(i18n.web_catalog("en"))):
            with self.subTest(island=island):
                got = self.run_js(island, self.PROBE)
                self.assertEqual((got["lang"], got["locale"], got["today"], got["many"], got["shown"]),
                                 ("en", "en-US", "today", "1,234 agents", "Archive"))


DOCS = PROJECT_ROOT / "docs"
GUIDES = ("README.md", "getting-started.md", "vault-conventions.md", "agents.md", "skills.md", "security.md", "vps-setup.md",
          "languages.md", "notion.md")  # architecture.md and design.md are for developers and stay English
_LINK = re.compile(r"\]\(([^)\s]+)\)")


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lower case, punctuation dropped (letters like ä stay), spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.S)
    return {_slug(m.group(1)) for m in re.finditer(r"^#{1,6} (.+)$", text, re.M)}


class DocsTests(unittest.TestCase):
    """The German guides: complete, linked right, and saying what the German onboarding prompts say they say."""

    def test_every_guide_has_a_german_copy(self):
        for name in GUIDES:
            english = PROJECT_ROOT / name if name == "README.md" else DOCS / name
            with self.subTest(guide=name):
                self.assertTrue(english.is_file())
                self.assertTrue((DOCS / "de" / name).is_file())

    def test_files_and_sections_the_german_texts_point_to_exist(self):
        sections = 0
        for key, text in i18n.catalog("de")["py"].items():
            for name in re.findall(r"docs/de/([\w.-]+\.md)", text):
                self.assertTrue((DOCS / "de" / name).is_file(), f"{name} in: {key[:60]}")
            # '"X" in docs/de/y.md' and 'docs/de/y.md (besonders "X" und "Z")': X and Z are headings of y.md
            refs = re.findall(r'"([^"\n]+)" in docs/de/([\w.-]+\.md)', text)
            for name, inner in re.findall(r"docs/de/([\w.-]+\.md) \(besonders ([^)\n]*)\)", text):
                refs += [(quoted, name) for quoted in re.findall(r'"([^"]+)"', inner)]
            for quoted, name in refs:  # a heading may add a detail: "Dashboard-Server" -> "## Dashboard-Server (`aos serve`)"
                sections += 1
                want = _slug(quoted)
                self.assertTrue(any(h == want or h.startswith(want + "-") for h in _anchors(DOCS / "de" / name)),
                                f'heading "{quoted}" not in docs/de/{name}')
        self.assertGreaterEqual(sections, 6)  # Dashboard-Server, Routinen, Einen Skill planen, two in agents.md, one in skills.md

    def test_german_getting_started_shows_what_aos_next_prints(self):
        from aos import onboarding as O
        doc = (DOCS / "de" / "getting-started.md").read_text(encoding="utf-8")
        self.addCleanup(i18n.use, i18n.SOURCE)
        with mock.patch.dict(os.environ, {"AOS_UI_LANGUAGE": "de"}):
            for name in ("AOS_USER", "AOS_LANGUAGE"):
                os.environ.pop(name, None)
            cfg = load_config(PROJECT_ROOT / "does-not-exist.toml")
        i18n.use(cfg.ui_language)
        for s in O.STAGES:
            title, why, steps = O.text(s)
            with self.subTest(stage=s.id):
                self.assertIn(title, doc)
                self.assertIn(why, doc)
                for step in steps:
                    self.assertIn(step, doc)
                prompt = O.prompt_for(s, cfg)
                self.assertTrue(prompt.startswith("Antworte mir auf Deutsch.\n\n"))
                self.assertIn(prompt, doc)

    def test_relative_links_and_anchors_resolve(self):
        pages = [PROJECT_ROOT / "README.md", PROJECT_ROOT / "CONTRIBUTING.md", *sorted(DOCS.glob("*.md")), *sorted((DOCS / "de").glob("*.md"))]
        for page in pages:
            text = re.sub(r"```.*?```", "", page.read_text(encoding="utf-8"), flags=re.S)
            for target in _LINK.findall(text):
                if re.match(r"[a-z]+:", target):
                    continue  # http(s), mailto
                path, _, anchor = target.partition("#")
                dest = (page.parent / path).resolve() if path else page
                with self.subTest(page=page.relative_to(PROJECT_ROOT).as_posix(), link=target):
                    self.assertTrue(dest.exists(), "missing target")
                    if anchor and dest.suffix == ".md":
                        self.assertIn(anchor, _anchors(dest), "missing heading")


class PackagingTests(unittest.TestCase):
    def test_locales_ship_with_the_package(self):
        with open(PROJECT_ROOT / "pyproject.toml", "rb") as fh:
            data = tomllib.load(fh)
        self.assertIn("locales/*.json", data["tool"]["setuptools"]["package-data"]["aos"])
        self.assertTrue(list((AOS / "locales").glob("*.json")))


if __name__ == "__main__":
    unittest.main()
