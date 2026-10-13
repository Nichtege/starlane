"""Notion (notion.py, notionguard.py): the pinned server install, the token, deletion requests that only the user
decides, the guard that blocks every deletion by the agent, and the endpoint and CLI for the decision."""

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import urllib.error
from pathlib import Path
from unittest import mock

from aos import agents as A
from aos import notion as N
from aos import notionguard as G
from tests import test_agents as TA  # the module, not its classes: their tests must not run twice

TOKEN = "ntn_" + "a" * 30
PAGE = "0123456789abcdef0123456789abcdef"
DASHED = "01234567-89ab-cdef-0123-456789abcdef"
NOTION_AGENT = '[[agent]]\nid = "notion"\nname = "Notion"\ntools = ["Read", "Notion"]\nprompt = "agents/research.md"\n'


def dashed(c):
    return f"{c * 8}-{c * 4}-{c * 4}-{c * 4}-{c * 12}"


class FakeNotion:
    """Stands in for Notion's API: answers by path, records every call."""

    def __init__(self, pages=None, fail=None):
        self.calls, self.pages, self.fail = [], pages or {}, fail

    def __call__(self, req, timeout=None):
        method, path = req.get_method(), req.full_url[len(N.API):]
        self.calls.append((method, path, json.loads(req.data) if req.data else None))
        assert req.get_header("Authorization") == f"Bearer {TOKEN}" and req.get_header("Notion-version") == N.API_VERSION
        if self.fail:
            raise urllib.error.HTTPError(req.full_url, self.fail, "x", {}, io.BytesIO(b'{"message": "nope"}'))
        body = io.BytesIO(json.dumps(self.pages.get(path, {})).encode())
        return mock.MagicMock(__enter__=lambda s: body, __exit__=lambda *a: False)


def page(title="Old notes", **kw):
    return {"properties": {"Name": {"type": "title", "title": [{"plain_text": title}]}}, "url": f"https://www.notion.so/Old-{PAGE}", **kw}


class NotionCase(TA.AgentCase):
    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"NOTION_TOKEN": TOKEN})
        env.start()
        self.addCleanup(env.stop)

    def fake(self, **kw):
        api = FakeNotion(**kw)
        patcher = mock.patch.object(N, "_urlopen", api)
        patcher.start()
        self.addCleanup(patcher.stop)
        return api


class TokenAndIdTests(NotionCase):
    def test_page_id_from_ids_and_links(self):
        for given in (PAGE, DASHED, f"https://www.notion.so/team/Old-notes-{PAGE}?pvs=4", f"https://www.notion.so/{PAGE}#{'f' * 32}"):
            self.assertEqual(N.page_id(given), DASHED, given)
        for bad in ("", None, "abc", "https://www.notion.so/no-id-here"):
            self.assertEqual(N.page_id(bad), "")

    def test_token_from_env_then_file_and_only_well_formed(self):
        self.assertEqual(N.token(self.cfg), TOKEN)
        with mock.patch.dict(os.environ, {"NOTION_TOKEN": ""}):
            self.assertEqual(N.token(self.cfg), "")
            N.save_token(self.cfg, " secret_" + "b" * 40 + "\n")
            self.assertEqual(N.token(self.cfg), "secret_" + "b" * 40)
            with self.assertRaises(N.NotionError):
                N.save_token(self.cfg, "sk-not-notion")
            N.token_file(self.cfg).write_text("ntn_short", encoding="utf-8")
            self.assertEqual(N.token(self.cfg), "")
        with mock.patch.dict(os.environ, {"NOTION_TOKEN": "garbage"}):
            self.assertEqual(N.token(self.cfg), "")


class InstallTests(NotionCase):
    def tarball(self, files):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for rel, data in files.items():
                info = tarfile.TarInfo("package/" + rel)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def pinned(self, blob, files):
        integrity = "sha512-" + base64.b64encode(hashlib.sha512(blob).digest()).decode()
        return mock.patch.multiple(N, INTEGRITY=integrity, FILES={k: hashlib.sha256(v).hexdigest() for k, v in files.items()})

    def test_install_checks_the_tarball_and_each_file_and_installed_notices_tampering(self):
        files = {"bin/cli.mjs": b"console.log(1)", "scripts/notion-openapi.json": b"{}"}
        blob = self.tarball({**files, "package.json": b"{}"})
        with self.pinned(blob, files):
            self.assertFalse(N.installed(self.cfg))
            base = N.install(self.cfg, fetch=lambda url: blob)
            self.assertEqual(sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()), sorted(files))
            self.assertTrue(N.installed(self.cfg))
            with mock.patch.object(N, "node", return_value="node"):
                entry = N.mcp_server(self.cfg)
                self.assertEqual((entry["command"], Path(entry["args"][0]).name), ("node", "cli.mjs"))
                self.assertNotIn(TOKEN, json.dumps(entry))                       # the token travels in the environment only
                with mock.patch.dict(os.environ, {"NOTION_TOKEN": ""}):
                    self.assertIsNone(N.mcp_server(self.cfg))
            (base / "bin" / "cli.mjs").write_bytes(b"evil()")
            self.assertFalse(N.installed(self.cfg))
        with self.pinned(blob, files), self.assertRaises(N.NotionError):
            N.install(self.cfg, fetch=lambda url: blob + b"x")                    # npm's checksum
        bad = self.tarball({**files, "bin/cli.mjs": b"evil()"})
        with self.pinned(bad, files), self.assertRaises(N.NotionError):
            N.install(self.cfg, fetch=lambda url: bad)                            # a file's own checksum
        self.assertNotIn("mcp__notion__API-delete-a-block", N.ALLOWED)


class RequestTests(NotionCase):
    def test_a_request_shows_what_notion_says_it_is_and_waits(self):
        api = self.fake(pages={f"/pages/{DASHED}": page()})
        rec = N.request_deletion(self.cfg, kind="Page", target=f"https://www.notion.so/Old-{PAGE}", why="  Duplicate\nof X ", job="j", agent="notion")
        self.assertEqual({k: rec[k] for k in ("status", "kind", "target", "title", "why", "agent")},
                         {"status": "pending", "kind": "page", "target": DASHED, "title": "Old notes", "why": "Duplicate of X", "agent": "notion"})
        self.assertEqual(api.calls, [("GET", f"/pages/{DASHED}", None)])                # nothing changed in Notion
        self.assertEqual(N.request_deletion(self.cfg, kind="page", target=PAGE, why="again")["id"], rec["id"])  # no duplicates
        self.assertEqual([r["id"] for r in N.pending(self.cfg)], [rec["id"]])
        for kw, says in (({"kind": "database"}, "kind"), ({"target": "nope"}, "No Notion id"), ({"why": " "}, "why")):
            with self.assertRaises(N.NotionError) as ctx:
                N.request_deletion(self.cfg, **{"kind": "page", "target": PAGE, "why": "w", **kw})
            self.assertIn(says, str(ctx.exception))

    def test_already_trashed_unshared_and_too_many(self):
        self.fake(pages={f"/pages/{DASHED}": page(in_trash=True)})
        with self.assertRaises(N.NotionError):
            N.request_deletion(self.cfg, kind="page", target=PAGE, why="w")
        self.fake(fail=404)
        with self.assertRaises(N.NotionError) as ctx:
            N.request_deletion(self.cfg, kind="page", target=PAGE, why="w")
        self.assertIn("shared with your integration", str(ctx.exception))
        self.fake()
        for i in range(N.MAX_PENDING):
            N.request_deletion(self.cfg, kind="block", target=f"{i:032x}", why="w")
        with self.assertRaises(N.NotionError):
            N.request_deletion(self.cfg, kind="block", target="f" * 32, why="w")

    def test_only_an_approval_deletes_and_starlane_does_it(self):
        api = self.fake(pages={f"/pages/{DASHED}": page(),
                               f"/blocks/{dashed('b')}": {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Old line"}]}}})
        p = N.request_deletion(self.cfg, kind="page", target=PAGE, why="w")
        b = N.request_deletion(self.cfg, kind="block", target="b" * 32, why="w")
        self.assertEqual(b["title"], "paragraph: Old line")
        api.calls.clear()
        self.assertEqual(N.decide(self.cfg, b["id"], False)["status"], "kept")
        self.assertEqual(api.calls, [])
        self.assertEqual(N.decide(self.cfg, p["id"], True)["status"], "deleted")
        self.assertEqual(api.calls, [("PATCH", f"/pages/{DASHED}", {"in_trash": True})])   # a page goes to Notion's trash
        with self.assertRaises(KeyError):
            N.decide(self.cfg, p["id"], True)                                              # decided once
        self.assertEqual(N.pending(self.cfg), [])
        self.assertEqual([(r["kind"], r["status"]) for r in N.all_requests(self.cfg)], [("block", "kept"), ("page", "deleted")])  # newest request first

    def test_a_block_is_deleted_and_a_failure_is_kept_for_the_user(self):
        api = self.fake()
        rec = N.request_deletion(self.cfg, kind="block", target="c" * 32, why="w")
        api.calls.clear()
        self.assertEqual(N.decide(self.cfg, rec["id"], True)["status"], "deleted")
        self.assertEqual(api.calls[0][:2], ("DELETE", f"/blocks/{dashed('c')}"))
        rec = N.request_deletion(self.cfg, kind="block", target="d" * 32, why="w")
        self.fake(fail=500)
        done = N.decide(self.cfg, rec["id"], True)
        self.assertEqual((done["status"], done["note"]), ("failed", "Notion: nope"))

    def test_status_for_the_dashboard(self):
        self.write_agents(NOTION_AGENT)
        st = N.status(self.cfg, A.load_agents(self.cfg.agents_file))
        self.assertEqual((st["agent"], st["token"], st["installed"], st["ready"], st["requests"]), ("notion", True, False, False, []))
        self.assertIsNone(N.status(self.cfg)["agent"])


class GuardTests(NotionCase):
    def test_check_blocks_every_kind_of_deletion(self):
        for tool, given in (("mcp__notion__API-delete-a-block", {"block_id": "x"}),
                            ("mcp__notion__API-patch-page", {"page_id": "x", "archived": True}),
                            ("mcp__notion__API-patch-page", {"page_id": "x", "in_trash": True}),
                            ("mcp__notion__API-update-a-block", {"block_id": "x", "is_archived": True}),
                            ("mcp__notion__API-update-page-markdown", {"page_id": "x", "allow_deleting_content": True}),
                            ("mcp__notion__API-patch-page", {"page_id": "x", "properties": '{"in_trash": true}'}),  # inside a string
                            ("mcp__notion__API-patch-page", {"page_id": "x", "body": {"deep": {"ARCHIVED": True}}})):
            self.assertTrue(G.check(tool, given), (tool, given))
        for tool, given in (("mcp__notion__API-patch-page", {"page_id": "x", "archived": False}),
                            ("mcp__notion__API-patch-block-children", {"block_id": "x", "children": [{"paragraph": {"text": "archived: yes"}}]}),
                            ("mcp__notion__API-post-search", {"query": "in_trash"})):
            self.assertEqual(G.check(tool, given), "", (tool, given))

    def test_target_of_a_change(self):
        self.assertEqual(G.target({"page_id": "p1", "properties": {}}), "p1")
        self.assertEqual(G.target({"parent": '{"page_id": "p2"}'}), "new in p2")
        self.assertEqual(G.target({"parent": {"data_source_id": "d1"}}), "new in d1")
        self.assertEqual(G.target("x"), "")

    def hook(self, stage, payload, state):
        env = {**os.environ, "AOS_NOTION_STATE": str(state), "AOS_NOTION_USER": "Kim"}
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        return subprocess.run([sys.executable, "-I", str(A.NOTION_GUARD), stage], input=data, capture_output=True, env=env, timeout=30)

    def test_the_hook_blocks_records_and_fails_closed(self):
        state = self.root / "s"
        res = self.hook("pre", {"tool_name": "mcp__notion__API-delete-a-block", "tool_input": {"block_id": "x"}}, state)
        self.assertEqual(res.returncode, 2)
        self.assertIn("request_deletion", res.stderr.decode())
        self.assertIn("Kim", res.stderr.decode())
        self.assertEqual(Path(str(state) + ".blocked").read_text(encoding="utf-8"), "mcp__notion__API-delete-a-block\n")
        self.assertEqual(self.hook("pre", {"tool_name": "mcp__notion__API-patch-page", "tool_input": {"page_id": "p"}}, state).returncode, 0)
        self.assertEqual(self.hook("pre", b"not json", state).returncode, 2)                  # cannot check: blocked
        for tool in ("mcp__notion__API-patch-page", "mcp__notion__API-retrieve-a-page"):
            self.assertEqual(self.hook("post", {"tool_name": tool, "tool_input": {"page_id": "p"}}, state).returncode, 0)
        self.assertEqual(self.hook("post", b"not json", state).returncode, 0)
        lines = Path(str(state) + ".changes").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(ln) for ln in lines], [{"tool": "patch-page", "target": "p"}])  # reading is no change


class LoadTests(NotionCase):
    def test_one_notion_agent_and_never_with_the_web(self):
        self.write_agents(NOTION_AGENT.replace('"Notion"]', '"Notion", "WebSearch"]'))
        with self.assertRaises(A.AgentError):
            A.load_agents(self.cfg.agents_file)
        self.write_agents(NOTION_AGENT + NOTION_AGENT.replace('id = "notion"', 'id = "notion2"'))
        with self.assertRaises(A.AgentError):
            A.load_agents(self.cfg.agents_file)


class NotionServerTests(TA.ServerAgentTests):
    # the inherited endpoint tests already run in test_agents
    test_submit_and_poll = test_model_and_effort_come_through_the_endpoint_and_bad_values_are_refused = None
    test_atlas_keeps_the_conversation_thread_and_board_shows_group_and_web = test_guards_and_bad_requests = None
    test_data_json_carries_agents_jobs_and_api_paths = test_static_dashboard_shows_broken_agents_file = None

    def setUp(self):
        super().setUp()
        env = mock.patch.dict(os.environ, {"NOTION_TOKEN": TOKEN})
        env.start()
        self.addCleanup(env.stop)
        self.api = FakeNotion(pages={f"/pages/{DASHED}": page()})
        patcher = mock.patch.object(N, "_urlopen", self.api)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_decide_through_the_endpoint(self):
        rec = N.request_deletion(self.cfg, kind="page", target=PAGE, why="w")
        _, data = self.req("GET", "/api/data")
        self.assertEqual(data["api"]["notion"], "/api/notion/requests/")
        self.assertEqual([r["id"] for r in data["notion"]["requests"]], [rec["id"]])
        url = "/api/notion/requests/" + rec["id"]
        self.assertEqual(self.req("POST", url, {"decision": "approve"}, token=None)[0], 401)
        self.assertEqual(self.req("POST", url, {"decision": "maybe"})[0], 400)
        self.assertEqual(self.req("POST", "/api/notion/requests/" + "0" * 12, {"decision": "deny"})[0], 404)
        status, body = self.req("POST", url, {"decision": "approve"})
        self.assertEqual((status, body["request"]["status"]), (200, "deleted"))
        self.assertEqual(self.api.calls[-1][0], "PATCH")
        rec = N.request_deletion(self.cfg, kind="page", target="e" * 32, why="w")
        self.api.fail = 500
        status, body = self.req("POST", "/api/notion/requests/" + rec["id"], {"decision": "approve"})
        self.assertEqual((status, body["ok"]), (502, False))


class NotionCliTests(TA.CliAgentTests):
    test_agents_agent_and_jobs = test_doctor_flags_a_forbidden_tool = None  # already run in test_agents

    def test_list_approve_deny(self):
        self.write_agents(NOTION_AGENT)
        api = FakeNotion(pages={f"/pages/{DASHED}": page()})
        with mock.patch.dict(os.environ, {"NOTION_TOKEN": TOKEN}), mock.patch.object(N, "_urlopen", api):
            code, out = self.run_cli("notion")
            self.assertEqual(code, 0)
            self.assertIn("Notion agent: notion", out)
            self.assertIn("No deletion requests are waiting.", out)
            keep = N.request_deletion(self.cfg, kind="page", target=PAGE, why="Duplicate")
            code, out = self.run_cli("notion")
            self.assertIn(keep["id"], out)
            self.assertIn("why: Duplicate", out)
            code, out = self.run_cli("notion-deny", keep["id"])
            self.assertEqual(code, 0)
            self.assertIn('Kept: page "Old notes"', out)
            self.assertEqual(self.run_cli("notion-approve", keep["id"])[0], 2)          # closed already
            rec = N.request_deletion(self.cfg, kind="page", target=PAGE, why="Duplicate")
            code, out = self.run_cli("notion-approve", rec["id"])
            self.assertEqual(code, 0)
            self.assertIn("in Notion's trash for 30 days", out)


class DashboardTests(NotionCase):
    def test_requests_and_conversations_are_wired_into_the_atlas_chat(self):
        html = (Path(A.__file__).parent / "web" / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("if (asks.length) kids.push(notionAsksBox(asks));", html)
        self.assertIn("live ? null : jobTalks(j),", html)                                   # under a finished answer
        self.assertIn("/^https:\/\/(www\.)?notion\.so\//.test(", html)                  # only Notion's own links
        self.assertIn("body: JSON.stringify({ decision: approve ? 'approve' : 'deny' })", html)
