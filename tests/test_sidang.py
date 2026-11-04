"""Pengujian Sidang Pemeriksa: dua model berbeda (Pemeriksa + Penantang) saling memeriksa.

llama-server dan model dipalsukan seperti di test_tim.py. Yang diuji: kapan sidang berlangsung,
siapa dipanggil dengan model apa, bagaimana sidang berakhir (sepakat / tidak sepakat), bahwa
keputusan akhir berpijak pada bukti di kode, dan bahwa tanpa pengaturan `model_k` perilaku lama
tidak berubah.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tim  # noqa: E402
from test_jalur import DIAG_BUG, DIAG_OK, DasarJalur, MAIN_BUG, StreamCatat  # noqa: E402
from test_tim import KODE_BAIK, LlamaPalsu, NILAI_OK, RENCANA, jenis  # noqa: E402
from tim import tim_cek, tim_config, tim_sidang  # noqa: E402


def nilai(ok, ringkas="", masalah=(), dilihat="", perbaikan=""):
    return json.dumps({"ok": ok, "ringkas": ringkas, "masalah": list(masalah), "dilihat": dilihat,
                       "perbaikan": perbaikan})


# KODE_BAIK = "print('halo')" (satu baris di main.py)
TOLAK_KUAT = nilai(False, "pesan salam tidak sesuai kriteria", ["main.py:1 - salam yang dicetak tidak sesuai kriteria"],
                   "print('halo')", "ganti salam sesuai kriteria")
TOLAK_LEMAH = nilai(False, "kurang rapi", ["main.py:1 - penamaan kurang jelas sekali"], "tidak ada di kode manapun",
                    "rapikan nama")
TOLAK_PALSU = nilai(False, "ada bug", ["ghost.py:5 - fungsi hitung menghasilkan total salah"], "total = 1",
                    "perbaiki fungsi hitung")


class StreamSidang(StreamCatat):
    """StreamCatat + antrian jawaban Penantang."""

    def __init__(self, *a, penantang=(), **k):
        super().__init__(*a, **k)
        self.antrian["PENANTANG"] = list(penantang)
        self.sistem = {}       # peran -> prompt sistem yang diterima tiap panggilan

    def __call__(self, model, pesan, *a, **k):
        for p in self.antrian:
            if pesan[0]["content"].startswith("Kamu " + p):
                self.sistem.setdefault(p, []).append(pesan[0]["content"])
        return super().__call__(model, pesan, *a, **k)

    def models(self, peran):
        return [m for p, m in self.panggilan if p == peran]


class DasarSidang(DasarJalur):
    def cfg_sidang(self, ronde=2, tambahan=None, **k):
        return dict(self.cfg(**k), model_k="K", sidang_ronde=ronde, **(tambahan or {}))

    def jalan_sidang(self, stream, ronde=2, maks=3, tambahan=None, **k):
        self.llama = LlamaPalsu("A", "B", "K")
        self.pasang(self.llama, stream)
        return self.proses("buat halo", self.cfg_sidang(ronde, tambahan, maks=maks, **k))

    @staticmethod
    def sidang_ev(ev):
        return [e for e in ev if e["t"] == "sidang"]


# ------------------------------------------------------------------ konfigurasi
class TestKonfigurasi(unittest.TestCase):
    ADA = {"A", "B", "C", "K"}

    def test_bawaan_tanpa_penantang(self):
        cfg, err = tim.siapkan_cfg({"mode": 2, "model_p": "A", "model_e": "B"}, self.ADA)
        self.assertEqual(err, "")
        self.assertIsNone(cfg["model_k"])
        self.assertEqual(cfg["sidang_ronde"], tim_config.SIDANG_RONDE_BAWAAN)

    def test_penantang_dan_batas_ronde(self):
        b = {"mode": 2, "model_p": "A", "model_e": "B", "model_k": "K"}
        self.assertEqual(tim.siapkan_cfg(dict(b, sidang_ronde=99), self.ADA)[0]["sidang_ronde"], 3)
        self.assertEqual(tim.siapkan_cfg(dict(b, sidang_ronde=-4), self.ADA)[0]["sidang_ronde"], 1)
        self.assertEqual(tim.siapkan_cfg(dict(b, sidang_ronde="x"), self.ADA)[0]["sidang_ronde"], 2)
        cfg, err = tim.siapkan_cfg(b, self.ADA)
        self.assertEqual((err, cfg["model_k"]), ("", "K"))

    def test_penantang_pemeriksa_dan_model_tak_dikenal(self):
        b = {"mode": 2, "model_p": "A", "model_e": "B"}
        self.assertIn("tidak dikenal", tim.siapkan_cfg(dict(b, model_k="Z"), self.ADA)[1])
        self.assertIn("berbeda dari Pemeriksa", tim.siapkan_cfg(dict(b, model_k="A"), self.ADA)[1])      # mode 2: Pemeriksa = A
        b3 = {"mode": 3, "model_p": "A", "model_e": "B", "model_c": "C"}
        self.assertIn("berbeda dari Pemeriksa", tim.siapkan_cfg(dict(b3, model_k="C"), self.ADA)[1])
        self.assertEqual(tim.siapkan_cfg(dict(b3, model_k="A"), self.ADA)[1], "")    # boleh sama dengan model lain
        self.assertEqual(tim.siapkan_cfg(dict(b, model_k=""), self.ADA)[0]["model_k"], None)


# ------------------------------------------------------------------ pembuktian di kode
class TestBukti(unittest.TestCase):
    BERKAS = [("main.py", "a = 1\nprint(a / 0)\n"), ("lib/u.py", "x = 2\n")]

    def test_lokasi_masalah(self):
        k = tim_cek.lokasi_masalah
        self.assertEqual(k("main.py:2 - bagi nol", self.BERKAS), "valid")
        self.assertEqual(k("main.py:9 - bagi nol", self.BERKAS), "palsu")          # baris di luar berkas
        self.assertEqual(k("hantu.py:1 - bagi nol", self.BERKAS), "palsu")         # berkas tidak ada
        self.assertEqual(k("u.py:1 - nama tanpa folder", self.BERKAS), "valid")
        self.assertEqual(k("?:? - tanpa lokasi", self.BERKAS), "netral")
        self.assertEqual(k("main.py:? - tanpa baris", self.BERKAS), "netral")
        self.assertEqual(k("tidak berformat", self.BERKAS), "netral")

    def test_kutipan_ada(self):
        k = tim_cek.kutipan_ada
        self.assertTrue(k("print(a / 0)", self.BERKAS))
        self.assertTrue(k("2: print(a/0)", self.BERKAS))                           # awalan nomor baris dibuang
        self.assertTrue(k("PRINT(a/0)", self.BERKAS))
        self.assertTrue(k("a = 1\n2: print(a/0)", self.BERKAS))                    # beberapa baris
        self.assertTrue(k("Traceback ... ZeroDivisionError", self.BERKAS, "Traceback (most recent call last)\nZeroDivisionError"))
        self.assertFalse(k("print(zzz)", self.BERKAS))
        self.assertFalse(k("a = 1\nprint(zzz)", self.BERKAS))                      # satu potongan tidak ada
        self.assertFalse(k("", self.BERKAS))
        self.assertFalse(k("ab", self.BERKAS))                                     # terlalu pendek untuk bukti

    def test_bukti_kuat_butuh_lokasi_dan_kutipan(self):
        k = tim_cek.bukti_kuat
        self.assertTrue(k({"ok": False, "masalah": ["main.py:2 - bagi nol"], "dilihat": "print(a/0)"}, self.BERKAS))
        self.assertFalse(k({"ok": False, "masalah": ["main.py:2 - bagi nol"], "dilihat": "print(b/0)"}, self.BERKAS))
        self.assertFalse(k({"ok": False, "masalah": ["main.py:9 - bagi nol"], "dilihat": "print(a/0)"}, self.BERKAS))
        self.assertFalse(k({"ok": False, "masalah": ["?:? - bagi nol"], "dilihat": "print(a/0)"}, self.BERKAS))
        self.assertFalse(k({"ok": True, "masalah": [], "dilihat": ""}, self.BERKAS))


# ------------------------------------------------------------------ aturan keputusan
class TestPutuskan(unittest.TestCase):
    BERKAS = [("main.py", "a = 1\nprint(a / 0)\n")]
    OK_BUKTI = {"ok": True, "baris": ["OK main.py: sintaks baik"], "keluaran": "halo"}
    GAGAL_BUKTI = {"ok": False, "baris": ["GAGAL uji jalan `python3 main.py` (exit code 1):"], "keluaran": "Traceback"}

    @staticmethod
    def n(ok, masalah=(), dilihat="", perbaikan="", ringkas="r"):
        return {"ok": ok, "masalah": list(masalah), "dilihat": dilihat, "perbaikan": perbaikan, "ringkas": ringkas}

    def test_sepakat_jadi(self):
        n, sepakat, alasan = tim_sidang.putuskan(self.n(True), self.n(True), self.OK_BUKTI, self.BERKAS)
        self.assertEqual((n["ok"], sepakat), (True, True))
        self.assertIn("sepakat", alasan)

    def test_sepakat_tolak_menggabung_masalah_dan_membuang_tuduhan_palsu(self):
        a = self.n(False, ["main.py:2 - bagi dengan nol", "hantu.py:3 - tuduhan karangan belaka"], "print(a/0)", "tangani nol")
        b = self.n(False, ["main.py:2 - Bagi  dengan nol", "main.py:1 - variabel tidak dipakai lagi"], "", "")
        n, sepakat, _ = tim_sidang.putuskan(a, b, self.OK_BUKTI, self.BERKAS)
        self.assertTrue(sepakat)
        self.assertFalse(n["ok"])
        self.assertEqual(n["masalah"], ["main.py:2 - bagi dengan nol", "main.py:1 - variabel tidak dipakai lagi"])
        self.assertEqual((n["dilihat"], n["perbaikan"]), ("print(a/0)", "tangani nol"))

    def test_beda_pendapat_program_gagal_berarti_perbaikan(self):
        n, sepakat, alasan = tim_sidang.putuskan(self.n(True), self.n(False, ["main.py:2 - bagi nol sekali"], "print(a/0)"),
                                                 self.GAGAL_BUKTI, self.BERKAS)
        self.assertEqual((n["ok"], sepakat), (False, False))
        self.assertIn("GAGAL uji jalan", n["masalah"][0])
        self.assertIn("gagal", alasan)

    def test_penolakan_semua_palsu_diterima(self):
        n, sepakat, alasan = tim_sidang.putuskan(self.n(False, ["hantu.py:5 - fungsi hitung total salah"], "total = 1"),
                                                 self.n(True), self.OK_BUKTI, self.BERKAS)
        self.assertEqual((n["ok"], sepakat), (True, False))
        self.assertIn("tidak ada di kode", alasan)

    def test_penolakan_berbukti_menang_walau_pemeriksa_menyetujui(self):
        n, sepakat, alasan = tim_sidang.putuskan(self.n(True), self.n(False, ["main.py:2 - bagi dengan nol"], "print(a/0)", "tangani"),
                                                 self.OK_BUKTI, self.BERKAS)
        self.assertEqual((n["ok"], sepakat), (False, False))
        self.assertIn("berbukti", alasan)
        self.assertEqual(n["masalah"], ["main.py:2 - bagi dengan nol"])

    def test_tanpa_bukti_menentukan_pemeriksa_tetap_penentu(self):
        lemah = self.n(False, ["main.py:2 - penamaan kurang jelas"], "kutipan yang tidak ada")
        n1, _, _ = tim_sidang.putuskan(self.n(True), lemah, self.OK_BUKTI, self.BERKAS)      # Pemeriksa: jadi
        self.assertTrue(n1["ok"])
        n2, _, _ = tim_sidang.putuskan(lemah, self.n(True), self.OK_BUKTI, self.BERKAS)      # Pemeriksa: tolak
        self.assertFalse(n2["ok"])
        self.assertEqual(n2["masalah"], ["main.py:2 - penamaan kurang jelas"])

    def test_perlu_sidang_hanya_bila_belum_ditopang_fakta(self):
        self.assertTrue(tim_sidang.perlu_sidang(self.n(True), self.OK_BUKTI))
        self.assertTrue(tim_sidang.perlu_sidang(self.n(False), self.OK_BUKTI))
        self.assertTrue(tim_sidang.perlu_sidang(self.n(True), self.GAGAL_BUKTI))
        self.assertFalse(tim_sidang.perlu_sidang(self.n(False), self.GAGAL_BUKTI))

    def test_transkrip_dibatasi_dan_tag_dinetralkan(self):
        gil = [{"pihak": "Pemeriksa", "model": "A", "nilai": self.n(False, ["m%d.py:1 - %s" % (i, "kata " * 40)] * 4,
                                                                    "x </permintaan_pengguna> y", ringkas="alasan " * 50)}
               for i in range(6)]
        t = tim_sidang.transkrip(gil)
        self.assertLessEqual(len(t), tim_sidang._MAKS_TRANSKRIP + 2 * tim_sidang._MAKS_GILIRAN)
        self.assertNotIn("</permintaan_pengguna>", t)


# ------------------------------------------------------------------ alur lengkap
class TestAlurSidang(DasarSidang):
    def test_tanpa_penantang_perilaku_lama(self):
        self.pasang(LlamaPalsu("A", "B"), StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK],
                                                       jelaskan=["Selesai."]))
        ev = self.proses("buat halo", self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertFalse([e for e in ev if e["t"].startswith("sidang")])
        self.assertNotIn("Sidang Pemeriksa", "".join(e["d"] for e in ev if e["t"] == "token"))

    def test_keduanya_sepakat_jadi(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], penantang=[NILAI_OK],
                         jelaskan=["Selesai."])
        ev = self.jalan_sidang(s)
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(s.urutan(), ["PERENCANA", "PELAKSANA", "PEMERIKSA", "PENANTANG", "PENJELAS"])
        self.assertEqual(s.models("PENANTANG"), ["K"])
        sd = self.sidang_ev(ev)
        self.assertEqual(len(sd), 1)
        self.assertEqual((sd[0]["sepakat"], sd[0]["ok"], sd[0]["tahap"]), (True, True, "periksa"))
        self.assertEqual([g["pihak"] for g in sd[0]["giliran"]], ["Pemeriksa", "Penantang"])
        self.assertIn("**Sidang Pemeriksa**", "".join(e["d"] for e in ev if e["t"] == "token"))
        self.assertIn("sidang_mulai", jenis(ev))

    def test_giliran_pertama_penantang_mandiri_tanpa_melihat_pemeriksa(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[nilai(True, "RINGKAS-RAHASIA-PEMERIKSA")],
                         penantang=[NILAI_OK], jelaskan=["x"])
        self.jalan_sidang(s)
        u = s.user["PENANTANG"][0]
        self.assertNotIn("RINGKAS-RAHASIA-PEMERIKSA", u)
        self.assertNotIn("PENDAPAT SEBELUMNYA", u)
        self.assertIn("main.py", u)                                              # tetap melihat kode yang sama
        self.assertIn("HASIL KAMU MENJALANKAN PROGRAM", u)                       # dan fakta yang sama

    def test_penantang_menemukan_bug_berbukti_lalu_dikoreksi(self):
        # Pemeriksa menyetujui; Penantang menolak dengan bukti; Pemeriksa tetap menyetujui -> bukti menentukan.
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK, KODE_BAIK],
                         periksa=[NILAI_OK, NILAI_OK, NILAI_OK], penantang=[TOLAK_KUAT, TOLAK_KUAT, NILAI_OK],
                         jelaskan=["x"])
        ev = self.jalan_sidang(s)
        self.assertEqual([e["ok"] for e in ev if e["t"] == "nilai"], [False, True])
        sd = self.sidang_ev(ev)
        self.assertEqual([(x["sepakat"], x["ok"]) for x in sd], [(False, False), (True, True)])
        self.assertIn("berbukti", sd[0]["alasan"])
        self.assertEqual(ev[-1]["status"], "lolos")
        folder = Path(self._tmp.name) / ev[-1]["id"]
        self.assertIn("salam yang dicetak tidak sesuai kriteria", (folder / "koreksi_1.md").read_text(encoding="utf-8"))
        # urutan giliran sidang pertama: P, K, P (menjawab), K
        self.assertEqual(s.urutan()[2:6], ["PEMERIKSA", "PENANTANG", "PEMERIKSA", "PENANTANG"])

    def test_pemeriksa_mengalah_pada_sanggahan_penantang(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK, KODE_BAIK],
                         periksa=[TOLAK_LEMAH, NILAI_OK], penantang=[NILAI_OK], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        self.assertEqual([e["n"] for e in ev if e["t"] == "putaran"], [1])           # tidak perlu putaran koreksi
        self.assertEqual(ev[-1]["status"], "lolos")
        sd = self.sidang_ev(ev)[0]
        self.assertEqual((sd["sepakat"], sd["ok"]), (True, True))
        self.assertEqual(s.urutan().count("PEMERIKSA"), 2)                            # menilai + menjawab
        u = s.user["PEMERIKSA"][1]
        self.assertIn("PENDAPAT SEBELUMNYA DALAM SIDANG", u)
        self.assertIn("GILIRANMU (PEMERIKSA)", u)
        self.assertIn("keputusan: ok=true", u)                                        # melihat pendapat Penantang

    def test_tuduhan_karangan_dibuang_dan_hasil_diterima(self):
        # Pemeriksa menolak dengan masalah di berkas yang tidak ada; Penantang menilai jadi; tidak sepakat sampai akhir.
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK],
                         periksa=[TOLAK_PALSU, TOLAK_PALSU], penantang=[NILAI_OK, NILAI_OK], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        self.assertEqual([e["ok"] for e in ev if e["t"] == "nilai"], [True])
        self.assertEqual(ev[-1]["status"], "lolos")
        sd = self.sidang_ev(ev)[0]
        self.assertEqual((sd["sepakat"], sd["ok"]), (False, True))
        self.assertIn("tidak ada di kode", sd["alasan"])
        self.assertFalse((Path(self._tmp.name) / ev[-1]["id"] / "koreksi_1.md").exists())

    def test_tidak_sepakat_tanpa_bukti_pemeriksa_penentu(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK, NILAI_OK],
                         penantang=[TOLAK_LEMAH, TOLAK_LEMAH], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        sd = self.sidang_ev(ev)[0]
        self.assertEqual((sd["sepakat"], sd["ok"]), (False, True))
        self.assertIn("tetap pada Pemeriksa", sd["alasan"])
        self.assertEqual(ev[-1]["status"], "lolos")

    def test_ronde_satu_tidak_memanggil_pemeriksa_lagi(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], penantang=[TOLAK_LEMAH],
                         jelaskan=["x"])
        ev = self.jalan_sidang(s, ronde=1)
        self.assertEqual(s.urutan().count("PEMERIKSA"), 1)
        self.assertEqual(s.urutan().count("PENANTANG"), 1)
        self.assertEqual(self.sidang_ev(ev)[0]["sepakat"], False)

    def test_ronde_tiga_batas_giliran(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK] * 3,
                         penantang=[TOLAK_LEMAH] * 3, jelaskan=["x"])
        self.jalan_sidang(s, ronde=3)
        self.assertEqual(s.urutan().count("PENANTANG"), 3)
        self.assertEqual(s.urutan().count("PEMERIKSA"), 3)          # 1 menilai + 2 menjawab

    def test_sidang_dilewati_bila_penolakan_sudah_ditopang_fakta(self):
        gagal = "=== FILE: main.py ===\nraise SystemExit(2)\n=== END ===\n"
        s = StreamSidang(rencana=[RENCANA], tulis=[gagal, KODE_BAIK], periksa=[
            nilai(False, "program gagal", ["main.py:1 - program keluar dengan kode 2"], "raise SystemExit(2)", "jangan keluar"),
            NILAI_OK], penantang=[NILAI_OK], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(s.urutan().count("PENANTANG"), 1)           # hanya untuk putaran 2 (program sudah jalan)
        self.assertTrue([e for e in ev if e["t"] == "ringkas" and "Sidang dilewati" in e["d"]])
        self.assertEqual(len(self.sidang_ev(ev)), 1)

    def test_penantang_tanpa_json_keputusan_pemeriksa_dipakai(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], penantang=["ngawur", "ngawur"],
                         jelaskan=["x"])
        ev = self.jalan_sidang(s)
        sd = self.sidang_ev(ev)[0]
        self.assertIsNone(sd["sepakat"])
        self.assertTrue(sd["ok"])
        self.assertIn("tidak memberi penilaian yang terbaca", sd["alasan"])
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertIn("tidak memberi penilaian", "".join(e["d"] for e in ev if e["t"] == "token"))

    def test_penantang_tidak_meniru_cadangan_dari_fakta(self):
        # JSON Pemeriksa tidak terbaca (cadangan dari fakta), JSON Penantang juga: tidak boleh "sepakat" palsu.
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=["ngawur", "ngawur"],
                         penantang=["ngawur", "ngawur"], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        self.assertIsNone(self.sidang_ev(ev)[0]["sepakat"])

    def test_model_dimuat_bergiliran_dan_semua_dibongkar(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], penantang=[NILAI_OK], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        self.assertIn("muat K", self.llama.log)
        self.assertIn("bongkar K", self.llama.log)
        self.assertTrue(all(v == "unloaded" for v in self.llama.state.values()), self.llama.state)
        self.assertFalse(tim.DIMUAT)
        muat = [e["model"] for e in ev if e["t"] == "muat_selesai"]
        self.assertEqual(muat[:3], ["A", "B", "A"])
        self.assertIn("K", muat)

    def test_tanpa_bongkar_tiap_tahap_model_tetap_termuat_sampai_akhir(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK, NILAI_OK],
                         penantang=[TOLAK_LEMAH, NILAI_OK], jelaskan=["x"])
        self.jalan_sidang(s, bongkar=False)
        self.assertEqual(self.llama.log.count("muat K"), 1)
        self.assertEqual(self.llama.log.count("muat A"), 1)
        self.assertTrue(all(v == "unloaded" for v in self.llama.state.values()), self.llama.state)

    def test_event_tahap_penantang_untuk_log_dan_halaman(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK, NILAI_OK],
                         penantang=[TOLAK_LEMAH, NILAI_OK], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        tahap = [e for e in ev if e["t"] == "tahap" and e["tahap"] == "sidang"]
        self.assertEqual([(t["peran"], t["model"]) for t in tahap],
                         [("Penantang · giliran 1", "K"), ("Pemeriksa menjawab · giliran 1", "A"),
                          ("Penantang · giliran 2", "K")])
        gil = [e for e in ev if e["t"] == "sidang_giliran"]
        self.assertEqual([(g["pihak"], g["ok"]) for g in gil], [("Penantang", False), ("Pemeriksa", True), ("Penantang", True)])

    def test_jejak_menyimpan_giliran_sidang(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], penantang=[NILAI_OK], jelaskan=["x"])
        ev = self.jalan_sidang(s)
        nama = [p.name for p in (Path(self._tmp.name) / ev[-1]["id"] / "jejak").iterdir()]
        self.assertTrue([n for n in nama if "sidang-penantang-1" in n], nama)

    def test_prompt_pilihan_pemeriksa_berlaku_juga_saat_menjawab(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[TOLAK_LEMAH, NILAI_OK], penantang=[NILAI_OK],
                         jelaskan=["x"])
        self.jalan_sidang(s, tambahan={"prompt_peran": {"pemeriksa": {"mode": "tambah", "teks": "GAYA-KHUSUS-XYZ",
                                                                      "nama": ["g"]}}})
        self.assertEqual(len(s.sistem["PEMERIKSA"]), 2)                       # menilai + menjawab
        self.assertTrue(all("GAYA-KHUSUS-XYZ" in t for t in s.sistem["PEMERIKSA"]))
        self.assertFalse(any("GAYA-KHUSUS-XYZ" in t for t in s.sistem["PENANTANG"]))


# ------------------------------------------------------------------ tahap Diagnosa
class TestSidangDiagnosa(DasarSidang):
    def cari_bug(self, stream, ronde=2):
        self.llama = LlamaPalsu("A", "B", "K")
        self.pasang(self.llama, stream)
        d = self.bahan({"main.py": MAIN_BUG})
        return self.proses("cari bug", dict(self.cfg(uji=False), model_k="K", sidang_ronde=ronde), d)

    def test_temuan_diperkuat_penantang(self):
        s = StreamSidang(periksa=[DIAG_BUG], penantang=[DIAG_BUG], jelaskan=["Ada pembagian nol."])
        ev = self.cari_bug(s)
        self.assertEqual(ev[-1]["status"], "analisis")
        sd = self.sidang_ev(ev)[0]
        self.assertEqual((sd["tahap"], sd["sepakat"], sd["ok"]), ("diagnosa", True, False))
        diag = [e for e in ev if e["t"] == "diagnosa"][0]
        self.assertFalse(diag["ok"])
        self.assertEqual(diag["sidang"]["tahap"], "diagnosa")
        self.assertIn("KONTEKS DIAGNOSA", s.sistem["PENANTANG"][0])             # Penantang tahu ini diagnosa
        laporan = "".join(e["d"] for e in ev if e["t"] == "token")
        self.assertIn("**Sidang Pemeriksa**", laporan)

    def test_temuan_karangan_dipatahkan_penantang(self):
        palsu = nilai(False, "ada bug", ["gaib.py:3 - pembagian dengan nol di fungsi gaib"], "return a / b", "tangani")
        s = StreamSidang(periksa=[palsu, palsu], penantang=[DIAG_OK, DIAG_OK], jelaskan=["Bersih."])
        ev = self.cari_bug(s)
        diag = [e for e in ev if e["t"] == "diagnosa"][0]
        self.assertTrue(diag["ok"])                         # temuan palsu tidak lolos
        self.assertEqual(diag["masalah"], [])
        self.assertEqual(ev[-1]["status"], "analisis")

    def test_bug_terlewat_ditemukan_penantang(self):
        s = StreamSidang(periksa=[DIAG_OK, DIAG_OK], penantang=[DIAG_BUG, DIAG_BUG], jelaskan=["Ada pembagian nol."])
        ev = self.cari_bug(s)
        diag = [e for e in ev if e["t"] == "diagnosa"][0]
        self.assertFalse(diag["ok"])
        self.assertIn("pembagian dengan nol", diag["masalah"][0])
        self.assertIn("berbukti", self.sidang_ev(ev)[0]["alasan"])

    def test_diagnosa_tersimpan_dan_bisa_dipakai_ulang(self):
        s = StreamSidang(periksa=[DIAG_BUG], penantang=[DIAG_BUG], jelaskan=["x"])
        ev = self.cari_bug(s)
        data = json.loads((Path(self._tmp.name) / ev[-1]["id"] / "diagnosa.json").read_text(encoding="utf-8"))
        self.assertEqual(data["nilai"]["sidang"]["sepakat"], True)
        self.assertIsNotNone(tim.diagnosa_lama(Path(self._tmp.name) / ev[-1]["id"], Path(self._tmp.name) / ev[-1]["id"] / "hasil"))

    def test_tanpa_penantang_diagnosa_tidak_berubah(self):
        self.pasang(LlamaPalsu("A", "B"), StreamSidang(periksa=[DIAG_BUG], jelaskan=["x"]))
        d = self.bahan({"main.py": MAIN_BUG})
        ev = self.proses("cari bug", self.cfg(uji=False), d)
        self.assertFalse(self.sidang_ev(ev))
        self.assertNotIn("sidang", [e for e in ev if e["t"] == "diagnosa"][0])


# ------------------------------------------------------------------ halaman Agent (agent.js dengan DOM tiruan)
class TestHalamanSidang(DasarSidang):
    """web/agent.js memutar event nyata sidang (dilewati bila node tidak terpasang)."""

    def smoke(self, ev, mode=""):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        berkas = Path(self._tmp.name) / "ev.ndjson"
        berkas.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in ev) + "\n", encoding="utf-8")
        skrip = Path(__file__).resolve().parent / "agent_smoke.js"
        r = subprocess.run([node, str(skrip), str(berkas)] + ([mode] if mode else []), capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_sidang_tampil_sebagai_kartu_dan_log_tanpa_mengubah_alur(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK, NILAI_OK],
                         penantang=[TOLAK_LEMAH, NILAI_OK], jelaskan=["Selesai."])
        ev = self.jalan_sidang(s)
        h = self.smoke(ev, "sidang")
        self.assertEqual(h["galat"], [], h["err"])
        self.assertEqual([a["id"] for a in h["alur"]], ["st_rencana", "st_tulis", "st_periksa", "st_jelaskan"])
        self.assertTrue(all("selesai" in a["kelas"] for a in h["alur"]), h["alur"])          # sidang tidak merusak stepper
        self.assertEqual(len(h["kartu_sidang"]), 1, h["kartu_sidang"])
        self.assertIn("Sidang: sepakat", h["kartu_sidang"][0])
        self.assertIn("Putusan: jadi", h["kartu_sidang"][0])
        self.assertIn("Penantang", h["kartu_sidang"][0])
        log = "\n".join(h["teks_log"])
        self.assertIn("Sidang Pemeriksa dimulai", log)
        self.assertIn("Penantang · giliran 1", log)
        self.assertIn("Sidang sepakat", log)
        self.assertTrue(h["lencana_selesai"])
        self.assertTrue(any("Penantang" in m for m in h["model"]), h["model"])               # K tampil di daftar model panel log
        self.assertEqual(h["body"]["model_k"], "K")
        self.assertEqual(h["body"]["sidang_ronde"], 3)
        self.assertEqual(h["body"]["model_c"], "A")

    def test_tidak_sepakat_dan_diagnosa_tampil(self):
        s = StreamSidang(periksa=[DIAG_OK, DIAG_OK], penantang=[DIAG_BUG, DIAG_BUG], jelaskan=["Ada pembagian nol."])
        self.llama = LlamaPalsu("A", "B", "K")
        self.pasang(self.llama, s)
        d = self.bahan({"main.py": MAIN_BUG})
        ev = self.proses("cari bug", dict(self.cfg(uji=False), model_k="K", sidang_ronde=2), d)
        h = self.smoke(ev, "sidang")
        self.assertEqual(h["galat"], [], h["err"])
        self.assertIn("Sidang: tidak sepakat", h["kartu_sidang"][0])
        self.assertEqual(h["kartu_diag"], 1)
        self.assertEqual([a["id"] for a in h["alur"]], ["st_diagnosa", "st_jelaskan"])

    def test_pengaturan_penantang_di_halaman_setup(self):
        s = StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], jelaskan=["x"])
        self.pasang(LlamaPalsu("A", "B"), s)
        ev = self.proses("buat halo", self.cfg())
        h = self.smoke(ev)                                           # tanpa penantang tersimpan
        self.assertEqual(h["galat"], [], h["err"])
        self.assertEqual(h["pilihan_k"][0]["v"], "")                 # pilihan "tanpa Penantang" ada di paling atas
        self.assertTrue(h["ronde_tersembunyi"])                      # giliran sidang disembunyikan bila tidak ada Penantang
        self.assertIsNone(h["body"]["model_k"])
        self.assertEqual(h["kartu_sidang"], [])
        h2 = self.smoke(ev, "sidang")
        self.assertFalse(h2["ronde_tersembunyi"])
        self.assertEqual(h2["ronde_nilai"], "3")
        self.assertEqual(h2["body"]["model_k"], "K")

    def test_html_memiliki_elemen_penantang(self):
        web = Path(__file__).resolve().parent.parent / "web"
        html = (web / "agent.html").read_text(encoding="utf-8")
        for pasti in ('id="selK"', 'id="ketK"', 'id="selRonde"', 'id="barisRonde"', 'id="fieldK"'):
            self.assertIn(pasti, html)

    def test_serahkan_membawa_penantang(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        skrip = (
            "global.window={localStorage:{getItem:()=>JSON.stringify({mode:2,p:'A',e:'B',k:'K',ronde:7,izinUji:false})}};"
            "global.document={};require(process.argv[1]);"
            "const c=window.Serahkan.bacaCfg();console.log(JSON.stringify(c));"
            "const d=window.Serahkan.bacaCfg({getItem:()=>JSON.stringify({mode:2,p:'A',e:'B',k:'A'})});console.log(JSON.stringify(d));")
        r = subprocess.run([node, "-e", skrip, str(Path(__file__).resolve().parent.parent / "web" / "serahkan.js")],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        a, b = [json.loads(x) for x in r.stdout.strip().splitlines()[-2:]]
        self.assertEqual((a["model_k"], a["sidang_ronde"]), ("K", 3))      # ronde dibatasi 1-3
        self.assertIsNone(b["model_k"])                                    # Penantang = Pemeriksa diabaikan


# ------------------------------------------------------------------ lewat HTTP (pengaturan dari halaman ke server)
class TestSidangLewatHttp(DasarSidang):
    TOKEN = "token-uji-sidang"

    def setUp(self):
        super().setUp()
        import threading
        import urllib.error
        import urllib.request
        from http.server import ThreadingHTTPServer
        from unittest import mock
        import asisten
        self.asisten, self.urllib = asisten, (urllib.request, urllib.error)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), asisten.H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        for obj, nama, nilai_ in ((asisten, "TOKEN", self.TOKEN),
                                  (asisten, "daftar_model", lambda: [{"id": n, "mb": 1000, "llama": None} for n in "ABK"])):
            p = mock.patch.object(obj, nama, nilai_)
            p.start()
            self.addCleanup(p.stop)
        with asisten.S_LOCK:
            self._s = dict(asisten.S)
            asisten.S.update(model=None, target=None, status="kosong")
        self.addCleanup(lambda: asisten.S.update(self._s))

    def req(self, metode, path, body=None):
        rq, er = self.urllib
        r = rq.Request("http://127.0.0.1:%d%s" % (self.port, path), method=metode,
                       data=json.dumps(body).encode() if body is not None else None)
        r.add_header("Authorization", "Bearer " + self.TOKEN)
        r.add_header("Content-Type", "application/json")
        try:
            with rq.urlopen(r, timeout=20) as resp:
                return resp.status, json.loads(resp.read())
        except er.HTTPError as e:
            return e.code, json.loads(e.read())

    DASAR = {"teks": "buat halo", "mode": 2, "model_p": "A", "model_e": "B", "maks": 2, "uji": False}

    def test_penantang_lewat_http_menghasilkan_sidang(self):
        self.pasang(LlamaPalsu("A", "B", "K"), StreamSidang(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK],
                                                            penantang=[NILAI_OK], jelaskan=["x"]))
        kode, d = self.req("POST", "/api/agent/jalankan", dict(self.DASAR, model_k="K", sidang_ronde=2))
        self.assertEqual(kode, 200, d)
        ev, nomor = [], 0
        for _ in range(100):
            kode, p = self.req("GET", "/api/agent/event?sesi=%s&dari=%d&tunggu=5" % (d["sesi"], nomor))
            ev += p["events"]
            nomor = p["next"]
            if p["habis"]:
                break
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(len(self.sidang_ev(ev)), 1)
        self.assertEqual(ev[0]["model"]["penantang"], "K")           # tercatat sebagai model proses

    def test_penantang_ditolak_bila_sama_dengan_pemeriksa_atau_tak_dikenal(self):
        kode, d = self.req("POST", "/api/agent/jalankan", dict(self.DASAR, model_k="A"))
        self.assertEqual(kode, 400)
        self.assertIn("berbeda dari Pemeriksa", d["error"])
        kode, d = self.req("POST", "/api/agent/jalankan", dict(self.DASAR, model_k="Z"))
        self.assertEqual(kode, 400)
        self.assertIn("tidak dikenal", d["error"])


class TestKontrakPrompt(unittest.TestCase):
    def test_penantang_dikenali_dan_meminta_json_yang_sama_dengan_pemeriksa(self):
        self.assertTrue(tim_sidang.SYSTEM_PENANTANG.startswith("Kamu PENANTANG"))
        for kunci in ('"ok"', '"ringkas"', '"masalah"', '"dilihat"', '"perbaikan"'):
            self.assertIn(kunci, tim_sidang.SYSTEM_PENANTANG)
            self.assertIn(kunci, tim.SYSTEM_PEMERIKSA)
        self.assertNotIn("KONTEKS DIAGNOSA", tim_sidang.sistem_penantang("periksa"))
        self.assertIn("KONTEKS DIAGNOSA", tim_sidang.sistem_penantang("diagnosa"))

    def test_tugas_giliran_berbeda_per_pihak(self):
        gil = [{"pihak": "Pemeriksa", "model": "A", "nilai": {"ok": True, "masalah": [], "dilihat": "", "ringkas": "baik"}}]
        p = tim_sidang.prompt_giliran("BAHAN", gil, "Penantang")
        self.assertTrue(p.startswith("BAHAN"))
        self.assertIn("GILIRANMU (PENANTANG)", p)
        self.assertIn("[Pemeriksa]", p)
        self.assertIn("GILIRANMU (PEMERIKSA)", tim_sidang.prompt_giliran("BAHAN", gil, "Pemeriksa"))


if __name__ == "__main__":
    unittest.main()
