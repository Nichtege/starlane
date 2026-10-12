# Auf einem Server (optional)

Alles funktioniert auf einem Laptop. Ein kleiner, immer laufender Server (ein VPS) kann denselben Code mit demselben Vault und denselben Routinen ausführen, damit der Morgen-Digest auch dann kommt, wenn dein Laptop zugeklappt ist. Nichts davon ist nötig; diese Seite beschreibt, wie es geht, wenn du es willst.

## Wann lohnt es sich?
Wenn der Digest auch kommen soll, während dein Laptop aus ist, oder wenn du Routinen willst, die nachts laufen (zum Beispiel den Entwurf für den Wochenrückblick). Den meisten reicht der Laptop allein.

## Bevor du anfängst (Bedingungen von Anthropic)
Claude Code mit **deinem eigenen Konto** auf deinem eigenen Server zu betreiben, ist die normale Nutzung. Ein Abonnement über Programme Dritter (andere Agenten-Umgebungen) zu leiten, ist womöglich nicht erlaubt. Prüf die aktuellen Nutzungsbedingungen selbst, bevor du etwas einrichtest.

## Schritte (Linux-Server, zum Beispiel Ubuntu)
1. **Server mieten.** Die kleinste Stufe reicht.
2. **Mit Tailscale privat machen** (oder einem anderen privaten Netz wie WireGuard). Installier es auf Laptop, Handy und Server und melde dich überall mit demselben Konto an. Danach sehen nur deine Geräte den Server. Öffne keine Ports ins Internet.
3. **Vault klonen**: `git clone <dein-vault-repository> ~/notes`. Nimm ein Zugriffstoken, das nur **lesen** kann, wenn der Server nur anzeigen und zusammenfassen soll.
4. **Dieses Projekt auf den Server kopieren** (`git clone` aus deinem eigenen Repository, oder `scp`). Es braucht Python 3.11 oder neuer: prüf das mit `python3 --version`. Ubuntu 22.04 liefert 3.10 (24.04 liefert 3.12); installier dort zuerst ein neueres (zum Beispiel über das deadsnakes-PPA oder `uv python install 3.12`) und nimm diesen Interpreter (`python3.12`, oder den Pfad, den `uv python find 3.12` ausgibt) überall, wo diese Seite `python3` sagt. Sonst ist nichts nötig: starte es aus dem Ordner (`python3 -m aos doctor`).
5. **`aos.toml` anpassen**: `[vault] path = "/home/<user>/notes"`, `[machine] name = "server"` (auf dem Laptop: `[machine] name = "mein-laptop"`; ohne diese Zeile wird der Rechnername genommen). Mit `[user] ui_language = "de"` schreibt auch der Server Digest und Vault-Check auf Deutsch; stell beide Rechner gleich ein, sonst wechselt die Sprache des Digests je nachdem, wer ihn zuletzt geschrieben hat.
6. **Routinen verteilen** in `routines.toml`: zum Beispiel `machine = "server"` für den Morgen-Digest (er kommt auch, wenn der Laptop zu ist) und `machine = "mein-laptop"` für alles, was nur dort Sinn ergibt. Schalte `git-pull` für den Server ein (`enabled = true`), damit er immer deinen aktuellen Stand hat.
7. **Planen**: führ `python3 -m aos install-task` aus. Unter Linux und macOS ändert es nichts und gibt zwei Zeilen aus; trag sie mit `crontab -e` ein. Sie sehen so aus (deine Pfade, dein `python3`):
   ```
   PATH=/home/<user>/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
   */5 * * * * cd /home/<user>/starlane && mkdir -p /home/<user>/starlane/data && PYTHONPATH=/home/<user>/starlane /usr/bin/python3 -P -m aos --config /home/<user>/starlane/aos.toml tick --quiet >> /home/<user>/starlane/data/tick.log 2>&1
   ```
   Die erste Zeile ist wichtig: cron startet mit einem nackten `PATH=/usr/bin:/bin`, ohne sie fänden Routinen, die Claude aufrufen, `claude` nicht. Wird `claude` gefunden, beginnt die Zeile mit seinem Ordner. Hat deine crontab schon eine `PATH=`-Zeile, führ die Ordner darin zusammen. Danach zeigt `python3 -m aos doctor`, ob die Zeile eingetragen ist. Unter macOS braucht cron womöglich Vollzugriff auf die Festplatte (Systemeinstellungen > Datenschutz & Sicherheit), bevor es einen Vault in Dokumente, Schreibtisch, Downloads, iCloud Drive oder auf einem Wechsel- oder Netzlaufwerk lesen kann; ein Vault an anderer Stelle in deinem Benutzerordner braucht das nicht.
8. **Dashboard von einem anderen Gerät**: Führ auf dem Server `python3 -m aos serve --no-browser` aus. Es gibt einen Link `http://127.0.0.1:8765/?k=<schlüssel>` aus; der Schlüssel ist bei jedem Start neu. Der Server lauscht absichtlich nur lokal und nimmt nur den `Host`-Header `127.0.0.1:<port>` oder `localhost:<port>` an, der Zugriff muss also über einen **SSH-Tunnel auf dieselbe lokale Portnummer** kommen:
   ```
   ssh -N -L 8765:127.0.0.1:8765 <user>@<server>
   ```
   Öffne dann den ausgegebenen Link (`http://127.0.0.1:8765/?k=<schlüssel>`) auf dem Gerät, auf dem der Tunnel läuft. Ein anderer lokaler Port (`-L 9000:127.0.0.1:8765`) funktioniert nicht: Der Browser würde `Host: 127.0.0.1:9000` schicken, und der Server lehnt das ab. Auf einem Handy nimm eine SSH-App, die lokale Portweiterleitung kann, mit derselben Regel. **Tailscale Serve und andere Reverse-Proxys werden nicht unterstützt**: Sie leiten einen anderen `Host`-Header weiter (deinen Tailnet-Namen), den der Server absichtlich ablehnt (Schutz gegen DNS-Rebinding).

## Claude Code auf dem Server absichern
Wenn du Claude Code dort betreibst (zum Beispiel für den Wochenrückblick), leg **eine** Einstellungsdatei an, die alles blockiert, was sendet. Beispiel `~/.claude/settings.json` auf dem Server:
```json
{
  "permissions": {
    "deny": [
      "Bash(git push:*)", "Bash(curl:*)", "Bash(wget:*)", "Bash(ssh:*)", "Bash(scp:*)", "Bash(rm:*)",
      "WebFetch", "WebSearch"
    ]
  }
}
```
Hast du Connectors installiert (Mail, Chat, Cloud-Speicher), nimm deren Werkzeuge zum Senden, Antworten, Weiterleiten und Löschen in dieselbe `deny`-Liste auf. Dann kann der Server dir im schlimmsten Fall einen Entwurf hinterlassen, aber nie einen senden.

Läufe von Agenten, Skills und Routinen lesen diese Einstellungen auf Benutzerebene ebenfalls. Die Zeile `"WebFetch", "WebSearch"` schaltet auf diesem Server deshalb die **Web-Agenten** ab (`assistant`, `data-analyst`, `coder`, `tutor` und deine eigenen Web-Agenten): Ihre Läufe schlagen fehl. Behalt die Zeile, wenn der Server nie ins Web soll; nimm sie heraus, wenn du dort Web-Agenten willst. Leg in dieser Datei keine `allow`-Regeln oder Hooks an: Sie würden ebenfalls für jeden Lauf gelten (siehe [security.md](security.md)).

## Synchronisierung
Die einfachste sichere Lösung: **Git als einzige Quelle der Wahrheit**. Der Laptop pusht (zum Beispiel mit dem Obsidian-Git-Plugin), der Server holt mit `git-pull` alle 10 Minuten. Abgesehen von `git pull` selbst (das die Vault-Dateien auf den Stand deines Remotes bringt) **schreibt** der Server nur in den Digest-Ordner des Vaults (standardmäßig `AI/Digest/`); damit es keine Konflikte gibt, schreibt entweder der Laptop oder der Server den Digest, nicht beide (leg die Routine mit `machine = ...` fest).

### Alternative: Syncthing (wenn der Server auch Dateien erzeugen soll, die du auf dem Laptop willst)
Für dieses System reicht Git, weil der Server nur liest. Syncthing (kostenlos, Open Source) lohnt sich nur, wenn beide Seiten Dateien anlegen, zum Beispiel `data/artifacts/` mit HTML-Ergebnissen, die du auf dem Laptop sehen willst:
1. Installier Syncthing auf Laptop und Server und kopple die beiden Geräte.
2. Teile **nur** diese Ordner: `skills/` und `data/artifacts/`. Nie `data/` als Ganzes (Zustand und Logs gehören jeweils einem Rechner) und nie `.git`.
3. Auf dem Server bleibt `aos serve` lokal wie oben. Skill-Routinen mit `machine = "server"` legen ihre Ergebnisse dann ins Dashboard (Artefakte).

## Nicht enthalten
Spracheingabe über einen Chat-Bot (Sprache zu Text, an Claude weitergeleitet) bräuchte ein Bot-Token und einen Spracherkennungsdienst. Sie ist absichtlich nicht Teil dieses Projekts.
