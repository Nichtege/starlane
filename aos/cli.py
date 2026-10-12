"""Command line: `python -m aos <command>`. Every routine calls exactly one of these commands."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from . import agentdefs as AD
from . import agents as A
from . import digest as D
from .config import INSTALLED, PROJECT_ROOT, SHIPPED_DIR, Config, Conventions, aos_cmd, home_dir, home_is_checkout, load_config
from .dates import now_local
from .mapcheck import run_checks
from . import artifacts as AR
from .skills import DEFAULT_MODEL, MODELS
from .routines import ALLOWED_COMMANDS, RoutineError, load_routines
from .scheduler import Busy, board, load_state, read_runs, run_now, tick, unblock
from .vault import Vault

STATUS_ICON = {
    "ok": "●", "due": "◐", "overdue": "◔", "failed": "✗", "blocked": "⛔",
    "never": "○", "disabled": "–", "elsewhere": "↗",
}

NEXT_HINT = "Next: `python -m aos next` (guided setup, see docs/getting-started.md)"


def _out(text: str = "") -> None:
    print(aos_cmd(text), flush=True)


def _scan(cfg: Config) -> Vault:
    return Vault.scan(cfg.vault, cfg.ignore)


def _safe_board(cfg: Config, now: datetime) -> list[dict]:
    try:
        return board(cfg, now)
    except RoutineError:
        return []


def _which(name: str) -> str | None:
    """PATH-only lookup (never the current folder, see agents.safe_which)."""
    return A.safe_which(name)


# --- Commands --------------------------------------------------------------------------
def cmd_init(cfg: Config, args) -> int:
    """Uses the conventions of the config that is found (--config, $AOS_CONFIG, aos.toml next to the project), else defaults."""
    from .scaffold import scaffold

    target = Path(args.folder).expanduser()
    created, skipped = scaffold(target, now_local().date(), cfg.conv)
    for rel in created:
        _out(f"  created  {rel}")
    for rel in skipped:
        _out(f"  skipped  {rel} (exists)")
    _out(f"Starter vault: {target.resolve()}")
    _out(f"Then: set [vault] path in aos.toml to this folder{' (`aos setup` makes it first)' if INSTALLED else ''}, run `python -m aos doctor`.")
    _out(NEXT_HINT)
    return 0


def cmd_setup(cfg: Config, args) -> int:
    """Copy the starter files (aos.toml, routines.toml, agents, skills, docs, demo vault) into your folder.

    Never overwrites: running it again after an upgrade only adds what is new."""
    from . import shipped

    if not args.folder and not INSTALLED:
        _out("Name the folder to set up, for example: python -m aos setup ~/agentic-os")
        return 2
    target = Path(args.folder).expanduser().resolve() if args.folder else home_dir()
    source = SHIPPED_DIR if INSTALLED else PROJECT_ROOT
    if source.resolve() == target:
        _out(f"This is the project folder itself ({target}); nothing to set up. Pass a different folder.")
        return 2
    if (target / ".obsidian").is_dir() and not (target / "aos.toml").exists():
        _out(f"{target} is an Obsidian vault: setup adds about fifty files of its own and would put them among your notes. "
             f"Name a new or empty folder (for example ~/agentic-os) and set [vault] path in its aos.toml to your notes.")
        return 2
    copied, skipped = shipped.copy(source, target)
    _out(f"Agentic OS folder: {target}  ({len(copied)} files added, {len(skipped)} kept as they are)")
    cfg_opt = ""
    if not INSTALLED or target != home_dir():
        conf = str(target / "aos.toml")
        conf = f'"{conf}"' if " " in conf else conf   # it is pasted into a terminal: quoted when the path has spaces
        cfg_opt = f"--config {conf} "
        _out(f"This is not the folder aos looks in by default: put `{cfg_opt.strip()}` before the command (python -m aos {cfg_opt}doctor), "
             f"or set AOS_CONFIG to {target / 'aos.toml'} (or AOS_HOME to {target}).")
    _out(f"Next: `python -m aos {cfg_opt}doctor`, then `python -m aos {cfg_opt}next`.")
    return 0


def cmd_digest(cfg: Config, args) -> int:
    now = now_local()
    vault = _scan(cfg)
    health = run_checks(vault, now.date(), cfg.large_file_kb, cfg.conv)
    data = D.build_today(vault, cfg, now.date(), now, health, _safe_board(cfg, now))
    written = D.write_digest(cfg, data, health, now.date(), now)
    _out(f"Digest {data['week']}: {len(data['needs'])} open items, {len(data['upcoming'])} dates; written: {', '.join(written) or 'nothing changed'}")
    return 0


def cmd_mapcheck(cfg: Config, args) -> int:
    now = now_local()
    vault = _scan(cfg)
    health = run_checks(vault, now.date(), cfg.large_file_kb, cfg.conv)
    D.write_if_changed(D.digest_base(cfg) / "vault-check.md",
                       D.render_health_markdown(health, now.date(), now, D.has_project_note(vault, cfg.conv), cfg.conv))
    c = health["counts"]
    _out(f"Vault check: {c['error']} errors, {c['warn']} warnings, {c['info']} notes; {health['stats']['within_two_hops_pct']} % within 2 hops")
    if args.verbose:
        for i in health["issues"]:
            if i["severity"] != "info" or args.verbose > 1:
                _out(f"  [{i['severity']}] {i['code']} {i['path']}:{i['line']} {i['message']}")
    return 1 if args.strict and c["error"] else 0


def cmd_dashboard(cfg: Config, args) -> int:
    from .dashboard import write_dashboard

    info = write_dashboard(cfg)
    _out(f"Dashboard: {info['html']} ({info['nodes']} nodes, {info['edges']} edges)")
    return 0


def cmd_tick(cfg: Config, args) -> int:
    results = tick(cfg)
    if not args.quiet:
        for r in results:
            _out(f"{r['status']:8} {r['id']}: {r['note'][:100]}")
        if not results:
            _out("Nothing started (nothing due, or another tick is running).")
    return 0


def cmd_run(cfg: Config, args) -> int:
    try:
        rec = run_now(cfg, args.id)
    except KeyError as exc:
        _out(str(exc.args[0]) if exc.args else str(exc))   # str(KeyError) would add quotes
        return 2
    except Busy as exc:
        _out(f"Not started: {exc}")
        return 3
    _out(f"{rec['status']} {rec['id']} in {rec['duration_s']} s: {rec['note'][:300]}")
    return 0 if rec["status"] == "ok" else 1


def cmd_status(cfg: Config, args) -> int:
    now = now_local()
    try:
        rows = board(cfg, now)
    except RoutineError as exc:
        _out(f"routines.toml: {exc}")
        return 1
    _out(f"Routines on {cfg.machine} ({now:%Y-%m-%d %H:%M})")
    last_tick = load_state(cfg).get("last_tick")
    _out(f" Last tick: {last_tick.replace('T', ' ')[:16]}" if last_tick else " Last tick: none recorded yet (schedule set up? `python -m aos install-task`)")
    for r in rows:
        nxt = (r["next_due"] or "")[5:16].replace("T", " ")
        last = (r["last_run"] or "")[5:16].replace("T", " ")
        _out(f" {STATUS_ICON.get(r['status'], '?')} {r['id']:<26} {r['status']:<9} last {last or '–':<11} next {nxt or '–':<11} {r['runs_today']}/{r['cap']} today")
        if r["status"] in ("failed", "blocked") and r["last_note"]:
            _out(f"     ↳ {r['last_note'][:160]}")
    runs = read_runs(cfg, 5)
    if runs:
        _out("Recent runs:")
        for x in runs:
            _out(f"   {x['started'][5:16].replace('T', ' ')} {x['id']:<24} {x['status']} ({x['duration_s']} s, {x['trigger']})")
    return 0


def cmd_unblock(cfg: Config, args) -> int:
    try:
        ok = unblock(cfg, args.id)
    except Busy as exc:
        _out(f"Not possible: {exc}. Try again in a moment.")
        return 3
    _out(f"{args.id}: unblocked" if ok else f"{args.id}: unknown or not blocked")
    return 0 if ok else 1


def cmd_serve(cfg: Config, args) -> int:
    from .server import serve

    return serve(cfg, port=args.port or cfg.server_port, open_browser=not args.no_browser)


def cmd_install_task(cfg: Config, args) -> int:
    from . import tasksched

    return tasksched.install(cfg, args.minutes)


def cmd_uninstall_task(cfg: Config, args) -> int:
    from . import tasksched

    return tasksched.uninstall()


def cmd_git_pull(cfg: Config, args) -> int:
    """Keeps the vault on this machine up to date. Only `pull --rebase --autostash`, never push."""
    if not (cfg.vault / ".git").exists():
        _out("The vault is not a git repository.")
        return 1
    git = _which("git")
    if not git:
        _out("git not found on PATH.")
        return 1
    proc = subprocess.run(
        [git, "-C", str(cfg.vault), "pull", "--rebase", "--autostash"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        # unattended: never ask for a password (otherwise the run hangs on an invisible prompt until the time limit)
        env=dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never"),
    )
    _out((proc.stdout or proc.stderr).strip()[-400:])
    return proc.returncode


CLAUDE_PROMPT = """You are Atlas, the coordinator agent for {user}. Write an honest DRAFT of the weekly review.
Read: {week_note}, {digest_dir}/ (the current digest) and, if present, the schedule notes for this week (file names containing "{schedule}"; only the section for the current week).
Compare the "{goal_heading}" section of the week note with what actually got done. Be honest, no sugarcoating. Name concretely what comes first next week
and how many days remain until the deadlines (recompute them from today's date {today}).
Output ONLY the text of the review, in {language}, Markdown, at most 25 lines, without frontmatter and without a preamble.
The first line is the heading: # Weekly review {week}. You only have read access; do not write any files.
Do not fill in the "{review_heading}" section; {user} does that."""

MAX_REVIEW_CHARS = 6000


def review_markdown(answer: str, today, week: str, has_project_note: bool, conv: Conventions | None = None) -> str:
    """Check Claude's answer and format it as a vault note. Claude never writes itself: only this code writes the file."""
    import re

    from .mapcheck import redact

    body = redact(answer.strip())
    body = re.sub(r"^---.*?---\s*", "", body, count=1, flags=re.S)  # drop accidental frontmatter
    if not body or len(body) > MAX_REVIEW_CHARS:
        raise ValueError("answer empty or too long")
    lines = body.splitlines()
    title = lines[0] if lines[0].startswith("# ") else f"# Weekly review {week}"
    rest = lines[1:] if lines[0].startswith("# ") else lines
    head = D._header({"date": today.isoformat(), "has_project_note": has_project_note}, "digest, auto, review", title,
                     "Draft by Claude (read-only), generated by `aos claude-digest`: check before trusting it", conv or Conventions())
    return "\n".join(head + rest[:40]).rstrip() + "\n"


def cmd_claude_digest(cfg: Config, args) -> int:
    """Optional (off in routines.toml): Claude headless, read-only. This code writes the file, not Claude."""
    exe, why = A.find_claude(cfg.vault)  # rejects batch wrappers: cmd.exe would cut the prompt at the first line break
    if not exe:
        _out(f"Aborted: {why}")
        return 1
    capped = A.daily_cap_reached(cfg, now_local())
    if capped:
        _out(f"Aborted: {capped}")
        return 1
    from .dates import iso_week_name

    today = now_local().date()
    week = iso_week_name(today)
    prompt = CLAUDE_PROMPT.format(
        user=cfg.user_name,
        language=cfg.language,
        week=week,
        today=today.isoformat(),
        week_note=cfg.conv.week_note(today),
        digest_dir=cfg.digest_dir,
        schedule=cfg.conv.schedule_keyword,
        goal_heading=cfg.conv.week_goal_heading,
        review_heading=cfg.conv.weekly_review_heading,
    )
    cmd = [
        exe, "-p", prompt,
        "--model", "sonnet",
        "--max-budget-usd", "10",
        "--no-session-persistence",
        "--permission-mode", "dontAsk",
        "--strict-mcp-config",  # load no connectors (Gmail, Notion, ...)
        "--setting-sources", "user",  # no hooks/permissions from the vault folder
        "--tools", "Read,Glob,Grep",  # no Write, no shell, no internet
        "--allowedTools", "Read(./**)",  # not Grep/Glob on their own: a bare "Grep" allows the whole file system
    ]
    proc = subprocess.run(cmd, cwd=cfg.vault, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=540)
    if proc.returncode != 0:
        _out((proc.stderr or proc.stdout).strip()[-500:])
        return proc.returncode
    try:
        text = review_markdown(proc.stdout, today, week, D.has_project_note(_scan(cfg), cfg.conv), cfg.conv)
    except ValueError as exc:
        _out(f"Answer discarded: {exc}")
        return 1
    target = D.digest_base(cfg) / "weekly-review.md"
    changed = D.write_if_changed(target, text)
    _out(f"Weekly review {'written' if changed else 'unchanged'}: {target.relative_to(cfg.vault).as_posix()}")
    return 0

def cmd_agents(cfg: Config, args) -> int:
    rows = A.board(cfg)
    if not rows:
        _out(f"No agents (agents.toml missing or empty: {cfg.agents_file})")
        return 0
    width = max(12, *(len(a["id"]) for a in rows))  # custom ids can be longer than the shipped ones
    for a in rows:
        state = "off" if not a["enabled"] else ("working" if a["busy"] else "ready")
        own = " (custom)" if a.get("custom") else ""
        _out(f" {a['id']:<{width}} {state:<9} {a['runs_today']}/{a['cap']} today  {a['description']}{own}")
    _out('Give a task: python -m aos agent <id> "What should I do?"')
    return 0


def cmd_agent(cfg: Config, args) -> int:
    try:
        job = A.submit(cfg, args.id, args.instruction, via="cli", wait=True)
    except KeyError as exc:
        _out(str(exc).strip("'\""))
        return 2
    except A.Refused as exc:
        _out(f"Refused: {exc}")
        return 3
    _out(job["result"] or f"{job['status']}: {job['note']}")
    _out()
    _out(f"[{job['status']} · {job['agent']} · {job['duration_s']} s · job {job['id']}]")
    return 0 if job["status"] == "ok" else 1

def _ask(label: str, default: str = "") -> str:
    shown = f" [{default}]" if default else ""
    try:
        return input(f"{label}{shown}: ").strip() or default
    except EOFError:
        return default


def _ask_lines(label: str) -> str:
    """Multi-line input, ended by an empty line."""
    _out(f"{label} (an empty line ends the input):")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip() and lines:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def cmd_agent_new(cfg: Config, args) -> int:
    """Create a custom agent: with options, or (without --name, in a terminal) as a question-and-answer dialog."""
    if args.template:
        _out(AD.TEMPLATE)
        return 0
    if args.name is None:
        if not sys.stdin.isatty():
            _out("Error: --name is missing. Without options `aos agent-new` asks in the terminal; `--template` prints a template for the instructions.")
            return 2
        _out("New agent. Leave empty = default in [square brackets].")
        raw = {
            "name": _ask("Name"),
            "description": _ask("Description (what it is for, and what not: Atlas picks agents by this)"),
            "access": _ask("Access: vault (read notes) or web (web search)", "vault"),
            "group": _ask("Field", AD.CUSTOM_GROUP),
            "model": _ask("Model (" + ", ".join(MODELS) + ")", DEFAULT_MODEL),
            "keywords": _ask("Keywords, comma-separated (optional)"),
            "instructions": _ask_lines("Instructions (role, way of working, limits)"),
        }
    else:
        instructions = args.instructions or ""
        if args.instructions_file:
            instructions = Path(args.instructions_file).read_text(encoding="utf-8")
        raw = {"name": args.name, "description": args.description or "", "instructions": instructions,
               "access": "web" if args.web else "vault", "group": args.group or "", "model": args.model or "sonnet",
               "keywords": args.keyword or [], "examples": args.example or []}
        if args.timeout is not None:
            raw["timeout_s"] = args.timeout
        if args.cap is not None:
            raw["max_runs_per_day"] = args.cap
    try:
        agent = AD.create(cfg, raw, agent_id=args.id)
    except A.Refused as exc:
        _out(f"Refused: {exc}")
        return 3
    _out(f"Agent '{agent.id}' ({agent.name}) created: {AD.local_file(cfg).name}, prompt {agent.prompt_file.relative_to(cfg.agents_file.parent).as_posix()}")
    _out(f'Try it: python -m aos agent {agent.id} "What can you do for me?"')
    return 0


def cmd_agent_rm(cfg: Config, args) -> int:
    try:
        known = AD.read(cfg, args.id)
    except KeyError as exc:
        _out(str(exc).strip("'\""))
        return 2
    except A.Refused as exc:
        _out(f"Refused: {exc}")
        return 3
    if not args.yes:
        if not sys.stdin.isatty():
            _out("To delete without confirmation, pass --yes.")
            return 2
        if _ask(f"Really delete agent '{known['name']}' ({args.id})? (yes/no)", "no").lower() not in ("y", "yes"):
            _out("Nothing deleted.")
            return 0
    try:
        AD.delete(cfg, args.id)
    except A.Refused as exc:
        _out(f"Refused: {exc}")
        return 3
    _out(f"Agent '{args.id}' deleted.")
    return 0


def cmd_skills(cfg: Config, args) -> int:
    rows = A.skills_board(cfg)
    if not rows:
        _out("No skills found. Create a folder with a SKILL.md in: " + ", ".join(str(d) for d in cfg.skills_dirs))
        return 0
    for s in rows:
        state = "working" if s["busy"] else "ready"
        _out(f" {s['id']:<18} {state:<9} {s['runs_today']}/{s['cap']} today  {s['model']}/{s['effort'] or 'std'}  {s['source']:<8} {s['description']}")
    _out('Start: python -m aos skill <id> "task" [--model haiku|sonnet|opus|fable] [--effort low|medium|high|xhigh|max]')
    return 0


def cmd_skill(cfg: Config, args) -> int:
    try:
        job = A.submit_skill(cfg, args.id, args.instruction, model=args.model, effort=args.effort, via=args.via, wait=True)
    except KeyError as exc:
        _out(str(exc).strip("'\""))
        return 2
    except A.Refused as exc:
        _out(f"Refused: {exc}")
        return 3
    _out(job["result"] or f"{job['status']}: {job['note']}")
    _out()
    cost = f" · ${job['cost_usd']:.4f}" if job.get("cost_usd") is not None else ""
    _out(f"[{job['status']} · {job['agent']} · {job.get('model')}/{job.get('effort') or 'std'} · {job['duration_s']} s{cost} · job {job['id']}]")
    return 0 if job["status"] == "ok" else 1


def cmd_artifacts(cfg: Config, args) -> int:
    q = (args.query or "").casefold()
    rows = [a for a in AR.list_artifacts(cfg) if q in f"{a['title']} {a['group']} {a['path']} {a['excerpt']}".casefold()]
    if not rows:
        _out("No artifacts found." if q else "No artifacts yet.")
    for a in rows[: args.n]:
        _out(f" {a['id']} {a['mtime'][:16].replace('T', ' ')} {a['kind']:<5} {a['group']:<22} {a['title']}")
    return 0


def cmd_spend(cfg: Config, args) -> int:
    s = A.spend(cfg)
    _out(f"Today ${s['today_usd']:.4f} · 7 days ${s['week_usd']:.4f} ({s['week_runs']} runs) · month ${s['month_usd']:.4f}")
    for d in s["days"]:
        bar = "#" * min(40, round(d["usd"] / max(s["week_usd"], 0.0001) * 40))
        _out(f" {d['date']} ${d['usd']:.4f} {bar}")
    for r in s["by_agent"]:
        _out(f" {r['id']:<24} ${r['usd']:.4f} in {r['runs']} runs")
    return 0


def cmd_jobs(cfg: Config, args) -> int:
    if args.id:
        job = A.get_job(cfg, args.id)
        if not job:
            _out(f"Unknown job: {args.id}")
            return 2
        _out(f"{job['agent']} · {job['status']} · {job['started']} · {job.get('duration_s')} s")
        _out(f"Task: {job['instruction']}")
        _out()
        _out(job.get("result") or job.get("note") or "")
        return 0
    jobs = A.all_jobs(cfg)[: args.n]
    if not jobs:
        _out("No jobs yet.")
    for j in jobs:
        first = j["instruction"].splitlines()[0][:60] if j.get("instruction") else ""
        _out(f" {j['id']} {(j.get('started') or '')[5:16].replace('T', ' ')} {j['agent']:<12} {j['status']:<8} {first}")
    return 0


def cmd_doctor(cfg: Config, args) -> int:
    problems = 0

    def check(ok: bool, label: str, detail: str = "", fatal: bool = True) -> None:
        nonlocal problems
        mark = "✓" if ok else ("✗" if fatal else "!")
        if not ok and fatal:
            problems += 1
        _out(f" {mark} {label}" + (f": {detail}" if detail else ""))

    _out(f"Agentic OS {__version__} · Python {sys.version.split()[0]} · machine {cfg.machine}")
    check(sys.version_info >= (3, 11), "Python >= 3.11")
    check(cfg.config_file is not None, "aos.toml found", str(cfg.config_file or "defaults"), fatal=False)
    check(cfg.vault.is_dir(), "Vault exists", str(cfg.vault))
    if cfg.vault.is_dir():
        vault = _scan(cfg)
        check(len(vault.notes) > 0, "Notes read", str(len(vault.notes)))
        for root in cfg.conv.roots:
            check(root in vault.notes, f"Entry note {root}", "" if root in vault.notes else "missing: the two-hop rule starts here", fatal=False)
        health = run_checks(vault, now_local().date(), cfg.large_file_kb, cfg.conv)
        c = health["counts"]
        check(c["error"] == 0, "Vault check without errors", f"{c['error']} errors, {c['warn']} warnings, {c['info']} notes")
        check(health["stats"]["within_two_hops_pct"] >= 90, "Two-hop rule", f"{health['stats']['within_two_hops_pct']} %", fatal=False)
    try:
        routines = load_routines(cfg.routines_file)
        check(True, "routines.toml valid", f"{len(routines)} routines, {sum(r.enabled for r in routines)} enabled")
        bad = [r.id for r in routines if r.command not in ALLOWED_COMMANDS]
        check(not bad, "Only allowed commands", ", ".join(bad))
    except RoutineError as exc:
        check(False, "routines.toml", str(exc))
    try:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        probe = cfg.data_dir / ".probe"
        probe.write_text("x")
        probe.unlink()
        check(True, "Data folder writable", str(cfg.data_dir))
    except OSError as exc:
        check(False, "Data folder writable", str(exc))
    try:
        D.digest_base(cfg)  # created on the first digest; it only has to stay inside an existing vault
        check(cfg.vault.is_dir(), "Digest folder can be created", cfg.digest_dir)
    except ValueError as exc:
        check(False, "Digest folder can be created", str(exc))
    check(_which("git") is not None, "git installed", fatal=False)
    try:
        agents = A.load_agents(cfg.agents_file)
        check(bool(agents), "agents.toml valid, prompts present", f"{len(agents)} agents" if agents else f"no agents ({cfg.agents_file})", fatal=bool(agents))
    except A.AgentError as exc:
        check(False, "agents.toml", str(exc))
    from . import skills as S

    found = S.discover(cfg)
    check(True, "Skills found", f"{len(found)}" if found else "none (create skills/<name>/SKILL.md)", fatal=False)
    try:
        known = {s.id for s in found}
        missing = [f"{r.id} -> {r.skill}" for r in load_routines(cfg.routines_file) if r.skill and r.skill not in known]
        check(not missing, "Skill routines point to existing skills", ", ".join(missing))
    except RoutineError:
        pass  # already reported above
    exe, why = A.find_claude(cfg.vault)
    check(exe is not None, "claude CLI (for agents and the optional Claude routine)", why, fatal=False)
    from . import tasksched

    check(tasksched.is_installed(), "Scheduled task registered (aos install-task)", fatal=False)
    _out("All good." if not problems else f"{problems} problem(s) found.")
    if not problems:
        _out(NEXT_HINT)
    return 1 if problems else 0


NEXT_MARK = {True: "✓", None: "·"}


def _stage_details(cfg: Config, stage, n: int) -> None:
    from . import onboarding as O

    _out()
    _out(f"── {n}. {stage.title} ({stage.id}) ──")
    _out(stage.why)
    _out()
    for i, step in enumerate(stage.steps, 1):
        _out(f"  {i}. {step}")
    _out()
    _out(f"Or let Claude Code do it: paste this into `claude` opened in this folder (or: python -m aos next --prompt --stage {stage.id}):")
    _out("----- BEGIN PROMPT -----")
    _out(O.prompt_for(stage, cfg))
    _out("----- END PROMPT -----")


def cmd_next(cfg: Config, args) -> int:
    """Getting started: a checklist of the onboarding stages and the details of the next open one. Reads nothing but
    existence checks, the jobs log line count and routines.toml; starts nothing."""
    from . import onboarding as O

    if args.stage and O.get(args.stage) is None:
        _out(f"Unknown stage: {args.stage}. Known: {', '.join(s.id for s in O.STAGES)}")
        return 2
    states = [O.status(s, cfg) for s in O.STAGES]
    nxt = next((i for i, st in enumerate(states) if st is False), None)
    chosen = [O.STAGES.index(O.get(args.stage))] if args.stage else (list(range(len(O.STAGES))) if args.all else
                                                                      ([nxt] if nxt is not None else []))
    if args.prompt:
        if not chosen:
            print("Every stage is done. Pick one with --stage <id>.", file=sys.stderr)
            return 0
        _out(O.prompt_for(O.STAGES[chosen[0]], cfg))
        return 0
    _out(f"Getting started ({sum(st is True for st in states)} of {len(states)} done)")
    for i, (stage, st) in enumerate(zip(O.STAGES, states)):
        mark = "→" if i == nxt else NEXT_MARK.get(st, "○")
        _out(f" {mark} {i + 1:>2}. {stage.id:<12} {stage.title}")
    _out(" ✓ done  → next  ○ later  · manual or optional")
    if not chosen:
        _out()
        _out("All detectable stages are done. Details of any stage: python -m aos next --stage <id>")
    for i in chosen:
        _stage_details(cfg, O.STAGES[i], i + 1)
    return 0


# --- Parser ----------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aos", description="Agentic OS for a Markdown vault and Claude Code")
    p.add_argument("--config", help="path to aos.toml (default: $AOS_CONFIG; after `pip install` the aos.toml in $AOS_HOME or ~/agentic-os; "
                                    "in a clone the one in the project folder)")
    p.add_argument("--version", action="version", version=f"aos {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")
    ini = sub.add_parser("init", help="create a starter vault in <folder> (never overwrites)")
    ini.add_argument("folder", help="target folder, created if missing")
    ini.set_defaults(fn=cmd_init)
    st = sub.add_parser("setup", help="copy the starter files into your folder ($AOS_HOME, default ~/agentic-os; never overwrites)")
    st.add_argument("folder", nargs="?", help="another folder than $AOS_HOME")
    st.set_defaults(fn=cmd_setup)
    sub.add_parser("digest", help="write the digest (into the digest folder, default AI/Digest)").set_defaults(fn=cmd_digest)
    m = sub.add_parser("mapcheck", help="vault check (links, two-hop rule, frontmatter, secrets)")
    m.add_argument("-v", "--verbose", action="count", default=0)
    m.add_argument("--strict", action="store_true", help="exit code 1 on errors")
    m.set_defaults(fn=cmd_mapcheck)
    sub.add_parser("dashboard", help="build the dashboard file (data/out/dashboard.html)").set_defaults(fn=cmd_dashboard)
    t = sub.add_parser("tick", help="run due routines (called every 5 minutes by the scheduler)")
    t.add_argument("--quiet", action="store_true")
    t.set_defaults(fn=cmd_tick)
    r = sub.add_parser("run", help="run one routine now")
    r.add_argument("id")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("status", help="routine board in the terminal").set_defaults(fn=cmd_status)
    u = sub.add_parser("unblock", help="release a blocked routine")
    u.add_argument("id")
    u.set_defaults(fn=cmd_unblock)
    s = sub.add_parser("serve", help="live dashboard at http://127.0.0.1:8765 (local only)")
    s.add_argument("--port", type=int)
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_serve)
    i = sub.add_parser("install-task", help="set up the schedule (Windows task, every 5 minutes)")
    i.add_argument("--minutes", type=int, default=5)
    i.set_defaults(fn=cmd_install_task)
    sub.add_parser("uninstall-task", help="remove the schedule again").set_defaults(fn=cmd_uninstall_task)
    sub.add_parser("doctor", help="self-test of the setup").set_defaults(fn=cmd_doctor)
    nx = sub.add_parser("next", help="getting started: what to set up next, with a prompt for Claude Code")
    nx.add_argument("--all", action="store_true", help="details of every stage")
    nx.add_argument("--stage", help="details of one stage (vault, obsidian, claude, digest, ...)")
    nx.add_argument("--prompt", action="store_true", help="print only the prompt of the next (or --stage) stage")
    nx.set_defaults(fn=cmd_next)
    sub.add_parser("agents", help="list the agents from agents.toml").set_defaults(fn=cmd_agents)
    ag = sub.add_parser("agent", help='give an agent a task: aos agent research "question"')
    ag.add_argument("id")
    ag.add_argument("instruction")
    ag.set_defaults(fn=cmd_agent)
    an = sub.add_parser("agent-new", help="create a custom agent (without --name: dialog in the terminal)")
    an.add_argument("--name", help="display name, e.g. 'Travel planner'")
    an.add_argument("--id", help="ID (a-z, 0-9, hyphen); default: derived from the name")
    an.add_argument("--description", help="what it is responsible for, and what not (Atlas picks agents by this)")
    an.add_argument("--instructions", help="instructions as text")
    an.add_argument("--instructions-file", help="instructions from a Markdown file")
    an.add_argument("--web", action="store_true", help="web search instead of reading notes (never both)")
    an.add_argument("--group", help=f"field in the Atlas view (default: {AD.CUSTOM_GROUP})")
    an.add_argument("--model", help="haiku | sonnet | opus | fable (default: sonnet)")
    an.add_argument("--keyword", action="append", help="keyword for routing (repeatable)")
    an.add_argument("--example", action="append", help="example task shown as a suggestion in the dashboard (up to 4)")
    an.add_argument("--timeout", type=int, help="time limit per task in seconds (30 to 900)")
    an.add_argument("--cap", type=int, help="tasks per day (1 to 200)")
    an.add_argument("--template", action="store_true", help="print a template for the instructions and exit")
    an.set_defaults(fn=cmd_agent_new)
    ar_ = sub.add_parser("agent-rm", help="delete a custom agent (shipped ones stay)")
    ar_.add_argument("id")
    ar_.add_argument("--yes", action="store_true", help="without confirmation")
    ar_.set_defaults(fn=cmd_agent_rm)
    sub.add_parser("skills", help="list skills (skills/<name>/SKILL.md)").set_defaults(fn=cmd_skills)
    sk = sub.add_parser("skill", help='start a skill: aos skill weekly-plan "plan for this week" --model sonnet --effort high')
    sk.add_argument("id")
    sk.add_argument("instruction")
    sk.add_argument("--model", help="haiku | sonnet | opus | fable (default: the skill's own)")
    sk.add_argument("--effort", help="low | medium | high | xhigh | max (default: the skill's own)")
    sk.add_argument("--via", choices=("cli", "routine"), default="cli", help=argparse.SUPPRESS)
    sk.set_defaults(fn=cmd_skill)
    ar = sub.add_parser("artifacts", help="search the artifact library")
    ar.add_argument("query", nargs="?")
    ar.add_argument("-n", type=int, default=30)
    ar.set_defaults(fn=cmd_artifacts)
    sub.add_parser("spend", help="what the runs cost (today, 7 days, month)").set_defaults(fn=cmd_spend)
    j = sub.add_parser("jobs", help="recent agent jobs (with <id>: the full answer)")
    j.add_argument("id", nargs="?")
    j.add_argument("-n", type=int, default=15)
    j.set_defaults(fn=cmd_jobs)
    sub.add_parser("git-pull", help="update the vault (git pull --rebase)").set_defaults(fn=cmd_git_pull)
    sub.add_parser("claude-digest", help="optional: weekly review draft by Claude (headless)").set_defaults(fn=cmd_claude_digest)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        if home_is_checkout() and not (args.config or os.environ.get("AOS_CONFIG")) and args.cmd != "init" \
                and not (args.cmd == "setup" and args.folder):
            # print, not _out: inside that project the command that works is `python -m aos`, not `aos`
            print(f"{home_dir()} holds a copy of the Agentic OS code, so it is a working project and not a folder `aos setup` made. "
                  f"Set AOS_HOME to a folder of its own (aos setup ~/my-aos, then AOS_HOME=~/my-aos), or run `python -m aos` inside that project.",
                  flush=True)
            return 2
        cfg = load_config(args.config)  # a missing file means defaults (init needs no config)
        if INSTALLED and cfg.config_file is None and args.cmd not in ("setup", "init"):
            asked = args.config or os.environ.get("AOS_CONFIG")
            if asked:
                _out(f"No config file at {Path(asked).expanduser()}. Check the path (write it in full, for example C:/Users/you/folder/aos.toml).")
            else:
                _out(f"No aos.toml in {home_dir()}. Run `aos setup` first (or point --config / $AOS_CONFIG / $AOS_HOME at your folder).")
            return 2
        return args.fn(cfg, args)
    except (RoutineError, A.AgentError, FileNotFoundError, ValueError, OSError) as exc:  # ValueError: e.g. a broken aos.toml
        _out(f"Error: {exc}")
        return 1
    except subprocess.TimeoutExpired as exc:
        _out(f"Timed out: {exc}")
        return 1
