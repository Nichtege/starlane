"""aos.local.toml: your own settings, merged over the shipped aos.toml (config.read_settings)."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aos import cli, config, i18n
from aos.config import load_config, local_path, peek_ui_language, read_settings

SHIPPED = """[user]
name = "You"
ui_language = "en"

[vault]
path = "examples/vault"
ignore = [".git", ".obsidian"]
large_file_kb = 50

[digest]
dir = "AI/Digest"
keep_days = 14
"""

MINE = """[user]
name = "Ege"
ui_language = "de"

[vault]
path = "notes"
ignore = [".git", ".obsidian", "Schulhefte"]

[digest]
file = "aktuell.md"

[conventions]
type_key = "typ"
"""


class LocalSettingsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "notes").mkdir()
        self.cfg_path = self.root / "aos.toml"
        self.cfg_path.write_text(SHIPPED, encoding="utf-8")
        self.local = self.root / "aos.local.toml"
        for p in (mock.patch.object(config, "LOCAL_OVERRIDES", True), mock.patch.dict(os.environ)):
            p.start()
            self.addCleanup(p.stop)
        os.environ.pop("AOS_UI_LANGUAGE", None)
        self.addCleanup(i18n.use, i18n.SOURCE)

    def test_the_local_file_sits_next_to_the_config(self):
        self.assertEqual(local_path(self.cfg_path), self.local)
        self.assertEqual(local_path(self.root / "server.toml"), self.root / "server.local.toml")

    def test_without_a_local_file_nothing_changes(self):
        raw, local = read_settings(self.cfg_path)
        self.assertIsNone(local)
        cfg = load_config(self.cfg_path)
        self.assertIsNone(cfg.local_file)
        self.assertEqual((cfg.user_name, cfg.ui_language, cfg.vault), ("You", "en", (self.root / "examples" / "vault").resolve()))

    def test_tables_merge_key_by_key_and_values_are_replaced(self):
        self.local.write_text(MINE, encoding="utf-8")
        raw, local = read_settings(self.cfg_path)
        self.assertEqual(local, self.local)
        self.assertEqual(raw["vault"]["large_file_kb"], 50)  # kept from aos.toml
        self.assertEqual(raw["vault"]["ignore"], [".git", ".obsidian", "Schulhefte"])  # a list is replaced, not appended
        self.assertEqual(raw["digest"], {"dir": "AI/Digest", "keep_days": 14, "file": "aktuell.md"})
        cfg = load_config(self.cfg_path)
        self.assertEqual(cfg.local_file, self.local)
        self.assertEqual(cfg.config_file, self.cfg_path)
        self.assertEqual((cfg.user_name, cfg.ui_language, cfg.language), ("Ege", "de", "Deutsch"))
        self.assertEqual(cfg.vault, (self.root / "notes").resolve())  # relative to the folder of both files
        self.assertEqual(cfg.conv.digest_file, "aktuell.md")
        self.assertEqual(cfg.conv.type_key, "typ")
        self.assertEqual(peek_ui_language(self.cfg_path), "de")

    def test_it_follows_the_file_however_it_is_named(self):
        """The scheduler hands AOS_CONFIG=<aos.toml> to its child runs; the cron line passes --config. Both must see it."""
        self.local.write_text(MINE, encoding="utf-8")
        os.environ["AOS_CONFIG"] = str(self.cfg_path)
        self.assertEqual(load_config().user_name, "Ege")
        self.assertEqual(peek_ui_language(), "de")

    def test_a_broken_local_file_is_named_in_the_error(self):
        self.local.write_text("[user\nname = 'x'\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "aos.local.toml"):
            load_config(self.cfg_path)
        self.assertEqual(peek_ui_language(self.cfg_path), "en")  # the CLI still starts and reports the error

    def test_unknown_keys_are_still_refused(self):
        self.local.write_text("[conventions]\ntype_kee = 'typ'\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            load_config(self.cfg_path)

    def test_doctor_shows_it(self):
        self.local.write_text('[user]\nname = "Ege"\n', encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--config", str(self.cfg_path), "doctor"])
        self.assertIn("Your own settings on top: " + str(self.local), out.getvalue())

    def test_switched_off_for_the_test_suite(self):
        self.local.write_text(MINE, encoding="utf-8")
        with mock.patch.object(config, "LOCAL_OVERRIDES", False):
            self.assertEqual(load_config(self.cfg_path).user_name, "You")


if __name__ == "__main__":
    unittest.main()
