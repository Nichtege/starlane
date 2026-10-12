"""Pulse: routines from routines.toml.

Safety rule: a routine only names a *known command name* (whitelist below), never a shell command.
So even a tampered routines.toml cannot start anything arbitrary.
"""

from __future__ import annotations

import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

# command name -> arguments for `python -m aos ...`
ALLOWED_COMMANDS: dict[str, list[str]] = {
    "digest": ["digest"],
    "mapcheck": ["mapcheck"],
    "dashboard": ["dashboard"],
    "git-pull": ["git-pull"],
    "claude-digest": ["claude-digest"],
    "skill": ["skill"],  # also needs `skill = "<id>"` in routines.toml (and optionally instruction/model/effort)
}
SKILL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,34}$")
MAX_INSTRUCTION = 4000
SKILL_MIN_TIMEOUT_S = 960  # = agents.MAX_TIMEOUT_S + 60: the outer timer must never fire before the skill run's own limit

# English names; the German ones are accepted too so existing routines.toml files keep working
_WEEKDAY_NAMES = {
    "mon": 0, "monday": 0, "mo": 0, "montag": 0,
    "tue": 1, "tuesday": 1, "di": 1, "dienstag": 1,
    "wed": 2, "wednesday": 2, "mi": 2, "mittwoch": 2,
    "thu": 3, "thursday": 3, "do": 3, "donnerstag": 3,
    "fri": 4, "friday": 4, "fr": 4, "freitag": 4,
    "sat": 5, "saturday": 5, "sa": 5, "samstag": 5,
    "sun": 6, "sunday": 6, "so": 6, "sonntag": 6,
}


class RoutineError(ValueError):
    """Error in routines.toml (a message the user can act on)."""


@dataclass(frozen=True)
class Schedule:
    kind: str  # every | daily | weekly
    interval: timedelta | None = None
    hour: int = 0
    minute: int = 0
    weekdays: tuple[int, ...] = ()

    @classmethod
    def parse(cls, text: str) -> "Schedule":
        t = (text or "").strip().lower()
        m = re.fullmatch(r"every\s+(\d+)\s*(s|m|h)", t)
        if m:
            n = int(m.group(1))
            if n <= 0:
                raise RoutineError(f"Interval must be greater than 0: '{text}'")
            unit = {"s": "seconds", "m": "minutes", "h": "hours"}[m.group(2)]
            interval = timedelta(**{unit: n})
            if interval < timedelta(minutes=1):
                raise RoutineError(f"The smallest interval is 1 minute: '{text}'")
            return cls("every", interval=interval)
        m = re.fullmatch(r"daily\s+(\d{1,2}):(\d{2})", t)
        if m:
            return cls("daily", hour=_hour(m.group(1), text), minute=_minute(m.group(2), text))
        m = re.fullmatch(r"weekly\s+([a-z,\s]+?)\s+(\d{1,2}):(\d{2})", t)
        if m:
            days = []
            for name in filter(None, re.split(r"[,\s]+", m.group(1).strip())):
                if name not in _WEEKDAY_NAMES:
                    raise RoutineError(f"Unknown weekday '{name}' in '{text}'")
                days.append(_WEEKDAY_NAMES[name])
            return cls("weekly", hour=_hour(m.group(2), text), minute=_minute(m.group(3), text), weekdays=tuple(sorted(set(days))))
        raise RoutineError(f"Unknown schedule '{text}'. Allowed: 'every 5m', 'daily 06:30', 'weekly mon,thu 08:00'")

    def _slot_on(self, day: datetime) -> datetime:
        return day.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)

    def _valid_day(self, day: datetime) -> bool:
        return self.kind == "daily" or day.weekday() in self.weekdays

    def latest_slot(self, now: datetime) -> datetime | None:
        """Most recent slot <= now (daily/weekly only)."""
        if self.kind == "every":
            return None
        for back in range(0, 9):
            day = now - timedelta(days=back)
            slot = self._slot_on(day)
            if self._valid_day(day) and slot <= now:
                return slot
        return None

    def next_slot(self, after: datetime) -> datetime | None:
        if self.kind == "every":
            return None
        for ahead in range(0, 9):
            day = after + timedelta(days=ahead)
            slot = self._slot_on(day)
            if self._valid_day(day) and slot > after:
                return slot
        return None

    def due_slot(self, now: datetime, last_slot: datetime | None) -> datetime | None:
        """Returns the slot that has to be handled now, else None. Missed slots run once afterwards."""
        if self.kind == "every":
            # Small slack: the scheduler only ticks roughly every 5 minutes, otherwise "every 15m" would become 20 minutes.
            slack = min(timedelta(seconds=60), self.interval / 5)
            if last_slot is None or now - last_slot >= self.interval - slack:
                return now
            return None
        latest = self.latest_slot(now)
        if latest and (last_slot is None or latest > last_slot):
            return latest
        return None

    def next_due(self, now: datetime, last_slot: datetime | None) -> datetime | None:
        if self.kind == "every":
            return now if last_slot is None else max(now, last_slot + self.interval)
        if self.due_slot(now, last_slot):
            return now
        return self.next_slot(now)


def _int(item: dict, key: str, default: int, rid: str) -> int:
    value = item.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutineError(f"Routine {rid}: `{key}` must be an integer, not {value!r}")
    return value


def _hour(v: str, text: str) -> int:
    h = int(v)
    if not 0 <= h <= 23:
        raise RoutineError(f"Hour outside 0-23 in '{text}'")
    return h


def _minute(v: str, text: str) -> int:
    m = int(v)
    if not 0 <= m <= 59:
        raise RoutineError(f"Minute outside 0-59 in '{text}'")
    return m


@dataclass(frozen=True)
class Routine:
    id: str
    description: str
    schedule_text: str
    schedule: Schedule
    command: str
    machine: tuple[str, ...]
    enabled: bool
    timeout_s: int
    max_runs_per_day: int
    max_failures: int
    skill: str = ""  # only for command = "skill"
    instruction: str = ""
    model: str = ""
    effort: str = ""

    def runs_on(self, machine: str) -> bool:
        return "any" in self.machine or machine.casefold() in self.machine

    def argv(self) -> list[str]:
        safe = ["-P"] if sys.version_info >= (3, 11) else []  # -P: the working folder is not put on sys.path
        argv = [sys.executable, *safe, "-m", "aos", *ALLOWED_COMMANDS[self.command]]
        if self.command == "skill":
            argv += ["--via", "routine"]
            if self.model:
                argv += ["--model", self.model]
            if self.effort:
                argv += ["--effort", self.effort]
            argv += ["--", self.skill, self.instruction]  # after "--": a task starting with "-" is never an option
        return argv


def load_routines(path: Path) -> list[Routine]:
    if not Path(path).is_file():
        raise RoutineError(f"routines.toml not found: {path}")
    with Path(path).open("rb") as fh:
        try:
            raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise RoutineError(f"routines.toml is not valid TOML: {exc}") from exc
    out: list[Routine] = []
    seen: set[str] = set()
    for i, item in enumerate(raw.get("routine", []), start=1):
        rid = str(item.get("id", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9\-]{0,40}", rid):
            raise RoutineError(f"Routine {i}: `id` missing or invalid (only a-z, 0-9, hyphen): '{rid}'")
        if rid in seen:
            raise RoutineError(f"Duplicate routine id: {rid}")
        seen.add(rid)
        command = str(item.get("command", rid))
        if command not in ALLOWED_COMMANDS:
            raise RoutineError(f"Routine {rid}: command '{command}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}")
        skill = instruction = model = effort = ""
        if command == "skill":
            from .skills import EFFORTS, MODELS  # imported late: skills.py does not need routines

            skill = str(item.get("skill", "")).strip()
            instruction = str(item.get("instruction", "")).strip()
            model = str(item.get("model", "")).strip().lower()
            effort = str(item.get("effort", "")).strip().lower()
            if not SKILL_ID_RE.match(skill):
                raise RoutineError(f"Routine {rid}: `skill` missing or invalid (only a-z, 0-9, hyphen): '{skill}'")
            if not instruction or len(instruction) > MAX_INSTRUCTION:
                raise RoutineError(f"Routine {rid}: `instruction` missing or longer than {MAX_INSTRUCTION} characters")
            if model and model not in MODELS:
                raise RoutineError(f"Routine {rid}: `model` '{model}' not allowed. Allowed: {', '.join(MODELS)}")
            if effort and effort not in EFFORTS:
                raise RoutineError(f"Routine {rid}: `effort` '{effort}' not allowed. Allowed: {', '.join(EFFORTS)}")
        machine = item.get("machine", "any")
        machines = tuple(m.casefold() for m in ([machine] if isinstance(machine, str) else machine))
        sched_text = str(item.get("schedule", ""))
        try:
            schedule = Schedule.parse(sched_text)
        except RoutineError as exc:
            raise RoutineError(f"Routine {rid}: {exc}") from exc
        out.append(
            Routine(
                id=rid,
                description=str(item.get("description", "")),
                schedule_text=sched_text,
                schedule=schedule,
                command=command,
                machine=machines,
                enabled=bool(item.get("enabled", True)),
                timeout_s=max(SKILL_MIN_TIMEOUT_S if command == "skill" else 5,
                              min(_int(item, "timeout_s", SKILL_MIN_TIMEOUT_S if command == "skill" else 120, rid), 3600)),
                max_runs_per_day=max(1, _int(item, "max_runs_per_day", 24, rid)),
                max_failures=max(1, _int(item, "max_failures", 3, rid)),
                skill=skill,
                instruction=instruction,
                model=model,
                effort=effort,
            )
        )
    return out
