"""Notion guard: a Claude Code hook around every Notion call of the Notion agent.

- PreToolUse (mcp__notion__*): deleting a block and every archive or trash flag (`archived`, `in_trash`,
  `allow_deleting_content` set to true, wherever they sit in the call, also inside a JSON string) are blocked. The
  block goes back to Claude with what to do instead: file a deletion request (request_deletion), which the user
  approves or denies. The run goes on.
- PostToolUse: notes each change (tool and the id it touched) for the job, so you see what the agent did in Notion.

Runs as `python -I notionguard.py pre|post` (stdin: the hook JSON) with AOS_NOTION_STATE (file prefix of this run) and
AOS_NOTION_USER (the user's name). Fails closed: a call it cannot check is blocked.
"""

from __future__ import annotations

import json
import os
import re
import sys

SERVER = "mcp__notion__"
NEVER = {SERVER + "API-delete-a-block"}
# a flag that deletes, set to true: matched on the call with every backslash removed, so a flag inside a JSON string counts too
DELETING = re.compile(r"(archived|in_trash|is_archived|allow_deleting_content)\W{1,8}true", re.I)
READ_ONLY = ("API-get-", "API-retrieve-", "API-post-search", "API-query-", "API-list-")
ID_KEYS = ("page_id", "block_id", "data_source_id", "database_id", "comment_id")


def check(tool: str, given) -> str:
    """Why this call deletes something, or ""."""
    if tool in NEVER:
        return "deleting a block"
    if DELETING.search(json.dumps(given, ensure_ascii=False).replace("\\", "")):
        return "archiving, trashing or deleting content"
    return ""


def target(given) -> str:
    """The id a call touched, for the job's list of changes."""
    if not isinstance(given, dict):
        return ""
    for k in ID_KEYS:
        if isinstance(given.get(k), str):
            return given[k][:64]
    parent = given.get("parent")
    if isinstance(parent, str):
        try:
            parent = json.loads(parent)
        except ValueError:
            parent = None
    if isinstance(parent, dict):
        return "new in " + next((str(v)[:64] for k, v in parent.items() if k.endswith("_id")), "?")
    return ""


def main(stage: str) -> int:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    tool, given = str(data.get("tool_name") or ""), data.get("tool_input") or {}
    state = os.environ["AOS_NOTION_STATE"]
    if stage == "post":
        short = tool[len(SERVER):]
        if tool.startswith(SERVER) and not short.startswith(READ_ONLY):
            with open(state + ".changes", "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"tool": short[4:] if short.startswith("API-") else short, "target": target(given)}) + "\n")
        return 0
    why = check(tool, given)
    if not why:
        return 0
    with open(state + ".blocked", "a", encoding="utf-8") as fh:
        fh.write(tool + "\n")
    user = os.environ.get("AOS_NOTION_USER") or "the user"
    print(f"Blocked by Starlane's Notion guard: {why} needs {user}'s permission. Call request_deletion with the page or "
          f"block id and why it should go; {user} approves or denies it in Starlane. Do not try another way to remove it.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        sys.exit(main(stage))
    except Exception as exc:  # noqa: BLE001 - fail closed: an unchecked call must not reach Notion
        if stage == "post":
            sys.exit(0)  # the list of changes is a convenience
        print(f"Starlane's Notion guard could not check this call ({type(exc).__name__}), so it was blocked.", file=sys.stderr)
        sys.exit(2)
