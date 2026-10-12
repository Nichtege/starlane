# Getting started

You installed Starlane. This guide takes you from an empty setup to a system that writes your digest, runs routines
and answers through your own agents. There are ten stages; do them in order, one sitting each is plenty.

The project folder is the folder that holds `aos.toml`: `~/starlane` (or `$AOS_HOME`) after `pip install .` and `aos setup`,
or your clone if you run straight from it. The commands below are written `python -m aos ...`, which is what works in a
clone (`python3 -m aos` on macOS and Linux). After `pip install` the same commands are `aos ...`: `aos next` prints them
that way, and `python -m aos` only finds your setup if it runs the Python that `aos` was installed into.

```
python -m aos next              # checklist + the next open stage
python -m aos next --all        # every stage in detail
python -m aos next --stage digest
python -m aos next --prompt     # only the prompt of the next stage
```

`aos next` only checks whether files exist, looks for a finished job in the jobs log and reads aos.toml and routines.toml;
it never reads your notes, never calls the network and never starts anything. The checklist marks: ✓ done, → next, ○ later, · manual or optional.

## Let Claude Code do the setup

Every stage has a prompt you can give to Claude Code. Open a terminal **in the Starlane project folder**, start
`claude`, and paste the prompt. Or hand it over directly:

```bash
claude "$(python -m aos next --prompt)"                 # bash, zsh: interactive session with the prompt
claude (python -m aos next --prompt | Out-String)       # PowerShell
python -m aos next --prompt | claude                    # pipe form, if your Claude Code version accepts a piped first message
```

**This is your choice, and it is different from the agents.** The prompts run in your own Claude Code session with
that session's normal permissions in the project folder, not under the read-only agent whitelist. That is why every
prompt ends with the same guardrails: no pushing, publishing or sending; no edits to your notes; every file change shown
as a diff and written only after your OK; stop and ask when something is unclear. Keep Claude Code's permission prompts
on and read each diff. The intro line takes your `[user]` name and language from aos.toml (the prompts below show the
defaults). See also [security.md](security.md#onboarding-prompts).

## 1. Point Starlane at your own notes

Everything reads one folder of Markdown notes, the vault. It ships pointing at the demo vault in examples/vault, so everything works right away; switch to your own notes when you are ready.

*Detected as done when* the configured vault folder exists and contains at least one `.md` file, so the shipped demo
vault already counts. Come back to this stage when you want to use your own notes.

1. Try everything on the demo vault first: aos.toml ships with `[vault] path = "examples/vault"`.
2. Ready for your own notes? An existing Obsidian vault works as is; with no notes yet, `python -m aos init ~/notes` creates a small starter vault (it never overwrites anything).
3. Open aos.toml and set `[vault] path` to your folder, e.g. "~/notes" (use "/" also on Windows; a relative path is relative to aos.toml).
4. Run `python -m aos doctor`: "Vault exists" and "Notes read" should show a check mark.

Prompt for Claude Code:

```text
Reply to me in English.

Help me switch Starlane from the bundled demo vault (examples/vault) to my own notes.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Ask me whether I already have a folder of Markdown notes (an Obsidian vault) or want a new starter vault, and where it is or should go.
2. Existing vault: propose the change to `[vault] path` in aos.toml. New vault: after I confirm the folder, run `python -m aos init <folder>` (it only creates files that do not exist yet), then propose the same aos.toml change. Remind me that `aos digest` writes into the digest folder of that vault (`[digest] dir`, default AI/Digest).
3. After I approve the change, run `python -m aos doctor` and explain every line that is not a check mark.
Verify: doctor shows "Vault exists" and "Notes read" with a check mark.
Only read notes as far as needed to tell whether the folder is a vault; never change or move them.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 2. Open the vault in Obsidian

Obsidian is where you read and write the notes; Starlane works next to it and links straight into it.

*Detected as done when* the vault contains a `.obsidian/` folder.

1. Install Obsidian from obsidian.md (free) and start it.
2. Choose "Open folder as vault" and pick the folder from `[vault] path`.
3. Settings > Files and links: turn on Wikilinks, put new notes in the Inbox folder and set an attachments folder (for example Resources/Attachments).
4. Core plugins: keep Backlinks and Graph view on; Daily notes is optional.
5. Set `[vault] name` in aos.toml only if Obsidian shows a different vault name than the folder name.

Prompt for Claude Code:

```text
Reply to me in English.

Guide me through opening my Starlane vault in Obsidian. You cannot click in Obsidian for me: tell me what to click and check the result.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Tell me the vault folder from `[vault] path` in aos.toml (with ~ expanded) and walk me through installing Obsidian and "Open folder as vault" with that folder.
2. Recommend these minimal settings and explain each in one line: Wikilinks on, new notes in the Inbox folder, an attachments folder, core plugins Backlinks and Graph view on, Daily notes optional.
3. Ask me which vault name Obsidian shows. Only if it differs from the folder name, propose `[vault] name = "<that name>"` for aos.toml.
Verify: the vault folder now contains a `.obsidian` folder (only check that it exists; do not read or change anything inside it).
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 3. Install and log in to Claude Code

Agents, skills and the optional Claude routine run the `claude` command line tool. Digest, vault check and dashboard work without it.

*Detected as done when* `claude` is found with the same safe PATH lookup the agents use (absolute PATH folders only, no .cmd/.bat wrapper).

1. Install Claude Code (see claude.com/claude-code) so that `claude` is on your PATH.
2. Run `claude` once in a terminal and log in.
3. Windows: Starlane needs the real claude.exe, not a .cmd or .bat wrapper.
4. Run `python -m aos doctor`: the line "claude CLI" should show a check mark.

Prompt for Claude Code:

```text
Reply to me in English.

Check that Claude Code is set up the way Starlane needs it.
First read README.md and docs/security.md (the sections on agents) in this folder.
1. Run `python -m aos doctor` and read the line "claude CLI". Starlane only searches absolute PATH folders, never the current folder or the vault, and rejects .cmd/.bat wrappers on Windows.
2. If it is not found or rejected, tell me how to fix my PATH or installation on my operating system; do not change system settings yourself.
3. Explain in two sentences what agents send to Anthropic when they run (see docs/security.md).
Verify: `python -m aos doctor` shows the claude line with a check mark.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 4. Write your first digest

The digest is the daily one-page summary: deadlines, the weekly goal, what needs you. It is the only thing the system writes into the vault.

*Detected as done when* `latest.md` exists in the digest folder.

1. Run `python -m aos digest`.
2. Open `AI/Digest/latest.md` (or your `[digest] dir`) in Obsidian.
3. Run `python -m aos mapcheck -v` to see the vault check findings behind the digest.

Prompt for Claude Code:

```text
Reply to me in English.

Help me create and understand my first Starlane digest.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Run `python -m aos doctor`, then `python -m aos digest`, then `python -m aos mapcheck -v`.
2. Read the generated latest.md and vault-check.md in the digest folder (`[digest] dir` in aos.toml, default AI/Digest) and explain to me what each section means.
3. Summarise the vault check findings by kind. If most findings come from my vault using other folders, frontmatter keys or headings than the defaults, say so and point me to the conventions stage (`python -m aos next --stage conventions`) instead of proposing to edit notes.
Verify: latest.md exists in the digest folder.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 5. Open the dashboard

The dashboard shows today, agents, skills, artifacts, links, timeline and vault health in one local page.

*Detection:* none; the checklist always shows this stage as manual (·).

1. Run `python -m aos serve` (in a clone on Windows, start-dashboard.bat starts the clone's own setup) and open the link it prints; the key in it changes on every start.
2. OS is the home screen: deadlines, weekly goal and what needs you. Second brain is your notes as a map.
3. Atlas: ask anything, Atlas picks the agents. Skills: run a skill with a model and effort.
4. Artifacts: everything the system produced. Rings, Links and Timeline: how your notes connect. Health: the vault check.
5. Stop the server with Ctrl+C. It listens on 127.0.0.1 only.

Prompt for Claude Code:

```text
Reply to me in English.

Give me a short tour of the Starlane dashboard. Do not start the server yourself: I run it in my own terminal.
First read README.md, docs/architecture.md and the "Dashboard server" section of docs/security.md in this folder.
1. Tell me to run `python -m aos serve` (in a clone on Windows, start-dashboard.bat starts the clone's own setup) and to open the link it prints.
2. Explain each view in one or two lines: OS (the home screen), Second brain, Atlas, skills, artifacts, rings, links, timeline, health.
3. Explain why the link contains a key and why the server only listens on 127.0.0.1.
4. If I report "Port 8765 not available", explain `python -m aos serve --port 8766` or `[server] port` in aos.toml.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 6. Let routines run on a schedule

Routines keep the digest, vault check and dashboard current without you. Each one has a time limit, a daily cap and a circuit breaker that blocks it after repeated failures.

*Detected as done when* `data/state.json` exists, which every scheduler tick writes.

1. Run `python -m aos install-task` (Windows: a task for your user, every 5 minutes; Linux/macOS: it prints the crontab lines to add).
2. Run `python -m aos status` to see the routines: digest, digest-evening, vault-check and dashboard are on.
3. Off by default: git-pull (keeps a server's copy current), claude-weekly-review (Claude drafts a weekly review on Sunday evening), weekly-plan-monday (the weekly-plan skill on Monday morning).
4. First automation: in routines.toml set `enabled = true` for claude-weekly-review and weekly-plan-monday, then `python -m aos doctor` and `python -m aos status`.
5. Try one now with `python -m aos run <id>`. A blocked routine is released with `python -m aos unblock <id>`.

Prompt for Claude Code:

```text
Reply to me in English.

Help me set up the Starlane routines and my first automations.
First read README.md, routines.toml, the "Routines" section of docs/security.md and the "Scheduling a skill" section of docs/skills.md in this folder.
1. Run `python -m aos status` and explain which routines exist, which are on, and what the off-by-default ones (git-pull, claude-weekly-review, weekly-plan-monday) would do, including which of them call Claude and cost money.
2. Explain time limit, daily cap and circuit breaker in one line each.
3. Propose enabling claude-weekly-review and weekly-plan-monday in routines.toml (only `enabled = true`, nothing else). Ask me first whether I want them.
4. After I approve, run `python -m aos doctor` and `python -m aos status` to check the file still loads.
5. Tell me to run `python -m aos install-task` myself, since it registers a scheduled task (on Linux/macOS it only prints the crontab lines). Do not run it for me.
Verify: doctor reports routines.toml valid, and status lists the routines I chose as enabled.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 7. Give an agent its first task

Agents are read-only specialists that answer from your notes or the web. Atlas, the coordinator, picks the right ones for you.

*Detected as done when* the jobs log (`data/agents/jobs.jsonl`) has a finished job with status ok (a start, a refusal or a failed start does not count).

1. Run `python -m aos agent research "What is in my vault?"` (or open Atlas in the dashboard and ask).
2. Run `python -m aos agents` to see all agents and their daily limits.
3. Run `python -m aos jobs` to see past answers, `python -m aos spend` for what runs cost.

Prompt for Claude Code:

```text
Reply to me in English.

Help me give my first task to a Starlane agent.
First read README.md and docs/agents.md in this folder.
1. Run `python -m aos agents` and explain the shipped agents in one line each, and which ones read my notes and which search the web.
2. Suggest three first tasks that fit my vault, each with the agent it would go to. Ask me which one to run; agent runs call Claude and cost money.
3. Run the one I pick with `python -m aos agent <id> "<task>"`, then `python -m aos jobs` and `python -m aos spend`.
Verify: `python -m aos jobs` lists the finished job.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 8. Create your own agent

The shipped agents are a starting set. A specialist with a sharp description for something you do often answers better than a general one.

*Detected as done when* `agents.local.toml` exists (it is removed when your last custom agent is deleted).

1. Dashboard: Atlas view > New agent. Terminal: `python -m aos agent-new` (asks step by step).
2. Decide vault (reads notes) or web (searches the web): never both.
3. Write the description as: what it delivers; vault or web. For: ... Not for: ... (→ other agent). See docs/agents.md.
4. Your agents go to agents.local.toml and agents/local/; delete one with `python -m aos agent-rm <id>`.

Prompt for Claude Code:

```text
Reply to me in English.

Help me design and create my own Starlane agent.
First read README.md, docs/agents.md (especially "Writing a great description" and "Creating your own agents") and agents.toml in this folder.
1. Ask me what the agent should do for me, with two or three real example tasks. Then decide with me: vault access (reads my notes) or web access (web search), never both.
2. Propose: name, description in the pattern from docs/agents.md (at most 280 characters, with "Not for" neighbours), group, model, up to 12 keywords, up to 4 example tasks, and instructions with the sections Identity, Working method, Boundaries, Output (`python -m aos agent-new --template` prints a template).
3. After I approve, write the instructions to a temporary Markdown file in this folder, run `python -m aos agent-new --name "..." --description "..." --instructions-file <file> [--web] --group "..." --model ... --keyword ... --example "..."`, and then delete the temporary file.
4. Run `python -m aos agents` and show me the new agent. Ask before running a test task, since it costs money.
Verify: agents.local.toml exists and `python -m aos agents` lists the agent as custom.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 9. Teach it your vault's conventions

If your notes use other folders, frontmatter keys or headings (or another language), the vault check reports many findings. One [conventions] block fixes that without renaming notes.

*Detected as done when* aos.toml has a `[conventions]` block that differs from the defaults; otherwise shown as optional (·).

1. Run `python -m aos mapcheck -v`. Many findings about missing types, statuses or folders usually mean other conventions, not a broken vault.
2. Read docs/vault-conventions.md and uncomment in `[conventions]` in aos.toml only what differs.
3. Run `python -m aos doctor` and `python -m aos mapcheck` again and compare the counts.

Prompt for Claude Code:

```text
Reply to me in English.

Help me adapt Starlane to the conventions of my vault.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Run `python -m aos mapcheck -v` and group the findings by kind.
2. Inspect my vault read-only: its top-level folders, the frontmatter keys and values most notes use, and the headings in week notes. Read only as many notes as you need; never change, move or rename a note.
3. Propose a `[conventions]` block for aos.toml that contains only the keys that differ from the defaults, and explain each key in one line with the evidence from my vault.
4. Write it into aos.toml only after I agree. Then run `python -m aos doctor` and `python -m aos mapcheck` and compare the counts with step 1.
Verify: doctor loads aos.toml without errors and the vault check reports fewer findings.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## 10. Run and schedule a skill

A skill is a written-down procedure Claude follows, by hand or on a schedule, read-only like an agent.

*Detected as done when* an enabled routine in routines.toml runs a skill (`command = "skill"`).

1. Run `python -m aos skills` to list them, then `python -m aos skill weekly-plan "Plan this week."`.
2. Schedule one: a routine with `command = "skill"` in routines.toml (weekly-plan-monday is ready, set `enabled = true`).
3. Your own skill: a folder skills/<id>/ with a SKILL.md (frontmatter name, description, model, effort; then steps and boundaries). See docs/skills.md.

Prompt for Claude Code:

```text
Reply to me in English.

Help me use Starlane skills and create one of my own.
First read README.md, docs/skills.md and the folders in skills/ in this folder.
1. Run `python -m aos skills` and explain each shipped skill in one line. Ask before running one, since skill runs cost money.
2. Ask me which procedure I repeat often enough to write down. Propose a new skill: skills/<id>/SKILL.md with frontmatter (name, description, model, effort), numbered steps, boundaries, and a references/checklist.md, following "Writing a good skill" in docs/skills.md. The skill must stay read-only: its output is text I adopt myself.
3. After I approve, create the files, run `python -m aos skills` and `python -m aos doctor`.
4. If I want it on a schedule, propose a `[[routine]]` block with `command = "skill"` for routines.toml and run `python -m aos doctor` after I approve it.
Verify: `python -m aos skills` lists the new skill and doctor reports no problems.
Do not push, publish or send anything. Do not edit my notes (only files in this project folder and aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before writing. Stop and ask if something is ambiguous.
```

## What a good first week looks like

- **Day 1:** vault, Obsidian, Claude Code, first digest (stages 1 to 4). Open the dashboard once and click through.
- **Day 2:** `python -m aos install-task`. From now on the digest is waiting each morning; read it with your coffee.
- **Day 3:** ask Atlas two or three real questions about your notes. Check `python -m aos spend` afterwards.
- **Day 4:** look at the vault check. Fix real broken links in Obsidian; if the findings are about structure, do stage 9.
- **Day 5:** create one agent for something you actually do every week.
- **Weekend:** enable `claude-weekly-review`, and `weekly-plan-monday` if you like it. On Monday, read both drafts and
  keep what is useful. Nothing is ever written into your notes except the digest folder.

## When something goes wrong

Start with `python -m aos doctor`. Every ✗ is a problem, every ! a hint.

| Symptom | Cause and fix |
|---|---|
| `claude` not found | Claude Code is not installed or not on your PATH. Starlane only looks in absolute PATH folders, never in the current folder or the vault. Install it, open a new terminal, run `claude` once to log in. |
| "... is a batch wrapper" (Windows) | Your PATH finds `claude.cmd` first. Put the folder with the real `claude.exe` earlier in PATH. |
| Vault exists ✗ / Notes read ✗ | `[vault] path` in aos.toml points to the wrong folder, or `AOS_VAULT` overrides it. Use `/` in paths, also on Windows; `~` is expanded. |
| "Port 8765 not available" | The dashboard is already running, or another program uses the port. Use the open dashboard, or `python -m aos serve --port 8766`, or set `[server] port`. |
| No digest appears | Run `python -m aos digest` and read its output. `[digest] dir` must be a relative folder inside the vault (no drive, no `..`). The digest is written to `<vault>/AI/Digest/latest.md` by default. |
| Many vault check findings | Usually other conventions, not a broken vault: see stage 9 and [vault-conventions.md](vault-conventions.md). |
| A routine shows ⛔ blocked | It failed several times in a row. Read the note in `python -m aos status`, fix the cause, then `python -m aos unblock <id>`. |
| Agents refuse with "daily cap" | The per-agent limit or the daily spending ceiling is reached; see `python -m aos spend` and [agents.md](agents.md#limits). |
