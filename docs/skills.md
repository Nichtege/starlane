# Skills

A skill is a recipe: a repeatable procedure that Claude follows, written down once. Where an agent is a specialist you talk to, a skill is a standard operating procedure you run, by hand or on a schedule. Skills are read-only like agents: they read the vault and their own folder, and answer with text.

```
python -m aos skills                                   # list skills with model and effort
python -m aos skill weekly-plan "Plan this week."      # run one
python -m aos skill weekly-plan "Plan this week." --model opus --effort high
```

In the dashboard, skills appear on the Skills tab and in the skill deck on the home page, each with a model and effort picker. Results show up under Artifacts and in `python -m aos jobs`.

## Shipped skills
| Skill | What it does |
|---|---|
| `weekly-plan` | Builds a realistic plan for the current week from deadlines, the week note and project schedules. |
| `vault-triage` | Orders the vault-check findings by urgency and proposes a concrete fix for each. |
| `study-plan` | Spreads study material backwards from an exam or due date over the remaining days. |

## Anatomy
```
skills/
  weekly-plan/
    SKILL.md              # the router: frontmatter + steps + boundaries
    references/
      format.md           # read on demand
      checklist.md
```

`SKILL.md` starts with frontmatter:

```markdown
---
name: Weekly plan
description: Builds a realistic plan for the current week from deadlines, the week note and project schedules
model: sonnet
effort: medium
---
# Weekly plan

You build a plan for the current week, using only what the vault contains.

## Steps
1. Read the latest digest in `AI/Digest/` ...
2. ...
3. Order the open tasks by deadline and effort. Format and rules: `references/format.md`.
4. Check the result against `references/checklist.md` before you answer.

## Boundaries
- Invent nothing ...
```

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | Display name. |
| `description` | yes | One line: what the skill produces. Shown on the skill card. |
| `model` | no | `haiku`, `sonnet`, `opus` or `fable`. Default `sonnet`. |
| `effort` | no | `low`, `medium`, `high`, `xhigh` or `max`. Empty means Claude's default. |

The folder name is the skill id (`a-z`, `0-9`, `-`). Keep `SKILL.md` short and move details (formats, checklists, examples, tone guides) into reference files: Claude reads them only when a step points to them, which keeps runs cheaper and more focused. Up to 40 reference files, at most three folder levels deep.

### Choosing model and effort
- `haiku` / `low`: mechanical sorting and summarising of a known file (for example triage of a report).
- `sonnet` / `medium`: the default for planning and drafting from several notes.
- `opus` / `high` and above: long, multi-step reasoning across many notes, or when quality matters more than speed and cost.

The value in the frontmatter is a default. Every run can override it (`--model`, `--effort`, or the picker in the dashboard).

## Where skills are found
`[skills] dirs` in `aos.toml`, default `["skills", "~/.claude/skills"]`. The first hit per skill id wins, so a project skill beats one with the same id in your Claude folder. Linked skill folders (symlinks, junctions) are skipped, and linked files are left out of a skill's reference list.

## Scheduling a skill
A routine with `command = "skill"` runs a skill headless. Add it to `routines.toml`:

```toml
[[routine]]
id = "weekly-plan-monday"
description = "Skill 'weekly-plan' writes the plan for the week early on Monday -> dashboard, Artifacts"
schedule = "weekly mon 07:00"
command = "skill"
skill = "weekly-plan"
instruction = "Create the plan for this week."
model = "sonnet"
effort = "medium"
machine = "any"
enabled = true
timeout_s = 960
max_runs_per_day = 1
max_failures = 2
```

Skill id, instruction, model and effort are validated when `routines.toml` loads and passed as separate arguments, never through a shell. The skill's own time limit comes from `[skills] timeout_s`; the routine's `timeout_s` is raised to at least 960 seconds so the outer timer never fires first.

## Security
- A skill run uses the same lock as a vault agent: only `Read`, `Grep` and `Glob`, no connectors, no saved session, a budget, a turn limit, a time limit (at most 15 minutes) and the daily spending ceiling shared with the agents. A skill cannot grant itself more tools, not even through its frontmatter.
- Besides the vault, the skill's own folder is added as readable (`--add-dir`), so the reference files are reachable. What Claude may open is decided by Claude Code's permission rules and your user-level settings (see [security.md](security.md)).
- Like every run, skill runs send the task and whatever Claude reads to Anthropic.
- Model and effort come from fixed lists; anything else is rejected.
- Each skill has a daily cap (`[skills] max_runs_per_day`), one run per skill at a time, three runs in total together with the agents.
- The answer is redacted (best effort, common key, token and password shapes) and never written into a note.
- Skills from `~/.claude/skills` may come from plugins or syncs. Their text steers Claude, not your system, so the worst a bad skill can do is give a bad answer. Still, read a `SKILL.md` before you rely on someone else's skill.

Details: [security.md](security.md).

## Writing a good skill
- One job per skill. If you find yourself writing "and also", make two skills.
- Write steps, not wishes: which file to read first, what to compute, in what order, in what format to answer.
- Say what to do when information is missing (ask, or list it as an open question), so the skill never invents.
- Keep it read-only in spirit as well: the output is text the user adopts, never "update the note".
- End with a short checklist in a reference file that the skill checks its answer against.
