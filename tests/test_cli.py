import contextlib
import io
import json
import unittest

from aos import cli
from aos.dashboard import _json_for_html, build_data, render_html, write_dashboard
from tests.helpers import TempVaultCase


def run(cfg_path, *args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(["--config", str(cfg_path), *args])
    return code, out.getvalue()


class CliTests(TempVaultCase):
    def test_digest_writes_files_and_is_idempotent(self):
        code, out = run(self.cfg_path, "digest")
        self.assertEqual(code, 0, out)
        target = self.vault_dir / "AI" / "Digest" / "latest.md"
        self.assertTrue(target.is_file())
        self.assertTrue((self.vault_dir / "AI" / "Digest" / "vault-check.md").is_file())
        first = target.read_bytes()
        code, out = run(self.cfg_path, "digest")
        self.assertEqual(code, 0)
        self.assertEqual(target.read_bytes(), first)
        self.assertIn("nothing changed", out)

    def test_mapcheck_strict_exit_codes(self):
        code, out = run(self.cfg_path, "mapcheck", "--strict")
        self.assertEqual(code, 1)  # broken link in the test vault
        self.assertIn("1 error,", out)  # singular and plural right (mapcheck.count_text)
        (self.vault_dir / "Resources" / "knowledge.md").write_text("---\ntype: knowledge\ncreated: 2026-10-01\n---\n# Knowledge\n", encoding="utf-8")
        code, _ = run(self.cfg_path, "mapcheck", "--strict")
        self.assertEqual(code, 0)

    def test_status_and_tick_and_run_unknown(self):
        code, out = run(self.cfg_path, "status")
        self.assertEqual(code, 0)
        self.assertIn("digest", out)
        self.assertIn("server-only", out)
        code, out = run(self.cfg_path, "run", "does-not-exist")
        self.assertEqual(code, 2)
        code, out = run(self.cfg_path, "unblock", "digest")
        self.assertIn(code, (0, 1))

    def test_broken_routines_file_gives_message_not_traceback(self):
        self.write_config("[[routine]]\nid = 'x'\nschedule = 'sometimes'\ncommand = 'digest'\n")
        code, out = run(self.cfg_path, "status")
        self.assertEqual(code, 1)
        self.assertIn("schedule", out)

    def test_doctor_reports_problems_and_passes_on_good_setup(self):
        code, out = run(self.cfg_path, "doctor")
        self.assertEqual(code, 1)  # the test vault has a broken link
        self.assertIn("✗", out)
        self.assertNotIn(cli.NEXT_HINT, out)
        (self.vault_dir / "Resources" / "knowledge.md").write_text("---\ntype: knowledge\ncreated: 2026-10-01\n---\n# Knowledge\n", encoding="utf-8")
        code, out = run(self.cfg_path, "doctor")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines()[-1], cli.NEXT_HINT)

    def test_dashboard_command_builds_html_and_json(self):
        code, out = run(self.cfg_path, "dashboard")
        self.assertEqual(code, 0, out)
        html = (self.cfg.out_dir / "dashboard.html").read_text(encoding="utf-8")
        data = json.loads((self.cfg.out_dir / "data.json").read_text(encoding="utf-8"))
        self.assertNotIn("__AOS_DATA__", html)
        self.assertEqual(data["version"], 1)
        self.assertIsNone(data["api"])
        self.assertTrue(data["vault"]["uri"].startswith("obsidian://open?vault=TestVault&file="))

    def test_data_contract_keys_and_hidden_archive(self):
        run(self.cfg_path, "digest")  # creates the digest archive folder
        data = build_data(self.cfg)
        for key in ("version", "generated", "today", "machine", "vault", "nodes", "edges", "changes", "digest", "health", "routines", "runs", "api"):
            self.assertIn(key, data)
        ids = {n["id"] for n in data["nodes"]}
        self.assertNotIn("AI/Digest/archive", " ".join(ids))
        self.assertTrue(all(e["s"] in ids and e["t"] in ids for e in data["edges"]))
        node = next(n for n in data["nodes"] if n["id"] == "Projects/alpha.md")
        for key in ("label", "kind", "area", "type", "status", "project", "deadline", "tags", "size", "words", "mtime", "in", "out"):
            self.assertIn(key, node)

    def test_json_for_html_is_script_safe(self):
        payload = _json_for_html({"x": "</script><!-- &  "})
        for bad in ("</script", "<!--", "<", ">", "&", " "):
            self.assertNotIn(bad, payload)
        self.assertEqual(json.loads(payload)["x"], "</script><!-- &  ")

    def test_render_html_requires_marker(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "t.html"
            bad.write_text("<html></html>", encoding="utf-8")
            with self.assertRaises(ValueError):
                render_html({"a": 1}, bad)

    def test_write_dashboard_info(self):
        info = write_dashboard(self.cfg)
        self.assertGreater(info["nodes"], 5)


if __name__ == "__main__":
    unittest.main()
