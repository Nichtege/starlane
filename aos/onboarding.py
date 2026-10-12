"""Getting started: the onboarding stages behind `python -m aos next` and docs/getting-started.md.

Detection is deliberately shallow: existence and size checks, the line count of the jobs log, and the parsed
routines.toml (project config, not notes). It never reads a note, never calls the network and never starts anything.
Every prompt is meant for the user's own Claude Code session in the project folder (see docs/security.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Callable

from . import agentdefs as AD
from . import agents as A
from .config import FROM_DIGEST, Config, Conventions
from .i18n import tr, tr_mark
from .routines import RoutineError, load_routines

# Every text below is English and marked with tr_mark: it is translated where it is shown (`text`, `prompt_for`).
GUARDRAILS = tr_mark("Do not push, publish or send anything. Do not edit my notes (only files in this project folder and "
                     "aos.toml/routines.toml/agents.local.toml). Show me each file change as a diff and wait for my OK before "
                     "writing. Stop and ask if something is ambiguous.")

_DEFAULT_NAMES = ("the user", "you")  # the code default and the shipped aos.toml value: not a real name


@dataclass(frozen=True)
class Stage:
    id: str
    title: str
    why: str
    done: Callable[[Config], bool | None]  # None: cannot be detected (manual or optional)
    steps: tuple[str, ...]
    prompt: str


# --- detection -------------------------------------------------------------------------
def _has_notes(cfg: Config) -> bool:
    if not cfg.vault.is_dir():
        return False
    for _root, dirs, files in os.walk(cfg.vault):
        dirs[:] = [d for d in dirs if d not in cfg.ignore and not d.startswith(".")]
        if any(f.endswith(".md") and not f.startswith(".") for f in files):  # the same notes the vault scan counts
            return True
    return False


def _obsidian(cfg: Config) -> bool:
    return (cfg.vault / ".obsidian").is_dir()


def _claude(cfg: Config) -> bool:
    return A.find_claude(cfg.vault)[0] is not None


def _digest(cfg: Config) -> bool:
    return (cfg.vault / cfg.digest_dir / cfg.conv.digest_file).is_file()


def _scheduler(cfg: Config) -> bool:
    # Trade-off: every tick writes data/state.json, so its existence means "the scheduler has run"; a manual
    # `aos run` creates it too. Asking the Windows task scheduler would start PowerShell on every `aos next`.
    return cfg.state_file.is_file()


def _first_job(cfg: Config) -> bool:
    # A job that finished with status ok. A start, a refusal or a start that failed (no `claude` yet) is not a first task.
    # Trade-off: a plain substring test per line (answers are never parsed or kept).
    try:
        with cfg.jobs_log.open("rb") as fh:
            return any(b'"status": "ok"' in line for line in fh)
    except OSError:
        return False


def _own_agent(cfg: Config) -> bool:
    return AD.local_file(cfg).is_file()  # removed again when the last custom agent is deleted


def _conventions(cfg: Config) -> bool | None:
    # the [digest] values live in Conventions too, but they are not what this stage is about
    return True if cfg.conv != replace(Conventions(), **{k: getattr(cfg.conv, k) for k in FROM_DIGEST}) else None


def _skill_scheduled(cfg: Config) -> bool:
    return any(r.enabled and r.command == "skill" for r in load_routines(cfg.routines_file))


# --- the stages --------------------------------------------------------------------------
STAGES: tuple[Stage, ...] = (
    Stage(
        id="vault",
        title=tr_mark("Point Starlane at your own notes"),
        why=tr_mark("Everything reads one folder of Markdown notes, the vault. It ships pointing at the demo vault in examples/vault, "
                    "so everything works right away; switch to your own notes when you are ready."),
        done=_has_notes,
        steps=(
            tr_mark("Try everything on the demo vault first: aos.toml ships with `[vault] path = \"examples/vault\"`."),
            tr_mark("Ready for your own notes? An existing Obsidian vault works as is; with no notes yet, "
                    "`python -m aos init ~/notes` creates a small starter vault (it never overwrites anything)."),
            tr_mark('Open aos.toml and set `[vault] path` to your folder, e.g. "~/notes" (use "/" also on Windows; a relative path is relative to aos.toml).'),
            tr_mark("Run `python -m aos doctor`: \"Vault exists\" and \"Notes read\" should show a check mark."),
        ),
        prompt=tr_mark("""Help me switch Starlane from the bundled demo vault (examples/vault) to my own notes.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Ask me whether I already have a folder of Markdown notes (an Obsidian vault) or want a new starter vault, and where it is or should go.
2. Existing vault: propose the change to `[vault] path` in aos.toml. New vault: after I confirm the folder, run `python -m aos init <folder>` (it only creates files that do not exist yet), then propose the same aos.toml change. Remind me that `aos digest` writes into the digest folder of that vault (`[digest] dir`, default AI/Digest).
3. After I approve the change, run `python -m aos doctor` and explain every line that is not a check mark.
Verify: doctor shows "Vault exists" and "Notes read" with a check mark.
Only read notes as far as needed to tell whether the folder is a vault; never change or move them.
"""),
    ),
    Stage(
        id="obsidian",
        title=tr_mark("Open the vault in Obsidian"),
        why=tr_mark("Obsidian is where you read and write the notes; Starlane works next to it and links straight into it."),
        done=_obsidian,
        steps=(
            tr_mark("Install Obsidian from obsidian.md (free) and start it."),
            tr_mark('Choose "Open folder as vault" and pick the folder from `[vault] path`.'),
            tr_mark("Settings > Files and links: turn on Wikilinks, put new notes in the Inbox folder and set an attachments "
                    "folder (for example Resources/Attachments)."),
            tr_mark("Core plugins: keep Backlinks and Graph view on; Daily notes is optional."),
            tr_mark("Set `[vault] name` in aos.toml only if Obsidian shows a different vault name than the folder name."),
        ),
        prompt=tr_mark("""Guide me through opening my Starlane vault in Obsidian. You cannot click in Obsidian for me: tell me what to click and check the result.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Tell me the vault folder from `[vault] path` in aos.toml (with ~ expanded) and walk me through installing Obsidian and "Open folder as vault" with that folder.
2. Recommend these minimal settings and explain each in one line: Wikilinks on, new notes in the Inbox folder, an attachments folder, core plugins Backlinks and Graph view on, Daily notes optional.
3. Ask me which vault name Obsidian shows. Only if it differs from the folder name, propose `[vault] name = "<that name>"` for aos.toml.
Verify: the vault folder now contains a `.obsidian` folder (only check that it exists; do not read or change anything inside it).
"""),
    ),
    Stage(
        id="claude",
        title=tr_mark("Install and log in to Claude Code"),
        why=tr_mark("Agents, skills and the optional Claude routine run the `claude` command line tool. Digest, vault check and dashboard work without it."),
        done=_claude,
        steps=(
            tr_mark("Install Claude Code (see claude.com/claude-code) so that `claude` is on your PATH."),
            tr_mark("Run `claude` once in a terminal and log in."),
            tr_mark("Windows: Starlane needs the real claude.exe, not a .cmd or .bat wrapper."),
            tr_mark("Run `python -m aos doctor`: the line \"claude CLI\" should show a check mark."),
        ),
        prompt=tr_mark("""Check that Claude Code is set up the way Starlane needs it.
First read README.md and docs/security.md (the sections on agents) in this folder.
1. Run `python -m aos doctor` and read the line "claude CLI". Starlane only searches absolute PATH folders, never the current folder or the vault, and rejects .cmd/.bat wrappers on Windows.
2. If it is not found or rejected, tell me how to fix my PATH or installation on my operating system; do not change system settings yourself.
3. Explain in two sentences what agents send to Anthropic when they run (see docs/security.md).
Verify: `python -m aos doctor` shows the claude line with a check mark.
"""),
    ),
    Stage(
        id="digest",
        title=tr_mark("Write your first digest"),
        why=tr_mark("The digest is the daily one-page summary: deadlines, the weekly goal, what needs you. It is the only thing the system writes into the vault."),
        done=_digest,
        steps=(
            tr_mark("Run `python -m aos digest`."),
            tr_mark("Open `AI/Digest/latest.md` (or your `[digest] dir`) in Obsidian."),
            tr_mark("Run `python -m aos mapcheck -v` to see the vault check findings behind the digest."),
        ),
        prompt=tr_mark("""Help me create and understand my first Starlane digest.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Run `python -m aos doctor`, then `python -m aos digest`, then `python -m aos mapcheck -v`.
2. Read the generated latest.md and vault-check.md in the digest folder (`[digest] dir` in aos.toml, default AI/Digest) and explain to me what each section means.
3. Summarise the vault check findings by kind. If most findings come from my vault using other folders, frontmatter keys or headings than the defaults, say so and point me to the conventions stage (`python -m aos next --stage conventions`) instead of proposing to edit notes.
Verify: latest.md exists in the digest folder.
"""),
    ),
    Stage(
        id="dashboard",
        title=tr_mark("Open the dashboard"),
        why=tr_mark("The dashboard shows today, agents, skills, artifacts, links, timeline and vault health in one local page."),
        done=lambda cfg: None,
        steps=(
            tr_mark("Run `python -m aos serve` (in a clone on Windows, start-dashboard.bat starts the clone's own setup) and open the link it prints; the key in it changes on every start."),
            tr_mark("OS is the home screen: deadlines, weekly goal and what needs you. Second brain is your notes as a map."),
            tr_mark("Atlas: ask anything, Atlas picks the agents. Skills: run a skill with a model and effort."),
            tr_mark("Artifacts: everything the system produced. Rings, Links and Timeline: how your notes connect. Health: the vault check."),
            tr_mark("Stop the server with Ctrl+C. It listens on 127.0.0.1 only."),
        ),
        prompt=tr_mark("""Give me a short tour of the Starlane dashboard. Do not start the server yourself: I run it in my own terminal.
First read README.md, docs/architecture.md and the "Dashboard server" section of docs/security.md in this folder.
1. Tell me to run `python -m aos serve` (in a clone on Windows, start-dashboard.bat starts the clone's own setup) and to open the link it prints.
2. Explain each view in one or two lines: OS (the home screen), Second brain, Atlas, skills, artifacts, rings, links, timeline, health.
3. Explain why the link contains a key and why the server only listens on 127.0.0.1.
4. If I report "Port 8765 not available", explain `python -m aos serve --port 8766` or `[server] port` in aos.toml.
"""),
    ),
    Stage(
        id="routines",
        title=tr_mark("Let routines run on a schedule"),
        why=tr_mark("Routines keep the digest, vault check and dashboard current without you. Each one has a time limit, a daily cap and a circuit breaker that blocks it after repeated failures."),
        done=_scheduler,
        steps=(
            tr_mark("Run `python -m aos install-task` (Windows: a task for your user, every 5 minutes; Linux/macOS: it prints the crontab lines to add)."),
            tr_mark("Run `python -m aos status` to see the routines: digest, digest-evening, vault-check and dashboard are on."),
            tr_mark("Off by default: git-pull (keeps a server's copy current), claude-weekly-review (Claude drafts a weekly review "
                    "on Sunday evening), weekly-plan-monday (the weekly-plan skill on Monday morning)."),
            tr_mark("First automation: in routines.toml set `enabled = true` for claude-weekly-review and weekly-plan-monday, then "
                    "`python -m aos doctor` and `python -m aos status`."),
            tr_mark("Try one now with `python -m aos run <id>`. A blocked routine is released with `python -m aos unblock <id>`."),
        ),
        prompt=tr_mark("""Help me set up the Starlane routines and my first automations.
First read README.md, routines.toml, the "Routines" section of docs/security.md and the "Scheduling a skill" section of docs/skills.md in this folder.
1. Run `python -m aos status` and explain which routines exist, which are on, and what the off-by-default ones (git-pull, claude-weekly-review, weekly-plan-monday) would do, including which of them call Claude and cost money.
2. Explain time limit, daily cap and circuit breaker in one line each.
3. Propose enabling claude-weekly-review and weekly-plan-monday in routines.toml (only `enabled = true`, nothing else). Ask me first whether I want them.
4. After I approve, run `python -m aos doctor` and `python -m aos status` to check the file still loads.
5. Tell me to run `python -m aos install-task` myself, since it registers a scheduled task (on Linux/macOS it only prints the crontab lines). Do not run it for me.
Verify: doctor reports routines.toml valid, and status lists the routines I chose as enabled.
"""),
    ),
    Stage(
        id="first-agent",
        title=tr_mark("Give an agent its first task"),
        why=tr_mark("Agents are read-only specialists that answer from your notes or the web. Atlas, the coordinator, picks the right ones for you."),
        done=_first_job,
        steps=(
            tr_mark('Run `python -m aos agent research "What is in my vault?"` (or open Atlas in the dashboard and ask).'),
            tr_mark("Run `python -m aos agents` to see all agents and their daily limits."),
            tr_mark("Run `python -m aos jobs` to see past answers, `python -m aos spend` for what runs cost."),
        ),
        prompt=tr_mark("""Help me give my first task to a Starlane agent.
First read README.md and docs/agents.md in this folder.
1. Run `python -m aos agents` and explain the shipped agents in one line each, and which ones read my notes and which search the web.
2. Suggest three first tasks that fit my vault, each with the agent it would go to. Ask me which one to run; agent runs call Claude and cost money.
3. Run the one I pick with `python -m aos agent <id> "<task>"`, then `python -m aos jobs` and `python -m aos spend`.
Verify: `python -m aos jobs` lists the finished job.
"""),
    ),
    Stage(
        id="own-agent",
        title=tr_mark("Create your own agent"),
        why=tr_mark("The shipped agents are a starting set. A specialist with a sharp description for something you do often answers better than a general one."),
        done=_own_agent,
        steps=(
            tr_mark("Dashboard: Atlas view > New agent. Terminal: `python -m aos agent-new` (asks step by step)."),
            tr_mark("Decide vault (reads notes) or web (searches the web): never both."),
            tr_mark("Write the description as: what it delivers; vault or web. For: ... Not for: ... (→ other agent). See docs/agents.md."),
            tr_mark("Your agents go to agents.local.toml and agents/local/; delete one with `python -m aos agent-rm <id>`."),
        ),
        prompt=tr_mark("""Help me design and create my own Starlane agent.
First read README.md, docs/agents.md (especially "Writing a great description" and "Creating your own agents") and agents.toml in this folder.
1. Ask me what the agent should do for me, with two or three real example tasks. Then decide with me: vault access (reads my notes) or web access (web search), never both.
2. Propose: name, description in the pattern from docs/agents.md (at most 280 characters, with "Not for" neighbours), group, model, up to 12 keywords, up to 4 example tasks, and instructions with the sections Identity, Working method, Boundaries, Output (`python -m aos agent-new --template` prints a template).
3. After I approve, write the instructions to a temporary Markdown file in this folder, run `python -m aos agent-new --name "..." --description "..." --instructions-file <file> [--web] --group "..." --model ... --keyword ... --example "..."`, and then delete the temporary file.
4. Run `python -m aos agents` and show me the new agent. Ask before running a test task, since it costs money.
Verify: agents.local.toml exists and `python -m aos agents` lists the agent as custom.
"""),
    ),
    Stage(
        id="conventions",
        title=tr_mark("Teach it your vault's conventions"),
        why=tr_mark("If your notes use other folders, frontmatter keys or headings (or another language), the vault check reports many findings. One [conventions] block fixes that without renaming notes."),
        done=_conventions,
        steps=(
            tr_mark("Run `python -m aos mapcheck -v`. Many findings about missing types, statuses or folders usually mean other conventions, not a broken vault."),
            tr_mark("Read docs/vault-conventions.md and uncomment in `[conventions]` in aos.toml only what differs."),
            tr_mark("Run `python -m aos doctor` and `python -m aos mapcheck` again and compare the counts."),
        ),
        prompt=tr_mark("""Help me adapt Starlane to the conventions of my vault.
First read README.md, docs/vault-conventions.md and aos.toml in this folder.
1. Run `python -m aos mapcheck -v` and group the findings by kind.
2. Inspect my vault read-only: its top-level folders, the frontmatter keys and values most notes use, and the headings in week notes. Read only as many notes as you need; never change, move or rename a note.
3. Propose a `[conventions]` block for aos.toml that contains only the keys that differ from the defaults, and explain each key in one line with the evidence from my vault.
4. Write it into aos.toml only after I agree. Then run `python -m aos doctor` and `python -m aos mapcheck` and compare the counts with step 1.
Verify: doctor loads aos.toml without errors and the vault check reports fewer findings.
"""),
    ),
    Stage(
        id="skills",
        title=tr_mark("Run and schedule a skill"),
        why=tr_mark("A skill is a written-down procedure Claude follows, by hand or on a schedule, read-only like an agent."),
        done=_skill_scheduled,
        steps=(
            tr_mark("Run `python -m aos skills` to list them, then `python -m aos skill weekly-plan \"Plan this week.\"`."),
            tr_mark("Schedule one: a routine with `command = \"skill\"` in routines.toml (weekly-plan-monday is ready, set `enabled = true`)."),
            tr_mark("Your own skill: a folder skills/<id>/ with a SKILL.md (frontmatter name, description, model, effort; then steps and boundaries). See docs/skills.md."),
        ),
        prompt=tr_mark("""Help me use Starlane skills and create one of my own.
First read README.md, docs/skills.md and the folders in skills/ in this folder.
1. Run `python -m aos skills` and explain each shipped skill in one line. Ask before running one, since skill runs cost money.
2. Ask me which procedure I repeat often enough to write down. Propose a new skill: skills/<id>/SKILL.md with frontmatter (name, description, model, effort), numbered steps, boundaries, and a references/checklist.md, following "Writing a good skill" in docs/skills.md. The skill must stay read-only: its output is text I adopt myself.
3. After I approve, create the files, run `python -m aos skills` and `python -m aos doctor`.
4. If I want it on a schedule, propose a `[[routine]]` block with `command = "skill"` for routines.toml and run `python -m aos doctor` after I approve it.
Verify: `python -m aos skills` lists the new skill and doctor reports no problems.
"""),
    ),
)

_BY_ID = {s.id: s for s in STAGES}


def get(stage_id: str) -> Stage | None:
    return _BY_ID.get(stage_id)


def status(stage: Stage, cfg: Config) -> bool | None:
    """The stage's detection; a missing folder or a broken file never stops `aos next`."""
    try:
        return stage.done(cfg)
    except (OSError, ValueError, RoutineError, A.AgentError):
        return False


def text(stage: Stage) -> tuple[str, str, tuple[str, ...]]:
    """(title, why, steps) in the interface language."""
    return tr(stage.title), tr(stage.why), tuple(tr(s) for s in stage.steps)


def prompt_for(stage: Stage, cfg: Config) -> str:
    """The paste-ready prompt with the user's name and language in its first line."""
    name = cfg.user_name if cfg.user_name.casefold() not in _DEFAULT_NAMES else ""
    intro = (tr("I am {name}; reply to me in {language}.", name=name, language=cfg.language) if name
             else tr("Reply to me in {language}.", language=cfg.language))
    return f"{intro}\n\n{tr(stage.prompt)}{tr(GUARDRAILS)}"
