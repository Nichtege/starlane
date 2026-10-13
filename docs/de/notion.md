# Notion

Ein Agent, `notion`, liest und ändert dein Notion: Er speichert Ergebnisse dort, aktualisiert Seiten und Datenbanken und findet Dinge darin. Er ist der einzige Agent in Starlane, der etwas ändert, und nur in den Notion-Seiten, die du mit ihm teilst. Er löscht nie: Er fragt dich, und Starlane löscht nach deinem Ja.

Andere Agenten bekommen Notion nicht. Brauchen sie es während eines Auftrags, fragen sie den Notion-Agenten (siehe [Agenten sprechen miteinander](agents.md#agenten-sprechen-miteinander)), und Atlas sieht dieses Gespräch, wenn es ihre Berichte prüft.

## Einrichten

Du brauchst [Node](https://nodejs.org) (die LTS-Version) und ein Notion-Konto.

1. **Eine Integration anlegen.** Geh auf <https://www.notion.so/profile/integrations>, *Neue Integration*, Typ *Intern*, wähl deinen Workspace. Schalte unter *Fähigkeiten* *Inhalte lesen*, *Inhalte aktualisieren*, *Inhalte einfügen*, *Kommentare lesen* und *Kommentare einfügen* ein. Kopier das *Internal Integration Secret* (es beginnt mit `ntn_`).
2. **Starlane verbinden.**
   ```
   python -m aos notion-connect
   ```
   Das lädt Notions offiziellen MCP-Server (`@notionhq/notion-mcp-server`, eine feste Version), prüft ihn gegen die von npm veröffentlichte Prüfsumme, behält nur die zwei Dateien, aus denen er läuft, und fragt nach dem Secret (Eingabe verborgen). Das Secret wird in `data/notion/token` gespeichert, außerhalb deiner Projektdateien. `NOTION_TOKEN` in der Umgebung hat Vorrang vor dem gespeicherten. Für ein Skript: `python -m aos notion-connect --token-stdin < datei`; ein neues Secret: `--new-token`.
3. **Seiten mit der Integration teilen.** Notion zeigt der Integration nichts, bis du teilst: Seite oder Datenbank öffnen, *•••* → *Verbindungen* → deine Integration. Unterseiten folgen ihrer Elternseite. Teile ein paar oberste Seiten (eine Seite *Starlane* für Ergebnisse, deine Projekt-Datenbank), nicht den ganzen Workspace.
4. **Den Server neu starten** (`python -m aos serve`), wenn er läuft, dann prüfen:
   ```
   python -m aos notion      # Node, Server, Token, wartende Anfragen
   python -m aos doctor      # dasselbe, zwischen den anderen Prüfungen
   ```

Der Agent steht im mitgelieferten Katalog (`agents.toml`, Prompt `agents/notion.md`). Solange Notion nicht verbunden ist, schlägt ein Auftrag an ihn mit einem kurzen Hinweis fehl, `notion-connect` auszuführen; sonst ändert sich nichts.

## Benutzen

Frag Atlas, zum Beispiel *„Speichere den Wochenplan auf meiner Notion-Seite Woche“*, oder den Agenten direkt: `python -m aos agent notion "Trag die drei offenen Aufgaben aus meinen Notizen in die Datenbank Aufgaben ein"`. Unter der Antwort klappt das Dashboard auf, was er in Notion geändert hat (*In Notion geändert*) und mit welchen Agenten er gesprochen hat (*Agenten haben gesprochen*).

## Löschen braucht dein Ja

Der Agent kann nicht löschen. Der **Notion-Wächter** (`aos/notionguard.py`, ein Claude-Code-Hook um jeden Notion-Aufruf des Agenten) blockt das Löschen eines Blocks und jeden Aufruf, der etwas archiviert oder in den Papierkorb legt (`archived`, `in_trash`, `allow_deleting_content` auf true, egal wo sie im Aufruf stehen), und das Lösch-Werkzeug steht auch nicht in der Erlaubnisliste des Agenten. Soll etwas weg, stellt der Agent stattdessen eine **Löschanfrage** und sagt dir das in seiner Antwort.

Bevor eine Anfrage gespeichert wird, fragt Starlane Notion selbst, was das Ziel ist; du entscheidest also über den echten Titel und Link, nicht über die Beschreibung des Agenten. Anfragen warten in `data/notion/requests.jsonl` (höchstens 20 gleichzeitig), bis du entscheidest:

- **Dashboard**: Im Chat von Atlas zeigt ein Kasten *Notion · wartet auf dich* jede Anfrage mit der Begründung des Agenten und einem Link zur Seite. *Behalten* schließt sie; *Löschen* löscht.
- **Terminal**: `python -m aos notion` listet sie auf, `python -m aos notion-approve <id>` löscht, `python -m aos notion-deny <id>` behält.

Erst nach deinem Ja ruft Starlane selbst (kein Modell) Notion auf: Eine Seite geht in den Papierkorb von Notion, wo du sie 30 Tage lang wiederherstellen kannst; ein Block wird gelöscht. Lehnt Notion ab, wird die Anfrage als fehlgeschlagen geschlossen, mit dem Grund von Notion.

## Was er kann und was nicht

| Kann | Kann nicht |
|---|---|
| die geteilten Seiten und Datenbanken lesen, durchsuchen und abfragen | etwas sehen, das du nicht geteilt hast |
| Seiten anlegen, Eigenschaften und Text ändern, Blöcke und Kommentare hinzufügen, Seiten verschieben, Datenquellen anlegen und ändern | etwas löschen oder archivieren (er fragt dich) |
| deinen Vault als Kontext lesen (`Read`, `Grep`, `Glob`) | im Web suchen oder abrufen (nie zusammen mit Notion, das Laden lehnt es ab) |
| Fragen anderer Agenten zu Notion beantworten | in deine Notizen schreiben |

Nur ein Agent darf das Werkzeug `Notion` haben; ein zweiter, oder einer, der auch Web-Werkzeuge hat, wird beim Laden von `agents.toml` abgelehnt.

## Sicherheit

- **Der Token** erreicht Notions Server nur über die Umgebung des eigenen Laufs des Notion-Agenten; er steht nie in einer Befehlszeile, in der Konfiguration des Laufs oder in einer Datei, die der Lauf mit seinen Werkzeugen lesen kann. Jeder andere Lauf startet ohne `NOTION_TOKEN` in seiner Umgebung.
- **Der Server-Code** wird vor jedem Lauf per SHA-256 geprüft. Haben sich die Dateien in `data/notion/server/` geändert, startet der Notion-Agent nicht, bis du `notion-connect` erneut ausführst.
- **Notion-Text ist Material, keine Anweisung.** Eine Seite kann Text enthalten, der versucht, den Agenten zu lenken. Der Wächter verhindert Löschungen, egal was dem Agenten gesagt wurde; gewöhnliche Änderungen an den geteilten Seiten verhindert er nicht. Teile also nur, was der Agent ändern darf, und teile keine Seiten, die im Web veröffentlicht sind: Was der Agent in so eine Seite schreibt, ist öffentlich.
- Jede Änderung des Agenten steht an seinem Auftrag (`notion_changes`: Werkzeug und Seiten- oder Block-ID). Notions eigener Seitenverlauf zeigt die Einzelheiten und kann sie rückgängig machen.

Mehr in [security.md](security.md#notion).
