"""Pengujian alur adaptif Agent: pemilihan jalur, tahap Diagnosa, jalur cari_bug dan perbaiki,
pemakaian ulang diagnosa, dan jalan pintas saat tidak ada bug."""
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tim  # noqa: E402
from test_tim import (CtxPalsu, DasarAgent, KODE_BAIK, LlamaPalsu, NILAI_OK, RENCANA,  # noqa: E402
                      StreamPalsu, jenis)
from test_unggah import DasarServer  # noqa: E402
import asisten  # noqa: E402
from tim import tim_cek, tim_config, tim_jalur, tim_prompt  # noqa: E402

DIAG_BUG = json.dumps({"ok": False, "ringkas": "pembagian nol tidak ditangani",
                       "masalah": ["main.py:3 - pembagian dengan nol menimbulkan ZeroDivisionError"],
                       "dilihat": "return a / b", "perbaikan": "tangani b == 0 sebelum membagi"})
DIAG_OK = json.dumps({"ok": True, "ringkas": "kode tampak benar", "masalah": [], "dilihat": "",
                      "perbaikan": ""})
MAIN_BUG = "def bagi(a, b):\n    # membagi dua angka\n    return a / b\n\nprint(bagi(4, 2))\n"
RENCANA_FIX = json.dumps({
    "judul": "Perbaiki bagi", "ringkasan": "Tangani pembagian nol", "bahasa": "python",
    "berkas": [{"nama": "main.py", "fungsi": "tangani b == 0"}], "langkah": ["periksa b"],
    "kriteria": ["tidak ada ZeroDivisionError"], "jalankan": ["python3", "main.py"],
    "harapan": ["halo"], "catatan": ""})


class StreamCatat(StreamPalsu):
    """StreamPalsu yang juga menyimpan isi prompt user tiap peran."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.user = {}

    def __call__(self, model, pesan, batal, token, suhu=0.2, json_mode=False):
        for p in self.antrian:
            if pesan[0]["content"].startswith("Kamu " + p):
                self.user.setdefault(p, []).append(pesan[1]["content"])
        return super().__call__(model, pesan, batal, token, suhu, json_mode)

    def urutan(self):
        return [p for p, _ in self.panggilan]


class DasarJalur(DasarAgent):
    def bahan(self, isi, nama="bahan"):
        d = Path(self._tmp.name) / nama
        for rel, teks in isi.items():
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(teks, encoding="utf-8")
        return d

    def proses(self, tugas, cfg, bahan=None, lanjut=None):
        ctx = CtxPalsu()
        return list(tim.jalankan(tugas, cfg, ctx, lanjut, bahan))

    def folder(self, ev):
        return Path(self._tmp.name) / [e for e in ev if e["t"] == "mulai"][0]["id"]

    def isi_hasil(self, ev):
        h = self.folder(ev) / "hasil"
        return {str(p.relative_to(h)): p.read_text() for p in sorted(h.rglob("*")) if p.is_file()}


# ------------------------------------------------------------------ pemilihan jalur
class TestPilihJalur(unittest.TestCase):
    KASUS = [
        ("Perbaiki bug pembagian nol di kalkulator", "perbaiki"),
        ("cari bug di kode ini", "cari_bug"),
        ("carikan masalah di proyek ini", "cari_bug"),
        ("review kode ini, apa saja kesalahannya", "cari_bug"),
        ("apa yang salah dengan kode ini", "cari_bug"),
        ("kenapa programnya error?", "cari_bug"),
        ("tolong audit keamanan kode ini cari celah", "cari_bug"),
        ("cari dan perbaiki bug", "perbaiki"),
        ("fix typo di README", "perbaiki"),
        ("programnya error saat input kosong", "perbaiki"),
        ("keluarannya salah untuk angka negatif", "perbaiki"),
        ("tambahkan fitur error handling", "buat"),
        ("tambahkan fungsi baru", "buat"),
        ("ubah warna tombol jadi biru", "buat"),
        ("kenapa tidak buat test baru?", "buat"),
        ("jelaskan cara kerja", "buat"),
    ]

    def test_otomatis_dengan_berkas(self):
        for tugas, harapan in self.KASUS:
            self.assertEqual(tim_jalur.pilih_jalur(tugas, "otomatis", True)[0], harapan, tugas)

    def test_tanpa_berkas_selalu_buat(self):
        for tugas, _ in self.KASUS:
            self.assertEqual(tim_jalur.pilih_jalur(tugas, "otomatis", False)[0], "buat", tugas)

    def test_pilihan_pengguna_menang(self):
        self.assertEqual(tim_jalur.pilih_jalur("buat kalkulator", "cari_bug", True),
                         ("cari_bug", "dipilih pengguna"))
        self.assertEqual(tim_jalur.pilih_jalur("cari bug", "buat", True)[0], "buat")
        self.assertEqual(tim_jalur.pilih_jalur("x", "perbaiki", False)[0], "perbaiki")   # dicek pemanggil

    def test_info_jalur_untuk_halaman(self):
        e = tim_jalur.info_jalur("perbaiki", "alasan")
        self.assertEqual([t["kunci"] for t in e["urut"]],
                         ["diagnosa", "rencana", "tulis", "periksa", "jelaskan"])
        self.assertEqual(e["urut"][0]["peran"], "Pemeriksa")
        self.assertEqual([t["kunci"] for t in tim_jalur.info_jalur("cari_bug")["urut"]], ["diagnosa", "jelaskan"])
        self.assertEqual(len(tim_jalur.info_jalur("buat")["urut"]), 4)

    def test_cfg_dari_web_memvalidasi_jalur(self):
        for masuk, harapan in (("perbaiki", "perbaiki"), ("cari_bug", "cari_bug"), ("ngawur", "otomatis"),
                               (None, "otomatis"), (3, "otomatis")):
            cfg, err = tim.siapkan_cfg({"model_p": "A", "model_e": "B", "jalur": masuk}, {"A", "B"})
            self.assertEqual((err, cfg["jalur"]), ("", harapan))


# ------------------------------------------------------------------ pemeriksaan awal
class TestDiagnosaMenjalankan(DasarJalur):
    def jalan_diag(self, isi, uji=False):
        self._n = getattr(self, "_n", 0) + 1
        d = self.bahan(isi, "bahan%d" % self._n)
        berkas = tim.baca_proyek(d, 100)
        gen = tim.diagnosa_menjalankan({"uji": uji}, d, berkas)
        ev = []
        try:
            while True:
                ev.append(next(gen))
        except StopIteration as s:
            return ev, s.value

    def test_sintaks_salah_gagal_dan_berkas_kosong_sah(self):
        ev, bukti = self.jalan_diag({"a.py": "def x(:\n", "pkg/__init__.py": "", "ok.py": "x = 1\n"})
        self.assertFalse(bukti["ok"])
        gagal = [b for b in bukti["baris"] if b.startswith("GAGAL")]
        self.assertEqual(len(gagal), 1)
        self.assertIn("a.py", gagal[0])
        self.assertNotIn("__init__.py", " ".join(bukti["baris"]))        # berkas kosong bukan bug
        self.assertEqual(jenis(ev), ["cek_mulai", "cek"])
        self.assertTrue(ev[-1]["diagnosa"])

    def test_uji_jalan_tebakan_hanya_catatan(self):
        ev, bukti = self.jalan_diag({"main.py": "if __name__ == '__main__':\n    raise SystemExit(3)\n"}, uji=True)
        self.assertTrue(bukti["ok"])                                     # kegagalan tebakan bukan bukti bug
        self.assertEqual(bukti["jalan"], "gagal")
        self.assertTrue(any(b.startswith("CATATAN tebakan") for b in bukti["baris"]))
        self.assertFalse(any(b.startswith("GAGAL") for b in bukti["baris"]))
        self.assertIn("uji_mulai", jenis(ev))

    def test_uji_jalan_dilewati_bila_tidak_diizinkan_atau_tidak_ada_titik_masuk(self):
        ev, bukti = self.jalan_diag({"main.py": "if __name__ == '__main__':\n    print('x')\n"}, uji=False)
        self.assertEqual(bukti["jalan"], "dilewati")
        self.assertNotIn("uji_mulai", jenis(ev))
        ev, bukti = self.jalan_diag({"lib.py": "x = 1\n"}, uji=True)
        self.assertEqual(bukti["jalan"], "dilewati")

    def test_tebak_perintah(self):
        main = "if __name__ == '__main__':\n    pass\n"
        self.assertEqual(tim_cek.tebak_perintah([("app.py", main), ("lib.py", "x = 1\n")]), ["python3", "app.py"])
        self.assertEqual(tim_cek.tebak_perintah([("app.py", main), ("main.py", main)]), ["python3", "main.py"])
        self.assertEqual(tim_cek.tebak_perintah([("lib.py", "x = 1\n")]), [])
        self.assertEqual(tim_cek.tebak_perintah([("a.py", main), ("b.py", main)]), [])       # ragu: tidak menebak
        self.assertEqual(tim_cek.tebak_perintah([("index.js", "console.log(1)")]), ["node", "index.js"])
        self.assertEqual(tim_cek.tebak_perintah([("sub/x.py", main)]), [])


class TestPromptDiagnosa(unittest.TestCase):
    def test_fokus_mendahulukan_yang_disebut_gagal_dan_titik_masuk(self):
        berkas = [("a_kecil.py", "x = 1\n"), ("main.py", "y = 2\n" * 10), ("rusak.py", "z = 3\n" * 10),
                  ("target.py", "w = 4\n" * 10)] + [("f%02d.py" % i, "q = 1\n" * 200) for i in range(20)]
        utama, lain = tim_prompt.pilih_fokus(berkas, "cek target.py", ["GAGAL rusak.py: sintaks Python salah"], 600)
        nama = [n for n, _ in utama]
        for wajib in ("target.py", "rusak.py", "main.py"):
            self.assertIn(wajib, nama)
        self.assertIn("a_kecil.py", nama)                                  # kecil dan muat
        self.assertEqual(len(utama) + len(lain), len(berkas))
        self.assertTrue(all(n.startswith("f") for n, _ in lain))           # besar-besar jadi konteks

    def test_prompt_menyebut_yang_tidak_ditampilkan_dan_jumlahnya(self):
        berkas = [("main.py", "print(1)\n")] + [("f%02d.py" % i, "q = 1\n" * 300) for i in range(30)]
        user, dilihat, total = tim_prompt.prompt_diagnosa("cari bug", "OK sintaks", berkas)
        self.assertEqual(total, 31)
        self.assertLess(dilihat, total)
        self.assertIn("isi tidak ditampilkan", user)
        self.assertIn("<permintaan_pengguna>", user)
        self.assertLess(len(user), tim_prompt.anggaran_prompt(tim_config.TOKEN_PERIKSA) + 1500)

    def test_prompt_rencana_memuat_temuan(self):
        p = tim_prompt.prompt_rencana("perbaiki", None, ["main.py"],
                                      diagnosa={"ringkas": "ada bug", "masalah": ["main.py:3 - x"], "perbaikan": "ubah x"})
        self.assertIn("TEMUAN PEMERIKSA", p)
        self.assertIn("- main.py:3 - x", p)
        self.assertIn("JANGAN menambah fitur", p)
        self.assertNotIn("TEMUAN PEMERIKSA", tim_prompt.prompt_rencana("buat", None, []))


# ------------------------------------------------------------------ jalur cari_bug
class TestCariBug(DasarJalur):
    def test_hanya_memeriksa_dan_melapor_tanpa_mengubah_berkas(self):
        d = self.bahan({"main.py": MAIN_BUG, "util.py": "def dua():\n    return 2\n"})
        stream = StreamCatat(periksa=[DIAG_BUG], jelaskan=["Ada pembagian nol yang belum ditangani."])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev = self.proses("cari bug di kode ini", self.cfg(uji=False), d)
        self.assertEqual(ev[-1]["status"], "analisis")
        self.assertEqual(stream.urutan(), ["PEMERIKSA", "PENJELAS"])          # tanpa Perencana dan Pelaksana
        tahap = [e["tahap"] for e in ev if e["t"] == "tahap"]
        self.assertEqual(tahap, ["diagnosa", "jelaskan"])
        for bukan in ("rencana", "putaran", "nilai", "berkas", "pulih"):
            self.assertNotIn(bukan, jenis(ev))
        urutan = [t for t in jenis(ev) if t in ("mulai", "bahan", "jalur", "tahap", "cek", "diagnosa", "selesai")]
        self.assertEqual(urutan, ["mulai", "bahan", "jalur", "tahap", "cek", "diagnosa", "tahap", "selesai"])
        self.assertEqual(self.isi_hasil(ev), {"main.py": MAIN_BUG, "util.py": "def dua():\n    return 2\n"})
        diag = [e for e in ev if e["t"] == "diagnosa"][0]
        self.assertFalse(diag["ok"])
        self.assertEqual((diag["diperiksa"], diag["total"], diag["dipakai_ulang"]), (2, 2, False))
        jalur = [e for e in ev if e["t"] == "jalur"][0]
        self.assertEqual(jalur["jalur"], "cari_bug")
        self.assertEqual([t["kunci"] for t in jalur["urut"]], ["diagnosa", "jelaskan"])

    def test_laporan_memuat_temuan_dari_kode_bukan_dari_model(self):
        d = self.bahan({"main.py": MAIN_BUG})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["Ada masalah."]))
        ev = self.proses("cari bug", self.cfg(uji=False), d)
        meta = json.loads((self.folder(ev) / "run.json").read_text())
        self.assertEqual((meta["status"], meta["jalur"]), ("analisis", "cari_bug"))
        self.assertEqual(meta["diagnosa"], {"ok": False, "temuan": 1})
        laporan = meta["laporan"]
        self.assertIn("**Temuan Pemeriksa** (1):", laporan)
        self.assertIn("1. main.py:3 - pembagian dengan nol", laporan)
        self.assertIn("**Saran perbaikan**: tangani b == 0", laporan)
        self.assertIn("**Langkah berikut**", laporan)
        self.assertIn("analisis selesai (tidak ada berkas yang diubah)", laporan)
        self.assertTrue((self.folder(ev) / "diagnosa.json").is_file())
        self.assertTrue((self.folder(ev) / "laporan.md").is_file())

    def test_tidak_ada_bug(self):
        d = self.bahan({"main.py": "print('halo')\n"})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_OK], jelaskan=["Tidak ada masalah."]))
        ev = self.proses("cari bug", self.cfg(uji=False), d)
        self.assertEqual(ev[-1]["status"], "analisis")
        laporan = json.loads((self.folder(ev) / "run.json").read_text())["laporan"]
        self.assertIn("tidak ada bug nyata", laporan)
        self.assertIn("bukan jaminan", laporan)
        self.assertNotIn("Langkah berikut", laporan)

    def test_sintaks_salah_tidak_boleh_dinyatakan_bersih(self):
        d = self.bahan({"main.py": "def x(:\n    pass\n"})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_OK], jelaskan=["x"]))
        ev = self.proses("cari bug", self.cfg(uji=False), d)
        diag = [e for e in ev if e["t"] == "diagnosa"][0]
        self.assertFalse(diag["ok"])
        self.assertIn("main.py", diag["masalah"][0])
        self.assertIn("disesuaikan", diag["ringkas"])

    def test_tanpa_berkas_minta_unggah_tanpa_memuat_model(self):
        stream = StreamCatat()
        llama = LlamaPalsu("A", "B")
        self.pasang(llama, stream)
        cfg = self.cfg()
        cfg["jalur"] = "cari_bug"                                           # pilihan eksplisit
        ev = self.proses("apa saja", cfg, None)
        self.assertEqual(ev[-1]["status"], "butuh_info")
        self.assertIn("tanya", jenis(ev))
        self.assertIn("Unggah berkas", [e for e in ev if e["t"] == "tanya"][0]["d"])
        self.assertEqual(stream.panggilan, [])
        self.assertEqual(set(llama.state.values()), {"unloaded"})

    def test_model_pemeriksa_dan_penjelas_dimuat_bergiliran_mode_3(self):
        d = self.bahan({"main.py": MAIN_BUG})
        llama = LlamaPalsu("A", "B", "C")
        stream = StreamCatat(periksa=[DIAG_BUG], jelaskan=["ok"])
        self.pasang(llama, stream)
        self.proses("cari bug", self.cfg(mode=3, uji=False), d)
        self.assertEqual(stream.panggilan, [("PEMERIKSA", "C"), ("PENJELAS", "A")])     # Pelaksana (B) tak pernah dimuat
        self.assertEqual(set(llama.state.values()), {"unloaded"})


# ------------------------------------------------------------------ jalur perbaiki
class TestPerbaiki(DasarJalur):
    def isi_stream(self, **k):
        return StreamCatat(**k)

    def test_urutan_diagnosa_rencana_tulis_periksa_jelaskan_dan_temuan_jadi_koreksi_pertama(self):
        d = self.bahan({"main.py": MAIN_BUG})
        stream = StreamCatat(rencana=[RENCANA_FIX], tulis=["=== FILE: main.py ===\nprint('halo')\n=== END ==="],
                             periksa=[DIAG_BUG, NILAI_OK], jelaskan=["Sudah diperbaiki."])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev = self.proses("perbaiki bug pembagian nol", self.cfg(uji=True), d)
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(stream.urutan(), ["PEMERIKSA", "PERENCANA", "PELAKSANA", "PEMERIKSA", "PENJELAS"])
        self.assertEqual([e["tahap"] for e in ev if e["t"] == "tahap"],
                         ["diagnosa", "rencana", "tulis", "periksa", "jelaskan"])
        # Perencana diberi temuan, Pelaksana menerimanya sebagai koreksi pertama
        self.assertIn("TEMUAN PEMERIKSA", stream.user["PERENCANA"][0])
        self.assertIn("pembagian dengan nol", stream.user["PERENCANA"][0])
        self.assertIn("MASUKAN PEMERIKSA", stream.user["PELAKSANA"][0])
        self.assertIn("tangani b == 0", stream.user["PELAKSANA"][0])
        jalur = [e for e in ev if e["t"] == "jalur"][0]
        self.assertEqual(jalur["jalur"], "perbaiki")
        self.assertEqual(len(jalur["urut"]), 5)
        self.assertEqual(self.isi_hasil(ev)["main.py"], "print('halo')\n")           # berkas diperbaiki

    def test_tidak_ada_bug_jalan_pintas_tanpa_menulis(self):
        d = self.bahan({"main.py": "print('halo')\n"})
        stream = StreamCatat(periksa=[DIAG_OK], jelaskan=["Tidak ada masalah."])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev = self.proses("perbaiki bug", self.cfg(uji=False), d)
        self.assertEqual(ev[-1]["status"], "analisis")
        self.assertEqual(stream.urutan(), ["PEMERIKSA", "PENJELAS"])
        self.assertIn("ringkas", jenis(ev))                                 # pengguna diberi tahu
        self.assertEqual(self.isi_hasil(ev), {"main.py": "print('halo')\n"})

    def test_jalur_dipilih_otomatis_dari_isi_tugas(self):
        d = self.bahan({"main.py": MAIN_BUG})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_OK], jelaskan=["x"]))
        ev = self.proses("perbaiki bug pembagian nol", self.cfg(uji=False), d)
        self.assertEqual([e for e in ev if e["t"] == "jalur"][0]["jalur"], "perbaiki")
        # tugas tambah fitur dengan berkas yang ada: alur lama (tanpa diagnosa)
        d2 = self.bahan({"main.py": MAIN_BUG}, "bahan2")
        stream = StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], jelaskan=["x"])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev = self.proses("tambahkan fungsi kali", self.cfg(uji=False), d2)
        self.assertEqual([e for e in ev if e["t"] == "jalur"][0]["jalur"], "buat")
        self.assertEqual(stream.urutan(), ["PERENCANA", "PELAKSANA", "PEMERIKSA", "PENJELAS"])

    def test_tanpa_pilihan_dan_tanpa_berkas_tetap_alur_lama(self):
        stream = StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev = self.proses("buat halo", self.cfg(uji=False))
        jalur = [e for e in ev if e["t"] == "jalur"][0]
        self.assertEqual((jalur["jalur"], len(jalur["urut"])), ("buat", 4))
        self.assertEqual(ev[-1]["status"], "lolos")

    def test_diagnosa_cari_bug_dipakai_ulang_saat_perbaiki_lanjutan(self):
        d = self.bahan({"main.py": MAIN_BUG, "util.py": "x = 1\n"})
        stream = StreamCatat(periksa=[DIAG_BUG], jelaskan=["laporan"])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev1 = self.proses("cari bug", self.cfg(uji=False), d)
        awal = json.loads((self.folder(ev1) / "run.json").read_text())["id"]
        # proses kedua: perbaiki temuan tadi, tanpa memeriksa ulang
        stream2 = StreamCatat(rencana=[RENCANA_FIX], tulis=["=== FILE: main.py ===\nprint('halo')\n=== END ==="],
                              periksa=[NILAI_OK], jelaskan=["selesai"])
        self.pasang(LlamaPalsu("A", "B"), stream2)
        ev2 = self.proses("perbaiki temuan dari analisis sebelumnya", self.cfg(uji=True), None, lanjut=awal)
        self.assertEqual(ev2[-1]["status"], "lolos")
        diag = [e for e in ev2 if e["t"] == "diagnosa"][0]
        self.assertTrue(diag["dipakai_ulang"])
        self.assertEqual(stream2.urutan(), ["PERENCANA", "PELAKSANA", "PEMERIKSA", "PENJELAS"])   # tanpa diagnosa baru
        self.assertEqual([e["tahap"] for e in ev2 if e["t"] == "tahap"], ["rencana", "tulis", "periksa", "jelaskan"])
        self.assertIn("pembagian dengan nol", stream2.user["PELAKSANA"][0])
        self.assertTrue((self.folder(ev2) / "diagnosa.json").is_file())          # rantai bisa dilanjutkan lagi

    def test_diagnosa_lama_tidak_dipakai_bila_proyek_berubah(self):
        d = self.bahan({"main.py": MAIN_BUG})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["laporan"]))
        ev1 = self.proses("cari bug", self.cfg(uji=False), d)
        awal = self.folder(ev1).name
        ubah = self.bahan({"main.py": MAIN_BUG + "# diubah pengguna\n"}, "bahan_baru")
        stream = StreamCatat(rencana=[RENCANA_FIX], tulis=["=== FILE: main.py ===\nprint('halo')\n=== END ==="],
                             periksa=[DIAG_BUG, NILAI_OK], jelaskan=["x"])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev2 = self.proses("perbaiki bug", self.cfg(uji=True), ubah, lanjut=awal)
        self.assertFalse([e for e in ev2 if e["t"] == "diagnosa"][0]["dipakai_ulang"])
        self.assertEqual(stream.urutan()[0], "PEMERIKSA")                        # diagnosa baru dijalankan

    def test_lanjut_menyalin_seluruh_proyek_besar(self):
        """Regresi: lanjutan hanya menyalin 36 berkas pertama, padahal unggahan bisa sampai 100."""
        isi = {"f%03d.py" % i: "x = %d\n" % i for i in range(60)}
        d = self.bahan(isi)
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["laporan"]))
        ev1 = self.proses("cari bug", self.cfg(uji=False), d)
        awal = self.folder(ev1).name
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["laporan"]))
        ev2 = self.proses("cari bug lagi", self.cfg(uji=False), None, lanjut=awal)
        self.assertEqual(len(self.isi_hasil(ev2)), 60)
        diag = [e for e in ev2 if e["t"] == "diagnosa"][0]
        self.assertEqual(diag["total"], 60)


class TestRiwayatJalur(DasarJalur):
    def test_status_analisis_tampil_di_riwayat_dan_jalur_tercatat(self):
        d = self.bahan({"main.py": MAIN_BUG})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["x"]))
        ev = self.proses("cari bug", self.cfg(uji=False), d)
        run = tim.daftar_run()[0]
        self.assertEqual(run["status"], "analisis")
        self.assertIn("analisis", tim_config.STATUS_TEKS)
        baca = tim.baca_run(run["id"])
        self.assertEqual(baca["jalur"], "cari_bug")
        self.assertEqual(ev[-1]["teks"], tim_config.STATUS_TEKS["analisis"])


class TestHalamanAlur(DasarJalur):
    """web/agent.js memutar event nyata dari jalur baru (dilewati bila node tidak terpasang)."""

    def smoke(self, ev):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        berkas = Path(self._tmp.name) / "ev.ndjson"
        berkas.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in ev) + "\n", encoding="utf-8")
        skrip = Path(__file__).resolve().parent / "agent_smoke.js"
        r = subprocess.run([node, str(skrip), str(berkas)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    def test_cari_bug_dua_tahap_dan_tombol_perbaiki(self):
        d = self.bahan({"main.py": MAIN_BUG})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["Ada pembagian nol."]))
        hasil = self.smoke(self.proses("cari bug", self.cfg(uji=False), d))
        self.assertEqual(hasil["galat"], [], hasil["err"])
        self.assertEqual([a["id"] for a in hasil["alur"]], ["st_diagnosa", "st_jelaskan"])      # alur diganti server
        self.assertEqual(hasil["alur_kolom"], "repeat(2,1fr)")
        self.assertEqual([a["nama"] for a in hasil["alur"]], ["Diagnosa", "Penjelas"])
        self.assertTrue(all("selesai" in a["kelas"] for a in hasil["alur"]), hasil["alur"])
        self.assertEqual(hasil["kartu_diag"], 1)
        log = "\n".join(hasil["teks_log"])
        self.assertIn("Jalur Cari bug", log)
        self.assertIn("Diagnosa: 1 temuan", log)
        self.assertIn("pembagian dengan nol", log)
        self.assertTrue(hasil["lencana_selesai"])
        self.assertIn("Jalur: Cari bug", " ".join(hasil["info"]))
        self.assertTrue(hasil["saran_tampil"])                                                  # tawarkan perbaikan
        self.assertEqual(hasil["saran_teks"], "1 temuan. Perbaiki sekarang?")

    def test_perbaiki_lima_tahap(self):
        d = self.bahan({"main.py": MAIN_BUG})
        stream = StreamCatat(rencana=[RENCANA_FIX], tulis=["=== FILE: main.py ===\nprint('halo')\n=== END ==="],
                             periksa=[DIAG_BUG, NILAI_OK], jelaskan=["Sudah diperbaiki."])
        self.pasang(LlamaPalsu("A", "B"), stream)
        hasil = self.smoke(self.proses("perbaiki bug pembagian nol", self.cfg(uji=True), d))
        self.assertEqual(hasil["galat"], [], hasil["err"])
        self.assertEqual([a["id"] for a in hasil["alur"]],
                         ["st_diagnosa", "st_rencana", "st_tulis", "st_periksa", "st_jelaskan"])
        self.assertEqual(hasil["alur_kolom"], "repeat(5,1fr)")
        self.assertTrue(all("selesai" in a["kelas"] for a in hasil["alur"]), hasil["alur"])
        self.assertFalse(hasil["saran_tampil"])                                                 # sudah diperbaiki

    def test_jalan_pintas_tahap_yang_dilewati_bertanda(self):
        d = self.bahan({"main.py": "print('halo')\n"})
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_OK], jelaskan=["Bersih."]))
        hasil = self.smoke(self.proses("perbaiki bug", self.cfg(uji=False), d))
        kelas = {a["id"]: a["kelas"] for a in hasil["alur"]}
        self.assertIn("selesai", kelas["st_diagnosa"])
        self.assertIn("selesai", kelas["st_jelaskan"])
        for k in ("st_rencana", "st_tulis", "st_periksa"):
            self.assertIn("lewat", kelas[k], k)                                                 # tidak dilalui
        self.assertFalse(hasil["saran_tampil"])

    def test_alur_lama_tetap_empat_tahap(self):
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK],
                                                       jelaskan=["Selesai."]))
        hasil = self.smoke(self.proses("buat halo", self.cfg(uji=False)))
        self.assertEqual([a["id"] for a in hasil["alur"]], ["st_rencana", "st_tulis", "st_periksa", "st_jelaskan"])
        self.assertEqual(hasil["alur_kolom"], "repeat(4,1fr)")

    def test_html_memiliki_elemen_yang_dirujuk_js(self):
        web = Path(__file__).resolve().parent.parent / "web"
        html = (web / "agent.html").read_text(encoding="utf-8")
        for pasti in ('id="relAlur"', 'id="saranBar"', 'id="btnSaran"', 'id="saranTeks"', 'id="jalurBar"',
                      'id="jl_otomatis"', 'id="jl_buat"', 'id="jl_perbaiki"', 'id="jl_cari_bug"'):
            self.assertIn(pasti, html)


class TestJalurLewatHttp(DasarServer):
    """Pilihan jalur dari halaman sampai ke proses di server (unggah -> jalankan -> baca event)."""
    DASAR = {"teks": "cari bug di kode ini", "mode": 2, "model_p": "A", "model_e": "B", "maks": 2, "uji": False}

    def setUp(self):
        super().setUp()
        with asisten.AGENT_COND:
            asisten.AGENT.update(sesi=None, id=None, tugas="", events=[], awal=0, aktif=False, mulai=0.0, status=None)

    def baca(self, sesi):
        ev, nomor = [], 0
        for _ in range(100):
            kode, isi = self.req("GET", "/api/agent/event?sesi=%s&dari=%d&tunggu=5" % (sesi, nomor))
            d = json.loads(isi)
            ev += d["events"]
            nomor = d["next"]
            if d["habis"]:
                return ev
        self.fail("proses tidak selesai")

    def jalankan(self, **tambahan):
        paket = self.unggah("main.py", MAIN_BUG.encode())[1]["paket"]
        kode, isi = self.req("POST", "/api/agent/jalankan", dict(self.DASAR, unggahan=paket, **tambahan))
        self.assertEqual(kode, 200, isi)
        return self.baca(json.loads(isi)["sesi"])

    def test_otomatis_memilih_cari_bug_dan_hanya_menganalisis(self):
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["Ada pembagian nol."]))
        ev = self.jalankan(jalur="otomatis")
        self.assertEqual([e for e in ev if e["t"] == "jalur"][0]["jalur"], "cari_bug")
        self.assertEqual(ev[-1]["status"], "analisis")
        self.assertEqual([e["tahap"] for e in ev if e["t"] == "tahap"], ["diagnosa", "jelaskan"])
        self.assertEqual(self.req("GET", "/api/agent/riwayat")[0], 200)
        run = json.loads(self.req("GET", "/api/agent/riwayat")[1])["run"][0]
        self.assertEqual(run["status"], "analisis")

    def test_pilihan_pengguna_mengalahkan_isi_tugas(self):
        stream = StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], jelaskan=["x"])
        self.pasang(LlamaPalsu("A", "B"), stream)
        ev = self.jalankan(jalur="buat")                       # tugasnya "cari bug", tetapi pengguna memilih Buat
        self.assertEqual([e for e in ev if e["t"] == "jalur"][0]["jalur"], "buat")
        self.assertEqual(stream.urutan(), ["PERENCANA", "PELAKSANA", "PEMERIKSA", "PENJELAS"])

    def test_nilai_jalur_ngawur_dianggap_otomatis(self):
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(periksa=[DIAG_BUG], jelaskan=["x"]))
        ev = self.jalankan(jalur="ngawur")
        self.assertEqual([e for e in ev if e["t"] == "jalur"][0]["jalur"], "cari_bug")


if __name__ == "__main__":
    unittest.main()
