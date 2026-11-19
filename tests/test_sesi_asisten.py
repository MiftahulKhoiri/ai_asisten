"""Pengujian Sesi AI Asisten (gabungan AI Chatboot + Agent): deteksi tugas dari pesan pengguna,
/api/asisten/deteksi (kapan tawaran "Kerjakan dengan tim Agent?" muncul), dan halaman /asisten."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import asisten  # noqa: E402
from server import server_chat, server_handoff  # noqa: E402
from test_serahterima import DasarSerah, setUpModule as _setUp, tearDownModule as _tear  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"


def setUpModule():
    _setUp()


def tearDownModule():
    _tear()


TUGAS = [
    "buatkan script python untuk download video youtube", "tolong perbaiki bug di kode ini",
    "bikin aplikasi kalkulator web", "tambahkan fitur login di app.py", "ubah warna halaman jadi biru",
    "kerjakan dengan agent ya", "oke serahkan ke agent", "tolong buatkan program c++ untuk sorting",
    "saya mau program kalkulator di python", "pakai agent saja buat ini", "buat file README.md untuk proyek ini",
    "fix error di main.py", "refactor fungsi hitung di modul util",
]
BUKAN = [
    "apa itu python?", "jelaskan cara kerja fastapi", "halo apa kabar", "kenapa error ini muncul: TypeError",
    "berapa suhu cpu sekarang?", "buat puisi tentang hujan", "cek folder home saya ada apa saja", "perbaiki",
    "bagaimana cara membuat program python?", "gimana cara bikin web pakai flask", "saya mau belajar python",
    "apa itu agent?", "", "   ",
]


class TestDeteksiTugas(unittest.TestCase):
    def test_tugas(self):
        for t in TUGAS:
            with self.subTest(teks=t):
                self.assertTrue(server_handoff.deteksi_tugas(t)["tugas"])

    def test_bukan_tugas(self):
        for t in BUKAN:
            with self.subTest(teks=t):
                self.assertFalse(server_handoff.deteksi_tugas(t)["tugas"])

    def test_lampiran_cukup_dengan_kata_kerja(self):
        self.assertFalse(server_handoff.deteksi_tugas("tolong rapikan")["tugas"])
        self.assertTrue(server_handoff.deteksi_tugas("tolong rapikan", ada_lampiran=True)["tugas"])

    def test_selalu_ada_alasan(self):
        for t in TUGAS + BUKAN:
            self.assertTrue(server_handoff.deteksi_tugas(t)["alasan"])


class TestApiDeteksi(DasarSerah):
    def deteksi(self, cid=None):
        kode, isi = self.req("POST", "/api/asisten/deteksi", {"id": self.cid if cid is None else cid})
        return kode, json.loads(isi)

    def test_tugas_ditawarkan_dengan_jalur(self):
        self.siap()
        self.diskusi(("user", "buatkan script python untuk menghitung luas lingkaran"), ("assistant", "Baik, ..."))
        kode, d = self.deteksi()
        self.assertEqual(kode, 200)
        self.assertTrue(d["tawar"])
        self.assertEqual(d["jalur"], "buat")
        self.assertTrue(d["jalur_label"])
        self.assertIsNone(d["lanjut"])

    def test_pertanyaan_tidak_ditawarkan(self):
        self.siap()
        self.diskusi(("user", "apa itu rekursi?"), ("assistant", "Rekursi adalah ..."))
        self.assertFalse(self.deteksi()[1]["tawar"])

    def test_hanya_pesan_terakhir_yang_dinilai(self):
        self.siap()
        self.diskusi(("user", "buatkan script python kalkulator"), ("assistant", "ok"), ("user", "makasih, apa itu pip?"))
        self.assertFalse(self.deteksi()[1]["tawar"])

    def test_yang_ditampilkan_dipakai_bukan_isi_lampiran(self):
        self.siap()
        server_chat.tambah_pesan(self.cid, {"role": "user", "content": "halo\n\n<berkas>buatkan program</berkas>",
                                            "tampil": "halo semua apa kabar"})
        self.assertFalse(self.deteksi()[1]["tawar"])

    def test_sudah_diserahkan_tidak_ditawarkan_lagi(self):
        self.siap()
        self.diskusi(("user", "buatkan script python kalkulator"))
        server_chat.tambah_pesan(self.cid, {"role": "assistant", "content": "Diserahkan ke Agent", "agent": {"status": "berjalan"}})
        d = self.deteksi()[1]
        self.assertFalse(d["tawar"])
        self.assertIn("diserahkan", d["alasan"])

    def test_agent_sedang_bekerja_tidak_ditawarkan(self):
        self.siap()
        self.diskusi(("user", "buatkan script python kalkulator"))
        with asisten.AGENT_COND:
            asisten.AGENT["aktif"] = True
        try:
            self.assertFalse(self.deteksi()[1]["tawar"])
        finally:
            with asisten.AGENT_COND:
                asisten.AGENT["aktif"] = False

    def test_obrolan_kosong_dan_id_salah(self):
        self.siap()
        self.assertFalse(self.deteksi()[1]["tawar"])
        self.assertEqual(self.deteksi("../x")[0], 404)
        self.assertEqual(self.deteksi(123)[0], 404)
        self.assertEqual(self.deteksi("20990101-000000-ffff")[0], 404)

    def test_butuh_token(self):
        self.siap()
        self.assertEqual(self.req("POST", "/api/asisten/deteksi", {"id": self.cid}, token=False)[0], 401)


class TestHalamanAsisten(unittest.TestCase):
    def test_rute_memakai_halaman_chat(self):
        from server import server_http
        self.assertEqual(server_http.STATIS["/asisten"][0], "index.html")
        self.assertEqual(server_http.STATIS["/chat"][0], "index.html")

    def test_index_js_punya_mode_asisten(self):
        js = (WEB / "index.js").read_text(encoding="utf-8")
        for pasti in ("MODE_ASISTEN", "'/api/asisten/deteksi'", "serah.tawarkan(d)", "cfgCadangan", "serah.tutupTawaran()"):
            self.assertIn(pasti, js)

    def test_dasbor_kartu_asisten_ke_halaman_asisten(self):
        html = (WEB / "dasbor.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'id="kartuAsisten"[^>]*href="asisten"')
        self.assertLess(html.index('id="kartuAsisten"'), html.index('id="kartuAgent"'))
        self.assertNotIn(">Sesi AI Asisten</span>\n            <span class=\"sesi-ket\">Tanya jawab", html)


if __name__ == "__main__":
    unittest.main()
