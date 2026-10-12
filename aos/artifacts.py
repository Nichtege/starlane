"""Artifact library: everything the system and Claude produced, in one searchable place.

Sources (read-only, nothing is changed):
- HTML files in `data/artifacts`, `data/out` (without the dashboard itself) and `<vault>/<conventions.ai_dir>/Artifacts` (default `AI/Artifacts`)
- Markdown files in `<vault>/<digest.dir>` (digest, vault check, weekly review)
- successful agent and skill runs from `data/agents/jobs.jsonl`

Every artifact has a stable id (hash of source + relative path, or the job id). Over HTTP, content is only reachable
through such an id, never through a path: there is no way to request arbitrary files.
"""

from __future__ import annotations

import hashlib
import html as _html
import re
from datetime import datetime
from pathlib import Path

from . import agents as A
from .config import Config
from .mapcheck import redact
from .vault import _is_link, parse_frontmatter, strip_markup

MAX_ITEMS = 300
MAX_READ = 400_000  # bytes: larger files are not served
HEAD_BYTES = 12_000  # this much is read for title and excerpt
EXTRA_HTML_SUBDIR = "Artifacts"  # inside the AI folder of the vault ([conventions] ai_dir)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_H1_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_ID_RE = re.compile(r"(f|j)-[0-9a-f]{12}")


def _key_id(prefix: str, key: str) -> str:
    return f"{prefix}-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _roots(cfg: Config) -> list[tuple[str, str, Path, str]]:
    """(key, group, folder, kind) of all file sources."""
    roots: list[tuple[str, str, Path, str]] = [
        ("artifacts", "Artifacts", cfg.data_dir / "artifacts", "html"),
        ("out", "Output", cfg.out_dir, "html"),
        ("digest", "Digest", cfg.vault / cfg.digest_dir, "md"),
    ]
    rel = f"{cfg.conv.ai_dir}/{EXTRA_HTML_SUBDIR}"
    roots.append((f"vault:{rel}", "Vault artifacts", cfg.vault / rel, "html"))
    return roots


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).replace(microsecond=0).isoformat()


def _html_text(raw: str) -> tuple[str, str]:
    title = ""
    m = _TITLE_RE.search(raw) or _H1_RE.search(raw)
    if m:
        title = _html.unescape(_TAG_RE.sub("", m.group(1))).strip()
    body = _STYLE_RE.sub(" ", raw)
    body = _html.unescape(_TAG_RE.sub(" ", body))
    return title, re.sub(r"\s+", " ", body).strip()


def _md_text(raw: str, fallback: str) -> tuple[str, str]:
    fm, body, _ = parse_frontmatter(raw)
    title = str(fm.get("title") or "").strip()
    excerpt = ""
    for ln in body.splitlines():
        t = ln.strip()
        if not t:
            continue
        if t.startswith("#"):
            title = title or t.lstrip("#").strip()
            continue
        if t.startswith(("---", "|", ">", "<!--")):
            continue
        excerpt = strip_markup(t, 160)
        break
    return strip_markup(title, 100) or fallback, excerpt


def _walk(root: Path, kind: str):
    """(path, relative path) of all files of the kind, skipping linked folders/files, at most 3 levels deep."""
    pattern = "*.html" if kind == "html" else "*.md"
    for path in sorted(root.rglob(pattern)):
        rel = path.relative_to(root)
        if len(rel.parts) > 3 or any(_is_link(root.joinpath(*rel.parts[: i + 1])) for i in range(len(rel.parts))):
            continue
        yield path, rel


def _file_items(cfg: Config) -> list[dict]:
    items: list[dict] = []
    for key, group, root, kind in _roots(cfg):
        try:
            if not root.is_dir() or _is_link(root):
                continue
            found = list(_walk(root, kind))
        except OSError:
            continue
        for path, rel in found:
            if key == "out" and rel.as_posix() == "dashboard.html":
                continue  # the dashboard itself is not an artifact
            try:
                st = path.stat()
                with path.open("rb") as fh:
                    head = fh.read(HEAD_BYTES).decode("utf-8", errors="replace")
            except OSError:
                continue
            title, excerpt = _html_text(head) if kind == "html" else _md_text(head, path.stem)
            items.append({
                "id": _key_id("f", f"{key}:{rel.as_posix()}"), "title": redact(title or path.stem)[:120], "kind": kind,
                "group": "Archive" if kind == "md" and len(rel.parts) > 1 else group, "path": rel.as_posix(),
                "mtime": _iso(st.st_mtime), "size": st.st_size, "excerpt": redact(excerpt)[:160],
            })
    return items


def _job_title(job: dict) -> str:
    lines = (job.get("instruction") or "").strip().splitlines()
    return strip_markup(lines[0], 100) if lines else "Job"


def _job_group(job: dict) -> str:
    return f"Skill: {job['skill']}" if job.get("skill") else f"Agent: {job.get('agent', '?')}"


def _job_item(job: dict) -> dict:
    res = str(job["result"])
    return {
        "id": f"j-{job['id']}", "title": _job_title(job), "kind": "job", "group": _job_group(job), "path": "",
        "mtime": str(job.get("finished") or job.get("started") or ""), "size": len(res),
        "excerpt": strip_markup(re.sub(r"^#+\s*", "", res.lstrip()), 160),
    }


def list_artifacts(cfg: Config, limit: int = MAX_ITEMS) -> list[dict]:
    """Newest first, at most `limit` entries."""
    jobs = [_job_item(j) for j in A.all_jobs(cfg) if j.get("status") == "ok" and j.get("result")]
    items = _file_items(cfg) + jobs
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return items[:limit]


def read_artifact(cfg: Config, artifact_id: str) -> dict | None:
    """Entry with `content` (text) or None. Unknown, invalid or too large artifacts give None."""
    if not isinstance(artifact_id, str) or not _ID_RE.fullmatch(artifact_id):
        return None
    if artifact_id.startswith("j-"):
        job = A.get_job(cfg, artifact_id[2:])
        if not job or job.get("status") != "ok" or not job.get("result"):
            return None
        return {**_job_item(job), "content": job["result"]}
    for key, _group, root, kind in _roots(cfg):
        try:
            if not root.is_dir() or _is_link(root):
                continue
            for path, rel in _walk(root, kind):
                if _key_id("f", f"{key}:{rel.as_posix()}") != artifact_id:
                    continue
                if path.stat().st_size > MAX_READ:
                    return None
                meta = next((i for i in _file_items(cfg) if i["id"] == artifact_id), None)
                if meta is None:
                    return None
                text = path.read_text(encoding="utf-8", errors="replace")
                return {**meta, "content": redact(text)}
        except OSError:
            continue
    return None
