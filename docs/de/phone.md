# Das Dashboard auf dem Handy

Starlane läuft auch als App auf deinem iPhone oder Android-Handy: ein Symbol auf dem Home-Bildschirm, das das Dashboard in einem eigenen Fenster öffnet, zu Hause und unterwegs. Aus einem App Store kommt nur Tailscale, und nichts von dir läuft über einen Cloud-Dienst:

- Starlane läuft weiter auf **deinem Rechner**: deinem PC oder Laptop, oder einem Rechner zu Hause, der immer an ist (ein alter Laptop, ein Mini-PC, ein Raspberry Pi). Das Handy ist nur ein Bildschirm dafür.
- **Tailscale** (für private Nutzung kostenlos) verbindet dein Handy direkt mit diesem Rechner, Ende zu Ende verschlüsselt. Nur deine eigenen Geräte erreichen die Adresse; sie steht nie im Internet.
- Der Dashboard-Server lauscht weiter nur auf `127.0.0.1`. Tailscale reicht ihm die Anfragen des Handys auf diesem Rechner weiter.

Rechne mit etwa 15 Minuten. Du brauchst den Rechner, auf dem Starlane schon läuft (`python -m aos doctor` ist sauber und `python -m aos serve` zeigt das Dashboard), und dein Handy.

## Welcher Rechner führt es aus?

| | Dein PC oder Laptop | Ein Rechner zu Hause, der immer läuft |
|---|---|---|
| Funktioniert, wenn | der PC an und wach ist und `aos serve` läuft | immer |
| Zusätzliche Einrichtung | keine | Starlane, Claude Code und dein Vault auf diesem Rechner ([unten](#ein-rechner-zu-hause-der-immer-läuft)) |
| Gut für | zum Ausprobieren, wenn der PC sowieso an ist | von überall, jederzeit, Routinen in der Nacht |

Fang mit deinem PC an. Auf einen Rechner, der immer läuft, kannst du später umziehen; die Schritte auf dem Handy bleiben gleich.

## Schritt 1: Tailscale auf dem Rechner

1. Lade Tailscale von https://tailscale.com/download herunter und installier es.
   - Linux (Ubuntu, Debian, Raspberry Pi OS): `curl -fsSL https://tailscale.com/install.sh | sh`, dann `sudo tailscale up`.
2. Melde dich an (mit Google, Microsoft, Apple oder GitHub). Deine Geräte bilden dein privates Netz, das *Tailnet*.
3. Schalte HTTPS für dein Tailnet ein (einmal): Öffne https://login.tailscale.com/admin/dns, prüf, dass **MagicDNS** an ist, und klick unter *HTTPS Certificates* auf **Enable HTTPS**. Ohne das kann das Handy die Adresse nicht öffnen.

## Schritt 2: Tailscale auf dem Handy

1. Installier die App **Tailscale**: App Store (iPhone) oder Google Play (Android).
2. Öffne sie und melde dich mit **demselben Konto** an wie auf dem Rechner.
3. Erlaub die VPN-Konfiguration, wenn das Handy fragt. Der Schalter in der App muss an sein, wann immer du Starlane auf dem Handy benutzt.

## Schritt 3: Das Handy koppeln

Führ auf dem Rechner in deinem Starlane-Ordner (dort, wo `aos.toml` liegt) aus:

```
python -m aos phone
```

Es fragt Tailscale nach dem Namen dieses Rechners (etwa `laptop.tail1234.ts.net`), erzeugt einen Handy-Schlüssel und gibt aus, was noch fehlt, den Handy-Link und einen QR-Code.

Beim ersten Mal bittet es dich, Tailscale an das Dashboard weiterleiten zu lassen. Führ den Befehl, den es ausgibt, einmal aus:

```
tailscale serve --bg 8765
```

- Unter Linux: `sudo tailscale serve --bg 8765`.
- Antwortet Tailscale mit einem Link, um HTTPS einzuschalten, öffne ihn, bestätige und führ den Befehl noch einmal aus.
- `--bg` behält die Einstellung über Neustarts des Rechners. `8765` ist der Port des Dashboards; hast du `[server] port` in `aos.toml` geändert, nimm diese Zahl.
- **Nimm nie `tailscale funnel`.** Funnel würde das Dashboard im Internet veröffentlichen. `serve` hält es in deinem Tailnet.

Führ dann `python -m aos phone` noch einmal aus: Schritt 1 der Liste sagt jetzt *erledigt*.

## Schritt 4: Das Dashboard starten

```
python -m aos serve
```

(oder unter Windows `start-dashboard.bat` doppelklicken). Es gibt wie immer den lokalen Link aus, dazu eine Zeile `Handy: https://<name>/`. Lass es laufen. Wie es von selbst startet, steht unter [Am Laufen halten](#am-laufen-halten).

## Schritt 5: Auf dem Handy öffnen und auf den Home-Bildschirm legen

1. Prüf, dass der Tailscale-Schalter auf dem Handy an ist.
2. Halt die Kamera des Handys auf den QR-Code im Terminal und tipp auf den Link, der erscheint. Das Dashboard öffnet sich. Der allererste Aufruf kann bis zu einer Minute dauern, während Tailscale das HTTPS-Zertifikat holt.
   - Kein QR-Code zur Hand (etwa im Terminal eines Rechners, den du über SSH erreichst)? Tipp den Link darunter von Hand ab.
3. Leg es auf den Home-Bildschirm:
   - **iPhone**: Der Link muss in **Safari** offen sein. Tipp auf die Teilen-Taste (das Quadrat mit dem Pfeil), scroll nach unten, tipp auf **Zum Home-Bildschirm**, dann auf **Hinzufügen**.
   - **Android**: In **Chrome** tipp auf das Menü (drei Punkte), dann auf **App installieren** (auf manchen Handys **Zum Startbildschirm hinzufügen**), dann auf **Installieren**.
4. Ab jetzt tippst du auf das Symbol **Starlane**. Es öffnet sich ohne Adressleiste und bleibt angemeldet, auch nach einem Neustart des Rechners.

Für ein weiteres Handy oder ein Tablet führ `python -m aos phone` noch einmal aus und scann denselben Code.

## Am Laufen halten

Das Handy erreicht Starlane nur, solange der Rechner an und wach ist, mit Tailscale verbunden ist und `aos serve` läuft.

### Windows
- **Energiesparmodus**: Einstellungen > System > Energie (oder Netzbetrieb und Akku) > Bildschirm und Energiesparmodus: stell den Energiesparmodus für *Netzbetrieb* auf **Nie**.
- **Das Dashboard bei der Anmeldung starten**:
  1. Drück Win+R, tipp `shell:startup` ein, drück Enter. Ein Ordner öffnet sich.
  2. Rechtsklick darin > Neu > Verknüpfung. Als Speicherort gib `pythonw -m aos serve --no-browser` ein, klick Weiter, nenn sie `Starlane-Dashboard`, Fertig stellen.
  3. Rechtsklick auf die neue Verknüpfung > Eigenschaften. Unter **Ausführen in** trag deinen Starlane-Ordner ein (den mit `aos.toml`, zum Beispiel `C:\Users\<du>\starlane`). OK.
  4. Doppelklick einmal auf die Verknüpfung, um es jetzt zu starten. Es läuft ohne Fenster; `data/server.log` hält fest, wann es startete und stoppte. Zum Beenden beende `pythonw.exe` im Task-Manager.
- Tailscale startet mit Windows von selbst.

### macOS
Lass ein Terminal-Fenster mit `caffeinate -s python3 -m aos serve --no-browser` offen: `caffeinate -s` hält den Mac wach, solange es läuft (am Netzteil).

### Linux (und der Rechner, der immer läuft)
Ein Benutzer-Dienst startet das Dashboard beim Hochfahren und startet es neu, wenn es stoppt. In deinem Starlane-Ordner:

```
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/starlane.service <<EOF
[Unit]
Description=Starlane dashboard

[Service]
WorkingDirectory=$PWD
ExecStart=$(command -v python3) -m aos serve --no-browser
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Restart=on-failure

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now starlane
sudo loginctl enable-linger $USER
```

- `$PWD` und `$(command -v python3)` werden beim Einfügen ausgefüllt: Führ es im Starlane-Ordner aus, mit dem `python3`, das Starlane ausführt (3.11 oder neuer; unter Ubuntu 22.04 nimm den neueren Interpreter aus [vps-setup.md](vps-setup.md)).
- Die Zeile `PATH` lässt Agenten `claude` finden (meist in `~/.local/bin`). Gibt `command -v claude` einen anderen Ordner aus, setz diesen nach vorn.
- `enable-linger` hält es am Laufen, auch wenn du nicht angemeldet bist.
- Prüfen: `systemctl --user status starlane`. Log: `journalctl --user -u starlane`.

## Ein Rechner zu Hause, der immer läuft

Jeder Rechner, der an bleibt, geht: ein alter Laptop mit zugeklapptem Deckel (stell ihn so ein, dass er nicht schläft), ein Mini-PC, ein Raspberry Pi 4 oder 5 mit Raspberry Pi OS oder Ubuntu. Er braucht seine eigene Kopie von Starlane, Claude Code und deinem Vault:

1. Installier dort Python 3.11 oder neuer, Starlane und Claude Code und melde dich bei Claude Code an (`claude`, dann `/login`). Folge den Schritten für einen Server in [vps-setup.md](vps-setup.md) (Schritte 3 bis 7): Der Vault kommt per Git hinüber, Routinen werden mit `machine = ...` auf die Rechner verteilt, und der Planer läuft über cron. Die Anleitung ist für einen gemieteten Server geschrieben; zu Hause ist es dasselbe, nur ohne Miete.
2. Sichere Claude Code dort ab wie in [vps-setup.md, Claude Code auf dem Server absichern](vps-setup.md#claude-code-auf-dem-server-absichern).
3. Schritte 1, 3 und 4 dieser Seite auf diesem Rechner, dazu der [Linux-Dienst](#linux-und-der-rechner-der-immer-läuft), damit das Dashboard ohne dich läuft.
4. Auf dem Handy: Scann den Code von diesem Rechner. Hattest du vorher deinen PC gekoppelt, hat das Handy jetzt zwei Symbole; lösch das alte (gedrückt halten).

Dein PC muss für das Handy dann kein `aos serve` mehr ausführen. Auf dem PC kannst du das Dashboard trotzdem über dieselbe Adresse öffnen: mit Tailscale auf dem PC den Handy-Link in seinem Browser öffnen.

## Im Alltag
- **„Server nicht erreichbar“ in der App**: Der Rechner ist aus oder schläft, `aos serve` läuft nicht, oder Tailscale ist auf dem Handy oder dem Rechner aus.
- **Nach einem Neustart von `aos serve`** lädt sich die App einmal neu und macht weiter.
- **Das Handy kann alles, was das Dashboard kann**: Agenten Aufträge geben, Routinen starten, Notion-Löschungen freigeben. Behandle es wie einen entsperrten Laptop.
- `python -m aos phone` gibt den Code jederzeit wieder aus. Es behält den Schlüssel, gekoppelte Handys funktionieren also weiter.

## Handy verloren, oder ausschalten
- **Handy verloren oder verkauft**: Führ `python -m aos phone --new-key` aus. Der alte Schlüssel gilt sofort nicht mehr (kein Neustart nötig); scann den neuen Code auf den Handys, die du noch hast. Entfern das verlorene Gerät außerdem in der Tailscale-Verwaltung (https://login.tailscale.com/admin/machines).
- **Handy-Zugang ausschalten**: `python -m aos phone --off`, dann `tailscale serve --https=443 off`, damit auch Tailscale nicht mehr weiterleitet.

## Wenn etwas nicht klappt
| Was du siehst | Warum, und was zu tun ist |
|---|---|
| Die Seite lädt gar nicht | Tailscale ist auf dem Handy oder dem Rechner aus, der Rechner schläft, oder `aos serve` läuft nicht. Auf dem Rechner sollte `tailscale serve status` `http://127.0.0.1:8765` zeigen. |
| Eine Zertifikatswarnung | HTTPS ist für das Tailnet nicht eingeschaltet (Schritt 1.3), oder das Zertifikat wird noch ausgestellt: eine Minute warten und neu laden. |
| `{"ok": false, "error": "Host nicht erlaubt"}` | Handy-Zugang ist auf diesem Rechner nicht eingerichtet, oder sein Tailscale-Name hat sich geändert. Führ `python -m aos phone` noch einmal aus und scann den neuen Code. |
| *Diese Adresse braucht den Link, den aos serve ausgegeben hat* | Der Schlüssel in der Adresse ist alt (nach `--new-key`) oder vertippt. Scann den Code aus `python -m aos phone` noch einmal. |
| Das Symbol öffnet einen normalen Browser-Tab | Es wurde aus einem anderen Browser als Safari (iPhone) oder Chrome (Android) hinzugefügt. Lösch es und füg es aus Safari oder Chrome neu hinzu. |
| Der Port ist nicht 8765 | `tailscale serve --bg <port>` muss denselben Port nehmen wie `aos serve` (`[server] port` in `aos.toml`, oder `--port`). |

## Wie es geschützt ist
- Der Server bindet weiter nur an `127.0.0.1`. Das Handy erreicht ihn nur über `tailscale serve` auf demselben Rechner, und nur von Geräten, die in deinem Tailnet angemeldet sind.
- Die Handy-Adresse funktioniert erst nach `python -m aos phone`: bis dahin lehnt der Server den Tailscale-Namen ab wie jeden anderen unbekannten Host. Der Name steht mit dem Handy-Schlüssel in `data/phone.json` auf diesem Rechner.
- Unter der Handy-Adresse braucht die Dashboard-Seite den **Handy-Schlüssel** (256 Bit, zufällig). Anders als der Startschlüssel überlebt er Neustarts, damit das Symbol weiter funktioniert; `--new-key` und `--off` widerrufen ihn sofort. Jeder API-Aufruf braucht weiter das Token des aktuellen Serverstarts, das in der Seite steckt.
- Der Handy-Schlüssel öffnet unter `127.0.0.1` nichts, und die Regeln des Startschlüssels dort bleiben gleich.
- Die Server von Tailscale koordinieren nur, welche deiner Geräte miteinander reden dürfen; der Verkehr selbst läuft direkt und verschlüsselt zwischen deinen Geräten. Teilst du dein Tailnet mit anderen Menschen, erreichen sie die Adresse auch, aber nicht ohne den Schlüssel.
- Einzelheiten: [security.md](security.md#dashboard-server-aos-serve).
