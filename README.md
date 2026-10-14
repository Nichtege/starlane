# Starlane

A small operating system around a folder of Markdown notes (an Obsidian-style *vault*) and
[Claude Code](https://claude.com/claude-code). It checks your notes, writes you a daily digest, runs scheduled
routines, and gives you a roster of read-only specialist agents behind a local dashboard.

It never edits your notes (the one exception is the opt-in `git-pull` routine, off by default, which updates a vault that
is a git checkout). Agents can read; they cannot write, run commands or push anything.

> **Honest note.** This is a personal tool made public, not a framework and not production software. It is stdlib-only
> Python, a single-user, single-machine design, and it is shared **as is**, without warranty (see [LICENSE](LICENSE)).
> Read [docs/security.md](docs/security.md) before you point it at notes you care about.

The command is `starlane` (the short form `aos` does the same, and so does `python -m aos`; the guides use the latter).

## What you get

| Layer | What it does | Command |
|---|---|---|
| **M**emory | vault check: broken links, two-hop rule, frontmatter, leaked secrets | `aos mapcheck` |
| **A**gent | specialist agents (read-only) and the Atlas coordinator that routes a task to them | `aos agent research "..."` |
| **P**ulse | routines on a schedule, with time limit, daily cap and circuit breaker | `aos tick`, `aos status` |
| **S**creen | local dashboard: today (a homescreen: arrange the widgets like on a phone, with a quick-launch tile for every view, and a see-through slider from matte to liquid glass), agents, graph, timeline, health, spend | `aos serve` |

You can add your own agents (dashboard "New agent", `aos agent-new`, or a Markdown file) and your own skills. Both are
read-only by construction.

## Quickstart (5 minutes)

Requirements: Python 3.11 or newer (check with `python3 --version`; on macOS and Linux the command is usually `python3`,
and some long-term-support systems still ship 3.10). For agents and skills also the
[Claude Code CLI](https://claude.com/claude-code) (`claude`) on your `PATH`, logged in. Digest, vault check and
dashboard need nothing else.

```bash
# 0. First download this repository (or the ZIP from the green "Code" button on GitHub, unpacked).
#    Any folder except ~/starlane, which `aos setup` makes: hence the name starlane-src.
git clone https://github.com/Nichtege/starlane.git starlane-src
cd starlane-src               # every step below runs from a terminal opened here (until step 1 moves you)
python -m pip install .       # adds the `aos` command; no dependencies. macOS / Linux: python3 -m pip install .

# 1. One folder for your setup: ~/starlane (or the folder in $AOS_HOME). Never overwrites a file.
aos setup                     # config, routines, agents, skills, docs and the demo vault in examples/vault
cd ~/starlane               # work from there; open `claude` there for the guided prompts

# 2. Self-test, then your first digest and vault check
aos doctor
aos digest                    # writes examples/vault/AI/Digest/latest.md (in that folder)

# 3. The dashboard: open the link it prints (http://127.0.0.1:8765/?k=..., the key changes on every start)
aos serve

# 4. Your first agent task (needs the claude CLI)
aos agent research "What are my active projects and when are they due?"
```

**Rather have Claude Code do it?** Download the repository first (step 0), open `claude` in that folder and paste:

> Install Starlane from this folder with `python -m pip install .` (use pipx or a virtual environment if pip refuses it), run `aos setup`, then `aos doctor` and `aos digest` from `~/starlane`. Tell me for each step whether it worked, start `aos serve` and give me the link. Do not change anything outside this folder and `~/starlane`.

Good to know:

- **`pip` refuses ("externally-managed-environment")?** Recent Debian, Ubuntu and Homebrew Pythons do. Use
  `pipx install .` (run `pipx ensurepath` once if `aos` is then not found), or a virtual environment
  (`sudo apt install python3-venv` first on Debian and Ubuntu):
  `python3 -m venv ~/.venvs/aos && ~/.venvs/aos/bin/python -m pip install .`, then run `~/.venvs/aos/bin/aos`.
- **`aos` not found after installing?** pip printed the folder it put `aos` in: add that folder to your `PATH`, or use
  `python -m aos ...` with the same Python (every command works that way).
- **Working on the code, or just looking?** Skip the install and run from the clone: `python -m aos doctor` (and the
  other commands, `python3 -m aos` on macOS and Linux) uses the `aos.toml` in that folder. That is a different setup
  than `~/starlane`: pick one and stay with it. The guides write commands as `python -m aos ...`; after `pip install`
  they are `aos ...` (and `aos next` prints them that way).
- **Safe to repeat.** `aos setup` only adds files that are missing and never changes one that exists, edited or not, so
  running it again after `pip install --upgrade .` cannot lose anything. For the same reason it does not update files
  you already have: to see what a new version ships, run `aos setup ~/aos-new` and compare.
- **Another folder?** `aos setup ~/somewhere` makes it there (a new or empty folder, never your notes folder). Then put
  the option before the command:
  `aos --config ~/somewhere/aos.toml doctor`, or set `AOS_HOME=~/somewhere` once for every command.

The demo vault belongs to a fictional illustrator who gardens, learns Spanish and draws a zine; it is set in week
2026-W41, so on a later date the digest reports the current week note as missing and some tasks as overdue: that is
the demo getting old, not a broken setup. Its `CLAUDE.md` lists more questions it can answer. You can also open **Atlas** in the dashboard and ask.

`aos install-task` schedules the routines (every 5 minutes, only routines that are due run). On Windows it registers one
task named "Starlane tick" for your user (running it from another folder replaces it; `aos uninstall-task` removes
it); on macOS and Linux it changes nothing and prints two lines for `crontab -e`. In a clone on Windows,
`start-dashboard.bat` also starts the dashboard, with the clone's own setup.

### Use your own notes

When you are ready, point Starlane at your own folder of Markdown notes:

- Existing notes (an Obsidian vault works as is): set `[vault] path` in `aos.toml` to that folder. Use `/` also on
  Windows; a relative path is relative to `aos.toml`.
- No notes yet: `aos init ~/notes` creates a small starter vault, then set `[vault] path = "~/notes"`.

Then run `aos doctor` again. Note that `aos digest` writes into the vault: `latest.md`, a daily archive copy
and `vault-check.md` go into its digest folder (`[digest] dir`, default `AI/Digest`). It never touches any other note.

Next: `aos next`. It shows a checklist of the remaining setup (Obsidian, routines, your own agent, ...) with a
ready prompt for Claude Code for each step. The full guide: [docs/getting-started.md](docs/getting-started.md).

## Make it yours

- **Your name and language**: `[user]` in `aos.toml` (`name`, `language`). Agents reply in that language.
- **Your vault's structure**: if your notes use other frontmatter keys, folders or headings (or another language), set
  `[conventions]` once instead of renaming notes. See [docs/vault-conventions.md](docs/vault-conventions.md).
- **Your agents**: [docs/agents.md](docs/agents.md). The shipped catalog (`agents.toml`) has nine; yours go to
  `agents.local.toml` and `agents/local/`, which are git-ignored.
- **Your skills**: [docs/skills.md](docs/skills.md).
- **Your Notion**: one agent saves results to Notion and changes the pages you share with it; deleting needs your
  yes. Set it up with `aos notion-connect`, see [docs/notion.md](docs/notion.md).
- **Your phone**: the dashboard as an app on the home screen of your iPhone or Android phone, through Tailscale,
  without opening anything to the internet. Set it up with `aos phone`, see [docs/phone.md](docs/phone.md).

## Safety model

- **Read-only agents.** Tools come from a fixed whitelist: vault (`Read`, `Grep`, `Glob`) and web (`WebSearch`,
  `WebFetch`). Every agent reads your notes for context; one that also searches the web must say `mixed = true` and is
  told never to put note text into a search or URL. Anything else is rejected when the file loads. The one exception,
  opt-in: the Notion agent changes the Notion pages you share with it, and deletes nothing without your yes.
- **Never writes into your notes.** The only place the system writes inside the vault is the digest folder (the opt-in
  `git-pull` routine is the exception: it runs `git pull --rebase` there, which updates files to match your remote).
- **Whitelisted routines.** `routines.toml` names commands from a fixed list; they run without a shell, with a time
  limit, a daily cap and a circuit breaker. Risky ones (git pull, Claude, skills) are off by default.
- **Local only.** The server listens on `127.0.0.1`, requires a per-start token, checks Host and Origin, and sends a
  Content Security Policy with a script nonce. Phone access (opt-in) comes through Tailscale, from your own devices only.
- **Secrets are redacted** from tasks and answers before anything is stored or shown.

Details, limits and what this does *not* protect against: [docs/security.md](docs/security.md).

## Layout

```
aos/            the code (Python, stdlib only); aos/web/dashboard.html is the whole frontend
agents.toml     shipped agent catalog      agents/    their prompts
skills/         shipped skills             routines.toml  the schedule
aos.toml        your configuration         docs/      guides, architecture, security
examples/       the demo vault, a custom agent   tests/  unittest suite
```

`aos setup` makes the same layout (minus the code) in your folder. Run the tests from a clone:
`python -m unittest discover -s tests -t .`.

More: [getting started](docs/getting-started.md) · [architecture](docs/architecture.md) · [design](docs/design.md) · [agents](docs/agents.md) · [skills](docs/skills.md) · [Notion](docs/notion.md) · [phone](docs/phone.md) ·
[vault conventions](docs/vault-conventions.md) · [running on a server](docs/vps-setup.md) · [contributing](CONTRIBUTING.md)

## License

MIT, provided "as is". See [LICENSE](LICENSE).
