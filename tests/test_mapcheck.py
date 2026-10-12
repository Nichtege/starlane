import unittest
from datetime import date

from aos.config import Conventions
from aos.mapcheck import redact, run_checks
from aos.vault import Vault
from tests.helpers import TempVaultCase

TODAY = date(2026, 10, 9)


class MapcheckTests(TempVaultCase):
    extra = {
        "Projects/beta.md": "---\ntype: project\nstatus: running\ncreated: 2026-10-01\ndeadline: 10.11.2026\n---\n# Beta\n",
        "Resources/loose.md": "---\ntype: knowledge\ncreated: 2026-10-01\n---\n# Loose\nNobody links to me.\n",
        "Resources/no-fm.md": "# Without frontmatter\n",
        "AI/no-part-of.md": '---\ntype: ai\ncreated: 2026-10-08\nproject: "[[Projects/alpha]]"\n---\n# Note\nNo reference.\n',
        "AI/broken-project.md": '---\ntype: ai\ncreated: 2026-10-08\nproject: ["[[Projects/alpha]]", "[[Projects/does-not-exist]]"]\n---\n# X\n',
        "AI/several.md": '---\ntype: ai\ncreated: 2026-10-08\nproject: ["[[Projects/alpha]]", "[[Projects/beta]]"]\n---\n# M\nPart of [[Projects/alpha]] and [[Projects/beta]]\n',
        "AI/attachments.md": '---\ntype: ai\ncreated: 2026-10-08\narea: "[[Projects/alpha]]"\n---\n# H\nPart of [[Projects/alpha]]\n[[Scans/notebook/biology.pdf]]\n',
        "Resources/secret.md": "---\ntype: knowledge\ncreated: 2026-10-01\n---\n# S\nsk-abcdefghijklmnopqrstuvwxyz0123456789\nPassword: hunter2hunter2\n",
        "Resources/Templates/template.md": "# Template\n[[Projects/]]\n",
    }

    def setUp(self):
        super().setUp()
        self.vault = Vault.scan(self.vault_dir, self.cfg.ignore)
        self.result = run_checks(self.vault, TODAY, large_kb=50, conv=self.cfg.conv)
        self.by_code = {}
        for i in self.result["issues"]:
            self.by_code.setdefault(i["code"], []).append(i)

    def paths(self, code):
        return {i["path"] for i in self.by_code.get(code, [])}

    def test_broken_link_found_with_line_number(self):
        broken = self.by_code["broken-link"]
        knowledge = [b for b in broken if b["path"] == "Resources/knowledge.md"]
        self.assertEqual(len(knowledge), 1)
        self.assertEqual(knowledge[0]["severity"], "error")
        self.assertGreater(knowledge[0]["line"], 0)
        self.assertEqual({b["path"] for b in broken}, {"Resources/knowledge.md", "AI/broken-project.md"})

    def test_templates_and_code_links_are_not_errors(self):
        self.assertNotIn("Resources/Templates/template.md", self.paths("broken-link"))
        self.assertNotIn("CLAUDE.md", self.paths("broken-link"))

    def test_local_attachments_are_info_not_errors(self):
        self.assertEqual(self.paths("attachment-local"), {"AI/attachments.md"})
        self.assertEqual(self.by_code["attachment-local"][0]["severity"], "info")

    def test_unreachable_note_is_warned(self):
        self.assertIn("Resources/loose.md", self.paths("unreachable"))
        self.assertNotIn("Projects/alpha.md", self.paths("unreachable"))

    def test_frontmatter_rules(self):
        self.assertIn("Resources/no-fm.md", self.paths("no-frontmatter"))
        self.assertIn("Projects/beta.md", self.paths("bad-status"))
        self.assertIn("Projects/beta.md", self.paths("bad-deadline"))
        self.assertNotIn("Projects/alpha.md", self.paths("bad-status"))  # 'active' is a valid status
        self.assertNotIn("Ideas/README.md", self.paths("no-frontmatter"))  # folder readmes need none

    def test_ai_link_rules_from_claude_md(self):
        self.assertIn("AI/no-part-of.md", self.paths("ai-no-part-of"))
        self.assertIn("AI/broken-project.md", self.paths("ai-bad-link"))
        self.assertNotIn("AI/several.md", self.paths("ai-no-part-of"))  # a list of projects is allowed
        self.assertNotIn("AI/Sessions/2026-10-08-alpha-test.md", self.paths("ai-no-part-of"))

    def test_secrets_found_and_never_printed(self):
        secrets = [i for i in self.by_code["secret"] if i["path"] == "Resources/secret.md"]
        self.assertEqual(len(secrets), 2)
        text = " ".join(i["message"] for i in secrets)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123456789", text)
        self.assertNotIn("hunter2hunter2", text)
        self.assertEqual(secrets[0]["severity"], "error")
        self.assertEqual(redact("key sk-abcdefghijklmnopqrstuvwxyz0123456789"), "key [redacted]")

    def test_brain_map_size_drift(self):
        drift = self.by_code["brain-map-size"]
        self.assertTrue(any("Resources/knowledge.md" in d["message"] for d in drift))

    def test_missing_week_note_warned_only_when_missing(self):
        self.assertNotIn("no-week-note", self.by_code)
        result = run_checks(self.vault, date(2026, 10, 20), 50)
        missing = [i for i in result["issues"] if i["code"] == "no-week-note"]
        self.assertEqual(missing[0]["path"], "Journal/2026-W43.md")
        self.assertIn("Resources/Templates/week", missing[0]["message"])

    def test_two_hop_stats(self):
        s = self.result["stats"]
        self.assertGreater(s["within_two_hops"], 0)
        self.assertLess(s["within_two_hops_pct"], 100)  # 'loose' and 'no-fm' are not reachable
        self.assertEqual(self.result["counts"]["error"], sum(1 for i in self.result["issues"] if i["severity"] == "error"))

    def test_large_file_flagged(self):
        (self.vault_dir / "Resources" / "large.md").write_text("---\ntype: knowledge\ncreated: 2026-10-01\n---\n# Large\n" + "x" * 60_000, encoding="utf-8")
        result = run_checks(Vault.scan(self.vault_dir, self.cfg.ignore), TODAY, 50)
        self.assertIn("Resources/large.md", {i["path"] for i in result["issues"] if i["code"] == "large"})


GERMAN = Conventions(
    type_key="typ", created_key="erstellt", project_key="projekt", projects_key="projekte", area_key="bereich",
    type_project="projekt", type_idea="idee", project_status=("idee", "neu", "aufbau", "aktiv", "pausiert", "abgeschlossen"),
    status_done="abgeschlossen", idea_status=("roh", "in-arbeit", "projekt", "verworfen"), belongs_to="Gehört zu",
    ideas_dir="Ideen", week_template="Resources/Templates/woche",
)


class GermanConventionsTests(TempVaultCase):
    """A vault written with German conventions passes as cleanly as the English one, once [conventions] says so."""

    extra = {
        "Projects/gamma.md": "---\ntyp: projekt\nerstellt: 2026-10-01\nstatus: aktiv\ndeadline: 2026-12-01\n---\n# Gamma\n",
        "AI/notiz.md": '---\ntyp: ai\nerstellt: 2026-10-08\nprojekt: "[[Projects/gamma]]"\n---\n# Notiz\nGehört zu [[Projects/gamma]]\n',
        "Ideen/README.md": "# Ideen\n",
    }

    def test_german_vault_is_clean_with_german_conventions(self):
        vault = Vault.scan(self.vault_dir, self.cfg.ignore)
        issues = {(i["code"], i["path"]) for i in run_checks(vault, TODAY, 50, GERMAN)["issues"]}
        for rel in ("Projects/gamma.md", "AI/notiz.md", "Ideen/README.md"):
            self.assertFalse({c for c, p in issues if p == rel} - {"unreachable"}, rel)
        # the same notes read with the English defaults are flagged
        english = {(i["code"], i["path"]) for i in run_checks(vault, TODAY, 50)["issues"]}
        self.assertIn(("no-type", "Projects/gamma.md"), english)
        self.assertIn(("ai-unlinked", "AI/notiz.md"), english)

    def test_german_conventions_from_aos_toml(self):
        self.cfg_path.write_text(
            self.cfg_path.read_text(encoding="utf-8")
            + '[conventions]\ntype_key = "typ"\ncreated_key = "erstellt"\nproject_key = "projekt"\ntype_project = "projekt"\n'
            'project_status = ["aktiv", "abgeschlossen"]\nbelongs_to = "Gehört zu"\n',
            encoding="utf-8",
        )
        from aos.config import load_config

        conv = load_config(self.cfg_path).conv
        vault = Vault.scan(self.vault_dir, self.cfg.ignore)
        issues = run_checks(vault, TODAY, 50, conv)["issues"]
        self.assertFalse([i for i in issues if i["path"] in ("Projects/gamma.md", "AI/notiz.md") and i["code"] != "unreachable"])


class RunTogetherEnvNames(unittest.TestCase):
    def test_upper_case_env_names_are_redacted_but_words_are_not(self):
        self.assertEqual(redact("PGPASSWORD=hunter2hunter2"), "[redacted]")
        self.assertEqual(redact("SECRETSANTA=yes"), "SECRETSANTA=yes")
        self.assertEqual(redact("the TOKEN is nice"), "the TOKEN is nice")


if __name__ == "__main__":
    unittest.main()
