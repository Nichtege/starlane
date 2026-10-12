import http.client
import json
import threading
import unittest
from unittest import mock

from aos import server as SV
from tests.helpers import TempVaultCase

TOKEN = "test-token-123"


class ServerTests(TempVaultCase):
    def setUp(self):
        super().setUp()
        self.httpd, self.state = SV.create_server(self.cfg, 0, token=TOKEN)
        self.port = self.httpd.server_address[1]
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(self, method, path, headers=None, host=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def page(self):
        return f"/?k={self.state.launch_key}"

    def auth(self, **extra):
        return {"X-AOS-Token": TOKEN, **extra}

    # -- Binding --
    def test_binds_to_loopback_only(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")

    # -- Page --
    def test_dashboard_page_has_csp_nonce_and_embedded_data(self):
        resp, body = self.request("GET", self.page())
        self.assertEqual(resp.status, 200)
        csp = resp.getheader("Content-Security-Policy")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        nonce = csp.split("'nonce-")[1].split("'")[0]
        html = body.decode("utf-8")
        self.assertIn(f'nonce="{nonce}"', html)
        self.assertIn(TOKEN, html)  # the token is in the page so the buttons work
        self.assertEqual(resp.getheader("Cache-Control"), "no-store")
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")

    def test_page_data_cannot_break_out_of_script_tag(self):
        (self.vault_dir / "Resources" / "evil.md").write_text(
            "---\ntype: knowledge\ncreated: 2026-10-01\n---\n# </script><img src=x onerror=alert(1)>\n", encoding="utf-8"
        )
        self.state.invalidate()
        _, body = self.request("GET", self.page())
        html = body.decode("utf-8")
        self.assertNotIn("<img src=x", html)
        self.assertIn("\\u003c/script\\u003e", html)

    def test_wrong_host_is_rejected_dns_rebinding(self):
        resp, _ = self.request("GET", self.page(), host="evil.example.com")
        self.assertEqual(resp.status, 403)
        resp, _ = self.request("GET", "/api/data", headers=self.auth(), host=f"evil.example.com:{self.port}")
        self.assertEqual(resp.status, 403)

    # -- API --
    def test_api_requires_token(self):
        self.assertEqual(self.request("GET", "/api/data")[0].status, 401)
        self.assertEqual(self.request("GET", "/api/data", {"X-AOS-Token": "wrong"})[0].status, 401)
        resp, body = self.request("GET", "/api/data", self.auth())
        self.assertEqual(resp.status, 200)
        data = json.loads(body)
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["api"]["token"], TOKEN)
        self.assertIn("nodes", data)

    def test_post_run_checks_token_origin_and_whitelist(self):
        self.assertEqual(self.request("POST", "/api/run/digest")[0].status, 401)
        resp, _ = self.request("POST", "/api/run/digest", self.auth(Origin="http://evil.example.com"))
        self.assertEqual(resp.status, 403)
        resp, _ = self.request("POST", "/api/run/does-not-exist", self.auth())
        self.assertEqual(resp.status, 404)
        resp, _ = self.request("POST", "/api/run/..%2f..%2fetc", self.auth())
        self.assertEqual(resp.status, 404)
        resp, _ = self.request("POST", "/api/run/DIGEST;calc", self.auth())
        self.assertEqual(resp.status, 404)

    def test_post_run_executes_known_routine(self):
        record = {"id": "digest", "status": "ok", "note": "ok", "duration_s": 0.1, "trigger": "manual"}
        with mock.patch.object(SV, "run_now", return_value=record) as run:
            resp, body = self.request("POST", "/api/run/digest", self.auth(Origin=f"http://127.0.0.1:{self.port}"))
        self.assertEqual(resp.status, 200)
        self.assertTrue(json.loads(body)["ok"])
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1], "digest")

    def test_post_run_busy_gives_409_and_failure_gives_ok_false(self):
        with mock.patch.object(SV, "run_now", side_effect=SV.Busy("running")):
            self.assertEqual(self.request("POST", "/api/run/digest", self.auth())[0].status, 409)
        with mock.patch.object(SV, "run_now", return_value={"id": "digest", "status": "failed", "note": "x"}):
            _, body = self.request("POST", "/api/run/digest", self.auth())
        self.assertFalse(json.loads(body)["ok"])

    def test_other_methods_and_paths(self):
        self.assertEqual(self.request("PUT", "/api/run/digest", self.auth())[0].status, 405)
        self.assertEqual(self.request("DELETE", "/", self.auth())[0].status, 405)
        self.assertEqual(self.request("GET", "/../../etc/passwd")[0].status, 404)
        self.assertEqual(self.request("GET", "/data/state.json")[0].status, 404)  # no file serving
        self.assertEqual(self.request("GET", "/healthz")[0].status, 200)

    def test_token_comparison_is_not_prefix_based(self):
        self.assertEqual(self.request("GET", "/api/data", {"X-AOS-Token": TOKEN[:-1]})[0].status, 401)
        self.assertEqual(self.request("GET", "/api/data", {"X-AOS-Token": TOKEN + "x"})[0].status, 401)


if __name__ == "__main__":
    unittest.main()
