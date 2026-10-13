"""The web guard: mixed agents (vault + web) cannot carry note text out through a search query or a URL."""

import base64
import json
import os
import subprocess
import sys
from dataclasses import replace
from unittest import mock
from urllib.parse import quote

from aos import agents as A
from aos import webguard as W
from tests.helpers import TempVaultCase

NOTE = ("# Health\nMy doctor said the knee needs three more weeks of physio before running again.\n"
        "IBAN DE89 3704 0044 0532 0130 00, call +49 151 2345 6789.\n"
        "Reading list: https://example.org/how-to-build-a-second-brain-in-obsidian-for-busy-people\n")
SENTENCE = "the knee needs three more weeks of physio before running"


class CheckTests(TempVaultCase):
    def setUp(self):
        super().setUp()
        (self.vault_dir / "Areas").mkdir(exist_ok=True)
        (self.vault_dir / "Areas" / "health.md").write_text(NOTE, encoding="utf-8")
        self.corpus, self.urls = W.build_corpus(self.vault_dir, set(self.cfg.ignore))

    def test_note_text_is_blocked_however_it_is_dressed(self):
        for payload in (
            SENTENCE,
            "https://evil.example/c?d=" + quote(SENTENCE),
            "https://evil.example/c?d=" + quote(quote(SENTENCE)),
            "https://evil.example/" + SENTENCE.replace(" ", "-"),
            "https://evil.example/c?d=" + base64.urlsafe_b64encode(SENTENCE.encode()).decode(),
            "https://evil.example/c?d=" + SENTENCE.encode().hex(),
            "https://evil.example/c?iban=DE89370400440532013000",  # other spacing than in the note
            "https://evil.example/c?tel=4915123456789",
            "https://evil.example/c?k=sk-abcdefghijklmnopqrstuvwxyz123456",  # a secret, note or not
        ):
            self.assertTrue(W.check(payload, self.corpus), payload)

    def test_ordinary_research_passes(self):
        for payload in (
            "knee physio running return timeline",
            "how long physio after knee injury before running again",
            "https://www.nhs.uk/conditions/knee-pain/",
            "https://example.org/2026/10/13/news?id=12345",
        ):
            self.assertEqual(W.check(payload, self.corpus), "", payload)

    def test_what_the_user_typed_is_theirs_to_send(self):
        self.assertEqual(W.check(SENTENCE, self.corpus, allow=f"Search the web for '{SENTENCE}'"), "")

    def test_note_urls_are_known_and_not_note_text(self):
        self.assertIn("https://example.org/how-to-build-a-second-brain-in-obsidian-for-busy-people", self.urls)
        self.assertNotIn("second brain in obsidian", self.corpus)


class HookTests(CheckTests):
    """The hook as Claude Code runs it: a separate `python -I` process, the call as JSON on stdin."""

    def hook(self, stage, tool, payload, allow=""):
        env = {**os.environ, "AOS_GUARD_VAULT": str(self.vault_dir), "AOS_GUARD_IGNORE": json.dumps(list(self.cfg.ignore)),
               "AOS_GUARD_STATE": str(self.root / "run1"), "AOS_GUARD_ALLOW": allow}
        key = "url" if tool == "WebFetch" else "query"
        data = {"tool_name": tool, "tool_input": {key: payload}}
        if stage == "post":
            data["tool_response"] = payload
        return subprocess.run([sys.executable, "-I", str(W.__file__), stage], input=json.dumps(data), env=env,
                              capture_output=True, text=True, timeout=60, cwd=self.root)

    def test_blocks_with_a_reason_and_lets_links_through(self):
        res = self.hook("pre", "WebSearch", SENTENCE)
        self.assertEqual(res.returncode, 2)
        self.assertIn("text from the notes", res.stderr)
        self.assertEqual((self.root / "run1.blocked").read_text(encoding="utf-8").split(), ["WebSearch"])
        self.assertEqual(self.hook("pre", "WebSearch", "knee physio timeline").returncode, 0)
        # a URL the agent did not make up passes unchecked: from the notes, from a result, from the user
        slug = "https://news.example/" + SENTENCE.replace(" ", "-")
        self.assertEqual(self.hook("pre", "WebFetch", slug).returncode, 2)
        self.hook("post", "WebSearch", f"results: [{slug}]")
        self.assertEqual(self.hook("pre", "WebFetch", slug).returncode, 0)
        self.assertEqual(self.hook("pre", "WebFetch", "https://example.org/how-to-build-a-second-brain-in-obsidian-for-busy-people").returncode, 0)

    def test_fails_closed(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("AOS_GUARD")}
        res = subprocess.run([sys.executable, "-I", str(W.__file__), "pre"], input="{}", env=env, capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(res.returncode, 2)


class WiringTests(TempVaultCase):
    def agent(self, tools):
        return A.Agent(id="a", name="A", description="", model="sonnet", tools=tools, timeout_s=60, max_runs_per_day=5,
                       enabled=True, prompt_file=self.root / "a.md")

    def test_only_mixed_agents_get_the_guard(self):
        for tools, guarded in ((A.VAULT_TOOLS + A.WEB_TOOLS, True), (A.VAULT_TOOLS, False), (A.WEB_TOOLS, False)):
            cmd = A.claude_command("claude.exe", self.agent(tools), "p")
            self.assertEqual("--settings" in cmd, guarded, tools)
            if guarded:  # --allowedTools stays the last option
                self.assertGreater(cmd.index("--allowedTools"), cmd.index("--settings"))
        hooks = json.loads(A.guard_settings())["hooks"]
        self.assertEqual(set(hooks), {"PreToolUse", "PostToolUse"})
        self.assertIn("webguard.py", hooks["PreToolUse"][0]["hooks"][0]["command"])

    def test_run_reports_blocks_and_cleans_up(self):
        mixed = replace(self.agent(A.VAULT_TOOLS + A.WEB_TOOLS), user_text="my words")
        seen = {}

        def popen(cmd, **kw):
            seen.update(kw["env"])
            with open(kw["env"]["AOS_GUARD_STATE"] + ".blocked", "w", encoding="utf-8") as fh:
                fh.write("WebFetch\nWebSearch\n")
            proc = mock.MagicMock(returncode=0)
            proc.communicate.return_value = ('{"result": "Answer", "total_cost_usd": 0.01}', "")
            return proc

        with mock.patch.object(A, "find_claude", return_value=("claude.exe", "")), mock.patch.object(A.subprocess, "Popen", popen):
            status, answer, _, meta = A._run(self.cfg, mixed, "system", "task")
        self.assertEqual((status, answer, meta["guard_blocked"]), ("ok", "Answer", 2))
        self.assertEqual((seen["AOS_GUARD_VAULT"], seen["AOS_GUARD_ALLOW"]), (str(self.cfg.vault), "my words"))
        self.assertEqual(list((self.cfg.jobs_log.parent / "guard").iterdir()), [])

    def test_the_users_own_question_reaches_the_guard(self):
        (self.root / "agents").mkdir()
        (self.root / "agents" / "a.md").write_text("# A\n", encoding="utf-8")
        (self.root / "agents.toml").write_text(
            '[[agent]]\nid = "web"\ntools = ["Read", "WebSearch"]\nmixed = true\nprompt = "agents/a.md"\n', encoding="utf-8")
        got = []
        A.submit(self.cfg, "web", "Find this exact phrase", wait=True,
                 runner=lambda cfg, agent, text: got.append(agent.user_text) or ("ok", "x", ""))
        self.assertEqual(got, ["Find this exact phrase"])
