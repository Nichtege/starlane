"""Configuration from aos.toml (or AOS_CONFIG). Everything path-like is resolved here."""

from __future__ import annotations

import os
import socket
import tomllib
from dataclasses import dataclass, fields, replace
from datetime import date
from pathlib import Path, PureWindowsPath

from .i18n import normalize as normalize_language
from .i18n import reply_language, tr

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Installed mode: a wheel or sdist install carries the starter files in aos/_shipped (built by setup.py) and there is no
# aos.toml next to the package. Never true in a checkout or an editable install. Then the user's own folder ($AOS_HOME,
# default ~/starlane; made by `aos setup`) plays the role of the project root.
SHIPPED_DIR = Path(__file__).resolve().parent / "_shipped"


def _is_installed(shipped: Path, root: Path) -> bool:
    return shipped.is_dir() and not (root / "aos.toml").is_file()


INSTALLED = _is_installed(SHIPPED_DIR, PROJECT_ROOT)


def home_dir() -> Path:
    """The user's folder in installed mode: aos.toml, routines.toml, agents, skills and data live here."""
    return Path(os.path.expanduser(os.environ.get("AOS_HOME") or "~/starlane")).resolve()


def default_root() -> Path:
    return home_dir() if INSTALLED else PROJECT_ROOT


def home_is_checkout() -> bool:
    """Installed mode, $AOS_HOME not set, and ~/starlane is itself a copy of the code (it holds the `aos` package).

    That is somebody's working project, not a folder `aos setup` made: do not adopt it silently (digests, routines and the
    state file in it would be rewritten by this install's code). Naming the folder (AOS_HOME, --config, a folder argument) is fine."""
    return INSTALLED and not os.environ.get("AOS_HOME") and (home_dir() / "aos" / "__init__.py").is_file()


def aos_cmd(text: str) -> str:
    """A command as the user should type it: `aos ...` after `pip install`, `python -m aos ...` in a checkout (no `aos` on the PATH there)."""
    return text.replace("python3 -m aos", "aos").replace("python -m aos", "aos") if INSTALLED else text

DEFAULT_IGNORE = (".git", ".obsidian", ".claude", ".trash", "node_modules")


@dataclass(frozen=True)
class Conventions:
    """How the vault is organised. Every field can be overridden in `[conventions]` (see docs/vault-conventions.md)."""

    # frontmatter keys
    type_key: str = "type"
    created_key: str = "created"
    status_key: str = "status"
    deadline_key: str = "deadline"
    tags_key: str = "tags"
    project_key: str = "project"
    projects_key: str = "projects"
    area_key: str = "area"
    # values of the type key
    type_project: str = "project"
    type_idea: str = "idea"
    type_week: str = "week"
    type_plan: str = "plan"
    type_knowledge: str = "knowledge"
    type_session: str = "session"
    type_overview: str = "overview"
    type_index: str = "index"
    type_digest: str = "digest"
    # status vocabularies
    project_status: tuple[str, ...] = ("idea", "new", "building", "active", "paused", "done")
    status_done: str = "done"
    idea_status: tuple[str, ...] = ("raw", "in-progress", "project", "dropped")
    # headings and phrases inside notes
    week_goal_heading: str = "Weekly goal"
    weekly_review_heading: str = "Weekly review"
    ideas_quick_heading: str = "Quick"
    belongs_to: str = "Part of"
    log_words: tuple[str, ...] = ("status", "done", "log", "history", "result", "learned", "went wrong", "notes", "archive")
    # folders and notes
    projects_dir: str = "Projects"
    areas_dir: str = "Areas"
    resources_dir: str = "Resources"
    journal_dir: str = "Journal"
    inbox_dir: str = "Inbox"
    ideas_dir: str = "Ideas"
    archive_dir: str = "Archive"
    templates_dir: str = "Resources/Templates"
    ai_dir: str = "AI"
    sessions_dir: str = "AI/Sessions"
    week_template: str = "Resources/Templates/week"
    schedule_keyword: str = "schedule"
    index_note: str = "index.md"
    brain_map: str = "AI/brain-map.md"
    project_note: str = ""  # optional: note the generated files link to, e.g. "Projects/my-project"
    # set from [digest], not from [conventions]
    digest_dir: str = "AI/Digest"
    digest_file: str = "latest.md"  # the current digest inside digest_dir
    digest_archive: str = "archive"  # one dated copy per day, inside digest_dir
    review_file: str = "weekly-review.md"  # `aos claude-digest`, inside digest_dir

    @property
    def roots(self) -> tuple[str, str]:
        return (self.index_note, self.brain_map)

    def week_note(self, d: date) -> str:
        from .dates import iso_week_name

        return f"{self.journal_dir}/{iso_week_name(d)}.md"

    def is_template(self, rel: str) -> bool:
        return rel.startswith(self.templates_dir + "/")

    def is_generated(self, rel: str) -> bool:
        """Written by the system itself: the vault check skips it, otherwise it would grade its own output."""
        return rel.startswith(self.digest_dir + "/")


FROM_DIGEST = {"digest_dir": "dir", "digest_file": "file", "digest_archive": "archive", "review_file": "review"}  # field -> [digest] key


def _file_name(value, name: str, suffix: str = "") -> str:
    """One plain file or folder name inside the digest folder: no path separators, no '..', no drive."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("{name} must be a non-empty name", name=name))
    text = value.strip()
    if any(ch in text for ch in '/\\:*?"<>|') or text in (".", "..") or text.startswith("."):
        raise ValueError(tr("{name} must be a plain name without folders: {value}", name=name, value=repr(value)))
    if suffix and not text.endswith(suffix):
        raise ValueError(tr("{name} must end in {suffix}: {value}", name=name, suffix=suffix, value=repr(value)))
    return text


def _digest_files(digest: dict) -> dict:
    return {
        "digest_file": _file_name(digest.get("file", "latest.md"), "digest.file", ".md"),
        "digest_archive": _file_name(digest.get("archive", "archive"), "digest.archive"),
        "review_file": _file_name(digest.get("review", "weekly-review.md"), "digest.review", ".md"),
    }


def _conventions(raw: dict, digest_dir: str, files: dict | None = None) -> Conventions:
    if not isinstance(raw, dict):
        raise ValueError(tr("[conventions] must be a table"))
    known = {f.name: f for f in fields(Conventions)}
    values: dict = {}
    for key, value in raw.items():
        f = known.get(key)
        if f is None or key in FROM_DIGEST:
            hint = " " + tr("(set it with [digest] {key})", key=FROM_DIGEST[key]) if key in FROM_DIGEST else ""
            raise ValueError(tr("conventions.{key} is not a known convention", key=key) + hint)
        if isinstance(f.default, tuple):
            if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
                raise ValueError(tr("{name} must be a list of non-empty strings", name=f"conventions.{key}"))
            values[key] = tuple(v.strip() for v in value)
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(tr("{name} must be a non-empty string", name=f"conventions.{key}"))
            value = value.strip()
            if key.endswith("_dir"):
                value = _safe_rel_dir(value.strip("/"), f"conventions.{key}")
            elif key in ("index_note", "brain_map") and not value.endswith(".md"):
                raise ValueError(tr("conventions.{key} must be a note path ending in .md: {value}", key=key, value=repr(value)))
            elif key in ("project_note", "week_template") and value.endswith(".md"):
                value = value[: -len(".md")]  # both are link targets, written without the extension
            values[key] = value
    return replace(Conventions(), **values, digest_dir=digest_dir, **(files or {}))


@dataclass(frozen=True)
class Config:
    project_root: Path
    vault: Path
    vault_name: str
    ignore: tuple[str, ...]
    data_dir: Path
    machine: str
    digest_dir: str
    digest_keep_days: int
    horizon_days: int
    large_file_kb: int
    server_host: str
    server_port: int
    routines_file: Path
    config_file: Path | None = None
    local_file: Path | None = None  # aos.local.toml next to config_file, merged over it (see read_settings)
    agents_file: Path = PROJECT_ROOT / "agents.toml"
    skills_dirs: tuple[Path, ...] = (PROJECT_ROOT / "skills",)  # first hit per skill id wins
    skills_cap: int = 10  # runs per skill and day
    skills_timeout_s: int = 600
    user_name: str = "the user"  # how agents address and refer to the human
    language: str = "English"  # language the agents reply in
    ui_language: str = "en"  # language of the terminal, the dashboard and the generated notes (aos/i18n.py)
    conv: Conventions = Conventions()

    @property
    def out_dir(self) -> Path:
        return self.data_dir / "out"

    @property
    def runs_log(self) -> Path:
        return self.data_dir / "runs.jsonl"

    @property
    def state_file(self) -> Path:
        return self.data_dir / "state.json"

    @property
    def jobs_log(self) -> Path:
        return self.data_dir / "agents" / "jobs.jsonl"

    @property
    def spend_log(self) -> Path:
        return self.data_dir / "agents" / "spend.jsonl"

    @property
    def lock_file(self) -> Path:
        return self.data_dir / "tick.lock"


def _safe_rel_dir(value: str, name: str = "digest.dir") -> str:
    """Folders live inside the vault: absolute paths, drives and '..' would let the system write outside of it."""
    p = Path(str(value))
    win = PureWindowsPath(str(value))  # also on Linux: "C:x" and "\\server" must not pass in a shared aos.toml
    if p.is_absolute() or p.anchor or win.drive or win.anchor or ".." in win.parts or not p.parts:
        raise ValueError(tr("{name} must be a relative folder inside the vault (no drive, no '..'): {value}", name=name, value=repr(value)))
    return p.as_posix()


def _resolve(base: Path, value: str) -> Path:
    p = Path(os.path.expanduser(value))
    return p if p.is_absolute() else (base / p).resolve()


MAX_USER_TEXT = 40


def _text(value, name: str) -> str:
    """One short line: the value goes into every agent's system rules, so no line breaks and no essays."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr("{name} must be a non-empty string", name=name))
    return " ".join(value.split())[:MAX_USER_TEXT].rstrip()


def _whole(table: dict, key: str, default: int, name: str, lo: int | None = None, hi: int | None = None) -> int:
    """A whole-number setting, optionally within bounds: a typo becomes a readable error, not a surprise
    (a negative digest.keep_days used to delete today's archive)."""
    value = table.get(key, default)
    try:
        if isinstance(value, bool):
            raise ValueError
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(tr("{name} must be a whole number, not {value}", name=name, value=repr(value))) from None
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        if hi is not None:
            raise ValueError(tr("{name} must be between {lo} and {hi}, not {value}", name=name, lo=lo, hi=hi, value=value))
        raise ValueError(tr("{name} must be at least {lo}, not {value}", name=name, lo=lo, value=value))
    return value


def _ignore(value) -> tuple[str, ...]:
    if isinstance(value, str):
        value = [value]  # `ignore = ".git"` means that one folder, not the letters . g i t
    if not isinstance(value, (list, tuple)) or not all(isinstance(d, str) and d.strip() for d in value):
        raise ValueError(tr('vault.ignore must be a list of folder names, e.g. [".git", ".obsidian"]'))
    return tuple(d.strip() for d in value)


def config_path(path: str | os.PathLike | None = None) -> Path:
    """The aos.toml a command reads: --config, else $AOS_CONFIG, else the one in the default folder."""
    given = path or os.environ.get("AOS_CONFIG")
    return Path(os.path.expanduser(given)) if given else default_root() / "aos.toml"   # cmd and PowerShell pass "~" through


LOCAL_OVERRIDES = True  # tests/__init__.py switches it off: the tests check the shipped files, never a developer's own


def local_path(cfg_path: Path) -> Path:
    """aos.toml -> aos.local.toml next to it (the same rule as agents.toml -> agents.local.toml)."""
    return cfg_path.with_name(cfg_path.stem + ".local.toml")


def _merge(base: dict, over: dict) -> dict:
    """`over` wins key by key; tables are merged, everything else (lists too) is replaced."""
    out = dict(base)
    for key, value in over.items():
        out[key] = _merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def _read_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        try:
            return tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(tr("{path}: {error}. A Windows path is written with / (\"C:/Users/me/notes\") "
                                "or in single quotes ('C:\\Users\\me\\notes').", path=path, error=exc)) from None


def read_settings(cfg_path: Path) -> tuple[dict, Path | None]:
    """The settings of aos.toml with your own aos.local.toml next to it merged over them, and that file if it exists.
    The shipped aos.toml stays as it is (an update never collides with your settings); aos.local.toml holds only what
    you change. It follows the file, not how it was named, so --config, $AOS_CONFIG and the scheduler's child runs
    all see the same settings."""
    raw = _read_toml(cfg_path) if cfg_path.is_file() else {}
    local = local_path(cfg_path)
    if LOCAL_OVERRIDES and local.is_file():
        return _merge(raw, _read_toml(local)), local
    return raw, None


def peek_ui_language(path: str | os.PathLike | None = None) -> str:
    """Only `[user] ui_language` (or $AOS_UI_LANGUAGE), without checking anything else: the CLI needs the language
    before it builds its help texts and before load_config reports an error in that language. "en" if unreadable."""
    try:
        code = os.environ.get("AOS_UI_LANGUAGE") or read_settings(config_path(path))[0].get("user", {}).get("ui_language", "en")
        return normalize_language(code)
    except (OSError, ValueError, AttributeError):  # TOMLDecodeError is a ValueError
        return "en"


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg_path = config_path(path)
    raw, local = read_settings(cfg_path)
    base = cfg_path.parent if cfg_path.is_file() or local else default_root()

    vault_raw = os.environ.get("AOS_VAULT") or raw.get("vault", {}).get("path") or "~/notes"
    vault = _resolve(base, vault_raw)
    ignore = _ignore(raw.get("vault", {}).get("ignore", DEFAULT_IGNORE))
    data_raw = os.environ.get("AOS_DATA") or raw.get("paths", {}).get("data", "data")
    machine = os.environ.get("AOS_MACHINE") or raw.get("machine", {}).get("name") or socket.gethostname()
    digest = raw.get("digest", {})
    server = raw.get("server", {})
    skills = raw.get("skills", {})
    user = raw.get("user", {})
    dirs = skills.get("dirs", ["skills", "~/.claude/skills"])
    if not isinstance(dirs, list) or not all(isinstance(d, str) for d in dirs):
        raise ValueError(tr("skills.dirs must be a list of folders"))
    digest_dir = _safe_rel_dir(digest.get("dir", "AI/Digest"))
    ui_language = normalize_language(os.environ.get("AOS_UI_LANGUAGE") or user.get("ui_language", "en"))
    return Config(
        project_root=base,
        vault=vault,
        vault_name=raw.get("vault", {}).get("name") or vault.name,
        ignore=ignore,
        data_dir=_resolve(base, data_raw),
        machine=machine,
        digest_dir=digest_dir,
        digest_keep_days=_whole(digest, "keep_days", 14, "digest.keep_days", lo=0),
        horizon_days=_whole(digest, "horizon_days", 14, "digest.horizon_days", lo=0),
        large_file_kb=_whole(raw.get("vault", {}), "large_file_kb", 50, "vault.large_file_kb", lo=1),
        server_host="127.0.0.1",  # deliberately not configurable: local only
        server_port=_whole(server, "port", 8765, "server.port", lo=1, hi=65535),
        routines_file=_resolve(base, raw.get("paths", {}).get("routines", "routines.toml")),
        config_file=cfg_path if cfg_path.is_file() else None,
        local_file=local,
        agents_file=_resolve(base, raw.get("paths", {}).get("agents", "agents.toml")),
        skills_dirs=tuple(dict.fromkeys(_resolve(base, d) for d in dirs)),
        skills_cap=max(1, _whole(skills, "max_runs_per_day", 10, "skills.max_runs_per_day")),
        skills_timeout_s=max(30, min(_whole(skills, "timeout_s", 600, "skills.timeout_s"), 900)),
        user_name=_text(os.environ.get("AOS_USER") or user.get("name", "the user"), "user.name"),
        # the agents reply in the interface language unless [user] language names another one
        language=_text(os.environ.get("AOS_LANGUAGE") or (user["language"] if "language" in user else reply_language(ui_language)), "user.language"),
        ui_language=ui_language,
        conv=_conventions(raw.get("conventions", {}), digest_dir, _digest_files(digest)),
    )
