import json
import subprocess
import unittest
from datetime import datetime
from unittest import mock

from aos import scheduler as S
from aos.routines import load_routines
from tests.helpers import TempVaultCase

NOW = datetime(2026, 10, 9, 7, 0, 0)  # Friday


def ok(cfg, routine, trigger, slot, now):
    return {"id": routine.id, "trigger": trigger, "slot": slot.isoformat() if slot else None, "started": now.isoformat(),
            "finished": now.isoformat(), "duration_s": 0.1, "status": "ok", "rc": 0, "note": "done", "machine": cfg.machine}


def failing(cfg, routine, trigger, slot, now):
    rec = ok(cfg, routine, trigger, slot, now)
    rec.update(status="failed", rc=1, note="broken")
    return rec


class TickTests(TempVaultCase):
    def routines(self):
        return load_routines(self.cfg.routines_file)

    def test_runs_due_routines_once_per_slot(self):
        calls = []
        runner = lambda *a: calls.append(a[1].id) or ok(*a)  # noqa: E731
        first = S.tick(self.cfg, NOW, self.routines(), runner)
        self.assertEqual(sorted(r["id"] for r in first), ["dashboard", "digest"])  # git-pull off, server-only belongs to another machine
        again = S.tick(self.cfg, NOW.replace(minute=5), self.routines(), runner)
        self.assertEqual(again, [])  # digest: slot done, dashboard: 15 min not over yet
        later = S.tick(self.cfg, NOW.replace(minute=20), self.routines(), runner)
        self.assertEqual([r["id"] for r in later], ["dashboard"])
        self.assertEqual(calls.count("digest"), 1)

    def test_state_and_log_are_written(self):
        S.tick(self.cfg, NOW, self.routines(), ok)
        state = json.loads(self.cfg.state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["routines"]["digest"]["last_status"], "ok")
        self.assertEqual(state["routines"]["digest"]["runs_today"], 1)
        runs = S.read_runs(self.cfg)
        self.assertEqual({r["id"] for r in runs}, {"digest", "dashboard"})

    def test_circuit_breaker_blocks_after_max_failures_and_unblock_frees(self):
        # digest has max_failures = 2 (see DEFAULT_ROUTINES)
        S.tick(self.cfg, NOW, self.routines(), failing)
        S.tick(self.cfg, datetime(2026, 10, 10, 7, 0), self.routines(), failing)
        row = {r["id"]: r for r in S.board(self.cfg, datetime(2026, 10, 10, 7, 1), self.routines())}["digest"]
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["fail_streak"], 2)
        calls = []
        S.tick(self.cfg, datetime(2026, 10, 11, 7, 0), self.routines(), lambda *a: calls.append(1) or ok(*a))
        self.assertNotIn("digest", [c for c in calls])  # blocked: no more runs
        self.assertTrue(S.unblock(self.cfg, "digest"))
        self.assertFalse(S.unblock(self.cfg, "does-not-exist"))
        res = S.tick(self.cfg, datetime(2026, 10, 11, 7, 5), self.routines(), ok)
        self.assertIn("digest", [r["id"] for r in res])

    def test_success_resets_failure_streak(self):
        S.tick(self.cfg, NOW, self.routines(), failing)
        S.tick(self.cfg, datetime(2026, 10, 10, 7, 0), self.routines(), ok)
        state = S.load_state(self.cfg)
        self.assertEqual(state["routines"]["digest"]["fail_streak"], 0)
        self.assertFalse(state["routines"]["digest"]["blocked"])

    def test_daily_cap_skips_without_running(self):
        text = '[[routine]]\nid = "dashboard"\nschedule = "every 1m"\ncommand = "dashboard"\nmax_runs_per_day = 2\n'
        self.write_config(text)
        routines = self.routines()
        calls = []
        runner = lambda *a: calls.append(1) or ok(*a)  # noqa: E731
        results = []
        for minute in range(0, 6):
            results += S.tick(self.cfg, NOW.replace(minute=minute), routines, runner)
        self.assertEqual(len(calls), 2)
        self.assertIn("skipped", [r["status"] for r in results])
        # the next day counts from zero again
        res = S.tick(self.cfg, datetime(2026, 10, 10, 7, 0), routines, runner)
        self.assertEqual(res[0]["status"], "ok")

    def test_busy_lock_means_no_double_start(self):
        with S.TickLock(self.cfg.lock_file):
            self.assertEqual(S.tick(self.cfg, NOW, self.routines(), ok), [])
        self.assertEqual(len(S.tick(self.cfg, NOW, self.routines(), ok)), 2)  # lock was released

    def test_stale_lock_is_taken_over(self):
        self.cfg.lock_file.parent.mkdir(parents=True, exist_ok=True)
        self.cfg.lock_file.write_text("old")
        old = self.cfg.lock_file.stat().st_mtime - 6000  # older than 75 min
        import os

        os.utime(self.cfg.lock_file, (old, old))
        self.assertEqual(len(S.tick(self.cfg, NOW, self.routines(), ok)), 2)

    def test_manual_run_ignores_schedule_and_clears_block(self):
        S.tick(self.cfg, NOW, self.routines(), failing)
        S.tick(self.cfg, datetime(2026, 10, 10, 7, 0), self.routines(), failing)
        rec = S.run_now(self.cfg, "digest", self.routines(), ok)
        self.assertEqual(rec["trigger"], "manual")
        self.assertFalse(S.load_state(self.cfg)["routines"]["digest"]["blocked"])
        with self.assertRaises(KeyError):
            S.run_now(self.cfg, "nope", self.routines(), ok)

    def test_board_statuses(self):
        rows = {r["id"]: r for r in S.board(self.cfg, NOW, self.routines())}
        self.assertEqual(rows["git-pull"]["status"], "disabled")
        self.assertEqual(rows["server-only"]["status"], "elsewhere")
        self.assertEqual(rows["digest"]["status"], "due")
        S.tick(self.cfg, NOW, self.routines(), ok)
        rows = {r["id"]: r for r in S.board(self.cfg, NOW, self.routines())}
        self.assertEqual(rows["digest"]["status"], "ok")
        self.assertEqual(rows["digest"]["runs_today"], 1)
        self.assertEqual(rows["digest"]["next_due"], "2026-10-10T06:30:00")

    def test_board_marks_overdue_when_slot_long_past(self):
        # last run was the day before, today's 06:30 slot is 3.5 hours past -> 'overdue'
        S.tick(self.cfg, datetime(2026, 10, 8, 7, 0), self.routines(), ok)
        rows = {r["id"]: r for r in S.board(self.cfg, datetime(2026, 10, 9, 10, 0), self.routines())}
        self.assertEqual(rows["digest"]["status"], "overdue")

    def test_log_is_pruned(self):
        with mock.patch.object(S, "MAX_LOG_LINES", 10), mock.patch.object(S, "KEEP_LOG_LINES", 4):
            for i in range(12):
                S.append_run(self.cfg, {"id": "x", "n": i})
        self.assertLessEqual(len(S.read_runs(self.cfg, 100)), 10)
        self.assertEqual(S.read_runs(self.cfg, 100)[-1]["n"], 11)

    def test_corrupt_state_and_log_do_not_crash(self):
        self.cfg.data_dir.mkdir(parents=True, exist_ok=True)
        self.cfg.state_file.write_text("{broken", encoding="utf-8")
        self.cfg.runs_log.write_text('{"id": "a"}\nnot json\n', encoding="utf-8")
        self.assertEqual(S.load_state(self.cfg), {"routines": {}})
        self.assertEqual(len(S.read_runs(self.cfg)), 1)
        self.assertEqual(len(S.tick(self.cfg, NOW, self.routines(), ok)), 2)


class RunnerTests(TempVaultCase):
    def test_timeout_and_oserror_become_records(self):
        routine = load_routines(self.cfg.routines_file)[0]
        proc = mock.MagicMock()
        proc.communicate.side_effect = [subprocess.TimeoutExpired("x", 1), ("", "")]
        with mock.patch("aos.scheduler.subprocess.Popen", return_value=proc), mock.patch.object(S, "_kill_tree") as kill:
            rec = S.run_routine(self.cfg, routine, "schedule", None, NOW)
        self.assertEqual(rec["status"], "timeout")
        kill.assert_called_once_with(proc)  # the process is killed together with its children
        with mock.patch("aos.scheduler.subprocess.Popen", side_effect=OSError("no Python")):
            rec = S.run_routine(self.cfg, routine, "schedule", None, NOW)
        self.assertEqual(rec["status"], "failed")
        self.assertIn("no Python", rec["note"])

    def test_real_subprocess_digest_end_to_end(self):
        routine = next(r for r in load_routines(self.cfg.routines_file) if r.id == "digest")
        rec = S.run_routine(self.cfg, routine, "manual", None, NOW)
        self.assertEqual(rec["status"], "ok", rec["note"])
        self.assertTrue((self.vault_dir / "AI" / "Digest" / "latest.md").is_file())

    def test_failing_subprocess_is_reported(self):
        self.write_config()
        self.cfg.config_file.write_text("[vault]\npath = 'Z:/does/not/exist'\n", encoding="utf-8")
        cfg = type(self.cfg)(**{**self.cfg.__dict__, "vault": self.root / "missing"})
        routine = next(r for r in load_routines(self.cfg.routines_file) if r.id == "digest")
        rec = S.run_routine(cfg, routine, "manual", None, NOW)
        self.assertEqual(rec["status"], "failed")


if __name__ == "__main__":
    unittest.main()
