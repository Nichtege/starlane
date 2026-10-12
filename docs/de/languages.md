# Sprachen

Starlane spricht standardmäßig Englisch und bringt Deutsch mit. Eine Einstellung schaltet jeden Text um, den ein Mensch
liest: das Terminal, das Dashboard und die Notizen, die das System schreibt.

```toml
[user]
ui_language = "de"      # "en" (Standard) oder "de"
# language = "Deutsch"  # die Sprache, in der Agenten und Skills antworten; Standard: folgt ui_language
```

`AOS_UI_LANGUAGE=de` überschreibt das für eine Shell, `AOS_LANGUAGE` dasselbe für die Antwortsprache. Die Codes sind
nachsichtig (`de`, `DE`, `de-DE`, `de_AT` heißen alle Deutsch); ein unbekannter Code ist ein Fehler, der die verfügbaren
aufzählt. `python -m aos doctor` zeigt die aktuelle Wahl in der Zeile „Sprache der Oberfläche“.

Die deutschen Anleitungen liegen in [docs/de/](README.md). Mit `ui_language = "de"` verweist das Onboarding
(`aos next`) auf sie.

## Was der Einstellung folgt

| Teil | Übersetzt |
|---|---|
| Terminal | Hilfe, `doctor`, `status`, `next` mit seinen Prompts für Claude Code, jede Meldung und jeder Fehler |
| Erzeugte Notizen | der Digest, `vault-check.md`, die Start-Notizen von `aos init` |
| Dashboard | jede Beschriftung, jeder Knopf, Hinweis und leere Zustand; Datum, Zahlen und Beträge im örtlichen Format (`1.234`, `0,00 $`, `Di 6.10.`) |
| Agenten und Skills | die Antwortsprache (`[user] language`), außer du setzt sie selbst |

## Was bleibt, wie es geschrieben ist

- **Deine Notizen und alles daraus**: Titel, Ordnernamen, Tags, der Text von Aufgaben und Fristen.
- **Die Struktur deines Vaults**: Ordnernamen, Frontmatter-Schlüssel und Überschriften sind
  [Konventionen](vault-conventions.md), einmal in `[conventions]` gesetzt, unabhängig von der Oberflächensprache. Ein
  deutscher Vault mit englischer Oberfläche funktioniert, und umgekehrt.
- **Text, der dir oder den Katalogen gehört**: Namen, Beschreibungen und Prompts von Agenten (`agents.toml`), Skills
  (`SKILL.md`) und Routinen (`routines.toml`). Die mitgelieferten sind englisch; bearbeite sie oder leg eigene in
  jeder Sprache an.
- **Was nicht zum Lesen gedacht ist**: IDs, Befehle, Schlüssel in `aos.toml`, Log-Felder, Dateiformate, der Inhalt von
  `data/` und die Regeln, die Starlane jedem Claude-Prompt anhängt (das Modell bekommt sie auf Englisch und antwortet in
  deiner Sprache).
- **Dateinamen im Digest-Ordner** bleiben `latest.md`, `archive/` und `weekly-review.md`, bis du sie mit
  `[digest] file`, `archive` und `review` umbenennst; ein Sprachwechsel verschiebt nie eine Datei.

Daten in Notizen werden unabhängig von deiner Wahl in beiden Sprachen verstanden: `Di 6.10.`, `Dienstag, 6.10.` und
`Tue 6.10.` (siehe [vault-conventions.md](vault-conventions.md#daten-in-notizen)).

## Eine Sprache hinzufügen

Eine Sprache ist eine Datei, `aos/locales/<code>.json`. Jede Datei dort wird automatisch angeboten.

1. Kopier `aos/locales/de.json` nach `aos/locales/<code>.json` (zum Beispiel `fr.json`).
2. Setz den Kopf: `"lang": "fr"`, `"name": "Français"` (zeigt `doctor`), `"locale": "fr-FR"` (BCP 47, damit formatiert
   das Dashboard Zahlen und Beträge) und `"reply_language": "Français"` (die Standard-Antwortsprache der Agenten).
3. Übersetz jeden Wert in `"py"` (Terminal und Notizen) und `"web"` (Dashboard). Die Schlüssel sind die englischen
   Ausgangstexte; lass sie, wie sie sind.
4. Führ `python -m unittest tests.test_i18n` aus. Es sammelt jeden markierten Text aus Code und Dashboard und prüft deine
   Datei dagegen: nichts fehlt, nichts ist veraltet, und jede Übersetzung erfüllt die Regeln unten.

Die Regeln, die die Tests durchsetzen:

- `{Platzhalter}` bleiben, mit denselben Namen (die Reihenfolge darf sich ändern).
- `` `Code-Spannen` `` (Befehle, Schlüssel, Dateinamen) bleiben wörtlich; nur ein Beispiel in Anführungszeichen darin darf
  übersetzt werden (`` `python -m aos agent research "..."` ``).
- Ein Text, der mit einem Zeilenumbruch endet, behält ihn.
- Ein Schlüssel, der mit `@` beginnt, hat einen **Kontext**: `@routine failed` und `@job failed` sind dasselbe englische
  Wort an zwei Stellen (Status einer Routine, Status eines Auftrags), getrennt übersetzt, weil eine andere Sprache zwei
  Formen brauchen kann. Übersetz den Teil nach dem Kontext.
- **Mehrzahl** sind zwei Schlüssel, einer für genau 1 und einer für alles andere (`{n} warning`, `{n} warnings`).
- **Datumsmuster** (`@date ...`) dürfen `{wd}` (Wochentag), `{d}` (Tag), `{m}` (Monatszahl), `{mon}` (Monatsname) und
  `{y}` (Jahr) nutzen, in der Reihenfolge, in der deine Sprache Daten schreibt. Deutsch schreibt `{wd} {d}.{m}.`.

Wochentags- und Monatsnamen sind gewöhnliche Einträge (`Monday`, `Mon`, `Jan`, ...). Der Datums-*Parser* für Notizen ist
eigener Code (`aos/dates.py`); damit er Daten in deiner Sprache liest, trag dort ihre Wochentagsnamen ein.

## Für Entwickler

Jeder Text, den ein Mensch liest, läuft durch eine dieser Markierungen, mit einem festen String (keine f-Strings:
Platzhalter werden nach dem Übersetzen gefüllt):

| Wo | Markierung |
|---|---|
| Python (`aos/*.py`) | `tr("Vault check: {n} errors", n=3)`, `trn(n, "{n} item", "{n} items")`, `trc("severity", "Notes")`, `tr_mark("Monday")` für Tabellen, die dort übersetzt werden, wo sie erscheinen |
| Dashboard-Skript | `tr('...')`, `trn(n, '...', '...')`, `trc('ctx', '...')`, `trm('...')` (dieselben vier, in JavaScript) |
| Dashboard-HTML | `{{t:Text}}`, vom Server beim Ausliefern der Seite ersetzt und HTML-maskiert |

Das Dashboard bekommt seine Texte als JSON in einem Block `<script type="application/json">`; ohne ihn (oder mit einem
kaputten) bleibt es englisch. `tests/test_i18n.py` findet neue markierte Texte von selbst und schlägt fehl, bis jede
Sprachdatei sie hat, ein neues Feature kann also nicht halb übersetzt ausgeliefert werden. Regeln für deutsche Texte:
„du“, deutsche Anführungszeichen „…“ und die Begriffe, die schon in `de.json` stehen (Frist, Zweites Gehirn, Auftrag,
Aufwand).
