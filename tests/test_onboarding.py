import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from aos import cli
from aos import onboarding as O
from aos.config import PROJECT_ROOT, load_config
from tests.helpers import TempVaultCase

DOC = PROJECT_ROOT / "docs" / "getting-started.md"


def run(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = cli.main(list(args))
    return code, out.getvalue()


def states(cfg):
    return {s.id: O.status(s, cfg) for s in O.STAGES}


class StageDataTests(unittest.TestCase):
    def test_ids_unique_and_order(self):
        ids = [s.id for s in O.STAGES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, ["vault", "obsidian", "claude", "digest", "dashboard", "routines", "first-agent",
                               "own-agent", "conventions", "skills"])

    def test_every_prompt_has_guardrails_and_is_in_the_doc(self):
        doc = DOC.read_text(encoding="utf-8")
        cfg = load_config(PROJECT_ROOT / "does-not-exist.toml")
        for s in O.STAGES:
            self.assertIn(O.GUARDRAILS, s.prompt, s.id)
            self.assertIn(s.prompt, doc, s.id)
            self.assertIn(O.prompt_for(s, cfg), doc, s.id)  # the doc shows the prompt as `aos next` prints it with defaults
            self.assertIn(s.title, doc, s.id)

    def test_prompt_uses_name_and_language(self):
        cfg = load_config(PROJECT_ROOT / "does-not-exist.toml")
        self.assertTrue(O.prompt_for(O.STAGES[0], cfg).startswith("Reply to me in English.\n\n"))
        with mock.patch.dict(os.environ, {"AOS_USER": "Sam", "AOS_LANGUAGE": "German"}):
            cfg = load_config(PROJECT_ROOT / "does-not-exist.toml")
        self.assertTrue(O.prompt_for(O.STAGES[0], cfg).startswith("I am Sam; reply to me in German.\n\n"))


class DetectionTests(TempVaultCase):
    def test_fresh_vault(self):
        with mock.patch.object(O.A, "find_claude", return_value=(None, "not found")):
            st = states(self.cfg)
        self.assertEqual(st, {"vault": True, "obsidian": False, "claude": False, "digest": False, "dashboard": None,
                              "routines": False, "first-agent": False, "own-agent": False, "conventions": None,
                              "skills": False})

    def test_missing_vault_never_crashes(self):
        self.cfg_path.write_text(f'[vault]\npath = "{(self.root / "nope").as_posix()}"\n[paths]\ndata = "nodata"\n'
                                 'routines = "missing.toml"\n', encoding="utf-8")
        st = states(load_config(self.cfg_path))
        self.assertIs(st["vault"], False)
        self.assertIs(st["obsidian"], False)
        self.assertIs(st["digest"], False)
        self.assertIs(st["skills"], False)  # missing routines.toml: not done, no exception

    def test_vault_needs_a_note_outside_ignored_folders(self):
        empty = self.root / "empty"
        (empty / ".obsidian").mkdir(parents=True)
        (empty / ".obsidian" / "x.md").write_text("x", encoding="utf-8")
        self.cfg_path.write_text(f'[vault]\npath = "{empty.as_posix()}"\n', encoding="utf-8")
        cfg = load_config(self.cfg_path)
        self.assertIs(O.status(O.get("vault"), cfg), False)
        self.assertIs(O.status(O.get("obsidian"), cfg), True)

    def test_each_stage_turns_done(self):
        (self.vault_dir / ".obsidian").mkdir()
        digest = self.vault_dir / "AI" / "Digest"
        digest.mkdir(parents=True)
        (digest / "latest.md").write_text("# Digest\n", encoding="utf-8")
        self.cfg.data_dir.mkdir(parents=True)
        self.cfg.state_file.write_text("{}", encoding="utf-8")
        self.cfg.jobs_log.parent.mkdir(parents=True)
        self.cfg.jobs_log.write_text('{"id": "a", "status": "running"}\n{"id": "a", "status": "ok"}\n', encoding="utf-8")
        (self.root / "agents.local.toml").write_text("", encoding="utf-8")
        with open(self.cfg_path, "a", encoding="utf-8") as fh:
            fh.write('[conventions]\ninbox_dir = "00 Inbox"\n')
        (self.root / "routines.toml").write_text('[[routine]]\nid = "plan"\nschedule = "weekly mon 07:00"\ncommand = "skill"\n'
                                                 'skill = "weekly-plan"\ninstruction = "Plan."\n', encoding="utf-8")
        cfg = load_config(self.cfg_path)
        with mock.patch.object(O.A, "find_claude", return_value=("/usr/bin/claude", "")):
            st = states(cfg)
        self.assertEqual({k for k, v in st.items() if v is not True}, {"dashboard"})

    def test_one_job_line_is_not_a_finished_job(self):
        self.cfg.jobs_log.parent.mkdir(parents=True)
        self.cfg.jobs_log.write_text('{"id": "a", "status": "running"}\n', encoding="utf-8")
        self.assertIs(O.status(O.get("first-agent"), self.cfg), False)

    def test_only_a_job_that_finished_ok_is_a_first_task(self):
        self.cfg.jobs_log.parent.mkdir(parents=True)
        self.cfg.jobs_log.write_text('{"id": "a", "status": "running"}\n{"id": "a", "status": "failed", "note": "`claude` not found"}\n',
                                     encoding="utf-8")
        self.assertIs(O.status(O.get("first-agent"), self.cfg), False)   # a failed start is not progress
        with self.cfg.jobs_log.open("a", encoding="utf-8") as fh:
            fh.write('{"id": "b", "status": "running"}\n{"id": "b", "status": "ok", "result": "Answer"}\n')
        self.assertIs(O.status(O.get("first-agent"), self.cfg), True)

    def test_disabled_skill_routine_does_not_count(self):
        (self.root / "routines.toml").write_text('[[routine]]\nid = "plan"\nschedule = "weekly mon 07:00"\ncommand = "skill"\n'
                                                 'skill = "weekly-plan"\ninstruction = "Plan."\nenabled = false\n', encoding="utf-8")
        self.assertIs(O.status(O.get("skills"), self.cfg), False)


class NextCommandTests(TempVaultCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(O.A, "find_claude", return_value=(None, "not found"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_checklist_and_next_details(self):
        code, out = run("--config", str(self.cfg_path), "next")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Getting started (1 of 10 done)"))
        lines = out.splitlines()
        self.assertIn(" ✓  1. vault", lines[1])
        self.assertIn(" →  2. obsidian", lines[2])
        self.assertIn(" ○  3. claude", lines[3])
        self.assertIn(" ·  5. dashboard", lines[5])
        self.assertLess(out.index("── 2. Open the vault in Obsidian"), out.index("----- BEGIN PROMPT -----"))
        self.assertIn(O.get("obsidian").prompt, out)
        self.assertNotIn(O.get("vault").prompt, out)  # only the first open stage in detail
        self.assertEqual(out.count("----- BEGIN PROMPT -----"), 1)

    def test_all(self):
        code, out = run("--config", str(self.cfg_path), "next", "--all")
        self.assertEqual(code, 0)
        self.assertEqual(out.count("----- END PROMPT -----"), len(O.STAGES))
        positions = [out.index(f"({s.id}) ──") for s in O.STAGES]
        self.assertEqual(positions, sorted(positions))

    def test_prompt_only(self):
        code, out = run("--config", str(self.cfg_path), "next", "--prompt")
        self.assertEqual(code, 0)
        self.assertEqual(out, O.prompt_for(O.get("obsidian"), self.cfg) + "\n")

    def test_stage(self):
        code, out = run("--config", str(self.cfg_path), "next", "--stage", "conventions")
        self.assertEqual(code, 0)
        self.assertIn("── 9. Teach it your vault's conventions (conventions) ──", out)
        self.assertEqual(out.count("----- BEGIN PROMPT -----"), 1)
        code, out = run("--config", str(self.cfg_path), "next", "--stage", "skills", "--prompt")
        self.assertEqual(out, O.prompt_for(O.get("skills"), self.cfg) + "\n")

    def test_unknown_stage(self):
        code, out = run("--config", str(self.cfg_path), "next", "--stage", "nope")
        self.assertEqual(code, 2)
        self.assertIn("Unknown stage: nope", out)
        self.assertIn("vault, obsidian", out)

    def test_no_config_file(self):
        missing = self.root / "missing" / "aos.toml"
        with mock.patch.dict(os.environ, {"AOS_VAULT": str(self.root / "no-vault"), "AOS_DATA": str(self.root / "no-data")}):
            code, out = run("--config", str(missing), "next")
        self.assertEqual(code, 0)
        self.assertIn(" →  1. vault", out)
        self.assertFalse((self.root / "no-data").exists())  # writes nothing
        self.assertFalse((self.root / "no-vault").exists())

    def test_init_ends_with_hint(self):
        code, out = run("--config", str(self.cfg_path), "init", str(self.root / "starter"))
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], cli.NEXT_HINT)


if __name__ == "__main__":
    unittest.main()
