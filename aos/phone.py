"""Phone access (`aos phone`): the dashboard on your phone through Tailscale, as an app on the home screen.

The server keeps listening on 127.0.0.1 only. `tailscale serve` forwards https://<machine>.<tailnet>.ts.net (reachable
only from your own Tailscale devices) to it, and this module pairs a phone:
- data/phone.json holds the machine's Tailscale name and a phone key. The server accepts that name as Host (and
  https://<name> as Origin), and the dashboard page under that name needs the phone key instead of the launch key.
  Unlike the launch key it survives a restart, so the icon on the home screen keeps working. `aos phone --new-key`
  replaces it, `aos phone --off` deletes it; the server reads the file on every request, so both apply at once.
- `aos phone` prints the phone link as a QR code (stdlib encoder below) to scan with the phone's camera.
- The home-screen icon is drawn here as a PNG (no image file ships).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import struct
import subprocess
import sys
import zlib
from functools import lru_cache
from pathlib import Path

from .agents import safe_which
from .config import Config, aos_cmd
from .i18n import tr
from .scheduler import atomic_write

HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
ICON_SIZES = (180, 192, 512)  # 180: iPhone (apple-touch-icon), 192 and 512: Android
# Where the installers put the CLI when it is not on the PATH
TAILSCALE_PATHS = (r"C:\Program Files\Tailscale\tailscale.exe", "/Applications/Tailscale.app/Contents/MacOS/Tailscale")


def phone_file(cfg: Config) -> Path:
    return cfg.data_dir / "phone.json"


def load(cfg: Config) -> dict | None:
    """{"host": ..., "key": ...} when a phone is paired and the file is well-formed, else None."""
    try:
        rec = json.loads(phone_file(cfg).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(rec, dict):
        return None
    host, key = rec.get("host"), rec.get("key")
    if not (isinstance(host, str) and HOST_RE.match(host) and isinstance(key, str) and KEY_RE.match(key)):
        return None
    return {"host": host, "key": key}


def save(cfg: Config, host: str, key: str) -> None:
    path = phone_file(cfg)
    atomic_write(path, json.dumps({"host": host, "key": key}) + "\n")
    try:
        os.chmod(path, 0o600)  # POSIX: only you; Windows keeps the profile folder's rights
    except OSError:
        pass


def link(rec: dict) -> str:
    return f"https://{rec['host']}/?k={rec['key']}"


# --- Tailscale ---------------------------------------------------------------------------
def tailscale_exe() -> str | None:
    return safe_which("tailscale") or next((p for p in TAILSCALE_PATHS if Path(p).is_file()), None)


def _tailscale(*args: str) -> str | None:
    exe = tailscale_exe()
    if not exe:
        return None
    try:
        proc = subprocess.run([exe, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def tailscale_name() -> str | None:
    """This machine's name in your tailnet (laptop.tail1234.ts.net), or None (no Tailscale, or not signed in)."""
    try:
        status = json.loads(_tailscale("status", "--json") or "")
    except ValueError:
        return None
    name = str(((status or {}).get("Self") or {}).get("DNSName") or "").rstrip(".").lower()
    return name if HOST_RE.match(name) else None


def serve_forwards(port: int) -> bool | None:
    """Does `tailscale serve` forward to the dashboard's port? None: Tailscale could not be asked."""
    out = _tailscale("serve", "status", "--json")
    if out is None:
        return None
    return f"127.0.0.1:{port}" in out or f"localhost:{port}" in out


# --- `aos phone` --------------------------------------------------------------------------
def setup(cfg: Config, host: str | None = None, new_key: bool = False, off: bool = False) -> int:
    port = cfg.server_port
    if off:
        try:
            phone_file(cfg).unlink()
        except FileNotFoundError:
            pass
        print(tr("Phone access is off: the phone link no longer opens the dashboard."))
        print(tr("Tailscale still forwards to this machine; stop that too with:  tailscale serve --https=443 off"))
        return 0
    if host is None and tailscale_exe() is None:
        print(tr("Tailscale is not installed. Install it from https://tailscale.com/download, sign in, then run this again."))
        print(tr("docs/phone.md walks through every step."))
        return 1
    name = (host or tailscale_name() or "").strip().rstrip(".").lower()
    if not HOST_RE.match(name):
        print(tr("This machine has no Tailscale name yet: open Tailscale, sign in, then run this again") + " "
              + (tr("(not a host name: {host})", host=repr(host)) if host else tr("(or pass --host <machine>.<tailnet>.ts.net)")) + ".")
        return 1
    old = load(cfg)
    key = old["key"] if old and not new_key else secrets.token_urlsafe(32)
    rec = {"host": name, "key": key}
    save(cfg, name, key)
    print(tr("Phone access for {host} (new key: every phone has to scan again).", host=name) if old and new_key
          else tr("Phone access for {host}.", host=name))
    print()
    forwards = serve_forwards(port)
    if not forwards:
        print(tr("1. Let Tailscale forward to the dashboard (once; it stays set across restarts):"))
        print(f"     tailscale serve --bg {port}")
        if forwards is None:
            print(tr("   (Tailscale could not be asked whether that is already set up.)"))
    else:
        print(tr("1. Tailscale forwards https://{host} to port {port}: done.", host=name, port=port))
    print(aos_cmd(tr("2. Keep the dashboard running: python -m aos serve --no-browser (docs/phone.md: start it automatically).")))
    print(tr("3. On the phone: Tailscale on, then scan this code with the camera:"))
    print()
    print(qr_terminal(link(rec)))
    print()
    print(tr("   or type the link:") + "  " + link(rec))
    print(tr("4. Add it to the home screen: iPhone: Share > Add to Home Screen. Android: menu > Install app (or Add to Home screen)."))
    print()
    print(aos_cmd(tr("Anyone with this link and access to your tailnet can use the dashboard. Never send it through a chat or by mail. "
                     "Lost a phone? `python -m aos phone --new-key`; switch off: `python -m aos phone --off`.")))
    return 0


# --- QR code (ISO/IEC 18004: byte mode, error correction level M, versions 1 to 10) ----------------------------
# Follows Project Nayuki's reference encoder. A phone link is about 90 characters (version 6).
ECC_M_CODEWORDS = (10, 16, 26, 18, 24, 16, 18, 22, 22, 26)  # error correction codewords per block, versions 1..10
ECC_M_BLOCKS = (1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
MASK = 0  # ponytail: one fixed mask (valid by the standard); scoring all eight helps only with hard-to-read print


def _raw_modules(ver: int) -> int:
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - ECC_M_CODEWORDS[ver - 1] * ECC_M_BLOCKS[ver - 1]


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _codewords(data: bytes, ver: int) -> list[int]:
    """Data with mode, length, terminator and padding, split into blocks, error correction added, interleaved."""
    bits: list[int] = []
    put = lambda val, n: bits.extend((val >> i) & 1 for i in reversed(range(n)))  # noqa: E731
    put(0b0100, 4)
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    cap = _data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))
    put(0, -len(bits) % 8)
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < cap // 8:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    nblocks, ecclen = ECC_M_BLOCKS[ver - 1], ECC_M_CODEWORDS[ver - 1]
    raw = _raw_modules(ver) // 8
    nshort, shortlen = nblocks - raw % nblocks, raw // nblocks
    divisor = _rs_divisor(ecclen)
    blocks, k = [], 0
    for i in range(nblocks):
        dat = words[k:k + shortlen - ecclen + (0 if i < nshort else 1)]
        k += len(dat)
        ecc = _rs_remainder(dat, divisor)
        if i < nshort:
            dat.append(0)  # placeholder, skipped when interleaving
        blocks.append(dat + ecc)
    return [blk[i] for i in range(len(blocks[0])) for j, blk in enumerate(blocks)
            if i != shortlen - ecclen or j >= nshort]


def qr_matrix(text: str) -> list[list[bool]]:
    """The QR code of `text` as rows of modules (True = dark), without the quiet zone."""
    data = text.encode("utf-8")
    ver = next((v for v in range(1, 11) if len(data) + 2 + (v >= 10) <= _data_codewords(v)), None)
    if ver is None:
        raise ValueError("text too long for a QR code up to version 10")
    size = ver * 4 + 17
    mods = [[False] * size for _ in range(size)]
    func = [[False] * size for _ in range(size)]

    def setf(x: int, y: int, dark: bool) -> None:
        mods[y][x], func[y][x] = dark, True

    for i in range(size):  # timing patterns
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)
    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):  # finder patterns with their separators
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                if 0 <= cx + dx < size and 0 <= cy + dy < size:
                    setf(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
    if ver > 1:  # alignment patterns
        n = ver // 7 + 2
        step = (ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
        pos = sorted([size - 7 - i * step for i in range(n - 1)] + [6])
        for i, px in enumerate(pos):
            for j, py in enumerate(pos):
                if (i, j) in ((0, 0), (0, n - 1), (n - 1, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        setf(px + dx, py + dy, max(abs(dx), abs(dy)) != 1)
    # format bits (level M = 0b00, then the mask) with their BCH code
    fmt = MASK
    rem = fmt
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    fbits = ((fmt << 10) | rem) ^ 0x5412
    bit = lambda v, i: (v >> i) & 1 == 1  # noqa: E731
    for i in range(6):
        setf(8, i, bit(fbits, i))
    setf(8, 7, bit(fbits, 6))
    setf(8, 8, bit(fbits, 7))
    setf(7, 8, bit(fbits, 8))
    for i in range(9, 15):
        setf(14 - i, 8, bit(fbits, i))
    for i in range(8):
        setf(size - 1 - i, 8, bit(fbits, i))
    for i in range(8, 15):
        setf(8, size - 15 + i, bit(fbits, i))
    setf(8, size - 8, True)  # the dark module
    if ver >= 7:  # version information
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        vbits = (ver << 12) | rem
        for i in range(18):
            a, b = size - 11 + i % 3, i // 3
            setf(a, b, bit(vbits, i))
            setf(b, a, bit(vbits, i))
    # data in the zigzag of two-module columns, from the bottom right
    cw = _codewords(data, ver)
    i, right = 0, size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                y = size - 1 - vert if (right + 1) & 2 == 0 else vert
                if not func[y][x] and i < len(cw) * 8:
                    mods[y][x] = bit(cw[i >> 3], 7 - (i & 7))
                    i += 1
        right -= 2
    for y in range(size):
        for x in range(size):
            if not func[y][x] and (x + y) % 2 == 0:  # mask 0
                mods[y][x] = not mods[y][x]
    return mods


def qr_terminal(text: str, quiet: int = 2) -> str:
    """The QR code for a terminal: two module rows per text line (half blocks), black on white set explicitly so it
    scans on a dark and a light terminal alike."""
    m = qr_matrix(text)
    n = len(m) + 2 * quiet
    dark = lambda x, y: 0 <= y - quiet < len(m) and 0 <= x - quiet < len(m) and m[y - quiet][x - quiet]  # noqa: E731
    if sys.platform == "win32":
        os.system("")  # switches the Windows console to ANSI colours
    lines = []
    for y in range(0, n, 2):
        row = "".join(f"\x1b[{30 if dark(x, y) else 97};{40 if dark(x, y + 1) else 107}m\u2580" for x in range(n))
        lines.append("  " + row + "\x1b[0m")
    return "\n".join(lines)


# --- home-screen icon ----------------------------------------------------------------------------
@lru_cache(maxsize=len(ICON_SIZES))
def icon_png(size: int) -> bytes:
    """A four-pointed star in a blue glow on black, as a PNG of size x size pixels. The star stays inside the middle
    80 % (Android's safe zone for "maskable" icons, which it crops to a circle or squircle)."""
    rows = bytearray()
    half = (size - 1) / 2
    for py in range(size):
        rows.append(0)  # PNG filter: none
        v = (py - half) / half
        for px in range(size):
            u = (px - half) / half
            r2 = u * u + v * v
            glow = 2.71828 ** (-r2 * 5)
            star = 2.71828 ** (-abs(u * v) * 900 - r2 * 9) + 2.71828 ** (-r2 * 90)
            rows += bytes(min(255, int(c)) for c in (10 * glow + 255 * star, 132 * glow + 255 * star, 255 * glow + 255 * star))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + chunk(b"IEND", b""))


def manifest(rec: dict) -> dict:
    """The web app manifest: the start address carries the phone key, so the app on the home screen opens signed in."""
    return {
        "name": "Starlane", "short_name": "Starlane", "id": "/", "scope": "/", "start_url": f"/?k={rec['key']}",
        "display": "standalone", "background_color": "#000000", "theme_color": "#000000",
        "icons": [{"src": f"/icon-{s}.png", "sizes": f"{s}x{s}", "type": "image/png", "purpose": "any"} for s in ICON_SIZES[1:]]
        + [{"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    }
