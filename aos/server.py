"""Screen with buttons: local server for the dashboard (`aos serve`).

Security (the dashboard can start routines, so):
- listens on 127.0.0.1 only, never on the network
- every API request needs the random token of this server start (header X-AOS-Token)
- the page that embeds the token needs the launch key of this server start (`/?k=...`, printed by `aos serve`)
  and must be a top-level browser navigation (Sec-Fetch-* headers, where the browser sends them)
- Host and Origin headers are checked (protection against DNS rebinding and foreign web pages)
- error messages never contain the vault, project or home path
- only routines from routines.toml, only via the whitelist; no file or shell access over HTTP
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import signal
import socket
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import agentdefs as AD
from . import agents as A
from . import artifacts as AR
from .config import Config
from .dashboard import build_data, render_html
from .i18n import tr
from .routines import RoutineError, load_routines
from .scheduler import Busy, Refused, run_now
from .vault import VaultNotFound

CACHE_SECONDS = 5
MAX_BODY = 32 * 1024  # custom agents: up to 6000 characters of instructions (UTF-8) plus fields
ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,40}$")
PAGE_PATHS = ("/", "/index.html", "/dashboard.html")


def forbidden_page() -> bytes:
    text = tr("This address needs the link that <code>aos serve</code> printed in the terminal "
              "(<code>http://127.0.0.1:&lt;port&gt;/?k=...</code>). Open that link, or restart <code>aos serve</code>.")
    return f'<!doctype html><meta charset="utf-8"><title>Starlane</title><p>{text}</p>'.encode("utf-8")


class State:
    def __init__(self, cfg: Config, port: int, token: str | None = None, launch_key: str | None = None):
        self.cfg, self.port = cfg, port
        self.token = token or secrets.token_urlsafe(24)
        self.launch_key = launch_key or secrets.token_urlsafe(18)  # in memory only, new on every start
        self._lock = threading.Lock()
        self._cache: tuple[float, dict] | None = None
        A.recover(cfg)  # close out jobs that were still running when the server last stopped

    @property
    def launch_url(self) -> str:
        """The only address that serves the dashboard page (and with it the token)."""
        return f"http://127.0.0.1:{self.port}/?k={self.launch_key}"

    def scrub(self, text: str) -> str:
        """Error text without absolute paths: vault, project and home folder become placeholders."""
        roots = [(getattr(self.cfg, "vault", None), "<vault>"), (getattr(self.cfg, "data_dir", None), "<data>"),
                 (getattr(self.cfg, "project_root", None), "<project>"), (Path.home(), "~")]
        roots = sorted(((r, s) for r, s in roots if r), key=lambda x: -len(str(x[0])))  # the deepest folder first
        for root, label in roots:
            for form in {str(root), Path(root).as_posix(), str(root).replace("\\", "\\\\")}:
                text = re.sub(re.escape(form), lambda _m, s=label: s, text, flags=re.I)
        return text

    @property
    def api(self) -> dict:
        return {"token": self.token, "run": "/api/run/", "data": "/api/data", "agents": "/api/agents/", "jobs": "/api/jobs", "atlas": "/api/atlas",
                "skills": "/api/skills/", "artifact": "/api/artifact/", "agent_defs": "/api/agent-defs"}

    def data(self, fresh: bool = False) -> dict:
        with self._lock:
            now = time.monotonic()
            if fresh or self._cache is None or now - self._cache[0] > CACHE_SECONDS:
                self._cache = (now, build_data(self.cfg, api=self.api))
            return self._cache[1]

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None


def make_handler(state: State):
    def allowed_hosts() -> set[str]:
        return {f"127.0.0.1:{state.port}", f"localhost:{state.port}"}

    class Handler(BaseHTTPRequestHandler):
        timeout = 30  # drop hanging connections (slowloris) after 30 s
        server_version = "aos"
        sys_version = ""

        def log_message(self, fmt, *args):  # stay quiet
            pass

        # -- Helpers --
        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "").lower() in allowed_hosts()

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin in {f"http://{h}" for h in allowed_hosts()}

        def _fail(self, exc: Exception) -> None:
            # e.g. vault not reachable: a readable message instead of a silently dropped connection
            if isinstance(exc, VaultNotFound):
                self._json(500, {"ok": False, "error": state.scrub(str(exc))})  # a setup problem, not an internal error
                return
            self._json(500, {"ok": False, "error": state.scrub(tr("Internal error: {kind}: {error}", kind=type(exc).__name__, error=exc))})

        def _page_ok(self) -> bool:
            """The page embeds the token: only a top-level navigation with the launch key of this server start gets it.
            Browsers send Sec-Fetch-*; a missing header (older browser, curl) is fine because the key is still needed."""
            dest = (self.headers.get("Sec-Fetch-Dest") or "document").lower()
            site = (self.headers.get("Sec-Fetch-Site") or "none").lower()
            if dest != "document" or site not in ("none", "same-origin"):
                return False
            given = parse_qs(urlsplit(self.path).query).get("k", [""])[0]
            return hmac.compare_digest(given.encode(), state.launch_key.encode())

        def _token_ok(self) -> bool:
            given = self.headers.get("X-AOS-Token") or ""
            return hmac.compare_digest(given.encode(), state.token.encode())

        def _guard(self, need_token: bool) -> bool:
            if not self._host_ok():
                self._json(403, {"ok": False, "error": tr("Host not allowed")})
                return False
            if not self._origin_ok():
                self._json(403, {"ok": False, "error": tr("Origin not allowed")})
                return False
            if need_token and not self._token_ok():
                self._json(401, {"ok": False, "error": tr("Token missing or wrong")})
                return False
            return True

        # -- Routes --
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in PAGE_PATHS:
                if not self._guard(False):
                    return
                if not self._page_ok():
                    self._send(403, forbidden_page(), "text/html; charset=utf-8",
                               {"Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"})
                    return
                nonce = secrets.token_urlsafe(16)
                try:
                    html = render_html(state.data()).replace("<script", f'<script nonce="{nonce}"')
                except Exception as exc:  # noqa: BLE001
                    self._fail(exc)
                    return
                csp = (
                    f"default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; img-src data:; "
                    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
                )
                self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", {"Content-Security-Policy": csp})
            elif path == "/api/data":
                if self._guard(True):
                    try:
                        data = state.data(fresh=True)
                    except Exception as exc:  # noqa: BLE001
                        self._fail(exc)
                        return
                    self._json(200, data)
            elif path == "/api/jobs" or path.startswith("/api/jobs/"):
                if not self._guard(True):
                    return
                try:
                    if path == "/api/jobs":
                        self._json(200, {"ok": True, "jobs": A.all_jobs(state.cfg)[: A.JOBS_SHOWN]})
                        return
                    job = A.get_job(state.cfg, path.rsplit("/", 1)[1])
                except Exception as exc:  # noqa: BLE001
                    self._fail(exc)
                    return
                self._json(200, {"ok": True, "job": job}) if job else self._json(404, {"ok": False, "error": tr("unknown job")})
            elif re.fullmatch(r"/api/agent-defs/[a-z0-9\-]+", path):
                if not self._guard(True):
                    return
                try:
                    self._json(200, {"ok": True, "agent": AD.read(state.cfg, path.rsplit("/", 1)[1])})
                except KeyError:
                    self._json(404, {"ok": False, "error": tr("unknown agent")})
                except A.Refused as exc:
                    self._json(exc.code, {"ok": False, "error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    self._fail(exc)
            elif path.startswith("/api/artifact/"):
                if not self._guard(True):
                    return
                try:
                    art = AR.read_artifact(state.cfg, path.rsplit("/", 1)[1])
                except Exception as exc:  # noqa: BLE001
                    self._fail(exc)
                    return
                self._json(200, {"ok": True, "artifact": art}) if art else self._json(404, {"ok": False, "error": tr("unknown artifact")})
            elif path == "/healthz":
                self._json(200, {"ok": True}) if self._host_ok() else self._json(403, {"ok": False})
            else:
                self._json(404, {"ok": False, "error": tr("not found")})

        def _read_json(self) -> dict | None:
            """Read a JSON body (application/json only, at most MAX_BODY). On error the response has already been sent."""
            try:
                length = int(self.headers.get("Content-Length") or "")
            except ValueError:
                self._json(411, {"ok": False, "error": tr("Content-Length missing")})
                return None
            # Still read and discard moderately large bodies: otherwise Windows resets the connection before
            # the browser gets the error message. Very large ones are not read at all.
            raw = self.rfile.read(length) if 0 <= length <= 4 * MAX_BODY else b""
            if length < 0 or length > MAX_BODY:
                self._json(413, {"ok": False, "error": tr("Request too large (at most {kb} KB)", kb=MAX_BODY // 1024)})
                return None
            if self.headers.get_content_type() != "application/json":
                self._json(415, {"ok": False, "error": tr("Content-Type must be application/json")})
                return None
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                body = None
            if not isinstance(body, dict):
                self._json(400, {"ok": False, "error": tr("Body must be a JSON object")})
                return None
            return body

        def _post_skill(self, sid: str) -> None:
            body = self._read_json()
            if body is None:
                return
            try:
                job = A.submit_skill(state.cfg, sid, body.get("instruction"), model=body.get("model"), effort=body.get("effort"))
            except KeyError:
                self._json(404, {"ok": False, "error": tr("unknown skill")})
                return
            except A.Refused as exc:
                self._json(exc.code, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._fail(exc)
                return
            state.invalidate()
            self._json(202, {"ok": True, "job": job})

        def _post_agent(self, aid: str | None) -> None:
            """aid None = Atlas picks the agent."""
            body = self._read_json()
            if body is None:
                return
            try:
                if aid is None:  # Atlas: plans, distributes to several specialists, merges the answers
                    job = A.submit_atlas(state.cfg, body.get("instruction"), thread=body.get("thread"),
                                         model=body.get("model"), effort=body.get("effort"), prefer=body.get("prefer"))
                else:
                    job = A.submit(state.cfg, aid, body.get("instruction"), thread=body.get("thread"),
                                   model=body.get("model"), effort=body.get("effort"))
            except KeyError:
                self._json(404, {"ok": False, "error": tr("unknown agent")})
                return
            except A.Refused as exc:
                self._json(exc.code, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001 (e.g. agents.toml broken)
                self._fail(exc)
                return
            state.invalidate()
            self._json(202, {"ok": True, "job": job})

        def _agent_def(self, aid: str | None) -> None:
            """Create a custom agent (aid None) or update one. Response: the agent in the shape of the agent board."""
            body = self._read_json()
            if body is None:
                return
            try:
                if aid is None:
                    given = body.get("id")
                    agent = AD.create(state.cfg, body, agent_id=given if isinstance(given, str) and given else None)
                else:
                    agent = AD.update(state.cfg, aid, body)
            except KeyError:
                self._json(404, {"ok": False, "error": tr("unknown agent")})
                return
            except (A.Refused, A.AgentError) as exc:
                self._json(getattr(exc, "code", 500), {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._fail(exc)
                return
            state.invalidate()
            row = next((r for r in A.board(state.cfg) if r["id"] == agent.id), None)
            self._json(201 if aid is None else 200, {"ok": True, "agent": row})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/agent-defs":
                if self._guard(True):
                    self._agent_def(None)
                return
            m = re.fullmatch(r"/api/agent-defs/([a-z0-9\-]+)", path)
            if m and ID_RE.match(m.group(1)):
                if self._guard(True):
                    self._agent_def(m.group(1))
                return
            if path == "/api/atlas":
                if self._guard(True):
                    self._post_agent(None)
                return
            m = re.fullmatch(r"/api/skills/([a-z0-9\-]+)", path)
            if m and ID_RE.match(m.group(1)):
                if self._guard(True):
                    self._post_skill(m.group(1))
                return
            m = re.fullmatch(r"/api/agents/([a-z0-9\-]+)", path)
            if m and ID_RE.match(m.group(1)):
                if self._guard(True):
                    self._post_agent(m.group(1))
                return
            m = re.fullmatch(r"/api/run/([a-z0-9\-]+)", path)
            if not m:
                self._json(404, {"ok": False, "error": tr("not found")})
                return
            if not self._guard(True):
                return
            rid = m.group(1)
            try:
                known = {r.id for r in load_routines(state.cfg.routines_file)}
            except RoutineError as exc:
                self._json(500, {"ok": False, "error": state.scrub(str(exc))})
                return
            if not ID_RE.match(rid) or rid not in known:
                self._json(404, {"ok": False, "error": tr("unknown routine")})
                return
            try:
                rec = run_now(state.cfg, rid, respect_limits=True)
            except Refused as exc:
                self._json(403, {"ok": False, "error": str(exc)})
                return
            except KeyError:  # routines.toml changed between the two reads
                self._json(404, {"ok": False, "error": tr("unknown routine")})
                return
            except Busy:
                self._json(409, {"ok": False, "error": tr("Something is already running, try again in a moment")})
                return
            except Exception as exc:  # noqa: BLE001
                self._fail(exc)
                return
            state.invalidate()
            self._json(200, {"ok": rec["status"] == "ok", "record": rec})

        def do_DELETE(self):
            path = self.path.split("?", 1)[0]
            m = re.fullmatch(r"/api/agent-defs/([a-z0-9\-]+)", path)
            if not m or not ID_RE.match(m.group(1)):
                self._json(405, {"ok": False, "error": tr("Method not allowed")})
                return
            if not self._guard(True):
                return
            try:
                AD.delete(state.cfg, m.group(1))
            except KeyError:
                self._json(404, {"ok": False, "error": tr("unknown agent")})
                return
            except (A.Refused, A.AgentError) as exc:
                self._json(getattr(exc, "code", 500), {"ok": False, "error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._fail(exc)
                return
            state.invalidate()
            self._json(200, {"ok": True})

        def do_PUT(self):
            self._json(405, {"ok": False, "error": tr("Method not allowed")})

        do_PATCH = do_PUT

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second process silently share the same port
    # (a second `aos serve` or another program). There, bind the port exclusively instead.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def create_server(cfg: Config, port: int, token: str | None = None) -> tuple[ThreadingHTTPServer, State]:
    state = State(cfg, port, token)
    httpd = _Server((cfg.server_host, port), make_handler(state))
    state.port = httpd.server_address[1]  # with port=0 the OS picks a free port
    return httpd, state


def serve(cfg: Config, port: int, open_browser: bool = True) -> int:
    try:
        httpd, state = create_server(cfg, port)
    except OSError as exc:
        print(tr("Port {port} not available (is the dashboard already running? Otherwise `aos serve --port 8766`): {error}", port=port, error=exc), flush=True)
        return 1
    url = state.launch_url
    print(tr("Dashboard running at {url} (this machine only; the link is valid until the server stops). Stop with Ctrl+C.", url=url), flush=True)
    log = state.cfg.data_dir / "server.log"

    def note(msg: str) -> None:
        # Why the server stopped should be traceable (data/server.log); errors here must never stop the server
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as fh:
                fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")
        except OSError:
            pass

    note(f"started on port {httpd.server_address[1]}")
    threading.excepthook = lambda a: note(f"error in thread: {a.exc_type.__name__}: {a.exc_value}")

    def on_interrupt(signum, frame):
        # Windows console: a Ctrl+C event right after an agent job comes from the child process, not from you: ignore it
        # (on macOS / Linux a child in its own session never sends one)
        if sys.platform == "win32" and time.monotonic() - A.LAST_ACTIVITY < 10:
            note("Ctrl+C shortly after a job ignored")
            print("\n" + tr("Ctrl+C right after a job ignored. Press it again in a few seconds to stop."), flush=True)
            return
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGINT, on_interrupt)
    except ValueError:  # not in the main thread (tests)
        pass
    headless = sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if open_browser and not headless:  # a headless box would start a text browser in this very terminal
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
        note("stopped (serve_forever returned)")
    except KeyboardInterrupt:
        note("stopped by Ctrl+C")
        print("\n" + tr("Stopped."), flush=True)
    except BaseException as exc:  # noqa: BLE001 - record the reason, then re-raise
        note(f"crashed: {type(exc).__name__}: {exc}")
        raise
    finally:
        httpd.server_close()
        A.kill_live()  # an agent run is in its own session: Ctrl+C does not reach it
    return 0
