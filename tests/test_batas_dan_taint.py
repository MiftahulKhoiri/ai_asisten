"""Pengujian perbaikan 5-8: kunci generasi tidak bocor, max_history mengikuti ASISTEN_CTX,
jawaban/tool terpotong batas token terdeteksi, dan tool web membuat AUTO tidak berlaku.
Jalankan: python3 -m unittest discover -s tests -v"""
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402
import asisten  # noqa: E402
from src import tolls, util  # noqa: E402

TOKEN = "token-uji-58"
_TMP_LOG = None
_LOG_ASLI = None


def setUpModule():
    """Catatan aksi dari tes ditulis ke folder sementara, bukan ke aksi.log yang asli."""
    global _TMP_LOG, _LOG_ASLI
    _TMP_LOG = tempfile.TemporaryDirectory()
    _LOG_ASLI = agen.LOG_AKSI
    agen.LOG_AKSI = Path(_TMP_LOG.name) / "aksi.log"


def tearDownModule():
    agen.LOG_AKSI = _LOG_ASLI
    _TMP_LOG.cleanup()


# ---------------------------------------------------------------- 5. kunci generasi
class TestKunciGenerasi(unittest.TestCase):
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
        with asisten.S_LOCK:
            self._s = dict(asisten.S)
            asisten.S.update(status="siap", model="m", skill=("tanpa",))
        self.cid = self.post("/api/chat/baru", {})[1]["id"]

    def tearDown(self):
        with asisten.S_LOCK:
            asisten.S.clear()
            asisten.S.update(self._s)

    def post(self, path, body):
        r = urllib.request.Request(self.base + path, data=json.dumps(body).encode(), method="POST")
        r.add_header("Authorization", "Bearer " + TOKEN)
        r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, json.loads(resp.read() or b"{}") if "json" in resp.headers.get(
                    "Content-Type", "") and "ndjson" not in resp.headers.get("Content-Type", "") else resp.read()
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    @staticmethod
    def giliran_palsu(riwayat, model, ctx, memori=None):
        riwayat.append({"role": "assistant", "content": "ok"})
        yield {"t": "token", "d": "ok"}
        yield {"t": "selesai"}

    def test_gagal_menyimpan_melepas_kunci(self):
        with mock.patch.object(asisten, "simpan_chat", side_effect=OSError("disk penuh")):
            kode, _ = self.post("/api/kirim", {"id": self.cid, "teks": "halo"})
        self.assertEqual(kode, 500)
        self.assertFalse(asisten.GEN_LOCK.locked())
        self.assertIsNone(asisten.AKTIF["ctx"])

    def test_gagal_membuat_ctx_melepas_kunci(self):
        with mock.patch.object(asisten, "Ctx", side_effect=RuntimeError("tak bisa")):
            kode, _ = self.post("/api/kirim", {"id": self.cid, "teks": "halo"})
        self.assertEqual(kode, 500)
        self.assertFalse(asisten.GEN_LOCK.locked())

    def test_obrolan_tidak_ada_melepas_kunci(self):
        kode, _ = self.post("/api/kirim", {"id": "20260101-000000-zzzz", "teks": "halo"})
        self.assertEqual(kode, 404)
        self.assertFalse(asisten.GEN_LOCK.locked())

    def test_kirim_berikutnya_tetap_jalan_dan_melepas_kunci(self):
        with mock.patch.object(asisten, "simpan_chat", side_effect=OSError("disk penuh")):
            self.post("/api/kirim", {"id": self.cid, "teks": "halo"})
        with mock.patch.object(asisten.agen, "giliran", self.giliran_palsu):
            kode, isi = self.post("/api/kirim", {"id": self.cid, "teks": "halo lagi"})
        self.assertEqual(kode, 200)
        self.assertIn(b'"selesai"', isi)
        self.assertFalse(asisten.GEN_LOCK.locked())


# ---------------------------------------------------------------- 6. max_history dan env
class TestMaxHistory(unittest.TestCase):
    @staticmethod
    def lama(panjang_tools):
        return max(5000, min(12000, 24000 - 1800 - panjang_tools - 2100 - 3000))

    def hitung(self, ctx, maks=700, panjang=0):
        tools = [{"x": "y" * max(0, panjang - 11)}] if panjang else []
        with mock.patch.object(agen, "CTX_MAKS", ctx), mock.patch.object(agen, "MAX_TOKENS", maks):
            return agen.max_history(tools), len(json.dumps(tools))

    def test_bawaan_sama_dengan_rumus_lama(self):
        for panjang in (0, 3000, 6000, 9000, 15000):
            with self.subTest(panjang=panjang):
                h, n = self.hitung(8192, 700, panjang)
                self.assertEqual(h, self.lama(n))

    def test_mengikuti_ukuran_konteks(self):
        kecil, besar, bawaan = (self.hitung(c)[0] for c in (4096, 16384, 8192))
        self.assertLess(kecil, bawaan)
        self.assertLess(bawaan, besar)
        self.assertEqual(besar, 24000)   # batas atas = setengah dari total karakter

    def test_konteks_kecil_dengan_banyak_tool_tidak_negatif(self):
        h, _ = self.hitung(4096, 700, 9000)
        self.assertEqual(h, 12000 * 5 // 24)

    def test_jawaban_lebih_panjang_mengurangi_riwayat(self):
        h1, _ = self.hitung(4096, 700)
        h2, _ = self.hitung(4096, 1500)
        self.assertLess(h2, h1)

    def test_env_rusak_memakai_bawaan(self):
        with mock.patch.dict("os.environ", {"X_UJI": "abc"}):
            self.assertEqual(agen._env_int("X_UJI", 700, 64), 700)
        with mock.patch.dict("os.environ", {"X_UJI": "5"}):
            self.assertEqual(agen._env_int("X_UJI", 700, 64), 64)
        with mock.patch.dict("os.environ", {"X_UJI": "1500"}):
            self.assertEqual(agen._env_int("X_UJI", 700, 64), 1500)


# ---------------------------------------------------------------- 7. terpotong batas token
class Ctx:
    def __init__(self, skill, auto=True, izin=True):
        self.skill, self.batal, self.auto = skill, threading.Event(), auto
        self.izin, self.ditanya, self.ringkas = izin, [], []

    def konfirmasi(self, jenis, ringkas, detail=""):
        self.ditanya.append(jenis)
        self.ringkas.append(ringkas)
        return self.izin


def chunk(teks=None, tool=None, selesai=None):
    d = {}
    if teks is not None:
        d["content"] = teks
    if tool:
        d["tool_calls"] = [{"index": 0, "id": "c1", "function": {"name": tool[0], "arguments": tool[1]}}]
    pil = {"delta": d}
    if selesai:
        pil["finish_reason"] = selesai
    return {"choices": [pil]}


class Palsu:
    def __init__(self, *jawaban):
        self.jawaban, self.panggilan = list(jawaban), []

    def __call__(self, model, pesan, batal, tools=None):
        self.panggilan.append({"pesan": pesan, "tools": tools})
        yield from self.jawaban.pop(0)


def jalan(skill, riwayat, palsu, ctx=None):
    ctx = ctx or Ctx(skill)
    asli_s, asli_g = agen.stream_chat, agen.GERBANG
    agen.stream_chat, agen.GERBANG = palsu, False
    try:
        return list(agen.giliran(riwayat, "m", ctx)), ctx
    finally:
        agen.stream_chat, agen.GERBANG = asli_s, asli_g


def jenis(ev):
    return [e["t"] for e in ev]


class TestTerpotong(unittest.TestCase):
    def test_stream_chat_memakai_max_tokens(self):
        with mock.patch.object(agen, "MAX_TOKENS", 1234), \
                mock.patch.object(agen.urllib.request, "urlopen") as uo:
            uo.return_value.__enter__.return_value = iter([b"data: [DONE]\n"])
            list(agen.stream_chat("m", [], threading.Event()))
        body = json.loads(uo.call_args[0][0].data)
        self.assertEqual(body["max_tokens"], 1234)

    def test_jawaban_terpotong_diberi_catatan(self):
        riwayat = [{"role": "user", "content": "ceritakan panjang"}]
        ev, _ = jalan(("tanpa",), riwayat, Palsu([chunk("Pada suatu hari", selesai="length")]))
        self.assertIn("terpotong", jenis(ev))
        tampil = "".join(e["d"] for e in ev if e["t"] == "token")
        self.assertTrue(tampil.startswith("Pada suatu hari"))
        self.assertIn("Jawaban terpotong", tampil)
        self.assertIn("Jawaban terpotong", riwayat[-1]["content"])
        self.assertEqual(jenis(ev)[-1], "selesai")

    def test_jawaban_utuh_tanpa_catatan(self):
        riwayat = [{"role": "user", "content": "halo"}]
        ev, _ = jalan(("tanpa",), riwayat, Palsu([chunk("Halo!", selesai="stop")]))
        self.assertNotIn("terpotong", jenis(ev))
        self.assertEqual(riwayat[-1]["content"], "Halo!")

    def test_tool_call_terpotong_dilaporkan_khusus(self):
        riwayat = [{"role": "user", "content": "tulis file panjang"}]
        potong = chunk(tool=("tulis_file", '{"path":"~/a.txt","isi":"abc'), selesai="length")
        ev, _ = jalan(("kompleks",), riwayat, Palsu([potong], [chunk("ok", selesai="stop")]))
        self.assertIn("terpotong", jenis(ev))
        hasil = [e["d"] for e in ev if e["t"] == "hasil"][0]
        self.assertIn("terpotong karena batas token", hasil)
        self.assertIn("tambah=true", hasil)

    def test_json_rusak_biasa_tetap_pesan_lama(self):
        riwayat = [{"role": "user", "content": "hitung"}]
        ev, _ = jalan(("kompleks",), riwayat,
                      Palsu([chunk(tool=("hitung", "{bad"), selesai="tool_calls")], [chunk("ok")]))
        self.assertNotIn("terpotong", jenis(ev))
        self.assertIn("bukan JSON object yang valid", [e["d"] for e in ev if e["t"] == "hasil"][0])

    def test_kritis_tahap_dua_terpotong(self):
        draf = "Ini draf jawaban yang cukup panjang supaya diperiksa ulang oleh tahap kedua berpikir kritis."
        riwayat = [{"role": "user", "content": "jelaskan"}]
        ev, _ = jalan(("kritis",), riwayat,
                      Palsu([chunk(draf, selesai="stop")],
                            [chunk("Jawaban final yang terputus di teng", selesai="length")]))
        self.assertIn("terpotong", jenis(ev))
        final = [e["d"] for e in ev if e["t"] == "token"][-1]
        self.assertIn("Jawaban terpotong", final)


# ---------------------------------------------------------------- 8. tool web -> AUTO tidak berlaku
class TestSumberLuar(unittest.TestCase):
    def test_penandaan_registri(self):
        for n in ("ambil_url", "baca_halaman", "berita", "cari_web"):
            self.assertTrue(tolls.REGISTRY[n]["luar"], n)
        for n in ("hitung", "baca_file", "tulis_file", "jalankan_perintah", "waktu_sekarang"):
            self.assertFalse(tolls.REGISTRY[n]["luar"], n)

    def test_izin_auto_normal_tidak_bertanya(self):
        ctx = Ctx(("kompleks",), auto=True)
        self.assertIsNone(util._izin(ctx, "tulis", "x"))
        self.assertEqual(ctx.ditanya, [])

    def test_izin_auto_tercemar_bertanya_dan_diberi_tanda(self):
        ctx = Ctx(("kompleks",), auto=True, izin=False)
        ctx.tercemar = True
        self.assertTrue(util._izin(ctx, "tulis", "x").startswith("DIBATALKAN"))
        self.assertEqual(ctx.ditanya, ["tulis"])
        self.assertIn("setelah tool web", ctx.ringkas[0])

    def _tulis(self, d):
        return json.dumps({"path": str(Path(d) / "a.txt"), "isi": "halo"})

    def test_tool_web_di_giliran_yang_sama_memaksa_izin(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch("src.tool_web._ambil_berita", return_value=[], create=True):
            palsu = Palsu([chunk(tool=("berita", "{}"))],
                          [chunk(tool=("tulis_file", self._tulis(d)))], [chunk("selesai")])
            riwayat = [{"role": "user", "content": "cari berita lalu buat file"}]
            ev, ctx = jalan(("kompleks",), riwayat, palsu, Ctx(("kompleks",), auto=True, izin=False))
            self.assertEqual(ctx.ditanya, ["tulis"])
            self.assertFalse((Path(d) / "a.txt").exists())
        self.assertTrue(ctx.tercemar)

    def test_tanpa_tool_web_auto_tetap_mulus(self):
        with tempfile.TemporaryDirectory() as d:
            palsu = Palsu([chunk(tool=("tulis_file", self._tulis(d)))], [chunk("selesai")])
            riwayat = [{"role": "user", "content": "buat file a.txt"}]
            ev, ctx = jalan(("kompleks",), riwayat, palsu, Ctx(("kompleks",), auto=True, izin=False))
            self.assertEqual(ctx.ditanya, [])
            self.assertTrue((Path(d) / "a.txt").exists())
        self.assertFalse(getattr(ctx, "tercemar", False))

    def test_riwayat_lama_yang_memakai_web_menandai_obrolan(self):
        lama = [{"role": "user", "content": "cari info"},
                {"role": "assistant", "content": "",
                 "tool_calls": [{"id": "c0", "type": "function",
                                 "function": {"name": "cari_web", "arguments": '{"kueri":"x"}'}}]},
                {"role": "tool", "tool_call_id": "c0", "content": "hasil web"},
                {"role": "assistant", "content": "ini hasilnya"}]
        self.assertTrue(agen._riwayat_tercemar(lama))
        with tempfile.TemporaryDirectory() as d:
            riwayat = lama + [{"role": "user", "content": "buat file a.txt"}]
            palsu = Palsu([chunk(tool=("tulis_file", self._tulis(d)))], [chunk("selesai")])
            ev, ctx = jalan(("kompleks",), riwayat, palsu, Ctx(("kompleks",), auto=True, izin=False))
            self.assertEqual(ctx.ditanya, ["tulis"])

    def test_riwayat_tanpa_tool_web_tidak_menandai(self):
        riwayat = [{"role": "assistant", "content": "",
                    "tool_calls": [{"id": "c0", "function": {"name": "hitung", "arguments": "{}"}}]}]
        self.assertFalse(agen._riwayat_tercemar(riwayat))
        self.assertFalse(agen._riwayat_tercemar([]))


if __name__ == "__main__":
    unittest.main()
