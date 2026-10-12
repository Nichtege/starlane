# Vault-Konventionen

Starlane liest einen Ordner mit Markdown-Notizen (einen *Vault* im Stil von Obsidian). Für Digest, Vault-Check und
Dashboard muss es ein paar Dinge darüber wissen, wie dieser Ordner aufgebaut ist: welcher Frontmatter-Schlüssel den Typ
einer Notiz enthält, welche Status ein Projekt haben darf, wo Wochennotizen liegen, wie die Überschrift über deinem
Wochenziel heißt.

Das sind die *Konventionen*. Alle haben englische Vorgaben, ein neuer Vault, der ihnen folgt, braucht also keine
Einstellungen. Hat dein Vault schon eine eigene Struktur (oder ist er auf Deutsch geschrieben), beschreibst du sie einmal
in der Tabelle `[conventions]` in `aos.toml`, statt deine Notizen umzubenennen. Ein fertiger Block für einen deutschen
Vault steht [am Ende dieser Seite](#beispiel-ein-deutscher-vault).

**Beispiel zum Ansehen:** [`examples/vault/`](../../examples/vault/) ist ein kleiner Demo-Vault, der jeder Vorgabe auf
dieser Seite folgt: Projekte mit Status und Frist, eine Zeitplan-Notiz, Bereichsnotizen, Wochennotizen mit Wochenziel und
Rückblick, eine Inbox, eine Schnellliste für Ideen, eine Sitzungsnotiz unter `AI/Sessions/` und eine `CLAUDE.md` mit Regeln
für Agenten. Die mitgelieferte `aos.toml` zeigt auf ihn. Er spielt in der Woche 2026-W41: In dieser Woche meldet sein
Vault-Check keine Befunde; an einem späteren Datum meldet er eine Warnung (`no-week-note` für die laufende Woche), und der
Digest zeigt einige Aufgaben als überfällig. Das ist die Demo, die altert, keine kaputte Einrichtung.

## Was das System liest

Ordner- und Notiznamen auf dieser Seite sind die Vorgaben; jeder folgt seinem Schlüssel in der Tabelle am Ende.

| Teil | Liest | Nutzt es für |
|---|---|---|
| Vault-Check (`aos mapcheck`) | jede Notiz: Links, Frontmatter, `index.md`, `AI/brain-map.md`, Regeln im Stil von `CLAUDE.md` | `vault-check.md`, die Ansicht Gesundheit |
| Digest (`aos digest`) | Projektnotizen (Frist, Status), die aktuelle Wochennotiz, Zeitplan-Notizen, `Inbox/`, `Ideas/README.md`, `AI/Sessions/` | `latest.md`, die Ansicht Heute |
| Dashboard (`aos dashboard`, `aos serve`) | alle Notizen (Titel, Typ, Status, Projekt, Tags, Links) | Graph, Ringe, Zeitleiste; Bereiche und Ringe folgen den Schlüsseln `*_dir`, `brain_map`, `index_note` und `status_done` |

Das System bearbeitet deine Notizen nie. Es schreibt nur in den Digest-Ordner (`[digest] dir`, Standard `AI/Digest`):

| Datei | Geschrieben von | Inhalt |
|---|---|---|
| `AI/Digest/latest.md` | `aos digest` | der Digest von heute (`[digest] file`) |
| `AI/Digest/archive/JJJJ-MM-TT.md` | `aos digest` | eine Kopie pro Tag, gelöscht nach `[digest] keep_days` (`[digest] archive`) |
| `AI/Digest/vault-check.md` | `aos digest`, `aos mapcheck` | jeder Befund des Vault-Checks, mit Datei und Zeile |
| `AI/Digest/weekly-review.md` | `aos claude-digest` (optional) | ein Entwurf für den Wochenrückblick, von Claude geschrieben, nur lesender Lauf (`[digest] review`) |

Dateien im Digest-Ordner überspringt der Vault-Check, das System bewertet also nie seine eigene Ausgabe. Ein Digest-Ordner,
der außerhalb des Vaults landet (zum Beispiel über einen Symlink), wird abgelehnt.

## Eine Notiz nach den Vorgaben

```markdown
---
type: project
created: 2026-10-02
status: active
deadline: 2026-11-10
tags: [project, writing]
---
# Abschlussarbeit

Part of [[Areas/university]]

## Next steps
- [ ] Gliederung fertigstellen
- **Di 13.10.** Termin mit der Betreuung
```

Notizen in `AI/` (von Agenten oder Sitzungen geschrieben) sollen sagen, wozu sie gehören, sowohl im Frontmatter
(`project:`, `projects:` oder `area:`) als auch als Zeile `Part of [[...]]` in den ersten 20 Zeilen. Mit dem deutschen
Block unten heißen die Schlüssel `projekt:`, `projekte:`, `bereich:` und die Zeile `Gehört zu [[...]]`.

## Daten in Notizen

Der Digest sucht Daten in Notizen unter `projects_dir`, `areas_dir` und `journal_dir` (ohne Vorlagen), und nur in
offenen Listenpunkten (`- ...`, `- [ ] ...`; nicht abgehakt, nicht ~~durchgestrichen~~) und in Überschriften von `##`
bis `####`. Er versteht genau drei Formen:

- `2026-11-10` (ISO, `JJJJ-MM-TT`)
- `10.11.2026` (`TT.MM.JJJJ`)
- ein Wochentag, gefolgt von Tag.Monat: `Di 6.10.`, `Dienstag, 6.10.`, `Tue 6.10.`. Der Wochentag muss zum Datum
  passen, das entscheidet auch das Jahr. Deutsche und englische Namen und Abkürzungen gehen (`Mo Di Mi Do Fr Sa So`,
  `Montag` … `Sonntag`), mit oder ohne Komma nach dem Wochentag.

Alles andere ist für den Digest kein Datum: Monatsnamen (`10. November`, `Nov 10`), amerikanische Reihenfolge
(`11/10/2026`) und ein nacktes `6.10.` ohne Wochentag werden nicht erkannt.

Daten, die Verlauf sind und keine Termine, werden ignoriert:

- in einem Abschnitt, dessen Überschrift eines der `log_words` enthält (zum Beispiel `## Erledigt` oder `## Logbuch`),
  bis zur nächsten Überschrift;
- in *Logzeilen*: Listenpunkte, die mit einem Datum Tag.Monat beginnen, wahlweise fett und mit Jahr, gefolgt von `:`,
  `-` oder `–` (`- 12.10.: Bank angerufen`, `- **12.10.2026** – verschickt`). Ein Listenpunkt, der mit einem ISO-Datum
  beginnt, ist keine Logzeile.

Zeitplan-Notizen (jede Notiz, deren Pfad `schedule_keyword` enthält) dürfen Checkboxen unter datierten Überschriften
gruppieren, etwa `## Woche 2 · Mo 12.10 – So 18.10`. Offene Checkboxen im aktuellen Zeitraum erscheinen als Aufgaben,
die in einem vergangenen Zeitraum als überfällig.

## Alle Konventions-Schlüssel

Jeder Schlüssel ist optional. Texte dürfen nicht leer sein, Listen müssen Listen aus nicht leeren Texten sein, und
unbekannte Schlüssel sind ein Fehler (ein Tippfehler fällt also nicht still auf die Vorgabe zurück). Die Schlüssel selbst
bleiben englisch, auch in einem deutschen Vault; nur ihre Werte beschreiben deine Notizen.

| Schlüssel | Vorgabe | Bedeutung |
|---|---|---|
| `type_key` | `type` | Frontmatter-Schlüssel mit dem Typ der Notiz |
| `created_key` | `created` | Frontmatter-Schlüssel mit dem Erstelldatum |
| `status_key` | `status` | Frontmatter-Schlüssel mit dem Status |
| `deadline_key` | `deadline` | Frontmatter-Schlüssel mit der Frist eines Projekts (`JJJJ-MM-TT`) |
| `tags_key` | `tags` | Frontmatter-Schlüssel mit den Tags |
| `project_key` | `project` | Frontmatter-Schlüssel, der eine Notiz mit ihrem Projekt verbindet (`"[[Projects/x]]"`) |
| `projects_key` | `projects` | dasselbe als Liste |
| `area_key` | `area` | Frontmatter-Schlüssel, der eine Notiz mit einem Bereich verbindet |
| `type_project` | `project` | Typ-Wert einer Projektnotiz (Fristen, Status-Prüfung) |
| `type_idea` | `idea` | Typ-Wert einer Ideennotiz (Status-Prüfung) |
| `type_week` | `week` | Typ-Wert einer Wochennotiz; genutzt, wenn `aos init` Notizen schreibt, sonst reserviert |
| `type_plan` | `plan` | reserviert: noch von keiner Logik gelesen (Zeitplan-Notizen findet `schedule_keyword`) |
| `type_knowledge` | `knowledge` | reserviert: noch von keiner Logik gelesen |
| `type_session` | `session` | reserviert: noch von keiner Logik gelesen (Sitzungsnotizen findet `sessions_dir`) |
| `type_overview` | `overview` | Typ-Wert einer Übersicht (zum Beispiel der Brain-Map); genutzt, wenn `aos init` Notizen schreibt, sonst reserviert |
| `type_index` | `index` | Typ-Wert des Index; genutzt, wenn `aos init` Notizen schreibt, sonst reserviert |
| `type_digest` | `digest` | Typ-Wert, den das System in seine eigenen Dateien schreibt |
| `project_status` | `["idea", "new", "building", "active", "paused", "done"]` | erlaubte Status eines Projekts (`status_done` ist immer auch erlaubt) |
| `status_done` | `done` | Projektstatus für „fertig“ (keine Fristen-Karte, im Dashboard als abgeschlossen gezeigt) |
| `idea_status` | `["raw", "in-progress", "project", "dropped"]` | erlaubte Status einer Idee |
| `week_goal_heading` | `Weekly goal` | Überschrift in der Wochennotiz über dem Ziel oder den Zielen |
| `weekly_review_heading` | `Weekly review` | Überschrift in der Wochennotiz für den Rückblick am Wochenende |
| `ideas_quick_heading` | `Quick` | Überschrift (oder ein Teil davon) der Schnellliste in `Ideas/README.md` |
| `belongs_to` | `Part of` | Wendung vor dem Link, der sagt, wozu eine KI-Notiz gehört |
| `log_words` | `["status", "done", "log", "history", "result", "learned", "went wrong", "notes", "archive"]` | Wörter, die eine Überschrift zu einem Log-Abschnitt machen |
| `projects_dir` | `Projects` | Ordner der Projektnotizen |
| `areas_dir` | `Areas` | Ordner der Bereichsnotizen |
| `resources_dir` | `Resources` | Ordner der Nachschlage-Notizen |
| `journal_dir` | `Journal` | Ordner der Wochennotizen, benannt nach ISO-Woche (`Journal/2026-W41.md`) |
| `inbox_dir` | `Inbox` | Inbox-Ordner; jede Notiz darin und jeder Listenpunkt in seiner `README.md` ist etwas zum Einsortieren |
| `ideas_dir` | `Ideas` | Ideen-Ordner (seine `README.md` enthält die Schnellliste) |
| `archive_dir` | `Archive` | Archiv-Ordner |
| `templates_dir` | `Resources/Templates` | Vorlagen: nie geprüft, nie als Ereignis gezeigt |
| `ai_dir` | `AI` | Ordner der Notizen, die Agenten schreiben (müssen sagen, wozu sie gehören) |
| `sessions_dir` | `AI/Sessions` | Sitzungsnotizen, die neueste steht im Digest |
| `week_template` | `Resources/Templates/week` | Vorlage, die genannt wird, wenn eine Wochennotiz fehlt |
| `schedule_keyword` | `schedule` | eine Notiz, deren Pfad dieses Wort enthält, wird als Zeitplan gelesen |
| `index_note` | `index.md` | Einstiegspunkt des Vaults (Zwei-Schritte-Regel); muss auf `.md` enden |
| `brain_map` | `AI/brain-map.md` | zweiter Einstiegspunkt, eine Karte der wichtigen Notizen mit ihrer Größe; muss auf `.md` enden |
| `project_note` | (keine) | optional, z. B. `Projects/mein-projekt`: die erzeugten Dateien verlinken auf diese Notiz, wenn es sie gibt |

Den Digest-Ordner selbst legt `[digest] dir` fest, nicht diese Tabelle. Ordner-Schlüssel (`*_dir`) und `[digest] dir`
müssen relative Ordner im Vault sein: kein Laufwerk (`C:`), kein Pfad, der mit `\` beginnt, kein `..`. `[digest] dir`
darf auch nicht mit `/` beginnen; bei den Ordner-Schlüsseln werden führende und abschließende `/` einfach entfernt.
`project_note` und `week_template` sind Link-Ziele; ein abschließendes `.md` fällt weg. Die reservierten Schlüssel
bleiben erhalten, damit eine Konfiguration, die sie setzt, gültig bleibt (unbekannte Schlüssel sind ein Fehler).

`aos init <ordner>` schreibt seine Start-Notizen mit den Konventionen der Konfiguration, die es findet (`--config`,
`$AOS_CONFIG` oder `aos.toml` neben dem Projekt), einschließlich `[digest] dir`; ohne Konfiguration nutzt es die
Vorgaben. Der Text der Start-Notizen folgt der Oberflächensprache (`[user] ui_language`).

## Mitgelieferte Prompts und Skills

Die Agenten-Prompts in `agents/*.md` und die Skills in `skills/` sind reiner Text, geschrieben für den Standardaufbau:
Wo sie `index.md`, `AI/brain-map.md`, den Digest-Ordner (`AI/Digest/`), `Journal/` oder `Projects/` erwähnen, meinen sie
„die Notiz oder den Ordner mit dieser Rolle“. Sie lesen `[conventions]` nicht. Nutzt dein Vault andere Namen, bearbeite
diese Dateien (oder kopier sie in einen eigenen Agenten oder Skill), damit die Agenten an den richtigen Stellen suchen.

Die *Zwei-Schritte-Regel*: Jede Notiz soll in höchstens zwei Links von `index_note` oder `brain_map` aus erreichbar sein.
Notizen, die gar nicht erreichbar sind, werden als `unreachable` gemeldet.

## Beispiel: ein deutscher Vault

Ein Vault mit deutschem Frontmatter und deutschen Überschriften funktioniert mit diesem Block in `aos.toml`:

```toml
[conventions]
type_key = "typ"
created_key = "erstellt"
project_key = "projekt"
projects_key = "projekte"
area_key = "bereich"
type_project = "projekt"
type_idea = "idee"
type_week = "woche"
type_knowledge = "wissen"
type_overview = "uebersicht"
project_status = ["idee", "neu", "aufbau", "aktiv", "pausiert", "abgeschlossen"]
status_done = "abgeschlossen"
idea_status = ["roh", "in-arbeit", "projekt", "verworfen"]
week_goal_heading = "Wochenziel"
weekly_review_heading = "Sonntags-Check"
ideas_quick_heading = "Schnell"
belongs_to = "Gehört zu"
log_words = ["stand", "erledigt", "logbuch", "verlauf", "ergebnis", "gelernt", "lief schief", "protokoll", "historie"]
ideas_dir = "Ideen"
week_template = "Resources/Templates/woche"
schedule_keyword = "zeitplan"
```

Die Konventionen decken nur ab, was zu deinen Notizen passen muss. Die Sprache des erzeugten Texts (Digest, Vault-Check,
Terminal, Dashboard) ist eine eigene Einstellung, `[user] ui_language = "de"`, und lässt auch die Agenten auf Deutsch
antworten; siehe [languages.md](languages.md). Auch die Dateinamen im Digest-Ordner können deinem Vault folgen:

```toml
[user]
ui_language = "de"

[digest]
file = "aktuell.md"            # statt latest.md
archive = "archiv"             # statt archive/
review = "wochenrueckblick.md" # statt weekly-review.md
```
