"""`aos init`: the starter vault is clean under the vault check and is never overwritten."""

import tempfile
import unittest
from datetime import date
from pathlib import Path

from aos.cli import main
from aos.config import Conventions
from aos.mapcheck import run_checks
from aos.scaffold import scaffold, starter_files
from aos.vault import Vault

TODAY = date(2026, 10, 9)


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "vault"

    def test_starter_vault_has_no_findings(self):
        created, skipped = scaffold(self.root, TODAY)
        self.assertTrue(created)
        self.assertEqual(skipped, [])
        result = run_checks(Vault.scan(self.root, ()), TODAY)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["stats"]["within_two_hops_pct"], 100)

    def test_existing_files_are_never_overwritten(self):
        self.root.mkdir()
        (self.root / "index.md").write_text("mine", encoding="utf-8")
        created, skipped = scaffold(self.root, TODAY)
        self.assertIn("index.md", skipped)
        self.assertNotIn("index.md", created)
        self.assertEqual((self.root / "index.md").read_text(encoding="utf-8"), "mine")

    def test_second_run_creates_nothing(self):
        scaffold(self.root, TODAY)
        created, skipped = scaffold(self.root, TODAY)
        self.assertEqual(created, [])
        self.assertTrue(skipped)

    def test_follows_custom_conventions(self):
        conv = Conventions(type_key="typ", created_key="erstellt", journal_dir="Tagebuch")
        files = starter_files(TODAY, conv)
        self.assertTrue(any(p.startswith("Tagebuch/") for p in files))
        self.assertIn("typ:", files["index.md"])

    def test_cli_init_needs_no_config(self):
        missing = Path(self._tmp.name) / "missing.toml"
        self.assertEqual(main(["--config", str(missing), "init", str(self.root)]), 0)
        self.assertTrue((self.root / "index.md").is_file())


if __name__ == "__main__":
    unittest.main()
