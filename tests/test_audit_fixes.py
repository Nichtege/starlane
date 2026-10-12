"""Regression tests for the backend audit findings (Windows file locks, port, silent errors, ...)."""

import contextlib
import http.client
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from unittest import mock

from aos import cli
from aos import digest as DG
from aos import scheduler as S
from aos import server as SV
from aos import tasksched
from aos.config import PROJECT_ROOT
from aos.dashboard import build_data
from aos.routines import load_routines
from aos.vault import Vault, VaultNotFound
from tests.helpers import TempVaultCase

NOW = datetime(2026, 10, 9, 7, 0, 0)


def ok(cfg, routine, trigger, slot, now):
    return {"id": routine.id, "trigger": trigger, "slot": None, "started": now.isoformat(), "finished": now.isoformat(),
            "duration_s": 0.1, "status": "ok", "rc": 0, "note": "done", "machine": cfg.machine}


class FileFixes(TempVaultCase):
    def test_atomic_write_retries_while_a_reader_holds_the_file(self):
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(13, "Access denied")  # how Windows reports an open reader
            return real(src, dst)

        target = self.root / "x.json"
        with mock.patch.object(S.os, "replace", side_effect=flaky), mock.patch.object(S.time, "sleep"):
            S.atomic_write(target, "new")
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        self.assertEqual(len(calls), 3)
        self.assertEqual([p.name for p in self.root.glob("*.tmp")], [])

    def test_state_read_error_is_not_mistaken_for_corruption(self):
        S.tick(self.cfg, NOW, load_routines(self.cfg.routines_file), ok)
        with mock.patch.object(Path, "read_text", side_effect=PermissionError(13, "locked")):
            with self.assertRaises(PermissionError):
                S.load_state(self.cfg)
        self.assertTrue(self.cfg.state_file.is_file())  # not moved to .bad, blocks/counters survive
        self.assertFalse(self.cfg.state_file.with_suffix(".json.bad").exists())

    def test_non_utf8_state_is_quarantined_not_crashing(self):
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.state_file.write_bytes(b'{"routines": {"\xff": 1}}')
        self.assertEqual(S.load_state(self.cfg), {"routines": {}})
        self.assertTrue(self.cfg.state_file.with_suffix(".json.bad").is_file())

    def test_read_runs_skips_non_objects(self):
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.runs_log.write_text('5\n"x"\n{"id": "a", "started": "2026-10-09T07:00:00"}\n', encoding="utf-8")
        self.assertEqual([r["id"] for r in S.read_runs(self.cfg)], ["a"])

    def test_write_if_changed_tolerates_a_non_utf8_old_file(self):
        target = self.vault_dir / "AI" / "Digest" / "latest.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old \xe4\n")  # saved by hand as cp1252
        self.assertTrue(DG.write_if_changed(target, "new\n"))
        self.assertEqual(target.read_text(encoding="utf-8"), "new\n")

    def test_vault_scan_skips_a_file_that_vanishes(self):
        real = Vault._load

        def vanish(self_, full, rel, kind):
            if rel == "Resources/knowledge.md":
                raise FileNotFoundError(rel)
            return real(self_, full, rel, kind)

        with mock.patch.object(Vault, "_load", vanish):
            v = Vault.scan(self.vault_dir, self.cfg.ignore)
        self.assertNotIn("Resources/knowledge.md", v.notes)
        self.assertNotIn("Resources/knowledge.md", v.files)
        self.assertIn("index.md", v.notes)


class PulseFixes(TempVaultCase):
    def test_tick_leaves_a_heartbeat_and_dashboard_gets_history(self):
        routines = load_routines(self.cfg.routines_file)
        S.tick(self.cfg, NOW, routines, ok)
        self.assertEqual(S.tick(self.cfg, NOW.replace(minute=5), routines, ok), [])  # nothing due ...
        self.assertEqual(S.load_state(self.cfg)["last_tick"], "2026-10-09T07:05:00")  # ... still a sign of life
        for i in range(30):
            S.append_run(self.cfg, {"id": "dashboard", "started": f"2026-10-09T08:{i:02d}:00", "status": "ok", "duration_s": 1})
        data = build_data(self.cfg, NOW)
        self.assertEqual(data["last_tick"], "2026-10-09T07:05:00")
        rows = {r["id"]: r for r in data["routines"]}
        self.assertEqual([h["status"] for h in rows["digest"]["history"]], ["ok"])  # not pushed out by dashboard
        self.assertEqual(len(rows["dashboard"]["history"]), 20)
        self.assertEqual(rows["dashboard"]["history"][-1]["started"], "2026-10-09T08:29:00")
        self.assertEqual(rows["git-pull"]["history"], [])

    def test_routine_process_starts_without_console_window(self):
        routine = load_routines(self.cfg.routines_file)[0]
        proc = mock.MagicMock(returncode=0)
        proc.communicate.return_value = ("done", "")
        with mock.patch("aos.scheduler.subprocess.Popen", return_value=proc) as popen:
            S.run_routine(self.cfg, routine, "manual", None, NOW)
        self.assertEqual(popen.call_args.kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_status_shows_last_tick(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["--config", str(self.cfg_path), "status"])
        self.assertIn("Last tick: none recorded yet", out.getvalue())

    def test_git_pull_never_prompts(self):
        (self.vault_dir / ".git").mkdir()
        done = subprocess.CompletedProcess([], 0, "Already up to date.", "")
        with mock.patch.object(cli.subprocess, "run", return_value=done) as run, \
                mock.patch.object(cli, "_which", return_value="/usr/bin/git"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_git_pull(self.cfg, None), 0)
        self.assertEqual(run.call_args.args[0][0], "/usr/bin/git")  # resolved on PATH, never from the current folder
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GCM_INTERACTIVE"], "never")

    def test_windows_task_is_not_killed_before_a_long_tick_ends(self):
        (self.root / "aos_tick.pyw").write_text("", encoding="utf-8")
        done = subprocess.CompletedProcess([], 0, "registered", "")
        with mock.patch.object(tasksched, "_is_windows", return_value=True), \
                mock.patch.object(tasksched, "_powershell", return_value=done) as ps, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(tasksched.install(self.cfg), 0)
        script = ps.call_args.args[0]
        self.assertIn(f"-ExecutionTimeLimit (New-TimeSpan -Minutes {S.LOCK_STALE_S // 60})", script)

    def test_tick_wrapper_logs_errors_that_pythonw_would_swallow(self):
        loader = importlib.machinery.SourceFileLoader("aos_tick_test", str(PROJECT_ROOT / "aos_tick.pyw"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        mod.LOG = self.root / "tick.log"

        def broken(argv):
            print("Error: routines.toml is not valid TOML")
            return 1

        with mock.patch.object(cli, "main", broken):
            self.assertEqual(mod.run(), 1)
        self.assertIn("routines.toml is not valid TOML", mod.LOG.read_text(encoding="utf-8"))


class ServerFixes(TempVaultCase):
    def setUp(self):
        super().setUp()
        self.httpd, self.state = SV.create_server(self.cfg, 0, token="t0k")
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def get(self, path, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}", **(headers or {})})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def test_build_errors_become_a_readable_500(self):
        with mock.patch.object(SV, "build_data", side_effect=VaultNotFound("Vault not found: X")):
            status, body = self.get("/?k=" + self.state.launch_key)  # the page needs the launch key of this server start
            self.assertEqual(status, 500)
            self.assertIn("Vault not found", json.loads(body)["error"])
            status, _ = self.get("/api/data", {"X-AOS-Token": "t0k"})
            self.assertEqual(status, 500)

    def test_second_server_cannot_share_the_port(self):
        with self.assertRaises(OSError):
            SV.create_server(self.cfg, self.port)
