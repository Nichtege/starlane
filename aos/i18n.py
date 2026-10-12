"""Interface language: every text a person reads (terminal, dashboard, generated notes) goes through `tr`.

English is the source language and stays in the code; a locale file (aos/locales/<code>.json) maps each English text to
its translation. A missing entry falls back to English, so an incomplete locale never breaks anything (the tests make
sure the shipped ones are complete).

    tr("Vault check: {n} errors", n=3)        placeholders in {braces}, filled in after translating
    trn(n, "{n} item", "{n} items")           one form for n == 1, the other for everything else (English and German)
    trc("severity", "Notes")                  a context, when one English word needs two translations
    tr_mark("Monday")                          marks a literal that is translated later, where it is shown (tr(name))

Not translated on purpose: prompts sent to Claude (the reply language is `[user] language`), log keys, status codes,
ids, file formats. The dashboard uses the same catalog through its "web" section (see dashboard.render_html).

Locale file: {"lang", "name", "locale" (BCP 47, for number formats in the browser), "reply_language", "py": {...},
"web": {...}}. A context key is written "@<context> <English text>".
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent / "locales"
SOURCE = "en"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_ENGLISH = {"lang": SOURCE, "name": "English", "locale": "en-US", "reply_language": "English", "py": {}, "web": {}}

_current = SOURCE


def available() -> tuple[str, ...]:
    """Language codes that can be chosen: English plus every locale file."""
    return (SOURCE, *sorted(p.stem for p in LOCALE_DIR.glob("*.json")))


def normalize(code) -> str:
    """'de', 'DE', 'de-DE', 'de_AT' -> 'de'. Raises ValueError for anything that is not an available language."""
    text = str(code or "").strip().lower().replace("_", "-").split("-")[0]
    if text not in available():
        raise ValueError(f"ui_language must be one of {', '.join(available())}, not {code!r}")
    return text


@lru_cache(maxsize=None)
def catalog(lang: str) -> dict:
    """The whole locale (English: empty maps). Read once per process."""
    if lang == SOURCE:
        return _ENGLISH
    data = json.loads((LOCALE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    for section in ("py", "web"):
        if not isinstance(data.get(section), dict):
            raise ValueError(f"locale {lang}: section {section!r} missing")
    return data


def use(lang: str) -> None:
    """Switch the language of this process (the CLI does it once, right after reading aos.toml)."""
    global _current
    _current = normalize(lang)


def current() -> str:
    return _current


def fill(text: str, values: dict) -> str:
    """Replace {name} with values[name]; unknown names stay as they are (a translation can never raise)."""
    if not values:
        return text
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def placeholders(text: str) -> set[str]:
    return set(_PLACEHOLDER.findall(text))


def tr(msg: str, **values) -> str:
    return fill(catalog(_current)["py"].get(msg, msg), values)


def trc(context: str, msg: str, **values) -> str:
    return fill(catalog(_current)["py"].get(f"@{context} {msg}", msg), values)


def trn(n: int, one: str, other: str, **values) -> str:
    return tr(one if n == 1 else other, n=n, **values)


def tr_mark(msg: str, context: str = "") -> str:
    """Returns `msg` unchanged. It only marks the literal for the catalog (the tests collect every marked text), for
    tables of names that are translated where they are shown: `tr(WEEKDAYS[i])`, `trc("routine", status)`."""
    return msg


def web_catalog(lang: str | None = None) -> dict:
    """What the dashboard gets: its strings plus the locale for number formats."""
    cat = catalog(lang or _current)
    return {"lang": cat["lang"], "locale": cat.get("locale", "en-US"), "strings": cat["web"]}


def reply_language(lang: str | None = None) -> str:
    """The default for `[user] language`: the language the agents reply in when aos.toml does not name one."""
    return catalog(lang or _current).get("reply_language", "English")
