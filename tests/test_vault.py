import os
import unittest
from unittest import mock

from aos import vault as V
from aos.config import DEFAULT_IGNORE, Conventions, load_config
from aos.vault import Vault, link_target, parse_frontmatter, strip_markup
from tests.helpers import TempVaultCase


class FrontmatterTests(unittest.TestCase):
    def test_scalars_lists_and_quotes(self):
        fm, body, offset = parse_frontmatter(
            '---\ntype: project\nstatus: active\ndeadline:\ntags: [a, b, "c d"]\nproject: "[[Projects/x]]"\n'
            "projects: [\"[[A]]\", \"[[B]]\"]\nlist:\n  - one\n  - two\n---\n# Title\n"
        )
        self.assertEqual(fm["type"], "project")
        self.assertEqual(fm["deadline"], "")
        self.assertEqual(fm["tags"], ["a", "b", "c d"])
        self.assertEqual(fm["project"], "[[Projects/x]]")
        self.assertEqual(fm["projects"], ["[[A]]", "[[B]]"])
        self.assertEqual(fm["list"], ["one", "two"])
        self.assertTrue(body.startswith("# Title"))
        self.assertEqual(offset, 11)

    def test_no_frontmatter_and_unclosed(self):
        self.assertEqual(parse_frontmatter("# Just text")[0], {})
        self.assertEqual(parse_frontmatter("---\ntype: x\nno end")[0], {})


class LinkTests(unittest.TestCase):
    def test_link_target_variants(self):
        self.assertEqual(link_target("Projects/thesis"), "Projects/thesis")
        self.assertEqual(link_target("Note|Alias"), "Note")
        self.assertEqual(link_target("Note#Section|Alias"), "Note")
        self.assertEqual(link_target("Note\\|Alias"), "Note")
        self.assertEqual(link_target("Note^block"), "Note")
        self.assertEqual(link_target("#section-only"), "")

    def test_strip_markup(self):
        self.assertEqual(strip_markup("**Tue 6.10.** [[Projects/a|Alpha]] and [[Resources/x]]"), "Tue 6.10. Alpha and x")
        self.assertTrue(strip_markup("x" * 300).endswith("…"))

    def test_code_is_blanked_but_lines_survive(self):
        text = "a\n```\n[[in block]]\n```\nb `[[inline]]` c\n[[real]]\n"
        clean = V.strip_code(text)
        self.assertEqual(clean.count("\n"), text.count("\n"))
        self.assertNotIn("in block", clean)
        self.assertNotIn("inline", clean)
        self.assertIn("[[real]]", clean)


class VaultTests(TempVaultCase):
    def setUp(self):
        super().setUp()
        self.vault = Vault.scan(self.vault_dir, self.cfg.ignore)

    def test_scan_and_titles(self):
        self.assertIn("Projects/alpha.md", self.vault.notes)
        self.assertEqual(self.vault.get("Projects/alpha.md").title, "Alpha project")
        self.assertEqual(self.vault.get("Projects/alpha.md").area, "Projects")
        self.assertEqual(self.vault.get("CLAUDE.md").area, "(root)")

    def test_resolution_rules(self):
        r = self.vault.resolve
        self.assertEqual(r("Projects/alpha"), "Projects/alpha.md")
        self.assertEqual(r("projects/ALPHA"), "Projects/alpha.md")  # case does not matter
        self.assertEqual(r("alpha"), "Projects/alpha.md")  # file name only
        self.assertEqual(r("alpha/schedule"), "Projects/alpha/schedule.md")  # partial path
        self.assertEqual(r("Resources/knowledge#Section"), "Resources/knowledge.md")
        self.assertEqual(r("", "Journal/2026-W41.md"), "Journal/2026-W41.md")  # [[#Section]] = the note itself
        self.assertIsNone(r("Does not exist"))

    def test_links_extracted_and_resolved(self):
        alpha = self.vault.get("Projects/alpha.md")
        targets = {l.target: l.resolved for l in alpha.links}
        self.assertEqual(targets["Projects/alpha/schedule"], "Projects/alpha/schedule.md")
        self.assertEqual(targets["Resources/knowledge"], "Resources/knowledge.md")

    def test_code_links_and_placeholders_ignored(self):
        self.assertEqual(self.vault.get("CLAUDE.md").links, [])
        knowledge = self.vault.get("Resources/knowledge.md")
        self.assertEqual([l.target for l in knowledge.links], ["Does not exist"])

    def test_backlinks_and_outlinks(self):
        back = self.vault.backlinks()
        self.assertIn("index.md", back["Projects/alpha.md"])
        self.assertNotIn("Projects/alpha.md", back["Projects/alpha.md"])
        self.assertIn("Projects/alpha.md", self.vault.outlinks("index.md"))

    def test_tasks_and_sections_use_file_line_numbers(self):
        note = self.vault.get("Journal/2026-W41.md")
        tasks = V.tasks(note)
        self.assertEqual(len(tasks), 1)
        line_no, done, text = tasks[0]
        self.assertFalse(done)
        self.assertEqual(text, "Outline is done")
        raw = (self.vault_dir / "Journal/2026-W41.md").read_text(encoding="utf-8").split("\n")
        self.assertIn("Outline is done", raw[line_no - 1])
        goal_lines = [t for _, t in V.section(note, self.cfg.conv.week_goal_heading) if t.strip()]
        self.assertEqual(goal_lines, ["- [ ] Outline is done"])

    def test_ignored_folders_skipped(self):
        (self.vault_dir / "node_modules").mkdir()
        (self.vault_dir / "node_modules" / "x.md").write_text("# x", encoding="utf-8")
        v = Vault.scan(self.vault_dir, self.cfg.ignore)
        self.assertNotIn("node_modules/x.md", v.notes)

    def test_missing_vault_raises(self):
        with self.assertRaises(FileNotFoundError):
            Vault.scan(self.root / "nope")


class ConfigTests(TempVaultCase):
    def load(self, extra: str) -> object:
        path = self.root / "extra.toml"
        path.write_text(extra + f'\n[vault]\npath = "{self.vault_dir.as_posix()}"\n', encoding="utf-8")
        return load_config(path)

    def test_defaults(self):
        with mock.patch.dict(os.environ, {}, clear=False) as env:
            env.pop("AOS_USER", None)
            env.pop("AOS_LANGUAGE", None)
            cfg = self.load("")
        self.assertEqual((cfg.user_name, cfg.language), ("the user", "English"))
        self.assertEqual(cfg.conv, Conventions())
        c = cfg.conv
        self.assertEqual((c.type_key, c.created_key, c.project_key, c.projects_key, c.area_key), ("type", "created", "project", "projects", "area"))
        self.assertEqual(c.project_status, ("idea", "new", "building", "active", "paused", "done"))
        self.assertEqual((c.week_goal_heading, c.weekly_review_heading, c.ideas_dir), ("Weekly goal", "Weekly review", "Ideas"))
        self.assertEqual(c.roots, ("index.md", "AI/brain-map.md"))
        self.assertEqual(DEFAULT_IGNORE, (".git", ".obsidian", ".claude", ".trash", "node_modules"))

    def test_default_vault_path_is_neutral(self):
        with mock.patch.dict(os.environ, {"AOS_CONFIG": str(self.root / "missing.toml")}) as env:
            env.pop("AOS_VAULT", None)
            cfg = load_config()
        self.assertEqual(cfg.vault.name, "notes")

    def test_user_section_and_env_overrides(self):
        with mock.patch.dict(os.environ, {}, clear=False) as env:
            env.pop("AOS_USER", None)
            env.pop("AOS_LANGUAGE", None)
            cfg = self.load('[user]\nname = "Sam"\nlanguage = "German"\n')
            self.assertEqual((cfg.user_name, cfg.language), ("Sam", "German"))
            env.update({"AOS_USER": "Alex", "AOS_LANGUAGE": "French"})
            cfg = self.load('[user]\nname = "Sam"\nlanguage = "German"\n')
        self.assertEqual((cfg.user_name, cfg.language), ("Alex", "French"))

    def test_conventions_override_and_digest_dir(self):
        cfg = self.load('[digest]\ndir = "Out/Digest"\n[conventions]\ntype_key = "typ"\nproject_status = ["aktiv", "fertig"]\nideas_dir = "Ideen/"\n')
        self.assertEqual(cfg.conv.type_key, "typ")
        self.assertEqual(cfg.conv.project_status, ("aktiv", "fertig"))
        self.assertEqual(cfg.conv.ideas_dir, "Ideen")
        self.assertEqual(cfg.conv.digest_dir, "Out/Digest")
        self.assertEqual(cfg.conv.created_key, "created")  # untouched keys keep their default

    def test_validation_errors_are_clear(self):
        cases = [
            ('[conventions]\ntype_key = 3\n', "conventions.type_key must be a non-empty string"),
            ('[conventions]\ntype_key = ""\n', "conventions.type_key must be a non-empty string"),
            ('[conventions]\nproject_status = "active"\n', "conventions.project_status must be a list"),
            ('[conventions]\nlog_words = ["log", 1]\n', "conventions.log_words must be a list"),
            ('[conventions]\ntyp = "x"\n', "conventions.typ is not a known convention"),
            ('[conventions]\ndigest_dir = "x"\n', "[digest] dir"),
            ('conventions = 1\n', "[conventions] must be a table"),
            ('[user]\nname = 5\n', "user.name must be a non-empty string"),
            ('[user]\nlanguage = ""\n', "user.language must be a non-empty string"),
        ]
        for extra, message in cases:
            with self.subTest(extra=extra), mock.patch.dict(os.environ, {}, clear=False) as env:
                env.pop("AOS_USER", None)
                env.pop("AOS_LANGUAGE", None)
                with self.assertRaises(ValueError) as ctx:
                    self.load(extra)
                self.assertIn(message, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
