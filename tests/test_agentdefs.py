"""Custom agents: create, change, delete (aos/agentdefs.py) via module, server and terminal."""

import contextlib
import http.client
import io
import json
import threading
import tomllib
import unittest
from datetime import datetime
from unittest import mock

from aos import agentdefs as AD
from aos import agents as A
from aos import cli
from aos import server as SV
from tests.helpers import TempVaultCase

BUILTIN = """
[atlas]
default = "research"

# This comment must survive
[[agent]]
id = "research"
name = "Research"
description = "Answer questions from the vault"
prompt = "agents/research.md"
keywords = ["search"]
"""

GOOD = {
    "name": "Trip Planner",
    "description": "Plans trips with route, budget and packing list. Not for visa questions.",
    "instructions": "## Identity\nYou are a trip planner.\n\n## Boundaries\nYou book nothing.",
    "access": "web",
    "keywords": "trip, vacation, packing list",
    "examples": ["Plan three days in Lisbon on a 300 euro budget", "What belongs on a packing list for Iceland?"],
}


class DefsCase(TempVaultCase):
    def setUp(self):
        super().setUp()
        (self.root / "agents").mkdir()
        (self.root / "agents" / "research.md").write_text("# Research\nYou search.\n", encoding="utf-8")
        (self.root / "agents.toml").write_text(BUILTIN, encoding="utf-8")
        self.builtin_bytes = (self.root / "agents.toml").read_bytes()

    def local(self):
        return tomllib.loads(AD.local_file(self.cfg).read_text(encoding="utf-8"))["agent"]

    def agent(self, aid):
        return next(a for a in A.load_agents(self.cfg.agents_file) if a.id == aid)


class SlugAndValidationTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(AD.slugify("Trip Planner"), "trip-planner")
        self.assertEqual(AD.slugify("Prüfer für Übungen & Größe"), "pruefer-fuer-uebungen-groesse")  # umlauts are transliterated
        self.assertEqual(AD.slugify("  --  "), "agent")
        self.assertEqual(AD.slugify("日本語"), "agent")
        self.assertLessEqual(len(AD.slugify("a" * 200)), 40)
        self.assertTrue(A.ID_RE.match(AD.slugify("§$% Test 2")))

    def test_valid_spec_is_normalized(self):
        s = AD.parse_spec({**GOOD, "name": "  Trip   Planner ", "keywords": "Trip, VACATION,trip"})
        self.assertEqual(s.name, "Trip Planner")
        self.assertEqual(s.keywords, ("trip", "vacation"))  # lower case, without duplicates
        self.assertEqual(s.group, AD.CUSTOM_GROUP)
        self.assertEqual(AD.CUSTOM_GROUP, "Custom")
        self.assertEqual((s.model, s.access, s.timeout_s, s.max_runs_per_day, s.enabled), ("sonnet", "web", 480, 20, True))
        self.assertEqual(AD.parse_spec({**GOOD, "access": "vault"}).timeout_s, A.DEFAULT_TIMEOUT_S)
        self.assertEqual(AD.parse_spec({**GOOD, "group": "   "}).group, AD.CUSTOM_GROUP)  # blank group: the default

    def test_every_invalid_field_is_a_400_with_a_readable_message(self):
        bad = {
            "name": ["", "   ", "x" * 41, None, "a\x00b"],
            "description": ["short", "x" * 281, None],
            "instructions": ["", "too short", "x" * (AD.INSTR_MAX + 1), None, "A prompt with \x1b control chars and enough length"],
            "access": ["both", "bash", ""],
            "model": ["gpt-5", "opus; rm -rf", "--dangerous"],
            "keywords": ["a", "x" * 31, [1, 2], ",".join(f"word{i}" for i in range(13))],
            "examples": ["a\nb\nc\nd\ne", ["x" * 201], [3]],
            "timeout_s": [5, 901, "300", True, 3.5],
            "max_runs_per_day": [0, 201, "5", False],
            "enabled": ["yes", 1],
            "group": ["g" * 41],
        }
        for field, values in bad.items():
            for value in values:
                with self.assertRaises(A.Refused, msg=f"{field}={value!r}") as ctx:
                    AD.parse_spec({**GOOD, field: value})
                self.assertEqual(ctx.exception.code, 400)
                self.assertTrue(str(ctx.exception))

    def test_secret_in_prompt_is_refused_and_not_echoed(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        with self.assertRaises(A.Refused) as ctx:
            AD.parse_spec({**GOOD, "instructions": f"You are a helper. Use the key {secret} for everything."})
        self.assertNotIn(secret, str(ctx.exception))

    def test_non_dict_is_refused(self):
        for raw in (None, [], "x", 3):
            with self.assertRaises(A.Refused):
                AD.parse_spec(raw)

    def test_lone_surrogates_cannot_reach_the_file(self):
        with self.assertRaises(A.Refused):
            AD.parse_spec({**GOOD, "name": "Test\ud800"})

    def test_template_has_the_three_english_sections(self):
        for heading in ("## Identity", "## Working method", "## Boundaries"):
            self.assertIn(heading, AD.TEMPLATE)


class CreateTests(DefsCase):
    def test_create_writes_prompt_and_local_file_and_agent_is_loaded(self):
        a = AD.create(self.cfg, GOOD)
        self.assertEqual((a.id, a.name, a.group, a.custom), ("trip-planner", "Trip Planner", "Custom", True))
        self.assertEqual(a.tools, A.WEB_TOOLS)  # web, no vault: never both
        self.assertEqual(a.keywords, ("trip", "vacation", "packing list"))
        self.assertEqual(len(a.examples), 2)
        self.assertEqual(a.prompt_file, (self.root / "agents" / "local" / "trip-planner.md").resolve())
        text = a.prompt_file.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Trip Planner\n\n## Identity"))
        entry = self.local()[0]
        self.assertEqual(entry["prompt"], "agents/local/trip-planner.md")
        self.assertNotIn("custom", entry)  # the origin follows from the file
        self.assertTrue(AD.local_file(self.cfg).read_text(encoding="utf-8").startswith("# Custom agents"))

    def test_vault_agent_gets_only_vault_tools(self):
        a = AD.create(self.cfg, {**GOOD, "access": "vault"})
        self.assertEqual(a.tools, A.VAULT_TOOLS)
        self.assertFalse(a.web)

    def test_shipped_file_is_never_touched(self):
        a = AD.create(self.cfg, GOOD)
        AD.update(self.cfg, a.id, {"description": "Plans trips very thoroughly, with a budget."})
        AD.delete(self.cfg, a.id)
        self.assertEqual((self.root / "agents.toml").read_bytes(), self.builtin_bytes)
        self.assertIn(b"# This comment must", (self.root / "agents.toml").read_bytes())

    def test_builtin_agents_stay_not_custom(self):
        AD.create(self.cfg, GOOD)
        self.assertFalse(self.agent("research").custom)
        board = {r["id"]: r for r in A.board(self.cfg)}
        self.assertTrue(board["trip-planner"]["custom"])
        self.assertEqual(board["trip-planner"]["examples"], list(GOOD["examples"]))
        self.assertFalse(board["research"]["custom"])

    def test_id_collisions_get_a_suffix_and_explicit_ids_are_strict(self):
        self.assertEqual(AD.create(self.cfg, {**GOOD, "name": "Research"}).id, "research-2")
        self.assertEqual(AD.create(self.cfg, {**GOOD, "name": "Research"}).id, "research-3")
        self.assertEqual(AD.create(self.cfg, {**GOOD, "name": "Atlas"}).id, "custom-atlas")  # reserved
        self.assertEqual(AD.create(self.cfg, {**GOOD, "name": "Skill Demo"}).id, "custom-skill-demo")  # reserved prefix
        with self.assertRaises(A.Refused) as ctx:
            AD.create(self.cfg, GOOD, agent_id="research")
        self.assertEqual(ctx.exception.code, 409)
        for bad in ("atlas", "atlas-x", "skill-x", "With Spaces", "../etc", "-x"):
            with self.assertRaises(A.Refused, msg=bad) as ctx:
                AD.create(self.cfg, GOOD, agent_id=bad)
            self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(AD.create(self.cfg, GOOD, agent_id="my-trips").id, "my-trips")

    def test_limit_of_custom_agents(self):
        with mock.patch.object(AD, "MAX_CUSTOM", 2):
            AD.create(self.cfg, {**GOOD, "name": "One"})
            AD.create(self.cfg, {**GOOD, "name": "Two"})
            with self.assertRaises(A.Refused) as ctx:
                AD.create(self.cfg, {**GOOD, "name": "Three"})
            self.assertEqual(ctx.exception.code, 409)

    def test_toml_special_characters_survive_the_round_trip(self):
        nasty = 'He says "hello" \\ and """three""" quotes, ümlauts, 日本, emoji 🙂 and \'single\''
        a = AD.create(self.cfg, {**GOOD, "name": "Test", "description": nasty + " (description)",
                                 "examples": [nasty], "keywords": 'a"b, c\\d'})
        got = self.agent(a.id)
        self.assertEqual(got.description, nasty + " (description)")
        self.assertEqual(got.examples, (nasty,))
        self.assertEqual(got.keywords, ('a"b', "c\\d"))

    def test_failed_validation_leaves_no_files_behind(self):
        with self.assertRaises(A.Refused):
            AD.create(self.cfg, {**GOOD, "model": "gpt-5"})
        self.assertFalse(AD.local_file(self.cfg).exists())
        self.assertFalse((self.root / "agents" / "local").exists())

    def test_failed_commit_rolls_back_prompt_and_file(self):
        AD.create(self.cfg, GOOD)
        before_toml = AD.local_file(self.cfg).read_bytes()
        real = A.load_agents
        calls = {"n": 0}

        def flaky(path):
            calls["n"] += 1
            if calls["n"] >= 2:  # 1: _unique_id, 2: the cross-check after writing
                raise A.AgentError("broken")
            return real(path)

        with mock.patch.object(A, "load_agents", flaky):
            with self.assertRaises(A.AgentError):
                AD.create(self.cfg, {**GOOD, "name": "Second"})
        self.assertEqual(AD.local_file(self.cfg).read_bytes(), before_toml)
        self.assertFalse((self.root / "agents" / "local" / "second.md").exists())

    def test_failed_first_commit_leaves_no_local_file(self):
        def broken(path):
            raise A.AgentError("broken")

        with mock.patch.object(AD, "_all_ids", return_value=set()), mock.patch.object(A, "load_agents", broken):
            with self.assertRaises(A.AgentError):
                AD.create(self.cfg, GOOD)
        self.assertFalse(AD.local_file(self.cfg).exists())
        self.assertFalse((self.root / "agents" / "local" / "trip-planner.md").exists())

    def test_atlas_routes_by_the_keywords_of_a_custom_agent(self):
        AD.create(self.cfg, GOOD)
        agent_id, why = A.route(self.cfg, "I am planning a vacation in Portugal", now=datetime(2026, 10, 9, 7, 0))
        self.assertEqual(agent_id, "trip-planner")
        self.assertIn("vacation", why)

    def test_custom_agent_can_run_with_a_fake_runner(self):
        AD.create(self.cfg, GOOD)
        seen = []

        def runner(cfg, agent, instruction):
            seen.append((agent.id, agent.tools, agent.model))
            return "ok", "A plan", ""

        job = A.submit(self.cfg, "trip-planner", "Lisbon, 3 days", wait=True, runner=runner)
        self.assertEqual(job["status"], "ok")
        self.assertEqual(seen, [("trip-planner", ("WebSearch", "WebFetch"), "sonnet")])


class UpdateDeleteTests(DefsCase):
    def setUp(self):
        super().setUp()
        self.a = AD.create(self.cfg, GOOD)

    def test_update_changes_only_given_fields(self):
        got = AD.update(self.cfg, self.a.id, {"model": "opus", "group": "Travel", "enabled": False})
        self.assertEqual((got.model, got.group, got.enabled), ("opus", "Travel", False))
        self.assertEqual(got.description, GOOD["description"])
        self.assertEqual(got.tools, A.WEB_TOOLS)
        self.assertEqual(got.keywords, ("trip", "vacation", "packing list"))

    def test_update_can_switch_access_never_to_both(self):
        got = AD.update(self.cfg, self.a.id, {"access": "vault"})
        self.assertEqual(got.tools, A.VAULT_TOOLS)
        with self.assertRaises(A.Refused):
            AD.update(self.cfg, self.a.id, {"access": "both"})

    def test_invalid_update_changes_nothing(self):
        before = AD.local_file(self.cfg).read_bytes()
        with self.assertRaises(A.Refused):
            AD.update(self.cfg, self.a.id, {"model": "gpt-5"})
        self.assertEqual(AD.local_file(self.cfg).read_bytes(), before)

    def test_hand_edited_prompt_survives_updates_of_other_fields(self):
        self.a.prompt_file.write_text("# Trip Planner\n\nWritten by hand, completely different.\n", encoding="utf-8")
        AD.update(self.cfg, self.a.id, {"description": "A new description that is long enough."})
        self.assertIn("Written by hand", self.a.prompt_file.read_text(encoding="utf-8"))
        # and the form gets the hand-written text back
        self.assertEqual(AD.read(self.cfg, self.a.id)["instructions"], "Written by hand, completely different.")

    def test_changed_instructions_rewrite_the_prompt(self):
        AD.update(self.cfg, self.a.id, {"instructions": "## Identity\nYou are now something else, in detail."})
        text = self.a.prompt_file.read_text(encoding="utf-8")
        self.assertIn("something else", text)
        self.assertNotIn("You book nothing", text)

    def test_renaming_rewrites_the_prompt_heading_but_keeps_the_id(self):
        got = AD.update(self.cfg, self.a.id, {"name": "Travel Agent"})
        self.assertEqual((got.id, got.name), ("trip-planner", "Travel Agent"))
        self.assertTrue(got.prompt_file.read_text(encoding="utf-8").startswith("# Travel Agent\n\n## Identity"))

    def test_unknown_keys_in_the_local_file_are_preserved(self):
        path = AD.local_file(self.cfg)
        path.write_text(path.read_text(encoding="utf-8").replace("enabled = true", "enabled = true\nmixed = false"), encoding="utf-8")
        AD.update(self.cfg, self.a.id, {"model": "haiku"})
        self.assertIn("mixed", self.local()[0])

    def test_read_returns_every_editable_field(self):
        r = AD.read(self.cfg, self.a.id)
        self.assertEqual(r["access"], "web")
        self.assertEqual(r["name"], "Trip Planner")
        self.assertIn("You book nothing.", r["instructions"])
        self.assertEqual(set(r), {"id", "name", "description", "instructions", "access", "group", "model", "keywords",
                                  "examples", "timeout_s", "max_runs_per_day", "enabled"})
        # round trip: what read() returns is valid input for update()
        AD.update(self.cfg, self.a.id, {k: v for k, v in r.items() if k != "id"})

    def test_builtin_and_unknown_agents_cannot_be_changed(self):
        for fn in (lambda: AD.update(self.cfg, "research", {"model": "opus"}), lambda: AD.delete(self.cfg, "research"),
                   lambda: AD.read(self.cfg, "research")):
            with self.assertRaises(A.Refused) as ctx:
                fn()
            self.assertEqual(ctx.exception.code, 403)
        for fn in (lambda: AD.update(self.cfg, "does-not-exist", {}), lambda: AD.delete(self.cfg, "does-not-exist"),
                   lambda: AD.read(self.cfg, "does-not-exist")):
            with self.assertRaises(KeyError):
                fn()

    def test_delete_removes_entry_prompt_and_empty_local_file(self):
        second = AD.create(self.cfg, {**GOOD, "name": "Second Agent"})
        AD.delete(self.cfg, self.a.id)
        self.assertFalse(self.a.prompt_file.exists())
        self.assertEqual([e["id"] for e in self.local()], [second.id])
        AD.delete(self.cfg, second.id)
        self.assertFalse(AD.local_file(self.cfg).exists())
        self.assertEqual([a.id for a in A.load_agents(self.cfg.agents_file)], ["research"])

    def test_busy_agent_cannot_be_deleted(self):
        A._append(self.cfg, {"id": "a" * 12, "agent": self.a.id, "status": "running",
                             "started": datetime.now().replace(microsecond=0).isoformat(), "via": "cli"})
        with self.assertRaises(A.Refused) as ctx:
            AD.delete(self.cfg, self.a.id)
        self.assertEqual(ctx.exception.code, 409)
        self.assertTrue(self.a.prompt_file.exists())

    def test_corrupt_local_file_is_a_clear_error(self):
        AD.local_file(self.cfg).write_text("not toml [", encoding="utf-8")
        with self.assertRaises(A.AgentError) as ctx:
            A.load_agents(self.cfg.agents_file)
        self.assertIn("agents.local.toml", str(ctx.exception))

    def test_duplicate_id_between_files_is_rejected_on_load(self):
        AD.local_file(self.cfg).write_text(
            '[[agent]]\nid = "research"\nprompt = "agents/research.md"\n', encoding="utf-8")
        with self.assertRaises(A.AgentError):
            A.load_agents(self.cfg.agents_file)

    def test_local_file_cannot_smuggle_forbidden_tools_or_paths(self):
        AD.local_file(self.cfg).write_text(
            '[[agent]]\nid = "evil"\ntools = ["Bash"]\nprompt = "agents/research.md"\n', encoding="utf-8")
        with self.assertRaises(A.AgentError):
            A.load_agents(self.cfg.agents_file)
        AD.local_file(self.cfg).write_text('[[agent]]\nid = "evil"\nprompt = "../aos.toml"\n', encoding="utf-8")
        with self.assertRaises(A.AgentError):
            A.load_agents(self.cfg.agents_file)
        AD.local_file(self.cfg).write_text(
            '[[agent]]\nid = "evil"\ntools = ["Read", "WebFetch"]\nprompt = "agents/research.md"\n', encoding="utf-8")
        with self.assertRaises(A.AgentError):  # vault + web without `mixed` is refused here too
            A.load_agents(self.cfg.agents_file)


class ServerDefsTests(DefsCase):
    def setUp(self):
        super().setUp()
        self.httpd, self.state = SV.create_server(self.cfg, 0, token="t0k")
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))

    def req(self, method, path, body=None, headers=None, token="t0k"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if token:
            h["X-AOS-Token"] = token
        h.update(headers or {})
        data = body if isinstance(body, (bytes, type(None))) else json.dumps(body).encode()
        conn.request(method, path, body=data, headers=h)
        resp = conn.getresponse()
        out = resp.read()
        conn.close()
        return resp.status, (json.loads(out) if out else None)

    def test_full_lifecycle_over_http(self):
        status, body = self.req("POST", "/api/agent-defs", GOOD)
        self.assertEqual(status, 201, body)
        self.assertEqual(body["agent"]["id"], "trip-planner")
        self.assertTrue(body["agent"]["custom"])
        self.assertTrue(body["agent"]["web"])
        status, body = self.req("GET", "/api/agent-defs/trip-planner")
        self.assertEqual(status, 200)
        self.assertIn("You book nothing.", body["agent"]["instructions"])
        status, body = self.req("POST", "/api/agent-defs/trip-planner", {"model": "opus"})
        self.assertEqual((status, body["agent"]["model"]), (200, "opus"))
        _, data = self.req("GET", "/api/data")
        self.assertIn("trip-planner", [a["id"] for a in data["agents"]])
        self.assertEqual(data["api"]["agent_defs"], "/api/agent-defs")
        self.assertEqual(self.req("DELETE", "/api/agent-defs/trip-planner")[0], 200)
        self.assertEqual(self.req("GET", "/api/agent-defs/trip-planner")[0], 404)

    def test_error_codes(self):
        self.assertEqual(self.req("POST", "/api/agent-defs", {**GOOD, "model": "gpt-5"})[0], 400)
        self.assertEqual(self.req("POST", "/api/agent-defs", {**GOOD, "access": "both"})[0], 400)
        self.assertEqual(self.req("POST", "/api/agent-defs", {**GOOD, "id": "research"})[0], 409)
        self.assertEqual(self.req("POST", "/api/agent-defs/research", {"model": "opus"})[0], 403)
        self.assertEqual(self.req("DELETE", "/api/agent-defs/research")[0], 403)
        self.assertEqual(self.req("GET", "/api/agent-defs/research")[0], 403)
        self.assertEqual(self.req("POST", "/api/agent-defs/nope", {"model": "opus"})[0], 404)
        self.assertEqual(self.req("DELETE", "/api/agent-defs/nope")[0], 404)
        self.assertEqual(self.req("POST", "/api/agent-defs", b"not json")[0], 400)
        self.assertEqual(self.req("POST", "/api/agent-defs", {**GOOD, "instructions": "x" * (SV.MAX_BODY + 10)})[0], 413)

    def test_guards(self):
        for method, path in (("POST", "/api/agent-defs"), ("POST", "/api/agent-defs/x"), ("DELETE", "/api/agent-defs/x"),
                             ("GET", "/api/agent-defs/x")):
            body = GOOD if method == "POST" else None
            self.assertEqual(self.req(method, path, body, token=None)[0], 401, (method, path))
            self.assertEqual(self.req(method, path, body, token="wrong")[0], 401)
            self.assertEqual(self.req(method, path, body, {"Origin": "http://evil.example"})[0], 403)
            self.assertEqual(self.req(method, path, body, {"Host": "evil.example"})[0], 403)
        self.assertFalse(AD.local_file(self.cfg).exists())  # none of this created anything

    def test_other_methods_and_paths_stay_closed(self):
        self.assertEqual(self.req("PUT", "/api/agent-defs/x", {})[0], 405)
        self.assertEqual(self.req("PATCH", "/api/agent-defs/x", {})[0], 405)
        self.assertEqual(self.req("DELETE", "/api/run/digest")[0], 405)
        self.assertEqual(self.req("DELETE", "/")[0], 405)
        self.assertEqual(self.req("POST", "/api/agent-defs/../etc", {})[0], 404)


class CliDefsTests(DefsCase):
    def run_cli(self, *args, tty=False):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("sys.stdin.isatty", return_value=tty):
            code = cli.main(["--config", str(self.cfg_path), *args])
        return code, out.getvalue()

    def test_agent_new_with_options_then_listed_then_removed(self):
        code, out = self.run_cli("agent-new", "--name", "Trip Planner", "--description", GOOD["description"],
                                 "--instructions", GOOD["instructions"], "--web", "--keyword", "trip", "--keyword", "vacation",
                                 "--example", "Plan Lisbon")
        self.assertEqual(code, 0, out)
        self.assertIn("trip-planner", out)
        a = self.agent("trip-planner")
        self.assertEqual((a.tools, a.keywords, a.examples), (A.WEB_TOOLS, ("trip", "vacation"), ("Plan Lisbon",)))
        code, out = self.run_cli("agents")
        self.assertIn("(custom)", out)
        code, out = self.run_cli("agent-rm", "trip-planner", "--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual([x.id for x in A.load_agents(self.cfg.agents_file)], ["research"])

    def test_instructions_file(self):
        f = self.root / "prompt.md"
        f.write_text("## Identity\nYou are a tester with enough text.", encoding="utf-8")
        code, out = self.run_cli("agent-new", "--name", "Tester", "--description", "Tests things thoroughly and honestly.",
                                 "--instructions-file", str(f))
        self.assertEqual(code, 0, out)
        self.assertIn("a tester", self.agent("tester").prompt_file.read_text(encoding="utf-8"))

    def test_agents_list_stays_aligned_for_long_ids(self):
        code, out = self.run_cli("agent-new", "--name", "Travel Planner Deluxe", "--description", GOOD["description"],
                                 "--instructions", GOOD["instructions"])
        self.assertEqual(code, 0, out)
        code, out = self.run_cli("agents")
        rows = [ln for ln in out.splitlines() if " today" in ln]
        self.assertEqual(len(rows), 2)
        self.assertIn("travel-planner-deluxe", out)
        self.assertEqual(len({ln.index(" ready") for ln in rows}), 1)  # the state column starts at the same place

    def test_refusals_have_exit_codes(self):
        code, out = self.run_cli("agent-new", "--name", "X", "--description", "short", "--instructions", "too short")
        self.assertEqual(code, 3)
        self.assertIn("Refused", out)
        self.assertEqual(self.run_cli("agent-new")[0], 2)  # no terminal, no --name
        self.assertEqual(self.run_cli("agent-rm", "research", "--yes")[0], 3)
        self.assertEqual(self.run_cli("agent-rm", "does-not-exist", "--yes")[0], 2)
        self.assertEqual(self.run_cli("agent-rm", "research")[0], 3)

    def test_template_and_interactive_dialog(self):
        code, out = self.run_cli("agent-new", "--template")
        self.assertEqual(code, 0)
        for heading in ("## Identity", "## Working method", "## Boundaries"):
            self.assertIn(heading, out)
        answers = iter(["Dialog Agent", "Answers questions in a dialog, in detail.", "vault", "", "", "dialog, question",
                        "You are a dialog agent and answer in detail.", ""])
        with mock.patch("builtins.input", lambda *_: next(answers)):
            code, out = self.run_cli("agent-new", tty=True)
        self.assertEqual(code, 0, out)
        a = self.agent("dialog-agent")
        self.assertEqual((a.tools, a.group, a.model, a.keywords), (A.VAULT_TOOLS, "Custom", "sonnet", ("dialog", "question")))


if __name__ == "__main__":
    unittest.main()
