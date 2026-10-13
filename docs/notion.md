# Notion

One agent, `notion`, reads and changes your Notion: it saves results there, updates pages and databases, and finds things in them. It is the one agent in Starlane that changes something, and only in the Notion pages you share with it. It never deletes: it asks you, and Starlane deletes after your yes.

Other agents do not get Notion. When they need it during a task, they ask the Notion agent (see [Agents talk to each other](agents.md#agents-talk-to-each-other)), and Atlas sees that conversation when it reviews their reports.

## Set it up

You need [Node](https://nodejs.org) (the LTS version) and a Notion account.

1. **Create an integration.** Go to <https://www.notion.so/profile/integrations>, *New integration*, type *Internal*, pick your workspace. Under *Capabilities* switch on *Read content*, *Update content*, *Insert content*, *Read comments* and *Insert comments*. Copy the *Internal Integration Secret* (it starts with `ntn_`).
2. **Connect Starlane.**
   ```
   python -m aos notion-connect
   ```
   It downloads Notion's official MCP server (`@notionhq/notion-mcp-server`, a pinned version), checks it against npm's published checksum, keeps only the two files it runs from, and asks for the secret (input hidden). The secret is stored in `data/notion/token`, outside your project files. `NOTION_TOKEN` in the environment wins over the stored one. For a script: `python -m aos notion-connect --token-stdin < file`; a new secret: `--new-token`.
3. **Share pages with the integration.** Notion shows the integration nothing until you share: open a page or database, *•••* → *Connections* → your integration. Sub-pages follow their parent. Share a few top pages (a *Starlane* page for results, your projects database), not the whole workspace.
4. **Restart the server** (`python -m aos serve`) if it is running, then check:
   ```
   python -m aos notion      # Node, server, token, waiting requests
   python -m aos doctor      # the same, among the other checks
   ```

The agent is in the shipped catalog (`agents.toml`, prompt `agents/notion.md`). Until Notion is connected, a task for it fails with a short note telling you to run `notion-connect`; nothing else is affected.

## Use it

Ask Atlas, for example *"Save this week's plan to my Notion page Weekly"*, or the agent directly: `python -m aos agent notion "Add the three open tasks from my notes to the Tasks database"`. Under the answer the dashboard folds out what it changed in Notion (*Changed in Notion*) and which agents it talked to (*Agents talked*).

## Deleting needs your yes

The agent cannot delete. The **Notion guard** (`aos/notionguard.py`, a Claude Code hook around every Notion call of the agent) blocks deleting a block and every call that archives or trashes something (`archived`, `in_trash`, `allow_deleting_content` set to true, wherever they sit in the call), and the delete tool is not in the agent's allow list either. When something should go, the agent files a **deletion request** instead and tells you so in its answer.

Before a request is stored, Starlane asks Notion itself what the target is, so you decide on its real title and link, not on the agent's description. Requests wait in `data/notion/requests.jsonl` (at most 20 at a time) until you decide:

- **Dashboard**: in the Atlas chat, a box *Notion · waiting for you* shows each request with the agent's reason and a link to the page. *Keep* closes it; *Delete* deletes.
- **Terminal**: `python -m aos notion` lists them, `python -m aos notion-approve <id>` deletes, `python -m aos notion-deny <id>` keeps.

Only after your yes does Starlane itself (not a model) call Notion: a page goes to Notion's trash, where you can restore it for 30 days; a block is deleted. If Notion refuses, the request is closed as failed with Notion's reason.

## What it can and cannot do

| Can | Cannot |
|---|---|
| read, search and query the pages and databases you shared | see anything you did not share |
| create pages, change properties and text, add blocks and comments, move pages, create and change data sources | delete or archive anything (it asks you) |
| read your vault as context (`Read`, `Grep`, `Glob`) | search or fetch the web (never together with Notion, loading rejects it) |
| answer other agents' questions about Notion | write into your notes |

Only one agent may have the `Notion` tool; a second one, or one that also has web tools, is rejected when `agents.toml` loads.

## Security

- **The token** reaches Notion's server only through the environment of the Notion agent's own run; it is never on a command line, in the run's config or in a file the run can read through its tools. Every other run starts with `NOTION_TOKEN` removed from its environment.
- **The server code** is checked by SHA-256 before every run. If the files in `data/notion/server/` changed, the Notion agent does not start until you run `notion-connect` again.
- **Notion text is material, not an instruction.** A page can contain text that tries to steer the agent. The guard stops deletions whatever the agent was told; it does not stop ordinary edits to the pages you shared. So share only what the agent may change, and do not share pages that are published to the web: whatever the agent writes into such a page is public.
- Every change the agent made is listed on its job (`notion_changes`: tool and page or block id). Notion's own page history shows the details and can undo them.

More in [security.md](security.md#notion).
