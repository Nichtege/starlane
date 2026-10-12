"""Pulse: the morning digest. Reads the vault and writes `<digest dir>/latest.md` (only there, never into your notes).

The file names come from `[digest]` (file, archive, review); the text is in the interface language (aos/i18n.py)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from . import vault as V
from .config import Config, Conventions
from .dates import (countdown_text, date_parts, find_dates, fmt_date, fmt_day, fmt_full, iso_week_name, parse_iso, week_bounds,
                    weekday_name)
from .i18n import tr, tr_mark, trc, trn
from .mapcheck import count_text, redact
from .scheduler import atomic_write
from .vault import Vault
from .vault import strip_markup as _strip_markup

LOG_LINE_RE = re.compile(r"^\s*[-*]\s+(?:\*\*)?\d{1,2}\.\d{1,2}\.(?:\d{2,4})?(?:\*\*)?\s*[:–-]")
MAX_EVENTS = 25
BULK_CHANGE_MIN = 5
_DEFAULT = Conventions()  # the file names ([digest] file, archive, review) live in Conventions too
# Routine status codes (scheduler.board) as the generated notes show them: trc("routine", status)
ROUTINE_STATUS = (tr_mark("ok", "routine"), tr_mark("due", "routine"), tr_mark("overdue", "routine"), tr_mark("failed", "routine"),
                  tr_mark("blocked", "routine"), tr_mark("never", "routine"), tr_mark("disabled", "routine"),
                  tr_mark("elsewhere", "routine"))


def strip_markup(text: str, limit: int = 160) -> str:
    """Prepare note text for the digest; credentials noted by accident are redacted on the way."""
    return redact(_strip_markup(text, limit))


def _log_section_re(conv: Conventions) -> re.Pattern:
    """Headings of sections whose dates are history (log, results), not appointments."""
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in conv.log_words) + r")\b", re.I)


# --- Building blocks --------------------------------------------------------------------
def deadlines(vault: Vault, today: date, conv: Conventions = _DEFAULT) -> list[dict]:
    out = []
    for note in vault.md_notes():
        if str(note.fm.get(conv.type_key)) != conv.type_project or str(note.fm.get(conv.status_key)) == conv.status_done:
            continue
        d = parse_iso(str(note.fm.get(conv.deadline_key, "")))
        if d:
            out.append(
                {
                    "path": note.rel,
                    "title": note.title,
                    "date": d.isoformat(),
                    "days": (d - today).days,
                    "text": tr("{title}: {date}, {countdown}", title=note.title, date=fmt_full(d), countdown=countdown_text(d, today)),
                }
            )
    return sorted(out, key=lambda x: x["date"])


def week_goals(vault: Vault, today: date, conv: Conventions = _DEFAULT) -> dict:
    rel = conv.week_note(today)
    note = vault.get(rel)
    if not note:
        return {"path": rel, "exists": False, "goals": [], "empty": True}
    goals = []
    for line_no, line in V.section(note, conv.week_goal_heading):
        m = re.match(r"^\s*[-*]\s+\[([ xX])\]\s*(.*)$", line)
        if m and m.group(2).strip():
            goals.append({"done": m.group(1).lower() == "x", "text": strip_markup(m.group(2)), "line": line_no})
        elif re.match(r"^\s*[-*]\s+\S", line) and not re.match(r"^\s*[-*]\s+\[", line):
            goals.append({"done": False, "text": strip_markup(line), "line": line_no})
    return {"path": rel, "exists": True, "goals": goals, "empty": not goals}


def _is_open_item(line: str) -> bool:
    return "~~" not in line and not re.search(r"\[[xX]\]", line)


def upcoming(vault: Vault, today: date, horizon: int, conv: Conventions = _DEFAULT) -> list[dict]:
    """Lines from project, area and week notes whose date falls within the next `horizon` days."""
    end = today + timedelta(days=horizon)
    areas = tuple(f"{d}/" for d in (conv.projects_dir, conv.areas_dir, conv.journal_dir))
    log_section_re = _log_section_re(conv)
    seen: set[tuple[str, str]] = set()
    events: list[dict] = []
    for note in vault.md_notes():
        if not note.rel.startswith(areas) or conv.is_template(note.rel) or note.size > 100_000:
            continue
        in_log_section = False
        for line_no, line in note.body_lines():
            if line.startswith("#"):
                in_log_section = bool(log_section_re.search(line))
            if in_log_section or LOG_LINE_RE.match(line):
                continue
            if not re.match(r"^\s*(?:[-*]|#{2,4})\s", line) or not _is_open_item(line):
                continue
            dates = find_dates(line, today)
            if not dates:
                continue
            d = next((x for x in dates if today <= x <= end), None)
            if d is None:
                continue
            text = strip_markup(re.sub(r"^\s*(?:[-*]\s+(?:\[ \]\s*)?|#{2,4}\s+)", "", line))
            key = (d.isoformat(), re.sub(r"\W+", "", text.lower())[:60])
            if key in seen or not text:
                continue
            seen.add(key)
            events.append({"date": d.isoformat(), "days": (d - today).days, "text": text, "path": note.rel, "line": line_no})
    events.sort(key=lambda e: (e["date"], e["path"], e["line"]))
    return events[:MAX_EVENTS]


def _section_window(heading: str, today: date) -> tuple[date, date] | None:
    dates = find_dates(heading, today)
    if not dates:
        return None
    start = dates[0]
    end = dates[-1] if len(dates) > 1 else start + timedelta(days=6)
    return start, end


def plan_tasks(vault: Vault, today: date, conv: Conventions = _DEFAULT) -> dict:
    """Open checkboxes from schedule notes, split into 'this week' and 'overdue'."""
    current, overdue = [], []
    keyword = conv.schedule_keyword.lower()
    for note in vault.md_notes():
        if keyword not in note.rel.lower():
            continue
        window, window_level = None, 0
        for line_no, line in note.body_lines():
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                found = _section_window(line, today)
                if found is not None:
                    window, window_level = found, level
                elif level <= window_level:
                    window, window_level = None, 0  # a heading of the same level without a date ends the window
                continue
            m = re.match(r"^\s*[-*]\s+\[ \]\s+(.*)$", line)
            if not m or window is None or "~~" in line:
                continue
            item = {"text": strip_markup(m.group(1), 140), "path": note.rel, "line": line_no}
            if window[0] <= today <= window[1]:
                current.append(item)
            elif window[1] < today:
                overdue.append({**item, "since": window[1].isoformat(), "days": (today - window[1]).days})
    return {"current": current, "overdue": overdue}


def weekly_review_open(vault: Vault, today: date, conv: Conventions = _DEFAULT) -> dict | None:
    """Rule from CLAUDE.md: on Sunday the current week's review, otherwise last week's; if it is empty, say so honestly."""
    ref = today if today.weekday() == 6 else today - timedelta(days=7)
    prev = vault.get(conv.week_note(ref))
    if not prev:
        return None
    body = [ln.strip() for _, ln in V.section(prev, conv.weekly_review_heading) if ln.strip()]
    real = [ln for ln in body if not (ln.startswith("_") and ln.endswith("_"))]
    if real:
        return None
    return {"path": prev.rel, "text": tr("{heading} of {week} is still empty: rate honestly what was achieved",
                                         heading=conv.weekly_review_heading, week=prev.stem)}


def inbox_items(vault: Vault, conv: Conventions = _DEFAULT) -> list[dict]:
    items = []
    prefix = conv.inbox_dir + "/"
    for note in vault.md_notes():
        if not note.rel.startswith(prefix):
            continue
        if note.stem.lower() != "readme":
            items.append({"path": note.rel, "text": note.title})
            continue
        for line_no, line in note.body_lines():
            if re.match(r"^\s*[-*]\s+\S", line):
                items.append({"path": note.rel, "line": line_no, "text": strip_markup(re.sub(r"^\s*[-*]\s+", "", line))})
    return items


def idea_quicklist(vault: Vault, conv: Conventions = _DEFAULT) -> int:
    note = vault.get(f"{conv.ideas_dir}/README.md")
    if not note:
        return 0
    lines = V.section(note, conv.ideas_quick_heading)
    return sum(1 for _, ln in lines if re.match(r"^\s*[-*]\s+\S", ln) and not re.match(r"^\s*[-*]\s+_", ln))


def _stamp(ts: float) -> str:
    dt = datetime.fromtimestamp(ts)
    return f"{fmt_day(dt.date())} {dt:%H:%M}"


def recent_changes(vault: Vault, now: datetime, hours: int = 36, limit: int = 10, conv: Conventions = _DEFAULT) -> list[dict]:
    """Recently changed notes. Many files in the same minute are a git sync, not work: one line."""
    cutoff = (now - timedelta(hours=hours)).timestamp()
    rows = [(n.mtime, n) for n in vault.notes.values() if n.mtime >= cutoff and not conv.is_generated(n.rel) and not n.rel.startswith("CLAUDE.md")]
    rows.sort(key=lambda r: r[0], reverse=True)
    groups: dict[str, list] = {}
    for mtime, n in rows:
        groups.setdefault(_stamp(mtime), []).append(n)
    out: list[dict] = []
    for when, notes in groups.items():
        if len(notes) > BULK_CHANGE_MIN:
            out.append({"path": "", "title": tr("{n} files at the same time (sync/git)", n=len(notes)), "time": when, "bulk": len(notes)})
        else:
            out += [{"path": n.rel, "title": n.title, "time": when} for n in notes]
    return out[:limit]


def last_sessions(vault: Vault, limit: int = 3, conv: Conventions = _DEFAULT) -> list[dict]:
    sessions = [n for n in vault.md_notes() if n.rel.startswith(conv.sessions_dir + "/")]
    sessions.sort(key=lambda n: (str(n.fm.get(conv.created_key, "")), n.rel), reverse=True)
    return [{"path": n.rel, "title": n.title} for n in sessions[:limit]]


def has_project_note(vault: Vault, conv: Conventions = _DEFAULT) -> bool:
    return bool(conv.project_note) and f"{conv.project_note}.md" in vault.notes


# --- The whole picture ------------------------------------------------------------------
def build_today(vault: Vault, cfg: Config, today: date, now: datetime, health: dict, board: list[dict] | None = None) -> dict:
    conv = cfg.conv
    goals = week_goals(vault, today, conv)
    plan = plan_tasks(vault, today, conv)
    needs: list[dict] = []
    if not goals["exists"]:
        needs.append({"kind": "warn", "text": tr("Week note {week} is missing", week=iso_week_name(today)), "path": goals["path"]})
    elif goals["empty"]:
        needs.append({"kind": "warn", "text": tr("No weekly goal set: without a goal there is nothing to review"), "path": goals["path"]})
    review = weekly_review_open(vault, today, conv)
    if review and today.weekday() in (6, 0):
        needs.append({"kind": "warn", "text": review["text"], "path": review["path"]})
    elif review:
        needs.append({"kind": "info", "text": review["text"], "path": review["path"]})
    for t in plan["overdue"][:8]:
        since = date.fromisoformat(t["since"])
        needs.append({"kind": "warn", "text": tr("Overdue since {day}: {text}", day=fmt_day(since), text=t["text"]), "path": t["path"], "line": t["line"]})
    for t in plan["current"][:12]:
        needs.append({"kind": "task", "text": t["text"], "path": t["path"], "line": t["line"]})
    inbox = inbox_items(vault, conv)
    if inbox:
        needs.append({"kind": "info", "text": trn(len(inbox), "Inbox: {n} item to sort", "Inbox: {n} items to sort"), "path": f"{conv.inbox_dir}/README.md"})
    ideas = idea_quicklist(vault, conv)
    if ideas > 10:
        needs.append({"kind": "info", "text": tr("The ideas quick list has {n} entries: work them out or drop some?", n=ideas), "path": f"{conv.ideas_dir}/README.md"})
    if health["counts"]["error"]:
        needs.append({"kind": "warn", "text": trn(health["counts"]["error"], "Vault check: {n} error", "Vault check: {n} errors"),
                      "path": f"{cfg.digest_dir}/vault-check.md"})
    for r in board or []:
        if r["status"] in ("failed", "blocked"):
            needs.append({"kind": "warn", "text": tr("Routine `{id}` {status}: {note}", id=r["id"], status=trc("routine", r["status"]),
                                                     note=(r.get("last_note") or "")[:100]), "path": ""})
    start, end = week_bounds(today)
    return {
        "date": today.isoformat(),
        "weekday": weekday_name(today),
        "week": iso_week_name(today),
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "generated": now.isoformat(timespec="minutes"),
        "horizon_days": cfg.horizon_days,
        "has_project_note": has_project_note(vault, conv),
        "deadlines": deadlines(vault, today, conv),
        "week_goals": goals,
        "upcoming": upcoming(vault, today, cfg.horizon_days, conv),
        "needs": needs,
        "recent": recent_changes(vault, now, conv=conv),
        "sessions": last_sessions(vault, conv=conv),
        "health": {"counts": health["counts"], "stats": health["stats"]},
        "routines": [{k: r.get(k) for k in ("id", "status", "last_run", "next_due")} for r in (board or [])],
    }


# --- Markdown ---------------------------------------------------------------------------
def _link(path: str) -> str:
    if not path:
        return ""
    name = path[:-3] if path.endswith(".md") else path
    return f"[[{name}|{Path(name).name}]]"


def _header(d: dict, tags: str, title: str, info: str, conv: Conventions = _DEFAULT) -> list[str]:
    """Frontmatter + heading. The project link (rule from CLAUDE.md) only when the project note exists."""
    linked = d.get("has_project_note", True) and bool(conv.project_note)
    out = ["---", f"{conv.type_key}: {conv.type_digest}", f"{conv.created_key}: {d['date']}"]
    if linked:
        out.append(f'{conv.project_key}: "[[{conv.project_note}]]"')
    out += [f"{conv.tags_key}: [{tags}]", "---", title, ""]
    out.append((f"{conv.belongs_to} [[{conv.project_note}]] · " if linked else "") + info)
    out.append("")
    return out


def render_markdown(d: dict, conv: Conventions = _DEFAULT) -> str:
    dt = date.fromisoformat(d["date"])
    title = tr("Digest {weekday}, {date}", weekday=d["weekday"], date=trc("date", "{d} {mon} {y}", **date_parts(dt)))
    info = tr("Week {week} · {stamp} · generated by `aos digest`, do not edit by hand", week=d["week"], stamp=_stamp_text(d["generated"][11:16]))
    out = _header(d, "digest, auto", "# " + title, info, conv)
    if d["deadlines"]:
        out += ["## " + tr("Deadlines")]
        out += [f"- {x['text']} · {_link(x['path'])}" for x in d["deadlines"]]
        out.append("")
    g = d["week_goals"]
    out += [f"## {conv.week_goal_heading}"]
    if g["goals"]:
        out += [f"- [{'x' if x['done'] else ' '}] {x['text']}" for x in g["goals"]]
    elif g["exists"]:
        out.append(f"- _{tr('None set yet')}_ → {_link(g['path'])}")
    else:
        out.append(f"- _{tr('Week note {week} does not exist yet', week=d['week'])}_")
    out.append("")
    out += ["## " + tr("Needs you")]
    if d["needs"]:
        icon = {"warn": "⚠️", "task": "☐", "info": "ℹ️"}
        for n in d["needs"]:
            link = f" → {_link(n['path'])}" if n.get("path") else ""
            out.append(f"- {icon.get(n['kind'], '•')} {n['text']}{link}")
    else:
        out.append("- " + tr("Nothing open."))
    out.append("")
    out += ["## " + tr("Next {n} days", n=d.get("horizon_days", 14))]
    if d["upcoming"]:
        last = None
        for e in d["upcoming"]:
            ed = date.fromisoformat(e["date"])
            head = "" if e["date"] == last else f"**{fmt_date(ed)}** ({countdown_text(ed, dt)}) "
            last = e["date"]
            out.append(f"- {head}{e['text']} → {_link(e['path'])}")
    else:
        out.append("- " + tr("No dated entries found."))
    out.append("")
    if d["recent"]:
        out += ["## " + tr("Recently changed")]
        out += [f"- {r['time']} · {_link(r['path']) if r['path'] else r['title']}" for r in d["recent"]]
        out.append("")
    if d["sessions"]:
        out += ["## " + tr("Recent sessions")]
        out += [f"- [[{s['path'][:-3]}|{s['title']}]]" for s in d["sessions"]]
        out.append("")
    h = d["health"]
    out += [
        "## " + tr("Vault health"),
        "- " + tr("{counts} · {pct} % of all notes at most 2 hops from the entry points", counts=count_text(h["counts"]),
                  pct=h["stats"]["within_two_hops_pct"]),
        "- " + tr("Details: {link}", link=f"[[{conv.digest_dir}/vault-check|{tr('Vault check')}]]"),
        "",
    ]
    if d["routines"]:
        out += ["## " + tr("Routines")]
        for r in d["routines"]:
            last = tr(", last run {when}", when=r["last_run"][5:16].replace("T", " ")) if r.get("last_run") else ""
            out.append(f"- `{r['id']}`: {trc('routine', r['status'])}{last}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_health_markdown(health: dict, today: date, now: datetime, has_project_note: bool = True, conv: Conventions = _DEFAULT) -> str:
    sev = {"error": tr("Errors"), "warn": tr("Warnings"), "info": tr("Notices")}
    c, s = health["counts"], health["stats"]
    out = _header({"date": today.isoformat(), "has_project_note": has_project_note}, "digest, auto, check", "# " + tr("Vault check"),
                  tr("{stamp} · generated by `aos mapcheck`", stamp=_stamp_text(now.strftime("%H:%M"), start=True)), conv)
    out += [
        tr("{counts} · {near} of {scored} notes at most 2 hops from the entry points ({pct} %)", counts=count_text(c, " · "),
           near=s["within_two_hops"], scored=s["scored"], pct=s["within_two_hops_pct"]),
        "",
    ]
    for level in ("error", "warn", "info"):
        items = [i for i in health["issues"] if i["severity"] == level]
        if not items:
            continue
        out += [f"## {sev[level]} ({len(items)})"]
        for i in items:
            is_md = i["path"].endswith(".md")
            where = f"[[{i['path'][:-3]}]]" if is_md else f"`{i['path']}`"
            line = f":{i['line']}" if i["line"] else ""
            message = i["message"].replace("[[", "⟦").replace("]]", "⟧")  # examples in the text must not become real links
            out.append(f"- `{i['code']}` {where}{line}: {message}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _stamp_text(hhmm: str, start: bool = False) -> str:
    """'as of 06:30' (German 'Stand 06:30'); `start`: capitalised, at the start of a line. write_if_changed ignores it."""
    text = tr("as of {time}", time=hhmm)
    return text[:1].upper() + text[1:] if start else text


# --- Writing ----------------------------------------------------------------------------
def _stamp_re() -> re.Pattern:
    """The time stamp in the current language and in English: a file in which only the time changed is not rewritten."""
    forms = {tr("as of {time}"), "as of {time}"}
    pats = [re.escape(f).replace(re.escape("{time}"), r"\d{2}:\d{2}") for f in forms]
    return re.compile("(?i)" + "|".join(sorted(pats, key=len, reverse=True)))


def write_if_changed(path: Path, text: str) -> bool:
    """Write atomically, but only if something other than the time changed (no needless git changes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        old = path.read_text(encoding="utf-8", errors="replace")  # saved by hand in another encoding: simply rewrite
        stamp = _stamp_re()
        if stamp.sub("", old) == stamp.sub("", text):
            return False
    atomic_write(path, text)
    return True


def prune_archive(folder: Path, keep_days: int, today: date) -> int:
    removed = 0
    if not folder.is_dir():
        return 0
    for f in folder.glob("????-??-??.md"):
        d = parse_iso(f.stem)
        if d and (today - d).days > keep_days:
            f.unlink()
            removed += 1
    return removed


def digest_base(cfg: Config) -> Path:
    """Target folder inside the vault. If it leads outside the vault (e.g. through a link), nothing is written."""
    base = cfg.vault / cfg.digest_dir
    vault_root = cfg.vault.resolve()
    for folder in (base, base / cfg.conv.digest_archive):
        if not folder.resolve().is_relative_to(vault_root):
            raise ValueError(tr("Digest folder is outside the vault (a link?): {folder}", folder=folder))
    return base


def write_digest(cfg: Config, today_data: dict, health: dict, today: date, now: datetime) -> list[str]:
    base = digest_base(cfg)
    written = []
    conv = cfg.conv
    md = render_markdown(today_data, conv)
    if write_if_changed(base / conv.digest_file, md):
        written.append(f"{cfg.digest_dir}/{conv.digest_file}")
    write_if_changed(base / conv.digest_archive / f"{today.isoformat()}.md", md)
    if write_if_changed(base / "vault-check.md", render_health_markdown(health, today, now, today_data.get("has_project_note", True), cfg.conv)):
        written.append(f"{cfg.digest_dir}/vault-check.md")
    prune_archive(base / conv.digest_archive, cfg.digest_keep_days, today)
    return written
