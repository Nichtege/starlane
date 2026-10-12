# Skills

Ein Skill ist ein Rezept: ein wiederholbares Vorgehen, das Claude befolgt und das einmal aufgeschrieben wird. Ein Agent ist ein Spezialist, mit dem du sprichst; ein Skill ist eine feste Arbeitsanweisung, die du ausführst, von Hand oder nach Zeitplan. Skills sind wie Agenten nur lesend: Sie lesen den Vault und ihren eigenen Ordner und antworten mit Text.

```
python -m aos skills                                   # Skills mit Modell und Aufwand auflisten
python -m aos skill weekly-plan "Plan diese Woche."    # einen ausführen
python -m aos skill weekly-plan "Plan diese Woche." --model opus --effort high
```

Im Dashboard stehen Skills im Tab Skills und im Skill-Deck auf der Startseite, jeder mit einer Auswahl für Modell und Aufwand. Ergebnisse erscheinen unter Artefakte und in `python -m aos jobs`.

## Mitgelieferte Skills
| Skill | Was er tut |
|---|---|
| `weekly-plan` | Baut aus Fristen, Wochennotiz und Projekt-Zeitplänen einen realistischen Plan für die laufende Woche. |
| `vault-triage` | Ordnet die Befunde des Vault-Checks nach Dringlichkeit und schlägt für jeden eine konkrete Lösung vor. |
| `study-plan` | Verteilt Lernstoff rückwärts von einer Prüfung oder Abgabe auf die verbleibenden Tage. |

## Aufbau
```
skills/
  weekly-plan/
    SKILL.md              # der Wegweiser: Frontmatter + Schritte + Grenzen
    references/
      format.md           # wird bei Bedarf gelesen
      checklist.md
```

`SKILL.md` beginnt mit Frontmatter:

```markdown
---
name: Wochenplan
description: Baut aus Fristen, Wochennotiz und Projekt-Zeitplänen einen realistischen Plan für die laufende Woche
model: sonnet
effort: medium
---
# Wochenplan

Du baust einen Plan für die laufende Woche und nutzt nur, was im Vault steht.

## Schritte
1. Lies den neuesten Digest in `AI/Digest/` ...
2. ...
3. Ordne die offenen Aufgaben nach Frist und Aufwand. Format und Regeln: `references/format.md`.
4. Prüf das Ergebnis gegen `references/checklist.md`, bevor du antwortest.

## Grenzen
- Erfinde nichts ...
```

| Feld | Pflicht | Bedeutung |
|---|---|---|
| `name` | ja | Anzeigename. |
| `description` | ja | Eine Zeile: was der Skill liefert. Steht auf der Skill-Karte. |
| `model` | nein | `haiku`, `sonnet`, `opus` oder `fable`. Standard `sonnet`. |
| `effort` | nein | `low`, `medium`, `high`, `xhigh` oder `max`. Leer heißt: Claudes Standard. |

Der Ordnername ist die Skill-ID (`a-z`, `0-9`, `-`). Halte `SKILL.md` kurz und leg Details (Formate, Checklisten, Beispiele, Hinweise zum Ton) in Referenzdateien: Claude liest sie nur, wenn ein Schritt darauf verweist. Das macht Läufe günstiger und fokussierter. Bis zu 40 Referenzdateien, höchstens drei Ordnerebenen tief.

### Modell und Aufwand wählen
- `haiku` / `low`: mechanisches Sortieren und Zusammenfassen einer bekannten Datei (zum Beispiel die Triage eines Berichts).
- `sonnet` / `medium`: der Standard für Planen und Entwerfen aus mehreren Notizen.
- `opus` / `high` und mehr: lange Überlegungen in mehreren Schritten über viele Notizen, oder wenn Qualität wichtiger ist als Tempo und Kosten.

Der Wert im Frontmatter ist ein Standard. Jeder Lauf kann ihn überschreiben (`--model`, `--effort` oder die Auswahl im Dashboard).

## Wo Skills gefunden werden
`[skills] dirs` in `aos.toml`, Standard `["skills", "~/.claude/skills"]`. Pro Skill-ID gewinnt der erste Treffer, ein Projekt-Skill schlägt also einen mit derselben ID in deinem Claude-Ordner. Verlinkte Skill-Ordner (Symlinks, Junctions) werden übersprungen, verlinkte Dateien fehlen in der Referenzliste eines Skills.

## Einen Skill planen
Eine Routine mit `command = "skill"` führt einen Skill ohne Oberfläche aus. Trag sie in `routines.toml` ein:

```toml
[[routine]]
id = "weekly-plan-monday"
description = "Skill 'weekly-plan' schreibt montags früh den Plan für die Woche -> Dashboard, Artefakte"
schedule = "weekly mon 07:00"
command = "skill"
skill = "weekly-plan"
instruction = "Erstell den Plan für diese Woche."
model = "sonnet"
effort = "medium"
machine = "any"
enabled = true
timeout_s = 960
max_runs_per_day = 1
max_failures = 2
```

Skill-ID, Auftrag, Modell und Aufwand werden beim Laden von `routines.toml` geprüft und als einzelne Argumente übergeben, nie über eine Shell. Das Zeitlimit des Skills selbst kommt aus `[skills] timeout_s`; `timeout_s` der Routine wird auf mindestens 960 Sekunden angehoben, damit der äußere Zeitgeber nie zuerst auslöst.

## Sicherheit
- Ein Skill-Lauf hat dieselbe Sperre wie ein Vault-Agent: nur `Read`, `Grep` und `Glob`, keine Connectors, keine gespeicherte Sitzung, ein Budget, ein Zuglimit, ein Zeitlimit (höchstens 15 Minuten) und die tägliche Ausgabengrenze, die er sich mit den Agenten teilt. Ein Skill kann sich keine weiteren Werkzeuge geben, auch nicht über sein Frontmatter.
- Neben dem Vault wird der eigene Ordner des Skills als lesbar hinzugefügt (`--add-dir`), damit die Referenzdateien erreichbar sind. Was Claude öffnen darf, entscheiden die Berechtigungsregeln von Claude Code und deine Einstellungen auf Benutzerebene (siehe [security.md](security.md)).
- Wie jeder Lauf schicken Skill-Läufe den Auftrag und alles, was Claude liest, an Anthropic.
- Modell und Aufwand kommen aus festen Listen; alles andere wird abgelehnt.
- Jeder Skill hat ein Tageslimit (`[skills] max_runs_per_day`), es läuft höchstens ein Lauf pro Skill gleichzeitig und insgesamt drei zusammen mit den Agenten.
- Die Antwort wird geschwärzt (nach bestem Bemühen, übliche Formen von Schlüsseln, Tokens und Passwörtern) und nie in eine Notiz geschrieben.
- Skills aus `~/.claude/skills` können aus Plugins oder Synchronisierungen stammen. Ihr Text steuert Claude, nicht dein System; das Schlimmste, was ein schlechter Skill tun kann, ist eine schlechte Antwort. Lies trotzdem die `SKILL.md`, bevor du dich auf den Skill eines anderen verlässt.

Details: [security.md](security.md).

## Einen guten Skill schreiben
- Eine Aufgabe pro Skill. Wenn du „und außerdem“ schreibst, mach zwei Skills daraus.
- Schreib Schritte, keine Wünsche: welche Datei zuerst zu lesen ist, was zu berechnen ist, in welcher Reihenfolge, in welchem Format geantwortet wird.
- Sag, was zu tun ist, wenn Informationen fehlen (nachfragen oder als offene Frage auflisten), damit der Skill nie etwas erfindet.
- Bleib auch im Geist nur lesend: Das Ergebnis ist Text, den du übernimmst, nie „aktualisiere die Notiz“.
- Schließ mit einer kurzen Checkliste in einer Referenzdatei ab, gegen die der Skill seine Antwort prüft.
