"""Skills, cost, artifact library, skill routines: behaviour, limits, server endpoints, CLI."""

import contextlib
import dataclasses
import http.client
import io
import json
import os
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest import mock

from aos import agents as A
from aos import artifacts as AR
from aos import cli
from aos import routines as R
from aos import server as SV
from aos import skills as S
from aos.config import PROJECT_ROOT
from aos.dashboard import build_data
from tests.helpers import TempVaultCase

SECRET = "sk-abcdefghijklmnopqrstuvwxyz123456"


def skill_md(name="Demo", desc="Does demo", extra=""):
    return f"---\nname: {name}\ndescription: {desc}\n{extra}---\n# {name}\nDo something useful.\n"


def metered(answer="Answer", cost=0.0123):
    def runner(cfg, agent, instruction):
        return "ok", answer, "", {"cost_usd": cost, "tokens_in": 1200, "tokens_out": 80, "model_used": "claude-sonnet-x", "turns": 2}
    return runner


class SkillCase(TempVaultCase):
    def setUp(self):
        super().setUp()
        self.skills_dir = self.root / "skills"
        self.add_skill("demo", skill_md("Demo", "Does demo", "model: opus\neffort: high\n"), {"references/a.md": "A", "checklist.md": "B"})

    def add_skill(self, folder, text, refs=None, base=None):
        d = (base or self.skills_dir) / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text, encoding="utf-8")
        for rel, body in (refs or {}).items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(body, encoding="utf-8")


class DiscoverTests(SkillCase):
    def test_discovers_skill_with_defaults_and_refs(self):
        (sk,) = S.discover(self.cfg)
        self.assertEqual((sk.id, sk.name, sk.model, sk.effort, sk.source), ("demo", "Demo", "opus", "high", "project"))
        self.assertEqual(sk.refs, ("references/a.md", "checklist.md"))
        self.assertEqual(sk.description, "Does demo")

    def test_invalid_model_effort_fall_back_and_multiline_description(self):
        self.add_skill("two", "---\nname: Two\ndescription: >\nmodel: gpt-9\neffort: ultra\n---\n# Heading\nText\n")
        sk = S.get(self.cfg, "two")
        self.assertEqual((sk.model, sk.effort), (S.DEFAULT_MODEL, ""))
        self.assertEqual(sk.description, "Heading")

    def test_first_directory_wins_and_user_source(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        other = Path(tmp.name) / "userskills"  # outside the project folder
        self.add_skill("demo", skill_md("Foreign", "other"), base=other)
        self.add_skill("user-only", skill_md("Only", "x"), base=other)
        cfg = dataclasses.replace(self.cfg, skills_dirs=(self.skills_dir, other))
        found = {s.id: s for s in S.discover(cfg)}
        self.assertEqual(found["demo"].name, "Demo")  # project beats user
        self.assertEqual(found["user-only"].source, "user")

    def test_missing_dirs_and_junk_are_ignored(self):
        cfg = dataclasses.replace(self.cfg, skills_dirs=(self.root / "does-not-exist",))
        self.assertEqual(S.discover(cfg), [])
        (self.skills_dir / "no-skill-md").mkdir()
        (self.skills_dir / "Odd Ä!").mkdir()
        (self.skills_dir / "Odd Ä!" / "SKILL.md").write_text(skill_md("K"), encoding="utf-8")
        self.assertEqual([s.id for s in S.discover(self.cfg)], ["demo", "odd"])

    def test_symlinked_skill_is_not_followed(self):
        target = self.root / "outside"
        self.add_skill("secret", skill_md("Secret"), base=target)
        try:
            os.symlink(target / "secret", self.skills_dir / "linked", target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not allowed")
        self.assertEqual([s.id for s in S.discover(self.cfg)], ["demo"])

    def test_prompt_text_strips_frontmatter_lists_refs_and_truncates(self):
        sk = S.get(self.cfg, "demo")
        text = S.prompt_text(sk)
        self.assertNotIn("model: opus", text)
        self.assertIn("Do something useful.", text)
        self.assertIn("- references/a.md", text)
        self.assertIn("[… truncated", S.prompt_text(sk, limit=5))

    def test_prompt_fits_windows_command_line_even_with_many_quotes(self):
        body = '"' * 15_000 + "x" * 5_000
        self.add_skill("quotes", f"---\nname: Quotes\ndescription: d\n---\n{body}\n", {f"folder/file-{i}.md": "r" for i in range(40)})
        sk = S.get(self.cfg, "quotes")
        agent = A.skill_agent(self.cfg, sk, "sonnet", "")
        cmd = A.claude_command("C:/Users/x/.local/bin/claude.exe", agent, agent.system + A.rules(agent, "2026-10-10"))
        self.assertLess(len(subprocess.list2cmdline(cmd)), 30_000)
        self.assertIn("[… truncated", agent.system)

    def test_junction_is_not_followed(self):
        if os.name != "nt":
            self.skipTest("junctions exist only on Windows")
        import _winapi

        target = self.root / "outside2"
        self.add_skill("secret", skill_md("Secret"), base=target)
        try:
            _winapi.CreateJunction(str(target / "secret"), str(self.skills_dir / "junk"))
        except OSError:
            self.skipTest("junction not possible")
        self.assertEqual([s.id for s in S.discover(self.cfg)], ["demo"])

    def test_linked_reference_is_left_out(self):
        outside = self.root / "secret.txt"
        outside.write_text("secret", encoding="utf-8")
        try:
            os.symlink(outside, self.skills_dir / "demo" / "linked.md")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not allowed")
        self.assertNotIn("linked.md", S.get(self.cfg, "demo").refs)

    def test_shipped_skills_are_valid(self):
        cfg = dataclasses.replace(self.cfg, skills_dirs=(PROJECT_ROOT / "skills",))
        found = {s.id: s for s in S.discover(cfg)}
        self.assertEqual(set(found), {"weekly-plan", "vault-triage", "study-plan"})
        for s in found.values():
            self.assertTrue(s.refs, s.id)
            self.assertTrue(s.description, s.id)


class RunTests(SkillCase):
    def test_command_has_effort_adddir_json_and_stays_read_only(self):
        sk = S.get(self.cfg, "demo")
        agent = A.skill_agent(self.cfg, sk, "opus", "xhigh")
        cmd = A.claude_command("claude.exe", agent, "SYS")
        self.assertEqual(cmd[:4], ["claude.exe", "-p", "--output-format", "json"])
        self.assertEqual(cmd[cmd.index("--effort") + 1], "xhigh")
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], str(sk.dir))
        self.assertLess(cmd.index("--add-dir"), cmd.index("--max-budget-usd"))  # variadic: an option must follow
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1:], ["Read(./**)"])  # Grep/Glob not allowed bare
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Read,Grep,Glob")
        self.assertFalse(any(t in cmd for t in ("Bash", "Write", "Edit", "WebFetch")))

    def test_no_effort_flag_when_default(self):
        agent = A.skill_agent(self.cfg, S.get(self.cfg, "demo"), "sonnet", "")
        self.assertNotIn("--effort", A.claude_command("c", agent, "S"))

    def test_submit_records_skill_model_effort_cost(self):
        job = A.submit_skill(self.cfg, "demo", "Do something", wait=True, runner=metered())
        self.assertEqual((job["status"], job["agent"], job["skill"]), ("ok", "skill-demo", "demo"))
        self.assertEqual((job["model"], job["effort"]), ("opus", "high"))  # the skill's default
        self.assertEqual((job["cost_usd"], job["tokens_in"], job["model_used"]), (0.0123, 1200, "claude-sonnet-x"))
        again = A.submit_skill(self.cfg, "demo", "Again", model="haiku", effort="low", wait=True, runner=metered(cost=0.5))
        self.assertEqual((again["model"], again["effort"]), ("haiku", "low"))
        sp = A.spend(self.cfg)
        self.assertAlmostEqual(sp["today_usd"], 0.5123, places=4)
        self.assertEqual(sp["by_agent"][0], {"id": "skill-demo", "usd": 0.5123, "runs": 2})
        self.assertEqual(sp["week_runs"], 2)
        self.assertEqual(len(sp["days"]), 7)

    def test_agents_cannot_use_reserved_skill_prefix(self):
        (self.root / "agents").mkdir(exist_ok=True)
        (self.root / "agents" / "x.md").write_text("# X\n", encoding="utf-8")
        self.cfg.agents_file.write_text('[[agent]]\nid = "skill-demo"\nprompt = "agents/x.md"\n', encoding="utf-8")
        with self.assertRaises(A.AgentError):
            A.load_agents(self.cfg.agents_file)

    def test_non_string_model_effort_are_refused(self):
        for kw in ({"model": ["opus"]}, {"model": {"a": 1}}, {"effort": ["low"]}, {"effort": 5}):
            with self.assertRaises(A.Refused, msg=str(kw)):
                A.submit_skill(self.cfg, "demo", "x", runner=metered(), **kw)
        job = A.submit_skill(self.cfg, "demo", "x", model=None, effort=None, wait=True, runner=metered())  # null = the skill's default
        self.assertEqual((job["model"], job["effort"]), ("opus", "high"))

    def test_skill_shares_parallel_limit_with_agents(self):
        gate = threading.Event()

        def slow(cfg, agent, instruction):
            gate.wait(5)
            return "ok", "done", ""

        for i in range(A.MAX_PARALLEL):
            self.add_skill(f"s{i}", skill_md(f"S{i}"))
            A.submit_skill(self.cfg, f"s{i}", "x", runner=slow)
        with self.assertRaises(A.Refused) as ctx:
            A.submit_skill(self.cfg, "demo", "x", runner=slow)
        self.assertEqual(ctx.exception.code, 409)
        gate.set()
        for _ in range(100):
            if not any(r["busy"] for r in A.skills_board(self.cfg)):
                break
            time.sleep(0.05)

    def test_explicit_empty_effort_means_no_flag_not_skill_default(self):
        job = A.submit_skill(self.cfg, "demo", "x", effort="", wait=True, runner=metered())
        self.assertEqual(job["effort"], "")

    def test_refusals(self):
        with self.assertRaises(KeyError):
            A.submit_skill(self.cfg, "does-not-exist", "x", runner=metered())
        for kw in ({"model": "gpt-9"}, {"model": "--help"}, {"effort": "ultra"}, {"model": "opus; rm -rf"}):
            with self.assertRaises(A.Refused, msg=str(kw)) as ctx:
                A.submit_skill(self.cfg, "demo", "x", runner=metered(), **kw)
            self.assertEqual(ctx.exception.code, 400)
        with self.assertRaises(A.Refused) as ctx:
            A.submit_skill(self.cfg, "demo", "   ", runner=metered())
        self.assertEqual(ctx.exception.code, 400)

    def test_daily_cap_is_per_skill(self):
        cfg = dataclasses.replace(self.cfg, skills_cap=1)
        self.add_skill("second", skill_md("Second"))
        A.submit_skill(cfg, "demo", "one", wait=True, runner=metered())
        with self.assertRaises(A.Refused) as ctx:
            A.submit_skill(cfg, "demo", "two", wait=True, runner=metered())
        self.assertEqual(ctx.exception.code, 429)
        A.submit_skill(cfg, "second", "one", wait=True, runner=metered())  # another skill: its own cap

    def test_secret_in_answer_and_instruction_is_redacted(self):
        job = A.submit_skill(self.cfg, "demo", f"Use {SECRET}", wait=True, runner=metered(f"The key is {SECRET}"))
        self.assertNotIn(SECRET, json.dumps(job))
        self.assertNotIn(SECRET, self.cfg.jobs_log.read_text(encoding="utf-8"))

    def test_skills_board_shows_usage_and_last_run(self):
        A.submit_skill(self.cfg, "demo", "x", wait=True, runner=metered())
        (row,) = A.skills_board(self.cfg)
        self.assertEqual((row["runs_today"], row["busy"], row["last"]["status"], row["last"]["cost_usd"]), (1, False, "ok", 0.0123))
        self.assertEqual(row["refs"], ["references/a.md", "checklist.md"])
        self.assertEqual(row["source"], "project")

    def test_spend_ledger_ignores_garbage(self):
        self.cfg.spend_log.parent.mkdir(parents=True, exist_ok=True)
        today = datetime.now().date().isoformat()
        self.cfg.spend_log.write_text(
            f'{{"date":"{today}","agent":"research","skill":null,"usd":0.25}}\nbroken\n{{"date":"{today}","usd":"x"}}\n', encoding="utf-8")
        sp = A.spend(self.cfg)
        self.assertEqual((sp["today_usd"], sp["week_runs"]), (0.25, 1))
        self.assertEqual(sp["by_agent"][0]["id"], "research")


class ParseOutputTests(TempVaultCase):
    def test_success_json(self):
        out = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": " Hello ", "total_cost_usd": 0.01234567,
                          "num_turns": 3, "usage": {"input_tokens": 4, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 20,
                                                    "output_tokens": 7}, "modelUsage": {"claude-haiku-5-5": {}}})
        status, text, note, meta = A.parse_output(out)
        self.assertEqual((status, text, note), ("ok", "Hello", ""))
        self.assertEqual(meta, {"cost_usd": 0.0123, "tokens_in": 34, "tokens_out": 7, "model_used": "claude-haiku-5-5", "turns": 3})

    def test_error_budget_and_plain_text(self):
        status, text, note, meta = A.parse_output(json.dumps({"subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 1.0}))
        self.assertEqual((status, text, note, meta["cost_usd"]), ("failed", "", "error_max_budget_usd", 1.0))
        self.assertEqual(A.parse_output("just text")[:2], ("ok", "just text"))
        self.assertEqual(A.parse_output("   ")[0], "failed")
        self.assertEqual(A.parse_output(json.dumps({"result": "", "total_cost_usd": 0.1}))[0], "failed")
        stream = json.dumps([{"type": "system"}, {"type": "result", "result": "End", "total_cost_usd": 0.2}])
        self.assertEqual(A.parse_output(stream)[:2], ("ok", "End"))


class ExecuteJsonTests(SkillCase):
    def run_execute(self, stdout, returncode=0, stderr=""):
        agent = A.skill_agent(self.cfg, S.get(self.cfg, "demo"), "haiku", "low")
        proc = mock.MagicMock(returncode=returncode)
        proc.communicate.return_value = (stdout, stderr)
        with mock.patch.object(A, "find_claude", return_value=("claude.exe", "")), \
                mock.patch.object(A.subprocess, "Popen", return_value=proc) as popen:
            return A.execute(self.cfg, agent, "Task"), popen.call_args.args[0]

    def test_json_result_carries_cost_into_the_job(self):
        out = json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Done", "total_cost_usd": 0.002,
                          "usage": {"input_tokens": 5, "output_tokens": 9}, "modelUsage": {"claude-haiku-5-5": {}}})
        (status, text, note, meta), cmd = self.run_execute(out)
        self.assertEqual((status, text, note, meta["cost_usd"], meta["model_used"]), ("ok", "Done", "", 0.002, "claude-haiku-5-5"))
        self.assertEqual(cmd[cmd.index("--effort") + 1], "low")
        self.assertIn("Do something useful.", cmd[cmd.index("--append-system-prompt") + 1])  # SKILL.md is the system prompt

    def test_failed_exit_keeps_cost_and_reason(self):
        out = json.dumps({"subtype": "error_max_budget_usd", "is_error": True, "total_cost_usd": 1.01})
        (status, _, note, meta), _ = self.run_execute(out, returncode=1)
        self.assertEqual((status, note, meta["cost_usd"]), ("failed", "error_max_budget_usd", 1.01))
        (status, _, note, meta), _ = self.run_execute("", returncode=1, stderr="Login required")
        self.assertEqual((status, note, meta), ("failed", "Login required", {}))

    def test_failed_run_is_still_billed_in_the_ledger(self):
        out = json.dumps({"subtype": "error_max_turns", "is_error": True, "total_cost_usd": 0.4})
        with mock.patch.object(A, "execute", return_value=A.parse_output(out)):
            job = A.submit_skill(self.cfg, "demo", "expensive", wait=True)
        self.assertEqual((job["status"], job["cost_usd"]), ("failed", 0.4))
        self.assertAlmostEqual(A.spend(self.cfg)["today_usd"], 0.4, places=4)


class ArtifactTests(SkillCase):
    def setUp(self):
        super().setUp()
        art = self.cfg.data_dir / "artifacts"
        art.mkdir(parents=True)
        (art / "report.html").write_text(
            "<html><head><title>My report &amp; plan</title><style>x{}</style></head><body><h1>Ignored</h1><p>Hello world</p></body></html>",
            encoding="utf-8")
        self.cfg.out_dir.mkdir(parents=True)
        (self.cfg.out_dir / "dashboard.html").write_text("<title>Dashboard</title>", encoding="utf-8")
        digest = self.cfg.vault / self.cfg.digest_dir
        digest.mkdir(parents=True, exist_ok=True)
        (digest / "latest.md").write_text(f"---\ntype: digest\n---\n# Digest Friday\n\nSecret {SECRET} and text.\n", encoding="utf-8")
        A.submit_skill(self.cfg, "demo", "Plan the week", wait=True, runner=metered("# Plan\n\nMonday: study"))

    def test_listing_sources_titles_and_exclusions(self):
        items = AR.list_artifacts(self.cfg)
        by_kind = {i["kind"]: i for i in items}
        self.assertEqual(by_kind["html"]["title"], "My report & plan")
        self.assertIn("Hello world", by_kind["html"]["excerpt"])
        self.assertNotIn("x{}", by_kind["html"]["excerpt"])
        self.assertEqual(by_kind["md"]["title"], "Digest Friday")
        self.assertEqual(by_kind["job"]["group"], "Skill: demo")
        self.assertEqual(by_kind["job"]["title"], "Plan the week")
        self.assertFalse(any(i["title"] == "Dashboard" for i in items))
        self.assertEqual(len({i["id"] for i in items}), len(items))
        self.assertEqual([i["mtime"] for i in items], sorted((i["mtime"] for i in items), reverse=True))

    def test_read_returns_content_and_redacts(self):
        items = {i["kind"]: i for i in AR.list_artifacts(self.cfg)}
        html = AR.read_artifact(self.cfg, items["html"]["id"])
        self.assertIn("<p>Hello world</p>", html["content"])
        md = AR.read_artifact(self.cfg, items["md"]["id"])
        self.assertNotIn(SECRET, md["content"])
        self.assertNotIn(SECRET, json.dumps(AR.list_artifacts(self.cfg)))
        job = AR.read_artifact(self.cfg, items["job"]["id"])
        self.assertTrue(job["content"].startswith("# Plan"))

    def test_ids_cannot_reach_arbitrary_files(self):
        for bad in ("../../etc/passwd", "f-../..", "f-" + "0" * 12, "j-" + "0" * 12, "", None, 5, "F-ABCDEF123456", "f-abcdef1234567"):
            self.assertIsNone(AR.read_artifact(self.cfg, bad), bad)

    def test_oversized_file_is_not_served(self):
        big = self.cfg.data_dir / "artifacts" / "big.html"
        big.write_text("<title>Big</title>" + "x" * (AR.MAX_READ + 10), encoding="utf-8")
        item = next(i for i in AR.list_artifacts(self.cfg) if i["title"] == "Big")
        self.assertIsNone(AR.read_artifact(self.cfg, item["id"]))

    def test_failed_jobs_are_not_artifacts(self):
        A.submit_skill(self.cfg, "demo", "broken", wait=True, runner=lambda c, a, i: ("failed", "", "boom"))
        self.assertFalse(any(i["title"] == "broken" for i in AR.list_artifacts(self.cfg)))

    def test_dashboard_data_contract(self):
        d = build_data(self.cfg)
        self.assertEqual([s["id"] for s in d["skills"]], ["demo"])
        self.assertEqual(d["options"], {"models": ["haiku", "sonnet", "opus", "fable"], "efforts": ["low", "medium", "high", "xhigh", "max"]})
        self.assertEqual(set(d["spend"]), {"today_usd", "week_usd", "month_usd", "week_runs", "days", "by_agent"})
        self.assertTrue(d["artifacts"])
        self.assertEqual(set(d["artifacts"][0]), {"id", "title", "kind", "group", "path", "mtime", "size", "excerpt"})
        self.assertNotIn(SECRET, json.dumps(d))


class SkillRoutineTests(SkillCase):
    def routine(self, extra):
        (self.root / "r.toml").write_text(
            '[[routine]]\nid = "plan"\nschedule = "weekly mon 07:00"\ncommand = "skill"\nenabled = false\n' + extra, encoding="utf-8")
        return R.load_routines(self.root / "r.toml")[0]

    def test_valid_skill_routine_builds_argv(self):
        r = self.routine('skill = "demo"\ninstruction = "Plan for this week"\nmodel = "haiku"\neffort = "low"\n')
        self.assertEqual(r.argv()[r.argv().index("aos") + 1:], ["skill", "--via", "routine", "--model", "haiku", "--effort", "low", "--", "demo", "Plan for this week"])

    def test_skill_routine_timeout_never_below_skill_run_limit(self):
        self.assertEqual(R.SKILL_MIN_TIMEOUT_S, A.MAX_TIMEOUT_S + 60)
        self.assertEqual(self.routine('skill = "demo"\ninstruction = "x"\n').timeout_s, R.SKILL_MIN_TIMEOUT_S)  # default
        self.assertEqual(self.routine('skill = "demo"\ninstruction = "x"\ntimeout_s = 120\n').timeout_s, R.SKILL_MIN_TIMEOUT_S)
        self.assertEqual(self.routine('skill = "demo"\ninstruction = "x"\ntimeout_s = 2000\n').timeout_s, 2000)

    def test_instruction_starting_with_dash_survives_the_real_parser(self):
        for text in ("--model=opus and then", "--effort=max", "--via=cli", "-x", "- list"):
            r = self.routine(f'skill = "demo"\ninstruction = "{text}"\n')
            args = cli.build_parser().parse_args(r.argv()[r.argv().index("aos") + 1:])
            self.assertEqual((args.id, args.instruction, args.via), ("demo", text, "routine"), text)

    def test_invalid_skill_routines_are_rejected(self):
        for extra in ('instruction = "x"\n', 'skill = "../x"\ninstruction = "x"\n', 'skill = "demo"\n',
                      'skill = "demo"\ninstruction = "x"\nmodel = "gpt"\n', 'skill = "demo"\ninstruction = "x"\neffort = "wild"\n',
                      'skill = "demo"\ninstruction = "' + "x" * 4001 + '"\n'):
            with self.assertRaises(R.RoutineError, msg=extra[:40]):
                self.routine(extra)

    def test_shipped_routines_load(self):
        routines = R.load_routines(PROJECT_ROOT / "routines.toml")
        skill_routines = [r for r in routines if r.command == "skill"]
        self.assertTrue(skill_routines)
        self.assertTrue(all(not r.enabled for r in skill_routines))  # costs money: off by default


class ServerSkillTests(SkillCase):
    def setUp(self):
        super().setUp()
        self.httpd, self.state = SV.create_server(self.cfg, 0, token="t0k")
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.httpd.shutdown(), self.httpd.server_close()))
        patcher = mock.patch.object(A, "execute", metered("Result from skill"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def req(self, method, path, body=None, token="t0k"):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        h = {"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"}
        if token:
            h["X-AOS-Token"] = token
        conn.request(method, path, body=None if body is None else json.dumps(body).encode(), headers=h)
        resp = conn.getresponse()
        raw = resp.read()
        conn.close()
        return resp.status, (json.loads(raw) if raw else None)

    def test_run_skill_and_fetch_artifact(self):
        status, body = self.req("POST", "/api/skills/demo", {"instruction": "Los", "model": "haiku", "effort": "low"})
        self.assertEqual(status, 202)
        self.assertEqual((body["job"]["skill"], body["job"]["model"], body["job"]["effort"]), ("demo", "haiku", "low"))
        for _ in range(100):
            job = self.req("GET", f"/api/jobs/{body['job']['id']}")[1]["job"]
            if job["status"] != "running":
                break
            time.sleep(0.05)
        self.assertEqual((job["status"], job["cost_usd"]), ("ok", 0.0123))
        status, art = self.req("GET", f"/api/artifact/j-{job['id']}")
        self.assertEqual((status, art["artifact"]["content"]), (200, "Result from skill"))
        api = self.req("GET", "/api/data")[1]["api"]
        self.assertEqual((api["skills"], api["artifact"]), ("/api/skills/", "/api/artifact/"))

    def raw(self, method, path, headers, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in headers.items():
            conn.putheader(k, v)
        data = json.dumps(body).encode() if body is not None else b""
        conn.putheader("Content-Length", str(len(data)))
        conn.endheaders(data)
        status = conn.getresponse().status
        conn.close()
        return status

    def test_wrong_host_or_origin_is_rejected_on_new_endpoints(self):
        good = {"X-AOS-Token": "t0k", "Content-Type": "application/json"}
        host = f"127.0.0.1:{self.port}"
        body = {"instruction": "x"}
        self.assertEqual(self.raw("POST", "/api/skills/demo", {**good, "Host": "evil.example"}, body), 403)
        self.assertEqual(self.raw("POST", "/api/skills/demo", {**good, "Host": host, "Origin": "http://evil.example"}, body), 403)
        self.assertEqual(self.raw("GET", "/api/artifact/j-000000000000", {**good, "Host": "evil.example"}), 403)
        self.assertEqual(self.raw("GET", "/api/artifact/j-000000000000", {**good, "Host": host, "Origin": "http://evil.example"}), 403)

    def test_running_job_is_not_an_artifact(self):
        A._append(self.cfg, {"id": "a" * 12, "agent": "skill-demo", "skill": "demo", "instruction": "running", "status": "running",
                             "started": datetime.now().isoformat(timespec="seconds"), "result": "half", "via": "server"})
        self.assertEqual(self.req("GET", "/api/artifact/j-" + "a" * 12)[0], 404)
        self.assertIsNone(AR.read_artifact(self.cfg, "j-" + "a" * 12))

    def test_errors_and_token(self):
        self.assertEqual(self.req("POST", "/api/skills/demo", {"instruction": "x", "model": "gpt-9"})[0], 400)
        self.assertEqual(self.req("POST", "/api/skills/demo", {"instruction": "x", "effort": "wild"})[0], 400)
        self.assertEqual(self.req("POST", "/api/skills/does-not-exist", {"instruction": "x"})[0], 404)
        self.assertEqual(self.req("POST", "/api/skills/demo", {"instruction": ""})[0], 400)
        self.assertEqual(self.req("POST", "/api/skills/demo", {"instruction": "x"}, token=None)[0], 401)
        self.assertEqual(self.req("POST", "/api/skills/demo", {"instruction": "x"}, token="wrong")[0], 401)
        self.assertEqual(self.req("GET", "/api/artifact/f-000000000000")[0], 404)
        self.assertEqual(self.req("GET", "/api/artifact/..%2F..%2Fsecret")[0], 404)
        self.assertEqual(self.req("GET", "/api/artifact/j-000000000000", token=None)[0], 401)


class CliSkillTests(SkillCase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["--config", str(self.cfg_path), *argv])
        return rc, buf.getvalue()

    def test_skills_skill_spend_artifacts(self):
        rc, out = self.run_cli("skills")
        self.assertEqual(rc, 0)
        self.assertIn("demo", out)
        with mock.patch.object(A, "execute", metered("Done!")):
            rc, out = self.run_cli("skill", "demo", "Do it", "--model", "haiku", "--effort", "low")
        self.assertEqual(rc, 0)
        self.assertIn("Done!", out)
        self.assertIn("haiku/low", out)
        self.assertIn("$0.0123", out)
        rc, out = self.run_cli("spend")
        self.assertIn("Today $0.0123", out)
        rc, out = self.run_cli("artifacts", "do it")
        self.assertIn("Skill: demo", out)
        self.assertEqual(self.run_cli("skill", "nope", "x")[0], 2)
        self.assertEqual(self.run_cli("skill", "demo", "x", "--model", "gpt")[0], 3)


if __name__ == "__main__":
    import unittest

    unittest.main()
