# The dashboard on your phone

Starlane can run as an app on your iPhone or Android phone: an icon on the home screen that opens the dashboard in its own window, at home and on the road. Nothing is installed from an app store except Tailscale, and nothing of yours goes through a cloud service:

- Starlane keeps running on **your computer**: your PC or laptop, or a machine at home that is always on (an old laptop, a mini PC, a Raspberry Pi). The phone is only a screen for it.
- **Tailscale** (free for personal use) connects your phone and that computer directly, encrypted end to end. Only your own devices can reach the address; it is never on the internet.
- The dashboard server keeps listening on `127.0.0.1` only. Tailscale hands it the phone's requests on that computer.

Plan about 15 minutes. You need the computer with Starlane already working (`python -m aos doctor` is clean and `python -m aos serve` shows the dashboard), and your phone.

## Which computer runs it?

| | Your PC or laptop | An always-on machine at home |
|---|---|---|
| Works when | the PC is on, awake and `aos serve` runs | always |
| Extra setup | none | Starlane, Claude Code and your vault on that machine ([below](#an-always-on-machine-at-home)) |
| Good for | trying it out, using it while the PC is on anyway | using it from anywhere at any time, routines at night |

Start with your PC. You can move to an always-on machine later; the steps on the phone stay the same.

## Step 1: Tailscale on the computer

1. Download Tailscale from https://tailscale.com/download and install it.
   - Linux (Ubuntu, Debian, Raspberry Pi OS): `curl -fsSL https://tailscale.com/install.sh | sh`, then `sudo tailscale up`.
2. Sign in (with Google, Microsoft, Apple or GitHub). Your devices form your private network, called a *tailnet*.
3. Switch on HTTPS for your tailnet (once): open https://login.tailscale.com/admin/dns, check that **MagicDNS** is on, and click **Enable HTTPS** under *HTTPS Certificates*. Without it the phone cannot open the address.

## Step 2: Tailscale on the phone

1. Install the **Tailscale** app: App Store (iPhone) or Google Play (Android).
2. Open it and sign in with **the same account** as on the computer.
3. Allow the VPN configuration when the phone asks. The switch in the app has to be on whenever you use Starlane on the phone.

## Step 3: Pair the phone

On the computer, in your Starlane folder (where `aos.toml` is), run:

```
python -m aos phone
```

It asks Tailscale for this computer's name (something like `laptop.tail1234.ts.net`), creates a phone key and prints what is still missing, the phone link and a QR code.

The first time it asks you to let Tailscale forward to the dashboard. Run the command it prints, once:

```
tailscale serve --bg 8765
```

- On Linux: `sudo tailscale serve --bg 8765`.
- If Tailscale answers with a link to enable HTTPS, open it, confirm, and run the command again.
- `--bg` keeps the setting across restarts of the computer. `8765` is the dashboard's port; if you changed `[server] port` in `aos.toml`, use that number.
- **Never use `tailscale funnel`.** Funnel would publish the dashboard on the internet. `serve` keeps it inside your tailnet.

Then run `python -m aos phone` again: step 1 of its list now says *done*.

## Step 4: Start the dashboard

```
python -m aos serve
```

(or double-click `start-dashboard.bat` on Windows). It prints the local link as always, plus a line `Phone: https://<name>/`. Leave it running. To have it start by itself, see [Keep it running](#keep-it-running).

## Step 5: Open it on the phone and add it to the home screen

1. Make sure the Tailscale switch on the phone is on.
2. Point the phone's camera at the QR code in the terminal and tap the link that appears. The dashboard opens. The very first visit can take up to a minute while Tailscale gets the HTTPS certificate.
   - No QR code in sight (for example the terminal of a machine you reach over SSH)? Type the link printed under it by hand.
3. Put it on the home screen:
   - **iPhone**: the link has to be open in **Safari**. Tap the share button (the square with the arrow), scroll down, tap **Add to Home Screen**, then **Add**.
   - **Android**: in **Chrome**, tap the menu (three dots), then **Install app** (on some phones **Add to Home screen**), then **Install**.
4. From now on, tap the **Starlane** icon. It opens without the browser's address bar and stays signed in, also after the computer restarts.

To pair another phone or a tablet, run `python -m aos phone` again and scan the same code.

## Keep it running

The phone can only reach Starlane while the computer is on, awake, connected to Tailscale, and `aos serve` runs.

### Windows
- **Sleep**: Settings > System > Power & battery > Screen, sleep & hibernate timeouts: set the sleep timeout for *plugged in* to **Never**.
- **Start the dashboard when you log in**:
  1. Press Win+R, type `shell:startup`, press Enter. A folder opens.
  2. Right-click in it > New > Shortcut. As the location enter `pythonw -m aos serve --no-browser`, click Next, name it `Starlane dashboard`, Finish.
  3. Right-click the new shortcut > Properties. In **Start in**, enter your Starlane folder (the one with `aos.toml`, for example `C:\Users\<you>\starlane`). OK.
  4. Double-click the shortcut once to start it now. It runs without a window; `data/server.log` notes when it started and stopped. To stop it, end `pythonw.exe` in the Task Manager.
- Tailscale starts with Windows by itself.

### macOS
Keep a Terminal window open with `caffeinate -s python3 -m aos serve --no-browser`: `caffeinate -s` keeps the Mac awake while it runs (on power).

### Linux (and the always-on machine)
A user service starts the dashboard at boot and restarts it if it stops. In your Starlane folder:

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

- `$PWD` and `$(command -v python3)` are filled in when you paste it: run it from the Starlane folder, with the `python3` that runs Starlane (3.11 or newer; on Ubuntu 22.04 use the newer interpreter from [vps-setup.md](vps-setup.md)).
- The `PATH` line lets agents find `claude` (usually in `~/.local/bin`). If `command -v claude` prints another folder, put that one first.
- `enable-linger` keeps it running when you are not logged in.
- Check: `systemctl --user status starlane`. Log: `journalctl --user -u starlane`.

## An always-on machine at home

Any computer that stays on works: an old laptop with the lid closed (set it not to sleep), a mini PC, a Raspberry Pi 4 or 5 with Raspberry Pi OS or Ubuntu. It needs its own copy of Starlane, Claude Code and your vault:

1. Install Python 3.11 or newer, Starlane and Claude Code there and sign in to Claude Code (`claude`, then `/login`). Follow the steps for a server in [vps-setup.md](vps-setup.md) (steps 3 to 7): the vault comes over with Git, routines are split between the machines with `machine = ...`, and the scheduler runs from cron. That guide was written for a rented server; at home it is the same, minus renting.
2. Lock down Claude Code on it as in [vps-setup.md, Locking down Claude Code](vps-setup.md#locking-down-claude-code-on-the-server).
3. Steps 1, 3 and 4 of this page on that machine, and the [Linux service](#linux-and-the-always-on-machine) so the dashboard runs without you.
4. On the phone: scan the code from that machine. If you had paired your PC before, the phone now has two icons; delete the old one (press and hold it).

Your PC no longer needs to run `aos serve` for the phone. You can still open the dashboard on the PC through the same address: with Tailscale on the PC, open the phone link in its browser.

## Everyday use
- **"Server unreachable" in the app**: the computer is off or asleep, `aos serve` is not running, or Tailscale is off on the phone or the computer.
- **After a restart of `aos serve`** the app reloads itself once and carries on.
- **The phone can do everything the dashboard can**: give agents tasks, start routines, approve Notion deletions. Treat it like an unlocked laptop.
- `python -m aos phone` prints the code again at any time. It keeps the key, so phones that are already paired keep working.

## Lost phone, or switching it off
- **Lost or sold a phone**: run `python -m aos phone --new-key`. The old key stops working at once (no restart needed); scan the new code on the phones you still have. Also remove the lost device in the Tailscale admin console (https://login.tailscale.com/admin/machines).
- **Switch phone access off**: `python -m aos phone --off`, then `tailscale serve --https=443 off` so Tailscale stops forwarding as well.

## When something goes wrong
| What you see | Why, and what to do |
|---|---|
| The page does not load at all | Tailscale is off on the phone or the computer, the computer sleeps, or `aos serve` is not running. On the computer, `tailscale serve status` should list `http://127.0.0.1:8765`. |
| A certificate warning | HTTPS is not enabled for the tailnet (step 1.3), or the certificate is still being issued: wait a minute and reload. |
| `{"ok": false, "error": "Host not allowed"}` | Phone access is not set up on this computer, or its Tailscale name changed. Run `python -m aos phone` again and scan the new code. |
| *This address needs the link that aos serve printed* | The key in the address is old (after `--new-key`) or mistyped. Scan the code from `python -m aos phone` again. |
| The icon opens a normal browser tab | It was added from a browser other than Safari (iPhone) or Chrome (Android). Delete it and add it again from Safari or Chrome. |
| The port is not 8765 | `tailscale serve --bg <port>` must use the same port as `aos serve` (`[server] port` in `aos.toml`, or `--port`). |

## How it is protected
- The server still binds to `127.0.0.1` only. The phone reaches it only through `tailscale serve` on the same computer, and only from devices signed in to your tailnet.
- The phone address works only after `python -m aos phone`: until then the server refuses the Tailscale name like any other unknown host. The name comes from `data/phone.json` on this machine, together with the phone key.
- Under the phone address the dashboard page needs the **phone key** (256 bits, random). Unlike the launch key it survives restarts, so the icon keeps working; `--new-key` and `--off` revoke it at once. Every API call still needs the token of the current server start, embedded in the page.
- The phone key opens nothing on `127.0.0.1`, and the launch key's rules there are unchanged.
- Tailscale's servers only coordinate which of your devices may talk to each other; the traffic itself goes directly between your devices, encrypted. If you share your tailnet with other people, they could reach the address too, but not without the key.
- Details: [security.md](security.md#dashboard-server-aos-serve).
