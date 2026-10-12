"""`aos init <folder>`: a small starter vault that already satisfies your conventions (`[conventions]`, `[digest] dir`).

Never overwrites: existing files are skipped and reported, so it is safe to run in a folder that already has notes.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .config import Conventions


def starter_files(today: date, conv: Conventions | None = None) -> dict[str, str]:
    """Relative path -> content. Written so the vault check finds nothing to complain about."""
    c = conv or Conventions()
    week = c.week_note(today)[: -len(".md")]
    week_name = week.split("/")[-1]
    iso = today.isoformat()
    index = c.index_note[: -len(".md")]
    brain_map = c.brain_map[: -len(".md")]
    projects = f"{c.projects_dir}/getting-started"
    status = "active" if "active" in c.project_status else c.project_status[0]
    deadline = (today + timedelta(days=14)).isoformat()

    def fm(typ: str, extra: str = "") -> str:
        return f"---\n{c.type_key}: {typ}\n{c.created_key}: {iso}\n{extra}---\n"

    return {
        c.index_note: fm(c.type_index) + f"""# Index

The entry point of this vault. Every note should be reachable from here within two links.

- [[{brain_map}]] how this vault is organised
- [[{projects}]] your first project
- [[{week}]] this week
- [[{c.inbox_dir}/README]] things to sort
- [[{c.ideas_dir}/README]] ideas
""",
        c.brain_map: fm(c.type_overview) + f"""# Map

| Folder | Holds |
|---|---|
| `{c.projects_dir}/` | one note per project, with `{c.status_key}` and `{c.deadline_key}` in the frontmatter |
| `{c.areas_dir}/` | long-running areas of your life or work |
| `{c.journal_dir}/` | one note per ISO week, e.g. `{week_name}` |
| `{c.resources_dir}/` | knowledge notes and templates |
| `{c.inbox_dir}/` | unsorted input |
| `{c.ideas_dir}/` | ideas that are not projects yet |
| `{c.ai_dir}/` | written by agents and sessions; the digest lands in `{c.digest_dir}/` |

Back to [[{index}]].
""",
        "CLAUDE.md": f"""# Rules for agents in this vault

- Read before you write. Never edit a note unless asked to.
- Cite note paths when you answer from the vault.
- Notes under `{c.ai_dir}/` are generated or session output; treat them as hints, not as facts.
- Start from `{c.index_note}` and `{c.brain_map}`; do not read large notes whole.
""",
        f"{projects}.md": fm(
            c.type_project,
            f"{c.status_key}: {status}\n{c.deadline_key}: {deadline}\n{c.tags_key}: [{c.type_project}]\n",
        ) + f"""# Getting started

{c.belongs_to} [[{index}]]

## Next steps
- [ ] Point `aos.toml` at this folder (`[vault] path`)
- [ ] Run `python -m aos digest` and open `{c.digest_dir}/latest.md`
- [ ] Ask an agent: `python -m aos agent research "What is in my vault?"`
""",
        f"{week}.md": fm(c.type_week) + f"""# {week_name}

{c.belongs_to} [[{index}]]

## {c.week_goal_heading}
- [ ] Try the digest and the dashboard

## {c.weekly_review_heading}
- [ ] What went well, what did not?
""",
        f"{c.week_template}.md": f"""---
{c.type_key}: {c.type_week}
---
# Week

## {c.week_goal_heading}
- [ ]

## {c.weekly_review_heading}
- [ ]
""",
        f"{c.inbox_dir}/README.md": fm(c.type_overview) + f"""# Inbox

{c.belongs_to} [[{index}]]

Drop anything here that you have not sorted yet.
""",
        f"{c.ideas_dir}/README.md": fm(c.type_overview) + f"""# Ideas

{c.belongs_to} [[{index}]]

## {c.ideas_quick_heading}
- _nothing yet_
""",
    }


def scaffold(target: Path, today: date, conv: Conventions | None = None) -> tuple[list[str], list[str]]:
    """Write the starter vault into `target`. Returns (created, skipped) relative paths."""
    created: list[str] = []
    skipped: list[str] = []
    root = target.resolve()
    for rel, text in starter_files(today, conv).items():
        path = (root / rel).resolve()
        if root not in path.parents:
            raise ValueError(f"refusing to write outside the target folder: {rel}")
        if path.exists():
            skipped.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        created.append(rel)
    return created, skipped
