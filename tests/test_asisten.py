"""Pengujian server web (asisten.py): riwayat, token, dan endpoint /api."""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import asisten  # noqa: E402

TOKEN = "token-uji-123"


class TestRiwayat(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._lama = asisten.RIWAYAT
        asisten.RIWAYAT = Path(self._tmp.name)

    def tearDown(self):
        asisten.RIWAYAT = self._lama
        self._tmp.cleanup()

    def test_simpan_baca_daftar(self):
        c = asisten.baru_chat("model-x")
        c["pesan"] = [{"role": "user", "content": "halo"},
                      {"role": "assistant", "content": "hai   apa\nkabar"}]
        asisten.simpan_chat(c)
        self.assertEqual(asisten.baca_chat(c["id"])["model"], "model-x")
        item = asisten.daftar_chat()[0]
        self.assertEqual(item["jumlah"], 1)
        self.assertEqual(item["cuplikan"], "hai apa kabar")

    def test_cuplikan_dipotong(self):
        teks = asisten.cuplikan_chat({"pesan": [{"role": "assistant", "content": "a" * 300}]})
        self.assertEqual(len(teks), 80)
        self.assertTrue(teks.endswith("\u2026"))
        self.assertEqual(asisten.cuplikan_chat({"pesan": []}), "")

    def test_id_tidak_valid(self):
        with self.assertRaises(FileNotFoundError):
            asisten.path_chat("../etc/passwd")

    def test_hapus_semua_kecuali(self):
        a = asisten.baru_chat(None)
        b = {"id": "20260101-000000-abcd", "judul": "lain", "model": None, "pesan": []}
        asisten.simpan_chat(b)
        self.assertEqual(asisten.hapus_semua_chat(kecuali=a["id"]), 1)
        self.assertEqual([c["id"] for c in asisten.daftar_chat()], [a["id"]])


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls._riwayat, cls._token = asisten.RIWAYAT, asisten.TOKEN
        asisten.RIWAYAT, asisten.TOKEN = Path(cls._tmp.name), TOKEN
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), asisten.H)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        asisten.RIWAYAT, asisten.TOKEN = cls._riwayat, cls._token
        cls._tmp.cleanup()

    def setUp(self):
        asisten.hapus_semua_chat()

    def req(self, metode, path, body=None, token=TOKEN):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=metode)
        if token:
            r.add_header("Authorization", "Bearer " + token)
        if data:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def j(self, *a, **kw):
        kode, isi = self.req(*a, **kw)
        return kode, json.loads(isi or b"{}")

    def test_halaman_statis(self):
        for path in ("/", "/index.css", "/index.js"):
            self.assertEqual(self.req("GET", path, token=None)[0], 200, path)
        self.assertEqual(self.req("GET", "/asisten.py", token=None)[0], 404)
        self.assertEqual(self.req("GET", "/.token", token=None)[0], 404)

    def test_token_wajib(self):
        self.assertEqual(self.req("GET", "/api/chat", token=None)[0], 401)
        self.assertEqual(self.req("GET", "/api/chat", token="salah")[0], 401)
        self.assertEqual(self.req("POST", "/api/chat/hapus-semua", {}, token="salah")[0], 401)

    def test_status(self):
        kode, d = self.j("GET", "/api/status")
        self.assertEqual(kode, 200)
        self.assertEqual(d["skills"]["tanpa"], 0)
        self.assertEqual(d["skills"]["dasar"], 4)
        self.assertGreater(d["skills"]["semua"], 4)

    def test_siklus_chat(self):
        kode, c = self.j("POST", "/api/chat/baru", {})
        self.assertEqual(kode, 200)
        cid = c["id"]
        self.assertEqual(self.j("GET", "/api/chat/" + cid)[1]["id"], cid)
        self.assertEqual([x["id"] for x in self.j("GET", "/api/chat")[1]["chat"]], [cid])
        self.assertEqual(self.j("DELETE", "/api/chat/" + cid)[0], 200)
        self.assertEqual(self.j("GET", "/api/chat")[1]["chat"], [])
        self.assertEqual(self.req("GET", "/api/chat/" + cid)[0], 404)

    def test_hapus_semua(self):
        a = self.j("POST", "/api/chat/baru", {})[1]["id"]
        asisten.simpan_chat({"id": "20260101-000000-abcd", "judul": "x", "model": None, "pesan": []})
        asisten.simpan_chat({"id": "20260101-000001-abcd", "judul": "y", "model": None, "pesan": []})
        kode, d = self.j("POST", "/api/chat/hapus-semua", {"kecuali": a})
        self.assertEqual((kode, d["dihapus"]), (200, 2))
        self.assertEqual([x["id"] for x in self.j("GET", "/api/chat")[1]["chat"]], [a])

    def test_hapus_semua_id_tidak_valid(self):
        self.assertEqual(self.j("POST", "/api/chat/hapus-semua", {"kecuali": "../x"})[0], 400)

    def test_id_tidak_valid_404(self):
        self.assertEqual(self.req("GET", "/api/chat/xx")[0], 404)


if __name__ == "__main__":
    unittest.main()
