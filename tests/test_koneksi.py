"""Pengujian pengaturan koneksi: alamat llama-server/penyedia online + API key.

Memakai server llama PALSU (HTTP sungguhan) yang bisa meminta kunci Bearer, berpura-pura router atau
bukan, dan mengalihkan (redirect), sehingga yang diuji adalah permintaan nyata yang keluar dari aplikasi.
"""
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agen  # noqa: E402
from agen import agen_config as acfg  # noqa: E402
_ASLI_ANTHROPIC = acfg.adalah_anthropic
import asisten  # noqa: E402
import tim  # noqa: E402
from server import server_koneksi as kon  # noqa: E402
from server import server_state as sstate  # noqa: E402
from server import server_model as mdl  # noqa: E402
from tim import tim_llm, tim_model  # noqa: E402

KUNCI = "sk-rahasia-1234567890"


class Palsu:
    """llama-server palsu. `catatan` berisi (metode, path, header Authorization, isi body)."""

    def __init__(self, kunci=None, router=True, ids=("m1", "m2"), alihkan_ke=None, balas=None):
        self.kunci, self.router, self.ids, self.alihkan_ke, self.balas = kunci, router, ids, alihkan_ke, balas
        self.catatan, self.kepala = [], []
        induk = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _kirim(self, kode, obj, tipe="application/json"):
                data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
                self.send_response(kode)
                self.send_header("Content-Type", tipe)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _tangani(self):
                n = int(self.headers.get("Content-Length") or 0)
                isi = self.rfile.read(n).decode() if n else ""
                auth = self.headers.get("Authorization", "")
                induk.catatan.append((self.command, self.path, auth, isi))
                induk.kepala.append({k.lower(): v for k, v in self.headers.items()})
                if induk.alihkan_ke:
                    self.send_response(302)
                    self.send_header("Location", induk.alihkan_ke + self.path)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if induk.kunci and auth != "Bearer " + induk.kunci:
                    return self._kirim(401, {"error": "kunci salah"})
                if induk.balas is not None:
                    return self._kirim(*induk.balas)
                if self.path.split("?")[0].endswith("/models") and self.command == "GET":
                    data = [{"id": i, **({"status": {"value": "unloaded"}} if induk.router else {})}
                            for i in induk.ids]
                    return self._kirim(200, {"data": data})
                if self.path.endswith("/chat/completions"):
                    sse = (b'data: {"choices":[{"delta":{"content":"hai"}}]}\n\n'
                           b'data: [DONE]\n\n')
                    return self._kirim(200, sse, "text/event-stream")
                if self.path in ("/models/load", "/models/unload"):
                    return self._kirim(200, {"ok": True})
                self._kirim(404, {"error": "tidak ada"})

            do_GET = do_POST = _tangani

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.alamat = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def tutup(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def yang(self, path):
        return [c for c in self.catatan if c[1].split("?")[0].endswith(path)]


class Dasar(unittest.TestCase):
    """Mengisolasi pengaturan: berkas di folder sementara dan nilai agen.* dipulihkan."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.berkas = Path(self._tmp.name) / "pengaturan.json"
        for obj, nama, nilai in ((kon.conf, "PENGATURAN_FILE", self.berkas),
                                 (agen, "LLAMA_URL", agen.LLAMA_URL), (agen, "LLAMA_V1", agen.LLAMA_V1),
                                 (agen, "LLAMA_KEY", ""), (agen, "LLAMA_JENIS", "llama")):
            p = mock.patch.object(obj, nama, nilai)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(kon.SUMBER, {"nilai": "bawaan"})
        p.start()
        self.addCleanup(p.stop)
        for d in (agen.LLAMA_EXTRA, sstate.KONEKSI_STATUS):          # koneksi tambahan & status tiap tes mulai kosong
            p = mock.patch.dict(d, clear=True)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(agen, "LLAMA_NAMA", "")
        p.start()
        self.addCleanup(p.stop)
        with asisten.S_LOCK:
            self._s = dict(asisten.S)
        self.addCleanup(lambda: asisten.S.update(self._s))

    def palsu(self, **kw):
        p = Palsu(**kw)
        self.addCleanup(p.tutup)
        return p


# ---------------------------------------------------------------- alamat
class TestAlamat(unittest.TestCase):
    def test_pecah_alamat(self):
        for masuk, harap in (
                ("http://127.0.0.1:8080", ("http://127.0.0.1:8080", "/v1")),
                ("http://127.0.0.1:8080/v1", ("http://127.0.0.1:8080", "/v1")),
                ("http://127.0.0.1:8080/v1/", ("http://127.0.0.1:8080", "/v1")),
                ("https://api.openai.com/v1", ("https://api.openai.com", "/v1")),
                ("https://openrouter.ai/api/v1", ("https://openrouter.ai/api", "/v1")),
                ("https://api.groq.com/openai/v1", ("https://api.groq.com/openai", "/v1")),
                ("https://host/v1beta/openai", ("https://host", "/v1beta/openai")),
                ("https://api.deepseek.com", ("https://api.deepseek.com", "/v1"))):
            self.assertEqual(agen.pecah_alamat(masuk), harap, masuk)

    def test_llama_url_memakai_awalan_server(self):
        self.assertEqual(agen.llama_url("/v1/models", "https://h", "/v1beta/openai"),
                         "https://h/v1beta/openai/models")
        self.assertEqual(agen.llama_url("/models/load", "https://h", "/v1beta/openai"), "https://h/models/load")

    def test_rapikan_alamat(self):
        self.assertEqual(kon.rapikan_alamat("192.168.1.5:8080/"), ("http://192.168.1.5:8080", ""))
        self.assertEqual(kon.rapikan_alamat("  https://api.openai.com/v1 "), ("https://api.openai.com/v1", ""))
        for buruk in ("", "   ", None, 5, "ftp://x", "http://a b", "http://u:p@host", "http://h/v1?k=1",
                      "http://", "x" * 400):
            alamat, galat = kon.rapikan_alamat(buruk)
            self.assertEqual(alamat, "", buruk)
            self.assertTrue(galat, buruk)


# ---------------------------------------------------------------- uji koneksi
class TestUji(Dasar):
    def test_router_dikenali_dan_model_dihitung(self):
        p = self.palsu(ids=("a", "b", "c"))
        kode, d = kon.koneksi_uji({"alamat": p.alamat})
        self.assertEqual((kode, d["ok"], d["jumlah"], d["router"]), (200, True, 3, True))
        self.assertEqual(d["contoh"], ["a", "b", "c"])

    def test_server_tanpa_router(self):
        p = self.palsu(router=False)
        d = kon.koneksi_uji({"alamat": p.alamat})[1]
        self.assertTrue(d["ok"])
        self.assertFalse(d["router"])

    def test_uji_tidak_menerapkan_apa_apa(self):
        p = self.palsu(kunci=KUNCI)
        asli = (agen.LLAMA_URL, agen.LLAMA_KEY)
        kon.koneksi_uji({"alamat": p.alamat, "key": KUNCI})
        self.assertEqual((agen.LLAMA_URL, agen.LLAMA_KEY), asli)
        self.assertFalse(self.berkas.exists())

    def test_server_butuh_kunci(self):
        p = self.palsu(kunci=KUNCI)
        d = kon.koneksi_uji({"alamat": p.alamat})[1]
        self.assertFalse(d["ok"])
        self.assertIn("butuh API key", d["error"])

    def test_kunci_salah_tidak_muncul_di_pesan(self):
        p = self.palsu(kunci=KUNCI)
        salah = "sk-salah-9999999999"
        d = kon.koneksi_uji({"alamat": p.alamat, "key": salah})[1]
        self.assertFalse(d["ok"])
        self.assertIn("salah", d["error"])
        self.assertNotIn(salah, json.dumps(d))

    def test_kunci_benar(self):
        p = self.palsu(kunci=KUNCI)
        d = kon.koneksi_uji({"alamat": p.alamat, "key": KUNCI})[1]
        self.assertTrue(d["ok"])
        self.assertEqual(p.catatan[-1][2], "Bearer " + KUNCI)

    def test_kunci_tersimpan_dipakai_bila_tidak_dikirim(self):
        p = self.palsu(kunci=KUNCI)
        agen.LLAMA_KEY = KUNCI
        self.assertTrue(kon.koneksi_uji({"alamat": p.alamat})[1]["ok"])

    def test_tidak_terhubung(self):
        d = kon.koneksi_uji({"alamat": "http://127.0.0.1:1"})[1]
        self.assertFalse(d["ok"])
        self.assertIn("Tidak bisa terhubung", d["error"])

    def test_bukan_json(self):
        p = self.palsu(balas=(200, b"<html>halo</html>", "text/html"))
        d = kon.koneksi_uji({"alamat": p.alamat})[1]
        self.assertFalse(d["ok"])
        self.assertIn("bukan JSON", d["error"])

    def test_json_tanpa_daftar_model(self):
        p = self.palsu(balas=(200, {"hasil": 1}))
        self.assertFalse(kon.koneksi_uji({"alamat": p.alamat})[1]["ok"])

    def test_404(self):
        p = self.palsu(balas=(404, {"error": "x"}))
        self.assertIn("404", kon.koneksi_uji({"alamat": p.alamat})[1]["error"])

    def test_alamat_buruk_ditolak_400(self):
        kode, d = kon.koneksi_uji({"alamat": "ftp://x"})
        self.assertEqual(kode, 400)
        self.assertFalse(d["ok"])

    def test_pengalihan_tidak_membocorkan_kunci(self):
        """urllib biasa meneruskan Authorization ke alamat tujuan pengalihan; di sini harus ditolak."""
        tujuan = self.palsu()
        asal = self.palsu(alihkan_ke=tujuan.alamat)
        d = kon.koneksi_uji({"alamat": asal.alamat, "key": KUNCI})[1]
        self.assertFalse(d["ok"])
        self.assertIn("mengalihkan", d["error"])
        self.assertEqual(tujuan.catatan, [], "permintaan sampai ke server tujuan pengalihan")
        self.assertNotIn(KUNCI, json.dumps(d))

    def test_pengalihan_saat_chat_dengan_kunci_tidak_diikuti(self):
        tujuan = self.palsu()
        asal = self.palsu(alihkan_ke=tujuan.alamat)
        kon.koneksi_terapkan(asal.alamat, KUNCI, "llama")
        with self.assertRaises(urllib.error.HTTPError):
            agen.llama("/v1/models", timeout=5)
        with self.assertRaises(urllib.error.HTTPError):
            list(agen.stream_chat("m", [], threading.Event()))
        with self.assertRaises(urllib.error.HTTPError):
            list(tim_llm._stream("m", [], threading.Event(), 100))
        self.assertEqual(tujuan.catatan, [])

    def test_peringatan_http_ke_internet_dengan_kunci(self):
        d = kon.koneksi_ringkas()
        self.assertEqual(d["peringatan"], "")
        kon.koneksi_terapkan("http://api.contoh.com", KUNCI, "online")
        self.assertIn("tanpa enkripsi", kon.koneksi_ringkas()["peringatan"])
        kon.koneksi_terapkan("https://api.contoh.com", KUNCI, "online")
        self.assertEqual(kon.koneksi_ringkas()["peringatan"], "")
        kon.koneksi_terapkan("http://192.168.1.5:8080", KUNCI, "llama")
        self.assertEqual(kon.koneksi_ringkas()["peringatan"], "")
        kon.koneksi_terapkan("http://pi.local:8080", KUNCI, "llama")
        self.assertEqual(kon.koneksi_ringkas()["peringatan"], "")


# ---------------------------------------------------------------- simpan, muat, reset
class TestSimpan(Dasar):
    def test_simpan_menerapkan_dan_menulis_berkas_rahasia(self):
        p = self.palsu(kunci=KUNCI)
        kode, d = kon.koneksi_simpan({"alamat": p.alamat + "/v1", "key": KUNCI, "jenis": "online"})
        self.assertEqual((kode, d["ok"], d["tersimpan"]), (200, True, True))
        self.assertEqual((agen.LLAMA_URL, agen.LLAMA_V1, agen.LLAMA_KEY, agen.LLAMA_JENIS),
                         (p.alamat, "/v1", KUNCI, "online"))
        mode = stat.S_IMODE(self.berkas.stat().st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(json.loads(self.berkas.read_text())["koneksi"]["key"], KUNCI)
        self.assertFalse(list(self.berkas.parent.glob("*.tmp")))

    def test_jawaban_dan_ringkasan_tidak_memuat_kunci(self):
        p = self.palsu(kunci=KUNCI)
        d = kon.koneksi_simpan({"alamat": p.alamat, "key": KUNCI})[1]
        self.assertNotIn(KUNCI, json.dumps(d))
        self.assertNotIn(KUNCI, json.dumps(kon.koneksi_ringkas()))
        self.assertTrue(kon.koneksi_ringkas()["key_ada"])

    def test_kunci_tidak_dicatat_di_log(self):
        p = self.palsu(kunci=KUNCI)
        with mock.patch.object(kon.lg, "log") as log:
            kon.koneksi_simpan({"alamat": p.alamat, "key": KUNCI})
        self.assertTrue(log.called)
        self.assertNotIn(KUNCI, json.dumps([c.args for c in log.call_args_list]))

    def test_kunci_dipertahankan_bila_tidak_dikirim_dan_dihapus_bila_kosong(self):
        p = self.palsu()
        kon.koneksi_simpan({"alamat": p.alamat, "key": KUNCI})
        kon.koneksi_simpan({"alamat": p.alamat, "jenis": "llama"})          # tanpa kolom key
        self.assertEqual(agen.LLAMA_KEY, KUNCI)
        kon.koneksi_simpan({"alamat": p.alamat, "key": ""})                  # kosong = hapus
        self.assertEqual(agen.LLAMA_KEY, "")
        self.assertFalse(kon.koneksi_ringkas()["key_ada"])

    def test_kunci_dengan_baris_baru_ditolak(self):
        kode, d = kon.koneksi_simpan({"alamat": "http://127.0.0.1:8080", "key": "abc\nX-Lain: 1"})
        self.assertEqual(kode, 400)
        self.assertEqual(agen.LLAMA_KEY, "")

    def test_jenis_tidak_dikenal_tidak_mengubah(self):
        kon.koneksi_simpan({"alamat": "http://127.0.0.1:9", "jenis": "ngawur"})
        self.assertEqual(agen.LLAMA_JENIS, "llama")

    def test_ditolak_saat_ada_proses_berjalan(self):
        asisten.GEN_LOCK.acquire()
        try:
            kode, d = kon.koneksi_simpan({"alamat": "http://127.0.0.1:9"})
        finally:
            asisten.GEN_LOCK.release()
        self.assertEqual(kode, 409)
        self.assertFalse(self.berkas.exists())
        with asisten.AGENT_COND:
            asli = asisten.AGENT["aktif"]
            asisten.AGENT["aktif"] = True
        try:
            self.assertEqual(kon.koneksi_simpan({"alamat": "http://127.0.0.1:9"})[0], 409)
            self.assertEqual(kon.koneksi_reset()[0], 409)
        finally:
            with asisten.AGENT_COND:
                asisten.AGENT["aktif"] = asli

    def test_gagal_menulis_tetap_berlaku_dan_memberi_tahu(self):
        self.berkas = Path(self._tmp.name) / "tidak-ada" / "p.json"
        kon.conf.PENGATURAN_FILE = self.berkas
        d = kon.koneksi_simpan({"alamat": "http://127.0.0.1:9"})[1]
        self.assertTrue(d["ok"])
        self.assertFalse(d["tersimpan"])
        self.assertEqual(agen.LLAMA_URL, "http://127.0.0.1:9")

    def test_muat_dari_berkas(self):
        self.berkas.write_text(json.dumps({"koneksi": {"alamat": "https://api.contoh.com/v1", "key": KUNCI,
                                                       "jenis": "online"}}))
        self.assertEqual(kon.koneksi_muat(), "")
        self.assertEqual((agen.LLAMA_URL, agen.LLAMA_V1, agen.LLAMA_KEY, agen.LLAMA_JENIS),
                         ("https://api.contoh.com", "/v1", KUNCI, "online"))
        self.assertEqual(kon.SUMBER["nilai"], "web")

    def test_muat_tanpa_berkas_tidak_mengubah(self):
        asli = agen.LLAMA_URL
        self.assertEqual(kon.koneksi_muat(), "")
        self.assertEqual(agen.LLAMA_URL, asli)

    def test_muat_berkas_rusak_memberi_peringatan_tanpa_error(self):
        asli = agen.LLAMA_URL
        for isi in ("{rusak", json.dumps([1, 2]), json.dumps({"koneksi": "x"}),
                    json.dumps({"koneksi": {"alamat": "ftp://x"}})):
            self.berkas.write_text(isi)
            kon.koneksi_muat()
            self.assertEqual(agen.LLAMA_URL, asli, isi)
        self.berkas.write_text("{rusak")
        self.assertIn("tidak terbaca", kon.koneksi_muat())

    def test_muat_kunci_bukan_teks_diabaikan(self):
        self.berkas.write_text(json.dumps({"koneksi": {"alamat": "http://127.0.0.1:9", "key": 123}}))
        kon.koneksi_muat()
        self.assertEqual(agen.LLAMA_KEY, "")

    def test_reset_menghapus_berkas_dan_kembali_ke_awal(self):
        kon.koneksi_simpan({"alamat": "http://127.0.0.1:9", "key": KUNCI, "jenis": "online"})
        self.assertTrue(self.berkas.exists())
        with mock.patch.dict(kon._AWAL, {"alamat": "http://127.0.0.1:8080", "key": "", "jenis": "llama"}):
            kode, d = kon.koneksi_reset()
        self.assertEqual(kode, 200)
        self.assertFalse(self.berkas.exists())
        self.assertEqual((agen.LLAMA_URL, agen.LLAMA_KEY, agen.LLAMA_JENIS), ("http://127.0.0.1:8080", "", "llama"))
        self.assertEqual(kon.koneksi_reset()[0], 200)       # tanpa berkas pun tidak error

    def test_pindah_server_membongkar_model_milik_kita_di_server_lama(self):
        lama = self.palsu()
        baru = self.palsu()
        kon.koneksi_terapkan(lama.alamat, "", "llama")
        with asisten.S_LOCK:
            asisten.S.update(model="m1", status="siap", kita_muat=True)
        kon.koneksi_simpan({"alamat": baru.alamat})
        self.assertEqual(len(lama.yang("/models/unload")), 1)
        self.assertEqual(baru.yang("/models/unload"), [])
        with asisten.S_LOCK:
            self.assertEqual((asisten.S["model"], asisten.S["status"]), (None, "kosong"))

    def test_server_sama_tidak_membongkar_apa_apa(self):
        p = self.palsu()
        kon.koneksi_terapkan(p.alamat, "", "llama")
        with asisten.S_LOCK:
            asisten.S.update(model="m1", status="siap", kita_muat=True)
        kon.koneksi_simpan({"alamat": p.alamat, "jenis": "online"})      # hanya jenis yang berubah
        self.assertEqual(p.yang("/models/unload"), [])
        with asisten.S_LOCK:
            self.assertEqual(asisten.S["model"], "m1")


# ---------------------------------------------------------------- permintaan keluar
class TestPermintaan(Dasar):
    def test_header_authorization_ikut_di_semua_jalur(self):
        p = self.palsu(kunci=KUNCI)
        kon.koneksi_terapkan(p.alamat, KUNCI, "llama")
        agen.llama("/v1/models", timeout=5)
        list(agen.stream_chat("m1", [{"role": "user", "content": "x"}], threading.Event()))
        list(tim_llm._stream("m1", [{"role": "user", "content": "x"}], threading.Event(), 100))
        agen.llama("/models/load", {"model": "m1"}, timeout=5)
        self.assertEqual(len(p.catatan), 4)
        self.assertTrue(all(c[2] == "Bearer " + KUNCI for c in p.catatan), p.catatan)

    def test_tanpa_kunci_tidak_ada_header(self):
        p = self.palsu()
        kon.koneksi_terapkan(p.alamat, "", "llama")
        agen.llama("/v1/models", timeout=5)
        self.assertEqual(p.catatan[0][2], "")

    def test_jenis_online_tanpa_parameter_khusus_llama(self):
        p = self.palsu()
        for jenis, ada in (("llama", True), ("online", False)):
            kon.koneksi_terapkan(p.alamat, "", jenis)
            p.catatan.clear()
            list(agen.stream_chat("m1", [], threading.Event()))
            list(tim_llm._stream("m1", [], threading.Event(), 100))
            for c in p.catatan:
                self.assertEqual("chat_template_kwargs" in json.loads(c[3]), ada, (jenis, c))

    def test_awalan_api_penyedia_dipakai(self):
        p = self.palsu()
        kon.koneksi_terapkan(p.alamat + "/v1beta/openai", "", "online")
        agen.llama("/v1/models", timeout=5)
        list(agen.stream_chat("m1", [], threading.Event()))
        self.assertEqual([c[1] for c in p.catatan], ["/v1beta/openai/models", "/v1beta/openai/chat/completions"])

    def test_stream_chat_tetap_memakai_urlopen_tanpa_kunci(self):
        """Tanpa kunci tidak ada rahasia yang bisa bocor, jadi jalur urlopen biasa dipakai."""
        kon.koneksi_terapkan("http://127.0.0.1:9", "", "llama")
        with mock.patch.object(agen.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value = iter([b"data: [DONE]\n"])
            list(agen.stream_chat("m", [], threading.Event()))
        self.assertTrue(uo.called)


# ---------------------------------------------------------------- model: router dan non-router
class TestRouter(Dasar):
    def test_daftar_model_online_tanpa_status(self):
        p = self.palsu(router=False, ids=("gpt-a", "gpt-b", "gpt-c"))
        kon.koneksi_terapkan(p.alamat, "", "online")
        hasil = mdl.daftar_model()
        self.assertEqual([m["id"] for m in hasil], ["gpt-a", "gpt-b", "gpt-c"])
        self.assertTrue(all(m["llama"] is None and m["mb"] is None for m in hasil))
        self.assertFalse(mdl.router_aktif(hasil))

    def test_daftar_model_router(self):
        p = self.palsu()
        kon.koneksi_terapkan(p.alamat, "", "llama")
        self.assertTrue(mdl.router_aktif(mdl.daftar_model()))

    def test_daftar_model_lewati_entri_aneh(self):
        p = self.palsu(balas=(200, {"data": [{"id": "ok"}, {"tanpa": "id"}, "teks", {"id": 5}]}))
        kon.koneksi_terapkan(p.alamat, "", "online")
        self.assertEqual([m["id"] for m in mdl.daftar_model()], ["ok"])

    def test_muat_model_tanpa_router_tidak_memuat_atau_membongkar(self):
        p = self.palsu(router=False)
        kon.koneksi_terapkan(p.alamat, "", "online")
        with mock.patch.object(mdl.time, "sleep", side_effect=RuntimeError("tidak boleh menunggu muat")):
            mdl.muat_model("m1")
        with asisten.S_LOCK:
            self.assertEqual((asisten.S["status"], asisten.S["model"], asisten.S["kita_muat"]),
                             ("siap", "m1", False))
        self.assertEqual(p.yang("/models/load"), [])
        mdl.bongkar_model()
        self.assertEqual(p.yang("/models/unload"), [])
        with asisten.S_LOCK:
            self.assertEqual(asisten.S["status"], "kosong")

    def test_muat_model_tak_ada_di_server_online_gagal_jelas(self):
        p = self.palsu(router=False)
        kon.koneksi_terapkan(p.alamat, "", "online")
        mdl.muat_model("tidak-ada")
        with asisten.S_LOCK:
            self.assertEqual(asisten.S["status"], "error")
            self.assertIn("tidak ditemukan", asisten.S["pesan"])

    def test_muat_model_router_tetap_memuat(self):
        p = self.palsu()
        kon.koneksi_terapkan(p.alamat, "", "llama")
        with mock.patch.object(mdl.time, "sleep"), \
                mock.patch.object(mdl, "status_llama", return_value="loaded"):
            mdl.muat_model("m1")
        self.assertEqual(len(p.yang("/models/load")), 1)
        with asisten.S_LOCK:
            self.assertTrue(asisten.S["kita_muat"])

    def test_agent_status_model_tanpa_router_dianggap_siap_dan_bukan_milik_kita(self):
        p = self.palsu(router=False)
        kon.koneksi_terapkan(p.alamat, "", "online")
        self.assertEqual(tim_model.status_model("m1"), "loaded")
        self.assertIsNone(tim_model.status_model("tidak-ada"))
        ctx = tim.Konteks() if hasattr(tim, "Konteks") else mock.Mock(batal=threading.Event())
        gen = tim_model.muat("m1", ctx)
        try:
            while True:
                next(gen)
        except StopIteration as s:
            self.assertFalse(s.value)         # bukan milik kita: tidak akan dibongkar
        self.assertEqual(p.yang("/models/load"), [])
        self.assertNotIn("m1", tim_model.DIMUAT)

    def test_agent_status_router_tetap_membaca_status(self):
        p = self.palsu()
        kon.koneksi_terapkan(p.alamat, "", "llama")
        self.assertEqual(tim_model.status_model("m1"), "unloaded")


# ---------------------------------------------------------------- rute HTTP
class TestRute(Dasar):
    TOKEN = "token-uji-koneksi-1234"

    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), asisten.H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        p = mock.patch.object(asisten, "TOKEN", self.TOKEN)
        p.start()
        self.addCleanup(p.stop)

    def req(self, metode, path, body=None, token=True):
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.server.server_address[1], path),
                                   method=metode, data=json.dumps(body).encode() if body is not None else None)
        if token:
            r.add_header("Authorization", "Bearer " + self.TOKEN)
        r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_semua_rute_wajib_token(self):
        for metode, path in (("GET", "/api/koneksi"), ("POST", "/api/koneksi"),
                             ("POST", "/api/koneksi/uji"), ("POST", "/api/koneksi/reset")):
            self.assertEqual(self.req(metode, path, {}, token=False)[0], 401, path)

    def test_alur_uji_simpan_baca(self):
        p = self.palsu(kunci=KUNCI, router=False, ids=("x", "y"))
        kode, isi = self.req("POST", "/api/koneksi/uji", {"alamat": p.alamat, "key": KUNCI})
        d = json.loads(isi)
        self.assertEqual((kode, d["ok"], d["jumlah"], d["router"]), (200, True, 2, False))
        kode, isi = self.req("POST", "/api/koneksi", {"alamat": p.alamat, "key": KUNCI, "jenis": "online"})
        self.assertEqual(kode, 200)
        self.assertNotIn(KUNCI.encode(), isi)
        kode, isi = self.req("GET", "/api/koneksi")
        d = json.loads(isi)
        self.assertEqual((d["alamat"], d["jenis"], d["key_ada"]), (p.alamat, "online", True))
        self.assertNotIn(KUNCI.encode(), isi)

    def test_status_memuat_koneksi_dan_model_server_baru_tanpa_kunci(self):
        p = self.palsu(kunci=KUNCI, router=False, ids=("gpt-a", "gpt-b"))
        self.req("POST", "/api/koneksi", {"alamat": p.alamat, "key": KUNCI, "jenis": "online"})
        for path in ("/api/status", "/api/agent/status"):
            kode, isi = self.req("GET", path)
            d = json.loads(isi)
            self.assertEqual(kode, 200, path)
            self.assertEqual([m["id"] for m in d["models"]], ["gpt-a", "gpt-b"], path)
            self.assertEqual(d["koneksi"]["jenis"], "online")
            self.assertFalse(d["router"])
            self.assertNotIn(KUNCI.encode(), isi)

    def test_status_server_mati_tetap_menjawab(self):
        kon.koneksi_terapkan("http://127.0.0.1:1", "", "llama")
        kode, isi = self.req("GET", "/api/status")
        d = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual(d["models"], [])
        self.assertIn("Tidak bisa menghubungi", d["pesan"])
        self.assertEqual(d["koneksi"]["alamat"], "http://127.0.0.1:1")

    def test_isi_body_tidak_valid(self):
        self.assertEqual(self.req("POST", "/api/koneksi", ["bukan", "kamus"])[0], 400)
        self.assertEqual(self.req("POST", "/api/koneksi/uji", {"alamat": 5})[0], 400)

    def test_berkas_statis_tersedia(self):
        for path, tipe in (("/koneksi.js", b"javascript"), ("/koneksi.css", b"css")):
            r = urllib.request.urlopen("http://127.0.0.1:%d%s" % (self.server.server_address[1], path), timeout=10)
            self.assertEqual(r.status, 200)
            self.assertIn(tipe, r.headers["Content-Type"].encode())


# ---------------------------------------------------------------- beberapa koneksi sekaligus
class TestMulti(Dasar):
    """Lokal (router) + penyedia online (berkunci) bersamaan: daftar gabungan dan routing per model."""

    def siapkan(self, **kw_online):
        self.lokal = self.palsu(ids=("a", "b"))
        self.online = self.palsu(kunci=KUNCI, router=False, **({"ids": ("gpt-1", "gpt-2")} | kw_online))
        kon.koneksi_terapkan(self.lokal.alamat, "", "llama")
        kode, d = kon.koneksi_simpan({"id": "baru", "nama": "OpenRouter", "alamat": self.online.alamat + "/v1",
                                      "key": KUNCI, "jenis": "online"})
        self.assertEqual((kode, d["ok"]), (200, True), d)
        self.cid = d["id"]

    def test_tambah_koneksi_tidak_mengubah_utama(self):
        self.siapkan()
        self.assertEqual(agen.LLAMA_URL, self.lokal.alamat)
        self.assertEqual(agen.LLAMA_KEY, "")
        self.assertRegex(self.cid, r"^k[0-9a-f]{6}$")
        e = agen.LLAMA_EXTRA[self.cid]
        self.assertEqual((e["nama"], e["url"], e["v1"], e["key"], e["jenis"]),
                         ("OpenRouter", self.online.alamat, "/v1", KUNCI, "online"))

    def test_daftar_gabungan_dengan_lencana_dan_kunci_unik(self):
        self.siapkan()
        h = mdl.daftar_model()
        self.assertEqual([m["id"] for m in h], ["a", "b", self.cid + "::gpt-1", self.cid + "::gpt-2"])
        on = h[2]
        self.assertEqual((on["nama"], on["jenis"], on["koneksi"], on["sumber"], on["router"]),
                         ("gpt-1", "online", self.cid, "OpenRouter", False))
        lo = h[0]
        self.assertEqual((lo["nama"], lo["jenis"], lo["koneksi"], lo["router"]), ("a", "llama", "lokal", True))
        self.assertEqual(sstate.KONEKSI_STATUS[self.cid]["jumlah"], 2)
        self.assertTrue(sstate.KONEKSI_STATUS["lokal"]["ok"])

    def test_nama_sama_di_dua_sumber_tidak_bentrok(self):
        self.siapkan(ids=("a", "x"))                       # "a" ada di lokal dan online
        ids = [m["id"] for m in mdl.daftar_model()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("a", ids)
        self.assertIn(self.cid + "::a", ids)

    def test_chat_online_memakai_kunci_dan_nama_asli_tanpa_param_llama(self):
        self.siapkan()
        list(agen.stream_chat(self.cid + "::gpt-1", [{"role": "user", "content": "hi"}], threading.Event()))
        c = self.online.yang("/chat/completions")[0]
        self.assertEqual(c[2], "Bearer " + KUNCI)
        body = json.loads(c[3])
        self.assertEqual(body["model"], "gpt-1")
        self.assertNotIn("chat_template_kwargs", body)
        self.assertEqual(self.lokal.yang("/chat/completions"), [])          # tidak bocor ke server lokal

    def test_chat_lokal_tanpa_kunci_dan_tidak_menyentuh_online(self):
        self.siapkan()
        list(agen.stream_chat("a", [{"role": "user", "content": "hi"}], threading.Event()))
        c = self.lokal.yang("/chat/completions")[0]
        self.assertEqual(c[2], "")
        body = json.loads(c[3])
        self.assertEqual(body["model"], "a")
        self.assertIn("chat_template_kwargs", body)
        self.assertEqual(self.online.yang("/chat/completions"), [])

    def test_kunci_utama_tidak_dikirim_ke_koneksi_lain(self):
        self.lokal = self.palsu(kunci="KUNCI-UTAMA-1")
        self.online = self.palsu(kunci=KUNCI, router=False)
        kon.koneksi_terapkan(self.lokal.alamat, "KUNCI-UTAMA-1", "llama")
        cid = kon.koneksi_simpan({"id": "baru", "alamat": self.online.alamat, "key": KUNCI, "jenis": "online"})[1]["id"]
        mdl.daftar_model()
        for c in self.online.catatan:
            self.assertNotIn("KUNCI-UTAMA-1", c[2])
        for c in self.lokal.catatan:
            self.assertNotIn(KUNCI, c[2])
        self.assertTrue(cid)

    def test_agent_tim_memakai_koneksi_model(self):
        self.siapkan()
        list(tim_llm._stream(self.cid + "::gpt-2", [{"role": "user", "content": "x"}], threading.Event(), 100))
        c = self.online.yang("/chat/completions")[0]
        self.assertEqual(c[2], "Bearer " + KUNCI)
        body = json.loads(c[3])
        self.assertEqual(body["model"], "gpt-2")
        self.assertNotIn("chat_template_kwargs", body)
        list(tim_llm._stream("b", [{"role": "user", "content": "x"}], threading.Event(), 100))
        c = self.lokal.yang("/chat/completions")[0]
        self.assertEqual((c[2], json.loads(c[3])["model"]), ("", "b"))
        self.assertEqual(len(self.online.yang("/chat/completions")), 1)

    def test_agent_status_model_per_koneksi(self):
        self.siapkan()
        self.assertEqual(tim_model.status_model(self.cid + "::gpt-1"), "loaded")     # penyedia online: selalu siap
        self.assertEqual(tim_model.status_model("a"), "unloaded")                     # lokal (router): belum dimuat
        self.assertIsNone(tim_model.status_model(self.cid + "::tidak-ada"))

    def test_sebagian_gagal_model_lain_tetap_tampil(self):
        self.siapkan()
        self.online.tutup()
        h = mdl.daftar_model()
        self.assertEqual([m["id"] for m in h], ["a", "b"])
        st = sstate.KONEKSI_STATUS[self.cid]
        self.assertFalse(st["ok"])
        self.assertTrue(st["galat"])
        self.assertNotIn(KUNCI, json.dumps(st))

    def test_semua_gagal_melempar(self):
        self.siapkan()
        self.lokal.tutup()
        self.online.tutup()
        with self.assertRaises(Exception):
            mdl.daftar_model()

    def test_hanya_online_gagal_tidak_melempar_bila_utama_hidup(self):
        self.siapkan(balas=(401, {"error": "x"}))
        h = mdl.daftar_model()
        self.assertEqual([m["id"] for m in h], ["a", "b"])
        self.assertFalse(sstate.KONEKSI_STATUS[self.cid]["ok"])

    def test_nama_tampil(self):
        self.siapkan()
        self.assertEqual(mdl.nama_tampil(self.cid + "::gpt-1"), "gpt-1 · OpenRouter")
        self.assertEqual(mdl.nama_tampil("a"), "a")

    def test_ringkasan_memuat_semua_koneksi_tanpa_kunci(self):
        self.siapkan()
        mdl.daftar_model()
        r = kon.koneksi_ringkas()
        self.assertEqual([c["id"] for c in r["daftar"]], ["lokal", self.cid])
        self.assertEqual([c["utama"] for c in r["daftar"]], [True, False])
        self.assertTrue(r["daftar"][1]["key_ada"])
        self.assertEqual(r["daftar"][1]["jumlah"], 2)
        self.assertEqual(r["maks_tambahan"], kon.MAKS_TAMBAHAN)
        self.assertNotIn(KUNCI, json.dumps(r))

    def test_ubah_koneksi_tambahan_mempertahankan_kunci(self):
        self.siapkan()
        kode, d = kon.koneksi_simpan({"id": self.cid, "nama": "Ganti", "alamat": self.online.alamat + "/v1"})
        self.assertEqual(kode, 200)
        self.assertEqual(agen.LLAMA_EXTRA[self.cid]["nama"], "Ganti")
        self.assertEqual(agen.LLAMA_EXTRA[self.cid]["key"], KUNCI)
        kon.koneksi_simpan({"id": self.cid, "alamat": self.online.alamat + "/v1", "key": ""})
        self.assertEqual(agen.LLAMA_EXTRA[self.cid]["key"], "")

    def test_hapus_koneksi_tambahan(self):
        self.siapkan()
        mdl.daftar_model()
        kode, d = kon.koneksi_hapus({"id": self.cid})
        self.assertEqual((kode, d["ok"]), (200, True))
        self.assertNotIn(self.cid, agen.LLAMA_EXTRA)
        self.assertNotIn(self.cid, sstate.KONEKSI_STATUS)
        self.assertEqual([m["id"] for m in mdl.daftar_model()], ["a", "b"])
        self.assertNotIn(KUNCI, self.berkas.read_text() if self.berkas.exists() else "")

    def test_hapus_ditolak_untuk_utama_tak_dikenal_dan_saat_sibuk(self):
        self.siapkan()
        self.assertEqual(kon.koneksi_hapus({"id": "lokal"})[0], 400)
        self.assertEqual(kon.koneksi_hapus({"id": "kzzzzzz"})[0], 404)
        self.assertEqual(kon.koneksi_hapus({"id": 5})[0], 404)
        self.assertEqual(kon.koneksi_hapus(["x"])[0], 404)
        with mock.patch.object(kon, "_sibuk", return_value=True):
            self.assertEqual(kon.koneksi_hapus({"id": self.cid})[0], 409)
            self.assertEqual(kon.koneksi_simpan({"id": "baru", "alamat": "http://127.0.0.1:9"})[0], 409)
        self.assertIn(self.cid, agen.LLAMA_EXTRA)

    def test_simpan_id_tak_dikenal_ditolak(self):
        kode, d = kon.koneksi_simpan({"id": "kzzzzzz", "alamat": "http://127.0.0.1:9"})
        self.assertEqual(kode, 400)

    def test_batas_koneksi_tambahan(self):
        for i in range(kon.MAKS_TAMBAHAN):
            kode, d = kon.koneksi_simpan({"id": "baru", "alamat": "http://127.0.0.1:%d" % (9000 + i), "jenis": "online"})
            self.assertEqual(kode, 200, d)
        kode, d = kon.koneksi_simpan({"id": "baru", "alamat": "http://127.0.0.1:9999", "jenis": "online"})
        self.assertEqual(kode, 400)
        self.assertEqual(len(agen.LLAMA_EXTRA), kon.MAKS_TAMBAHAN)

    def test_nama_otomatis_bila_kosong(self):
        d = kon.koneksi_simpan({"id": "baru", "alamat": "https://api.openai.com/v1", "key": KUNCI, "jenis": "online"})[1]
        self.assertTrue(agen.LLAMA_EXTRA[d["id"]]["nama"])
        self.assertNotIn(KUNCI, agen.LLAMA_EXTRA[d["id"]]["nama"])

    def test_tersimpan_di_berkas_rahasia_dan_dimuat_ulang(self):
        self.siapkan()
        self.assertEqual(stat.S_IMODE(self.berkas.stat().st_mode), 0o600)
        isi = json.loads(self.berkas.read_text())
        self.assertEqual(len(isi["tambahan"]), 1)
        agen.LLAMA_EXTRA.clear()
        kon.koneksi_muat()
        self.assertEqual(list(agen.LLAMA_EXTRA), [self.cid])
        self.assertEqual(agen.LLAMA_EXTRA[self.cid]["key"], KUNCI)
        self.assertEqual(agen.LLAMA_EXTRA[self.cid]["jenis"], "online")

    def test_reset_hanya_koneksi_utama(self):
        self.siapkan()
        kon.koneksi_reset()
        self.assertIn(self.cid, agen.LLAMA_EXTRA)

    def test_status_model_tambahan_tidak_pakai_router(self):
        self.siapkan()
        self.assertIsNone(mdl.status_llama(self.cid + "::gpt-1"))                  # tanpa status = tak ada muat/bongkar
        self.assertEqual(mdl.status_llama("a"), "unloaded")


class TestMultiRute(TestRute):
    """Rute HTTP untuk beberapa koneksi (memakai penyiapan server dari TestRute)."""

    def test_hapus_wajib_token(self):
        self.assertEqual(self.req("POST", "/api/koneksi/hapus", {"id": "x"}, token=False)[0], 401)

    def test_alur_tambah_status_gabungan_hapus(self):
        lokal = self.palsu(ids=("a", "b"))
        online = self.palsu(kunci=KUNCI, router=False, ids=("g1", "g2", "g3"))
        kon.koneksi_terapkan(lokal.alamat, "", "llama")
        kode, isi = self.req("POST", "/api/koneksi", {"id": "baru", "nama": "OpenRouter", "alamat": online.alamat,
                                                    "key": KUNCI, "jenis": "online"})
        self.assertEqual(kode, 200)
        self.assertNotIn(KUNCI.encode(), isi)
        cid = json.loads(isi)["id"]
        for path in ("/api/status", "/api/agent/status"):
            kode, isi = self.req("GET", path)
            d = json.loads(isi)
            self.assertEqual(kode, 200, path)
            self.assertEqual([m["id"] for m in d["models"]],
                             ["a", "b"] + [cid + "::" + n for n in ("g1", "g2", "g3")], path)
            self.assertEqual([c["id"] for c in d["koneksi"]["daftar"]], ["lokal", cid], path)
            self.assertTrue(d["koneksi"]["daftar"][1]["ok"], path)
            self.assertNotIn(KUNCI.encode(), isi)
        kode, isi = self.req("GET", "/api/status")
        d = json.loads(isi)
        self.assertTrue(d["router"])                      # ditentukan koneksi utama saja
        kode, isi = self.req("POST", "/api/koneksi/hapus", {"id": cid})
        self.assertEqual(kode, 200)
        self.assertEqual([c["id"] for c in json.loads(isi)["koneksi"]["daftar"]], ["lokal"])
        self.assertEqual(self.req("POST", "/api/koneksi/hapus", {"id": cid})[0], 404)

    def test_satu_koneksi_gagal_status_tetap_menjawab(self):
        lokal = self.palsu(ids=("a",))
        kon.koneksi_terapkan(lokal.alamat, "", "llama")
        cid = json.loads(self.req("POST", "/api/koneksi", {"id": "baru", "alamat": "http://127.0.0.1:1", "jenis": "online"})[1])["id"]
        kode, isi = self.req("GET", "/api/status")
        d = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual([m["id"] for m in d["models"]], ["a"])
        gagal = [c for c in d["koneksi"]["daftar"] if c["id"] == cid][0]
        self.assertFalse(gagal["ok"])
        self.assertTrue(gagal["galat"])

    def test_uji_koneksi_tambahan_memakai_kunci_tersimpan(self):
        online = self.palsu(kunci=KUNCI, router=False)
        cid = json.loads(self.req("POST", "/api/koneksi", {"id": "baru", "alamat": online.alamat, "key": KUNCI, "jenis": "online"})[1])["id"]
        kode, isi = self.req("POST", "/api/koneksi/uji", {"id": cid, "alamat": online.alamat})
        d = json.loads(isi)
        self.assertTrue(d["ok"], d)



# ---------------------------------------------------------------- Anthropic (Claude)
class TestAnthropic(Dasar):
    """Jalur kompatibel OpenAI milik Anthropic menolak temperature < 1 dan response_format json_object pada
    model Claude terbaru, dan daftar model aslinya butuh x-api-key. Server palsu berpura-pura jadi Anthropic."""

    def setUp(self):
        super().setUp()
        p = mock.patch.object(acfg, "adalah_anthropic", lambda url: bool(url) and "127.0.0.1" in url)
        p.start()
        self.addCleanup(p.stop)

    def test_adalah_anthropic_hanya_host_resmi(self):
        f = _ASLI_ANTHROPIC          # fungsi asli (di setUp sudah diganti agar server palsu dianggap Anthropic)
        for ya in ("https://api.anthropic.com", "https://api.anthropic.com/v1", "https://API.Anthropic.com"):
            self.assertTrue(f(ya), ya)
        for tidak in ("", None, "http://127.0.0.1:8080", "https://api.anthropic.com.evil.example",
                      "https://evil.example/api.anthropic.com", "https://anthropic.com", "https://api.openai.com"):
            self.assertFalse(f(tidak), tidak)

    def test_saring_body(self):
        asli = {"model": "m", "temperature": 0.3, "top_p": 0.9, "max_tokens": 5, "stream": True,
                "messages": [], "chat_template_kwargs": {"enable_thinking": False},
                "response_format": {"type": "json_object"}}
        anth = {"url": "http://127.0.0.1:1", "jenis": "online"}
        b = acfg.saring_body(asli, anth)
        self.assertEqual(sorted(b), ["max_tokens", "messages", "model", "stream"])
        self.assertIn("temperature", asli)                                   # body asli tidak diubah
        js = dict(asli, response_format={"type": "json_schema", "json_schema": {}})
        self.assertIn("response_format", acfg.saring_body(js, anth))         # json_schema boleh

    def test_saring_body_penyedia_lain_dan_lokal_tidak_berubah_selain_param_llama(self):
        with mock.patch.object(acfg, "adalah_anthropic", lambda url: False):
            asli = {"temperature": 0.3, "chat_template_kwargs": {"x": 1}, "response_format": {"type": "json_object"}}
            on = acfg.saring_body(asli, {"url": "https://api.openai.com", "jenis": "online"})
            self.assertEqual(sorted(on), ["response_format", "temperature"])
            lo = acfg.saring_body(asli, {"url": "http://127.0.0.1:8080", "jenis": "llama"})
            self.assertEqual(sorted(lo), ["chat_template_kwargs", "response_format", "temperature"])

    def test_daftar_model_memakai_x_api_key_dan_limit(self):
        p = self.palsu(kunci=KUNCI, router=False, ids=("claude-a", "claude-b"))
        kode, d = kon.koneksi_uji({"alamat": p.alamat + "/v1", "key": KUNCI, "jenis": "online"})
        self.assertTrue(d["ok"], d)
        c = p.yang("/models")[0]
        self.assertTrue(c[1].endswith("?limit=1000"), c[1])
        self.assertEqual(p.kepala[0]["x-api-key"], KUNCI)
        self.assertEqual(p.kepala[0]["anthropic-version"], "2023-06-01")
        self.assertEqual(p.kepala[0]["authorization"], "Bearer " + KUNCI)

    def test_daftar_model_koneksi_tersimpan(self):
        p = self.palsu(kunci=KUNCI, router=False, ids=("claude-a", "claude-b"))
        lokal = self.palsu(ids=("a",))
        kon.koneksi_terapkan(lokal.alamat, "", "llama")
        cid = kon.koneksi_simpan({"id": "baru", "nama": "Claude", "alamat": p.alamat + "/v1", "key": KUNCI, "jenis": "online"})[1]["id"]
        h = mdl.daftar_model()
        self.assertEqual([m["nama"] for m in h], ["a", "claude-a", "claude-b"])
        self.assertTrue(p.kepala[-1].get("x-api-key"))
        self.assertNotIn("x-api-key", lokal.kepala[-1])          # kunci tidak bocor ke server lain
        self.assertTrue(cid)

    def test_chat_tanpa_temperature_dan_param_llama(self):
        p = self.palsu(kunci=KUNCI, router=False, ids=("claude-a",))
        lokal = self.palsu(ids=("a",))
        kon.koneksi_terapkan(lokal.alamat, "", "llama")
        cid = kon.koneksi_simpan({"id": "baru", "alamat": p.alamat + "/v1", "key": KUNCI, "jenis": "online"})[1]["id"]
        list(agen.stream_chat(cid + "::claude-a", [{"role": "user", "content": "hai"}], threading.Event()))
        body = json.loads(p.yang("/chat/completions")[0][3])
        self.assertEqual(sorted(body), ["max_tokens", "messages", "model", "stream"])
        self.assertEqual(body["model"], "claude-a")
        # permintaan chat biasa tidak membawa x-api-key (jalur kompatibel OpenAI memakai Authorization)
        self.assertNotIn("x-api-key", p.kepala[-1])

    def test_agent_tanpa_temperature_dan_json_object(self):
        p = self.palsu(kunci=KUNCI, router=False, ids=("claude-a",))
        lokal = self.palsu(ids=("a",))
        kon.koneksi_terapkan(lokal.alamat, "", "llama")
        cid = kon.koneksi_simpan({"id": "baru", "alamat": p.alamat + "/v1", "key": KUNCI, "jenis": "online"})[1]["id"]
        list(tim_llm._stream(cid + "::claude-a", [{"role": "user", "content": "x"}], threading.Event(), 100, json_mode=True))
        body = json.loads(p.yang("/chat/completions")[0][3])
        self.assertEqual(sorted(body), ["max_tokens", "messages", "model", "stream"])

    def test_permintaan_biasa_ringkasan_tanpa_temperature(self):
        p = self.palsu(kunci=KUNCI, router=False, ids=("claude-a",), balas=None)
        lokal = self.palsu(ids=("a",))
        kon.koneksi_terapkan(lokal.alamat, "", "llama")
        cid = kon.koneksi_simpan({"id": "baru", "alamat": p.alamat + "/v1", "key": KUNCI, "jenis": "online"})[1]["id"]
        try:
            agen.llama("/v1/chat/completions", {"model": cid + "::claude-a", "temperature": 0.2, "max_tokens": 9, "stream": False,
                                                "messages": [], "chat_template_kwargs": {}})
        except Exception:  # noqa: BLE001  - jawaban palsu bukan JSON biasa; yang dicek isi permintaannya
            pass
        body = json.loads(p.yang("/chat/completions")[0][3])
        self.assertNotIn("temperature", body)
        self.assertNotIn("chat_template_kwargs", body)


# ---------------------------------------------------------------- aplikasi tetap hidup tanpa llama-server
class TestAplikasiTanpaLlama(unittest.TestCase):
    def test_asisten_naik_walau_llama_server_mati_dan_berhenti_rapi(self):
        with tempfile.TemporaryDirectory() as tmp:
            kode = (
                "import sys\n"
                "from pathlib import Path\n"
                "sys.path.insert(0, %r)\n"
                "import asisten\n"
                "from server import server_config as c\n"
                "c.TOKEN_FILE = Path(%r) / 'token'\n"
                "c.RIWAYAT = Path(%r) / 'riwayat'\n"
                "sys.argv = ['asisten.py', '--port', %r, '--host', '127.0.0.1', '--tanpa-warna']\n"
                "asisten.main()\n")
            s = __import__("socket").socket()
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
            s.close()
            env = dict(os.environ, LLAMA_BASE_URL="http://127.0.0.1:1", ASISTEN_PENGATURAN=str(Path(tmp) / "p.json"),
                       HOME=tmp)
            env.pop("LLAMA_API_KEY", None)
            pr = subprocess.Popen([sys.executable, "-c", kode % (str(ROOT), tmp, tmp, str(port))],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
            keluaran = []
            try:
                for baris in pr.stdout:
                    keluaran.append(baris)
                    if "Tekan Ctrl+C" in baris:
                        break
                self.assertIn("Tekan Ctrl+C", "".join(keluaran), "".join(keluaran))
                self.assertIn("Belum bisa menghubungi llama-server", "".join(keluaran))
                token = (Path(tmp) / "token").read_text().strip()
                r = urllib.request.Request("http://127.0.0.1:%d/api/status" % port,
                                           headers={"Authorization": "Bearer " + token})
                with urllib.request.urlopen(r, timeout=10) as resp:
                    d = json.loads(resp.read())
                self.assertEqual(d["models"], [])
                self.assertEqual(d["koneksi"]["alamat"], "http://127.0.0.1:1")
                pr.send_signal(signal.SIGTERM)
                self.assertEqual(pr.wait(timeout=20), 0)
            finally:
                if pr.poll() is None:
                    pr.kill()
                    pr.wait()


# ---------------------------------------------------------------- tampilan web
class TestTampilan(unittest.TestCase):
    def test_dialog_koneksi_dengan_dom_tiruan(self):
        node = __import__("shutil").which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, str(ROOT / "tests" / "koneksi_smoke.js")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("OK", r.stdout)

    def test_pilihan_model_agent_dikelompokkan_lokal_online(self):
        node = __import__("shutil").which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        with tempfile.TemporaryDirectory() as d:
            nd = Path(d) / "ev.ndjson"
            nd.write_text(json.dumps({"type": "info", "teks": "x"}) + "\n")
            r = subprocess.run([node, str(ROOT / "tests" / "agent_smoke.js"), str(nd), "campur"],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        h = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual([(g["tag"], g["label"]) for g in h["pilihan"]],
                         [("optgroup", "Lokal · llama-server"), ("optgroup", "Online · OpenRouter")])
        self.assertEqual([[o["v"] for o in g["anak"]] for g in h["pilihan"]], [["A", "B"], ["k1::gpt-4o"]])
        self.assertEqual(h["pilihan"][1]["anak"][0]["t"], "gpt-4o ☁")          # kunci "k1::" tidak tampil

    def test_halaman_memuat_dialog_koneksi(self):
        for nama in ("index.html", "agent.html"):
            html = (ROOT / "web" / nama).read_text(encoding="utf-8")
            self.assertIn('id="koneksiBaris"', html, nama)
            self.assertIn('src="koneksi.js"', html, nama)
            self.assertIn('href="koneksi.css"', html, nama)

    def test_kunci_tidak_pernah_ditulis_ke_penyimpanan_browser(self):
        js = (ROOT / "web" / "koneksi.js").read_text(encoding="utf-8")
        self.assertNotIn("localStorage", js)
        self.assertNotIn("sessionStorage", js)


if __name__ == "__main__":
    unittest.main()
