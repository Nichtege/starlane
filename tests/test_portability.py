"""macOS and Linux: what only a POSIX machine (or an old Python) can break, run here with the platform patched.

These tests patch the platform, so they run (and mean something) on Windows, too. They are no replacement for a run on a real macOS or Linux machine.
"""

import contextlib
import dataclasses
import io
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

import aos
from aos import agents as A
from aos import onboarding
from aos import scheduler as S
from aos import tasksched
from aos.routines import load_routines
from aos.vault import Vault
from tests.helpers import TempVaultCase

NOW = datetime(2026, 10, 9, 7, 0, 0)


class VersionGate(unittest.TestCase):
    def test_an_old_python_gets_a_message_not_a_traceback(self):
        source = Path(aos.__file__).read_text(encoding="utf-8")
        with mock.patch.object(sys, "version_info", (3, 10, 12, "final", 0)):
            with self.assertRaises(SystemExit) as caught:
                exec(compile(source, "aos/__init__.py", "exec"), {"__name__": "aos_probe"})
        self.assertIn("3.11", str(caught.exception))
        self.assertIn("python3.12 -m aos", str(caught.exception))


class ProcessGroups(TempVaultCase):
    def test_posix_kill_ends_the_whole_group(self):
        proc = mock.MagicMock(pid=4242)
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(os, "killpg", create=True) as killpg, \
                mock.patch.object(signal, "SIGKILL", 9, create=True), mock.patch.object(S.subprocess, "run") as run:
            S._kill_tree(proc)
        killpg.assert_called_once_with(4242, 9)
        run.assert_not_called()                  # no taskkill
        proc.kill.assert_not_called()

    def test_posix_kill_falls_back_to_the_process_when_there_is_no_group(self):
        proc = mock.MagicMock(pid=4242)
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(os, "killpg", create=True, side_effect=ProcessLookupError), \
                mock.patch.object(signal, "SIGKILL", 9, create=True):
            S._kill_tree(proc)                   # must not raise
        proc.kill.assert_called_once_with()

    def test_windows_still_uses_taskkill(self):
        proc = mock.MagicMock(pid=4242)
        with mock.patch.object(sys, "platform", "win32"), mock.patch.object(os, "killpg", create=True) as killpg, \
                mock.patch.object(S.subprocess, "run") as run:
            S._kill_tree(proc)
        killpg.assert_not_called()
        self.assertEqual(run.call_args.args[0][:2], ["taskkill", "/PID"])

    def _routine_kwargs(self, platform):
        routine = load_routines(self.cfg.routines_file)[0]
        proc = mock.MagicMock(returncode=0)
        proc.communicate.return_value = ("done", "")
        with mock.patch.object(sys, "platform", platform), mock.patch("aos.scheduler.subprocess.Popen", return_value=proc) as popen:
            S.run_routine(self.cfg, routine, "manual", None, NOW)
        return popen.call_args.kwargs

    def test_a_routine_leads_its_own_session_on_posix_only(self):
        self.assertIs(self._routine_kwargs("linux")["start_new_session"], True)
        self.assertIs(self._routine_kwargs("darwin")["start_new_session"], True)
        self.assertIs(self._routine_kwargs("win32")["start_new_session"], False)
        self.assertIn("creationflags", self._routine_kwargs("linux"))    # accepted (0) on POSIX; tests and Windows rely on it

    def test_an_agent_process_leads_its_own_session_on_posix_only(self):
        for platform, expected in (("linux", True), ("darwin", True), ("win32", False)):
            proc = mock.MagicMock(returncode=0)
            proc.communicate.return_value = ("Answer", "")
            with mock.patch.object(sys, "platform", platform), mock.patch.object(A, "find_claude", return_value=("/x/claude", "")), \
                    mock.patch.object(A, "claude_command", return_value=["/x/claude"]), mock.patch.object(A, "workdir", return_value=self.root), \
                    mock.patch.object(A.subprocess, "Popen", return_value=proc) as popen:
                A._run(self.cfg, mock.MagicMock(timeout_s=5, notion=False, job=""), "system", "instruction")
            self.assertIs(popen.call_args.kwargs["start_new_session"], expected, platform)
            self.assertIn("creationflags", popen.call_args.kwargs)

    def test_claude_stays_in_the_group_of_a_routine_that_already_leads_a_session(self):
        with mock.patch.object(sys, "platform", "linux"):
            with mock.patch.object(os, "getsid", create=True, return_value=os.getpid()):
                self.assertFalse(S._own_session())               # ending the routine's group then ends claude, too
            with mock.patch.object(os, "getsid", create=True, return_value=os.getpid() + 1):
                self.assertTrue(S._own_session())
        with mock.patch.object(sys, "platform", "win32"):
            self.assertFalse(S._own_session())

    def test_ctrl_c_while_an_agent_runs_stops_claude(self):
        proc = mock.MagicMock()
        proc.communicate.side_effect = KeyboardInterrupt
        with mock.patch.object(A, "find_claude", return_value=("/x/claude", "")), mock.patch.object(A, "claude_command", return_value=["/x/claude"]),                 mock.patch.object(A, "workdir", return_value=self.root), mock.patch.object(A.subprocess, "Popen", return_value=proc),                 mock.patch.object(A, "_kill_tree") as kill:
            with self.assertRaises(KeyboardInterrupt):
                A._run(self.cfg, mock.MagicMock(timeout_s=5, notion=False, job=""), "system", "instruction")
        kill.assert_called_once_with(proc)

    def _agent_run(self, proc):
        with mock.patch.object(A, "find_claude", return_value=("/x/claude", "")), mock.patch.object(A, "claude_command", return_value=["/x/claude"]),                 mock.patch.object(A, "workdir", return_value=self.root), mock.patch.object(A.subprocess, "Popen", return_value=proc):
            return A._run(self.cfg, mock.MagicMock(timeout_s=5, notion=False, job=""), "system", "instruction")

    def test_a_running_agent_is_known_until_it_ends_and_a_stopped_server_ends_it(self):
        proc = mock.MagicMock(returncode=0)
        seen = []

        def communicate(*args, **kwargs):
            seen.append(proc in A.LIVE)
            return "Answer", ""
        proc.communicate.side_effect = communicate
        self._agent_run(proc)
        self.assertEqual(seen, [True])
        self.assertNotIn(proc, A.LIVE)                   # gone again once it has ended
        A.LIVE.add(proc)
        try:
            with mock.patch.object(A, "_kill_tree") as kill:
                A.kill_live()                            # what `aos serve` does when it stops: the agent leads its own session
            kill.assert_called_once_with(proc)
        finally:
            A.LIVE.discard(proc)

    def test_ctrl_c_in_a_terminal_closes_the_job(self):
        job = {"id": "j-ctrl-c", "agent": "research", "instruction": "x", "status": "running", "started": "2026-10-09T07:00:00"}

        def runner(cfg, agent, instruction):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            agent = A.Agent(id="research", name="Research", description="", model="", tools=("Read",), timeout_s=30,
                            max_runs_per_day=5, enabled=True, prompt_file=Path("."))
            A._finish(self.cfg, agent, job, runner)  # not mixed: no web guard setup
        rec = next(j for j in A.all_jobs(self.cfg) if j["id"] == "j-ctrl-c")
        self.assertEqual(rec["status"], "failed")        # not "running": the agent would count as busy for the next 16 minutes
        self.assertIn("Ctrl+C", rec["note"])

    def test_an_installed_routine_does_not_get_a_pythonpath(self):
        package_root = str(Path(S.__file__).resolve().parent.parent)
        with mock.patch.dict(os.environ, {"PYTHONPATH": ""}):
            with mock.patch.object(S, "INSTALLED", False):
                self.assertIn(package_root, self._routine_kwargs("linux")["env"].get("PYTHONPATH", ""))
            with mock.patch.object(S, "INSTALLED", True):        # `aos` is in the interpreter's own site-packages
                self.assertNotIn(package_root, self._routine_kwargs("linux")["env"].get("PYTHONPATH", ""))

    def test_ctrl_c_while_a_routine_runs_stops_the_routine(self):
        routine = load_routines(self.cfg.routines_file)[0]
        proc = mock.MagicMock()
        proc.communicate.side_effect = KeyboardInterrupt
        with mock.patch("aos.scheduler.subprocess.Popen", return_value=proc), mock.patch.object(S, "_kill_tree") as kill:
            with self.assertRaises(KeyboardInterrupt):
                S.run_routine(self.cfg, routine, "manual", None, NOW)
        kill.assert_called_once_with(proc)


class Crontab(TempVaultCase):
    def cfg_in(self, root: str):
        return dataclasses.replace(self.cfg, project_root=Path(root), data_dir=Path(root) / "data")

    def test_the_lines_are_quoted_complete_and_find_claude(self):
        cfg = self.cfg_in("/home/me/My Notes/starlane")
        with mock.patch.object(tasksched, "find_claude", return_value=("/opt/tools/claude", "")):
            path_line, tick_line = tasksched.crontab_lines(cfg, 5)
        q = shlex.quote
        self.assertTrue(path_line.startswith("PATH=" + str(Path("/opt/tools")) + ":"))   # claude's folder first, then the usual ones
        self.assertIn("/usr/bin", path_line)
        self.assertTrue(tick_line.startswith("*/5 * * * * cd " + q(str(cfg.project_root)) + " && mkdir -p " + q(str(cfg.data_dir))))
        package_root = Path(tasksched.__file__).resolve().parent.parent
        self.assertIn("PYTHONPATH=" + q(str(package_root)), tick_line)                  # -P keeps the folder off sys.path
        self.assertIn(q(sys.executable) + " -P -m aos", tick_line)
        self.assertTrue(tick_line.endswith(" tick --quiet >> " + q(str(cfg.data_dir / "tick.log")) + " 2>&1"))
        self.assertIn("My Notes", tick_line)

    def test_the_config_is_passed_on_when_there_is_one(self):
        with mock.patch.object(tasksched, "find_claude", return_value=(None, "no")):
            tick_line = tasksched.crontab_lines(self.cfg, 10)[1]
        self.assertIn(" -P -m aos --config " + shlex.quote(str(self.cfg_path)) + " tick --quiet", tick_line)
        self.assertTrue(tick_line.startswith("*/10 * * * * "))

    def test_an_installed_tick_needs_no_pythonpath(self):
        with mock.patch.object(tasksched, "find_claude", return_value=(None, "no")), mock.patch.object(tasksched, "INSTALLED", True):
            tick_line = tasksched.crontab_lines(self.cfg, 5)[1]
        self.assertNotIn("PYTHONPATH", tick_line)                # site-packages in front of the stdlib is not what a routine wants
        self.assertIn(" -P -m aos", tick_line)

    def test_without_claude_the_path_is_still_usable(self):
        with mock.patch.object(tasksched, "find_claude", return_value=(None, "not found")):
            path_line = tasksched.crontab_lines(self.cfg, 5)[0]
        for part in ("/usr/bin", "/bin", "/opt/homebrew/bin", str(Path.home() / ".local" / "bin")):
            self.assertIn(part, path_line)

    def test_a_percent_sign_is_escaped_for_cron(self):
        cfg = self.cfg_in("/home/me/100%/notes")
        with mock.patch.object(tasksched, "find_claude", return_value=(None, "no")):
            tick_line = tasksched.crontab_lines(cfg, 5)[1]
        self.assertIn(chr(92) + "%", tick_line)
        self.assertNotIn("0%/", tick_line)

    def test_install_prints_the_lines_off_windows(self):
        out = io.StringIO()
        with mock.patch.object(tasksched, "_is_windows", return_value=False), mock.patch.object(tasksched, "find_claude", return_value=(None, "no")), \
                contextlib.redirect_stdout(out):
            self.assertEqual(tasksched.install(self.cfg, 5), 0)
        text = out.getvalue()
        self.assertIn("crontab -e", text)
        self.assertIn("PATH=", text)
        self.assertIn(" -m aos", text)

    def test_doctor_sees_the_crontab_line_off_windows(self):
        def crontab(stdout, code=0):
            return subprocess.CompletedProcess(["crontab", "-l"], code, stdout, "")

        line = "*/5 * * * * cd /x && PYTHONPATH=/p /usr/bin/python3 -P -m aos tick --quiet >> /x/data/tick.log 2>&1"
        with mock.patch.object(tasksched, "_is_windows", return_value=False):
            with mock.patch.object(tasksched.subprocess, "run", return_value=crontab("PATH=/usr/bin\n" + line + "\n")):
                self.assertTrue(tasksched.is_installed())
            with mock.patch.object(tasksched.subprocess, "run", return_value=crontab("# " + line + "\n")):
                self.assertFalse(tasksched.is_installed())           # commented out
            with mock.patch.object(tasksched.subprocess, "run", return_value=crontab("", 1)):
                self.assertFalse(tasksched.is_installed())           # "no crontab for user"
            with mock.patch.object(tasksched.subprocess, "run", side_effect=FileNotFoundError):
                self.assertFalse(tasksched.is_installed())           # no crontab program


class MacVaults(unittest.TestCase):
    NFD_CAFE = "Cafe" + chr(0x301)
    NFC_CAFE = "Caf" + chr(0xE9)

    def make(self, files: dict) -> Vault:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel, text in files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        return Vault.scan(self.root, ())

    def test_a_decomposed_file_name_is_found_by_a_composed_link(self):
        v = self.make({self.NFD_CAFE + ".md": "# Cafe\n", "index.md": f"[[{self.NFC_CAFE}]] and [[{self.NFC_CAFE.lower()}]]\n"})
        self.assertEqual([link.resolved for link in v.notes["index.md"].links], [self.NFD_CAFE + ".md"] * 2)

    def test_a_composed_file_name_is_found_by_a_decomposed_link(self):
        v = self.make({self.NFC_CAFE + ".md": "# Cafe\n", "index.md": f"[[{self.NFD_CAFE}]]\n"})
        self.assertEqual(v.notes["index.md"].links[0].resolved, self.NFC_CAFE + ".md")

    def test_dot_files_and_dot_folders_are_not_notes(self):
        v = self.make({"real.md": "# Real\n", ".hidden.md": "# Hidden\n", "._real.md": "AppleDouble", ".git/x.md": "# x\n",
                       ".stuff/inner.md": "# inner\n", "sub/._other.md": "x", "sub/other.md": "# Other\n"})
        self.assertEqual(sorted(v.notes), ["real.md", "sub/other.md"])

    def test_the_setup_check_counts_the_same_notes(self):
        self.make({"._only.md": "AppleDouble", ".hidden/x.md": "# x\n"})
        cfg = mock.MagicMock(vault=self.root, ignore=())
        self.assertFalse(onboarding._has_notes(cfg))
        (self.root / "note.md").write_text("# Note\n", encoding="utf-8")
        self.assertTrue(onboarding._has_notes(cfg))


if __name__ == "__main__":
    unittest.main()
