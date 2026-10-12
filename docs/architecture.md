# Architecture

Starlane is a small operating layer around two things you already have: a folder of Markdown notes (the *vault*) and Claude Code running headless (`claude -p`). It reads the vault, runs routines on a schedule, lets read-only agents answer questions, and shows everything in a local dashboard. This page is for contributors: how it is built, why, and where to find things.

## Design principles
- **Standard library only.** Python 3.11+, no dependencies. It is written for Windows, macOS and Linux, on a laptop or a small server. Day to day it has been used on Windows. The test suite and a clean `pip install` run on Linux, macOS and Windows (Python 3.11 to 3.13) in GitHub Actions on every push; the POSIX-only parts (process groups, the cron line, Unicode file names) are also tested with the platform patched. The dashboard and the agents (which need `claude`) have only been tried by hand on Windows, so reports from macOS and Linux are welcome.
- **The vault is the truth.** Everything generated lands in `AI/Digest/` (inside the vault) or `data/` (inside the project). The system never changes or deletes a note of yours.
- **Show, don't store.** The dashboard reads files and renders them; it keeps no database of its own.
- **Read-only by construction.** Routines name commands from a whitelist, agents and skills get read and search tools only, the server listens on `127.0.0.1` only. Every routine and every agent run has time, daily and failure limits. See [security.md](security.md).
- **Configurable, not personal.** User name, interface and reply language and every vault convention (folder names, frontmatter keys, status words) come from `aos.toml`. See [vault-conventions.md](vault-conventions.md) and [languages.md](languages.md).
- **Honest limits.** Where a protection has a ceiling, the code and the docs say so.

## The four layers (MAPS)
| Layer | What it does | Modules |
|---|---|---|
| **M**emory | Read the vault, resolve wikilinks, check reachability (every note within two hops of `index.md` / `AI/brain-map.md`), validate frontmatter, scan for secrets | `vault.py`, `mapcheck.py`, `dates.py` |
| **A**gent | The same code on several machines (Git sync), routines pinned per machine, specialist agents and Atlas, skills, tool locks | `config.py`, `agents.py`, `agentdefs.py`, `skills.py`, [vps-setup.md](vps-setup.md) |
| **P**ulse | `routines.toml`, a scheduler with due times, daily caps, circuit breaker, run log, OS task installation | `routines.py`, `scheduler.py`, `tasksched.py`, `digest.py`, `aos_tick.pyw` |
| **S**creen | One data JSON, one HTML dashboard (home, today, Atlas, artifacts, rings, links, timeline, health, skills), a local server | `graph.py`, `dashboard.py`, `artifacts.py`, `server.py`, `web/dashboard.html` |

A fifth concern, **skills**, sits across Agent and Pulse: a skill is a recipe (`skills/<id>/SKILL.md` plus reference files) that runs with the same lock as an agent and can be scheduled like a routine. See [skills.md](skills.md).

## Module map
| Module | Responsibility |
|---|---|
| `aos/config.py` | Loads `aos.toml` (or `AOS_CONFIG`), resolves paths, holds `Config` and `Conventions`. Decides between *checkout* (the project folder is the code folder) and *installed* (a wheel: the user's folder `$AOS_HOME`, default `~/starlane`, is the project root). |
| `aos/shipped.py` | The list of starter files (`aos.toml`, routines, agents, skills, docs, the demo vault) with what never ships. `aos setup` copies them, never overwriting; `setup.py` bundles the same list into the wheel as `aos/_shipped`, and `MANIFEST.in` mirrors it for the sdist. |
| `aos/i18n.py` | The interface language: `tr`, `trc` (with a context), `trn` (singular/plural) and `tr_mark` look English source texts up in `aos/locales/<code>.json` and fall back to English. The CLI switches the process language once from `[user] ui_language`; `dashboard.render_html` embeds the locale's `web` section for the page. See [languages.md](languages.md). |
| `aos/vault.py` | Walks the vault, parses frontmatter and wikilinks, builds the link index. Never writes. |
| `aos/dates.py` | Date parsing (ISO, `DD.MM.YYYY`, weekday forms) and ISO week names. |
| `aos/mapcheck.py` | The vault check: broken links, reachability, frontmatter rules, large files, secret patterns; also `redact()`, used everywhere text leaves the system. |
| `aos/digest.py` | The daily digest (deadlines, weekly goal, what needs you, next 14 days) and the vault-check report, written to `AI/Digest/`. |
| `aos/graph.py` | Note graph (nodes, edges, types, projects) for the dashboard. |
| `aos/artifacts.py` | Finds what agents, skills and Claude produced, served by id only. |
| `aos/dashboard.py` | Builds the data JSON and embeds it into `web/dashboard.html` -> `data/out/dashboard.html`. |
| `aos/routines.py` | Loads and validates `routines.toml`; maps command names to fixed argument lists. |
| `aos/scheduler.py` | `aos tick`: decides what is due, runs it as a subprocess with limits, logs to `data/runs.jsonl`, keeps `data/state.json`. |
| `aos/tasksched.py` | Installs and removes the OS task that calls `aos tick` every few minutes: Windows Task Scheduler, and elsewhere it only prints the `PATH` and `tick` lines for `crontab -e` (it never edits your crontab). `doctor` reads `crontab -l` to see whether they are in. |
| `aos/agents.py` | Agent catalog, job log, the `claude -p` call with its locks, Atlas (plan, fan-out, synthesis), cost log. |
| `aos/agentdefs.py` | Custom agents: validated create, update, delete in `agents.local.toml` and `agents/local/`. |
| `aos/skills.py` | Skill discovery and frontmatter; builds the skill run on top of `agents.py`. |
| `aos/server.py` | `aos serve`: local HTTP server with token, Host and Origin checks, CSP. |
| `aos/cli.py` | Every `python -m aos ...` command. |
| `aos/web/dashboard.html` | The single-page dashboard (plain JS, no build step). The home stage and the Atlas view draw one procedural Milky Way on a canvas: `galaxyPoint()` builds a barred spiral (yellowish bulge, elongated golden bar whose ends feed two major arms, two fainter minor arms, a dense faint thin disc, blue young clusters and pink HII patches strung on the arms, a sparse halo with globular clusters; arms and bar turn rigidly as a density wave, the rest differentially), `galaxyMistPoint()` adds the unresolved starlight and the dark dust lanes as ordinary particles of the same cloud (about 1800 faint, large glow particles and 900 dust particles after the 9000 stars, each a soft sprite: glow additive under the stars, dust darkening over them). Every particle follows the same physics, targets and flights, and the budget is fixed at 11,700 particles: nothing thins the cloud out, not time, not Atlas, not a slow machine (the frame rate is capped at about 75 fps instead, and a stage that is hidden or scrolled out of view does no work). The cloud is painted by a WebGL2 painter (`glxScene`: one instanced draw per pass over the arrays the simulation steps, composited as additive glow and stars and then the dust over them); the 2D canvas painter (`drawCloudScene`) paints the same picture and is the reference and the fallback: without WebGL2, on a software renderer, after a lost context, or with `localStorage` `aos.gl` = `0`. In the canvas painter small stars (under 6.5 px) are not drawn one by one: they are added up on the CPU into one RGBA layer per frame and blitted once (`dotAdd` / `dotFlush`), because the canvas pays per operation (the disc is tilted about 50 degrees). The UI palette is derived from it: deep blue-violet space, galactic gold accent, indigo/cyan/pink secondaries (CSS custom properties in section 1 and the OS block). Atlas keeps the framing the entry flight dives to; some of the galaxy's own stars are promoted to the agents (they grow, take their group color and glide to their slot on the arms) and are demoted again on the way home. The camera, promotion and morph math is pure (`// ---- Galaxy model` block) and covered by `tests/test_galaxy_transitions.py`. No images, no dependencies. Every pane and control is rounded, floating "liquid glass" (frost everywhere; a refracting lens on small pieces in Chromium, under a budget; flat for reduced transparency), driven by one header switch and a handful of `--lg-*` tokens: see [design.md](design.md). The home page is a homescreen: the widgets are tiles on a snap grid in a zone on each side of the galaxy, in pages, moved and resized by pointer or keyboard and saved per browser; a widget adapts to the size of its tile (type follows the box, blocks and rows leave in order of importance, `WIDGET_FIT` and `fitPlan`) and one slider in the Customise menu sets how see-through all of them are, from matte to liquid (`aos.widgetGlass`); its model is pure (`// ---- homescreen model`, covered by `tests/test_homescreen.py`), see "The homescreen" in [design.md](design.md). |

## How a run flows

**A routine.** The OS task calls `python -m aos tick` every 5 minutes. The scheduler takes a lock file, loads `routines.toml`, and for each enabled routine pinned to this machine checks whether it is due (missed slots run once on the next tick), under its daily cap and not blocked by the circuit breaker. It then starts `python -m aos <command>` as a subprocess without a shell, with a time limit, and appends the result to `data/runs.jsonl`. Too many failures in a row block the routine until `aos unblock <id>`.

**The digest.** `aos digest` reads the vault, collects deadlines (frontmatter and dated lines outside log sections), the weekly goal from the current week note, what needs attention, and the next days; then it writes `AI/Digest/` (current digest, a daily copy, the vault-check report). Text copied from notes is redacted on the way.

**An agent task.** A task arrives from the dashboard (`POST /api/agents/<id>`) or `aos agent <id> "..."`. `agents.submit` checks the limits (one task per agent, three in total, daily cap, length) and logs the job. A worker thread starts `claude -p` (vault agents in the vault folder; web agents and Atlas calls in an empty sandbox folder, `data/agents/sandbox/`) with the agent's prompt plus a fixed rules block as system prompt, the task on standard input, the agent's tool list in `--tools` (`--allowedTools` holds `Read(./**)` and/or the web tools), no connectors, no session, a budget, a turn limit, a time limit and a daily spending ceiling. The answer is redacted, cut to size and written to `data/agents/jobs.jsonl`; the dashboard polls and shows it as text.

**Atlas.** A task without a chosen agent goes to Atlas. One short planning call sees the catalog as `id: description` lines and picks up to three agents with a sub-task each. They work in parallel; Atlas reviews their reports and either answers or runs another round (at most three). An agent whose task is outside its scope answers `[OUT_OF_SCOPE]` and is replaced. If the plan is unusable, keywords and the default agent decide.

**A skill.** `aos skill <id> "task"`, the dashboard skill deck, or a routine with `command = "skill"` turns `SKILL.md` into the system prompt of an agent run with read-only vault tools and `--add-dir` for the skill folder. Model and effort come from fixed lists.

## Decision log (condensed)
- **Order of construction: Memory, then Pulse, then Screen.** The vault parser and the check had to be solid before anything scheduled or displayed their output.
- **Whitelist instead of shell commands in routines.** A configuration file should never be able to start arbitrary programs.
- **One data JSON as the contract between Python and the dashboard.** It let the backend and the frontend be built in parallel and keeps the HTML free of server logic.
- **Skills as folders with reference files** instead of one large prompt: `SKILL.md` routes, references are read on demand.
- **Routines can run skills** (`command = "skill"`): a scheduled prompt is just another whitelisted command with validated arguments.
- **An artifacts view** so that everything Claude produced can be found again, served by id only, HTML in an empty sandbox.
- **Cost tracking per run** (`aos spend`, a cost widget) instead of hard savings logic; budgets per run guard against loops.
- **Atlas replaces a free chat.** Specialist agents with narrow descriptions answer better than one generic prompt, and the scope rule (`[OUT_OF_SCOPE]`) keeps them honest.
- **Vault agents and web agents are separate.** An agent that can read your notes and fetch URLs could be steered by a web page into leaking notes; separating them removes that path. `mixed = true` exists as a deliberate, visible exception.
- **Custom agents live in their own files** (`agents.local.toml`, `agents/local/`), so the shipped catalog stays hand-edited and comment-rich while the dashboard can rewrite its own file safely.
- **Descriptions follow one pattern** ("what it delivers; vault or web. For: ... Not for: ... (→ neighbour)"), because Atlas sees nothing else when it routes. See [agents.md](agents.md).
- **`Read(./**)` instead of bare `Grep`/`Glob` permissions**, because the bare forms allowed searching the whole file system.
- **Liquid glass in plain CSS, one SVG filter and one WebGL2 pass, not a library.** The reference implementations are either a native iOS view or need a CDN script and one WebGL context per piece; the dashboard is one file that is served under `default-src 'none'`. Small controls get refraction from a displacement map used as a backdrop filter, with a measured budget; the large widgets of the home page are drawn by one WebGL2 pass (one context for all panes) and fall back to frost. Both degrade through three steps to flat. Details and numbers: [design.md](design.md).
- **English source texts as catalog keys, one JSON file per language, no gettext.** The code stays readable in English, a missing entry falls back to English instead of breaking, and the tests extract every marked text from the Python sources (AST) and the dashboard (regex) to hold each locale to it: nothing missing, nothing stale, placeholders and code spans unchanged. Interface language and vault conventions are separate settings, because the language of the notes is not the language of the person reading the dashboard.
- **Not built, on purpose:** always-on external agent services (need their own server and broader rights), calendar and e-mail widgets (need connectors, which are deliberately locked), skills with write access (against the read-only principle).

## Definition of done for a change
- `python -m unittest` is green; new behaviour has a test (parsers, due times, caps, circuit breaker, digest, server security are covered today).
- `python -m aos doctor` reports no errors on a real vault.
- Dashboard changes are checked in a browser: all views, search, opening a note in Obsidian, light and dark, phone width.
