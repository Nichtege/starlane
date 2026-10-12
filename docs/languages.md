# Languages

Starlane speaks English by default and ships German. One setting switches every text a person reads: the terminal, the
dashboard and the notes the system writes.

```toml
[user]
ui_language = "de"      # "en" (default) or "de"
# language = "Deutsch"  # the language agents and skills reply in; default: follows ui_language
```

`AOS_UI_LANGUAGE=de` overrides it for one shell, `AOS_LANGUAGE` does the same for the reply language. Codes are
forgiving (`de`, `DE`, `de-DE`, `de_AT` all mean German); an unknown one is an error that lists the available codes.
`python -m aos doctor` shows the current choice in the line "Interface language".

German guides live in [docs/de/](de/README.md). With `ui_language = "de"` the onboarding (`aos next`) points to them.

## What follows the setting

| Part | Translated |
|---|---|
| Terminal | help, `doctor`, `status`, `next` with its prompts for Claude Code, every message and error |
| Generated notes | the digest, `vault-check.md`, the starter notes of `aos init` |
| Dashboard | every label, button, hint and empty state; dates, numbers and amounts in the local format (`1.234`, `0,00 $`, `Di 6.10.`) |
| Agents and skills | the reply language (`[user] language`), unless you set it yourself |

## What stays as written

- **Your notes and everything from them**: titles, folder names, tags, the text of tasks and deadlines.
- **Your vault's structure**: folder names, frontmatter keys and headings are [conventions](vault-conventions.md), set
  once in `[conventions]`, independent of the interface language. A German vault with an English interface works, and
  the other way round.
- **Text you or the catalogs own**: names, descriptions and prompts of agents (`agents.toml`), skills (`SKILL.md`) and
  routines (`routines.toml`). The shipped ones are English; edit them, or add your own in any language.
- **What is not meant for reading**: ids, commands, keys in `aos.toml`, log fields, file formats, `data/` contents and
  the rules Starlane adds to every Claude prompt (the model gets them in English and replies in your language).
- **File names in the digest folder** stay `latest.md`, `archive/` and `weekly-review.md` until you rename them with
  `[digest] file`, `archive` and `review`; changing the language never moves a file.

Dates in notes are understood in both languages whatever you choose: `Tue 6.10.` and `Di 6.10.`, `Dienstag, 6.10.`
(see [vault-conventions.md](vault-conventions.md#dates-in-notes)).

## Adding a language

A language is one file, `aos/locales/<code>.json`. Every file there is offered automatically.

1. Copy `aos/locales/de.json` to `aos/locales/<code>.json` (for example `fr.json`).
2. Set the header: `"lang": "fr"`, `"name": "Français"` (shown by `doctor`), `"locale": "fr-FR"` (BCP 47, used by the
   dashboard to format numbers and amounts) and `"reply_language": "Français"` (the default reply language of the
   agents).
3. Translate every value in `"py"` (terminal and notes) and `"web"` (dashboard). The keys are the English source texts;
   leave them as they are.
4. Run `python -m unittest tests.test_i18n`. It collects every marked text from the code and the dashboard and checks
   your file against it: nothing missing, nothing stale, and each translation passes the rules below.

The rules the tests enforce:

- `{placeholders}` stay, with the same names (their order may change).
- `` `code spans` `` (commands, keys, file names) stay verbatim; only a quoted example inside one may be translated
  (`` `python -m aos agent research "..."` ``).
- A text that ends with a line break keeps it.
- A key that starts with `@` has a **context**: `@routine failed` and `@job failed` are the same English word in two
  places (a routine status, a job status), translated separately because another language may need two forms.
  Translate the part after the context.
- **Plurals** are two keys, one for exactly 1 and one for everything else (`{n} warning`, `{n} warnings`).
- **Date patterns** (`@date ...`) may use any of `{wd}` (weekday), `{d}` (day), `{m}` (month number), `{mon}` (month
  name) and `{y}` (year), in the order your language writes dates. German writes `{wd} {d}.{m}.`.

Weekday and month names are ordinary entries (`Monday`, `Mon`, `Jan`, ...). The date *parser* for notes is separate
code (`aos/dates.py`); to read dates written in your language, add its weekday names there.

## For developers

Every text a person reads goes through one of these, with a literal string (no f-strings: placeholders are filled after
translating):

| Where | Mark |
|---|---|
| Python (`aos/*.py`) | `tr("Vault check: {n} errors", n=3)`, `trn(n, "{n} item", "{n} items")`, `trc("severity", "Notes")`, `tr_mark("Monday")` for tables translated where they are shown |
| Dashboard script | `tr('...')`, `trn(n, '...', '...')`, `trc('ctx', '...')`, `trm('...')` (the same four, in JavaScript) |
| Dashboard HTML | `{{t:Text}}`, replaced and HTML-escaped by the server when it renders the page |

The dashboard receives its strings as JSON in a `<script type="application/json">` block; without one (or with a broken
one) it falls back to English. `tests/test_i18n.py` finds new marked texts on its own and fails until every locale has
them, so a new feature cannot ship half translated. Rules for the wording of German texts: "du", German quotes „…“, and
the terms already in `de.json` (Frist, Zweites Gehirn, Auftrag, Aufwand).
