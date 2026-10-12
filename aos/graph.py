"""Build the knowledge graph from the vault (nodes = notes, edges = wikilinks)."""

from __future__ import annotations

import re
from datetime import datetime

from .config import Conventions
from .vault import Vault

_WORD_RE = re.compile(r"\w+", re.U)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def build_graph(vault: Vault, conv: Conventions | None = None) -> dict:
    conv = conv or Conventions()
    back = vault.backlinks()
    nodes = []
    for rel, note in sorted(vault.notes.items()):
        out = vault.outlinks(rel)
        tags = note.fm.get(conv.tags_key)
        nodes.append(
            {
                "id": rel,
                "label": note.title or note.stem,
                "kind": note.kind,
                "area": note.area,
                "type": str(note.fm.get(conv.type_key, "")),
                "status": str(note.fm.get(conv.status_key, "")),
                "project": _wikilink_target(note.fm.get(conv.project_key)),
                "deadline": str(note.fm.get(conv.deadline_key, "") or ""),
                "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
                "size": note.size,
                "words": len(_WORD_RE.findall(note.text)) if note.kind == "md" else 0,
                "mtime": _iso(note.mtime),
                "in": len(back.get(rel, ())),
                "out": len(out),
            }
        )
    edges: dict[tuple[str, str], int] = {}
    for rel, note in vault.notes.items():
        for link in note.links:
            if link.resolved in vault.notes and link.resolved != rel:
                edges[(rel, link.resolved)] = edges.get((rel, link.resolved), 0) + 1
    return {
        "nodes": nodes,
        "edges": [{"s": s, "t": t, "w": w} for (s, t), w in sorted(edges.items())],
    }


def _wikilink_target(value) -> str:
    if not value:
        return ""
    m = re.search(r"\[\[([^\]|#]+)", str(value))
    return m.group(1).strip() if m else ""


def changes_by_day(vault: Vault, exclude_prefixes: tuple[str, ...] = ()) -> dict[str, list[str]]:
    """File -> day it changed, for the timeline. Generated files (digest) stay out."""
    days: dict[str, list[str]] = {}
    for rel, note in vault.notes.items():
        if rel.startswith(exclude_prefixes):
            continue
        days.setdefault(_iso(note.mtime), []).append(rel)
    return {d: sorted(v) for d, v in sorted(days.items())}
