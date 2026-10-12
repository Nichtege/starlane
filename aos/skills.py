"""Skills: the system's recipes (SOPs), shown as a deck in the dashboard and runnable from the terminal.

A skill is a folder with `SKILL.md` (frontmatter `name`, `description`, optional `model`, `effort`) and
any number of reference files next to it (brand, checklists, examples). SKILL.md is the router, Claude reads
the references when needed.

Skills are found in `[skills] dirs` (aos.toml). Per id the first hit wins: the project beats
`~/.claude/skills`. Linked skill folders (symlink, junction) are skipped and linked files are left out of the
reference list.

Safety: a skill run uses the same lock as the vault agents (only Read/Grep/Glob, no web tools, no connectors,
answer redacted and never written into notes). In addition its own skill folder is added with `--add-dir` so
the references are reachable. Model and effort come from fixed lists, never as free text.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .vault import _is_link, parse_frontmatter

MODELS = ("haiku", "sonnet", "opus", "fable")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
DEFAULT_MODEL = "sonnet"
MAX_SKILL_MD = 200_000  # larger SKILL.md files are not read at all
MAX_REFS = 40
MAX_REF_DEPTH = 3
ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,34}$")


@dataclass(frozen=True)
class Skill:
    id: str
    name: str
    description: str
    source: str  # "project" (inside the project folder) or "user" (e.g. ~/.claude/skills)
    path: Path  # SKILL.md
    refs: tuple[str, ...]  # reference files relative to the skill folder
    model: str  # default model
    effort: str  # default effort ("" = Claude's default)

    @property
    def dir(self) -> Path:
        return self.path.parent


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:35].strip("-")


def _refs(folder: Path) -> tuple[str, ...]:
    out: list[str] = []

    def walk(d: Path, depth: int) -> None:
        try:
            entries = sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for e in entries:
            if len(out) >= MAX_REFS or _is_link(e) or e.name.startswith("."):
                continue
            if e.is_dir():
                if depth < MAX_REF_DEPTH:
                    walk(e, depth + 1)
            elif e.is_file() and not (d == folder and e.name == "SKILL.md"):
                out.append(e.relative_to(folder).as_posix())

    walk(folder, 1)
    return tuple(out)


def _first_line(body: str) -> str:
    for ln in body.splitlines():
        t = ln.strip().lstrip("#").strip()
        if t:
            return t[:200]
    return ""


def _load(folder: Path, project_root: Path) -> Skill | None:
    md = folder / "SKILL.md"
    if _is_link(folder) or _is_link(md) or not md.is_file():
        return None
    try:
        if md.stat().st_size > MAX_SKILL_MD:
            return None
        text = md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    fm, body, _ = parse_frontmatter(text)
    sid = slug(folder.name)
    if not ID_RE.match(sid):
        return None
    desc = str(fm.get("description") or "").strip()
    if desc in ("", ">", "|", ">-", "|-"):  # the simple parser does not understand multi-line YAML
        desc = _first_line(body)
    model = str(fm.get("model") or "").strip().lower()
    effort = str(fm.get("effort") or "").strip().lower()
    try:
        folder.resolve().relative_to(project_root.resolve())
        source = "project"
    except ValueError:
        source = "user"
    return Skill(
        id=sid,
        name=str(fm.get("name") or folder.name).strip()[:60] or sid,
        description=desc[:300],
        source=source,
        path=md,
        refs=_refs(folder),
        model=model if model in MODELS else DEFAULT_MODEL,
        effort=effort if effort in EFFORTS else "",
    )


def discover(cfg: Config) -> list[Skill]:
    """All skills, sorted by name. Missing folders are not an error (there simply are none then)."""
    found: dict[str, Skill] = {}
    for base in cfg.skills_dirs:
        try:
            if not base.is_dir() or _is_link(base):
                continue
            children = sorted(p for p in base.iterdir() if p.is_dir())
        except OSError:
            continue
        for child in children:
            skill = _load(child, cfg.project_root)
            if skill and skill.id not in found:
                found[skill.id] = skill
    return sorted(found.values(), key=lambda s: s.name.lower())


def get(cfg: Config, skill_id: str) -> Skill | None:
    return next((s for s in discover(cfg) if s.id == skill_id), None)


QUOTED_LIMIT = 20_000  # Windows: command line at most 32,767 characters; quotes are doubled when quoting


def _quoted_len(text: str) -> int:
    return len(subprocess.list2cmdline([text]))


def prompt_text(skill: Skill, limit: int = 20_000) -> str:
    """SKILL.md without frontmatter as the system prompt. Truncated by characters (`limit`) and by the length the
    text has after quoting for the Windows command line (many quotes make it longer)."""
    _, body, _ = parse_frontmatter(skill.path.read_text(encoding="utf-8", errors="replace"))
    body = body.strip()
    refs = ""
    if skill.refs:
        refs = f"\n\nReference files of this skill (read them with Read when needed), folder {skill.dir.as_posix()}:\n" + "\n".join(
            f"- {r}" for r in skill.refs)
    note = f"\n\n[… truncated. Read the rest with the Read tool in {skill.path}]"
    head = f"# Skill: {skill.name}\n\n"
    cut = len(body) > limit
    if cut:
        body = body[:limit]
    while _quoted_len(head + body + (note if cut else "") + refs) > QUOTED_LIMIT and len(body) > 200:
        body = body[: int(len(body) * 0.85)]
        cut = True
    return head + body + (note if cut else "") + refs
