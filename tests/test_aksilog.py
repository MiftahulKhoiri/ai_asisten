"""Pengujian src/aksilog.py: rotasi aksi.log dan pemakaiannya oleh agen.catat."""
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402
from src import aksilog  # noqa: E402


class TestAksiLog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.log = self.dir / "aksi.log"

    def tearDown(self):
        self._tmp.cleanup()

    def isi(self, nama):
        return (self.dir / nama).read_text(encoding="utf-8")

    def test_tulis_biasa_menambah_baris(self):
        aksilog.tulis(self.log, "satu\n", maks=1000)
        aksilog.tulis(self.log, "dua\n", maks=1000)
        self.assertEqual(self.isi("aksi.log"), "satu\ndua\n")
        self.assertFalse((self.dir / "aksi.log.1").exists())

    def test_putar_saat_mencapai_batas(self):
        aksilog.tulis(self.log, "x" * 10 + "\n", maks=10)    # file baru, belum diputar
        aksilog.tulis(self.log, "baru\n", maks=10)           # sudah >= batas -> putar
        self.assertEqual(self.isi("aksi.log"), "baru\n")
        self.assertEqual(self.isi("aksi.log.1"), "x" * 10 + "\n")

    def test_salinan_tertua_dibuang(self):
        for i in range(1, 7):
            aksilog.tulis(self.log, f"isi{i}\n" + "x" * 20, maks=10, salinan=3)
        nama = sorted(p.name for p in self.dir.iterdir())
        self.assertEqual(nama, ["aksi.log", "aksi.log.1", "aksi.log.2", "aksi.log.3"])
        self.assertTrue(self.isi("aksi.log").startswith("isi6"))
        self.assertTrue(self.isi("aksi.log.1").startswith("isi5"))
        self.assertTrue(self.isi("aksi.log.3").startswith("isi3"))   # isi1, isi2 sudah hilang

    def test_maks_nol_berarti_tanpa_rotasi(self):
        for _ in range(5):
            aksilog.tulis(self.log, "x" * 100 + "\n", maks=0)
        self.assertEqual(len(self.isi("aksi.log").splitlines()), 5)
        self.assertFalse((self.dir / "aksi.log.1").exists())

    def test_batas_dari_variabel_lingkungan(self):
        with mock.patch.dict(os.environ, {"ASISTEN_LOG_MAKS_KB": "1"}):
            self.assertEqual(aksilog._maks_byte(), 1024)
        with mock.patch.dict(os.environ, {"ASISTEN_LOG_MAKS_KB": "0"}):
            self.assertEqual(aksilog._maks_byte(), 0)
        with mock.patch.dict(os.environ, {"ASISTEN_LOG_MAKS_KB": "bukan-angka"}):
            self.assertEqual(aksilog._maks_byte(), 1024 * 1024)
        with mock.patch.dict(os.environ, {"ASISTEN_LOG_MAKS_KB": "-5"}):
            self.assertEqual(aksilog._maks_byte(), 0)

    def test_gagal_menulis_tidak_melempar(self):
        aksilog.tulis(self.dir / "tidak_ada" / "aksi.log", "x\n", maks=100)   # folder tak ada

    def test_banyak_thread_tidak_error_dan_tidak_melebihi_salinan(self):
        def kerja(n):
            for i in range(100):
                aksilog.tulis(self.log, f"t{n}-{i} " + "y" * 40 + "\n", maks=500, salinan=2)
        ts = [threading.Thread(target=kerja, args=(n,)) for n in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        nama = {p.name for p in self.dir.iterdir()}
        self.assertTrue(nama <= {"aksi.log", "aksi.log.1", "aksi.log.2"}, nama)
        for p in self.dir.iterdir():                  # tidak ada baris yang terpotong
            for baris in p.read_text(encoding="utf-8").splitlines():
                self.assertRegex(baris, r"^t\d-\d+ y{40}$")

    def test_agen_catat_memakai_rotasi(self):
        with mock.patch.object(agen, "LOG_AKSI", self.log), \
                mock.patch.dict(os.environ, {"ASISTEN_LOG_MAKS_KB": "1"}):
            for i in range(40):
                agen.catat("hitung", {"ekspresi": f"{i}+1"}, "hasil " + "z" * 50)
        self.assertTrue((self.dir / "aksi.log.1").exists())
        self.assertLessEqual(self.log.stat().st_size, 1024 + 300)
        baris = self.isi("aksi.log").splitlines()[-1]
        self.assertRegex(baris, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d hitung \{")


if __name__ == "__main__":
    unittest.main()
