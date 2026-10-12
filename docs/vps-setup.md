# Running on a server (optional)

Everything works on a laptop. A small always-on server (a VPS) can run the same code with the same vault and routines, so that the morning digest arrives even while your laptop is closed. Nothing here is required; this page describes how to do it if you want it.

## When is it worth it?
When the digest should also arrive while your laptop is off, or when you want routines that run at night (for example the weekly review draft). For most people the laptop alone is enough.

## Before you start (Anthropic's terms)
Running Claude Code with **your own account** on your own server is the normal use. Routing a subscription through third-party programs (other agent harnesses) may not be allowed. Check the current terms of service yourself before you set anything up.

## Steps (Linux server, for example Ubuntu)
1. **Rent a server.** The smallest tier is enough.
2. **Make it private with Tailscale** (or another private network such as WireGuard). Install it on laptop, phone and server and sign in with the same account. After that the server is visible only to your devices. Do not open any ports to the internet.
3. **Clone the vault**: `git clone <your-vault-repository> ~/notes`. Use an access token that can only **read** if the server should only display and summarise.
4. **Copy this project to the server** (`git clone` from your own repository, or `scp`). It needs Python 3.11 or newer: check with `python3 --version`. Ubuntu 22.04 ships 3.10 (24.04 ships 3.12), so there install a newer one first (for example the deadsnakes PPA, or `uv python install 3.12`) and use that interpreter (`python3.12`, or the path `uv python find 3.12` prints) wherever this page says `python3`. Nothing else is needed: run it from the folder (`python3 -m aos doctor`).
5. **Adjust `aos.toml`**: `[vault] path = "/home/<user>/notes"`, `[machine] name = "server"` (on the laptop: `[machine] name = "my-laptop"`; without it the host name is used).
6. **Distribute the routines** in `routines.toml`: for example `machine = "server"` for the morning digest (it arrives even when the laptop is closed) and `machine = "my-laptop"` for everything that only makes sense there. Switch `git-pull` on for the server (`enabled = true`) so that it always has your current state.
7. **Schedule**: run `python3 -m aos install-task`. On Linux and macOS it changes nothing and prints two lines; add them with `crontab -e`. They look like this (your paths, your `python3`):
   ```
   PATH=/home/<user>/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
   */5 * * * * cd /home/<user>/agentic-os && mkdir -p /home/<user>/agentic-os/data && PYTHONPATH=/home/<user>/agentic-os /usr/bin/python3 -P -m aos --config /home/<user>/agentic-os/aos.toml tick --quiet >> /home/<user>/agentic-os/data/tick.log 2>&1
   ```
   The first line matters: cron starts with a bare `PATH=/usr/bin:/bin`, so without it routines that call Claude would not find `claude`. When `claude` is found, the line starts with its folder. If your crontab already has a `PATH=` line, merge the folders into it. Afterwards `python3 -m aos doctor` shows whether the line is installed. On macOS, cron may need Full Disk Access (System Settings > Privacy & Security) before it can read a vault in Documents, Desktop, Downloads, iCloud Drive or on a removable or network volume; a vault elsewhere in your home folder does not.
8. **Dashboard from another device**: on the server run `python3 -m aos serve --no-browser`. It prints a link `http://127.0.0.1:8765/?k=<key>`; the key changes on every start. The server deliberately listens only locally and accepts only the `Host` header `127.0.0.1:<port>` or `localhost:<port>`, so access has to come through an **SSH tunnel to the same local port number**:
   ```
   ssh -N -L 8765:127.0.0.1:8765 <user>@<server>
   ```
   Then open the printed link (`http://127.0.0.1:8765/?k=<key>`) on the device that runs the tunnel. A different local port (`-L 9000:127.0.0.1:8765`) does not work: the browser would send `Host: 127.0.0.1:9000` and the server refuses it. On a phone, use an SSH app that supports local port forwarding with the same rule. **Tailscale Serve and other reverse proxies are not supported**: they forward a different `Host` header (your tailnet name), which the server rejects on purpose (protection against DNS rebinding).

## Locking down Claude Code on the server
If you run Claude Code there (for example for the weekly review), create **one** settings file that blocks everything that sends. Example `~/.claude/settings.json` on the server:
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
If you have connectors installed (mail, chat, cloud drives), add their send, reply, forward and delete tools to the same `deny` list. Then the worst the server can do is leave you a draft, never send one.

Agent, skill and routine runs read these user-level settings too. The line `"WebFetch", "WebSearch"` therefore switches off the **web agents** (`assistant`, `data-analyst`, `coder`, `tutor` and your own web agents) on this server: their runs fail. Keep that line if the server should never reach the web; remove it if you want web agents there. Do not add `allow` rules or hooks to this file: they would apply to every run as well (see [security.md](security.md)).

## Synchronisation
The simplest safe option: **Git as the single source of truth**. The laptop pushes (for example with the Obsidian Git plugin), the server pulls with `git-pull` every 10 minutes. Apart from `git pull` itself (which updates the vault files to your remote's state), the server **writes** into the vault only in the digest folder (`AI/Digest/` by default); to avoid conflicts, either the laptop or the server writes the digest, not both (pin the routine with `machine = ...`).

### Alternative: Syncthing (if the server should also produce files you want on the laptop)
For this system Git is enough, because the server only reads. Syncthing (free, open source) is worth it only when both sides create files, for example `data/artifacts/` with HTML results you want to see on the laptop:
1. Install Syncthing on laptop and server and pair the two devices.
2. Share **only** these folders: `skills/` and `data/artifacts/`. Never `data/` as a whole (state and logs belong to one machine each) and never `.git`.
3. On the server, `aos serve` stays local as above. Skill routines with `machine = "server"` then put their results into the dashboard (Artifacts).

## Not included
Voice input through a chat bot (speech to text forwarded to Claude) would need a bot token and a speech recognition service. It is deliberately not part of this project.
