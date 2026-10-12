"""Date helpers: weekday names, ISO weeks, finding dates in notes.

The names below are English, the source language; `weekday_name`, `fmt_day`, `fmt_date` and `fmt_full` translate them
(aos/i18n.py), so a German interface writes "Di 6.10." where an English one writes "Tue 6 Oct".
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .i18n import tr, tr_mark, trc

WEEKDAYS = [tr_mark("Monday"), tr_mark("Tuesday"), tr_mark("Wednesday"), tr_mark("Thursday"), tr_mark("Friday"),
            tr_mark("Saturday"), tr_mark("Sunday")]
WD_SHORT = [tr_mark("Mon"), tr_mark("Tue"), tr_mark("Wed"), tr_mark("Thu"), tr_mark("Fri"), tr_mark("Sat"), tr_mark("Sun")]
MONTHS = [tr_mark("Jan"), tr_mark("Feb"), tr_mark("Mar"), tr_mark("Apr"), tr_mark("May"), tr_mark("Jun"), tr_mark("Jul"),
          tr_mark("Aug"), tr_mark("Sep"), tr_mark("Oct"), tr_mark("Nov"), tr_mark("Dec")]
_DE_WEEKDAYS = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")
# Weekday token -> Monday=0: English names and abbreviations, German names and abbreviations (a German vault keeps working)
_WD_INDEX = {**{n.lower(): i for i, n in enumerate(WD_SHORT)}, **{n: i for i, n in enumerate(("mo", "di", "mi", "do", "fr", "sa", "so"))},
             **{n: i for i, n in enumerate(_DE_WEEKDAYS)}}

MAX_YEAR_GUESS_DAYS = 183  # without a year, only dates at most half a year away from today count

_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_FULL_RE = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})\b")
# Day.month with a weekday in front. Excluded: a year right after (then the explicit year wins), decimals
# ("Tue 6.10.5") and units ("Thu 1.10 h", "Sun 2.5 million").
_WD_RE = re.compile(
    r"\b(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag"
    r"|Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?"
    r"|Mo|Di|Mi|Do|Fr|Sa|So)\.?,?\s+(\d{1,2})\.\s?(\d{1,2})\b(?!\.?\s?20\d{2})(?!\.\d)"
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
    """All dates in a line: '2026-11-10', '10.11.2026', 'Tue 6.10.', 'Dienstag, 6.10.' (weekday + day.month)."""
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
        wd = _WD_INDEX[token if token in _WD_INDEX else token[:3]]
        matching = [c for c in _nearest_year(int(m.group(2)), int(m.group(3)), today) if c.weekday() == wd]
        if matching:
            found.add(min(matching, key=lambda c: abs((c - today).days)))
    return sorted(found)


def days_until(target: date, today: date) -> int:
    return (target - today).days


def countdown_text(target: date, today: date) -> str:
    n = days_until(target, today)
    if n == 0:
        return tr("today")
    if n == 1:
        return tr("tomorrow")
    if n == -1:
        return tr("yesterday")
    return tr("in {n} days", n=n) if n > 0 else tr("{n} days ago", n=-n)


def weekday_name(d: date) -> str:
    """'Tuesday' (translated)"""
    return tr(WEEKDAYS[d.weekday()])


def date_parts(d: date) -> dict:
    """What a date pattern may use: {wd} short weekday, {d} day, {m} month number, {mon} short month name, {y} year."""
    return {"wd": tr(WD_SHORT[d.weekday()]), "d": d.day, "m": d.month, "mon": tr(MONTHS[d.month - 1]), "y": d.year}


def fmt_day(d: date) -> str:
    """'6 Oct' (German '6.10.')"""
    return trc("date", "{d} {mon}", **date_parts(d))


def fmt_date(d: date) -> str:
    """'Tue 6 Oct' (German 'Di 6.10.')"""
    return trc("date", "{wd} {d} {mon}", **date_parts(d))


def fmt_full(d: date) -> str:
    """'Tue 6 Oct 2026' (German 'Di 6.10.2026')"""
    return trc("date", "{wd} {d} {mon} {y}", **date_parts(d))


def now_local() -> datetime:
    return datetime.now().replace(microsecond=0)
