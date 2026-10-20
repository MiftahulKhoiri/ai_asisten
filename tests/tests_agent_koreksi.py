"""Pengujian perbaikan Agent: blok tanpa END, penolakan Pemeriksa saat program gagal,
'masalah' berupa teks tunggal, dan perintah uji dengan tanda * (tanpa shell).
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tim  # noqa: E402
from test_tim import (  # noqa: E402
    DasarAgent, LlamaPalsu, StreamPalsu, RENCANA, KODE_BAIK, NILAI_OK,
)

KODE_TANPA_END = "=== FILE: main.py ===\nprint('halo')\n"
KODE_GAGAL = "=== FILE: main.py ===\nimport sys\nprint('x')\nsys.exit(3)\n=== END ===\n"
TOLAK_KOSONG = json.dumps({"ok": False, "ringkas": "salah", "masalah": [],
                           "dilihat": "", "perbaikan": ""})


class TestAlurKoreksi(DasarAgent):
    def test_lupa_end_tanpa_terpotong_tetap_ditulis(self):
        s = StreamPalsu([RENCANA], [KODE_TANPA_END], [NILAI_OK])
        self.pasang(LlamaPalsu("A", "B"), s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertTrue([e for e in ev if e["t"] == "berkas"])

    def test_penolakan_kosong_saat_program_gagal_tidak_diterima(self):
        s = StreamPalsu([RENCANA], [KODE_GAGAL], [TOLAK_KOSONG, TOLAK_KOSONG])
        self.pasang(LlamaPalsu("A", "B"), s)
        ev, _ = self.jalan(self.cfg(maks=1))
        nilai = [e for e in ev if e["t"] == "nilai"][0]
        self.assertFalse(nilai["ok"])
        self.assertTrue(nilai["masalah"])
        self.assertEqual(ev[-1]["status"], "belum")

    def test_penolakan_kosong_saat_program_baik_tetap_diterima(self):
        s = StreamPalsu([RENCANA], [KODE_BAIK], [TOLAK_KOSONG, TOLAK_KOSONG])
        self.pasang(LlamaPalsu("A", "B"), s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")


class TestBentukJawaban(unittest.TestCase):
    def test_masalah_teks_tunggal_tidak_dipecah_per_huruf(self):
        n = tim.rapikan_nilai({"ok": False, "masalah": "main.py:3 - variabel salah dipakai"})
        self.assertEqual(n["masalah"], ["main.py:3 - variabel salah dipakai"])

    def test_perintah_uji_dengan_tanda_kali(self):
        spec = tim.rapikan_spec({"berkas": [{"nama": "main.py"}],
                                 "jalankan": ["python3", "main.py", "6", "7", "*"]}, "t")
        self.assertEqual(spec["jalankan"], ["python3", "main.py", "6", "7", "*"])

    def test_perintah_uji_tetap_menolak_kode_sisipan(self):
        for cmd in (["python3", "-c", "print(1)"], ["python3", "main.py", "a;b"],
                    ["python3", "main.py", "$(id)"]):
            spec = tim.rapikan_spec({"berkas": [{"nama": "main.py"}], "jalankan": cmd}, "t")
            self.assertEqual(spec["jalankan"], [], cmd)


if __name__ == "__main__":
    unittest.main()
