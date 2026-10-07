"""Pengujian agen.py: skill gabungan, gerbang tool, dan skill berpikir kritis (dua tahap)."""
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
