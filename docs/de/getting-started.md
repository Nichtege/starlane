# Erste Schritte

Du hast Starlane installiert. Diese Anleitung führt dich von einer leeren Einrichtung zu einem System, das deinen Digest
schreibt, Routinen ausführt und über deine eigenen Agenten antwortet. Es gibt zehn Stufen; mach sie der Reihe nach, eine
Sitzung pro Stufe reicht völlig.

Der Projektordner ist der Ordner mit der `aos.toml`: `~/starlane` (oder `$AOS_HOME`) nach `pip install .` und `aos setup`,
oder dein Klon, wenn du direkt daraus startest. Die Befehle unten sind als `python -m aos ...` geschrieben, so funktionieren
sie in einem Klon (`python3 -m aos` unter macOS und Linux). Nach `pip install` heißen dieselben Befehle `aos ...`: `aos next`
gibt sie so aus, und `python -m aos` findet deine Einrichtung nur, wenn es das Python ist, in das `aos` installiert wurde.

Diese Seite setzt `[user] ui_language = "de"` voraus (siehe [languages.md](languages.md)): Dann gibt `aos next` die Stufen,
Schritte und Prompts genau so aus, wie sie hier stehen.

```
python -m aos next              # Checkliste + die nächste offene Stufe
python -m aos next --all        # jede Stufe im Detail
python -m aos next --stage digest
python -m aos next --prompt     # nur der Prompt der nächsten Stufe
```

`aos next` prüft nur, ob Dateien existieren, sucht im Auftragsprotokoll nach einem fertigen Auftrag und liest aos.toml und
routines.toml; es liest nie deine Notizen, geht nie ins Netz und startet nie etwas. Die Checkliste markiert: ✓ erledigt,
→ als Nächstes, ○ später, · manuell oder optional.

## Claude Code die Einrichtung machen lassen

Jede Stufe hat einen Prompt, den du Claude Code geben kannst. Öffne ein Terminal **im Starlane-Projektordner**, starte
`claude` und füg den Prompt ein. Oder übergib ihn direkt:

```bash
claude "$(python -m aos next --prompt)"                 # bash, zsh: interaktive Sitzung mit dem Prompt
claude (python -m aos next --prompt | Out-String)       # PowerShell
python -m aos next --prompt | claude                    # Pipe-Form, wenn deine Claude-Code-Version eine erste Nachricht über die Pipe annimmt
```

**Das ist deine Wahl, und es ist etwas anderes als die Agenten.** Die Prompts laufen in deiner eigenen Claude-Code-Sitzung
mit deren normalen Rechten im Projektordner, nicht unter der nur lesenden Agenten-Positivliste. Deshalb endet jeder Prompt
mit denselben Leitplanken: nichts pushen, veröffentlichen oder senden; keine Änderungen an deinen Notizen; jede
Dateiänderung als Diff gezeigt und erst nach deinem OK geschrieben; anhalten und fragen, wenn etwas unklar ist. Lass die
Berechtigungsabfragen von Claude Code an und lies jeden Diff. Die erste Zeile nimmt deinen `[user]`-Namen und deine Sprache
aus aos.toml (die Prompts unten zeigen die Vorgaben). Siehe auch [security.md](security.md#onboarding-prompts).

## 1. Starlane auf deine eigenen Notizen zeigen lassen

Alles liest einen Ordner mit Markdown-Notizen, den Vault. Ausgeliefert zeigt er auf den Demo-Vault in examples/vault, damit sofort alles funktioniert; wechsle zu deinen eigenen Notizen, wenn du so weit bist.

*Gilt als erledigt, wenn* der eingestellte Vault-Ordner existiert und mindestens eine `.md`-Datei enthält; der mitgelieferte Demo-Vault zählt also schon. Komm zu dieser Stufe zurück, wenn du deine eigenen Notizen nutzen willst.

1. Probier zuerst alles am Demo-Vault aus: aos.toml kommt mit `[vault] path = "examples/vault"`.
2. Bereit für deine eigenen Notizen? Ein vorhandener Obsidian-Vault funktioniert so, wie er ist; ohne Notizen legt `python -m aos init ~/notes` einen kleinen Start-Vault an (er überschreibt nie etwas).
3. Öffne aos.toml und setz `[vault] path` auf deinen Ordner, z. B. "~/notes" (auch unter Windows mit "/"; ein relativer Pfad gilt relativ zur aos.toml).
4. Führ `python -m aos doctor` aus: "Vault vorhanden" und "Notizen gelesen" sollten einen Haken zeigen.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Hilf mir, Starlane vom mitgelieferten Demo-Vault (examples/vault) auf meine eigenen Notizen umzustellen.
Lies zuerst docs/de/README.md, docs/de/vault-conventions.md und aos.toml in diesem Ordner.
1. Frag mich, ob ich schon einen Ordner mit Markdown-Notizen habe (einen Obsidian-Vault) oder einen neuen Start-Vault möchte, und wo er liegt oder liegen soll.
2. Vorhandener Vault: schlag die Änderung an `[vault] path` in aos.toml vor. Neuer Vault: nachdem ich den Ordner bestätigt habe, führ `python -m aos init <folder>` aus (es legt nur Dateien an, die es noch nicht gibt), dann schlag dieselbe Änderung an aos.toml vor. Erinnere mich daran, dass `aos digest` in den Digest-Ordner dieses Vaults schreibt (`[digest] dir`, Standard AI/Digest).
3. Nachdem ich die Änderung freigegeben habe, führ `python -m aos doctor` aus und erklär jede Zeile, die keinen Haken hat.
Prüfen: doctor zeigt "Vault vorhanden" und "Notizen gelesen" mit Haken.
Lies Notizen nur so weit, wie nötig ist, um zu erkennen, ob der Ordner ein Vault ist; ändere oder verschiebe sie nie.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 2. Den Vault in Obsidian öffnen

In Obsidian liest und schreibst du die Notizen; Starlane arbeitet daneben und verlinkt direkt hinein.

*Gilt als erledigt, wenn* der Vault einen Ordner `.obsidian/` enthält.

1. Installier Obsidian von obsidian.md (kostenlos) und starte es.
2. Wähle "Ordner als Vault öffnen" und nimm den Ordner aus `[vault] path`.
3. Einstellungen > Dateien und Links: Wikilinks einschalten, neue Notizen in den Inbox-Ordner legen und einen Anhang-Ordner festlegen (zum Beispiel Resources/Attachments).
4. Kern-Plugins: Rückverweise und Graphansicht anlassen; Tägliche Notizen ist optional.
5. Setz `[vault] name` in aos.toml nur, wenn Obsidian einen anderen Vault-Namen zeigt als den Ordnernamen.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Führ mich durch das Öffnen meines Starlane-Vaults in Obsidian. Du kannst in Obsidian nicht für mich klicken: sag mir, was ich anklicken soll, und prüf das Ergebnis.
Lies zuerst docs/de/README.md, docs/de/vault-conventions.md und aos.toml in diesem Ordner.
1. Nenn mir den Vault-Ordner aus `[vault] path` in aos.toml (mit aufgelöstem ~) und führ mich durch die Installation von Obsidian und "Ordner als Vault öffnen" mit diesem Ordner.
2. Empfiehl diese Mindesteinstellungen und erklär jede in einer Zeile: Wikilinks an, neue Notizen in den Inbox-Ordner, ein Anhang-Ordner, Kern-Plugins Rückverweise und Graphansicht an, Tägliche Notizen optional.
3. Frag mich, welchen Vault-Namen Obsidian zeigt. Nur wenn er vom Ordnernamen abweicht, schlag `[vault] name = "<that name>"` für aos.toml vor.
Prüfen: der Vault-Ordner enthält jetzt einen Ordner `.obsidian` (prüf nur, dass er existiert; lies oder ändere nichts darin).
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 3. Claude Code installieren und anmelden

Agenten, Skills und die optionale Claude-Routine nutzen das Kommandozeilen-Werkzeug `claude`. Digest, Vault-Check und Dashboard laufen ohne.

*Gilt als erledigt, wenn* `claude` mit derselben sicheren PATH-Suche gefunden wird, die die Agenten nutzen (nur absolute PATH-Ordner, kein .cmd/.bat-Wrapper).

1. Installier Claude Code (siehe claude.com/claude-code), sodass `claude` in deinem PATH liegt.
2. Führ `claude` einmal in einem Terminal aus und melde dich an.
3. Windows: Starlane braucht die echte claude.exe, keinen .cmd- oder .bat-Wrapper.
4. Führ `python -m aos doctor` aus: die Zeile "claude-CLI" sollte einen Haken zeigen.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Prüf, ob Claude Code so eingerichtet ist, wie Starlane es braucht.
Lies zuerst docs/de/README.md und docs/de/security.md (die Abschnitte zu Agenten) in diesem Ordner.
1. Führ `python -m aos doctor` aus und lies die Zeile "claude-CLI". Starlane sucht nur in absoluten PATH-Ordnern, nie im aktuellen Ordner oder im Vault, und lehnt unter Windows .cmd/.bat-Wrapper ab.
2. Wenn es nicht gefunden oder abgelehnt wird, sag mir, wie ich PATH oder Installation auf meinem Betriebssystem repariere; ändere selbst keine Systemeinstellungen.
3. Erklär in zwei Sätzen, was Agenten an Anthropic senden, wenn sie laufen (siehe docs/de/security.md).
Prüfen: `python -m aos doctor` zeigt die claude-Zeile mit Haken.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 4. Deinen ersten Digest schreiben

Der Digest ist die tägliche Zusammenfassung auf einer Seite: Fristen, das Wochenziel, was dich braucht. Er ist das Einzige, was das System in den Vault schreibt.

*Gilt als erledigt, wenn* die aktuelle Digest-Datei (`[digest] file`, Standard `latest.md`) im Digest-Ordner existiert.

1. Führ `python -m aos digest` aus.
2. Öffne `AI/Digest/latest.md` (oder deinen `[digest] dir`) in Obsidian.
3. Führ `python -m aos mapcheck -v` aus, um die Befunde des Vault-Checks hinter dem Digest zu sehen.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Hilf mir, meinen ersten Starlane-Digest zu erzeugen und zu verstehen.
Lies zuerst docs/de/README.md, docs/de/vault-conventions.md und aos.toml in diesem Ordner.
1. Führ `python -m aos doctor` aus, dann `python -m aos digest`, dann `python -m aos mapcheck -v`.
2. Lies die erzeugten Dateien (die aktuelle Digest-Datei, `[digest] file`, Standard latest.md, und vault-check.md) im Digest-Ordner (`[digest] dir` in aos.toml, Standard AI/Digest) und erklär mir, was jeder Abschnitt bedeutet.
3. Fass die Befunde des Vault-Checks nach Art zusammen. Wenn die meisten daher kommen, dass mein Vault andere Ordner, Frontmatter-Schlüssel oder Überschriften als die Vorgaben nutzt, sag das und verweis mich auf die Stufe Konventionen (`python -m aos next --stage conventions`), statt vorzuschlagen, Notizen zu bearbeiten.
Prüfen: die aktuelle Digest-Datei existiert im Digest-Ordner.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 5. Das Dashboard öffnen

Das Dashboard zeigt Heute, Agenten, Skills, Artefakte, Links, Zeitleiste und Vault-Gesundheit auf einer lokalen Seite.

*Erkennung:* keine; die Checkliste zeigt diese Stufe immer als manuell (·).

1. Führ `python -m aos serve` aus (in einem Klon unter Windows startet start-dashboard.bat die Einrichtung des Klons) und öffne den Link, den es ausgibt; der Schlüssel darin ändert sich bei jedem Start.
2. OS ist der Startbildschirm: Fristen, Wochenziel und was dich braucht. Zweites Gehirn zeigt deine Notizen als Karte.
3. Atlas: frag irgendwas, Atlas wählt die Agenten. Skills: einen Skill mit Modell und Aufwand starten.
4. Artefakte: alles, was das System erzeugt hat. Ringe, Links und Zeitleiste: wie deine Notizen zusammenhängen. Gesundheit: der Vault-Check.
5. Stopp den Server mit Strg+C. Er lauscht nur auf 127.0.0.1.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Gib mir eine kurze Tour durch das Starlane-Dashboard. Starte den Server nicht selbst: ich starte ihn in meinem eigenen Terminal.
Lies zuerst docs/de/README.md, docs/architecture.md und den Abschnitt "Dashboard-Server" in docs/de/security.md in diesem Ordner.
1. Sag mir, dass ich `python -m aos serve` ausführen soll (in einem Klon unter Windows startet start-dashboard.bat die Einrichtung des Klons) und den Link öffnen soll, den es ausgibt.
2. Erklär jede Ansicht in ein oder zwei Zeilen: OS (der Startbildschirm), Zweites Gehirn, Atlas, Skills, Artefakte, Ringe, Links, Zeitleiste, Gesundheit.
3. Erklär, warum der Link einen Schlüssel enthält und warum der Server nur auf 127.0.0.1 lauscht.
4. Wenn ich "Port 8765 nicht verfügbar" melde, erklär `python -m aos serve --port 8766` oder `[server] port` in aos.toml.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 6. Routinen nach Zeitplan laufen lassen

Routinen halten Digest, Vault-Check und Dashboard ohne dich aktuell. Jede hat ein Zeitlimit, ein Tageslimit und eine Sicherung, die sie nach wiederholten Fehlschlägen sperrt.

*Gilt als erledigt, wenn* `data/state.json` existiert, das jeder Tick des Planers schreibt.

1. Führ `python -m aos install-task` aus (Windows: eine Aufgabe für deinen Benutzer, alle 5 Minuten; Linux/macOS: es gibt die crontab-Zeilen zum Eintragen aus).
2. Führ `python -m aos status` aus, um die Routinen zu sehen: digest, digest-evening, vault-check und dashboard sind an.
3. Standardmäßig aus: git-pull (hält die Kopie auf einem Server aktuell), claude-weekly-review (Claude entwirft am Sonntagabend einen Wochenrückblick), weekly-plan-monday (der Skill weekly-plan am Montagmorgen).
4. Erste Automatisierung: in routines.toml für claude-weekly-review und weekly-plan-monday `enabled = true` setzen, dann `python -m aos doctor` und `python -m aos status`.
5. Probier eine jetzt mit `python -m aos run <id>` aus. Eine gesperrte Routine gibst du mit `python -m aos unblock <id>` frei.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Hilf mir, die Starlane-Routinen und meine ersten Automatisierungen einzurichten.
Lies zuerst docs/de/README.md, routines.toml, den Abschnitt "Routinen" in docs/de/security.md und den Abschnitt "Einen Skill planen" in docs/de/skills.md in diesem Ordner.
1. Führ `python -m aos status` aus und erklär, welche Routinen es gibt, welche an sind und was die standardmäßig ausgeschalteten (git-pull, claude-weekly-review, weekly-plan-monday) tun würden, auch welche davon Claude aufrufen und Geld kosten.
2. Erklär Zeitlimit, Tageslimit und Sicherung in je einer Zeile.
3. Schlag vor, claude-weekly-review und weekly-plan-monday in routines.toml einzuschalten (nur `enabled = true`, sonst nichts). Frag mich vorher, ob ich sie will.
4. Nachdem ich zugestimmt habe, führ `python -m aos doctor` und `python -m aos status` aus, um zu prüfen, dass die Datei noch lädt.
5. Sag mir, dass ich `python -m aos install-task` selbst ausführen soll, weil es eine geplante Aufgabe einrichtet (unter Linux/macOS gibt es nur die crontab-Zeilen aus). Führ es nicht für mich aus.
Prüfen: doctor meldet routines.toml gültig, und status listet die Routinen, die ich gewählt habe, als aktiv.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 7. Einem Agenten seine erste Aufgabe geben

Agenten sind nur lesende Spezialisten, die aus deinen Notizen oder dem Web antworten. Atlas, der Koordinator, wählt die passenden für dich aus.

*Gilt als erledigt, wenn* das Auftragsprotokoll (`data/agents/jobs.jsonl`) einen fertigen Auftrag mit Status ok enthält (ein Start, eine Ablehnung oder ein fehlgeschlagener Start zählen nicht).

1. Führ `python -m aos agent research "Was steht in meinem Vault?"` aus (oder öffne Atlas im Dashboard und frag dort).
2. Führ `python -m aos agents` aus, um alle Agenten und ihre Tageslimits zu sehen.
3. Führ `python -m aos jobs` für frühere Antworten aus und `python -m aos spend` für die Kosten der Läufe.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Hilf mir, einem Starlane-Agenten meine erste Aufgabe zu geben.
Lies zuerst docs/de/README.md und docs/de/agents.md in diesem Ordner.
1. Führ `python -m aos agents` aus und erklär die mitgelieferten Agenten in je einer Zeile, und welche meine Notizen lesen und welche im Web suchen.
2. Schlag drei erste Aufgaben vor, die zu meinem Vault passen, jeweils mit dem Agenten, an den sie gehen würde. Frag mich, welche ausgeführt werden soll; Agentenläufe rufen Claude auf und kosten Geld.
3. Führ die gewählte mit `python -m aos agent <id> "<task>"` aus, dann `python -m aos jobs` und `python -m aos spend`.
Prüfen: `python -m aos jobs` listet den fertigen Auftrag.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 8. Einen eigenen Agenten anlegen

Die mitgelieferten Agenten sind ein Anfang. Ein Spezialist mit einer scharfen Beschreibung für etwas, das du oft machst, antwortet besser als ein allgemeiner.

*Gilt als erledigt, wenn* `agents.local.toml` existiert (es wird entfernt, wenn du deinen letzten eigenen Agenten löschst).

1. Dashboard: Atlas-Ansicht > Neuer Agent. Terminal: `python -m aos agent-new` (fragt Schritt für Schritt).
2. Entscheide: vault (liest Notizen) oder web (sucht im Web), nie beides.
3. Schreib die Beschreibung so: was er liefert; vault oder web. Für: ... Nicht für: ... (→ anderer Agent). Siehe docs/de/agents.md.
4. Deine Agenten landen in agents.local.toml und agents/local/; löschen mit `python -m aos agent-rm <id>`.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Hilf mir, meinen eigenen Starlane-Agenten zu entwerfen und anzulegen.
Lies zuerst docs/de/README.md, docs/de/agents.md (besonders "Eine gute Beschreibung schreiben" und "Eigene Agenten anlegen") und agents.toml in diesem Ordner.
1. Frag mich, was der Agent für mich tun soll, mit zwei oder drei echten Beispielaufgaben. Dann entscheide mit mir: Vault-Zugriff (liest meine Notizen) oder Web-Zugriff (Websuche), nie beides.
2. Schlag vor: Name, Beschreibung nach dem Muster aus docs/de/agents.md (höchstens 280 Zeichen, mit "Nicht für"-Nachbarn), Gruppe, Modell, bis zu 12 Stichwörter, bis zu 4 Beispielaufgaben und Anweisungen mit den Abschnitten Identität, Arbeitsweise, Grenzen, Ausgabe (`python -m aos agent-new --template` gibt eine Vorlage aus).
3. Nachdem ich zugestimmt habe, schreib die Anweisungen in eine temporäre Markdown-Datei in diesem Ordner, führ `python -m aos agent-new --name "..." --description "..." --instructions-file <file> [--web] --group "..." --model ... --keyword ... --example "..."` aus und lösch danach die temporäre Datei.
4. Führ `python -m aos agents` aus und zeig mir den neuen Agenten. Frag, bevor du eine Testaufgabe startest, denn das kostet Geld.
Prüfen: agents.local.toml existiert und `python -m aos agents` listet den Agenten als eigenen.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 9. Ihm die Konventionen deines Vaults beibringen

Wenn deine Notizen andere Ordner, Frontmatter-Schlüssel oder Überschriften nutzen (oder eine andere Sprache), meldet der Vault-Check viele Befunde. Ein [conventions]-Block behebt das, ohne Notizen umzubenennen.

*Gilt als erledigt, wenn* aos.toml einen `[conventions]`-Block hat, der von den Vorgaben abweicht; sonst als optional (·) gezeigt.

1. Führ `python -m aos mapcheck -v` aus. Viele Befunde zu fehlenden Typen, Status oder Ordnern bedeuten meist andere Konventionen, keinen kaputten Vault.
2. Lies docs/de/vault-conventions.md und kommentier in `[conventions]` in aos.toml nur ein, was abweicht.
3. Führ `python -m aos doctor` und `python -m aos mapcheck` noch einmal aus und vergleich die Zahlen.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Hilf mir, Starlane an die Konventionen meines Vaults anzupassen.
Lies zuerst docs/de/README.md, docs/de/vault-conventions.md und aos.toml in diesem Ordner.
1. Führ `python -m aos mapcheck -v` aus und gruppier die Befunde nach Art.
2. Sieh dir meinen Vault nur lesend an: seine obersten Ordner, die Frontmatter-Schlüssel und -Werte, die die meisten Notizen nutzen, und die Überschriften in Wochennotizen. Lies nur so viele Notizen wie nötig; ändere, verschiebe oder benenne nie eine Notiz um.
3. Schlag einen `[conventions]`-Block für aos.toml vor, der nur die Schlüssel enthält, die von den Vorgaben abweichen, und erklär jeden Schlüssel in einer Zeile mit dem Beleg aus meinem Vault.
4. Schreib ihn erst in aos.toml, wenn ich zustimme. Dann führ `python -m aos doctor` und `python -m aos mapcheck` aus und vergleich die Zahlen mit Schritt 1.
Prüfen: doctor lädt aos.toml ohne Fehler und der Vault-Check meldet weniger Befunde.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## 10. Einen Skill starten und planen

Ein Skill ist ein aufgeschriebenes Vorgehen, dem Claude folgt, von Hand oder nach Zeitplan, nur lesend wie ein Agent.

*Gilt als erledigt, wenn* eine eingeschaltete Routine in routines.toml einen Skill ausführt (`command = "skill"`).

1. Führ `python -m aos skills` aus, um sie aufzulisten, dann `python -m aos skill weekly-plan "Plane diese Woche."`.
2. Einen planen: eine Routine mit `command = "skill"` in routines.toml (weekly-plan-monday ist fertig, `enabled = true` setzen).
3. Dein eigener Skill: ein Ordner skills/<id>/ mit einer SKILL.md (Frontmatter name, description, model, effort; dann Schritte und Grenzen). Siehe docs/de/skills.md.

Prompt für Claude Code:

```text
Antworte mir auf Deutsch.

Hilf mir, Starlane-Skills zu nutzen und einen eigenen anzulegen.
Lies zuerst docs/de/README.md, docs/de/skills.md und die Ordner in skills/ in diesem Ordner.
1. Führ `python -m aos skills` aus und erklär jeden mitgelieferten Skill in einer Zeile. Frag, bevor du einen startest, denn Skill-Läufe kosten Geld.
2. Frag mich, welches Vorgehen ich oft genug wiederhole, um es aufzuschreiben. Schlag einen neuen Skill vor: skills/<id>/SKILL.md mit Frontmatter (name, description, model, effort), nummerierten Schritten, Grenzen und einer references/checklist.md, nach "Einen guten Skill schreiben" in docs/de/skills.md. Der Skill muss nur lesend bleiben: seine Ausgabe ist Text, den ich selbst übernehme.
3. Nachdem ich zugestimmt habe, leg die Dateien an und führ `python -m aos skills` und `python -m aos doctor` aus.
4. Wenn ich ihn nach Zeitplan will, schlag einen `[[routine]]`-Block mit `command = "skill"` für routines.toml vor und führ `python -m aos doctor` aus, nachdem ich zugestimmt habe.
Prüfen: `python -m aos skills` listet den neuen Skill und doctor meldet keine Probleme.
Pushe, veröffentliche oder sende nichts. Bearbeite meine Notizen nicht (nur Dateien in diesem Projektordner und aos.toml/routines.toml/agents.local.toml). Zeig mir jede Dateiänderung als Diff und warte vor dem Schreiben auf mein OK. Halte an und frag nach, wenn etwas unklar ist.
```

## Wie eine gute erste Woche aussieht

- **Tag 1:** Vault, Obsidian, Claude Code, erster Digest (Stufen 1 bis 4). Öffne einmal das Dashboard und klick dich durch.
- **Tag 2:** `python -m aos install-task`. Ab jetzt wartet jeden Morgen der Digest; lies ihn beim Kaffee.
- **Tag 3:** Stell Atlas zwei oder drei echte Fragen zu deinen Notizen. Sieh dir danach `python -m aos spend` an.
- **Tag 4:** Sieh dir den Vault-Check an. Repariere echte kaputte Links in Obsidian; geht es bei den Befunden um die
  Struktur, mach Stufe 9.
- **Tag 5:** Leg einen Agenten für etwas an, das du wirklich jede Woche machst.
- **Wochenende:** Schalte `claude-weekly-review` ein, und `weekly-plan-monday`, wenn er dir gefällt. Lies am Montag beide
  Entwürfe und übernimm, was nützt. In deine Notizen wird nie etwas geschrieben außer in den Digest-Ordner.

## Wenn etwas schiefgeht

Fang mit `python -m aos doctor` an. Jedes ✗ ist ein Problem, jedes ! ein Hinweis.

| Symptom | Ursache und Lösung |
|---|---|
| `claude` nicht gefunden | Claude Code ist nicht installiert oder nicht auf deinem PATH. Starlane sucht nur in absoluten PATH-Ordnern, nie im aktuellen Ordner oder im Vault. Installier es, öffne ein neues Terminal, führ einmal `claude` aus und melde dich an. |
| Batch-Wrapper (Windows) | Dein PATH findet zuerst `claude.cmd`. Stell den Ordner mit der echten `claude.exe` im PATH weiter nach vorn. |
| Vault vorhanden ✗ / Notizen gelesen ✗ | `[vault] path` in aos.toml zeigt auf den falschen Ordner, oder `AOS_VAULT` überschreibt ihn. Nutz `/` in Pfaden, auch unter Windows; `~` wird aufgelöst. |
| Port 8765 nicht verfügbar | Das Dashboard läuft schon, oder ein anderes Programm nutzt den Port. Nutz das offene Dashboard, oder `python -m aos serve --port 8766`, oder setz `[server] port`. |
| Kein Digest erscheint | Führ `python -m aos digest` aus und lies die Ausgabe. `[digest] dir` muss ein relativer Ordner im Vault sein (kein Laufwerk, kein `..`). Standardmäßig landet der Digest in `<vault>/AI/Digest/latest.md` (`[digest] file`). |
| Viele Befunde im Vault-Check | Meist andere Konventionen, kein kaputter Vault: siehe Stufe 9 und [vault-conventions.md](vault-conventions.md). |
| Eine Routine zeigt ⛔ | Sie ist mehrmals in Folge fehlgeschlagen und gesperrt. Lies die Notiz in `python -m aos status`, behebe die Ursache, dann `python -m aos unblock <id>`. |
| Agenten lehnen ab (Tageslimit) | Das Limit pro Agent oder die tägliche Ausgabengrenze ist erreicht; siehe `python -m aos spend` und [agents.md](agents.md#limits). |
| Text erscheint auf Englisch | `[user] ui_language` steht nicht auf `"de"`, oder `AOS_UI_LANGUAGE` überschreibt es; `python -m aos doctor` zeigt sie in der Zeile „Sprache der Oberfläche“. Daten aus deinem Vault und die Beschreibungen von Agenten, Skills und Routinen bleiben, wie sie geschrieben sind. |
