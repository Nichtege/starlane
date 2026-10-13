"""Notion: the one agent that may change something, and only in the Notion pages you share with it.

Everything else in Starlane reads. The Notion agent (the single agent with the tool "Notion" in agents.toml) also gets
the tools of Notion's official MCP server, and only them:
- The server is @notionhq/notion-mcp-server, pinned (VERSION). `aos notion-connect` downloads its npm tarball once,
  checks npm's published hash and extracts only the two files it runs from, each checked again by SHA-256 on every
  run. It needs Node, nothing from npm at run time.
- The token of an internal integration (NOTION_TOKEN, or data/notion/token written by `aos notion-connect`) reaches
  the server through the environment of that one run, never a file the run can read or a command line. Notion itself
  limits it to the pages you share with the integration.
- Nothing is deleted by an agent: the notion guard (notionguard.py) blocks deleting blocks and every archive or trash
  flag. The agent files a deletion request instead (request_deletion, see peers.py); you approve or deny it in the
  dashboard or with `aos notion-approve` / `aos notion-deny`, and only then Starlane itself, not a model, deletes.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import secrets
import shutil
import tarfile
import threading
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .config import Config
from .scheduler import atomic_write

PACKAGE = "@notionhq/notion-mcp-server"
VERSION = "2.5.2"
TARBALL = f"https://registry.npmjs.org/{PACKAGE}/-/notion-mcp-server-{VERSION}.tgz"
INTEGRITY = "sha512-5nPSwHMnugSGAhSJS5vVIlMao+iTJO9HoWGpCnT8lJNrPy3rZMqs1V/CPiN4MuxF+5EBgRE/f/Tirl6Wfi75Mg=="  # npm's dist.integrity
FILES = {  # what the server runs from (bin/cli.mjs is one bundle that reads the OpenAPI file next to it), with SHA-256
    "bin/cli.mjs": "70a958eff66104a3a76857a63206e8494548e9358031907905bcdadd52cb72b0",
    "scripts/notion-openapi.json": "d33548174dfc6ebad012fc73b1483532c7887d8c97fd6deb62d56c742e96baba",
}
MAX_TARBALL = 20_000_000
API = "https://api.notion.com/v1"
API_VERSION = "2025-09-03"
SERVER = "notion"  # the MCP server's name: its tools are mcp__notion__<tool>
TOOL = "Notion"  # the tool name in agents.toml that gives an agent Notion
# The tools of VERSION. Reading ones first; API-delete-a-block is left out on purpose (and blocked by the guard as well).
READ_TOOLS = ("API-get-self", "API-get-user", "API-get-users", "API-post-search", "API-retrieve-a-page", "API-retrieve-page-markdown",
              "API-retrieve-a-page-property", "API-get-block-children", "API-retrieve-a-block", "API-retrieve-a-comment",
              "API-retrieve-a-database", "API-retrieve-a-data-source", "API-query-data-source", "API-list-data-source-templates")
WRITE_TOOLS = ("API-post-page", "API-patch-page", "API-update-page-markdown", "API-patch-block-children", "API-update-a-block",
               "API-create-a-comment", "API-move-page", "API-create-a-data-source", "API-update-a-data-source")
ALLOWED = tuple(f"mcp__{SERVER}__{t}" for t in READ_TOOLS + WRITE_TOOLS)
TOKEN_RE = re.compile(r"^(ntn_|secret_)[A-Za-z0-9]{20,100}$")
_ID_RE = re.compile(r"([0-9a-f]{32})(?![0-9a-f])")
MAX_PENDING = 20
_LOCK = threading.Lock()


class NotionError(RuntimeError):
    """Something the user can read: no token, not shared, Notion said no."""


# --- where things live ----------------------------------------------------------------
def folder(cfg: Config) -> Path:
    return Path(cfg.data_dir) / "notion"


def server_dir(cfg: Config) -> Path:
    return folder(cfg) / "server" / VERSION


def requests_log(cfg: Config) -> Path:
    return folder(cfg) / "requests.jsonl"


def token_file(cfg: Config) -> Path:
    return folder(cfg) / "token"


# --- token ------------------------------------------------------------------------------
def token(cfg: Config) -> str:
    """NOTION_TOKEN wins, then data/notion/token. "" if neither holds a well-formed token."""
    raw = os.environ.get("NOTION_TOKEN", "").strip()
    if not raw:
        try:
            raw = token_file(cfg).read_text(encoding="utf-8").strip()
        except OSError:
            raw = ""
    return raw if TOKEN_RE.match(raw) else ""


def save_token(cfg: Config, value: str) -> None:
    value = (value or "").strip()
    if not TOKEN_RE.match(value):
        raise NotionError("That is not a Notion integration token (it starts with ntn_ or secret_).")
    path = token_file(cfg)
    atomic_write(path, value + "\n")
    try:
        os.chmod(path, 0o600)  # POSIX: only you; Windows keeps the profile folder's rights
    except OSError:
        pass


# --- the MCP server ---------------------------------------------------------------------
def node() -> str | None:
    return shutil.which("node")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def installed(cfg: Config) -> bool:
    """Both files there and unchanged (checked on every run: the data folder is writable by anything you run)."""
    try:
        return all(_sha256(server_dir(cfg) / rel) == digest for rel, digest in FILES.items())
    except OSError:
        return False


def install(cfg: Config, fetch=None) -> Path:
    """Download the pinned tarball, check it against npm's hash, extract the two files and check them too."""
    fetch = fetch or _download
    blob = fetch(TARBALL)
    algo, _, want = INTEGRITY.partition("-")
    if base64.b64encode(hashlib.new(algo, blob).digest()).decode() != want:
        raise NotionError(f"The download of {PACKAGE} {VERSION} does not match npm's checksum. Nothing was installed.")
    out = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        for rel, digest in FILES.items():
            member = tar.getmember("package/" + rel)
            if not member.isfile():
                raise NotionError(f"{rel} in the package is not a file")
            data = tar.extractfile(member).read()
            if hashlib.sha256(data).hexdigest() != digest:
                raise NotionError(f"{rel} in the package does not match its checksum. Nothing was installed.")
            out[rel] = data
    base = server_dir(cfg)
    for rel, data in out.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    return base


def _download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as res:  # noqa: S310 - a fixed https URL
        blob = res.read(MAX_TARBALL + 1)
    if len(blob) > MAX_TARBALL:
        raise NotionError("The download is larger than expected")
    return blob


def mcp_server(cfg: Config) -> dict | None:
    """The --mcp-config entry of the Notion server, or None if Node, the files or the token are missing.
    The token is not in it: the run passes NOTION_TOKEN in its environment, which the server inherits."""
    exe = node()
    if not exe or not installed(cfg) or not token(cfg):
        return None
    return {"type": "stdio", "command": exe, "args": [str(server_dir(cfg) / "bin" / "cli.mjs")]}


# --- Notion's API (for checking the token and for deletions you approved) -------------------------
_urlopen = urllib.request.urlopen  # tests replace it


def api(cfg: Config, method: str, path: str, body: dict | None = None) -> dict:
    tok = token(cfg)
    if not tok:
        raise NotionError("No Notion token: run `python -m aos notion-connect`.")
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {tok}", "Notion-Version": API_VERSION,
                                          "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with _urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read().decode("utf-8")).get("message") or exc.reason
        except (ValueError, OSError, AttributeError):
            msg = exc.reason
        if exc.code == 404:
            msg = "Notion does not show this to Starlane. Is the page shared with your integration (••• → Connections)?"
        raise NotionError(f"Notion: {msg}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise NotionError(f"Notion is not reachable: {exc}") from None


def who(cfg: Config) -> str:
    """The integration's name (checks the token)."""
    me = api(cfg, "GET", "/users/me")
    return str(me.get("name") or (me.get("bot") or {}).get("workspace_name") or "your integration")


def page_id(text) -> str:
    """A Notion id from an id (with or without dashes) or a Notion URL, dashed; "" if there is none."""
    s = str(text or "").strip().lower().split("?", 1)[0].split("#", 1)[0].replace("-", "")
    found = _ID_RE.findall(s)
    if not found:
        return ""
    h = found[-1]
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def _plain(rich) -> str:
    return "".join(str(r.get("plain_text") or "") for r in rich or [] if isinstance(r, dict))


def describe(cfg: Config, kind: str, target: str) -> dict:
    """What Notion itself says the target is: its real title and link, so you never decide on the agent's word alone."""
    if kind == "page":
        p = api(cfg, "GET", f"/pages/{target}")
        title = next((_plain(v.get("title")) for v in (p.get("properties") or {}).values()
                      if isinstance(v, dict) and v.get("type") == "title"), "")
        return {"title": title or "(untitled page)", "url": str(p.get("url") or ""), "gone": bool(p.get("in_trash") or p.get("archived"))}
    b = api(cfg, "GET", f"/blocks/{target}")
    btype = str(b.get("type") or "block")
    inner = b.get(btype) if isinstance(b.get(btype), dict) else {}
    text = inner.get("title") if btype in ("child_page", "child_database") else _plain(inner.get("rich_text"))
    return {"title": f"{btype}: {str(text or '').strip()[:160] or '(no text)'}", "url": "", "gone": bool(b.get("in_trash") or b.get("archived"))}


# --- deletion requests (data/notion/requests.jsonl; a request appears several times, the last entry wins) ---------
def _append(cfg: Config, rec: dict) -> None:
    path = requests_log(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def all_requests(cfg: Config) -> list[dict]:
    """Newest first."""
    try:
        lines = requests_log(cfg).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    by_id: dict[str, dict] = {}
    for ln in lines:
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict) and isinstance(rec.get("id"), str):
            by_id[rec["id"]] = rec
    return list(by_id.values())[::-1]


def pending(cfg: Config) -> list[dict]:
    return [r for r in all_requests(cfg) if r.get("status") == "pending"]


def request_deletion(cfg: Config, *, kind: str, target: str, why: str, job: str = "", agent: str = "") -> dict:
    """File a request to delete a page (it goes to Notion's trash) or a block. Checks with Notion what it is first."""
    kind = str(kind or "").strip().lower()
    if kind not in ("page", "block"):
        raise NotionError('kind must be "page" or "block"')
    tid = page_id(target)
    if not tid:
        raise NotionError("No Notion id found: pass the page or block id (or the page's link).")
    why = " ".join(str(why or "").split())[:500]
    if not why:
        raise NotionError("Say why it should be deleted: the user decides on that.")
    facts = describe(cfg, kind, tid)
    if facts["gone"]:
        raise NotionError("It is already in Notion's trash.")
    now = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        waiting = pending(cfg)
        same = next((r for r in waiting if r.get("target") == tid), None)
        if same:
            return same
        if len(waiting) >= MAX_PENDING:
            raise NotionError(f"{MAX_PENDING} deletion requests are already waiting for the user.")
        rec = {"id": secrets.token_hex(6), "status": "pending", "kind": kind, "target": tid, "title": facts["title"][:200],
               "url": facts["url"], "why": why, "job": job, "agent": agent, "created": now, "decided": None, "note": ""}
        _append(cfg, rec)
    return rec


def decide(cfg: Config, rid: str, approve: bool) -> dict:
    """Your decision. Approved: Starlane deletes it now (a page goes to Notion's trash, where you can restore it for
    30 days; a block is deleted). Denied: nothing happens. Either way the request is closed."""
    with _LOCK:
        rec = next((r for r in pending(cfg) if r.get("id") == rid), None)
        if rec is None:
            raise KeyError(rid)
        now = datetime.now().isoformat(timespec="seconds")
        if not approve:
            done = {**rec, "status": "kept", "decided": now}
        else:
            try:
                if rec["kind"] == "page":
                    api(cfg, "PATCH", f"/pages/{rec['target']}", {"in_trash": True})
                else:
                    api(cfg, "DELETE", f"/blocks/{rec['target']}")
                done = {**rec, "status": "deleted", "decided": now}
            except NotionError as exc:
                done = {**rec, "status": "failed", "decided": now, "note": str(exc)[:300]}
        _append(cfg, done)
    return done


# --- for the dashboard and doctor (no network) ---------------------------------------------
def notion_agent(agents) -> object | None:
    return next((a for a in agents if TOOL in a.tools), None)


def status(cfg: Config, agents=()) -> dict:
    a = notion_agent(agents)
    has_node, has_files, has_token = bool(node()), installed(cfg), bool(token(cfg))
    return {"agent": a.id if a else None, "name": a.name if a else None, "enabled": bool(a and a.enabled),
            "node": has_node, "installed": has_files, "token": has_token, "ready": bool(a and has_node and has_files and has_token),
            "version": VERSION, "requests": pending(cfg),
            "recent": [r for r in all_requests(cfg) if r.get("status") != "pending"][:5]}
