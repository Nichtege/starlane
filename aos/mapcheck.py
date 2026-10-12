"""Memory layer: checks that the vault is a maintained map (two-hop rule, links, rules from CLAUDE.md)."""

from __future__ import annotations

import os
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import date

from .config import Conventions
from .dates import iso_week_name, parse_iso
from .i18n import tr, tr_mark, trn
from .vault import MAX_LINE_CHARS, Vault, link_target

ATTACHMENT_EXTS = {".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pptx", ".docx", ".csv", ".zip"}

PLAINTEXT_LABEL = tr_mark("plaintext password/token")  # labels stay English here; the message translates them
# A keyword may sit inside a longer name (DB_PASSWORD, OPENAI_API_KEY, client_secret) but not inside a word ("tokens").
# 'passwort' stays so German notes are covered too.
_KEY = (r"(?<![A-Za-z])(?:passwort|password|passwd|passphrase|api[_\- ]?key|secret|token|access[_\-]?key)"
        r"(?:[_\-][A-Za-z]+){0,3}(?![A-Za-z0-9])")
_PASSWORD_KEY = r"(?<![A-Za-z])(?:passwort|password|passwd|passphrase)(?:[_\-][A-Za-z]+){0,2}(?![A-Za-z0-9])"
_SEP = r"[\"']?\s*[:=]\**\s*"  # "key": value (JSON), key = value, **key:** value
SECRET_PATTERNS = [
    (tr_mark("OpenAI/Anthropic key"), re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    (tr_mark("Stripe key"), re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}")),
    (tr_mark("GitHub token"), re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")),
    (tr_mark("GitLab token"), re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}")),
    (tr_mark("Hugging Face token"), re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    (tr_mark("npm token"), re.compile(r"\bnpm_[A-Za-z0-9]{30,}")),
    (tr_mark("AWS key"), re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (tr_mark("Google API key"), re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    (tr_mark("Slack token"), re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    (tr_mark("JSON web token"), re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    (tr_mark("private key"), re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----")),
    (tr_mark("bearer token"), re.compile(r"(?i)\bbearer\s+([A-Za-z0-9\-._~+/]{20,}=*)")),
    # only the credentials of scheme://user:pw@host, so the host stays readable
    (tr_mark("password in URL"), re.compile(r"(?<=://)[^\s/@:\[\]]+:([^\s/@\[\]]+)(?=@)")),
    # password-like keys: a quoted value may contain spaces ...
    (PLAINTEXT_LABEL, re.compile(r"(?i)" + _PASSWORD_KEY + _SEP + r"(?:\"([^\"\n]{4,})\"|'([^'\n]{4,})'|`([^`\n]{4,})`)")),
    # ... and so may an unquoted one on a config line (the key comes first), up to the end of the line
    (PLAINTEXT_LABEL, re.compile(
        r"(?im)^[ \t>*+\-]*(?:export\s+)?[A-Za-z0-9_.\-]*?" + _PASSWORD_KEY + _SEP + r"(?!\[)([^\s\"'`][^\n]{3,}?)[ \t]*$")),
    (PLAINTEXT_LABEL, re.compile(r"(?i)" + _KEY + _SEP + r"[`'\"]?([A-Za-z0-9_\-+/=.]{10,})")),
    # run-together upper-case environment names (PGPASSWORD=..., MYSQLPWD is out of scope)
    (PLAINTEXT_LABEL, re.compile(r"\b[A-Z]{2,12}(?:PASSWORD|PASSWD|SECRET|TOKEN|APIKEY)\s*=\s*[`'\"]?([^\s`'\"]{6,})")),
]


@dataclass
class Issue:
    severity: str  # error | warn | info
    code: str
    path: str
    line: int
    message: str


def _skip_fm(conv: Conventions) -> set[str]:
    """Notes that may go without frontmatter (folder readmes, rules, the index)."""
    readmes = {f"{d}/README.md" for d in (conv.archive_dir, conv.inbox_dir, conv.ideas_dir)}
    return {"README.md", "CLAUDE.md", conv.index_note} | readmes


def _bfs_depths(vault: Vault, roots: tuple[str, ...]) -> dict[str, int]:
    depth: dict[str, int] = {}
    queue: deque[str] = deque()
    for root in roots:
        if root in vault.notes:
            depth[root] = 0
            queue.append(root)
    while queue:
        cur = queue.popleft()
        for nxt in sorted(vault.outlinks(cur)):
            if nxt not in depth:
                depth[nxt] = depth[cur] + 1
                queue.append(nxt)
    return depth


def _mask(value: str) -> str:
    """Reveal nothing of the value (vault-check.md is synced via git): only its length."""
    return tr("{n} characters", n=len(value))


def redact(text: str) -> str:
    """Replace secret patterns with a placeholder before note text is copied into digest/dashboard data."""
    mark = tr("[redacted]")
    for _, pat in SECRET_PATTERNS:
        text = pat.sub(mark, text)
    return text


def count_text(counts: dict, sep: str = ", ") -> str:
    """The finding counts of run_checks() as text, singular and plural right: "1 error, 2 warnings, 0 notices"."""
    return sep.join((trn(counts["error"], "{n} error", "{n} errors"), trn(counts["warn"], "{n} warning", "{n} warnings"),
                     trn(counts["info"], "{n} notice", "{n} notices")))


def run_checks(vault: Vault, today: date, large_kb: int = 50, conv: Conventions | None = None) -> dict:
    conv = conv or Conventions()
    issues: list[Issue] = []

    def add(sev: str, code: str, path: str, line: int, msg: str) -> None:
        issues.append(Issue(sev, code, path, line, msg))

    roots = conv.roots
    index_links = vault.outlinks(conv.index_note)

    # 1. Links -----------------------------------------------------------
    missing_attachments: dict[str, int] = {}
    checked = [n for n in vault.notes.values() if not conv.is_template(n.rel) and not conv.is_generated(n.rel)]
    for note in checked:
        for link in note.links:
            if link.resolved is not None:
                continue
            ext = os.path.splitext(link.target)[1].lower()
            if ext in ATTACHMENT_EXTS:
                missing_attachments[note.rel] = missing_attachments.get(note.rel, 0) + 1
            else:
                add("error", "broken-link", note.rel, link.line, tr("Link to nowhere: [[{target}]]", target=link.target))
    for rel, n in sorted(missing_attachments.items()):
        add("info", "attachment-local", rel, 0, tr("{n} links to attachments that are not in the vault (e.g. local PDFs, intended)", n=n))

    # 2. Two-hop rule ------------------------------------------------------
    depth = _bfs_depths(vault, roots)
    scored = [n for n in vault.md_notes() if not conv.is_template(n.rel) and n.rel not in roots and n.rel not in ("CLAUDE.md", "README.md") and not conv.is_generated(n.rel)]
    within2 = sum(1 for n in scored if depth.get(n.rel, 99) <= 2)
    for n in scored:
        d = depth.get(n.rel)
        if d is None:
            add("warn", "unreachable", n.rel, 0, tr("Not reachable from {index} or the brain map: new notes belong in the index", index=conv.index_note))
        elif d > 3:
            add("info", "deep", n.rel, 0, tr("{n} hops from the entry points (goal: at most 2)", n=d))

    # 3. Frontmatter and rules ---------------------------------------------
    skip_fm = _skip_fm(conv)
    for note in vault.md_notes():
        rel = note.rel
        if rel in skip_fm or conv.is_template(rel) or conv.is_generated(rel):
            continue
        fm = note.fm
        typ = str(fm.get(conv.type_key, ""))
        if not fm:
            add("warn", "no-frontmatter", rel, 1, tr("No frontmatter ({keys})", keys=f"{conv.type_key}, {conv.created_key}, {conv.tags_key}"))
            continue
        if not typ:
            add("warn", "no-type", rel, 1, tr("Frontmatter without `{key}`", key=conv.type_key))
        if not fm.get(conv.created_key):
            add("info", "no-created", rel, 1, tr("Frontmatter without `{key}`", key=conv.created_key))
        status = str(fm.get(conv.status_key, ""))
        if typ == conv.type_project and status and status not in conv.project_status and status != conv.status_done:
            add("warn", "bad-status", rel, 1, tr("Project status `{status}` is not valid ({allowed})", status=status,
                                                 allowed=", ".join(sorted(conv.project_status))))
        if typ == conv.type_idea and status and status not in conv.idea_status:
            add("warn", "bad-status", rel, 1, tr("Idea status `{status}` is not valid ({allowed})", status=status,
                                                 allowed=", ".join(sorted(conv.idea_status))))
        deadline = fm.get(conv.deadline_key)
        if typ == conv.type_project and deadline and parse_iso(str(deadline)) is None:
            add("warn", "bad-deadline", rel, 1, tr("`{key}: {value}` is not YYYY-MM-DD", key=conv.deadline_key, value=deadline))
        if rel.startswith(conv.ai_dir + "/") and rel != conv.brain_map:
            _check_ai_link(vault, note, index_links, add, conv)

    # 4. Brain map -----------------------------------------------------------
    bm = vault.get(conv.brain_map)
    if bm:
        mentioned = {l.resolved for l in bm.links if l.resolved}
        line_re = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\][^\n]*?·\s*\**(<\s*)?([\d.,]+)\s*KB")
        for ln_no, ln in bm.body_lines():
            if len(ln) > MAX_LINE_CHARS:
                continue
            m = line_re.search(ln)
            if not m:
                continue
            target = vault.resolve(link_target(m.group(1)), bm.rel)
            if target and target in vault.notes:
                try:
                    claimed = float(m.group(3).replace(",", "."))
                except ValueError:
                    continue
                actual = vault.notes[target].size / 1024
                if m.group(2) and actual <= claimed:  # "< 1 KB" holds as long as the file is smaller
                    continue
                if claimed >= 1 and abs(actual - claimed) / claimed > 0.5:
                    add("info", "brain-map-size", bm.rel, ln_no, tr("{target}: map says {claimed} KB, actual {actual} KB (off by > 50 %, rule from the map)",
                                                                   target=target, claimed=f"{claimed:g}", actual=f"{actual:.0f}"))
        mapped_areas = (conv.projects_dir, conv.areas_dir, conv.resources_dir)
        for n in vault.md_notes():
            if n.rel.startswith(tuple(a + "/" for a in mapped_areas)) and not conv.is_template(n.rel) and n.rel not in mentioned and n.size > 3000:
                add("info", "brain-map-missing", n.rel, 0, tr("Larger note is missing from the brain map"))

    # 5. Large files -------------------------------------------------------
    for n in vault.md_notes():
        if n.size > large_kb * 1024 and not conv.is_generated(n.rel):
            add("info", "large", n.rel, 0, tr("{kb} KB: never read it whole (grep the headings, then read a section)", kb=n.size // 1024))

    # 6. Secrets ---------------------------------------------------------
    for n in vault.md_notes():
        for i, raw in enumerate(n.text.split("\n"), start=1):
            for label, pat in SECRET_PATTERNS:
                m = pat.search(raw)
                if m:
                    value = next((g for g in m.groups() if g), m.group(0))
                    if label == PLAINTEXT_LABEL and not (re.search(r"\d", value) and re.search(r"[A-Za-z]", value)):
                        continue
                    add("error", "secret", n.rel, i, tr("Possible credential ({label}, {size}). CLAUDE.md forbids this.", label=tr(label), size=_mask(value)))
                    break

    # 7. Week note ---------------------------------------------------------
    if any(r.startswith(conv.journal_dir + "/") for r in vault.notes):
        wk = conv.week_note(today)
        if wk not in vault.notes:
            add("warn", "no-week-note", wk, 0, tr("Week note {week} is missing (create it from {template})", week=iso_week_name(today), template=conv.week_template))

    order = {"error": 0, "warn": 1, "info": 2}
    counts = {s: sum(1 for i in issues if i.severity == s) for s in order}
    return {
        "issues": [asdict(i) for i in sorted(issues, key=lambda i: (order[i.severity], i.path, i.line))],
        "counts": counts,
        "stats": {
            "notes": len([n for n in vault.notes.values() if not conv.is_generated(n.rel)]),
            "scored": len(scored),
            "within_two_hops": within2,
            "within_two_hops_pct": round(100 * within2 / len(scored)) if scored else 100,
        },
    }


def _targets(value) -> list[str]:
    """A project key may hold one link or a list of links."""
    items = value if isinstance(value, list) else [value]
    out = []
    for item in items:
        t = link_target(re.sub(r"^\[+|\]+$", "", str(item or "").strip()))
        if t:
            out.append(t)
    return out


def _check_ai_link(vault: Vault, note, index_links: set[str], add, conv: Conventions) -> None:
    rel = note.rel
    keys = (conv.project_key, conv.projects_key, conv.area_key)
    targets = [t for k in keys for t in _targets(note.fm.get(k))]
    shown = "`/`".join(keys)
    if not targets:
        if rel not in index_links:
            add("warn", "ai-unlinked", rel, 1, tr("AI note without `{keys}` and not linked from the index", keys=shown))
        return
    for target in targets:
        if not vault.resolve(target, rel):
            add("error", "ai-bad-link", rel, 1, tr("`{keys}` points to [[{target}]], which does not exist", keys=shown, target=target))
            return
    head = "\n".join(ln for _, ln in note.body_lines()[:20])
    if conv.belongs_to not in head or not any(f"[[{t}" in head for t in targets):
        add("warn", "ai-no-part-of", rel, 1, tr("Line `{line}` below the heading is missing", line=f"{conv.belongs_to} [[{targets[0]}]]"))
