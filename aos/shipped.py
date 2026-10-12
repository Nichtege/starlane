"""What a user's own folder starts with. `aos setup` copies it; a wheel carries it in aos/_shipped (see setup.py).

Stdlib only, and importable without the rest of the package: setup.py loads this file by path at build time.
"""

from __future__ import annotations

import shutil
from pathlib import Path

FILES = ("README.md", "CONTRIBUTING.md", "SECURITY.md", "LICENSE", "aos.toml", "routines.toml", "agents.toml", "aos_tick.pyw")
TREES = ("agents", "skills", "docs", "examples")
# Posix paths relative to the root: a developer's own agents and the digests generated from the demo vault never ship.
# Top-level only: examples/custom-agent/agents.local.toml is part of the example and does ship.
EXCLUDE_PATHS = frozenset({"agents/local", "agents.local.toml", "examples/vault/AI/Digest"})
EXCLUDE_NAMES = frozenset({".obsidian", "__pycache__", "Thumbs.db", "desktop.ini"})
EXCLUDE_SUFFIXES = (".pyc", ".lock")


def wanted(rel: str) -> bool:
    parts = rel.split("/")
    prefixes = {"/".join(parts[: i + 1]) for i in range(len(parts))}
    hidden = any(part.startswith(".") for part in parts)  # .DS_Store, ._x (macOS), .trash, .git: an editor's or a vault's own business
    return not (hidden or prefixes & EXCLUDE_PATHS or set(parts) & EXCLUDE_NAMES or rel.endswith(EXCLUDE_SUFFIXES))


def files(root: Path) -> list[str]:
    """Every shipped file as a posix path relative to `root`. A missing entry is an error: never ship half a folder."""
    out: list[str] = []
    for name in FILES:
        if not (root / name).is_file():
            raise FileNotFoundError(f"shipped file missing: {root / name}")
        out.append(name)
    for tree in TREES:
        found = [p.relative_to(root).as_posix() for p in sorted((root / tree).rglob("*")) if p.is_file()]
        found = [rel for rel in found if wanted(rel)]
        if not found:
            raise FileNotFoundError(f"shipped folder missing or empty: {root / tree}")
        out += found
    return out


def copy(src_root: Path, dst_root: Path, overwrite: bool = False) -> tuple[list[str], list[str]]:
    """Copy the shipped files into `dst_root`. Existing files are kept unless `overwrite`. Returns (copied, skipped)."""
    copied: list[str] = []
    skipped: list[str] = []
    for rel in files(src_root):
        target = dst_root / rel
        if (target.exists() or target.is_symlink()) and not overwrite:  # a dangling link is "there": never write through it
            skipped.append(rel)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_root / rel, target)  # content only: a read-only site-packages must not make the user's aos.toml read-only
        copied.append(rel)
    return copied, skipped
