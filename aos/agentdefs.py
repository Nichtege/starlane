"""Custom agents: create, change, delete (dashboard, `aos agent-new`, `aos agent-rm`).

Custom agents live apart from the shipped ones:

    agents.toml              maintained by hand, with comments (never touched here)
    agents.local.toml        owned by this module: one `[[agent]]` block per custom agent, rewritten completely
    agents/local/<id>.md     the custom agent's prompt (freely editable, kept when other fields change)

`load_agents()` reads both files together, so every other part of the system (Atlas, server, CLI) sees the
custom agents like all others. The safety rules are the same as for agents.toml and are not bypassed here:
tools only by access type (read the vault OR the web, never both), model from the fixed list, no path
outside agents/local/, prompt without credential patterns.
"""

from __future__ import annotations

import json
import re
import threading
import time
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import agents as A
from . import skills as S
from .config import Config
from .i18n import tr, tr_mark
from .mapcheck import redact
from .scheduler import Busy, TickLock, atomic_write

CUSTOM_GROUP = tr_mark("Custom")  # stored in English, shown translated (tr(group))
ACCESS = {"vault": A.VAULT_TOOLS, "web": A.WEB_TOOLS}
MAX_CUSTOM = 40
NAME_MAX = 40
DESC_MIN, DESC_MAX = 10, 280
INSTR_MIN, INSTR_MAX = 20, 6000
GROUP_MAX = 40
KEYWORD_MAX, KEYWORDS_MAX = 30, 12
TIMEOUT_MIN = 30
CAP_MAX = 200
PROMPT_DIR = "agents/local"
_LOCK = threading.Lock()  # threads of this process; _locked() adds a lock file against a parallel CLI or server
FILE_LOCK_WAIT_S = 5
FILE_LOCK_STALE_S = 60  # a lock file older than this comes from a crashed process
_BARE_KEY = re.compile(r"^[A-Za-z0-9_\-]+$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # \t and \n stay allowed (instructions span several lines)
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"})

HEADER = """\
# Custom agents. This file is managed by the dashboard (Atlas -> "New agent") and `aos agent-new`.
# It is rewritten completely on every change: comments are not kept.
# The prompts live in agents/local/<id>.md and may be edited by hand.
# The shipped agents live in agents.toml and are never changed.
"""

# printed by `aos agent-new --template` in the interface language: tr(TEMPLATE)
TEMPLATE = tr_mark("""## Identity
You are <role in one sentence: who you are and what you are responsible for>.

## Working method
- <How do you proceed? What do you deliver first, what after that?>
- <How do you back up statements? What do you do when you are unsure?>

## Boundaries
- <What do you explicitly not do?>
- <When do you ask back, when do you work with assumptions?>
""")


@dataclass(frozen=True)
class Spec:
    name: str
    description: str
    instructions: str
    access: str
    group: str
    model: str
    keywords: tuple[str, ...]
    examples: tuple[str, ...]
    timeout_s: int
    max_runs_per_day: int
    enabled: bool


# --- paths ---------------------------------------------------------------------------------
def local_file(cfg: Config) -> Path:
    """agents.toml -> agents.local.toml (same folder, so relative prompt paths resolve the same way)."""
    base = Path(cfg.agents_file)
    return base.with_name(base.stem + ".local.toml")


def prompt_dir(cfg: Config) -> Path:
    return (Path(cfg.agents_file).parent / PROMPT_DIR).resolve()


@contextmanager
def _locked(cfg: Config):
    """Thread lock plus a lock file next to agents.local.toml (O_EXCL): the dashboard server and `aos agent-new` in a
    terminal never rewrite the file at the same time. Waits up to FILE_LOCK_WAIT_S, then refuses with 409."""
    path = local_file(cfg).with_suffix(".lock")
    with _LOCK:
        deadline = time.monotonic() + FILE_LOCK_WAIT_S
        while True:
            try:
                lock = TickLock(path, stale_s=FILE_LOCK_STALE_S)
                lock.__enter__()
                break
            except Busy:
                if time.monotonic() > deadline:
                    raise A.Refused(tr("Custom agents are being changed elsewhere right now. Try again in a moment."), 409) from None
                time.sleep(0.1)
        try:
            yield
        finally:
            lock.__exit__(None, None, None)


# --- input validation ------------------------------------------------------------------------
def slugify(name: str) -> str:
    """Name -> id (a-z, 0-9, hyphen). German umlauts are transliterated, anything else unsuitable is dropped."""
    s = re.sub(r"[^a-z0-9]+", "-", str(name).translate(_UMLAUTS).lower()).strip("-")[:40].strip("-")
    return s or "agent"


def _utf8(text: str, label: str) -> None:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise A.Refused(tr("{label} contains invalid characters", label=tr(label)), 400) from None


# The `label` arguments are English field names marked with tr_mark; the messages translate them.
def _one_line(value, label: str, lo: int, hi: int) -> str:
    if not isinstance(value, str):
        raise A.Refused(tr("{label} is missing", label=tr(label)), 400)
    text = re.sub(r"\s+", " ", value).strip()
    if _CONTROL.search(text):
        raise A.Refused(tr("{label} contains control characters", label=tr(label)), 400)
    if len(text) < lo:
        raise A.Refused(tr("{label} is too short (at least {n} characters)", label=tr(label), n=lo) if lo > 1
                        else tr("{label} is missing", label=tr(label)), 400)
    if len(text) > hi:
        raise A.Refused(tr("{label} is too long ({n} characters, at most {max})", label=tr(label), n=len(text), max=hi), 400)
    _utf8(text, label)
    return text


def _list(value, label: str, split: str) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = re.split(split, value)
    elif isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise A.Refused(tr("{label} must be a list of strings", label=tr(label)), 400)
    return [re.sub(r"\s+", " ", v).strip() for v in value if v.strip()]


def _bounded(value, label: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise A.Refused(tr("{label} must be an integer", label=tr(label)), 400)
    if not lo <= value <= hi:
        raise A.Refused(tr("{label} must be between {lo} and {hi}", label=tr(label), lo=lo, hi=hi), 400)
    return value


def parse_spec(raw: dict, *, base: Spec | None = None) -> Spec:
    """Check and clean the fields. With `base` (update), missing fields keep their previous value.
    Violations are `Refused` with code 400 and a message that can be shown to the person as is."""
    if not isinstance(raw, dict):
        raise A.Refused(tr("Agent details are missing"), 400)

    def pick(key, default):
        return raw[key] if key in raw else (getattr(base, key) if base else default)

    name = _one_line(pick("name", None), tr_mark("Name"), 1, NAME_MAX)
    description = _one_line(pick("description", None), tr_mark("Description"), DESC_MIN, DESC_MAX)
    instructions = pick("instructions", None)
    if not isinstance(instructions, str):
        raise A.Refused(tr("Instructions are missing"), 400)
    instructions = instructions.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(instructions) < INSTR_MIN:
        raise A.Refused(tr("Instructions are too short (at least {n} characters): describe role, working method and boundaries", n=INSTR_MIN), 400)
    if len(instructions) > INSTR_MAX:
        raise A.Refused(tr("Instructions are too long ({n} characters, at most {max})", n=len(instructions), max=INSTR_MAX), 400)
    if _CONTROL.search(instructions):
        raise A.Refused(tr("Instructions contain control characters"), 400)
    _utf8(instructions, tr_mark("Instructions"))
    if redact(instructions) != instructions:
        raise A.Refused(tr("The instructions look like they contain a password or key. That does not belong in a prompt."), 400)
    access = str(pick("access", "vault")).strip().lower()
    if access not in ACCESS:
        raise A.Refused(tr("Access must be 'vault' (read notes) or 'web' (web search), not both"), 400)
    group = pick("group", CUSTOM_GROUP)
    group = _one_line(group, tr_mark("Group"), 1, GROUP_MAX) if str(group or "").strip() else CUSTOM_GROUP
    model = str(pick("model", S.DEFAULT_MODEL)).strip().lower()
    if model not in S.MODELS:
        raise A.Refused(tr("Model '{model}' is not allowed. Allowed: {allowed}", model=model, allowed=", ".join(S.MODELS)), 400)
    keywords: list[str] = []
    for k in _list(pick("keywords", []), tr_mark("Keywords"), r"[,\n]"):
        k = k.lower()
        if len(k) < 2 or len(k) > KEYWORD_MAX or _CONTROL.search(k):
            raise A.Refused(tr("Keyword '{keyword}' is invalid (2 to {max} characters)", keyword=k[:KEYWORD_MAX], max=KEYWORD_MAX), 400)
        _utf8(k, tr_mark("Keyword"))
        if k not in keywords:
            keywords.append(k)
    if len(keywords) > KEYWORDS_MAX:
        raise A.Refused(tr("At most {n} keywords", n=KEYWORDS_MAX), 400)
    examples = _list(pick("examples", []), tr_mark("Examples"), r"\n")
    if len(examples) > A.MAX_EXAMPLES:
        raise A.Refused(tr("At most {n} examples", n=A.MAX_EXAMPLES), 400)
    for e in examples:
        if len(e) > A.MAX_EXAMPLE_CHARS or _CONTROL.search(e):
            raise A.Refused(tr("An example is too long (at most {n} characters)", n=A.MAX_EXAMPLE_CHARS), 400)
        _utf8(e, tr_mark("Example"))
    timeout_default = 480 if access == "web" else A.DEFAULT_TIMEOUT_S
    timeout_s = _bounded(pick("timeout_s", timeout_default), tr_mark("Time limit"), TIMEOUT_MIN, A.MAX_TIMEOUT_S)
    cap = _bounded(pick("max_runs_per_day", 20), tr_mark("Daily cap"), 1, CAP_MAX)
    enabled = pick("enabled", True)
    if not isinstance(enabled, bool):
        raise A.Refused(tr("`enabled` must be true or false"), 400)
    return Spec(name, description, instructions, access, group, model, tuple(keywords), tuple(examples), timeout_s, cap, enabled)


# --- read and write the file ------------------------------------------------------------
def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    return json.dumps(str(v), ensure_ascii=False)  # JSON strings are valid TOML basic strings (control characters were rejected before)


def _render(entries: list[dict]) -> str:
    out = [HEADER]
    for e in entries:
        out.append("[[agent]]")
        # keys added by hand may need quotes (`"my key" = 1`); a bare key that is not one would break the file
        out += [f"{k if _BARE_KEY.match(k) else json.dumps(k, ensure_ascii=False)} = {_toml_value(v)}"
                for k, v in e.items() if isinstance(v, (str, int, bool, list))]
        out.append("")
    return "\n".join(out)


def _read_entries(cfg: Config) -> list[dict]:
    path = local_file(cfg)
    if not path.is_file():
        return []
    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise A.AgentError(tr("{file} is not valid TOML: {error}", file=path.name, error=exc)) from exc
    return [dict(e) for e in raw.get("agent", []) if isinstance(e, dict)]


def _write_entries(cfg: Config, entries: list[dict]) -> None:
    path = local_file(cfg)
    if entries:
        atomic_write(path, _render(entries))
    elif path.exists():
        path.unlink()  # no custom agent left: do not leave an empty file behind


def _entry_for(agent_id: str, spec: Spec, existing: dict | None = None) -> dict:
    e = dict(existing or {})
    e.update(
        id=agent_id, name=spec.name, group=spec.group, description=spec.description, model=spec.model,
        tools=list(ACCESS[spec.access]), timeout_s=spec.timeout_s, max_runs_per_day=spec.max_runs_per_day,
        enabled=spec.enabled, prompt=f"{PROMPT_DIR}/{agent_id}.md", keywords=list(spec.keywords), examples=list(spec.examples),
    )
    return e


def _prompt_path(cfg: Config, agent_id: str) -> Path:
    p = (prompt_dir(cfg) / f"{agent_id}.md").resolve()
    if not p.is_relative_to(prompt_dir(cfg)):  # ID_RE already prevents this; a second lock here
        raise A.Refused(tr("Invalid agent id"), 400)
    return p


def _prompt_text(spec: Spec) -> str:
    return f"# {spec.name}\n\n{spec.instructions}\n"


def _body(text: str, name: str) -> str:
    """Prompt file -> instructions: the heading written by the system is dropped, the rest stays as it is."""
    head = f"# {name}\n"
    if text.startswith(head):
        text = text[len(head):]
    return text.strip()


def _all_ids(cfg: Config) -> set[str]:
    return {a.id for a in A.load_agents(cfg.agents_file)}


def _unique_id(cfg: Config, wanted: str) -> str:
    taken = _all_ids(cfg)
    base = wanted[:36].strip("-") or "agent"
    if base == A.ATLAS_ID or base.startswith(("skill-", "atlas-")) or A.RESERVED_IDS.match(base):
        base = f"custom-{base}"  # reserved names: otherwise every numbered variant would land in the reserved range too
    cand, n = base, 2
    while cand in taken:
        cand = f"{base}-{n}"
        n += 1
    return cand


def _busy(cfg: Config, agent_id: str) -> bool:
    now = datetime.now().replace(microsecond=0)
    return any(j.get("agent") == agent_id and A._is_active(j, now) for j in A.all_jobs(cfg))


def _spec_of(cfg: Config, e: dict) -> Spec:
    tools = e.get("tools") or []
    access = "web" if any(t in A.WEB_TOOLS for t in tools) else "vault"
    try:
        body = _body(_prompt_path(cfg, str(e.get("id"))).read_text(encoding="utf-8"), str(e.get("name", "")))
    except OSError:
        body = ""
    return Spec(
        name=str(e.get("name", e.get("id", ""))), description=str(e.get("description", "")), instructions=body, access=access,
        group=str(e.get("group", "")) or CUSTOM_GROUP, model=str(e.get("model", S.DEFAULT_MODEL)),
        keywords=tuple(str(k) for k in e.get("keywords", []) if isinstance(k, str)),
        examples=tuple(str(x) for x in e.get("examples", []) if isinstance(x, str)),
        timeout_s=int(e.get("timeout_s", A.DEFAULT_TIMEOUT_S)), max_runs_per_day=int(e.get("max_runs_per_day", 20)),
        enabled=e.get("enabled", True) is not False,
    )


def _not_custom(cfg: Config, agent_id: str):
    """Not a custom agent: either shipped (Refused 403) or unknown (KeyError)."""
    if any(a.id == agent_id for a in A.load_agents(cfg.agents_file)):
        raise A.Refused(tr("Only custom agents can be changed or deleted. Shipped agents live in agents.toml."), 403)
    raise KeyError(tr("Unknown agent: {id}", id=agent_id))


def _commit(cfg: Config, entries: list[dict], agent_id: str, prompt_text: str | None) -> None:
    """Write prompt and entries, then cross-check. If the check fails, the old state is restored."""
    path = local_file(cfg)
    prompt = _prompt_path(cfg, agent_id)
    old_toml = path.read_text(encoding="utf-8") if path.is_file() else None
    old_md = prompt.read_text(encoding="utf-8") if prompt.is_file() else None
    try:
        if prompt_text is not None:
            atomic_write(prompt, prompt_text)
        _write_entries(cfg, entries)
        A.load_agents(cfg.agents_file)  # the same check as at startup: tools, paths, duplicate ids
    except Exception:
        if old_toml is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, old_toml)
        if prompt_text is not None:
            if old_md is None:
                prompt.unlink(missing_ok=True)
            else:
                atomic_write(prompt, old_md)
        raise


# --- public operations --------------------------------------------------------------
def create(cfg: Config, raw: dict, agent_id: str | None = None) -> A.Agent:
    """Create a new agent. Empty `agent_id`: derive it from the name (on collision -2, -3, ...)."""
    spec = parse_spec(raw)
    with _locked(cfg):
        entries = _read_entries(cfg)
        if len(entries) >= MAX_CUSTOM:
            raise A.Refused(tr("At most {n} custom agents. Delete one before you create a new one.", n=MAX_CUSTOM), 409)
        if agent_id:
            if (not A.ID_RE.match(agent_id) or agent_id.startswith(("skill-", "atlas-")) or agent_id == A.ATLAS_ID
                    or A.RESERVED_IDS.match(agent_id)):
                raise A.Refused(tr("Agent id '{id}' is invalid or reserved (a-z, 0-9, hyphen)", id=agent_id), 400)
            if agent_id in _all_ids(cfg):
                raise A.Refused(tr("Agent id '{id}' is already taken", id=agent_id), 409)
            aid = agent_id
        else:
            aid = _unique_id(cfg, slugify(spec.name))
        _commit(cfg, entries + [_entry_for(aid, spec)], aid, _prompt_text(spec))
    return next(a for a in A.load_agents(cfg.agents_file) if a.id == aid)


def update(cfg: Config, agent_id: str, raw: dict) -> A.Agent:
    """Change the fields of a custom agent. Shipped agents: Refused 403. Unknown: KeyError."""
    with _locked(cfg):
        entries = _read_entries(cfg)
        idx = next((i for i, e in enumerate(entries) if e.get("id") == agent_id), None)
        if idx is None:
            _not_custom(cfg, agent_id)
        old = _spec_of(cfg, entries[idx])
        spec = parse_spec(raw, base=old)
        entries[idx] = _entry_for(agent_id, spec, entries[idx])
        # instructions and name unchanged: the prompt file (possibly edited by hand) stays untouched
        changed = spec.instructions != old.instructions or spec.name != old.name
        _commit(cfg, entries, agent_id, _prompt_text(spec) if changed else None)
    return next(a for a in A.load_agents(cfg.agents_file) if a.id == agent_id)


def delete(cfg: Config, agent_id: str) -> None:
    """Delete a custom agent and its prompt file. Shipped: Refused 403. Unknown: KeyError. Running: 409."""
    with _locked(cfg):
        entries = _read_entries(cfg)
        if not any(e.get("id") == agent_id for e in entries):
            _not_custom(cfg, agent_id)
        if _busy(cfg, agent_id):
            raise A.Refused(tr("This agent is working on a task right now. Try again afterwards."), 409)
        _write_entries(cfg, [e for e in entries if e.get("id") != agent_id])
        try:
            _prompt_path(cfg, agent_id).unlink(missing_ok=True)
        except OSError:
            pass  # without an entry the file is harmless


def read(cfg: Config, agent_id: str) -> dict:
    """All editable fields of a custom agent (for the form). Shipped: Refused 403."""
    e = next((e for e in _read_entries(cfg) if e.get("id") == agent_id), None)
    if e is None:
        _not_custom(cfg, agent_id)
    s = _spec_of(cfg, e)
    return {"id": agent_id, "name": s.name, "description": s.description, "instructions": s.instructions, "access": s.access,
            "group": s.group, "model": s.model, "keywords": list(s.keywords), "examples": list(s.examples),
            "timeout_s": s.timeout_s, "max_runs_per_day": s.max_runs_per_day, "enabled": s.enabled}
