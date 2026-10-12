"""`aos init <folder>`: a small starter vault that already satisfies your conventions (`[conventions]`, `[digest] dir`).

Never overwrites: existing files are skipped and reported, so it is safe to run in a folder that already has notes.
The text of the notes is in the interface language ([user] ui_language); folder names, keys and headings come from
`[conventions]`, so the vault check finds nothing to complain about in any language.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .config import Conventions
from .i18n import tr, tr_mark

INDEX = tr_mark("""# Index

The entry point of this vault. Every note should be reachable from here within two links.

- [[{brain_map}]] how this vault is organised
- [[{project}]] your first project
- [[{week}]] this week
- [[{inbox}/README]] things to sort
- [[{ideas}/README]] ideas
""")
BRAIN_MAP = tr_mark("""# Map

| Folder | Holds |
|---|---|
| `{projects}/` | one note per project, with `{status_key}` and `{deadline_key}` in the frontmatter |
| `{areas}/` | long-running areas of your life or work |
| `{journal}/` | one note per ISO week, e.g. `{week_name}` |
| `{resources}/` | knowledge notes and templates |
| `{inbox}/` | unsorted input |
| `{ideas}/` | ideas that are not projects yet |
| `{ai}/` | written by agents and sessions; the digest lands in `{digest_dir}/` |

Back to [[{index}]].
""")
CLAUDE_MD = tr_mark("""# Rules for agents in this vault

- Read before you write. Never edit a note unless asked to.
- Cite note paths when you answer from the vault.
- Notes under `{ai}/` are generated or session output; treat them as hints, not as facts.
- Start from `{index_note}` and `{brain_map_note}`; do not read large notes whole.
""")
PROJECT = tr_mark("""# Getting started

{belongs_to} [[{index}]]

## Next steps
- [ ] Point `aos.toml` at this folder (`[vault] path`)
- [ ] Run `python -m aos digest` and open `{digest_dir}/{digest_file}`
- [ ] Ask an agent: `python -m aos agent research "What is in my vault?"`
""")
WEEK = tr_mark("""# {week_name}

{belongs_to} [[{index}]]

## {goal_heading}
- [ ] Try the digest and the dashboard

## {review_heading}
- [ ] What went well, what did not?
""")
WEEK_TEMPLATE = tr_mark("""# Week

## {goal_heading}
- [ ]

## {review_heading}
- [ ]
""")
INBOX = tr_mark("""# Inbox

{belongs_to} [[{index}]]

Drop anything here that you have not sorted yet.
""")
IDEAS = tr_mark("""# Ideas

{belongs_to} [[{index}]]

## {quick_heading}
- _nothing yet_
""")


def starter_files(today: date, conv: Conventions | None = None) -> dict[str, str]:
    """Relative path -> content. Written so the vault check finds nothing to complain about."""
    c = conv or Conventions()
    week = c.week_note(today)[: -len(".md")]
    iso = today.isoformat()
    project = f"{c.projects_dir}/getting-started"
    status = "active" if "active" in c.project_status else c.project_status[0]
    deadline = (today + timedelta(days=14)).isoformat()
    v = {
        "index": c.index_note[: -len(".md")], "brain_map": c.brain_map[: -len(".md")], "project": project, "week": week,
        "week_name": week.split("/")[-1], "projects": c.projects_dir, "areas": c.areas_dir, "journal": c.journal_dir,
        "resources": c.resources_dir, "inbox": c.inbox_dir, "ideas": c.ideas_dir, "ai": c.ai_dir, "digest_dir": c.digest_dir,
        "digest_file": c.digest_file, "status_key": c.status_key, "deadline_key": c.deadline_key, "index_note": c.index_note,
        "brain_map_note": c.brain_map, "belongs_to": c.belongs_to, "goal_heading": c.week_goal_heading,
        "review_heading": c.weekly_review_heading, "quick_heading": c.ideas_quick_heading,
    }

    def fm(typ: str, extra: str = "") -> str:
        return f"---\n{c.type_key}: {typ}\n{c.created_key}: {iso}\n{extra}---\n"

    return {
        c.index_note: fm(c.type_index) + tr(INDEX, **v),
        c.brain_map: fm(c.type_overview) + tr(BRAIN_MAP, **v),
        "CLAUDE.md": tr(CLAUDE_MD, **v),
        f"{project}.md": fm(
            c.type_project,
            f"{c.status_key}: {status}\n{c.deadline_key}: {deadline}\n{c.tags_key}: [{c.type_project}]\n",
        ) + tr(PROJECT, **v),
        f"{week}.md": fm(c.type_week) + tr(WEEK, **v),
        f"{c.week_template}.md": f"---\n{c.type_key}: {c.type_week}\n---\n" + tr(WEEK_TEMPLATE, **v),
        f"{c.inbox_dir}/README.md": fm(c.type_overview) + tr(INBOX, **v),
        f"{c.ideas_dir}/README.md": fm(c.type_overview) + tr(IDEAS, **v),
    }


def scaffold(target: Path, today: date, conv: Conventions | None = None) -> tuple[list[str], list[str]]:
    """Write the starter vault into `target`. Returns (created, skipped) relative paths."""
    created: list[str] = []
    skipped: list[str] = []
    root = target.resolve()
    for rel, text in starter_files(today, conv).items():
        path = (root / rel).resolve()
        if root not in path.parents:
            raise ValueError(tr("refusing to write outside the target folder: {path}", path=rel))
        if path.exists():
            skipped.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        created.append(rel)
    return created, skipped
