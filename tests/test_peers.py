"""Agents talk to each other (peers.py): who may ask whom, limits, waiting for a busy agent, the MCP server, the run's
command and environment, and what Atlas and the job get to see."""

import io
import json
from dataclasses import replace
from datetime import datetime
from unittest import mock

from aos import agents as A
from aos import notion as N
from aos import peers as P
from tests.test_agents import AgentCase

AGENTS = """
[[agent]]
id = "research"
name = "Research"
description = "Answers from the notes"
tools = ["Read", "Grep"]
prompt = "agents/research.md"

[[agent]]
id = "planner"
name = "Planner"
description = "Plans"
tools = ["Read"]
prompt = "agents/research.md"

[[agent]]
id = "web"
name = "Web"
description = "Searches the web"
tools = ["WebSearch"]
prompt = "agents/research.md"

[[agent]]
id = "notion"
name = "Notion"
description = "Changes Notion"
tools = ["Read", "Notion"]
prompt = "agents/research.md"
"""


def answer(text="Plan: step 1"):
    return lambda cfg, agent, instruction: ("ok", text, "")


class PeerCase(AgentCase):
    def setUp(self):
        super().setUp()
        self.write_agents(AGENTS)
        self.user = A.persona(self.cfg)[0]

    def task(self, agent="research", text="Plan my week from my notes"):
        return A.submit(self.cfg, agent, text, wait=True, runner=answer("done"))

    def peer(self, jid, **kw):
        rec = {"id": jid, "agent": "planner", "instruction": "x", "status": "ok", "thread": jid, "via": "peer",
               "started": datetime.now().isoformat(timespec="seconds"), "result": "r"}
        rec.update(kw)
        A._append(self.cfg, rec)
        return rec


class AskTests(PeerCase):
    def test_answer_comes_back_and_the_asked_run_knows_whose_message_it_is(self):
        job = self.task()
        seen = {}

        def planner(cfg, agent, instruction):
            seen.update(agent=agent, instruction=instruction)
            return "ok", "Plan: step 1", ""

        ok, text = P.ask(self.cfg, job["id"], "planner", "Which deadlines are this week?", runner=planner)
        self.assertTrue(ok, text)
        self.assertEqual(text, "Answer from Planner:\nPlan: step 1")
        letter = seen["instruction"]
        self.assertIn('Message from the agent "Research"', letter)
        self.assertIn(f"Not from {self.user}", letter)
        self.assertIn("Plan my week from my notes", letter)              # the user's request, as context
        self.assertIn("Message:\nWhich deadlines are this week?", letter)
        self.assertTrue(letter.endswith(P.PEER_RULE % {"user": self.user}))
        asked = A.get_job(self.cfg, seen["agent"].job)
        self.assertEqual((asked["via"], asked["parent"], asked["root"], asked["depth"], asked["asker"]),
                         ("peer", job["id"], job["id"], 1, "research"))
        self.assertEqual(seen["agent"].depth, 1)

    def test_the_earlier_exchange_goes_into_the_next_letter(self):
        job = self.task()
        P.ask(self.cfg, job["id"], "planner", "First question", runner=answer("First answer"))
        seen = []
        P.ask(self.cfg, job["id"], "planner", "Second question",
              runner=lambda cfg, agent, instruction: (seen.append(instruction), ("ok", "x", ""))[1])
        self.assertIn("Earlier in this exchange:\nResearch: First question\nPlanner: First answer", seen[0])

    def test_who_cannot_be_asked(self):
        job = self.task()
        for target, says in (("web", "only searches the web"), ("nobody", "no agent 'nobody'"),
                             ("research", "waiting for your answer"), ("off", "no agent 'off'")):
            ok, text = P.ask(self.cfg, job["id"], target, "x", runner=answer())
            self.assertFalse(ok, target)
            self.assertIn(says, text)
        self.assertEqual(P.ask(self.cfg, job["id"], "planner", "   ", runner=answer()), (False, "The message is empty."))
        self.assertFalse(P.ask(self.cfg, "0" * 12, "planner", "x", runner=answer())[0])
        self.assertFalse(any(j.get("via") == "peer" for j in A.all_jobs(self.cfg)))  # nothing ran

    def test_nobody_up_the_chain_can_be_asked_and_depth_ends_at_two(self):
        job = self.task()
        mid = self.peer("a" * 12, agent="planner", parent=job["id"], root=job["id"], depth=1, asker="research")
        ok, text = P.ask(self.cfg, mid["id"], "research", "x", runner=answer())
        self.assertFalse(ok)
        self.assertIn("waiting for your answer", text)
        self.assertTrue(P.ask(self.cfg, mid["id"], "notion", "x", runner=answer())[0])  # one level more is fine
        deep = self.peer("b" * 12, agent="notion", parent=mid["id"], root=job["id"], depth=2, asker="planner")
        ok, text = P.ask(self.cfg, deep["id"], "research", "x", runner=answer())
        self.assertFalse(ok)
        self.assertIn("at most 2 levels", text)
        self.assertEqual(A.PEER_DEPTH, P.MAX_DEPTH)

    def test_a_task_has_a_message_budget(self):
        job = self.task()
        for i in range(P.MAX_CALLS):
            self.peer(f"{i:012x}", parent=job["id"], root=job["id"], depth=1, asker="research")
        self.peer("f" * 12, parent=job["id"], root=job["id"], status="refused")  # refused ones do not count
        ok, text = P.ask(self.cfg, job["id"], "planner", "x", runner=answer())
        self.assertFalse(ok)
        self.assertIn(f"used its {P.MAX_CALLS} messages", text)

    def test_a_busy_agent_is_waited_for_and_given_up_on_after_the_deadline(self):
        job = self.task()
        busy = {"id": "c" * 12, "agent": "planner", "instruction": "x", "status": "running", "thread": "c" * 12,
                "started": datetime.now().isoformat(timespec="seconds"), "via": "server"}
        A._append(self.cfg, busy)
        sleeps = []

        def sleep(s):  # while it waits, the other task ends
            sleeps.append(s)
            A._append(self.cfg, {**busy, "status": "ok", "result": "done"})

        ok, text = P.ask(self.cfg, job["id"], "planner", "x", runner=answer(), sleep=sleep, clock=lambda: 0)
        self.assertTrue(ok, text)
        self.assertEqual(sleeps, [3])
        A._append(self.cfg, {**busy, "id": "d" * 12, "thread": "d" * 12})
        times = iter([0, P.WAIT_S + 1])
        ok, text = P.ask(self.cfg, job["id"], "planner", "x", runner=answer(), sleep=lambda s: None, clock=lambda: next(times))
        self.assertFalse(ok)
        self.assertIn("Planner cannot answer now: This agent is still working", text)

    def test_failed_out_of_scope_and_long_answers(self):
        job = self.task()
        ok, text = P.ask(self.cfg, job["id"], "planner", "x", runner=lambda c, a, i: ("failed", "", "broken"))
        self.assertEqual((ok, text), (False, "Planner did not answer (failed): broken"))
        ok, text = P.ask(self.cfg, job["id"], "planner", "x", runner=answer(A.OUT_OF_SCOPE + " ask Research"))
        self.assertEqual((ok, text), (False, "Planner says this is not its field: ask Research"))
        ok, text = P.ask(self.cfg, job["id"], "planner", "x", runner=answer("y" * (P.ANSWER_CHARS + 50)))
        self.assertTrue(ok)
        self.assertTrue(text.endswith("y\n[… shortened]"))

    def test_peer_jobs_do_not_count_toward_the_parallel_limit(self):
        job = self.task()
        for i in range(A.MAX_PARALLEL):  # the other agents are all busy with tasks of their own
            A._append(self.cfg, {"id": f"e{i:011x}", "agent": f"x{i}", "instruction": "x", "status": "running",
                                 "thread": f"e{i:011x}", "started": datetime.now().isoformat(timespec="seconds"), "via": "server"})
        with self.assertRaises(A.Refused):
            A.submit(self.cfg, "planner", "x", wait=True, runner=answer())
        self.assertTrue(P.ask(self.cfg, job["id"], "planner", "x", runner=answer())[0])


class TalksTests(PeerCase):
    def test_the_asking_job_keeps_the_conversation(self):
        def research(cfg, agent, instruction):
            ok, text = P.ask(cfg, agent.job, "planner", "Deadlines?", runner=answer("Friday"))
            return "ok", "Done: " + text, ""

        job = A.submit(self.cfg, "research", "Plan", wait=True, runner=research)
        self.assertEqual(job["result"], "Done: Answer from Planner:\nFriday")
        [talk] = job["talks"]
        self.assertEqual({k: talk[k] for k in ("from", "to", "message", "answer", "status", "depth")},
                         {"from": "research", "to": "planner", "message": "Deadlines?", "answer": "Friday", "status": "ok", "depth": 1})
        self.assertNotIn("talks", A.get_job(self.cfg, talk["job"]))  # the asked run said nothing to anyone

    def test_atlas_sees_the_messages_of_its_specialists_and_of_those_they_asked(self):
        now = datetime.now().isoformat(timespec="seconds")
        jobs = [  # newest first, like all_jobs()
            {"id": "4" * 12, "agent": "notion", "via": "peer", "parent": "3" * 12, "asker": "planner", "message": "Save it",
             "result": "", "note": "timeout", "status": "timeout", "depth": 2, "started": now},
            {"id": "3" * 12, "agent": "planner", "via": "peer", "parent": "2" * 12, "asker": "research", "message": "Plan?",
             "result": "Plan", "status": "ok", "depth": 1, "started": now},
            {"id": "9" * 12, "agent": "planner", "via": "peer", "parent": "8" * 12, "asker": "research", "message": "other task",
             "status": "ok", "depth": 1, "started": now},
            {"id": "2" * 12, "agent": "research", "via": "atlas", "parent": "1" * 12, "status": "ok", "started": now},
            {"id": "1" * 12, "agent": "atlas", "via": "server", "status": "ok", "started": now},
        ]
        said = P.talks(self.cfg, "1" * 12, jobs)
        self.assertEqual([(t["from"], t["to"], t["answer"]) for t in said], [("research", "planner", "Plan"), ("planner", "notion", "timeout")])
        text = P.transcript(said, {"research": "Research", "planner": "Planner", "notion": "Notion"})
        self.assertIn("- Research → Planner: Plan?\n  Planner: Plan", text)
        self.assertIn("- Planner → Notion: Save it\n  Notion (timeout): timeout", text)
        self.assertEqual(P.transcript([], {}), "")


class McpTests(PeerCase):
    def call(self, job_id, method, params=None, mid=1):
        return P.handle(self.cfg, job_id, {"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})

    def test_handshake_and_tool_lists(self):
        job = self.task()
        init = self.call(job["id"], "initialize", {"protocolVersion": "2025-03-26"})["result"]
        self.assertEqual((init["protocolVersion"], init["serverInfo"]["name"]), ("2025-03-26", "starlane"))
        self.assertEqual(self.call(job["id"], "initialize", {"protocolVersion": "1999"})["result"]["protocolVersion"], P.PROTOCOLS[0])
        self.assertEqual(self.call(job["id"], "ping")["result"], {})
        self.assertIsNone(P.handle(self.cfg, job["id"], {"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(self.call(job["id"], "resources/list")["error"]["code"], -32601)
        [tool] = self.call(job["id"], "tools/list")["result"]["tools"]
        self.assertEqual(tool["name"], "ask_agent")
        self.assertIn("- planner: Plans", tool["description"])
        self.assertIn("- notion: Changes Notion", tool["description"])
        for gone in ("- research:", "- web:"):  # not itself, not a web-only agent
            self.assertNotIn(gone, tool["description"])
        names = [t["name"] for t in self.call(self.task("notion")["id"], "tools/list")["result"]["tools"]]
        self.assertEqual(names, ["ask_agent", "request_deletion"])
        deep = self.peer("b" * 12, agent="planner", parent=job["id"], root=job["id"], depth=P.MAX_DEPTH)
        self.assertEqual(self.call(deep["id"], "tools/list")["result"]["tools"], [])

    def test_tool_calls(self):
        job = self.task()
        with mock.patch.object(A, "execute", answer("Friday")):
            res = self.call(job["id"], "tools/call", {"name": "ask_agent", "arguments": {"agent": "planner", "message": "When?"}})["result"]
        self.assertEqual((res["isError"], res["content"][0]["text"]), (False, "Answer from Planner:\nFriday"))
        res = self.call(job["id"], "tools/call", {"name": "request_deletion", "arguments": {"kind": "page", "id": "x", "why": "y"}})["result"]
        self.assertTrue(res["isError"])
        self.assertIn("Unknown tool", res["content"][0]["text"])  # only the Notion agent has it
        self.assertEqual(P.delete_request(self.cfg, job["id"], "page", "x", "y"), (False, "Only the Notion agent can ask for a deletion."))

    def test_serve_reads_lines_skips_garbage_and_survives_a_broken_call(self):
        job = self.task()
        lines = [b"not json\n", b"[1]\n", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode() + b"\n",
                 json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).encode() + b"\n"]
        out = io.BytesIO()
        with mock.patch.object(P, "tools", side_effect=RuntimeError("boom")):
            P.serve(self.cfg, job["id"], stdin=iter(lines), stdout=out)
        replies = [json.loads(ln) for ln in out.getvalue().decode().splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2])
        self.assertTrue(replies[1]["result"]["isError"])
        self.assertIn("RuntimeError", replies[1]["result"]["content"][0]["text"])


class RunTests(PeerCase):
    """What a run gets: the servers, the allow list, the guards, the environment (the token only for the Notion run)."""

    def agent(self, aid, **kw):
        return replace(next(a for a in A.load_agents(self.cfg.agents_file) if a.id == aid), **kw)

    def test_servers_of_a_run(self):
        self.assertEqual(A.servers_for(self.cfg, self.agent("research")), {})                 # no job: a plain run
        self.assertEqual(list(A.servers_for(self.cfg, self.agent("research", job="a" * 12))), ["starlane"])
        self.assertEqual(A.servers_for(self.cfg, self.agent("web", job="a" * 12)), {})        # web-only: never
        with self.assertRaises(A.Refused) as ctx:
            A.servers_for(self.cfg, self.agent("notion", job="a" * 12))
        self.assertIn("notion-connect", str(ctx.exception))
        entry = {"type": "stdio", "command": "node", "args": ["cli.mjs"]}
        with mock.patch.object(N, "mcp_server", return_value=entry):
            self.assertEqual(A.servers_for(self.cfg, self.agent("notion", job="a" * 12)), {"starlane": mock.ANY, "notion": entry})

    def test_command_of_the_notion_run(self):
        servers = {"starlane": {"type": "stdio", "command": "py", "args": []}, "notion": {"type": "stdio", "command": "node", "args": []}}
        cmd = A.claude_command("claude", self.agent("notion", job="a" * 12), "sys", servers)
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read")                              # Notion is no built-in tool
        self.assertEqual(json.loads(cmd[cmd.index("--mcp-config") + 1]), {"mcpServers": servers})
        allowed = cmd[cmd.index("--allowedTools") + 1:]
        self.assertIn("mcp__starlane__ask_agent", allowed)
        self.assertIn("mcp__notion__API-patch-page", allowed)
        self.assertNotIn("mcp__notion__API-delete-a-block", allowed)
        hooks = json.loads(cmd[cmd.index("--settings") + 1])["hooks"]
        self.assertEqual([h["matcher"] for h in hooks["PreToolUse"]], ["mcp__notion__.*"])
        self.assertIn("notionguard.py", hooks["PreToolUse"][0]["hooks"][0]["command"])
        self.assertIn("--strict-mcp-config", cmd)
        plain = A.claude_command("claude", self.agent("research"), "sys")
        self.assertNotIn("--mcp-config", plain)
        self.assertNotIn("--settings", plain)

    def test_rules_tell_who_to_ask_for_notion(self):
        rules = A.rules(self.agent("research", job="a" * 12), "2026-10-13", "Kim", notion="notion")
        self.assertIn("ask_agent", rules)
        self.assertIn('For anything in Notion, ask "notion"', rules)
        self.assertNotIn("ask_agent", A.rules(self.agent("research"), "2026-10-13", "Kim"))                  # no job: no tools
        self.assertNotIn("ask_agent", A.rules(self.agent("research", job="a" * 12, depth=2), "2026-10-13", "Kim"))
        own = A.rules(self.agent("notion", job="a" * 12), "2026-10-13", "Kim", notion="notion")
        self.assertNotIn('ask "notion"', own)
        self.assertIn("request_deletion", own)

    def spawn(self, agent):
        proc = mock.MagicMock(returncode=0)
        proc.communicate.return_value = ("Answer", "")
        envs = []

        def popen(cmd, **kw):
            envs.append(kw["env"])
            if kw["env"].get("AOS_NOTION_STATE"):  # what the guard's post hook writes during the run
                with open(kw["env"]["AOS_NOTION_STATE"] + ".changes", "w", encoding="utf-8") as fh:
                    fh.write(json.dumps({"tool": "patch-page", "target": "p1"}) + "\nbroken\n")
            return proc

        with mock.patch.object(A, "find_claude", return_value=("claude.exe", "")), mock.patch.object(A.subprocess, "Popen", side_effect=popen), \
                mock.patch.object(N, "mcp_server", return_value={"type": "stdio", "command": "node", "args": []}), \
                mock.patch.dict("os.environ", {"NOTION_TOKEN": "ntn_" + "a" * 30}):
            res = A.execute(self.cfg, agent, "x")
        return res, (envs[0] if envs else None)

    def test_only_the_notion_run_holds_the_token_and_its_changes_reach_the_job(self):
        res, env = self.spawn(self.agent("notion", job="a" * 12))
        self.assertEqual(env["NOTION_TOKEN"], "ntn_" + "a" * 30)
        self.assertEqual(env["AOS_PEER_JOB"], "a" * 12)
        self.assertEqual(res[3]["notion_changes"], [{"tool": "patch-page", "target": "p1"}])
        res, env = self.spawn(self.agent("research", job="a" * 12))
        self.assertNotIn("NOTION_TOKEN", env)
        self.assertNotIn("notion_changes", res[3])
        self.assertEqual(list((self.cfg.jobs_log.parent / "guard").iterdir()), [])  # the run's files are gone
