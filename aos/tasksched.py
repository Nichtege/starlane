"""Agent layer on your own machine: have the scheduler (`aos tick`) started every 5 minutes.

Windows: a scheduled task for the current user only (no admin needed), runs invisibly via pythonw.
Linux/macOS: nothing is changed; the matching crontab lines are printed (`crontab_lines`).
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from pathlib import Path

from .agents import find_claude
from .config import INSTALLED, Config, aos_cmd
from .i18n import tr
from .scheduler import LOCK_STALE_S

# One tick runs several routines in a row (up to 60 min each). If Windows stops it early, a half-finished run and
# the lock file are left behind. So the limit is as long as the lock file stays valid.
TICK_LIMIT_MIN = LOCK_STALE_S // 60

TASK_NAME = "Starlane tick"


def _is_windows() -> bool:
    return sys.platform == "win32"


def _powershell(script: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )


def _ps_quote(value: str) -> str:
    # PowerShell also treats the typographic apostrophes as quotes
    for quote in ("'", chr(0x2018), chr(0x2019), chr(0x201A), chr(0x201B)):
        value = value.replace(quote, quote * 2)
    return "'" + value + "'"


def _pythonw() -> str:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate if candidate.is_file() else exe)


def crontab_lines(cfg: Config, minutes: int) -> list[str]:
    """What to add with `crontab -e`: a PATH line and the tick.

    cron starts with a bare PATH (/usr/bin:/bin), so `claude` would not be found without the first line. Paths are quoted
    (spaces), the config is passed on (it may live elsewhere) and the data folder is made first: the log redirect fails, and the
    tick never runs, when the folder is missing."""
    q = shlex.quote
    data = Path(cfg.data_dir)
    config = f" --config {q(str(cfg.config_file))}" if cfg.config_file else ""
    # -P keeps the working folder off sys.path, so `aos` itself is found through PYTHONPATH (the same as in run_routine)
    package_root = Path(__file__).resolve().parent.parent
    env = "" if INSTALLED else f"PYTHONPATH={q(str(package_root))} "  # installed: `aos` is in the interpreter's own site-packages
    cmd = (f"cd {q(str(cfg.project_root))} && mkdir -p {q(str(data))} && {env}"
           f"{q(sys.executable)} -P -m aos{config} tick --quiet >> {q(str(data / 'tick.log'))} 2>&1")
    claude, _ = find_claude(cfg.vault)
    dirs = [str(Path(claude).parent)] if claude else []
    dirs += [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]  # cron expands no ~ or $HOME
    return ["PATH=" + ":".join(dict.fromkeys(dirs)), f"*/{minutes} * * * * " + cmd.replace("%", "\\%")]  # % is special in a crontab


def _crontab_installed() -> bool:
    try:
        proc = subprocess.run(["crontab", "-l"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return False
    lines = [ln for ln in proc.stdout.splitlines() if not ln.lstrip().startswith("#")]
    return proc.returncode == 0 and any("-m aos" in ln and " tick" in ln for ln in lines)


def is_installed() -> bool:
    if not _is_windows():
        return _crontab_installed()
    try:
        proc = _powershell(f"if (Get-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -ErrorAction SilentlyContinue) {{ 'yes' }}")
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "yes" in proc.stdout


def install(cfg: Config, minutes: int = 5) -> int:
    minutes = max(1, min(int(minutes), 60))
    root = Path(cfg.project_root)
    if not _is_windows():
        print(tr("Not Windows: nothing changed. Add these lines with `crontab -e`"))
        print(tr("(cron has a bare PATH, so the first line is what lets it find `claude`; merge it if you already have a PATH line):"))
        for line in crontab_lines(cfg, minutes):
            print(line)
        print(aos_cmd(tr("Check afterwards with: python3 -m aos doctor")))
        return 0
    script = root / "aos_tick.pyw"
    if not script.is_file():
        print(tr("Missing: {path}", path=script) + (" " + tr("(run `aos setup` first)") if INSTALLED else ""))
        return 1
    ps = f"""
$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute {_ps_quote(_pythonw())} -Argument {_ps_quote(chr(34) + str(script) + chr(34))} -WorkingDirectory {_ps_quote(str(root))}
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes {minutes})
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes {TICK_LIMIT_MIN}) -Hidden
Register-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Action $action -Trigger $trigger -Settings $settings -Description 'Starlane tick: runs due routines (aos tick). Remove with: {aos_cmd('python -m aos uninstall-task')}' -Force | Out-Null
'registered'
"""
    proc = _powershell(ps)
    if "registered" not in proc.stdout:
        print(tr("Setup failed: {error}", error=(proc.stderr or proc.stdout).strip()[:400]))
        return 1
    print(tr("Task '{name}' registered: every {n} minutes, only while you are logged in, invisible.", name=TASK_NAME, n=minutes))
    print(aos_cmd(tr("Remove with: python -m aos uninstall-task")))
    return 0


def uninstall() -> int:
    if not _is_windows():
        print(tr("Not Windows: nothing to remove (delete the crontab line yourself)."))
        return 0
    proc = _powershell(
        f"if (Get-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -ErrorAction SilentlyContinue) "
        f"{{ Unregister-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Confirm:$false; 'removed' }} else {{ 'absent' }}"
    )
    print(tr("Task removed.") if "removed" in proc.stdout else tr("No task was registered."))
    return 0
