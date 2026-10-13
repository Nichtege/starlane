# Contributing

Thanks for looking. This is a small, opinionated project; the bar for changes is "does it keep the tool small, local
and read-only?".

## Ground rules

- **Standard library only**, Python 3.11+. No new dependencies.
- **Safety first.** Agents stay read-only, the server stays on `127.0.0.1`, nothing writes into the user's notes
  outside the digest folder. A change that loosens one of those needs a very good reason and a test.
- **Tests with every change.** `python -m unittest discover -s tests -t .` must be green. Tests use `unittest` and the
  fake vault in `tests/helpers.py`; no network, no real `claude` calls.
- **No personal data** in code, prompts, docs or fixtures: no real names, paths, e-mail addresses or private note
  titles.
- **English** for code, comments, docs and shipped prompts.

## Where things live

See [docs/architecture.md](docs/architecture.md) for the module map and how a run flows. The dashboard is one
self-contained file, `aos/web/dashboard.html` (vanilla JS, no build step); `tests/test_*` check it with string
matches and small `node` harnesses, so a node install is needed to run those.
The look (the iOS 27 language: system colours, tints, controls; rounded floating glass, the lens, its budget and fallbacks) is
described in [docs/design.md](docs/design.md); a change to it is checked in light and dark, on Home, Atlas, Second brain and a
page tab, at phone width, in all three glass steps and with a tint besides blue.

## Pull requests

Keep them small and focused, explain the *why*, and mention anything that touches the safety model
([docs/security.md](docs/security.md)) explicitly.
