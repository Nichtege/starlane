"""Memory layer: read the Obsidian vault, understand frontmatter and wikilinks.

Read-only. This module never changes a file in the vault.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

NOTE_EXTS = {".md": "md", ".base": "base", ".canvas": "canvas"}

MAX_NOTE_BYTES = 2_000_000  # larger files are only read up to here
MAX_LINE_CHARS = 2000  # longer lines are not run through regexes (guards against pathologically slow patterns)

# Every pattern here is deliberately bounded so a hostile note cannot stall the scheduler.
_INLINE_CODE_RE = re.compile(r"(`{1,10})([^`\n]+?)\1")
_WIKILINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
_TASK_RE = re.compile(r"^\s*[-*+]\s+\[([ xX])\]\s?(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _blank_text(text: str) -> str:
    """Replace text with spaces but keep line breaks (line numbers stay correct)."""
    return re.sub(r"[^\n]", " ", text)


def parse_heading(line: str) -> tuple[int, str] | None:
    """('## Title ##') -> (2, 'Title'). Closing hashes do not count, a '#' at the end of a word ('C#') does."""
    if len(line) > MAX_LINE_CHARS:
        return None
    m = _HEADING_RE.match(line)
    if not m:
        return None
    text = m.group(2).rstrip()
    stripped = text.rstrip("#")
    if stripped != text and (not stripped or stripped[-1].isspace()):
        text = stripped.rstrip()
    return len(m.group(1)), text


def strip_code(text: str) -> str:
    """Blank out code blocks, inline code and HTML comments. Linear in the length of the text."""
    # 1. HTML comments (find instead of a regex: no backtracking)
    out, pos = [], 0
    while True:
        start = text.find("<!--", pos)
        if start < 0:
            out.append(text[pos:])
            break
        end = text.find("-->", start + 4)
        out.append(text[pos:start])
        if end < 0:
            out.append(_blank_text(text[start:]))
            break
        out.append(_blank_text(text[start : end + 3]))
        pos = end + 3
    lines = "".join(out).split("\n")
    # 2. Code fences line by line (like Markdown itself); an unclosed fence runs to the end of the file
    in_fence, fence = False, ""
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        marker = next((m for m in ("```", "~~~") if stripped.startswith(m)), "")
        if in_fence:
            if marker == fence:
                in_fence = False
            lines[i] = _blank_text(line)
        elif marker:
            if stripped.count(marker) >= 2:  # ```like this``` on one line is inline code, not a fence
                lines[i] = _blank_text(line)
            else:
                in_fence, fence = True, marker
                lines[i] = _blank_text(line)
        elif len(line) <= MAX_LINE_CHARS and "`" in line:
            lines[i] = _INLINE_CODE_RE.sub(lambda m: _blank_text(m.group(0)), line)
    return "\n".join(lines)


def _key(name: str) -> str:
    """The form in which names are compared: composed Unicode (NFC), lower case.

    macOS and old git checkouts store file names decomposed (NFD) while a link is typed composed, so "Café" would not find "Café"."""
    return unicodedata.normalize("NFC", name).lower()


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)  # Python 3.12+
    if isjunction:
        return bool(isjunction(path))
    try:  # Python 3.11 on Windows: a junction is a reparse point that is not a symlink
        return bool(os.lstat(path).st_file_attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except (AttributeError, OSError):
        return False


def _scalar(value: str):
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return _strip_comment(v)


def _strip_comment(v: str) -> str:
    """Drop a trailing YAML comment: "status: new  # idea | new | ..." (quotes protect the value)."""
    v = v.strip()
    if v.startswith("#"):
        return ""
    if v[:1] not in ("\"", "'") and " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return v


def parse_frontmatter(text: str) -> tuple[dict, str, int]:
    """Simple YAML frontmatter (scalars, [a, b] lists, '- x' lists).

    Returns (frontmatter, body, line offset of the body).
    """
    text = text.lstrip(chr(0xFEFF))  # BOM
    if not text.startswith("---"):
        return {}, text, 0
    lines = text.split("\n")
    if lines[0].strip() != "---":
        return {}, text, 0
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        return {}, text, 0
    fm: dict = {}
    current: str | None = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s+(.*)$", raw)
        if item and current is not None and (fm.get(current, "") == "" or isinstance(fm.get(current), list)):
            if fm.get(current, "") == "":
                fm[current] = []  # 'key:' without a value, followed by a '- x' list
            if isinstance(fm[current], list):
                fm[current].append(_scalar(item.group(1)))
            continue
        kv = re.match(r"^([A-Za-zÄÖÜäöüß0-9_\-]+)\s*:\s*(.*)$", raw)
        if not kv:
            continue
        key, val = kv.group(1), _strip_comment(kv.group(2))
        current = key
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [_scalar(p) for p in _split_list(inner)] if inner else []
        elif val == "":
            fm[key] = ""
        else:
            fm[key] = _scalar(val)
    body = "\n".join(lines[end + 1 :])
    return fm, body, end + 1


def _split_list(inner: str) -> list[str]:
    parts, depth, buf = [], 0, ""
    for ch in inner:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        parts.append(buf)
    return parts


def link_target(raw: str) -> str:
    """'[[Target#Section|Alias]]' -> 'Target' (also with an escaped pipe inside tables)."""
    target = re.split(r"\\?\|", raw, maxsplit=1)[0]
    target = target.split("#", 1)[0].split("^", 1)[0]
    return target.strip().replace("\\", "/").lstrip("/")


def is_placeholder(target: str) -> bool:
    return any(ch in target for ch in "<>{}…") or "..." in target


@dataclass
class Link:
    target: str
    line: int
    embed: bool = False
    resolved: str | None = None


@dataclass
class Note:
    rel: str
    kind: str
    size: int
    mtime: float
    fm: dict = field(default_factory=dict)
    text: str = ""
    body_offset: int = 0
    title: str = ""
    links: list[Link] = field(default_factory=list)

    @property
    def area(self) -> str:
        return self.rel.split("/", 1)[0] if "/" in self.rel else "(root)"

    @property
    def stem(self) -> str:
        return Path(self.rel).stem

    def body_lines(self) -> list[tuple[int, str]]:
        """(1-based line number in the file, line) without frontmatter and without code."""
        clean = strip_code(self.text)
        return [(self.body_offset + i + 1, ln) for i, ln in enumerate(clean.split("\n")[self.body_offset :])]


class Vault:
    def __init__(self, root: Path, ignore: tuple[str, ...] = ()):
        self.root = Path(root)
        self.ignore = set(ignore)
        self.notes: dict[str, Note] = {}
        self.files: set[str] = set()
        self._by_path: dict[str, str] = {}
        self._by_name: dict[str, list[str]] = {}

    # --- Reading ------------------------------------------------------
    @classmethod
    def scan(cls, root: Path, ignore: tuple[str, ...] = ()) -> "Vault":
        v = cls(root, ignore)
        if not v.root.is_dir():
            raise FileNotFoundError(
                f"Vault not found: {v.root}. Set [vault] path in aos.toml (or AOS_VAULT), "
                "or create a starter vault with `python -m aos init <folder>`."
            )
        for dirpath, dirnames, filenames in os.walk(v.root):
            # Links (symlinks, Windows junctions) are not followed: otherwise a folder in the vault
            # could point anywhere on the disk or form a loop.
            # Dot folders and files are not notes (Obsidian skips them, and macOS leaves ._name.md next to files on exFAT/SMB).
            dirnames[:] = sorted(d for d in dirnames if d not in v.ignore and not d.startswith(".") and not _is_link(Path(dirpath) / d))
            for name in sorted(filenames):
                if name.startswith("."):
                    continue
                full = Path(dirpath) / name
                if _is_link(full):
                    continue
                rel = full.relative_to(v.root).as_posix()
                kind = NOTE_EXTS.get(full.suffix.lower())
                if kind:
                    try:
                        v.notes[rel] = v._load(full, rel, kind)
                    except OSError:  # deleted/renamed while scanning (Obsidian saving, git pull running)
                        continue
                v.files.add(rel)
        v._build_index()
        for note in v.notes.values():
            for link in note.links:
                link.resolved = v.resolve(link.target, note.rel)
        return v

    def _load(self, full: Path, rel: str, kind: str) -> Note:
        st = full.stat()
        note = Note(rel=rel, kind=kind, size=st.st_size, mtime=st.st_mtime)
        try:
            with full.open("rb") as fh:
                # utf-8-sig: Obsidian/Notepad may write a BOM. Huge files are only read up to the limit.
                text = fh.read(MAX_NOTE_BYTES).decode("utf-8-sig", errors="replace")
        except OSError:
            text = ""
        if kind == "md":
            text = text.replace("\r\n", "\n")
            note.fm, body, note.body_offset = parse_frontmatter(text)
            note.text = text
            note.title = self._title(note, body)
            note.links = self._md_links(strip_code(text))
        elif kind == "canvas":
            note.title = note.stem
            note.links = self._canvas_links(text)
        else:
            note.title = note.stem
        return note

    @staticmethod
    def _title(note: Note, body: str) -> str:
        for ln in strip_code(body).split("\n"):
            h = parse_heading(ln)
            if h and h[0] == 1:
                return re.sub(r"\[\[([^\]|]*\|)?([^\]]*)\]\]", r"\2", h[1]).strip()
        return str(note.fm.get("title") or note.stem)

    @staticmethod
    def _md_links(clean: str) -> list[Link]:
        out: list[Link] = []
        for m in _WIKILINK_RE.finditer(clean):
            target = link_target(m.group(2))
            if is_placeholder(target):
                continue
            line = clean.count("\n", 0, m.start()) + 1
            out.append(Link(target=target, line=line, embed=bool(m.group(1))))
        return out

    @staticmethod
    def _canvas_links(text: str) -> list[Link]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        return [
            Link(target=n["file"], line=0)
            for n in data.get("nodes", [])
            if isinstance(n, dict) and n.get("type") == "file" and n.get("file")
        ]

    # --- Resolving----------------------------------------------------
    def _build_index(self) -> None:
        for rel in self.files:
            low = _key(rel)
            self._by_path[low] = rel
            base = low.rsplit("/", 1)[-1]
            keys = {base}
            if low.endswith(".md"):
                self._by_path[low[:-3]] = rel
                keys.add(base[:-3])
            for k in keys:
                self._by_name.setdefault(k, []).append(rel)

    def resolve(self, target: str, source: str | None = None) -> str | None:
        """Obsidian rules: full path, partial path or unique file name. An empty target is the note itself."""
        t = link_target(target)
        if not t:
            return source
        key = _key(t)
        hit = self._by_path.get(key)
        if hit:
            return hit
        if "/" not in key:
            cands = self._by_name.get(key)
            if cands:
                return sorted(cands, key=lambda r: (r.count("/"), len(r), r))[0]
            return None
        suffix_hits = [r for lower, r in self._by_path.items() if lower.endswith("/" + key)]
        if suffix_hits:
            return sorted(suffix_hits, key=lambda r: (len(r), r))[0]
        return None

    # --- Queries ------------------------------------------------------
    def md_notes(self) -> list[Note]:
        return [n for n in self.notes.values() if n.kind == "md"]

    def get(self, rel: str) -> Note | None:
        return self.notes.get(rel)

    def backlinks(self) -> dict[str, set[str]]:
        back: dict[str, set[str]] = {rel: set() for rel in self.notes}
        for note in self.notes.values():
            for link in note.links:
                if link.resolved in back and link.resolved != note.rel:
                    back[link.resolved].add(note.rel)
        return back

    def outlinks(self, rel: str) -> set[str]:
        note = self.notes.get(rel)
        if not note:
            return set()
        return {l.resolved for l in note.links if l.resolved in self.notes and l.resolved != rel}


def tasks(note: Note) -> list[tuple[int, bool, str]]:
    """Checkboxes of a note: (line, done, text)."""
    out = []
    for line_no, line in note.body_lines():
        m = _TASK_RE.match(line)
        if m:
            out.append((line_no, m.group(1).lower() == "x", m.group(2).strip()))
    return out


def section(note: Note, heading: str) -> list[tuple[int, str]]:
    """Lines below the first heading that contains `heading` (up to the next heading of the same or a higher level)."""
    lines = note.body_lines()
    start = level = None
    for i, (_, ln) in enumerate(lines):
        h = parse_heading(ln)
        if h and start is None and heading.lower() in h[1].lower():
            start, level = i + 1, h[0]
        elif h and start is not None and h[0] <= level:
            return lines[start:i]
    return lines[start:] if start is not None else []


def strip_markup(text: str, limit: int = 160) -> str:
    """Wikilinks to display text, drop bold/italic/strikethrough, shorten."""
    text = text[:MAX_LINE_CHARS]
    text = re.sub(
        r"\[\[([^\]|]*\|)?([^\]]*)\]\]",
        lambda m: (m.group(2) or "").split("/")[-1],
        text,
    )
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*_~`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -–:")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
