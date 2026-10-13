"""Screen: one data JSON for everything, one HTML dashboard that stores nothing (show, don't store).

Data contract (`data.json`, version 1); everything is read from files:
  version, generated (ISO), today (YYYY-MM-DD), machine
  user    {name}                      cfg.user_name, for greetings
  vault   {name, uri}                 uri + path without ".md" opens the note in Obsidian
  nodes   [{id,label,kind,area,type,status,project,deadline,tags,size,words,mtime,in,out}]
          type/status/project/deadline/tags are read through the [conventions] keys; project = link target or ""
  edges   [{s,t,w}]
  changes {YYYY-MM-DD: [id,...]}      file changes per day (timeline); the digest folder is left out
  digest  {date,weekday,week,week_start,week_end,generated,horizon_days,has_project_note,deadlines,week_goals,
           upcoming,needs,recent,sessions,health,routines}
  health  {counts,stats,issues:[{severity,code,path,line,message}]}
  routines [{id,description,schedule,machine,enabled,status,last_run,last_ok,last_note,next_due,...,
             history:[{started,status,duration_s,trigger}]}]   history: latest runs of this routine, oldest first
  runs    [{id,trigger,slot,started,finished,duration_s,status,rc,note,machine}]   the last 150 runs of all routines
  last_tick ISO or null               last scheduler tick (sign of life of the schedule; null = never ran)
  agents  [{id,name,description,model,tools,enabled,timeout_s,cap,runs_today,busy,keywords,group,web,examples,custom}]
          agents from agents.toml plus custom agents (custom true: agents.local.toml + agents/local/<id>.md);
          examples = sample instructions; broken agents.toml: one row with id "agents.toml", enabled false,
          the error text in description
  jobs    [{id,agent,instruction,status,started,finished,duration_s,result,note,via}]   last 30 jobs,
          newest first; status running|ok|failed|timeout|refused, result = Markdown text (redacted, shortened),
          finished/duration_s null while running, via "server"|"cli"
  jobs[]  additionally (skill runs / billed runs only): skill, model, effort, cost_usd, tokens_in, tokens_out, model_used
  skills  [{id,name,description,source,refs:[file names],model,effort,cap,runs_today,busy,
            last:{id,status,finished,cost_usd}|null}]   skill deck; source "project"|"user"; effort "" = default
  options {models:["haiku","sonnet","opus","fable"], efforts:["low","medium","high","xhigh","max"]}   allowed values per run
  spend   {today_usd,week_usd,month_usd,week_runs,days:[{date,usd}] (7 days, oldest first),by_agent:[{id,usd,runs}]}
  artifacts [{id,title,kind:"html"|"md"|"job",group,path,mtime,size,excerpt}]   newest first, at most 300
  conventions {dirs:{projects,areas,journal,inbox,ideas,resources,ai,archive}, brain_map, index_note, status_done,
          digest_dir}   how the vault is organised ([conventions]); the page falls back to the English defaults

The page text itself is not part of the data: render_html embeds the "web" section of the locale ([user] ui_language) as
<script id="aos-i18n">, and translates the {{t:...}} markers of the static HTML (aos/i18n.py, docs/languages.md).
  api     null (file mode, view only) or (server mode)
          {token, run: "/api/run/", data: "/api/data", agents: "/api/agents/", jobs: "/api/jobs", atlas: "/api/atlas",
           skills: "/api/skills/" (POST /api/skills/<id> {instruction, model?, effort?}),
           artifact: "/api/artifact/" (GET /api/artifact/<id> -> {ok, artifact:{...entry, content}}),
           agent_defs: "/api/agent-defs" (POST create a custom agent; /api/agent-defs/<id>: GET read, POST update, DELETE)}
"""

from __future__ import annotations

import html as _html
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from . import agents as A
from . import artifacts as AR
from . import digest as D
from . import skills as S
from .config import Config
from .graph import build_graph, changes_by_day
from .i18n import web_catalog
from .mapcheck import run_checks
from .routines import RoutineError
from .scheduler import MAX_LOG_LINES, board, load_state, read_runs
from .vault import Vault

TEMPLATE = Path(__file__).resolve().parent / "web" / "dashboard.html"
MAX_INFO_ISSUES = 120
HISTORY_PER_ROUTINE = 20
RECENT_RUNS = 150


def build_data(cfg: Config, now: datetime | None = None, api: dict | None = None) -> dict:
    now = now or datetime.now().replace(microsecond=0)
    today = now.date()
    vault = Vault.scan(cfg.vault, cfg.ignore)
    health = run_checks(vault, today, cfg.large_file_kb, cfg.conv)
    try:
        routines = board(cfg, now)
    except RoutineError as exc:
        routines = [{"id": "routines.toml", "description": str(exc), "status": "failed", "schedule": "", "machine": "", "enabled": False,
                     "last_run": None, "last_ok": None, "last_note": str(exc), "next_due": None, "fail_streak": 0, "runs_today": 0, "cap": 0}]
    runs = read_runs(cfg, MAX_LOG_LINES)  # whole log: the 15-minute dashboard run would otherwise push daily routines out
    for r in routines:
        own = [x for x in runs if x.get("id") == r["id"]][-HISTORY_PER_ROUTINE:]
        r["history"] = [{k: x.get(k) for k in ("started", "status", "duration_s", "trigger")} for x in own]
    try:
        agents = A.board(cfg, now)
    except A.AgentError as exc:
        agents = [{"id": "agents.toml", "name": "agents.toml", "description": str(exc), "model": "", "tools": [], "enabled": False,
                   "timeout_s": 0, "cap": 0, "runs_today": 0, "busy": False}]
    try:
        skills = A.skills_board(cfg, now)
    except OSError:
        skills = []
    graph = build_graph(vault, cfg.conv)
    hidden = {n["id"] for n in graph["nodes"] if n["id"].startswith(f"{cfg.digest_dir}/{cfg.conv.digest_archive}/")}
    nodes = [n for n in graph["nodes"] if n["id"] not in hidden]
    edges = [e for e in graph["edges"] if e["s"] not in hidden and e["t"] not in hidden]
    issues = [i for i in health["issues"] if i["severity"] != "info"] + [i for i in health["issues"] if i["severity"] == "info"][:MAX_INFO_ISSUES]
    return {
        "version": 1,
        "generated": now.isoformat(timespec="seconds"),
        "today": today.isoformat(),
        "machine": cfg.machine,
        "user": {"name": cfg.user_name},
        "vault": {"name": cfg.vault_name, "uri": f"obsidian://open?vault={quote(cfg.vault_name)}&file="},
        "nodes": nodes,
        "edges": edges,
        "changes": changes_by_day(vault, (f"{cfg.digest_dir}/",)),
        "digest": D.build_today(vault, cfg, today, now, health, routines),
        "health": {"counts": health["counts"], "stats": health["stats"], "issues": issues},
        "routines": routines,
        "runs": runs[-RECENT_RUNS:],
        "last_tick": load_state(cfg).get("last_tick"),
        "agents": agents,
        "jobs": A.all_jobs(cfg)[: A.JOBS_SHOWN],
        "skills": skills,
        "options": {"models": list(S.MODELS), "efforts": list(S.EFFORTS)},
        "spend": A.spend(cfg, now),
        "artifacts": AR.list_artifacts(cfg),
        "conventions": conventions(cfg),
        "api": api,
    }


def conventions(cfg: Config) -> dict:
    """The parts of [conventions] the page needs to sort notes into areas and rings."""
    c = cfg.conv
    dirs = {k: getattr(c, f"{k}_dir") for k in ("projects", "areas", "journal", "inbox", "ideas", "resources", "ai", "archive")}
    return {"dirs": dirs, "brain_map": c.brain_map, "index_note": c.index_note, "status_done": c.status_done, "digest_dir": c.digest_dir}


def _json_for_html(data: dict) -> str:
    """Embed JSON safely in a <script> tag (titles from the vault may contain '</script>')."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


I18N_MARKER = "__AOS_I18N__"
TEXT_MARKER = re.compile(r"\{\{t:(.+?)\}\}")  # static page text: {{t:English}} -> translation (HTML-escaped)


def render_html(data: dict, template: Path = TEMPLATE, lang: str | None = None) -> str:
    """The page in the interface language (default: the current one, see i18n.use). The data goes in last, so nothing
    from the vault can ever be taken for a text marker."""
    html = template.read_text(encoding="utf-8")
    marker = "__AOS_DATA__"
    if marker not in html:
        raise ValueError(f"Placeholder {marker} is missing in {template}")
    cat = web_catalog(lang)
    strings = cat["strings"]

    def text(m: re.Match) -> str:
        source = _html.unescape(m.group(1))
        return _html.escape(strings.get(source, source), quote=True)

    html = TEXT_MARKER.sub(text, html)
    html = html.replace('<html lang="en">', f'<html lang="{cat["lang"]}">', 1)
    html = html.replace(I18N_MARKER, _json_for_html(cat), 1)
    html = html.replace(marker, _json_for_html(data), 1)
    return html


def write_dashboard(cfg: Config, now: datetime | None = None) -> dict:
    data = build_data(cfg, now)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    D.write_if_changed(cfg.out_dir / "data.json", json.dumps(data, ensure_ascii=False, indent=1))
    html_path = cfg.out_dir / "dashboard.html"
    D.write_if_changed(html_path, render_html(data))
    return {"html": str(html_path), "json": str(cfg.out_dir / "data.json"), "nodes": len(data["nodes"]), "edges": len(data["edges"])}
