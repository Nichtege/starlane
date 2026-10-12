"""Date helpers: weekday names, ISO weeks, finding dates in notes."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WD_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
# Weekday prefix -> Monday=0. English names and abbreviations, plus the German abbreviations so a German vault keeps working.
_WD_INDEX = {**{n.lower(): i for i, n in enumerate(WD_SHORT)}, **{n: i for i, n in enumerate(("mo", "di", "mi", "do", "fr", "sa", "so"))}}

MAX_YEAR_GUESS_DAYS = 183  # without a year, only dates at most half a year away from today count

_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_FULL_RE = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})\b")
# Day.month with a weekday in front. Excluded: a year right after (then the explicit year wins), decimals
# ("Tue 6.10.5") and units ("Thu 1.10 h", "Sun 2.5 million").
_WD_RE = re.compile(
    r"\b(Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?"
    r"|Mo|Di|Mi|Do|Fr|Sa|So)\.?\s+(\d{1,2})\.\s?(\d{1,2})\b(?!\.?\s?20\d{2})(?!\.\d)"
    r"(?!\s*(?:h\b|hrs?\b|min\b|sec\b|pages?\b|p\.|million|bn\b|percent|%|€|\$|Uhr|Mio|Mrd|Prozent|Min|Sek|Seiten|S\.))\.?"
)


def iso_week_name(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_bounds(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def parse_iso(value: str) -> date | None:
    m = _ISO_RE.fullmatch((value or "").strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _nearest_year(day: int, month: int, today: date) -> list[date]:
    """No year given ('Tue 6.10.'): candidates from last year, this year and next year."""
    cands = [_safe_date(y, month, day) for y in (today.year - 1, today.year, today.year + 1)]
    return [c for c in cands if c and abs((c - today).days) <= MAX_YEAR_GUESS_DAYS]


def find_dates(text: str, today: date) -> list[date]:
    """All dates in a line: '2026-11-10', '10.11.2026', 'Tue 6.10.' (weekday + day.month)."""
    found: set[date] = set()
    for m in _ISO_RE.finditer(text):
        d = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            found.add(d)
    for m in _FULL_RE.finditer(text):
        d = _safe_date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d:
            found.add(d)
    for m in _WD_RE.finditer(text):
        # The weekday has to match the date: that filters out chance hits and decides the year.
        token = m.group(1).lower()
        wd = _WD_INDEX[token[:3] if len(token) > 2 else token]
        matching = [c for c in _nearest_year(int(m.group(2)), int(m.group(3)), today) if c.weekday() == wd]
        if matching:
            found.add(min(matching, key=lambda c: abs((c - today).days)))
    return sorted(found)


def days_until(target: date, today: date) -> int:
    return (target - today).days


def countdown_text(target: date, today: date) -> str:
    n = days_until(target, today)
    if n == 0:
        return "today"
    if n == 1:
        return "tomorrow"
    if n == -1:
        return "yesterday"
    return f"in {n} days" if n > 0 else f"{-n} days ago"


def fmt_day(d: date) -> str:
    """'6 Oct'"""
    return f"{d.day} {MONTHS[d.month - 1]}"


def fmt_date(d: date) -> str:
    """'Tue 6 Oct'"""
    return f"{WD_SHORT[d.weekday()]} {fmt_day(d)}"


def now_local() -> datetime:
    return datetime.now().replace(microsecond=0)
