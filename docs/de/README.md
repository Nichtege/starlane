# Starlane

Ein kleines Betriebssystem rund um einen Ordner mit Markdown-Notizen (einen *Vault* im Stil von Obsidian) und
[Claude Code](https://claude.com/claude-code). Es prüft deine Notizen, schreibt dir einen täglichen Digest, führt
geplante Routinen aus und gibt dir eine Riege nur lesender Spezialisten-Agenten hinter einem lokalen Dashboard.

Es bearbeitet deine Notizen nie (die eine Ausnahme ist die Routine `git-pull`, standardmäßig aus, die einen Vault
aktualisiert, der ein Git-Checkout ist). Agenten können lesen; sie können nicht schreiben, keine Befehle ausführen und
nichts pushen.

https://github.com/user-attachments/assets/5fcf147b-3d2e-4691-80c3-6c00accaa781

*▶ Die Tour ([herunterladen](../../media/starlane-tour.mp4)), 82 s mit Ton, auf Englisch: die Galaxie, dein Tag, die Looks,
Atlas, das Second Brain und die Kommandozeile, gemacht aus dem Code und den Bildschirmen des Dashboards selbst.*

> **Ehrlicher Hinweis.** Das ist ein persönliches Werkzeug, das öffentlich gemacht wurde, kein Framework und keine
> Produktionssoftware. Es ist Python nur mit der Standardbibliothek, für eine Person auf einem Rechner gebaut, und wird
> **so, wie es ist**, ohne Gewähr geteilt (siehe [LICENSE](../../LICENSE)). Lies [security.md](security.md), bevor du
> es auf Notizen richtest, die dir wichtig sind.

Der Befehl heißt `starlane` (die Kurzform `aos` tut dasselbe, ebenso `python -m aos`; die Anleitungen nutzen letzteres).

**Auf Deutsch umschalten:** `ui_language = "de"` unter `[user]` in `aos.toml`. Dann sind Terminal, Dashboard, Digest und
Vault-Check deutsch, und die Agenten antworten auf Deutsch. Details: [languages.md](languages.md).

## Was du bekommst

| Schicht | Was sie tut | Befehl |
|---|---|---|
| **M**emory (Gedächtnis) | Vault-Check: kaputte Links, Zwei-Schritte-Regel, Frontmatter, versehentlich abgelegte Geheimnisse | `aos mapcheck` |
| **A**gent | Spezialisten-Agenten (nur lesend) und der Koordinator Atlas, der einen Auftrag an sie verteilt | `aos agent research "..."` |
| **P**ulse (Takt) | Routinen nach Zeitplan, mit Zeitlimit, Tageslimit und Sicherung | `aos tick`, `aos status` |
| **S**creen (Bildschirm) | lokales Dashboard: Heute (ein Startbildschirm: ordne die Widgets an wie auf einem Handy, mit einer Schnellstart-Kachel für jede Ansicht und einem Regler für die Durchsicht von matt bis Liquid Glass), Agenten, Graph, Zeitleiste, Gesundheit, Kosten | `aos serve` |

Du kannst eigene Agenten anlegen (im Dashboard „Neuer Agent“, mit `aos agent-new` oder als Markdown-Datei) und eigene
Skills. Beide sind durch ihren Aufbau nur lesend.

## Schnellstart (5 Minuten)

Voraussetzungen: Python 3.11 oder neuer (prüf das mit `python3 --version`; unter macOS und Linux heißt der Befehl meist
`python3`, und manche Systeme mit Langzeit-Support liefern noch 3.10). Für Agenten und Skills außerdem die
[Claude-Code-CLI](https://claude.com/claude-code) (`claude`) auf deinem `PATH`, angemeldet. Digest, Vault-Check und
Dashboard brauchen sonst nichts.

```bash
# 0. Zuerst dieses Repository herunterladen (oder das ZIP über den grünen Knopf „Code“ auf GitHub, entpackt).
#    Jeder Ordner außer ~/starlane, den `aos setup` anlegt: deshalb der Name starlane-src.
git clone https://github.com/Nichtege/starlane.git starlane-src
cd starlane-src               # alle Schritte unten laufen in einem Terminal, das hier geöffnet ist (bis Schritt 1 dich weiterschickt)
python -m pip install .       # fügt den Befehl `aos` hinzu; keine Abhängigkeiten. macOS / Linux: python3 -m pip install .

# 1. Ein Ordner für deine Einrichtung: ~/starlane (oder der Ordner in $AOS_HOME). Überschreibt nie eine Datei.
aos setup                     # Konfiguration, Routinen, Agenten, Skills, Doku und der Demo-Vault in examples/vault
cd ~/starlane                 # arbeite von dort aus; öffne dort `claude` für die geführten Prompts

# 2. Auf Deutsch umschalten: in aos.toml unter [user] ui_language = "de" setzen (oder für diese Shell: AOS_UI_LANGUAGE=de)

# 3. Selbsttest, dann dein erster Digest und Vault-Check
aos doctor
aos digest                    # schreibt examples/vault/AI/Digest/latest.md (in diesem Ordner)

# 4. Das Dashboard: öffne den Link, den es ausgibt (http://127.0.0.1:8765/?k=..., der Schlüssel ist bei jedem Start neu)
aos serve

# 5. Dein erster Auftrag an einen Agenten (braucht die claude-CLI)
aos agent research "Welche aktiven Projekte habe ich und wann sind sie fällig?"
```

**Lieber Claude Code machen lassen?** Lade zuerst das Repository herunter (Schritt 0), öffne `claude` in diesem Ordner und füg ein:

> Installier Starlane aus diesem Ordner mit `python -m pip install .` (nimm pipx oder eine virtuelle Umgebung, wenn pip ablehnt), führ `aos setup` aus, setz in `~/starlane/aos.toml` unter `[user]` `ui_language = "de"`, dann `aos doctor` und `aos digest` aus `~/starlane`. Sag mir bei jedem Schritt, ob er geklappt hat, starte `aos serve` und gib mir den Link. Ändere nichts außerhalb dieses Ordners und `~/starlane`.

Gut zu wissen:

- **`pip` lehnt ab („externally-managed-environment“)?** Neuere Pythons von Debian, Ubuntu und Homebrew tun das. Nimm
  `pipx install .` (führ einmal `pipx ensurepath` aus, wenn `aos` danach nicht gefunden wird) oder eine virtuelle
  Umgebung (unter Debian und Ubuntu zuerst `sudo apt install python3-venv`):
  `python3 -m venv ~/.venvs/aos && ~/.venvs/aos/bin/python -m pip install .`, dann `~/.venvs/aos/bin/aos` ausführen.
- **`aos` nach der Installation nicht gefunden?** pip hat den Ordner ausgegeben, in den es `aos` gelegt hat: Füg diesen
  Ordner deinem `PATH` hinzu, oder nutz `python -m aos ...` mit demselben Python (jeder Befehl funktioniert so).
- **Du arbeitest am Code oder schaust nur?** Lass die Installation weg und starte aus dem Klon: `python -m aos doctor`
  (und die anderen Befehle, `python3 -m aos` unter macOS und Linux) nutzt die `aos.toml` in diesem Ordner. Das ist eine
  andere Einrichtung als `~/starlane`: Entscheide dich für eine und bleib dabei. Die Anleitungen schreiben Befehle als
  `python -m aos ...`; nach `pip install` heißen sie `aos ...` (und `aos next` gibt sie so aus).
- **Gefahrlos wiederholbar.** `aos setup` fügt nur fehlende Dateien hinzu und ändert nie eine vorhandene, bearbeitet oder
  nicht. Ein erneuter Lauf nach `pip install --upgrade .` kann also nichts verlieren. Aus demselben Grund aktualisiert es
  keine Dateien, die du schon hast: Um zu sehen, was eine neue Version mitbringt, führ `aos setup ~/aos-new` aus und
  vergleich.
- **Ein anderer Ordner?** `aos setup ~/irgendwo` legt die Einrichtung dort an (ein neuer oder leerer Ordner, nie dein
  Notizordner). Stell die Option dann vor den Befehl: `aos --config ~/irgendwo/aos.toml doctor`, oder setz einmal
  `AOS_HOME=~/irgendwo` für jeden Befehl.

Der Demo-Vault gehört einer erfundenen Illustratorin, die gärtnert, Spanisch lernt und ein Zine zeichnet; er ist
englisch geschrieben und spielt in der Woche 2026-W41. An einem späteren Datum meldet der Digest deshalb die
Wochennotiz der laufenden Woche als fehlend und einige Aufgaben als überfällig: Das ist die Demo, die altert, keine
kaputte Einrichtung. Seine `CLAUDE.md` nennt weitere Fragen, die er beantworten kann. Du kannst auch **Atlas** im
Dashboard öffnen und fragen.

`aos install-task` plant die Routinen (alle 5 Minuten, nur fällige Routinen laufen). Unter Windows richtet es eine
Aufgabe namens „Starlane tick“ für deinen Benutzer ein (ein Aufruf aus einem anderen Ordner ersetzt sie;
`aos uninstall-task` entfernt sie); unter macOS und Linux ändert es nichts und gibt zwei Zeilen für `crontab -e` aus. In
einem Klon unter Windows startet `start-dashboard.bat` außerdem das Dashboard, mit der eigenen Einrichtung des Klons.

### Deine eigenen Notizen nutzen

Wenn du so weit bist, richte Starlane auf deinen eigenen Ordner mit Markdown-Notizen:

- Vorhandene Notizen (ein Obsidian-Vault funktioniert so, wie er ist): Setz `[vault] path` in `aos.toml` auf diesen
  Ordner. Nutz `/` auch unter Windows; ein relativer Pfad gilt relativ zur `aos.toml`.
- Noch keine Notizen: `aos init ~/notizen` legt einen kleinen Start-Vault an (mit `ui_language = "de"` auf Deutsch),
  dann setz `[vault] path = "~/notizen"`.

Dann führ `aos doctor` noch einmal aus. Beachte, dass `aos digest` in den Vault schreibt: `latest.md`, eine tägliche
Archivkopie und `vault-check.md` kommen in seinen Digest-Ordner (`[digest] dir`, Standard `AI/Digest`; die Dateinamen
stellst du mit `[digest] file`, `archive` und `review` ein). Andere Notizen berührt es nie.

Weiter: `aos next`. Es zeigt eine Checkliste der restlichen Einrichtung (Obsidian, Routinen, dein eigener Agent, ...)
mit einem fertigen Prompt für Claude Code für jeden Schritt. Die ganze Anleitung: [getting-started.md](getting-started.md).

## Mach es zu deinem

- **Deine Einstellungen, sauber getrennt**: Schreib, was du änderst, in eine `aos.local.toml` neben der `aos.toml`, nur
  mit diesen Schlüsseln (zum Beispiel `[vault] path`, `[user] name` und `ui_language = "de"`). Sie wird Tabelle für
  Tabelle über die `aos.toml` gelegt; ein `git pull` einer neuen Starlane-Version kommt deinen Einstellungen also nie in
  die Quere, und `aos doctor` zeigt, dass sie benutzt wird.
- **Dein Name und deine Sprache**: `[user]` in `aos.toml` (`name`, `ui_language`, `language`). `ui_language` stellt die
  Oberfläche um, `language` die Sprache der Agenten (Standard: dieselbe). Siehe [languages.md](languages.md).
- **Die Struktur deines Vaults**: Nutzen deine Notizen andere Frontmatter-Schlüssel, Ordner oder Überschriften (oder
  eine andere Sprache), setz einmal `[conventions]`, statt Notizen umzubenennen. Ein fertiger Block für einen deutschen
  Vault steht in [vault-conventions.md](vault-conventions.md#beispiel-ein-deutscher-vault).
- **Deine Agenten**: [agents.md](agents.md). Der mitgelieferte Katalog (`agents.toml`) hat neun; deine kommen nach
  `agents.local.toml` und `agents/local/`, die Git ignoriert.
- **Deine Skills**: [skills.md](skills.md).
- **Dein Notion**: Ein Agent speichert Ergebnisse in Notion und ändert die Seiten, die du mit ihm teilst; Löschen braucht
  dein Ja. Einrichten mit `aos notion-connect`, siehe [notion.md](notion.md).
- **Dein Handy**: das Dashboard als App auf dem Home-Bildschirm deines iPhones oder Android-Handys, über Tailscale,
  ohne etwas ins Internet zu öffnen. Einrichten mit `aos phone`, siehe [phone.md](phone.md).

## Sicherheitsmodell

- **Nur lesende Agenten.** Werkzeuge kommen aus einer festen Positivliste: Vault (`Read`, `Grep`, `Glob`) und Web
  (`WebSearch`, `WebFetch`). Jeder Agent liest deine Notizen als Kontext; einer, der außerdem im Web sucht, braucht
  `mixed = true` und hat die feste Regel, nie Notiztext in eine Suche oder URL zu schreiben. Alles andere wird beim
  Laden der Datei abgelehnt. Die eine Ausnahme, nur wenn du sie einrichtest: Der Notion-Agent ändert die Notion-Seiten,
  die du mit ihm teilst, und löscht nichts ohne dein Ja.
- **Schreibt nie in deine Notizen.** Die einzige Stelle im Vault, an die das System schreibt, ist der Digest-Ordner
  (die Ausnahme ist die Routine `git-pull`, die du einschalten musst: Sie führt dort `git pull --rebase` aus, was
  Dateien an deinen Remote anpasst).
- **Routinen aus einer Positivliste.** `routines.toml` nennt Befehle aus einer festen Liste; sie laufen ohne Shell, mit
  Zeitlimit, Tageslimit und Sicherung. Riskante (git pull, Claude, Skills) sind standardmäßig aus.
- **Nur lokal.** Der Server lauscht auf `127.0.0.1`, verlangt ein Token pro Start, prüft Host und Origin und schickt
  eine Content Security Policy mit einer Skript-Nonce. Handy-Zugang (nur wenn du ihn einrichtest) kommt über Tailscale,
  nur von deinen eigenen Geräten.
- **Geheimnisse werden geschwärzt**, aus Aufträgen und Antworten, bevor etwas gespeichert oder gezeigt wird.

Details, Grenzen und wogegen das *nicht* schützt: [security.md](security.md).

## Aufbau

```
aos/            der Code (Python, nur Standardbibliothek); aos/web/dashboard.html ist das ganze Frontend
aos/locales/    die Sprachdateien (de.json)
agents.toml     mitgelieferter Agenten-Katalog   agents/    ihre Prompts
skills/         mitgelieferte Skills             routines.toml  der Zeitplan
aos.toml        deine Konfiguration              docs/      Anleitungen, Architektur, Sicherheit (docs/de/: deutsch)
examples/       der Demo-Vault, ein eigener Agent   tests/  unittest-Suite
```

`aos setup` legt denselben Aufbau (ohne den Code) in deinem Ordner an. Die Tests startest du aus einem Klon:
`python -m unittest discover -s tests -t .`.

Mehr: [Erste Schritte](getting-started.md) · [Agenten](agents.md) · [Skills](skills.md) · [Notion](notion.md) · [Handy](phone.md) ·
[Vault-Konventionen](vault-conventions.md) · [Sprachen](languages.md) · [Sicherheit](security.md) ·
[Auf einem Server](vps-setup.md) · auf Englisch: [Architektur](../architecture.md) · [Design](../design.md) ·
[Mitmachen](../../CONTRIBUTING.md)

## Lizenz

MIT, bereitgestellt „wie besehen“. Siehe [LICENSE](../../LICENSE).
