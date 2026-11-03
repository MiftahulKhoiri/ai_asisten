"""Pengujian prompt pilihan per peran Agent (tombol "+ prompt"): pemisahan perilaku/kontrak format,
perakitan prompt sistem (tambah/ganti), sambungan ke alur tim, penyimpanan per peran
(prompt/agent/<peran>/), rute /api/agent/prompt*, dan halamannya."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import asisten  # noqa: E402
import tim  # noqa: E402
from server import server_agent, server_peran as per  # noqa: E402
from server import server_prompt as prm  # noqa: E402
from test_tim import (CtxPalsu, DasarAgent, KODE_BAIK, LlamaPalsu, NILAI_OK, RENCANA, jenis)  # noqa: E402
from test_unggah import DasarServer  # noqa: E402
from test_unggah import setUpModule as _unggah_setUp, tearDownModule as _unggah_tear  # noqa: E402
from tim import tim_llm, tim_prompt  # noqa: E402

PERAN = ("perencana", "pelaksana", "pemeriksa", "penjelas")


def setUpModule():
    _unggah_setUp()


def tearDownModule():
    _unggah_tear()


# ---------------------------------------------------------------- prompt sistem
class TestPisahPerilakuKontrak(unittest.TestCase):
    PENANDA = {"perencana": '"SKEMA WAJIB', "pelaksana": "=== FILE: nama_berkas ===", "periksa": '"ok": true atau false',
               "diagnosa": '"ok": true bila TIDAK ADA bug'}

    def test_kontrak_memuat_format_dan_perilaku_tidak(self):
        for tahap, penanda in self.PENANDA.items():
            self.assertIn(penanda.strip('"'), tim_prompt.KONTRAK[tahap], tahap)
            self.assertNotIn(penanda.strip('"'), tim_prompt.PERILAKU[tahap], tahap)

    def test_tidak_ada_baris_yang_hilang(self):
        """perilaku + kontrak = seluruh prompt bawaan (tidak ada aturan yang hilang diam-diam)."""
        for tahap, dasar in tim_prompt.DASAR_SISTEM.items():
            gabung = tim_prompt.PERILAKU[tahap] + "\n" + tim_prompt.KONTRAK[tahap]
            for baris in dasar.splitlines():
                if baris.strip():
                    self.assertIn(baris.strip(), gabung, "%s: %r" % (tahap, baris[:60]))

    def test_perencana_kontrak_memuat_contoh_dan_perilaku_memuat_prinsip(self):
        self.assertIn("CONTOH (permintaan", tim_prompt.KONTRAK["perencana"])
        self.assertIn("PRINSIP MEMAHAMI MAKSUD", tim_prompt.PERILAKU["perencana"])
        self.assertIn("ATURAN TAMBAHAN", tim_prompt.PERILAKU["perencana"])

    def test_kontrak_menyertakan_pengaman_data_untuk_peran_yang_membaca_data(self):
        for tahap in ("perencana", "pelaksana", "periksa", "diagnosa"):
            self.assertIn("<permintaan_pengguna>", tim_prompt.KONTRAK[tahap])

    def test_penjelas_kontraknya_prosa_singkat(self):
        for tahap in ("jelaskan", "jelaskan_bug"):
            self.assertIn("prosa singkat", tim_prompt.KONTRAK[tahap])

    def test_perilaku_peran_untuk_salinan(self):
        for peran in PERAN:
            self.assertEqual(tim.perilaku_peran(peran), tim_prompt.PERILAKU[tim_prompt.PERAN_TAHAP[peran][0]])


class TestRakitSistem(unittest.TestCase):
    DASAR, KONTRAK = "Kamu X. Bekerja rapi.", "Balas JSON."

    def rakit(self, spek):
        return tim_prompt.rakit_sistem(self.DASAR, self.KONTRAK, spek)

    def test_tanpa_pilihan_persis_bawaan(self):
        for spek in (None, {}, {"mode": "ganti", "teks": ""}, {"mode": "tambah", "teks": "   "}, "bukan dict", 5):
            self.assertEqual(self.rakit(spek), self.DASAR, spek)

    def test_tambah_bawaan_utuh_lalu_instruksi(self):
        h = self.rakit({"mode": "tambah", "teks": "Jawab singkat."})
        self.assertTrue(h.startswith(self.DASAR))
        self.assertTrue(h.endswith("Jawab singkat."))
        self.assertIn("INSTRUKSI TAMBAHAN DARI PENGGUNA", h)

    def test_mode_tak_dikenal_dianggap_tambah(self):
        self.assertTrue(self.rakit({"mode": "aneh", "teks": "A"}).startswith(self.DASAR))

    def test_ganti_membuang_perilaku_bawaan_tetapi_kontrak_selalu_ikut(self):
        h = self.rakit({"mode": "ganti", "teks": "Kamu penulis puisi."})
        self.assertTrue(h.startswith("Kamu penulis puisi."))
        self.assertNotIn(self.DASAR, h)
        self.assertTrue(h.endswith(self.KONTRAK))
        self.assertIn("WAJIB dipenuhi apa pun instruksi di atas", h)

    def test_waktu_diganti(self):
        for mode in ("tambah", "ganti"):
            h = self.rakit({"mode": mode, "teks": "Sekarang {waktu}."})
            self.assertNotIn("{waktu}", h)
            self.assertRegex(h, r"Sekarang \d{4}-\d{2}-\d{2} \d{2}:\d{2}\.")

    def test_sistem_peran_memilih_peran_menurut_tahap(self):
        class C:
            prompt_peran = {"pemeriksa": {"mode": "tambah", "teks": "P-PERIKSA"},
                            "penjelas": {"mode": "ganti", "teks": "P-JELAS"}}
        c = C()
        self.assertIn("P-PERIKSA", tim_prompt.sistem_peran(c, "periksa"))
        self.assertIn("P-PERIKSA", tim_prompt.sistem_peran(c, "diagnosa"))        # Pemeriksa juga mendiagnosa
        self.assertIn("P-JELAS", tim_prompt.sistem_peran(c, "jelaskan"))
        self.assertIn("P-JELAS", tim_prompt.sistem_peran(c, "jelaskan_bug"))
        self.assertEqual(tim_prompt.sistem_peran(c, "perencana"), tim_prompt.SYSTEM_PERENCANA)
        self.assertEqual(tim_prompt.sistem_peran(c, "pelaksana"), tim_prompt.SYSTEM_PELAKSANA)

    def test_ctx_tanpa_atribut_atau_tiruan_memakai_bawaan(self):
        for ctx in (object(), None, mock.MagicMock(), type("C", (), {"prompt_peran": "x"})()):
            for tahap, dasar in tim_prompt.DASAR_SISTEM.items():
                self.assertEqual(tim_prompt.sistem_peran(ctx, tahap), dasar)


class TestCfgPromptPeran(unittest.TestCase):
    def test_siapkan_cfg_merapikan(self):
        b = {"model_p": "A", "model_e": "B", "prompt_peran": {
            "perencana": {"mode": "ganti", "teks": "  rencana  ", "nama": ["X", 5, "Y" * 80]},
            "pelaksana": {"mode": "aneh", "teks": "tulis"},
            "pemeriksa": {"mode": "tambah", "teks": "   "},          # kosong: dibuang
            "penjelas": "bukan dict",                                  # salah bentuk: dibuang
            "hacker": {"mode": "ganti", "teks": "x"}}}                 # peran tak dikenal: dibuang
        cfg, err = tim.siapkan_cfg(b, {"A", "B"})
        self.assertEqual(err, "")
        self.assertEqual(sorted(cfg["prompt_peran"]), ["pelaksana", "perencana"])
        self.assertEqual(cfg["prompt_peran"]["perencana"], {"mode": "ganti", "teks": "rencana", "nama": ["X", "Y" * 40]})
        self.assertEqual(cfg["prompt_peran"]["pelaksana"]["mode"], "tambah")

    def test_tanpa_atau_rusak_menjadi_kosong(self):
        for nilai in (None, [], "x", 5, {}):
            cfg, _ = tim.siapkan_cfg({"model_p": "A", "model_e": "B", "prompt_peran": nilai}, {"A", "B"})
            self.assertEqual(cfg["prompt_peran"], {}, nilai)

    def test_teks_dipotong_ke_batas(self):
        cfg, _ = tim.siapkan_cfg({"model_p": "A", "model_e": "B",
                                  "prompt_peran": {"perencana": {"teks": "x" * 99999}}}, {"A", "B"})
        self.assertEqual(len(cfg["prompt_peran"]["perencana"]["teks"]), tim.MAKS_TEKS_PERAN)


# ---------------------------------------------------------------- alur tim
class StreamCatatSistem:
    """Menjawab berurutan (rencana, tulis, periksa, jelaskan) dan mencatat pesan system tiap panggilan."""

    def __init__(self):
        self.jawaban = [RENCANA, KODE_BAIK, NILAI_OK, "Selesai dibuat."]
        self.sistem = []

    def __call__(self, model, pesan, batal, token, suhu=0.2, json_mode=False):
        self.sistem.append(pesan[0]["content"])
        j = self.jawaban.pop(0)
        yield {"choices": [{"delta": {"content": j}, "finish_reason": "stop"}],
               "timings": {"predicted_n": 5, "predicted_per_second": 2.0, "prompt_n": 10}}


class TestAlurDenganPrompt(DasarAgent):
    def proses(self, prompt_peran=None):
        s = StreamCatatSistem()
        self.pasang(LlamaPalsu("A", "B"), s)
        cfg = self.cfg(uji=False)
        if prompt_peran is not None:
            cfg["prompt_peran"] = prompt_peran
        ev, ctx = self.jalan(cfg)
        return ev, s, ctx

    def test_tanpa_pilihan_prompt_sama_persis_dengan_dulu(self):
        ev, s, _ = self.proses()
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(s.sistem, [tim_prompt.SYSTEM_PERENCANA, tim_prompt.SYSTEM_PELAKSANA,
                                    tim_prompt.SYSTEM_PEMERIKSA, tim_prompt.SYSTEM_PENJELAS])
        self.assertEqual([e for e in ev if e["t"] == "mulai"][0]["prompt"], {})

    def test_tambah_sampai_ke_tiap_peran(self):
        pil = {p: {"mode": "tambah", "teks": "TAMBAHAN-" + p.upper(), "nama": ["N-" + p]} for p in PERAN}
        ev, s, _ = self.proses(pil)
        self.assertEqual(ev[-1]["status"], "lolos")
        urut = ["perencana", "pelaksana", "pemeriksa", "penjelas"]
        dasar = [tim_prompt.SYSTEM_PERENCANA, tim_prompt.SYSTEM_PELAKSANA, tim_prompt.SYSTEM_PEMERIKSA, tim_prompt.SYSTEM_PENJELAS]
        for sis, peran, bawaan in zip(s.sistem, urut, dasar):
            self.assertTrue(sis.startswith(bawaan), peran)
            self.assertTrue(sis.endswith("TAMBAHAN-" + peran.upper()), peran)

    def test_ganti_menggantikan_perilaku_tetapi_format_tetap_dan_proses_tetap_lolos(self):
        pil = {"pelaksana": {"mode": "ganti", "teks": "Kamu penulis kode ringkas.", "nama": ["Ringkas"]},
               "perencana": {"mode": "ganti", "teks": "Kamu perancang tugas.", "nama": ["Rancang"]}}
        ev, s, _ = self.proses(pil)
        self.assertEqual(ev[-1]["status"], "lolos")
        rencana, tulis = s.sistem[0], s.sistem[1]
        self.assertTrue(tulis.startswith("Kamu penulis kode ringkas."))
        self.assertNotIn("Kamu PELAKSANA dalam tim", tulis)
        self.assertIn("=== FILE: nama_berkas ===", tulis)                  # format blok berkas tetap ikut
        self.assertTrue(rencana.startswith("Kamu perancang tugas."))
        self.assertIn("SKEMA WAJIB", rencana)                               # skema JSON tetap ikut
        self.assertEqual(s.sistem[2], tim_prompt.SYSTEM_PEMERIKSA)          # peran lain tidak terpengaruh

    def test_event_mulai_dan_riwayat_mencatat_prompt_yang_dipakai(self):
        pil = {"pemeriksa": {"mode": "ganti", "teks": "x", "nama": ["Teliti"]}}
        ev, _, _ = self.proses(pil)
        mulai = [e for e in ev if e["t"] == "mulai"][0]
        self.assertEqual(mulai["prompt"], {"pemeriksa": {"mode": "ganti", "nama": ["Teliti"]}})
        meta = json.loads((Path(self._tmp.name) / mulai["id"] / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["prompt"], {"pemeriksa": {"mode": "ganti", "nama": ["Teliti"]}})
        self.assertNotIn("teks", json.dumps(mulai["prompt"]))                # isi prompt tidak ikut ke event

    def test_pilihan_rusak_diabaikan_bukan_menggagalkan_proses(self):
        ev, s, _ = self.proses({"perencana": "rusak", "x": 1, "pelaksana": {"teks": 5}})
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(s.sistem[0], tim_prompt.SYSTEM_PERENCANA)


# ---------------------------------------------------------------- penyimpanan per peran
class DasarPeran(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "prompt"
        for nama, nilai in (("PROMPT_DIR", self.dir), ("PROMPT_FILE", Path(self._tmp.name) / "prompt.json")):
            p = mock.patch.object(asisten, nama, nilai)
            p.start()
            self.addCleanup(p.stop)


class TestPenyimpananPeran(DasarPeran):
    def test_awal_hanya_bawaan_peran_berisi_perilaku_tanpa_format(self):
        for peran in PERAN:
            d = per.daftar_prompt_peran(peran)
            self.assertEqual(len(d), 1)
            self.assertEqual((d[0]["id"], d[0]["bawaan"]), ("bawaan", True))
            self.assertEqual(d[0]["nama"], "Bawaan (%s)" % tim.PERAN_LABEL[peran])
            self.assertEqual(d[0]["isi"], tim.perilaku_peran(peran))
        self.assertNotIn("SKEMA WAJIB", per.daftar_prompt_peran("perencana")[0]["isi"])
        self.assertFalse(self.dir.exists())

    def test_tersimpan_sebagai_berkas_di_folder_peran(self):
        a = per.tambah_prompt_peran("pelaksana", "Kode Ringkas", "Tulis kode sesingkat mungkin.", "untuk model kecil")
        self.assertEqual(a["id"], "kode-ringkas")
        f = self.dir / "agent" / "pelaksana" / "kode-ringkas.json"
        self.assertTrue(f.is_file())
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")),
                         {"format": "ai-asisten-prompt", "versi": 1, "nama": "Kode Ringkas",
                          "isi": "Tulis kode sesingkat mungkin.", "catatan": "untuk model kecil"})
        self.assertFalse(list(f.parent.glob("*.tmp")))

    def test_tiap_peran_punya_daftar_sendiri_dan_chat_tidak_ikut_campur(self):
        per.tambah_prompt_peran("perencana", "Rencana A", "isi rencana")
        per.tambah_prompt_peran("pelaksana", "Kode B", "isi kode")
        prm.tambah_prompt("Obrolan C", "isi obrolan")
        nama = lambda d: [p["nama"] for p in d if not p["bawaan"]]      # noqa: E731
        self.assertEqual(nama(per.daftar_prompt_peran("perencana")), ["Rencana A"])
        self.assertEqual(nama(per.daftar_prompt_peran("pelaksana")), ["Kode B"])
        self.assertEqual(nama(per.daftar_prompt_peran("pemeriksa")), [])
        self.assertEqual(nama(prm.daftar_prompt()), ["Obrolan C"])          # prompt peran tidak muncul di chat
        self.assertEqual(sorted(p.name for p in self.dir.glob("*.json")), ["obrolan-c.json"])

    def test_nama_sama_boleh_di_peran_berbeda_tetapi_tidak_di_peran_yang_sama(self):
        per.tambah_prompt_peran("perencana", "Teliti", "a")
        per.tambah_prompt_peran("pemeriksa", "Teliti", "b")
        with self.assertRaises(ValueError):
            per.tambah_prompt_peran("perencana", "teliti", "c")
        with self.assertRaises(ValueError):                                       # nama bawaan peran dicadangkan
            per.tambah_prompt_peran("perencana", "Bawaan (Perencana)", "d")

    def test_validasi_sama_dengan_prompt_chat(self):
        for nama, isi in (("", "x"), ("x", ""), ("a" * 41, "x"), ("x", "y" * 4001)):
            with self.assertRaises(ValueError):
                per.tambah_prompt_peran("penjelas", nama, isi)

    def test_peran_tidak_dikenal_ditolak_dan_tidak_membuat_folder(self):
        for peran in ("hacker", "", None, "../x", "perencana/../..", 5):
            with self.assertRaises(ValueError, msg=repr(peran)):
                per.tambah_prompt_peran(peran, "a", "b")
            with self.assertRaises(ValueError, msg=repr(peran)):
                per.daftar_prompt_peran(peran)
        self.assertFalse(self.dir.exists())

    def test_ubah_hapus_ekspor(self):
        a = per.tambah_prompt_peran("pemeriksa", "Teliti", "periksa dengan teliti")
        b = per.ubah_prompt_peran("pemeriksa", a["id"], "Sangat Teliti", "baru", "cat")
        self.assertEqual((b["id"], b["nama"], b["isi"], b["catatan"]), (a["id"], "Sangat Teliti", "baru", "cat"))
        self.assertEqual(per.ekspor_prompt_peran("pemeriksa", a["id"]),
                         {"format": "ai-asisten-prompt", "versi": 1, "nama": "Sangat Teliti", "isi": "baru", "catatan": "cat"})
        self.assertIsNone(per.ekspor_prompt_peran("perencana", a["id"]))          # peran lain tidak punya
        self.assertIsNone(per.ubah_prompt_peran("perencana", a["id"], "x", "y"))
        with self.assertRaises(ValueError):
            per.ubah_prompt_peran("pemeriksa", "bawaan", "x", "y")
        with self.assertRaises(ValueError):
            per.hapus_prompt_peran("pemeriksa", "bawaan")
        self.assertFalse(per.hapus_prompt_peran("perencana", a["id"]))
        self.assertTrue(per.hapus_prompt_peran("pemeriksa", a["id"]))
        self.assertEqual(len(per.daftar_prompt_peran("pemeriksa")), 1)

    def test_impor_dan_bagikan_antar_instalasi(self):
        per.tambah_prompt_peran("pelaksana", "Kode Ringkas", "ringkas saja", "cat")
        d = per.ekspor_prompt_peran("pelaksana", "kode-ringkas")
        hasil = per.impor_prompt_peran("perencana", json.dumps(d))               # boleh diimpor ke peran lain
        self.assertEqual([p["nama"] for p in hasil["baru"]], ["Kode Ringkas"])
        hasil = per.impor_prompt_peran("perencana", json.dumps(d))
        self.assertEqual((hasil["baru"], hasil["dilewati"][0]["alasan"]), ([], "sudah ada (isinya sama)"))
        with self.assertRaises(ValueError):
            per.impor_prompt_peran("perencana", "{rusak")
        with self.assertRaises(ValueError):
            per.impor_prompt_peran("perencana", json.dumps({"format": "lain", "nama": "a", "isi": "b"}))

    def test_berkas_disalin_manual_ke_folder_peran_langsung_muncul(self):
        f = self.dir / "agent" / "perencana"
        f.mkdir(parents=True)
        (f / "dari-teman.json").write_text(json.dumps({"format": "ai-asisten-prompt", "versi": 1, "nama": "Dari Teman", "isi": "isi"}))
        (f / "rusak.json").write_text("{bukan json")
        self.assertEqual([p["id"] for p in per.daftar_prompt_peran("perencana")], ["bawaan", "dari-teman"])
        self.assertEqual([x["berkas"] for x in per.abaikan_prompt_peran("perencana")], ["rusak.json"])

    def test_hapus_tidak_mengikuti_symlink(self):
        luar = Path(self._tmp.name) / "luar.json"
        luar.write_text("{}")
        f = self.dir / "agent" / "perencana"
        f.mkdir(parents=True)
        (f / "tautan.json").symlink_to(luar)
        self.assertFalse(per.hapus_prompt_peran("perencana", "tautan"))
        self.assertTrue(luar.exists())

    def test_folder_peran_ikut_asisten_prompt_dir(self):
        self.assertEqual(per.folder_peran("pelaksana"), self.dir / "agent" / "pelaksana")


class TestRakitPromptPeran(DasarPeran):
    def setUp(self):
        super().setUp()
        self.a = per.tambah_prompt_peran("perencana", "Satu", "isi satu")["id"]
        self.b = per.tambah_prompt_peran("perencana", "Dua", "isi dua")["id"]
        self.k = per.tambah_prompt_peran("pelaksana", "Kode", "isi kode")["id"]

    def test_tanpa_pilihan_kosong(self):
        self.assertEqual(per.rakit_prompt_peran(None), {})
        self.assertEqual(per.rakit_prompt_peran({}), {})
        self.assertEqual(per.rakit_prompt_peran({"perencana": {"ids": [], "mode": "ganti"}}), {})

    def test_gabung_menurut_urutan_daftar_bukan_urutan_klik(self):
        h = per.rakit_prompt_peran({"perencana": {"ids": [self.b, self.a], "mode": "ganti"}, "pelaksana": {"ids": [self.k]}})
        self.assertEqual(h["perencana"]["mode"], "ganti")
        self.assertEqual(h["perencana"]["nama"], ["Dua", "Satu"])                  # urut nama: Dua, Satu
        self.assertEqual(h["perencana"]["teks"], "isi dua\n\nisi satu")
        self.assertEqual(h["pelaksana"], {"mode": "tambah", "teks": "isi kode", "nama": ["Kode"]})

    def test_id_dari_peran_lain_atau_yang_sudah_dihapus_dilewati(self):
        self.assertEqual(per.rakit_prompt_peran({"pelaksana": {"ids": [self.a]}}), {})       # milik perencana
        per.hapus_prompt_peran("perencana", self.a)
        h = per.rakit_prompt_peran({"perencana": {"ids": [self.a, self.b]}})
        self.assertEqual(h["perencana"]["nama"], ["Dua"])
        self.assertEqual(per.rakit_prompt_peran({"perencana": {"ids": [self.a]}}), {})        # semua hilang = bawaan

    def test_bawaan_tidak_ikut_diteks(self):
        self.assertEqual(per.rakit_prompt_peran({"perencana": {"ids": ["bawaan"]}}), {})

    def test_bentuk_salah_ditolak(self):
        for pil in ("x", [], {"hacker": {"ids": []}}, {"perencana": "x"}, {"perencana": {"ids": "x"}},
                    {"perencana": {"ids": [1]}}):
            with self.assertRaises(ValueError, msg=repr(pil)):
                per.rakit_prompt_peran(pil)

    def test_terlalu_panjang_ditolak_dengan_pesan_jelas(self):
        ids = [per.tambah_prompt_peran("penjelas", "P%d" % i, "x" * 2000)["id"] for i in range(4)]
        with self.assertRaises(ValueError) as c:
            per.rakit_prompt_peran({"penjelas": {"ids": ids}})
        self.assertIn("Penjelas", str(c.exception))
        self.assertIn("terlalu panjang", str(c.exception))
        per.rakit_prompt_peran({"penjelas": {"ids": ids[:2]}})                              # 4000 karakter: boleh


# ---------------------------------------------------------------- rute HTTP
class DasarServerPeran(DasarServer):
    def setUp(self):
        super().setUp()
        self.dir = Path(self._tmp.name) / "prompt"
        for nama, nilai in (("PROMPT_DIR", self.dir), ("PROMPT_FILE", Path(self._tmp.name) / "prompt.json")):
            p = mock.patch.object(asisten, nama, nilai)
            p.start()
            self.addCleanup(p.stop)

    def j(self, metode, path, body=None):
        kode, isi = self.req(metode, path, body)
        return kode, json.loads(isi)


class TestRutePeran(DasarServerPeran):
    def test_wajib_token(self):
        for metode, path in (("GET", "/api/agent/prompt?peran=perencana"), ("GET", "/api/agent/prompt/ekspor?peran=perencana&id=x"),
                             ("POST", "/api/agent/prompt"), ("POST", "/api/agent/prompt/ubah"),
                             ("POST", "/api/agent/prompt/impor"), ("POST", "/api/agent/prompt/hapus")):
            self.assertEqual(self.req(metode, path, {} if metode == "POST" else None, token=False)[0], 401, path)

    def test_daftar_tambah_ubah_hapus(self):
        kode, d = self.j("GET", "/api/agent/prompt?peran=pelaksana")
        self.assertEqual((kode, d["peran"], [p["id"] for p in d["prompt"]]), (200, "pelaksana", ["bawaan"]))
        self.assertEqual(d["prompt"][0]["isi"], tim.perilaku_peran("pelaksana"))
        kode, d = self.j("POST", "/api/agent/prompt", {"peran": "pelaksana", "nama": "Kode", "isi": "tulis rapi", "catatan": "c"})
        self.assertEqual((kode, d["baru"]["id"], [p["nama"] for p in d["prompt"]]), (200, "kode", ["Bawaan (Pelaksana)", "Kode"]))
        kode, d = self.j("POST", "/api/agent/prompt/ubah", {"peran": "pelaksana", "id": "kode", "nama": "Kode 2", "isi": "baru"})
        self.assertEqual((kode, d["baru"]["nama"], d["baru"]["catatan"]), (200, "Kode 2", "c"))
        self.assertEqual(self.j("GET", "/api/agent/prompt?peran=perencana")[1]["prompt"][1:], [])         # terpisah
        kode, d = self.j("POST", "/api/agent/prompt/hapus", {"peran": "pelaksana", "id": "kode"})
        self.assertEqual((kode, d["ok"], len(d["prompt"])), (200, True, 1))
        self.assertEqual(self.j("POST", "/api/agent/prompt/hapus", {"peran": "pelaksana", "id": "kode"})[0], 404)

    def test_penolakan(self):
        self.assertEqual(self.req("GET", "/api/agent/prompt")[0], 400)
        self.assertEqual(self.req("GET", "/api/agent/prompt?peran=hacker")[0], 400)
        self.assertEqual(self.req("GET", "/api/agent/prompt/ekspor?peran=hacker&id=x")[0], 400)
        for path in ("", "/ubah", "/impor", "/hapus"):
            self.assertEqual(self.req("POST", "/api/agent/prompt" + path, {"peran": "../x", "id": "a", "nama": "a", "isi": "b"})[0], 400, path)
            self.assertEqual(self.req("POST", "/api/agent/prompt" + path, {"nama": "a", "isi": "b"})[0], 400, path)
        self.assertEqual(self.req("POST", "/api/agent/prompt", {"peran": "perencana", "nama": "", "isi": "b"})[0], 400)
        self.assertEqual(self.req("POST", "/api/agent/prompt/hapus", {"peran": "perencana", "id": "bawaan"})[0], 400)
        self.assertEqual(self.req("POST", "/api/agent/prompt/ubah", {"peran": "perencana", "id": "tidakada", "nama": "a", "isi": "b"})[0], 404)
        self.assertFalse(self.dir.exists())

    def test_ekspor_dan_impor(self):
        self.j("POST", "/api/agent/prompt", {"peran": "pemeriksa", "nama": "Teliti", "isi": "periksa teliti"})
        kode, isi = self.req("GET", "/api/agent/prompt/ekspor?peran=pemeriksa&id=teliti")
        self.assertEqual(kode, 200)
        berkas = json.loads(isi)
        self.assertEqual((berkas["format"], berkas["nama"]), ("ai-asisten-prompt", "Teliti"))
        self.assertEqual(self.req("GET", "/api/agent/prompt/ekspor?peran=perencana&id=teliti")[0], 404)
        kode, d = self.j("POST", "/api/agent/prompt/impor", {"peran": "perencana", "teks": isi.decode()})
        self.assertEqual((kode, [p["nama"] for p in d["baru"]]), (200, ["Teliti"]))
        self.assertEqual(self.j("POST", "/api/agent/prompt/impor", {"peran": "perencana", "teks": "{rusak"})[0], 400)

    def test_rute_prompt_chat_tidak_berubah(self):
        self.j("POST", "/api/agent/prompt", {"peran": "perencana", "nama": "A", "isi": "b"})
        self.assertEqual([p["id"] for p in self.j("GET", "/api/prompt")[1]["prompt"]], ["bawaan"])

    def test_berkas_statis_dilayani(self):
        kode, isi = self.req("GET", "/prompt_peran.js")
        self.assertEqual(kode, 200)
        self.assertIn(b"PromptPeran", isi)


class TestJalankanDenganPrompt(DasarServerPeran):
    DASAR = {"teks": "buat halo", "mode": 2, "model_p": "A", "model_e": "B", "maks": 2, "uji": False}

    def jalankan(self, **tambahan):
        """Jalankan lewat HTTP; kembalian: (kode, isi, cfg yang diterima mulai_proses atau None)."""
        diterima = {}

        def palsu(tugas, cfg, *a, **k):
            diterima["cfg"] = cfg
            return "sesi0000"
        with mock.patch.object(server_agent, "mulai_proses", palsu):
            kode, isi = self.req("POST", "/api/agent/jalankan", dict(self.DASAR, **tambahan))
        return kode, isi, diterima.get("cfg")

    def test_id_dijadikan_isi_prompt_di_cfg(self):
        per.tambah_prompt_peran("perencana", "Rencana Rapi", "rencanakan rapi")
        per.tambah_prompt_peran("pemeriksa", "Teliti", "periksa teliti")
        kode, _, cfg = self.jalankan(prompt_peran={"perencana": {"ids": ["rencana-rapi"], "mode": "ganti"},
                                                   "pemeriksa": {"ids": ["teliti"], "mode": "tambah"},
                                                   "pelaksana": {"ids": []}})
        self.assertEqual(kode, 200)
        self.assertEqual(cfg["prompt_peran"], {"perencana": {"mode": "ganti", "teks": "rencanakan rapi", "nama": ["Rencana Rapi"]},
                                               "pemeriksa": {"mode": "tambah", "teks": "periksa teliti", "nama": ["Teliti"]}})

    def test_tanpa_pilihan_cfg_kosong(self):
        kode, _, cfg = self.jalankan()
        self.assertEqual((kode, cfg["prompt_peran"]), (200, {}))

    def test_klien_tidak_bisa_menyelundupkan_teks_langsung(self):
        """Yang diterima server hanya id; kunci "teks" dari klien tidak pernah sampai ke model."""
        kode, _, cfg = self.jalankan(prompt_peran={"perencana": {"ids": [], "teks": "SUSUPAN", "mode": "ganti"}})
        self.assertEqual((kode, cfg["prompt_peran"]), (200, {}))

    def test_pilihan_salah_ditolak_sebelum_proses_dimulai(self):
        for pil in ("x", {"hacker": {"ids": ["a"]}}, {"perencana": {"ids": [5]}}):
            kode, isi, cfg = self.jalankan(prompt_peran=pil)
            self.assertEqual(kode, 400, pil)
            self.assertIsNone(cfg)

    def test_terlalu_panjang_ditolak(self):
        ids = [per.tambah_prompt_peran("penjelas", "P%d" % i, "x" * 2000)["id"] for i in range(4)]
        kode, isi, cfg = self.jalankan(prompt_peran={"penjelas": {"ids": ids}})
        self.assertEqual(kode, 400)
        self.assertIn("terlalu panjang", json.loads(isi)["error"])

    def test_sampai_ke_model_lewat_server_sungguhan(self):
        per.tambah_prompt_peran("pelaksana", "Kode Ringkas", "TULIS-SINGKAT")
        s = StreamCatatSistem()
        self.pasang(LlamaPalsu("A", "B"), s)
        with asisten.AGENT_COND:
            asisten.AGENT.update(sesi=None, id=None, tugas="", events=[], awal=0, aktif=False, mulai=0.0, status=None)
        kode, isi = self.req("POST", "/api/agent/jalankan", dict(self.DASAR, prompt_peran={"pelaksana": {"ids": ["kode-ringkas"], "mode": "tambah"}}))
        self.assertEqual(kode, 200, isi)
        sesi, ev, nomor = json.loads(isi)["sesi"], [], 0
        for _ in range(100):
            k, isi = self.req("GET", "/api/agent/event?sesi=%s&dari=%d&tunggu=5" % (sesi, nomor))
            d = json.loads(isi)
            ev += d["events"]
            nomor = d["next"]
            if d["habis"]:
                break
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertTrue(s.sistem[1].endswith("TULIS-SINGKAT"))
        self.assertEqual(s.sistem[0], tim_prompt.SYSTEM_PERENCANA)
        self.assertEqual([e for e in ev if e["t"] == "mulai"][0]["prompt"]["pelaksana"]["nama"], ["Kode Ringkas"])


# ---------------------------------------------------------------- halaman
class TestHalamanPeran(unittest.TestCase):
    WEB = Path(__file__).resolve().parent.parent / "web"

    def test_html_punya_tempat_prompt_tiap_peran_dan_modul_dimuat_sebelum_agent_js(self):
        html = (self.WEB / "agent.html").read_text(encoding="utf-8")
        for p in PERAN:
            self.assertIn('id="pp_%s"' % p, html)
        self.assertLess(html.index('src="prompt_peran.js"'), html.index('src="agent.js"'))
        self.assertLess(html.index('id="pp_perencana"'), html.index('id="pp_pelaksana"'))
        self.assertLess(html.index('id="pp_pelaksana"'), html.index('id="pp_pemeriksa"'))
        self.assertLess(html.index('id="pp_pemeriksa"'), html.index('id="pp_penjelas"'))
        self.assertNotIn('id="fieldC" hidden', html)                  # Pemeriksa tetap tampil di mode 2 (prompt-nya diatur)

    def test_agent_js_mengirim_dan_menyimpan_pilihan(self):
        js = (self.WEB / "agent.js").read_text(encoding="utf-8")
        for pasti in ("PromptPeran.pasang", "prompt_peran: promptPeranBody()", "pasangPanelPrompt();", "muatPanelPrompt();"):
            self.assertIn(pasti, js)
        self.assertLess(js.index("  muatCfg();\n  pasangPanelPrompt();"), js.index("const bukaDariTautan"))

    def test_serahkan_js_meneruskan_pilihan_ke_serah_terima(self):
        js = (self.WEB / "serahkan.js").read_text(encoding="utf-8")
        self.assertIn("prompt_peran: pp", js)

    def test_modul_memakai_rute_yang_ada(self):
        js = (self.WEB / "prompt_peran.js").read_text(encoding="utf-8")
        for pasti in ("/api/agent/prompt", "/ubah", "/impor", "/hapus", "/ekspor", "(✎)", "(⬇)", "(−)", "+ prompt", "Selesai"):
            self.assertIn(pasti, js)

    def test_logika_panel_dengan_dom_tiruan(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, str(Path(__file__).resolve().parent / "prompt_peran_smoke.js")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "OK")


if __name__ == "__main__":
    unittest.main()
