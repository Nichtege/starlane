---
name: Weekly plan
description: Builds a realistic plan for the current week from deadlines, the week note and project schedules
model: sonnet
effort: medium
---
# Weekly plan

You build a plan for the current week, using only what the vault contains.

## Steps
1. Read the latest digest in the digest folder (default `AI/Digest/`; deadlines, weekly goal, what needs attention, next 14 days).
2. Read the week note in the journal folder (default `Journal/`; the file named after the current ISO week, for example `Journal/2026-W41.md`) and the schedule notes of active projects (default folder `Projects/`). Use the root notes (default `index.md` and `AI/brain-map.md`) to find them if the names differ.
3. Order the open tasks by deadline and effort. Format and rules: `references/format.md`.
4. Check the result against `references/checklist.md` before you answer.

## Boundaries
- Invent nothing: whatever is not in the vault goes into the open questions at the end, not into the plan.
- Write nothing: the plan is plain text, the user adopts it themselves.
- Dates in log sections (status, done, log, history) are history, not appointments.
