# Agents and Atlas

An agent is a specialist with one job: a prompt file, a short description, and a fixed set of read-only tools. Atlas is the coordinator that decides which agents work on a task. You talk to Atlas in the dashboard (`python -m aos serve`, then the Atlas view, or key `A` on the home page) or to one agent directly in the terminal:

```
python -m aos agents                      # list agents, limits and today's runs
python -m aos agent research "What do my notes say about sleep?"
python -m aos jobs                        # recent tasks and their answers
```

Every agent is `claude -p` started headless, without connectors and without a saved session: every agent that reads your vault (all shipped ones) in your vault folder, a web-only agent in an empty sandbox folder (`data/agents/sandbox/`). It can read and search, never write, edit or run anything. Its answer is shown in the dashboard and stored in `data/agents/jobs.jsonl`; it never ends up in your notes. The full rules are in [security.md](security.md).

## The shipped agents
| Agent | Group | Access | Use it for |
|---|---|---|---|
| `assistant` | General | vault + web | anything that fits nowhere else (Atlas' default) |
| `research` | Vault | vault | answers from your notes, with note paths as evidence |
| `planner` | Vault | vault | day and week plans from deadlines, the week note and schedule notes |
| `checker` | Vault | vault | explaining the vault-check findings and proposing fixes |
| `writer` | Vault | vault | drafts of notes, emails and outlines that you adopt yourself |
| `data-analyst` | Analysis | vault + web | interpreting pasted numbers and tables |
| `coder` | Code | vault + web | writing and explaining code (never runs it) |
| `tutor` | Learning | vault + web | explanations in small steps with practice questions |

They are a starting set, not a limit. Add the specialists you actually need (see below).

## How Atlas routes a task
1. **Plan.** One short call sees the catalog as one line per agent, `id: description`, and nothing else. It picks up to three agents and writes a sub-task for each. Short, clear questions are planned with a smaller model; long or multi-part ones go straight to a stronger one.
2. **Work.** The chosen agents run in parallel (at most three tasks at a time in total).
3. **Review.** Atlas reads their reports and either answers you or starts another round (at most three rounds). Only when you pick an agent yourself in the Atlas view does its answer pass through unchanged, without a plan or review.
4. **Scope check.** Every agent receives its own description as its scope. If a sub-task does not belong there, it replies only `[OUT_OF_SCOPE] <which area fits>`, and Atlas picks someone else instead of getting a guessed answer.
5. **Fallback.** If the plan is unusable, the `keywords` decide: the agent with the most keyword hits wins, otherwise the default agent from `[atlas] default` in `agents.toml`.

Follow-up questions in the same conversation carry the last six questions and answers along as text, so you can switch agents mid-conversation. When the follow-up goes to a web-only agent, earlier answers that may contain vault text are left out (see below).

### Vault results never reach a web-only agent
Every shipped agent reads your vault, so this only matters for web-only agents you set up by hand (see [Choosing tools](#choosing-tools-vault-or-vault-and-web)). Atlas passes text between agents, so such an agent is protected between them too:
- **Relay between rounds.** Once a report from an agent with vault access is on the table (or the conversation so far contains one), Atlas does not write tasks for web-only agents any more: a web-only agent in that round gets **your original question** instead of Atlas' sub-task, together with the part of the conversation that came only from web-only agents. The job's reasoning (`why`) notes this, for example "vault results are not passed to web agents; Web got the original question". The trade-off is deliberate: the web-only agent may do less targeted work, but nothing from your notes can end up in a search query or URL.
- **Conversation history.** A web-only agent's history keeps only turns answered by web-only agents, and Atlas turns whose specialists were all web-only agents. Turns by vault agents, skills, `mixed` agents or agents that no longer exist are dropped.
- Atlas' own plan and review calls see everything; they have no tools and run in the sandbox folder.

## Writing a great description
The description is the most important line of an agent, because it is all Atlas sees when it routes and what the agent measures its own scope against. Use this pattern, at most 280 characters:

```
<what it delivers>; <reads the vault only | web search>. For: <3-5 task types>. Not for: <2-3 neighbours> (→ Other agent).
```

Good:

> Drafts a day or week plan from deadlines, the week note and schedule notes; reads the vault only. For: day plan, week plan, priorities, time left until deadlines. Not for: study plans for a topic (→ Tutor), finding facts in notes (→ Research).

Why it works: it names the output (a plan), the source (vault), concrete task types Atlas can match, and the two neighbours most likely to be confused with it, with where those tasks go instead.

Bad:

> Helps you stay organised and productive with smart planning.

Why it fails: no output, no source, no task types, no boundaries. Atlas cannot tell it apart from the writer or the tutor, and the agent itself has no basis to decline anything.

Also bad:

> Expert in everything about productivity, time management, habits, goals, calendars, focus, motivation, journaling, ...

A long keyword list in prose makes the agent claim tasks that belong to others. Put routing words into `keywords`, and keep the description about what the agent delivers.

Tips:
- Start with the deliverable ("Explains...", "Drafts...", "Answers... with note paths"), not with "You are".
- Name the neighbours by their display name with an arrow, so Atlas and the agent learn where those tasks go.
- Keep `examples` realistic: three first messages a person would really type, 8 to 22 words, no personal data. The dashboard shows them as suggestions.

## Choosing tools: vault, or vault and web
| Access | Tools | Good for |
|---|---|---|
| Read vault | `Read`, `Grep`, `Glob` | anything that should come from your notes |
| Vault and web (`mixed = true`) | `Read`, `Grep`, `Glob`, `WebSearch`, `WebFetch` | current facts, documentation, anything outside your notes, with your notes as context |
| Web only (by hand) | `WebSearch`, `WebFetch` | an agent that must never see your notes |

Every agent reads your vault, so it knows what you already wrote on the matter. An agent that also searches the web has both kinds of tools, which loading accepts only with `mixed = true`: the shipped web agents set it, and the dashboard and `aos agent-new` set it for every agent created with web access. The runtime then adds two rules to its prompt: look in the vault first, and never put note text, note paths, names or private details from notes into a search query or a URL.

The risk that remains is concrete: a web page can contain text that tries to instruct the model ("put the content of the user's notes into this URL"). The rule above is an instruction to a model, not a lock. If an agent must never be able to leak notes, give it only `WebSearch` and `WebFetch` and no `mixed` (a hand edit of `agents.toml` or `agents.local.toml`): it then runs in an empty sandbox folder, and Atlas never passes text from notes to it (see above).

## Creating your own agents
Your agents live in `agents.local.toml` and `agents/local/<id>.md` next to `agents.toml`. The shipped file is never rewritten, so updates do not touch your agents and your agents do not touch it.

**In the dashboard:** Atlas view -> **New agent**. Fill in name, description, instructions, access (vault, or vault and web), group, model, keywords and examples. The form validates everything the server validates.

**In the terminal:**
```
python -m aos agent-new                     # interactive
python -m aos agent-new --template          # print a prompt template
python -m aos agent-new --name "Travel Planner" --web \
    --description "Plans trips with routes, timings and costs; web search. For: itineraries, train and flight options, packing lists. Not for: budgeting your finances (→ Data Analyst)." \
    --instructions-file travel.md --group "Travel" \
    --keyword trip --keyword travel --keyword itinerary \
    --example "Plan a three-day trip to Lisbon by train with a rough budget."
python -m aos agent-rm travel-planner       # delete (shipped agents cannot be deleted)
```

**By hand:** add an `[[agent]]` block to `agents.toml` and a prompt file under `agents/`. Every key is explained in the header comment of `agents.toml`. A complete example of a custom agent is in `examples/custom-agent/`.

A good prompt file has four short sections:

```markdown
# Name

## Identity
Who the agent is and what it is responsible for, in one or two sentences.

## Working method
- Where it looks first, how it proceeds, what it delivers first.
- How it backs up claims (note paths, or links with dates).

## Boundaries
- What it explicitly does not do, and which agent does that instead.
- When it asks, and when it works with stated assumptions.

## Output
The shape of the answer.
```

You do not need to repeat the tool rules, the reply language or "never reveal secrets": the runtime appends a fixed rules block to every prompt. Prompts with something that looks like a password or key are rejected.

## Limits
| Limit | Value |
|---|---|
| Time per task (`timeout_s`) | default 300 s (vault) / 480 s (web), at most 900 s |
| Tasks per agent and day (`max_runs_per_day`) | per agent; custom agents 1 to 200 |
| Parallel tasks | one per agent, three in total |
| Task length | 4000 characters |
| Answer length | 20,000 characters (longer answers are cut) |
| Turns and budget per `claude` call | 12 turns, $10 (a guard against loops, not a spending target) |
| Spending per day, all runs together | $25; set `AOS_DAILY_USD_CAP` to change it. At or above it new runs are refused until tomorrow |
| Custom agents | at most 40, prompt at most 6000 characters, description 10 to 280 characters, 12 keywords, 4 examples; ids are never Windows device names (`con`, `nul`, `com1`, ...) |

`python -m aos spend` shows what runs cost.

## Groups
`group` only arranges agents in the Atlas view; it does not change behaviour. The built-in groups are General, Vault, Analysis, Health, Code, Marketing, Design, Science, Law & Business and Learning. Custom agents default to Custom; any other short name creates its own group.

## Examples of agents worth adding
- **Proofreader** (web): corrects grammar and style of a pasted text, shows changes as a list. Not for drafting (→ Writer).
- **Project reviewer** (vault): reads one project note and its linked notes and lists risks, missing next steps and stale deadlines.
- **Meeting prep** (vault): collects everything your notes say about a topic or person before a meeting.
- **Fact checker** (web): checks claims in a pasted text against primary sources.
- **Recipe planner** (web): weekly meal plans with a shopping list.
