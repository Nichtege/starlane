"""Pulse: the scheduler. A `tick` checks all routines and starts whatever is due.

Safeguards (a broken routine must not burn the monthly budget overnight):
- daily cap per routine (`max_runs_per_day`)
- circuit breaker after `max_failures` failures in a row: the routine is blocked until `aos unblock <id>`
- time limit per run (`timeout_s`); the run is a separate process and is killed hard
- lock file: two concurrent ticks never start anything twice
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import INSTALLED, Config
from .routines import Routine, load_routines

LOCK_STALE_S = 75 * 60  # longer than the largest allowed routine time limit (60 min) plus a margin
MAX_LOG_LINES = 5000
KEEP_LOG_LINES = 2000
NOTE_LIMIT = 600
REPLACE_TRIES = 20  # 50 ms each
# Windows: start routine processes (and their git/claude) without a flashing console window; 0 elsewhere
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --- State ----------------------------------------------------------------------------
def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        for attempt in range(REPLACE_TRIES):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                # Windows: while a reader (server, `aos status`, Obsidian, browser) has the file open,
                # the replace fails. Wait briefly instead of failing the run.
                if attempt == REPLACE_TRIES - 1:
                    raise
                time.sleep(0.05)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_state(cfg: Config) -> dict:
    try:
        data = json.loads(cfg.state_file.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("routines"), dict):
            return data
    except FileNotFoundError:
        pass
    except ValueError:  # not valid JSON or not UTF-8
        # Do not silently overwrite a broken state file: all blocks and daily counters would be gone. Keep it aside.
        # Other read errors (file locked right now) propagate: better no tick than an empty state.
        try:
            os.replace(cfg.state_file, cfg.state_file.with_suffix(".json.bad"))
        except OSError:
            pass
    return {"routines": {}}


def save_state(cfg: Config, state: dict) -> None:
    atomic_write(cfg.state_file, json.dumps(state, indent=2, ensure_ascii=False))


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat(timespec="seconds") if dt else None


def _parse(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def append_run(cfg: Config, record: dict) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    with cfg.runs_log.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    try:
        lines = cfg.runs_log.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_LOG_LINES:
            atomic_write(cfg.runs_log, "\n".join(lines[-KEEP_LOG_LINES:]) + "\n")
    except OSError:
        pass


def read_runs(cfg: Config, limit: int = 200) -> list[dict]:
    try:
        lines = cfg.runs_log.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-limit:]:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


# --- Lock file -------------------------------------------------------------------------
class Busy(RuntimeError):
    pass


class TickLock:
    def __init__(self, path: Path, stale_s: int = LOCK_STALE_S):
        self.path, self.stale_s, self._fd = path, stale_s, None

    def __enter__(self) -> "TickLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self._fd, f"{os.getpid()} {time.time()}".encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale_s:
                        self.path.unlink()
                        continue
                except OSError:
                    continue
                raise Busy("another tick is running")
        raise Busy("could not acquire the lock file")

    def __exit__(self, *exc) -> None:
        if self._fd is not None:
            os.close(self._fd)
            try:
                self.path.unlink()
            except OSError:
                pass


# --- Running ----------------------------------------------------------------------------
def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the process with its children (e.g. git or claude started by a routine process)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
        return
    # The child leads its own process group (start_new_session in both Popen calls), so the group holds its children, too.
    # Killing only the child would leave `claude` running behind it, still holding the pipe, and communicate() would wait for it.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:  # no such group (not started with its own session) or already gone
        proc.kill()


def _own_session() -> bool:
    """Should a child lead its own session (POSIX)? Not when this process already does: a routine's process leads one, and
    a `claude` started by it stays in that group, so ending the routine's group ends claude, too."""
    if sys.platform == "win32":
        return False
    try:
        return os.getsid(0) != os.getpid()
    except (AttributeError, OSError):
        return True


def run_routine(cfg: Config, routine: Routine, trigger: str, slot: datetime | None, now: datetime) -> dict:
    """Starts the routine as a separate process and returns the run record."""
    # PYTHONSAFEPATH (and -P in Routine.argv): the working folder is never on sys.path, so no file there can
    # shadow a module; `aos` itself is found through PYTHONPATH
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONSAFEPATH="1")
    if not INSTALLED:  # installed: `aos` is in the interpreter's own site-packages (PYTHONPATH there would put all of it before the stdlib)
        package_root = str(Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = package_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if cfg.config_file:
        env["AOS_CONFIG"] = str(cfg.config_file)
    started = datetime.now().replace(microsecond=0)
    t0 = time.monotonic()
    status, rc, note = "ok", 0, ""
    try:
        proc = subprocess.Popen(
            routine.argv(),
            cwd=cfg.project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=NO_WINDOW,
            start_new_session=sys.platform != "win32",  # own process group: _kill_tree can end the whole tree
        )
        try:
            stdout, stderr = proc.communicate(timeout=routine.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.communicate()
            raise
        except KeyboardInterrupt:  # Ctrl+C in the terminal does not reach a process of its own session: stop it here
            _kill_tree(proc)
            raise
        rc = proc.returncode
        out = (stdout or "").strip() or (stderr or "").strip()
        note = out[-NOTE_LIMIT:]
        if rc != 0:
            status = "failed"
            note = ((stderr or "").strip() or out)[-NOTE_LIMIT:]
    except subprocess.TimeoutExpired:
        status, rc, note = "timeout", -1, f"Aborted after {routine.timeout_s} s"
    except OSError as exc:
        status, rc, note = "failed", -1, f"Could not start: {exc}"
    return {
        "id": routine.id,
        "trigger": trigger,
        "slot": _iso(slot),
        "started": _iso(started),
        "finished": _iso(datetime.now().replace(microsecond=0)),
        "duration_s": round(time.monotonic() - t0, 1),
        "status": status,
        "rc": rc,
        "note": note,
        "machine": cfg.machine,
    }


def _entry(state: dict, rid: str) -> dict:
    return state["routines"].setdefault(
        rid,
        {"last_slot": None, "last_start": None, "last_ok": None, "last_status": None, "last_note": "", "last_duration_s": None,
         "fail_streak": 0, "blocked": False, "day": None, "runs_today": 0},
    )


def _roll_day(entry: dict, today: date) -> None:
    if entry.get("day") != today.isoformat():
        entry["day"] = today.isoformat()
        entry["runs_today"] = 0


def _apply_result(entry: dict, rec: dict, routine: Routine) -> None:
    entry["last_start"] = rec["started"]
    entry["last_status"] = rec["status"]
    entry["last_note"] = rec["note"]
    entry["last_duration_s"] = rec["duration_s"]
    if rec["status"] == "ok":
        entry["last_ok"] = rec["finished"]
        entry["fail_streak"] = 0
        entry["blocked"] = False
    else:
        entry["fail_streak"] = entry.get("fail_streak", 0) + 1
        if entry["fail_streak"] >= routine.max_failures:
            entry["blocked"] = True


def tick(cfg: Config, now: datetime | None = None, routines: list[Routine] | None = None, runner=run_routine) -> list[dict]:
    """One pass. Returns the run records (including ones skipped because of the daily cap)."""
    now = now or datetime.now().replace(microsecond=0)
    routines = routines if routines is not None else load_routines(cfg.routines_file)
    results: list[dict] = []
    try:
        with TickLock(cfg.lock_file):
            state = load_state(cfg)
            for r in routines:
                entry = _entry(state, r.id)
                if not r.enabled or not r.runs_on(cfg.machine) or entry.get("blocked"):
                    continue
                _roll_day(entry, now.date())
                slot = r.schedule.due_slot(now, _parse(entry.get("last_slot")))
                if slot is None:
                    continue
                entry["last_slot"] = _iso(slot)
                if entry["runs_today"] >= r.max_runs_per_day:
                    rec = {"id": r.id, "trigger": "schedule", "slot": _iso(slot), "started": _iso(now), "finished": _iso(now),
                           "duration_s": 0, "status": "skipped", "rc": 0, "note": f"Daily cap of {r.max_runs_per_day} reached", "machine": cfg.machine}
                    entry["last_note"] = rec["note"]
                else:
                    entry["runs_today"] += 1
                    save_state(cfg, state)  # before the run: if the process dies midway, the daily count and slot are kept
                    rec = runner(cfg, r, "schedule", slot, now)
                    _apply_result(entry, rec, r)
                append_run(cfg, rec)
                results.append(rec)
                save_state(cfg, state)
            state["last_tick"] = _iso(now)  # sign of life of the scheduler, even if nothing was due
            save_state(cfg, state)
    except Busy:
        return []
    return results


class Refused(RuntimeError):
    """A run was refused (disabled, blocked, daily cap, other machine)."""


def run_now(cfg: Config, routine_id: str, routines: list[Routine] | None = None, runner=run_routine, respect_limits: bool = False) -> dict:
    """Manual run. `aos run <id>` ignores schedule, block and daily cap (the user decides).

    From the dashboard (network access, even if local only) `respect_limits=True` applies: disabled, blocked
    or capped routines are refused, otherwise any local process could start them endlessly."""
    routines = routines if routines is not None else load_routines(cfg.routines_file)
    found = next((r for r in routines if r.id == routine_id), None)
    if found is None:
        raise KeyError(f"Unknown routine: {routine_id}")
    now = datetime.now().replace(microsecond=0)
    with TickLock(cfg.lock_file):
        state = load_state(cfg)
        entry = _entry(state, found.id)
        _roll_day(entry, now.date())
        if respect_limits:
            if not found.enabled:
                raise Refused("Routine is disabled (enabled = false in routines.toml)")
            if not found.runs_on(cfg.machine):
                raise Refused(f"Routine only runs on: {', '.join(found.machine)}")
            if entry.get("blocked"):
                raise Refused("Routine is blocked, run `python -m aos unblock " + found.id + "` first")
            if entry["runs_today"] >= found.max_runs_per_day:
                raise Refused(f"Daily cap of {found.max_runs_per_day} reached")
        entry["runs_today"] += 1
        save_state(cfg, state)
        rec = runner(cfg, found, "manual", None, now)
        _apply_result(entry, rec, found)
        append_run(cfg, rec)
        save_state(cfg, state)
    return rec


def unblock(cfg: Config, routine_id: str) -> bool:
    """Lift a block. Under the tick lock, otherwise a running tick would overwrite the change."""
    with TickLock(cfg.lock_file):
        state = load_state(cfg)
        entry = state["routines"].get(routine_id)
        if not entry:
            return False
        entry["blocked"], entry["fail_streak"] = False, 0
        save_state(cfg, state)
    return True


# --- Display ----------------------------------------------------------------------------
def board(cfg: Config, now: datetime | None = None, routines: list[Routine] | None = None) -> list[dict]:
    """The routine board for the dashboard and the digest."""
    now = now or datetime.now().replace(microsecond=0)
    routines = routines if routines is not None else load_routines(cfg.routines_file)
    state = load_state(cfg)
    rows = []
    for r in routines:
        e = state["routines"].get(r.id, {})
        last_slot = _parse(e.get("last_slot"))
        pending = r.schedule.due_slot(now, last_slot)
        if not r.enabled:
            status = "disabled"
        elif not r.runs_on(cfg.machine):
            status = "elsewhere"
        elif e.get("blocked"):
            status = "blocked"
        elif e.get("last_status") in ("failed", "timeout"):
            status = "failed"
        elif e.get("last_status") is None:
            status = "never" if pending is None else "due"
        elif pending is not None and r.schedule.kind != "every" and now - pending > timedelta(minutes=30):
            status = "overdue"
        else:
            status = "ok"
        nd = r.schedule.next_due(now, last_slot) if status not in ("disabled", "elsewhere", "blocked") else None
        rows.append(
            {
                "id": r.id,
                "description": r.description,
                "schedule": r.schedule_text,
                "machine": ", ".join(r.machine),
                "enabled": r.enabled,
                "status": status,
                "last_run": e.get("last_start"),
                "last_ok": e.get("last_ok"),
                "last_note": e.get("last_note", ""),
                "last_duration_s": e.get("last_duration_s"),
                "next_due": _iso(nd),
                "fail_streak": e.get("fail_streak", 0),
                "runs_today": e.get("runs_today", 0) if e.get("day") == now.date().isoformat() else 0,
                "cap": r.max_runs_per_day,
                "max_failures": r.max_failures,
            }
        )
    return rows
