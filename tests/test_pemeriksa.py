"""Tes penguatan Pemeriksa: verifikasi kutipan, Pemeriksa kedua + sanggahan, deteksi macet,
penanda keputusan lemah, dan peringatan di laporan akhir."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tim  # noqa: E402
from test_tim import (DasarAgent, KODE_BAIK, KODE_BAIK2, KODE_RUSAK, LlamaPalsu, NILAI_OK,  # noqa: E402
                      NILAI_TOLAK, RENCANA, StreamPalsu, jenis)
from tim import tim_cek, tim_tahap  # noqa: E402

BERKAS = [("main.py", "def jumlah(a, b):\n    return a - b\n\nprint(jumlah(2, 3))\n")]


def tolak(masalah="main.py:2 - operator minus seharusnya plus", dilihat="return a - b",
          perbaikan="ganti minus jadi plus"):
    return json.dumps({"ok": False, "ringkas": "salah operator", "masalah": [masalah],
                       "dilihat": dilihat, "perbaikan": perbaikan})


def teks_laporan(ev):
    return "".join(e["d"] for e in ev if e["t"] == "token")


class TestVerifikasiKutipan(unittest.TestCase):
    def test_kutipan_ada_dan_tidak_ada(self):
        k = tim_cek.kutipan_ditemukan
        self.assertTrue(k("return a - b", BERKAS))
        self.assertTrue(k("RETURN  a -   b", BERKAS))                 # spasi dan huruf besar diabaikan
        self.assertTrue(k("2:     return a - b", BERKAS))             # awalan nomor baris dibuang
        self.assertTrue(k("main.py:2 - return a - b", BERKAS))
        self.assertTrue(k("1: def jumlah(a, b): 2: return a - b", BERKAS))
        self.assertTrue(k("def jumlah(a, b): ... print(jumlah(2, 3))", BERKAS))
        self.assertFalse(k("return a + b", BERKAS))
        self.assertFalse(k("def jumlah(a, b): ... return a * b", BERKAS))   # semua potongan harus ada

    def test_kutipan_kosong_atau_terlalu_pendek_tidak_dinilai(self):
        self.assertIsNone(tim_cek.kutipan_ditemukan("", BERKAS))
        self.assertIsNone(tim_cek.kutipan_ditemukan("ab", BERKAS))

    def test_kutipan_dari_keluaran_program(self):
        self.assertTrue(tim_cek.kutipan_ditemukan("ZeroDivisionError: division by zero", BERKAS,
                                                  ["Traceback...\nZeroDivisionError: division by zero"]))

    def test_masalah_menyebut_berkas_yang_tidak_ada(self):
        m = ["main.py:2 - salah", "util.py:3 - tidak ada berkas ini", "src/x.py:1 - juga tidak ada"]
        self.assertEqual(tim_cek.masalah_tanpa_berkas(m, ["main.py", "src/lib.py"]), m[1:])
        self.assertEqual(tim_cek.masalah_tanpa_berkas(["?:? - x", "tanpa berkas"], ["main.py"]), [])

    def test_periksa_dasar(self):
        ok = {"ok": False, "masalah": ["main.py:2 - operator salah"], "dilihat": "return a - b"}
        self.assertTrue(tim_cek.periksa_dasar(ok, BERKAS))
        self.assertFalse(tim_cek.periksa_dasar(dict(ok, dilihat="return a * b"), BERKAS))
        self.assertFalse(tim_cek.periksa_dasar(dict(ok, masalah=["lain.py:1 - ngarang"]), BERKAS))
        self.assertIsNone(tim_cek.periksa_dasar(dict(ok, dilihat=""), BERKAS))
        self.assertIsNone(tim_cek.periksa_dasar({"ok": True}, BERKAS))      # penerimaan tidak diverifikasi

    def test_kemiripan_masalah(self):
        a = "main.py:2 - operator minus salah seharusnya plus"
        self.assertTrue(tim_cek.mirip(a, "main.py:2 - operator minus salah, gunakan plus"))
        self.assertFalse(tim_cek.mirip(a, "util.py:9 - variabel tidak didefinisikan"))
        self.assertEqual(len(tim_cek.gabung_masalah([a], ["main.py:2 - operator minus salah gunakan plus",
                                                          "util.py:9 - variabel tidak didefinisikan"])), 2)
        self.assertTrue(tim_cek.masalah_berulang([a], ["main.py:2 - operator minus salah, gunakan plus"]))
        self.assertFalse(tim_cek.masalah_berulang([a], []))


class TestKutipanDiAlur(DasarAgent):
    def test_kutipan_tak_ada_ditanya_ulang_sekali_lalu_penolakan_tetap_dengan_catatan(self):
        llama = LlamaPalsu("A", "B")
        ngarang = tolak(dilihat="return a * b * c")           # tidak ada di kode
        s = StreamPalsu([RENCANA], [KODE_BAIK, KODE_BAIK2], [ngarang, ngarang, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual([p for p, _ in s.panggilan].count("PEMERIKSA"), 3)    # jawab + tanya ulang + putaran 2
        nilai = [e for e in ev if e["t"] == "nilai"]
        self.assertEqual([n["ok"] for n in nilai], [False, True])
        self.assertIs(nilai[0]["kutipan"], False)
        folder = Path(self._tmp.name) / ev[-1]["id"]
        koreksi = (folder / "koreksi_1.md").read_text(encoding="utf-8")
        self.assertIn("operator minus", koreksi)                # penolakan tetap dikirim (hak Pemeriksa)
        self.assertIn("CATATAN SISTEM", koreksi)                # ... tetapi Pelaksana diberi tahu
        self.assertIn("TIDAK ditemukan", koreksi)

    def test_kutipan_yang_ada_tidak_ditanya_ulang(self):
        llama = LlamaPalsu("A", "B")
        kode = "=== FILE: main.py ===\ndef jumlah(a, b):\n    return a - b\nprint(jumlah(2, 3))\n=== END ===\n"
        s = StreamPalsu([RENCANA], [kode, KODE_BAIK], [tolak(), NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual([p for p, _ in s.panggilan].count("PEMERIKSA"), 2)
        self.assertIs([e for e in ev if e["t"] == "nilai"][0]["kutipan"], True)
        folder = Path(self._tmp.name) / ev[-1]["id"]
        self.assertNotIn("CATATAN SISTEM", (folder / "koreksi_1.md").read_text(encoding="utf-8"))

    def test_pemeriksa_mencabut_temuan_yang_tak_terbukti_diterima_dengan_tanda_lemah(self):
        llama = LlamaPalsu("A", "B")
        ngarang = tolak(dilihat="return a * b * c")
        s = StreamPalsu([RENCANA], [KODE_BAIK], [ngarang, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")
        nilai = [e for e in ev if e["t"] == "nilai"][0]
        self.assertTrue(nilai["ok"])
        self.assertIn("mencabut", nilai["lemah"])
        self.assertIn("Keputusan lemah", teks_laporan(ev))


class TestMacet(DasarAgent):
    def test_kode_sama_persis_tidak_diperiksa_ulang_dan_proses_dihentikan(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_RUSAK, KODE_RUSAK, KODE_RUSAK], [NILAI_TOLAK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(maks=5))
        self.assertEqual(ev[-1]["status"], "belum")
        self.assertEqual([p for p, _ in s.panggilan].count("PEMERIKSA"), 1)    # kode sama: tidak dinilai lagi
        self.assertEqual([p for p, _ in s.panggilan].count("PELAKSANA"), 3)
        self.assertEqual([e["n"] for e in ev if e["t"] == "putaran"], [1, 2, 3])   # berhenti di putaran 3 dari 5
        self.assertIn("Berhenti lebih awal", teks_laporan(ev))
        self.assertEqual(set(llama.state.values()), {"unloaded"})
        folder = Path(self._tmp.name) / ev[-1]["id"]
        self.assertTrue((folder / "koreksi_1.md").is_file())

    def test_peringatan_ganti_pendekatan_diteruskan_ke_pelaksana(self):
        llama = LlamaPalsu("A", "B")
        isi = []
        s = StreamPalsu([RENCANA], [KODE_RUSAK, KODE_RUSAK, KODE_BAIK2], [NILAI_TOLAK, NILAI_OK])
        asli = s.__call__

        def rekam(model, pesan, batal, token, suhu=0.2, json_mode=False):
            isi.append(pesan[1]["content"])
            return asli(model, pesan, batal, token, suhu, json_mode)
        self.pasang(llama, rekam)
        ev, _ = self.jalan(self.cfg(maks=4))
        self.assertEqual(ev[-1]["status"], "lolos")
        pelaksana = [t for t in isi if "LEMBAR TUGAS" in t and "BERKAS (dengan" not in t]
        self.assertIn("PERINGATAN SISTEM", pelaksana[2])

    def test_masalah_yang_sama_berulang_dihentikan_lebih_awal(self):
        llama = LlamaPalsu("A", "B")
        kode = lambda n: "=== FILE: main.py ===\nprint('v%d')\n=== END ===\n" % n  # noqa: E731
        s = StreamPalsu([RENCANA], [kode(1), kode(2), kode(3), kode(4), kode(5)],
                        [NILAI_TOLAK] * 5)
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(maks=5))
        self.assertEqual(ev[-1]["status"], "belum")
        self.assertEqual([e["n"] for e in ev if e["t"] == "putaran"], [1, 2, 3])
        self.assertIn("masalah yang sama muncul terus", teks_laporan(ev))

    def test_masalah_berbeda_tidak_dianggap_macet(self):
        llama = LlamaPalsu("A", "B")
        t1 = json.dumps({"ok": False, "ringkas": "x", "masalah": ["main.py:1 - fungsi pertama bermasalah besar"],
                         "dilihat": "", "perbaikan": "p1"})
        t2 = json.dumps({"ok": False, "ringkas": "y", "masalah": ["main.py:1 - variabel kedua tidak terdefinisi"],
                         "dilihat": "", "perbaikan": "p2"})
        t3 = json.dumps({"ok": False, "ringkas": "z", "masalah": ["main.py:1 - impor ketiga hilang total"],
                         "dilihat": "", "perbaikan": "p3"})
        kode = lambda n: "=== FILE: main.py ===\nprint('v%d')\n=== END ===\n" % n  # noqa: E731
        s = StreamPalsu([RENCANA], [kode(1), kode(2), kode(3), kode(4)], [t1, t2, t3, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(maks=4))
        self.assertEqual(ev[-1]["status"], "lolos")


class TestPemeriksaKedua(DasarAgent):
    def cfg2(self, c2="D", **kw):
        cfg = self.cfg(mode=3, c="C", **kw)
        cfg["model_c2"] = c2
        return cfg

    def test_keduanya_menerima(self):
        llama = LlamaPalsu("A", "B", "C", "D")
        s = StreamPalsu([RENCANA], [KODE_BAIK], [NILAI_OK, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg2())
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual([m for p, m in s.panggilan if p == "PEMERIKSA"], ["C", "D"])
        nilai = [e for e in ev if e["t"] == "nilai"][0]
        self.assertEqual([p["model"] for p in nilai["pendapat"]], ["C", "D"])
        self.assertIn("Dua Pemeriksa sepakat", nilai["ringkas"])
        self.assertEqual(set(llama.state.values()), {"unloaded"})
        self.assertEqual(tim.baca_run(ev[-1]["id"])["model"]["pemeriksa2"], "D")

    def test_keduanya_menolak_masalah_digabung(self):
        llama = LlamaPalsu("A", "B", "C", "D")
        t1 = tolak("main.py:1 - operator minus salah seharusnya plus", dilihat="")
        t2 = tolak("main.py:1 - nama variabel tidak jelas dan membingungkan", dilihat="",
                   perbaikan="ganti nama")
        s = StreamPalsu([RENCANA], [KODE_BAIK, KODE_BAIK2], [t1, t2, NILAI_OK, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg2())
        nilai = [e for e in ev if e["t"] == "nilai"]
        self.assertFalse(nilai[0]["ok"])
        self.assertEqual(len(nilai[0]["masalah"]), 2)
        folder = Path(self._tmp.name) / ev[-1]["id"]
        koreksi = (folder / "koreksi_1.md").read_text(encoding="utf-8")
        self.assertIn("operator minus", koreksi)
        self.assertIn("nama variabel", koreksi)

    def test_berbeda_pendapat_penerima_berbalik_jadi_ditolak(self):
        llama = LlamaPalsu("A", "B", "C", "D")
        # C menolak, D menerima; D disanggah (memeriksa temuan C) lalu membenarkan temuan itu
        s = StreamPalsu([RENCANA], [KODE_BAIK, KODE_BAIK2],
                        [tolak("main.py:1 - operator minus salah seharusnya plus", dilihat=""),
                         NILAI_OK,
                         tolak("main.py:1 - benar, operator minus salah", dilihat="", perbaikan="plus"),
                         NILAI_OK, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg2())
        self.assertEqual([m for p, m in s.panggilan if p == "PEMERIKSA"][:3], ["C", "D", "D"])
        nilai = [e for e in ev if e["t"] == "nilai"][0]
        self.assertFalse(nilai["ok"])
        self.assertIn("membenarkan temuan", nilai["ringkas"])
        self.assertEqual([p.get("sanggahan", False) for p in nilai["pendapat"]], [False, False, True])
        self.assertTrue(any("berbeda pendapat" in e["d"] for e in ev if e["t"] == "ringkas"))

    def test_berbeda_pendapat_penerima_bertahan_diterima_lemah_dengan_sengketa(self):
        llama = LlamaPalsu("A", "B", "C", "D")
        # D menolak, C menerima; C disanggah lalu tetap menerima -> C harus dimuat ulang untuk sanggahan
        s = StreamPalsu([RENCANA], [KODE_BAIK],
                        [NILAI_OK, tolak("main.py:1 - operator minus salah seharusnya plus", dilihat=""),
                         NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg2())
        self.assertEqual([m for p, m in s.panggilan if p == "PEMERIKSA"], ["C", "D", "C"])
        self.assertEqual(ev[-1]["status"], "lolos")
        nilai = [e for e in ev if e["t"] == "nilai"][0]
        self.assertTrue(nilai["ok"])
        self.assertIn("berbeda pendapat", nilai["lemah"])
        self.assertEqual(len(nilai["sengketa"]), 1)
        laporan = teks_laporan(ev)
        self.assertIn("Temuan yang disanggah", laporan)
        self.assertIn("operator minus", laporan)
        self.assertIn("Keputusan lemah", laporan)
        self.assertEqual(set(llama.state.values()), {"unloaded"})

    def test_fakta_kegagalan_mengalahkan_penerima(self):
        # sintaks rusak (fakta sistem) -> penolakan dipertahankan walau penerima bertahan
        llama = LlamaPalsu("A", "B", "C", "D")
        s = StreamPalsu([RENCANA], [KODE_RUSAK, KODE_BAIK2],
                        [NILAI_TOLAK, NILAI_OK, NILAI_OK, NILAI_OK, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg2())
        nilai = [e for e in ev if e["t"] == "nilai"]
        self.assertFalse(nilai[0]["ok"])
        self.assertIn("kegagalan", nilai[0]["ringkas"])

    def test_pemeriksa_kedua_sama_dengan_pertama_diabaikan(self):
        cfg, err = tim.siapkan_cfg({"model_p": "A", "model_e": "B", "model_c": "C", "mode": 3,
                                    "model_c2": "C"}, {"A", "B", "C"})
        self.assertEqual(err, "")
        self.assertIsNone(cfg["model_c2"])

    def test_pemeriksa_kedua_divalidasi(self):
        cfg, err = tim.siapkan_cfg({"model_p": "A", "model_e": "B", "model_c": "C", "mode": 3,
                                    "model_c2": "D"}, {"A", "B", "C", "D"})
        self.assertEqual((cfg["model_c2"], err), ("D", ""))
        cfg, err = tim.siapkan_cfg({"model_p": "A", "model_e": "B", "model_c": "C", "mode": 3,
                                    "model_c2": "Z"}, {"A", "B", "C"})
        self.assertIsNone(cfg)
        self.assertIn("Model tidak dikenal", err)
        cfg, err = tim.siapkan_cfg({"model_p": "A", "model_e": "B"}, {"A", "B"})
        self.assertIsNone(cfg["model_c2"])


class TestPutusanDua(unittest.TestCase):
    """_putuskan_dua adalah fungsi murni: aturannya diuji langsung, tanpa model."""
    OK = {"ok": True, "masalah": [], "dilihat": "", "perbaikan": "", "ringkas": "baik"}
    NO = {"ok": False, "masalah": ["main.py:2 - operator minus salah seharusnya plus"], "dilihat": "return a - b",
          "perbaikan": "plus", "ringkas": "salah", "kutipan": True}
    BAIK = {"ok": True, "baris": ["OK main.py: sintaks baik"]}
    GAGAL = {"ok": False, "baris": ["GAGAL main.py: sintaks Python salah di baris 1"]}

    def test_tabel_keputusan(self):
        f = tim_tahap._putuskan_dua
        self.assertTrue(f(self.OK, "C", self.OK, "D", None, None, self.BAIK)["ok"])
        self.assertFalse(f(self.NO, "C", self.NO, "D", None, None, self.BAIK)["ok"])
        # berbeda, penerima bertahan: diterima lemah bila program baik
        n = f(self.NO, "C", self.OK, "D", self.OK, "D", self.BAIK)
        self.assertTrue(n["ok"])
        self.assertTrue(n["lemah"])
        self.assertEqual(n["sengketa"], self.NO["masalah"])
        # ... tetapi ditolak bila program gagal
        n = f(self.NO, "C", self.OK, "D", self.OK, "D", self.GAGAL)
        self.assertFalse(n["ok"])
        self.assertEqual(n["masalah"], self.NO["masalah"])
        # penerima berbalik
        self.assertFalse(f(self.NO, "C", self.OK, "D", self.NO, "D", self.BAIK)["ok"])
        # pendapat tercatat lengkap
        n = f(self.NO, "C", self.OK, "D", self.OK, "D", self.BAIK)
        self.assertEqual([(p["model"], p["ok"], p.get("sanggahan", False)) for p in n["pendapat"]],
                         [("C", False, False), ("D", True, False), ("D", True, True)])


class TestLaporan(DasarAgent):
    def test_peringatan_bila_program_tidak_pernah_dijalankan(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_BAIK], [NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(uji=False))
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertIn("belum pernah dijalankan", teks_laporan(ev))

    def test_tanpa_peringatan_bila_program_dijalankan(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_BAIK], [NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(uji=True))
        self.assertNotIn("belum pernah dijalankan", teks_laporan(ev))
        self.assertNotIn("Keputusan lemah", teks_laporan(ev))

    def test_keputusan_cadangan_ditandai_lemah(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_BAIK], ["bukan json", "tetap bukan json"])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertIn("Keputusan lemah", teks_laporan(ev))
        self.assertIn("nilai", jenis(ev))



class TestTampilan(unittest.TestCase):
    """Pilihan Pemeriksa kedua terpasang di halaman Agent dan ikut dikirim ke server."""
    WEB = Path(__file__).resolve().parent.parent / "web"

    def test_pilihan_ada_di_halaman_dan_dikirim(self):
        html = (self.WEB / "agent.html").read_text(encoding="utf-8")
        js = (self.WEB / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="selC2"', html)
        self.assertIn("model_c2: cfg.c2 || ''", js)
        self.assertIn("selC2", js)
        self.assertIn("model_c2", (self.WEB / "serahkan.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
