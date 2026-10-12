# Vault conventions

Starlane reads a folder of Markdown notes (an Obsidian-style *vault*). To build the digest, the vault check and the
dashboard it has to know a few things about how that folder is organised: which frontmatter key holds a note's type,
what a project status may be, where week notes live, what the heading above your weekly goal is called.

These are the *conventions*. They all have English defaults, so a new vault that follows them needs no configuration.
If your vault already has its own structure (or is written in another language), you describe it once in the
`[conventions]` table of `aos.toml` instead of renaming your notes.

**Worked example:** [`examples/vault/`](../examples/vault/) is a small demo vault that follows every default on this
page: projects with status and deadline, a schedule note, area notes, week notes with a weekly goal and review, an inbox,
an ideas quick list, a session note under `AI/Sessions/`, and a `CLAUDE.md` with rules for agents. The shipped `aos.toml`
points at it. It is set in week 2026-W41: in that week its vault check reports no findings; on a later date it reports
one warning (`no-week-note` for the current week) and the digest shows some tasks as overdue. That is the demo getting
old, not a broken setup.

## What the system reads

Folder and note names on this page are the defaults; each one follows its key in the table at the end.

| Part | Reads | Uses it for |
|---|---|---|
| Vault check (`aos mapcheck`) | every note: links, frontmatter, `index.md`, `AI/brain-map.md`, `CLAUDE.md`-style rules | `vault-check.md`, the health view |
| Digest (`aos digest`) | project notes (deadline, status), the current week note, schedule notes, `Inbox/`, `Ideas/README.md`, `AI/Sessions/` | `latest.md`, the Today view |
| Dashboard (`aos dashboard`, `aos serve`) | all notes (title, type, status, project, tags, links) | graph, rings, timeline; areas and rings follow the `*_dir` keys, `brain_map`, `index_note` and `status_done` |

The system never edits your notes. It only writes into the digest folder (`[digest] dir`, default `AI/Digest`):

| File | Written by | Content |
|---|---|---|
| `AI/Digest/latest.md` | `aos digest` | today's digest |
| `AI/Digest/archive/YYYY-MM-DD.md` | `aos digest` | one copy per day, pruned after `[digest] keep_days` |
| `AI/Digest/vault-check.md` | `aos digest`, `aos mapcheck` | every finding of the vault check, with file and line |
| `AI/Digest/weekly-review.md` | `aos claude-digest` (optional) | a weekly review draft written by Claude, read-only run |

Files in the digest folder are skipped by the vault check, so the system never grades its own output. A digest folder that
resolves outside the vault (for example through a symlink) is refused.

## A note that follows the defaults

```markdown
---
type: project
created: 2026-10-02
status: active
deadline: 2026-11-10
tags: [project, writing]
---
# Thesis

Part of [[Areas/university]]

## Next steps
- [ ] Finish the outline
- **Tue 13.10.** meeting with the supervisor
```

Notes in `AI/` (written by agents or sessions) should name what they belong to, both in the frontmatter
(`project:`, `projects:` or `area:`) and as a `Part of [[...]]` line in the first 20 lines.

## Dates in notes

The digest looks for dates in notes under `projects_dir`, `areas_dir` and `journal_dir` (templates excluded), and only in
open list items (`- ...`, `- [ ] ...`; not checked off, not ~~struck through~~) and in `##` to `####` headings.
It understands exactly three forms:

- `2026-11-10` (ISO, `YYYY-MM-DD`)
- `10.11.2026` (`DD.MM.YYYY`)
- a weekday followed by day.month: `Tue 6.10.`, `Tuesday 6.10.`. The weekday must match the date, which also decides the
  year. English names and abbreviations are accepted, and so are the German abbreviations `Mo Di Mi Do Fr Sa So`.

Anything else is not a date to the digest: month names (`10 November`, `Nov 10`), US order (`11/10/2026`) and a bare
`6.10.` without a weekday are not parsed.

Dates are history, not appointments, and are ignored:

- in a section whose heading contains one of the `log_words` (for example `## Done` or `## Log`), up to the next heading;
- in *log lines*: list items that start with a day.month date, optionally bold and with a year, followed by `:`, `-` or
  `–` (`- 12.10.: called the bank`, `- **12.10.2026** – sent`). A list item that starts with an ISO date is not a log line.

Schedule notes (any note whose path contains `schedule_keyword`) may group checkboxes under dated headings such as
`## Week 2 · Mon 12.10 – Sun 18.10`. Open checkboxes in the current window are shown as tasks, those in a past window
as overdue.

## All convention keys

Every key is optional. Strings must be non-empty, lists must be lists of non-empty strings, and unknown keys are an
error (so a typo does not silently fall back to the default).

| Key | Default | Meaning |
|---|---|---|
| `type_key` | `type` | frontmatter key that holds the note type |
| `created_key` | `created` | frontmatter key with the creation date |
| `status_key` | `status` | frontmatter key with the status |
| `deadline_key` | `deadline` | frontmatter key with a project deadline (`YYYY-MM-DD`) |
| `tags_key` | `tags` | frontmatter key with the tags |
| `project_key` | `project` | frontmatter key linking a note to its project (`"[[Projects/x]]"`) |
| `projects_key` | `projects` | the same, as a list |
| `area_key` | `area` | frontmatter key linking a note to an area |
| `type_project` | `project` | type value of a project note (deadlines, status check) |
| `type_idea` | `idea` | type value of an idea note (status check) |
| `type_week` | `week` | type value of a week note; used when `aos init` writes notes, reserved otherwise |
| `type_plan` | `plan` | reserved: not read by any logic yet (schedule notes are found by `schedule_keyword`) |
| `type_knowledge` | `knowledge` | reserved: not read by any logic yet |
| `type_session` | `session` | reserved: not read by any logic yet (session notes are found by `sessions_dir`) |
| `type_overview` | `overview` | type value of an overview (for example the brain map); used when `aos init` writes notes, reserved otherwise |
| `type_index` | `index` | type value of the index; used when `aos init` writes notes, reserved otherwise |
| `type_digest` | `digest` | type value the system writes into its own files |
| `project_status` | `["idea", "new", "building", "active", "paused", "done"]` | allowed project status values (`status_done` is always allowed too) |
| `status_done` | `done` | project status that means finished (no deadline card, shown as closed in the dashboard) |
| `idea_status` | `["raw", "in-progress", "project", "dropped"]` | allowed idea status values |
| `week_goal_heading` | `Weekly goal` | heading in the week note above the goal(s) |
| `weekly_review_heading` | `Weekly review` | heading in the week note for the end-of-week review |
| `ideas_quick_heading` | `Quick` | heading (or part of it) of the quick list in `Ideas/README.md` |
| `belongs_to` | `Part of` | phrase before the link that says what an AI note belongs to |
| `log_words` | `["status", "done", "log", "history", "result", "learned", "went wrong", "notes", "archive"]` | words that mark a heading as a log section |
| `projects_dir` | `Projects` | folder of project notes |
| `areas_dir` | `Areas` | folder of area notes |
| `resources_dir` | `Resources` | folder of reference notes |
| `journal_dir` | `Journal` | folder of week notes, named by ISO week (`Journal/2026-W41.md`) |
| `inbox_dir` | `Inbox` | inbox folder; every note in it, and every list item in its `README.md`, is an item to sort |
| `ideas_dir` | `Ideas` | ideas folder (its `README.md` holds the quick list) |
| `archive_dir` | `Archive` | archive folder |
| `templates_dir` | `Resources/Templates` | templates: never checked, never shown as events |
| `ai_dir` | `AI` | folder of notes written by agents (must say what they belong to) |
| `sessions_dir` | `AI/Sessions` | session notes, newest shown in the digest |
| `week_template` | `Resources/Templates/week` | template named when a week note is missing |
| `schedule_keyword` | `schedule` | a note whose path contains this word is read as a schedule |
| `index_note` | `index.md` | entry point of the vault (two-hop rule); must end in `.md` |
| `brain_map` | `AI/brain-map.md` | second entry point, a map of the important notes with their sizes; must end in `.md` |
| `project_note` | (none) | optional, e.g. `Projects/my-project`: the generated files link to this note when it exists |

The digest folder itself is set with `[digest] dir`, not here. Folder keys (`*_dir`) and `[digest] dir` must be relative
folders inside the vault: no drive (`C:`), no path starting with `\`, no `..`. `[digest] dir` may not start with `/`
either; the folder keys simply drop leading and trailing `/`. `project_note` and `week_template` are link targets;
a trailing `.md` is dropped. The reserved keys are kept so that a config which sets them stays valid (unknown keys are
an error).

`aos init <folder>` writes its starter notes with the conventions of the config it finds (`--config`, `$AOS_CONFIG`, or
`aos.toml` next to the project), including `[digest] dir`; without a config it uses the defaults.

## Shipped prompts and skills

The agent prompts in `agents/*.md` and the skills in `skills/` are plain text written for the default layout: where they
mention `index.md`, `AI/brain-map.md`, the digest folder (`AI/Digest/`), `Journal/` or `Projects/`, they mean "the note or
folder with that role". They do not read `[conventions]`. If your vault uses other names, edit those files (or copy them
into a custom agent or skill of your own) so the agents look in the right places.

The *two-hop rule*: every note should be reachable in at most two links from `index_note` or `brain_map`. Notes that
cannot be reached at all are reported as `unreachable`.

## Example: a German vault

A vault that uses German frontmatter and headings keeps working with this block in `aos.toml`:

```toml
[conventions]
type_key = "typ"
created_key = "erstellt"
project_key = "projekt"
projects_key = "projekte"
area_key = "bereich"
type_project = "projekt"
type_idea = "idee"
type_week = "woche"
type_knowledge = "wissen"
type_overview = "uebersicht"
project_status = ["idee", "neu", "aufbau", "aktiv", "pausiert", "abgeschlossen"]
status_done = "abgeschlossen"
idea_status = ["roh", "in-arbeit", "projekt", "verworfen"]
week_goal_heading = "Wochenziel"
weekly_review_heading = "Sonntags-Check"
ideas_quick_heading = "Schnell"
belongs_to = "Gehört zu"
log_words = ["stand", "erledigt", "logbuch", "verlauf", "ergebnis", "gelernt", "lief schief", "protokoll", "historie"]
ideas_dir = "Ideen"
week_template = "Resources/Templates/woche"
schedule_keyword = "zeitplan"
```

The generated text (digest, vault check) stays English; only the parts that have to match your notes follow the
conventions. Set `[user] language` to have the agents reply in your language.
