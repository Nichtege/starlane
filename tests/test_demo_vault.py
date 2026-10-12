"""The bundled demo vault (examples/vault) and the shipped aos.toml that points at it: everything works out of the box."""

import contextlib
import dataclasses
import io
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from aos import cli
from aos import onboarding as O
from aos.config import PROJECT_ROOT, load_config
from aos.mapcheck import redact, run_checks
from aos.vault import Vault

SHIPPED = PROJECT_ROOT / "aos.toml"
DEMO = PROJECT_ROOT / "examples" / "vault"
TODAY = datetime(2026, 10, 11, 8, 0)  # Sunday of 2026-W41, the week the demo vault is set in
_ENV = ("AOS_CONFIG", "AOS_VAULT", "AOS_DATA")


def _run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(list(args))
    return code, out.getvalue()


class DemoVaultTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        env = {k: v for k, v in os.environ.items() if k not in _ENV}
        for p in (mock.patch.dict(os.environ, env, clear=True),
                  mock.patch.object(cli, "now_local", return_value=TODAY),
                  mock.patch.object(O.A, "find_claude", return_value=(None, "not found"))):
            p.start()
            self.addCleanup(p.stop)

    def test_shipped_config_points_at_the_demo_vault_independent_of_cwd(self):
        cwd = os.getcwd()
        os.chdir(self.tmp)  # a relative vault path resolves against aos.toml, never the current folder
        self.addCleanup(os.chdir, cwd)
        cfg = load_config(SHIPPED)
        self.assertEqual(cfg.vault, DEMO.resolve())
        self.assertTrue(cfg.vault.is_dir())
        self.assertTrue(cfg.vault.is_relative_to(PROJECT_ROOT))
        self.assertEqual(cfg.vault_name, "vault")

    def test_vault_check_is_clean(self):
        cfg = load_config(SHIPPED)
        health = run_checks(Vault.scan(cfg.vault, cfg.ignore), TODAY.date(), cfg.large_file_kb, cfg.conv)
        self.assertEqual((health["counts"]["error"], health["counts"]["warn"]), (0, 0), health["issues"])
        self.assertEqual(health["stats"]["within_two_hops_pct"], 100)
        self.assertGreaterEqual(health["stats"]["notes"], 20)

    def test_digest_on_a_copy(self):
        vault = self.tmp / "vault"
        shutil.copytree(DEMO, vault, ignore=shutil.ignore_patterns("Digest"))
        cfg_path = self.tmp / "aos.toml"
        cfg_path.write_text(f'[vault]\npath = "vault"\n[paths]\ndata = "data"\n'
                            f'routines = "{(PROJECT_ROOT / "routines.toml").as_posix()}"\n', encoding="utf-8")
        code, out = _run("--config", str(cfg_path), "digest")
        self.assertEqual(code, 0, out)
        latest = (vault / "AI" / "Digest" / "latest.md").read_text(encoding="utf-8")
        self.assertIn("## Deadlines", latest)
        self.assertIn("Raised beds before the frost: Sat 28 Nov 2026", latest)
        self.assertIn("- [x] Both raised-bed frames built and in place", latest)
        self.assertIn("conversation club", latest)  # an upcoming date from an area note
        self.assertIn("0 errors, 0 warnings", latest)

    def test_claude_md_explains_the_vault(self):
        text = (DEMO / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("index.md", text)
        self.assertIn("brain-map", text)

    def test_no_secrets_in_the_demo_vault(self):
        for f in DEMO.rglob("*"):
            if f.is_file():
                text = f.read_text(encoding="utf-8")
                self.assertEqual(redact(text), text, f)

    def test_next_shows_the_vault_stage_done(self):
        os.environ["AOS_DATA"] = str(self.tmp / "data")
        self.assertIs(O.status(O.get("vault"), load_config(SHIPPED)), True)
        code, out = _run("--config", str(SHIPPED), "next")
        self.assertEqual(code, 0)
        self.assertIn(" ✓  1. vault", out)

    def test_doctor_passes_on_the_shipped_config(self):
        cfg = dataclasses.replace(load_config(SHIPPED), data_dir=self.tmp / "data", skills_dirs=(PROJECT_ROOT / "skills",))
        out = io.StringIO()
        with mock.patch("aos.tasksched.is_installed", return_value=False), contextlib.redirect_stdout(out):
            code = cli.cmd_doctor(cfg, None)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("✓ Vault check without errors", out.getvalue())


if __name__ == "__main__":
    unittest.main()
