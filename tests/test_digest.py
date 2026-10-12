import unittest
from datetime import date, datetime

from aos import digest as D
from aos.config import Conventions, load_config
from aos.mapcheck import run_checks
from aos.vault import Vault
from tests.helpers import TempVaultCase

TODAY = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 6, 30)
PROJECT_NOTE = "---\ntype: project\ncreated: 2026-10-09\nstatus: active\n---\n# Agentic OS\n"


class DigestTests(TempVaultCase):
    extra = {"Projects/my-project.md": PROJECT_NOTE}

    def setUp(self):
        super().setUp()
        self.cfg_path.write_text(self.cfg_path.read_text(encoding="utf-8") + '[conventions]\nproject_note = "Projects/my-project"\n', encoding="utf-8")
        self.cfg = load_config(self.cfg_path)
        self.vault = Vault.scan(self.vault_dir, self.cfg.ignore)
        self.health = run_checks(self.vault, TODAY)
        self.data = D.build_today(self.vault, self.cfg, TODAY, NOW, self.health, [])

    def test_deadlines_are_recomputed_from_today(self):
        d = self.data["deadlines"][0]
        self.assertEqual((d["date"], d["days"]), ("2026-11-10", 32))
        self.assertIn("in 32 days", d["text"])
        self.assertIn("Tue 10 Nov 2026", d["text"])
        later = D.deadlines(self.vault, date(2026, 11, 1))
        self.assertEqual(later[0]["days"], 9)

    def test_completed_projects_have_no_deadline_card(self):
        path = self.vault_dir / "Projects" / "alpha.md"
        path.write_text(path.read_text(encoding="utf-8").replace("status: active", "status: done"), encoding="utf-8")
        self.assertEqual(D.deadlines(Vault.scan(self.vault_dir, self.cfg.ignore), TODAY), [])

    def test_week_goals_and_empty_goal_warning(self):
        self.assertEqual([g["text"] for g in self.data["week_goals"]["goals"]], ["Outline is done"])
        path = self.vault_dir / "Journal" / "2026-W41.md"
        path.write_text(path.read_text(encoding="utf-8").replace("- [ ] Outline is done", "- [ ] "), encoding="utf-8")
        data = D.build_today(Vault.scan(self.vault_dir, self.cfg.ignore), self.cfg, TODAY, NOW, self.health, [])
        self.assertTrue(data["week_goals"]["empty"])
        self.assertTrue(any("No weekly goal" in n["text"] for n in data["needs"]))

    def test_missing_week_note_is_reported(self):
        (self.vault_dir / "Journal" / "2026-W41.md").unlink()
        data = D.build_today(Vault.scan(self.vault_dir, self.cfg.ignore), self.cfg, TODAY, NOW, self.health, [])
        self.assertFalse(data["week_goals"]["exists"])
        self.assertTrue(any("missing" in n["text"] for n in data["needs"]))

    def test_upcoming_only_future_dated_open_items_within_horizon(self):
        texts = [(e["date"], e["text"]) for e in self.data["upcoming"]]
        self.assertTrue(any(d == "2026-10-13" and "Team review" in t for d, t in texts))
        self.assertFalse(any("Quiz" in t for _, t in texts))  # 6.10. is in the past
        self.assertFalse(any("Struck out" in t for _, t in texts))
        self.assertTrue(all("2026-10-09" <= d <= "2026-10-23" for d, _ in texts))
        # the submission on 10.11. is outside the 14 days
        self.assertFalse(any(d == "2026-11-10" for d, _ in texts))
        self.assertEqual(self.data["upcoming"], sorted(self.data["upcoming"], key=lambda e: (e["date"], e["path"], e["line"])))

    def test_needs_split_current_week_and_overdue(self):
        kinds = [(n["kind"], n["text"]) for n in self.data["needs"]]
        self.assertIn(("task", "Finish the outline"), kinds)
        self.assertNotIn(("task", "Write chapter 4"), kinds)  # next week
        overdue = [t for k, t in kinds if k == "warn" and "Overdue" in t]
        self.assertEqual(len(overdue), 1)
        self.assertIn("Left over from week 0", overdue[0])
        self.assertIn("since 4 Oct", overdue[0])

    def test_weekly_review_is_honest_push_on_sunday_and_monday(self):
        self.assertTrue(any(n["kind"] == "info" and "Weekly review" in n["text"] for n in self.data["needs"]))  # Friday: only a notice
        monday = D.build_today(self.vault, self.cfg, date(2026, 10, 12), NOW, self.health, [])
        self.assertTrue(any(n["kind"] == "warn" and "Weekly review" in n["text"] for n in monday["needs"]))

    def test_inbox_and_failed_routines_surface(self):
        board = [{"id": "digest", "status": "blocked", "last_note": "broken"}, {"id": "x", "status": "ok"}]
        data = D.build_today(self.vault, self.cfg, TODAY, NOW, self.health, board)
        texts = " | ".join(n["text"] for n in data["needs"])
        self.assertIn("Inbox: 1 item to sort", texts)
        self.assertIn("Routine `digest` blocked: broken", texts)
        self.assertNotIn("Routine `x`", texts)

    def test_markdown_follows_vault_conventions(self):
        md = D.render_markdown(self.data, self.cfg.conv)
        self.assertTrue(md.startswith("---\ntype: digest\ncreated: 2026-10-09\n"))
        self.assertIn('project: "[[Projects/my-project]]"', md)
        self.assertIn("Part of [[Projects/my-project]]", md)
        self.assertIn("# Digest Friday, 9 Oct 2026", md)
        self.assertIn("## Needs you", md)
        self.assertIn("## Weekly goal", md)
        self.assertIn("in 32 days", md)
        self.assertIn("**Tue 13 Oct** (in 4 days)", md)
        self.assertNotIn("\r", md)

    def test_markdown_uses_configured_conventions(self):
        conv = Conventions(project_note="Projects/my-project", type_key="typ", created_key="erstellt", project_key="projekt", belongs_to="Gehört zu", week_goal_heading="Wochenziel")
        md = D.render_markdown(self.data, conv)
        self.assertTrue(md.startswith("---\ntyp: digest\nerstellt: 2026-10-09\nprojekt: "))
        self.assertIn("Gehört zu [[Projects/my-project]]", md)
        self.assertIn("## Wochenziel", md)

    def test_no_project_link_by_default(self):
        md = D.render_markdown(self.data, Conventions())
        self.assertNotIn("my-project", md)
        self.assertTrue(md.startswith("---\ntype: digest\ncreated: 2026-10-09\ntags: "))

    def test_without_project_note_no_dangling_link_is_written(self):
        (self.vault_dir / "Projects" / "my-project.md").unlink()
        vault = Vault.scan(self.vault_dir, self.cfg.ignore)
        health = run_checks(vault, TODAY)
        data = D.build_today(vault, self.cfg, TODAY, NOW, health, [])
        md = D.render_markdown(data)
        self.assertNotIn("my-project", md)
        self.assertNotIn("my-project", D.render_health_markdown(health, TODAY, NOW, data["has_project_note"]))

    def test_write_is_idempotent_and_ignores_clock_changes(self):
        written = D.write_digest(self.cfg, self.data, self.health, TODAY, NOW)
        self.assertIn("AI/Digest/latest.md", written)
        later = dict(self.data, generated="2026-10-09T18:45")
        self.assertEqual(D.write_digest(self.cfg, later, self.health, TODAY, datetime(2026, 10, 9, 18, 45)), [])
        archive = self.vault_dir / "AI" / "Digest" / "archive" / "2026-10-09.md"
        self.assertTrue(archive.is_file())

    def test_write_only_touches_digest_folder(self):
        before = {p: p.read_bytes() for p in self.vault_dir.rglob("*.md")}
        D.write_digest(self.cfg, self.data, self.health, TODAY, NOW)
        after = {p: p.read_bytes() for p in self.vault_dir.rglob("*.md") if "Digest" not in p.parts}
        self.assertEqual(before, after)

    def test_log_sections_and_dated_log_lines_are_not_events(self):
        note = self.vault_dir / "Projects" / "alpha.md"
        note.write_text(
            note.read_text(encoding="utf-8")
            + "\n## Status\n- 12.10.2026: Something was done\n## Next steps\n"
            + "- 12.10.2026: log line with a leading date\n- Meeting on 14.10.2026 at the office\n",
            encoding="utf-8",
        )
        events = D.upcoming(Vault.scan(self.vault_dir, self.cfg.ignore), TODAY, 14)
        texts = [e["text"] for e in events]
        self.assertFalse(any("Something was done" in t for t in texts))
        self.assertFalse(any("log line" in t for t in texts))
        self.assertTrue(any("Meeting on 14.10.2026" in t for t in texts))

    def test_bulk_changes_are_collapsed_to_one_line(self):
        import os
        import time

        stamp = time.time() - 3600
        for note in self.vault_dir.rglob("*.md"):
            os.utime(note, (stamp, stamp))  # all at once, like after a git pull
        recent = D.recent_changes(Vault.scan(self.vault_dir, self.cfg.ignore), datetime.now())
        self.assertEqual(len(recent), 1)
        self.assertIn("at the same time", recent[0]["title"])
        self.assertEqual(recent[0]["path"], "")
        # exactly one individually changed file stays visible
        single = self.vault_dir / "Projects" / "alpha.md"
        os.utime(single, (time.time(), time.time()))
        recent = D.recent_changes(Vault.scan(self.vault_dir, self.cfg.ignore), datetime.now())
        self.assertEqual(recent[0]["path"], "Projects/alpha.md")
        md = D.render_markdown(dict(self.data, recent=recent))
        self.assertIn("at the same time", md)

    def test_archive_is_pruned(self):
        folder = self.vault_dir / "AI" / "Digest" / "archive"
        folder.mkdir(parents=True)
        for name in ("2026-09-01.md", "2026-10-01.md", "note.md"):
            (folder / name).write_text("x", encoding="utf-8")
        removed = D.prune_archive(folder, 14, TODAY)
        self.assertEqual(removed, 1)
        self.assertTrue((folder / "2026-10-01.md").exists())
        self.assertTrue((folder / "note.md").exists())  # other files stay

    def test_digest_of_generated_notes_passes_the_vault_check(self):
        D.write_digest(self.cfg, self.data, self.health, TODAY, NOW)
        index = self.vault_dir / "index.md"
        index.write_text(index.read_text(encoding="utf-8") + "- [[AI/Digest/latest]]\n", encoding="utf-8")
        (self.vault_dir / "Projects" / "my-project.md").write_text(PROJECT_NOTE, encoding="utf-8")
        vault = Vault.scan(self.vault_dir, self.cfg.ignore)
        result = run_checks(vault, TODAY)
        bad = [i for i in result["issues"] if i["path"].startswith("AI/Digest/") and i["severity"] != "info"]
        self.assertEqual([b for b in bad if b['code'] != 'broken-link' or 'vault-check' in b['path']], [], bad)


class GermanVaultDigestTests(TempVaultCase):
    """A German vault (typ/erstellt/Wochenziel/zeitplan) still yields a full digest with matching [conventions]."""

    extra = {
        "Projects/delta.md": "---\ntyp: projekt\nerstellt: 2026-10-01\nstatus: aktiv\ndeadline: 2026-10-20\n---\n# Delta\n",
        "Projects/delta/zeitplan.md": "# Zeitplan\n\n## Woche 1 · Mo 5.10 – So 11.10\n- [ ] Gliederung\n- **Di 13.10. Termin**\n",
        "Journal/2026-W41.md": "---\ntyp: woche\n---\n# Woche\n\n## Wochenziel\n- [ ] Ziel A\n\n## Erledigt\n- 14.10.2026 nichts\n",
    }

    def test_german_conventions_drive_the_digest(self):
        self.cfg_path.write_text(
            self.cfg_path.read_text(encoding="utf-8")
            + '[conventions]\ntype_key = "typ"\ncreated_key = "erstellt"\ntype_project = "projekt"\nstatus_done = "abgeschlossen"\n'
            'week_goal_heading = "Wochenziel"\nschedule_keyword = "zeitplan"\nlog_words = ["erledigt", "stand"]\n',
            encoding="utf-8",
        )
        from aos.config import load_config

        cfg = load_config(self.cfg_path)
        vault = Vault.scan(self.vault_dir, cfg.ignore)
        data = D.build_today(vault, cfg, TODAY, NOW, run_checks(vault, TODAY, 50, cfg.conv), [])
        self.assertEqual([d["path"] for d in data["deadlines"]], ["Projects/delta.md"])
        self.assertEqual([g["text"] for g in data["week_goals"]["goals"]], ["Ziel A"])
        self.assertIn(("task", "Gliederung"), [(n["kind"], n["text"]) for n in data["needs"]])
        self.assertFalse(any("nichts" in e["text"] for e in data["upcoming"]))  # 'Erledigt' is a log section
        self.assertTrue(any(e["date"] == "2026-10-13" for e in data["upcoming"]))  # German weekday abbreviation


if __name__ == "__main__":
    unittest.main()
