"""Installed mode and `aos setup`: the starter files, never overwriting, and what a checkout must never do."""

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aos import cli, config, shipped
from aos.config import PROJECT_ROOT


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(list(argv))
    return rc, out.getvalue()


class ShippedFiles(unittest.TestCase):
    def test_the_starter_files_are_listed_and_a_developers_own_files_are_not(self):
        files = shipped.files(PROJECT_ROOT)
        for needed in ("aos.toml", "routines.toml", "agents.toml", "aos_tick.pyw", "README.md", "LICENSE",
                       "agents/research.md", "docs/getting-started.md", "examples/vault/index.md",
                       "examples/custom-agent/agents.local.toml"):
            self.assertIn(needed, files)
        self.assertEqual(len(files), len(set(files)))
        for rel in files:
            self.assertFalse(rel.startswith(("agents/local/", "examples/vault/AI/Digest/")), rel)
            self.assertFalse(rel.endswith((".pyc", ".lock")), rel)
            self.assertNotIn("__pycache__", rel)
            self.assertNotIn(".obsidian", rel)

    def test_what_is_excluded(self):
        for rel in ("agents/local/mine.md", "agents/local", "examples/vault/AI/Digest/latest.md",
                    "examples/vault/.obsidian/app.json", "skills/x/__pycache__/a.pyc", "agents.local.toml", "x/y.lock",
                    "examples/vault/.DS_Store", "examples/vault/._index.md", "examples/vault/.trash/old.md",
                    "docs/Thumbs.db", "examples/desktop.ini"):
            self.assertFalse(shipped.wanted(rel), rel)
        for rel in ("agents/research.md", "examples/custom-agent/agents.local.toml", "examples/vault/AI/brain-map.md"):
            self.assertTrue(shipped.wanted(rel), rel)

    def test_copy_never_overwrites_and_a_second_run_adds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp)
            (dst / "aos.toml").write_text("mine = true\n", encoding="utf-8")
            copied, skipped = shipped.copy(PROJECT_ROOT, dst)
            self.assertIn("aos.toml", skipped)
            self.assertNotIn("aos.toml", copied)
            self.assertEqual((dst / "aos.toml").read_text(encoding="utf-8"), "mine = true\n")
            self.assertTrue((dst / "routines.toml").is_file())
            again, skipped_again = shipped.copy(PROJECT_ROOT, dst)
            self.assertEqual(again, [])
            self.assertEqual(len(skipped_again), len(copied) + len(skipped))

    def test_a_dangling_link_counts_as_there_and_is_not_written_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp)
            with mock.patch.object(Path, "is_symlink", lambda self: self.name == "aos.toml"):   # a dangling link: not exists(), but is_symlink()
                copied, skipped = shipped.copy(PROJECT_ROOT, dst)
            self.assertIn("aos.toml", skipped)
            self.assertFalse((dst / "aos.toml").exists())
            self.assertTrue((dst / "routines.toml").is_file())

    def test_a_missing_starter_file_is_an_error_not_half_a_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                shipped.files(Path(tmp))

    def test_the_sdist_manifest_names_what_the_wheel_ships(self):
        manifest = (PROJECT_ROOT / "MANIFEST.in").read_text(encoding="utf-8")
        include = next(ln for ln in manifest.splitlines() if ln.startswith("include "))
        for name in shipped.FILES:
            if name not in ("README.md", "LICENSE"):   # these two come in by themselves (readme, license file)
                self.assertIn(name, include.split(), name)
        for tree in shipped.TREES:
            self.assertIn("graft " + tree, manifest.splitlines())
        for pruned in shipped.EXCLUDE_PATHS - {"agents.local.toml"}:
            self.assertIn("prune " + pruned, manifest.splitlines())

    def test_build_output_is_ignored_by_git(self):
        self.assertIn("aos/_shipped/", (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines())


class InstalledMode(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        env = {k: v for k, v in os.environ.items() if not k.startswith("AOS_")}
        env["AOS_HOME"] = str(self.tmp / "home")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def installed(self):
        """Pretend to be a wheel install: starter files in a _shipped folder, no aos.toml next to the package."""
        fake = self.tmp / "_shipped"
        shipped.copy(PROJECT_ROOT, fake, overwrite=True)
        stack = contextlib.ExitStack()
        for mod in (config, cli):
            stack.enter_context(mock.patch.object(mod, "INSTALLED", True))
        stack.enter_context(mock.patch.object(cli, "SHIPPED_DIR", fake))
        self.addCleanup(stack.close)
        return fake

    def test_detection(self):
        shipped_dir, root = self.tmp / "s", self.tmp / "r"
        shipped_dir.mkdir()
        root.mkdir()
        self.assertTrue(config._is_installed(shipped_dir, root))
        (root / "aos.toml").write_text("", encoding="utf-8")
        self.assertFalse(config._is_installed(shipped_dir, root))      # a checkout with a stray _shipped folder is still a checkout
        self.assertFalse(config._is_installed(self.tmp / "missing", self.tmp / "other"))

    def test_this_checkout_is_not_installed(self):
        self.assertFalse(config.INSTALLED)
        self.assertEqual(config.default_root(), PROJECT_ROOT)

    def test_the_folder_comes_from_aos_home_or_the_default(self):
        self.assertEqual(config.home_dir(), (self.tmp / "home").resolve())
        del os.environ["AOS_HOME"]
        self.assertEqual(config.home_dir(), Path(os.path.expanduser("~/starlane")).resolve())

    def test_config_is_read_from_the_users_folder(self):
        self.installed()
        home = self.tmp / "home"
        home.mkdir()
        (home / "aos.toml").write_text('[vault]\npath = "notes"\n', encoding="utf-8")
        cfg = config.load_config()
        self.assertEqual(cfg.project_root, home.resolve())
        self.assertEqual(cfg.vault, (home / "notes").resolve())
        self.assertEqual(cfg.data_dir, (home / "data").resolve())
        self.assertEqual(cfg.routines_file, (home / "routines.toml").resolve())

    def test_setup_makes_the_folder_once_and_keeps_your_edits(self):
        self.installed()
        home = self.tmp / "home"
        rc, out = run_cli("setup")
        self.assertEqual(rc, 0)
        self.assertIn("files added", out)
        for rel in ("aos.toml", "routines.toml", "agents.toml", "aos_tick.pyw", "examples/vault/index.md", "docs/getting-started.md"):
            self.assertTrue((home / rel).is_file(), rel)
        self.assertNotIn("--config", out)                       # the default folder needs no extra option
        (home / "aos.toml").write_text("# edited\n", encoding="utf-8")
        rc, out = run_cli("setup")
        self.assertEqual(rc, 0)
        self.assertIn("0 files added", out)
        self.assertEqual((home / "aos.toml").read_text(encoding="utf-8"), "# edited\n")

    def test_setup_into_another_folder_says_how_to_use_it(self):
        self.installed()
        other = self.tmp / "elsewhere"
        rc, out = run_cli("setup", str(other))
        self.assertEqual(rc, 0)
        self.assertTrue((other / "aos.toml").is_file())
        self.assertIn("--config", out)

    def test_a_default_folder_that_holds_the_code_is_not_adopted(self):
        self.installed()
        del os.environ["AOS_HOME"]
        for var in ("HOME", "USERPROFILE"):                      # "~" is the scratch folder
            os.environ[var] = str(self.tmp)
        mine = self.tmp / "starlane"
        (mine / "aos").mkdir(parents=True)
        (mine / "aos" / "__init__.py").write_text("", encoding="utf-8")
        (mine / "aos.toml").write_text("# a working project" + chr(10), encoding="utf-8")
        self.assertTrue(config.home_is_checkout())
        for cmd in (["doctor"], ["digest"], ["setup"]):
            rc, out = run_cli(*cmd)
            self.assertEqual(rc, 2, cmd)
            self.assertIn("working project", out)
            self.assertIn("`python -m aos`", out)                # inside that project `aos` is not on the PATH: name what works
        self.assertEqual(sorted(p.name for p in mine.iterdir()), ["aos", "aos.toml"])    # nothing was written there
        own = self.tmp / "own"
        self.assertEqual(run_cli("setup", str(own))[0], 0)       # a folder that is named is the user's decision
        os.environ["AOS_HOME"] = str(own)
        self.assertFalse(config.home_is_checkout())
        self.assertEqual(run_cli("agents")[0], 0)

    def test_a_config_option_may_use_a_tilde_and_a_wrong_one_names_the_file(self):
        self.installed()
        self.assertEqual(run_cli("setup")[0], 0)
        for var in ("HOME", "USERPROFILE"):                      # cmd and PowerShell hand "~" over as it is
            os.environ[var] = str(self.tmp / "home")
        rc, out = run_cli("--config", "~/aos.toml", "doctor")
        self.assertNotIn("No config file", out)
        rc, out = run_cli("--config", str(self.tmp / "nope" / "aos.toml"), "doctor")
        self.assertEqual(rc, 2)
        self.assertIn("nope", out)                               # the file that was asked for, not "run aos setup first"

    def test_a_windows_path_in_aos_toml_is_explained(self):
        self.installed()
        home = self.tmp / "home"
        home.mkdir()
        (home / "aos.toml").write_text('[vault]\npath = "C:\\Users\\me\\notes"\n', encoding="utf-8")
        rc, out = run_cli("doctor")
        self.assertEqual(rc, 1)
        self.assertIn("aos.toml", out)
        self.assertIn("single quotes", out)

    def test_setup_does_not_unpack_into_a_notes_folder(self):
        self.installed()
        vault = self.tmp / "MyVault"
        (vault / ".obsidian").mkdir(parents=True)
        (vault / "Note.md").write_text("# mine" + chr(10), encoding="utf-8")
        rc, out = run_cli("setup", str(vault))
        self.assertEqual(rc, 2)
        self.assertIn("Obsidian vault", out)
        self.assertEqual(sorted(p.name for p in vault.iterdir()), [".obsidian", "Note.md"])

    def test_setup_from_a_checkout_needs_a_folder(self):
        rc, out = run_cli("setup")
        self.assertEqual(rc, 2)
        self.assertIn("Name the folder", out)

    def test_aos_cmd_writes_the_command_the_way_it_works_here(self):
        text = "python -m aos doctor, then python3 -m aos next"
        self.assertEqual(config.aos_cmd(text), text)             # a checkout has no `aos` on the PATH
        with mock.patch.object(config, "INSTALLED", True):
            self.assertEqual(config.aos_cmd(text), "aos doctor, then aos next")

    def test_every_other_command_asks_for_setup_first(self):
        self.installed()
        rc, out = run_cli("doctor")
        self.assertEqual(rc, 2)
        self.assertIn("aos setup", out)
        rc, _ = run_cli("init", str(self.tmp / "starter"))      # init and setup work without a config
        self.assertEqual(rc, 0)

    def test_the_whole_first_run_works_from_the_users_folder(self):
        self.installed()
        self.assertEqual(run_cli("setup")[0], 0)
        for cmd in (["digest"], ["mapcheck", "--strict"], ["agents"], ["next", "--prompt"]):
            rc, out = run_cli(*cmd)
            self.assertEqual(rc, 0, (cmd, out))
        self.assertTrue((self.tmp / "home" / "examples" / "vault" / "AI" / "Digest" / "latest.md").is_file())

    def test_setup_in_the_checkout_does_not_copy_onto_itself(self):
        rc, out = run_cli("setup", str(PROJECT_ROOT))
        self.assertEqual(rc, 2)
        self.assertIn("nothing to set up", out)


class FirstRunDetails(unittest.TestCase):
    def test_the_dashboard_link_is_flushed_for_a_pipe_or_a_log_file(self):
        import inspect

        from aos import server
        lines = [ln for ln in inspect.getsource(server.serve).splitlines() if "print(f" in ln]
        self.assertTrue(any("Dashboard running at" in ln for ln in lines))
        for ln in lines:
            self.assertIn("flush=True", ln)                      # the key exists only in memory: a buffered link is lost for good


class TickWrapper(unittest.TestCase):
    def test_the_scheduled_task_names_its_own_config(self):
        loader = importlib.machinery.SourceFileLoader("aos_tick_cfg", str(PROJECT_ROOT / "aos_tick.pyw"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        seen = []
        with mock.patch.object(cli, "main", lambda argv: seen.append(argv) or 0):
            self.assertEqual(mod.run(), 0)
        self.assertEqual(seen, [["--config", str(mod.ROOT / "aos.toml"), "tick", "--quiet"]])


if __name__ == "__main__":
    unittest.main()
