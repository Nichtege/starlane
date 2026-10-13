"""Web guard: a Claude Code hook around the web calls of agents that read the vault and the web (`mixed = true`).

RULES_MIXED asks the model to keep note text out of search queries and URLs; this enforces it outside the model,
where a prepared web page cannot talk it away. claude_command() installs it with --settings for mixed agents only.
- PreToolUse (WebSearch, WebFetch): a query or URL that carries note text is blocked. Note text means WINDOW
  consecutive words of a note, a long number or code from a note (phone, IBAN, ID) or a secret pattern, also after URL
  decoding and inside base64 or hex chunks. The block goes back to Claude as a reason; the run goes on.
- PostToolUse: remembers the URLs in search results and fetched pages. A URL from a result, a page, a note or the
  user's own message is opened unchecked, so following links never trips the guard.
- Whatever the user typed for this run is theirs to send: it never counts as note text.

Runs as `python -I webguard.py pre|post` (stdin: the hook JSON) with AOS_GUARD_VAULT, AOS_GUARD_IGNORE (JSON list of
folder names), AOS_GUARD_STATE (file prefix of this run) and AOS_GUARD_ALLOW (the user's message). Fails closed.
Limit: it catches note text, not a paraphrase of it; the prompt rule stays the first line of defence.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote_plus

if __package__ in (None, ""):  # started as a script with -I: the folder that holds the package is not on sys.path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aos.mapcheck import redact  # noqa: E402

WINDOW = 8  # this many consecutive words of a note count as note text (fewer would catch everyday phrases)
MIN_WINDOW_CHARS = 32  # ... if they are not just short tokens
MIN_DIGITS = 9  # a number this long from a note (phone, IBAN, account) counts in any spacing; a date has 8
TEXT_EXTS = {".md", ".markdown", ".txt", ".canvas", ".csv", ".json", ".base", ".yaml", ".yml"}
MAX_FILE = 2_000_000
URL_RE = re.compile(r"https?://[^\s<>\"'`(){}\[\]|\\^]+", re.I)
CHUNK_RE = re.compile(r"[A-Za-z0-9+/_\-]{16,}={0,2}")
_NONWORD = re.compile(r"[\W_]+")
_NUM_RE = re.compile(r"\d[\d ]*\d")  # on normalised text: "+49 151 1234-5678" and "4915112345678" both become digits


def norm(text: str) -> str:
    """Words only, case-folded, single spaces: the same text matches however it is punctuated or encoded in a URL."""
    return " ".join(_NONWORD.sub(" ", unicodedata.normalize("NFKC", text).casefold()).split())


def url_key(url: str) -> str:
    u = url.strip().rstrip(".,;:!?)'\"").split("#", 1)[0].rstrip("/")
    scheme, sep, rest = u.partition("://")
    host, slash, path = rest.partition("/")
    return f"{scheme.lower()}{sep}{host.lower()}{slash}{path}"


def numbers(normed: str) -> list[str]:
    return [d for d in (m.replace(" ", "") for m in _NUM_RE.findall(normed)) if len(d) >= MIN_DIGITS]


def build_corpus(vault: Path, ignore: set[str]) -> tuple[str, set[str]]:
    """All note text the agent can read, normalised (one line per file, URLs left out: a link is not a secret, and an
    article slug must not match the clipped title; last a line "#<the notes' long numbers>"), plus the notes' URLs."""
    lines, urls = [], set()
    for dirpath, dirs, files in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in ignore]
        for name in files:
            p = Path(dirpath, name)
            if p.suffix.lower() not in TEXT_EXTS:
                continue
            try:
                if p.stat().st_size > MAX_FILE:
                    continue
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            urls.update(url_key(u) for u in URL_RE.findall(text))
            lines.append(" " + norm(URL_RE.sub(" ", text)) + " ")
    nums = " ".join(n for line in lines for n in numbers(line))
    return "\n".join(lines) + "\n#" + nums, urls


def _decode(chunk: str) -> str:
    """Readable text hidden in a hex or base64 chunk, else ''."""
    try:
        if len(chunk) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", chunk):
            raw = bytes.fromhex(chunk)
        else:
            c = chunk.replace("-", "+").replace("_", "/").rstrip("=")
            raw = base64.b64decode(c + "=" * (-len(c) % 4), validate=True)
        text = raw.decode("utf-8")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return ""
    return text if sum(ch.isprintable() for ch in text) >= 0.9 * len(text) else ""


def _variants(payload: str) -> list[str]:
    out = [payload, unquote_plus(payload)]
    out.append(unquote_plus(out[-1]))  # encoded twice
    for chunk in set(CHUNK_RE.findall(payload) + CHUNK_RE.findall(out[-1])):
        if dec := _decode(chunk):
            out.append(dec)
    return out


def check(payload: str, corpus: str, allow: str = "") -> str:
    """Why `payload` (a URL or a search query) would carry note text out, or '' if it does not.
    corpus: from build_corpus. allow: the user's own words for this run (they may send what they typed)."""
    allow = " " + norm(allow) + " "
    for text in _variants(payload):
        if redact(text) != text:
            return "something that looks like a password, token or key"
        words = norm(text).split()
        for i in range(len(words) - WINDOW + 1):
            w = " " + " ".join(words[i:i + WINDOW]) + " "
            if len(w) >= MIN_WINDOW_CHARS and w in corpus and w not in allow:
                return "text from the notes"
        for t in words:  # a code with digits, e.g. a customer or policy number
            if len(t) >= 8 and sum(ch.isdigit() for ch in t) >= 5 and f" {t} " in corpus and f" {t} " not in allow:
                return "a number from the notes"
        noted = corpus[corpus.rfind("\n#") + 2:]
        for n in numbers(" ".join(words)):
            if n in noted and n not in allow.replace(" ", ""):
                return "a number from the notes"
    return ""


def _corpus(state: str) -> tuple[str, set[str]]:
    """Built once per run (on the first web call) and cached next to the run's other guard files."""
    cache = Path(state + ".corpus.json")
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        return data["text"], set(data["urls"])
    except (OSError, ValueError, KeyError):
        pass
    text, urls = build_corpus(Path(os.environ["AOS_GUARD_VAULT"]), set(json.loads(os.environ.get("AOS_GUARD_IGNORE", "[]"))))
    tmp = cache.with_name(cache.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"text": text, "urls": sorted(urls)}), encoding="utf-8")
    os.replace(tmp, cache)
    return text, urls


def _seen(state: str) -> set[str]:
    try:
        return set(Path(state + ".seen").read_text(encoding="utf-8").split())
    except OSError:
        return set()


def main(stage: str) -> int:
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    state = os.environ["AOS_GUARD_STATE"]
    tool, given = data.get("tool_name"), data.get("tool_input") or {}
    if stage == "post":
        found = URL_RE.findall(json.dumps(data.get("tool_response"), ensure_ascii=False))
        with open(state + ".seen", "a", encoding="utf-8") as fh:
            fh.write("".join(url_key(u) + "\n" for u in found))
        return 0
    allow = os.environ.get("AOS_GUARD_ALLOW", "")
    payload = str(given.get("url") if tool == "WebFetch" else given.get("query") or "")
    corpus, note_urls = _corpus(state)
    if tool == "WebFetch" and url_key(payload) in note_urls | _seen(state) | {url_key(u) for u in URL_RE.findall(allow)}:
        return 0
    why = check(payload, corpus, allow)
    if not why:
        return 0
    with open(state + ".blocked", "a", encoding="utf-8") as fh:
        fh.write(f"{tool}\n")
    kind = "URL" if tool == "WebFetch" else "search query"
    print(f"Blocked by Starlane's web guard: this {kind} would send {why} to the web, and nothing from the notes may "
          "leave this computer. Use general terms only, or answer from what you already have.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        sys.exit(main(stage))
    except Exception as exc:  # noqa: BLE001 - fail closed: an unchecked call must not go out
        if stage == "post":
            sys.exit(0)  # remembering URLs is a convenience; a later fetch is still checked
        print(f"Starlane's web guard could not check this call ({type(exc).__name__}), so it was blocked.", file=sys.stderr)
        sys.exit(2)
