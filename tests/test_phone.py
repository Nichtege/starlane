import contextlib
import hashlib
import http.client
import io
import json
import struct
import threading
import unittest
from unittest import mock

from aos import phone as PH
from aos import server as SV
from tests.helpers import TempVaultCase

TOKEN = "test-token-123"
HOST = "laptop.tail1234.ts.net"


class QrAndIconTests(unittest.TestCase):
    def test_qr_matches_the_reference_encoder(self):
        # Known answer, checked against the `qrcode` package (level M, mask 0) for every length from 1 to 199
        m = PH.qr_matrix(f"https://{HOST}/?k=" + "A" * 43)
        self.assertEqual(len(m), 37)  # version 5
        bits = "".join("1" if c else "0" for row in m for c in row)
        self.assertEqual(hashlib.sha256(bits.encode()).hexdigest(), "d7ae595200cfd72a6143d935be4dcedca218c5d952c82e263c0f3ae8e8270908")

    def test_qr_sizes_and_limit(self):
        self.assertEqual(len(PH.qr_matrix("x")), 21)
        self.assertEqual(len(PH.qr_matrix("x" * 200)), 57)  # version 10
        with self.assertRaises(ValueError):
            PH.qr_matrix("x" * 300)

    def test_icon_is_a_png_of_the_asked_size(self):
        png = PH.icon_png(180)
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(struct.unpack(">II", png[16:24]), (180, 180))


class PhoneTests(TempVaultCase):
    def setUp(self):
        super().setUp()
        self.httpd, self.state = SV.create_server(self.cfg, 0, token=TOKEN)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self._stop)

    def _stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def request(self, method, path, host=HOST, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request(method, path, body=body, headers={"Host": host, **(headers or {})})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def pair(self, new_key=False, host=HOST):
        out = io.StringIO()
        with mock.patch.object(PH, "serve_forwards", return_value=True), contextlib.redirect_stdout(out):
            code = PH.setup(self.cfg, host=host, new_key=new_key)
        return code, out.getvalue()

    # -- aos phone --
    def test_setup_pairs_keeps_the_key_and_new_key_replaces_it(self):
        code, out = self.pair()
        self.assertEqual(code, 0)
        rec = PH.load(self.cfg)
        self.assertEqual(rec["host"], HOST)
        self.assertIn(PH.link(rec), out)
        self.pair()
        self.assertEqual(PH.load(self.cfg)["key"], rec["key"])  # running it again shows the same code
        self.pair(new_key=True)
        self.assertNotEqual(PH.load(self.cfg)["key"], rec["key"])

    def test_setup_rejects_a_bad_host_and_off_unpairs(self):
        self.assertEqual(self.pair(host="not a host")[0], 1)
        self.assertIsNone(PH.load(self.cfg))
        self.pair()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(PH.setup(self.cfg, off=True), 0)
        self.assertIsNone(PH.load(self.cfg))

    def test_a_broken_file_means_not_paired(self):
        PH.phone_file(self.cfg).parent.mkdir(parents=True, exist_ok=True)
        for text in ("{", "[]", json.dumps({"host": "evil.example/x", "key": "k" * 40}), json.dumps({"host": HOST, "key": "short"})):
            PH.phone_file(self.cfg).write_text(text, encoding="utf-8")
            self.assertIsNone(PH.load(self.cfg), text)

    # -- server --
    def test_phone_host_is_refused_until_paired_and_again_after_off(self):
        self.assertEqual(self.request("GET", "/healthz")[0].status, 403)
        self.pair()
        self.assertEqual(self.request("GET", "/healthz")[0].status, 200)
        self.assertEqual(self.request("GET", "/healthz", host=HOST + ":443")[0].status, 200)
        self.assertEqual(self.request("GET", "/healthz", host="other.tail1234.ts.net")[0].status, 403)
        with contextlib.redirect_stdout(io.StringIO()):
            PH.setup(self.cfg, off=True)
        self.assertEqual(self.request("GET", "/healthz")[0].status, 403)  # no restart needed

    def test_phone_page_needs_the_phone_key_and_becomes_an_app(self):
        self.pair()
        key = PH.load(self.cfg)["key"]
        self.assertEqual(self.request("GET", "/?k=wrong" + "x" * 40)[0].status, 403)
        resp, body = self.request("GET", f"/?k={key}")
        self.assertEqual(resp.status, 200)
        html = body.decode("utf-8")
        self.assertIn(TOKEN, html)
        self.assertIn(f'<link rel="manifest" href="/manifest.webmanifest?k={key}">', html)
        self.assertIn("manifest-src 'self'", resp.getheader("Content-Security-Policy"))
        # the phone key opens nothing on 127.0.0.1, and the local page stays without a manifest
        self.assertEqual(self.request("GET", f"/?k={key}", host=f"127.0.0.1:{self.port}")[0].status, 403)
        local = self.request("GET", f"/?k={self.state.launch_key}", host=f"127.0.0.1:{self.port}")[1].decode("utf-8")
        self.assertNotIn('<link rel="manifest"', local)

    def test_manifest_and_icons(self):
        self.pair()
        key = PH.load(self.cfg)["key"]
        self.assertEqual(self.request("GET", "/manifest.webmanifest")[0].status, 403)
        self.assertEqual(self.request("GET", f"/manifest.webmanifest?k={key}", host=f"127.0.0.1:{self.port}")[0].status, 403)
        resp, body = self.request("GET", f"/manifest.webmanifest?k={key}")
        self.assertEqual(resp.status, 200)
        man = json.loads(body)
        self.assertEqual((man["start_url"], man["display"]), (f"/?k={key}", "standalone"))
        resp, body = self.request("GET", "/icon-192.png")
        self.assertEqual((resp.status, resp.getheader("Content-Type")), (200, "image/png"))
        self.assertEqual(self.request("GET", "/icon-7.png")[0].status, 404)

    def test_api_accepts_the_https_origin_of_the_phone_address_only(self):
        self.pair()
        auth = {"X-AOS-Token": TOKEN}
        self.assertEqual(self.request("GET", "/api/jobs", headers={**auth, "Origin": f"https://{HOST}"})[0].status, 200)
        self.assertEqual(self.request("GET", "/api/jobs", headers={**auth, "Origin": "https://evil.example"})[0].status, 403)
        self.assertEqual(self.request("GET", "/api/jobs", headers={"Origin": f"https://{HOST}"})[0].status, 401)


if __name__ == "__main__":
    unittest.main()
