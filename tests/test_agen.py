"""Pengujian agen.py: skill gabungan, gerbang tool, dan skill berpikir kritis (dua tahap)."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402

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

DRAF = "Ini draf jawaban yang cukup panjang supaya diperiksa ulang oleh tahap kedua berpikir kritis."


class Ctx:
    def __init__(self, skill):
        self.skill, self.batal, self.auto = skill, threading.Event(), True

    def konfirmasi(self, *a, **k):
        return True


def chunk(teks=None, tool=None):
    d = {}
    if teks is not None:
        d["content"] = teks
    if tool:
        d["tool_calls"] = [{"index": 0, "id": "c1", "function": {"name": tool[0], "arguments": tool[1]}}]
    return {"choices": [{"delta": d}]}


class Palsu:
    """Pengganti agen.stream_chat: memberi jawaban berurutan dan mencatat permintaan."""

    def __init__(self, *jawaban):
        self.jawaban, self.panggilan = list(jawaban), []

    def __call__(self, model, pesan, batal, tools=None):
        self.panggilan.append({"pesan": pesan, "tools": tools})
        yield from self.jawaban.pop(0)


def jalan(skill, user, palsu):
    asli, agen.stream_chat = agen.stream_chat, palsu
    try:
        riwayat = [{"role": "user", "content": user}]
        return riwayat, list(agen.giliran(riwayat, "m", Ctx(skill)))
    finally:
        agen.stream_chat = asli


def jenis(ev):
    return [e["t"] for e in ev]


def teks(ev, t="token"):
    return "".join(e["d"] for e in ev if e["t"] == t)


class TestPrompt(unittest.TestCase):
    def test_per_skill(self):
        web = agen.buat_system("", ("web",))
        self.assertIn("SKILL WEB AKTIF", web)
        self.assertNotIn("Raspberry Pi 5", web)          # web saja: tanpa akses sistem
        self.assertNotIn("BERPIKIR KRITIS", web)
        self.assertIn("BERPIKIR KRITIS", agen.buat_system("", ("kritis",)))
        gabung = agen.buat_system("", ("web", "dasar", "kritis"))
        self.assertIn("SKILL WEB AKTIF", gabung)
        self.assertIn("BERPIKIR KRITIS", gabung)
        self.assertIn("Raspberry Pi 5", gabung)
        self.assertIn("Tool yang tersedia saat ini hanya", gabung)
        self.assertIn("8. Pilih tool", agen.buat_system("", ("kompleks",)))
        self.assertNotIn("Tool yang tersedia", agen.buat_system("", ("tanpa",)))

    def test_ringkasan_ikut(self):
        self.assertIn("RINGKAS-UJI", agen.buat_system("RINGKAS-UJI", ("web",)))


class TestGerbang(unittest.TestCase):
    def test_web(self):
        self.assertFalse(agen.perlu_tool("halo", [], ("web",)))
        self.assertTrue(agen.perlu_tool("carikan berita terbaru hari ini", [], ("web",)))
        self.assertTrue(agen.perlu_tool("berapa harga emas sekarang", [], ("web",)))
        self.assertFalse(agen.perlu_tool("baca file notes.txt", [], ("web",)))   # tool sistem tak aktif

    def test_sistem(self):
        self.assertTrue(agen.perlu_tool("baca file notes.txt", [], ("dasar",)))
        self.assertFalse(agen.perlu_tool("halo", [], ("kompleks",)))
        self.assertTrue(agen.perlu_tool("baca file notes.txt", [], ("web", "dasar")))


class TestGiliran(unittest.TestCase):
    def test_tanpa_skill_langsung_token(self):
        palsu = Palsu([chunk("Halo"), chunk(" dunia")])
        riwayat, ev = jalan(("tanpa",), "halo", palsu)
        self.assertEqual(teks(ev), "Halo dunia")
        self.assertNotIn("pikir", jenis(ev))
        self.assertIsNone(palsu.panggilan[0]["tools"])
        self.assertEqual(riwayat[-1], {"role": "assistant", "content": "Halo dunia"})

    def test_kritis_dua_tahap(self):
        palsu = Palsu([chunk(DRAF)], [chunk("Jawaban "), chunk("final.")])
        riwayat, ev = jalan(("kritis",), "jelaskan sesuatu", palsu)
        self.assertEqual(len(palsu.panggilan), 2)
        self.assertEqual(teks(ev, "pikir"), DRAF)               # draf tampil sebagai "berpikir"
        self.assertEqual(teks(ev), "Jawaban final.")            # hanya jawaban final sebagai token
        self.assertIn("kritik", jenis(ev))
        pesan2 = palsu.panggilan[1]["pesan"]
        self.assertEqual(pesan2[-1]["content"], agen.PROMPT_KRITIK)
        self.assertEqual(pesan2[-2], {"role": "assistant", "content": DRAF})
        self.assertEqual(riwayat[-1]["content"], "Jawaban final.")   # draf tidak disimpan
        self.assertEqual([m["role"] for m in riwayat], ["user", "assistant"])

    def test_kritis_label_final_dibuang(self):
        palsu = Palsu([chunk(DRAF)], [chunk(DRAF + "\n\nJAWABAN FINAL:\n\nIsi yang benar.")])
        riwayat, ev = jalan(("kritis",), "jelaskan sesuatu", palsu)
        self.assertEqual(teks(ev), "Isi yang benar.")
        self.assertEqual(riwayat[-1]["content"], "Isi yang benar.")

    def test_kritis_draf_pendek_tidak_diperiksa(self):
        palsu = Palsu([chunk("Halo!")])
        riwayat, ev = jalan(("kritis",), "halo", palsu)
        self.assertEqual(len(palsu.panggilan), 1)
        self.assertEqual(teks(ev), "Halo!")
        self.assertNotIn("kritik", jenis(ev))
        self.assertEqual(riwayat[-1]["content"], "Halo!")

    def test_kritis_pemeriksaan_kosong_pakai_draf(self):
        riwayat, ev = jalan(("kritis",), "jelaskan sesuatu", Palsu([chunk(DRAF)], []))
        self.assertEqual(teks(ev), DRAF)
        self.assertEqual(riwayat[-1]["content"], DRAF)

    def test_web_memanggil_tool(self):
        palsu = Palsu([chunk(tool=("waktu_sekarang", "{}"))], [chunk("Sekarang hari ini.")])
        riwayat, ev = jalan(("tanpa", "web"), "berita terbaru hari ini", palsu)
        self.assertEqual(jenis(ev)[:2], ["tool", "hasil"])
        nama = {t["function"]["name"] for t in palsu.panggilan[0]["tools"]}
        self.assertEqual(nama, {"cari_web", "berita", "baca_halaman", "waktu_sekarang"})
        self.assertRegex(next(e["d"] for e in ev if e["t"] == "hasil"), r"\d{4}-\d{2}-\d{2}")
        self.assertEqual([m["role"] for m in riwayat], ["user", "assistant", "tool", "assistant"])

    def test_web_tanpa_kata_kunci_tidak_kirim_tool(self):
        palsu = Palsu([chunk("Halo juga!")])
        jalan(("web",), "halo", palsu)
        self.assertIsNone(palsu.panggilan[0]["tools"])

    def test_web_dan_kritis_tiga_panggilan(self):
        palsu = Palsu([chunk(tool=("waktu_sekarang", "{}"))], [chunk(DRAF)], [chunk("Final bagus.")])
        riwayat, ev = jalan(("web", "kritis"), "berita terbaru hari ini", palsu)
        self.assertEqual(len(palsu.panggilan), 3)
        self.assertEqual(riwayat[-1]["content"], "Final bagus.")
        self.assertEqual(teks(ev), "Final bagus.")


def ambil_hasil(gen):
    """Kumpulkan event dari generator beserta nilai kembaliannya (untuk `yield from`)."""
    ev = []
    try:
        while True:
            ev.append(next(gen))
    except StopIteration as e:
        return ev, e.value


class TestLangkahGiliran(unittest.TestCase):
    """Fungsi-fungsi kecil hasil pemecahan giliran() serta perilaku antar-putarannya."""

    def test_gabung_tool_call_bertahap(self):
        calls = {}
        agen._gabung_tool_call(calls, {"index": 0, "id": "c1", "function": {"name": "hit"}})
        agen._gabung_tool_call(calls, {"index": 0, "function": {"arguments": '{"a":'}})
        agen._gabung_tool_call(calls, {"index": 0, "function": {"arguments": "1}"}})
        self.assertEqual(calls[0]["id"], "c1")
        self.assertEqual(calls[0]["function"], {"name": "hit", "arguments": '{"a":1}'})

    def test_event_info(self):
        self.assertIsNone(agen._event_info(None))
        info = agen._event_info({"predicted_n": 7, "prompt_n": 30, "cache_n": 5,
                                 "predicted_per_second": 12.345})
        self.assertEqual((info["t"], info["tok_s"], info["tok"], info["pakai"]),
                         ("info", 12.3, 7, 42))
        self.assertEqual(info["maks"], agen.CTX_MAKS)

    def test_urut_tool_calls_beri_id(self):
        calls = {1: {"id": "", "function": {"name": "b", "arguments": "{}"}},
                 0: {"id": "x", "function": {"name": "a", "arguments": "{}"}}}
        daftar = agen._urut_tool_calls(calls, 3)
        self.assertEqual([c["function"]["name"] for c in daftar], ["a", "b"])
        self.assertEqual([c["id"] for c in daftar], ["x", "call_3_1"])

    def test_baca_stream_error_mengembalikan_none(self):
        def rusak(model, pesan, batal, tools=None):
            yield chunk("a")
            raise RuntimeError("meledak")
        asli, agen.stream_chat = agen.stream_chat, rusak
        try:
            ev, nilai = ambil_hasil(agen._baca_stream("m", [], Ctx(("tanpa",)), None, False))
        finally:
            agen.stream_chat = asli
        self.assertIsNone(nilai)
        self.assertEqual(jenis(ev), ["token", "error"])
        self.assertIn("RuntimeError: meledak", ev[-1]["d"])

    def test_baca_stream_sukses_mengembalikan_teks(self):
        palsu = Palsu([chunk("ha"), chunk("lo")])
        asli, agen.stream_chat = agen.stream_chat, palsu
        try:
            ev, nilai = ambil_hasil(agen._baca_stream("m", [], Ctx(("tanpa",)), None, False))
        finally:
            agen.stream_chat = asli
        self.assertEqual(nilai[0], "halo")
        self.assertEqual(teks(ev), "halo")

    def test_tool_dengan_argumen_sama_tidak_diulang(self):
        panggil = ("hitung", '{"ekspresi":"2+3"}')
        palsu = Palsu([chunk(tool=panggil)], [chunk(tool=panggil)], [chunk("selesai")])
        asli, agen.GERBANG = agen.GERBANG, False
        try:
            riwayat, ev = jalan(("kompleks",), "hitung", palsu)
        finally:
            agen.GERBANG = asli
        hasil = [e["d"] for e in ev if e["t"] == "hasil"]
        self.assertEqual(hasil[0], "2+3 = 5")
        self.assertIn("sudah dijalankan", hasil[1])
        self.assertEqual(jenis(ev)[-1], "selesai")

    def test_batas_putaran(self):
        putaran = [[chunk(tool=("hitung", '{"ekspresi":"1+%d"}' % k))]
                   for k in range(1, agen.MAX_STEPS + 3)]
        palsu = Palsu(*putaran)
        asli, agen.GERBANG = agen.GERBANG, False
        try:
            riwayat, ev = jalan(("kompleks",), "hitung", palsu)
        finally:
            agen.GERBANG = asli
        self.assertEqual(jenis(ev)[-1], "batas")
        self.assertEqual(len(palsu.panggilan), agen.MAX_STEPS)

    def test_argumen_json_rusak_dilaporkan(self):
        palsu = Palsu([chunk(tool=("hitung", "{bad"))], [chunk("ok")])
        asli, agen.GERBANG = agen.GERBANG, False
        try:
            riwayat, ev = jalan(("kompleks",), "hitung", palsu)
        finally:
            agen.GERBANG = asli
        self.assertIn("argumen bukan JSON", next(e["d"] for e in ev if e["t"] == "hasil"))


if __name__ == "__main__":
    unittest.main()
