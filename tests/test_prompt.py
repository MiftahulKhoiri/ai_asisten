"""Pengujian pilihan prompt untuk skill Tanpa: penyimpanan (tambah/hapus/rakit), pemakaian di agen
(prompt sistem kustom, tanpa prompt = murni), rute /api/prompt, dan alurnya dari pilih sesi sampai kirim."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402
import asisten  # noqa: E402
from server import server_prompt as prm  # noqa: E402
from test_batas_dan_taint import Ctx, Palsu, chunk, jalan  # noqa: E402
from test_unggah import DasarServer  # noqa: E402
from test_unggah import setUpModule as _unggah_setUp, tearDownModule as _unggah_tear  # noqa: E402


def setUpModule():
    _unggah_setUp()


def tearDownModule():
    _unggah_tear()


class DasarPrompt(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "prompt"                    # satu prompt = satu berkas di sini
        self.berkas = Path(self._tmp.name) / "prompt.json"            # berkas lama (hanya untuk migrasi)
        for nama, nilai in (("PROMPT_DIR", self.dir), ("PROMPT_FILE", self.berkas)):
            p = mock.patch.object(asisten, nama, nilai)
            p.start()
            self.addCleanup(p.stop)

    def isi(self, nama_berkas):
        return json.loads((self.dir / nama_berkas).read_text(encoding="utf-8"))


class TestPenyimpanan(DasarPrompt):
    def test_awal_hanya_bawaan(self):
        d = prm.daftar_prompt()
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["id"], d[0]["bawaan"]), ("bawaan", True))
        self.assertEqual(d[0]["isi"], agen.SYSTEM_CHAT)
        self.assertFalse(self.dir.exists())                                       # folder baru dibuat saat ada prompt

    def test_tambah_menyimpan_satu_berkas_per_prompt(self):
        a = prm.tambah_prompt("  Penerjemah  ", "Terjemahkan ke Inggris.", "cocok untuk model kecil")
        b = prm.tambah_prompt("Singkat", "Jawab satu kalimat.")
        self.assertEqual((a["id"], b["id"]), ("penerjemah", "singkat"))              # id = nama berkas
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["penerjemah.json", "singkat.json"])
        self.assertEqual(self.isi("penerjemah.json"), {"format": "ai-asisten-prompt", "versi": 1, "nama": "Penerjemah",
                                                      "isi": "Terjemahkan ke Inggris.", "catatan": "cocok untuk model kecil"})
        self.assertNotIn("catatan", self.isi("singkat.json"))                         # catatan kosong tidak ditulis
        self.assertEqual([p["nama"] for p in prm.daftar_prompt()], ["Bawaan (asisten ramah)", "Penerjemah", "Singkat"])
        self.assertEqual(prm.daftar_prompt()[1]["catatan"], "cocok untuk model kecil")
        self.assertFalse(list(self.dir.glob("*.tmp")))                                # penulisan atomik

    def test_nama_menjadi_nama_berkas_yang_aman_dan_unik(self):
        kasus = [("Catatan é", "catatan-e"), ("   ", None), ("!!!", "prompt"), ("Bawaan", "bawaan-prompt"),
                 ("A b", "a-b"), ("a-b", "a-b-2"), ("A  B!", "a-b-3"), ("x" * 40, "x" * 40)]
        for nama, harapan in kasus:
            if harapan is None:
                with self.assertRaises(ValueError):
                    prm.tambah_prompt(nama, "isi")
                continue
            self.assertEqual(prm.tambah_prompt(nama, "isi %s" % nama)["id"], harapan, nama)
        for f in self.dir.iterdir():
            self.assertRegex(f.name, r"^[a-z0-9][a-z0-9_-]{0,39}\.json$")

    def test_berkas_yang_disalin_ke_folder_langsung_muncul(self):
        self.dir.mkdir()
        (self.dir / "buatan-teman.json").write_text(json.dumps(
            {"format": "ai-asisten-prompt", "versi": 1, "nama": "Dari Teman", "isi": "Jawab puitis.", "catatan": "uji di 3B"}), encoding="utf-8")
        (self.dir / "tanpa-format.json").write_text(json.dumps({"nama": "Sederhana", "isi": "Jawab pendek."}), encoding="utf-8")
        d = {p["id"]: p for p in prm.daftar_prompt()}
        self.assertEqual(d["buatan-teman"]["nama"], "Dari Teman")
        self.assertEqual(d["buatan-teman"]["catatan"], "uji di 3B")
        self.assertEqual(d["tanpa-format"]["isi"], "Jawab pendek.")                   # format boleh dihilangkan
        self.assertEqual(prm.rakit(["buatan-teman", "tanpa-format"])[0], "Jawab puitis.\n\nJawab pendek.")   # urut nama

    def test_validasi(self):
        kasus = [("", "isi", "Nama prompt wajib diisi"), ("   ", "isi", "Nama prompt wajib diisi"),
                 ("nama", "  ", "Isi prompt wajib diisi"), ("x" * (asisten.MAKS_NAMA_PROMPT + 1), "isi", "maksimal"),
                 ("nama", "x" * (asisten.MAKS_ISI_PROMPT + 1), "maksimal")]
        for nama, isi, pesan in kasus:
            with self.assertRaises(ValueError) as c:
                prm.tambah_prompt(nama, isi)
            self.assertIn(pesan, str(c.exception))
        prm.tambah_prompt("Satu", "a")
        for kembar in ("satu", "SATU", " Satu ", "bawaan (asisten ramah)"):
            with self.assertRaises(ValueError) as c:
                prm.tambah_prompt(kembar, "b")
            self.assertIn("Sudah ada", str(c.exception))
        self.assertEqual(len(prm.daftar_prompt()), 2)

    def test_batas_jumlah(self):
        with mock.patch.object(asisten, "MAKS_PROMPT", 2):
            prm.tambah_prompt("a", "1")
            prm.tambah_prompt("b", "2")
            with self.assertRaises(ValueError) as c:
                prm.tambah_prompt("c", "3")
            self.assertIn("penuh", str(c.exception))

    def test_berkas_tidak_valid_dilewati_dan_dilaporkan(self):
        self.dir.mkdir()
        isi = lambda **k: json.dumps(dict({"format": "ai-asisten-prompt", "nama": "N", "isi": "I"}, **k))   # noqa: E731
        tulis = {"rusak.json": "{rusak", "larik.json": "[]", "format-lain.json": isi(format="lain"),
                 "tanpa-isi.json": json.dumps({"nama": "N"}), "isi-angka.json": isi(isi=5), "isi-kosong.json": isi(isi="  "),
                 "isi-panjang.json": isi(isi="x" * 4001), "HURUF-BESAR.json": isi(), "bawaan.json": isi(),
                 "besar.json": isi(isi="y" * (asisten.MAKS_BERKAS_PROMPT + 10)), "baik.json": isi(nama="Baik", isi="ok")}
        for nama, teks in tulis.items():
            (self.dir / nama).write_text(teks, encoding="utf-8")
        (self.dir / "catatan.txt").write_text("bukan json", encoding="utf-8")            # bukan *.json: diabaikan diam-diam
        (self.dir / "tautan.json").symlink_to(self.dir / "baik.json")
        self.assertEqual([p["id"] for p in prm.daftar_prompt()], ["bawaan", "baik"])    # hanya yang valid; tidak melempar galat
        lewat = {x["berkas"]: x["alasan"] for x in prm.berkas_diabaikan()}
        self.assertEqual(sorted(lewat), sorted(set(tulis) - {"baik.json"} | {"tautan.json"}))
        self.assertIn("bukan JSON", lewat["rusak.json"])
        self.assertIn("terlalu besar", lewat["besar.json"])
        self.assertIn("nama berkas tidak valid", lewat["HURUF-BESAR.json"])
        self.assertIn("nama berkas tidak valid", lewat["bawaan.json"])
        self.assertIn("format tidak dikenal", lewat["format-lain.json"])
        self.assertIn("bukan berkas biasa", lewat["tautan.json"])
        prm.tambah_prompt("Baru", "isi")                                               # berkas rusak tidak menghalangi menyimpan
        self.assertEqual([p["id"] for p in prm.daftar_prompt()], ["bawaan", "baik", "baru"])

    def test_ubah_mempertahankan_id_dan_nama_berkas(self):
        a = prm.tambah_prompt("Satu", "isi lama")
        b = prm.tambah_prompt("Dua", "isi dua")
        baru = prm.ubah_prompt(a["id"], "  Zebra ", "  isi baru  ", "catatan baru")
        self.assertEqual((baru["id"], baru["nama"], baru["isi"], baru["catatan"], baru["bawaan"]),
                         (a["id"], "Zebra", "isi baru", "catatan baru", False))
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["dua.json", "satu.json"])   # nama berkas tidak berubah
        self.assertEqual(self.isi("satu.json")["nama"], "Zebra")
        self.assertEqual(self.isi("satu.json")["catatan"], "catatan baru")
        self.assertEqual([p["id"] for p in prm.daftar_prompt()], ["bawaan", b["id"], a["id"]])    # daftar urut nama: Dua, Zebra
        self.assertEqual(prm.ubah_prompt(a["id"], "Zebra", "isi baru")["catatan"], "catatan baru")  # catatan None = tidak diubah
        self.assertEqual(prm.ubah_prompt(a["id"], "Zebra", "isi baru", "")["catatan"], "")          # string kosong = dihapus
        self.assertNotIn("catatan", self.isi("satu.json"))
        self.assertFalse(list(self.dir.glob("*.tmp")))

    def test_ubah_boleh_mempertahankan_nama_sendiri_atau_hanya_ganti_huruf_besar(self):
        a = prm.tambah_prompt("Satu", "x")
        self.assertEqual(prm.ubah_prompt(a["id"], "Satu", "y")["isi"], "y")           # nama sama dengan dirinya sendiri
        self.assertEqual(prm.ubah_prompt(a["id"], "SATU", "y")["nama"], "SATU")

    def test_ubah_ditolak(self):
        a = prm.tambah_prompt("Satu", "x")
        prm.tambah_prompt("Dua", "y")
        with self.assertRaises(ValueError) as c:
            prm.ubah_prompt("bawaan", "Baru", "isi")
        self.assertIn("tidak bisa diubah", str(c.exception))
        for nama, isi, pesan in (("", "isi", "Nama"), ("n", "", "Isi"), ("x" * 41, "i", "maksimal"), ("n", "x" * 4001, "maksimal"),
                                 ("dua", "i", "Sudah ada"), ("Bawaan (asisten ramah)", "i", "Sudah ada")):
            with self.assertRaises(ValueError) as c:
                prm.ubah_prompt(a["id"], nama, isi)
            self.assertIn(pesan, str(c.exception))
        self.assertIsNone(prm.ubah_prompt("p00000000", "n", "i"))                      # tidak ada
        self.assertEqual({p["id"]: p["isi"] for p in prm.daftar_prompt()}[a["id"]], "x")   # yang gagal tidak mengubah apa pun

    def test_hapus_menghapus_berkasnya(self):
        a = prm.tambah_prompt("Satu", "a")
        self.assertTrue((self.dir / "satu.json").is_file())
        with self.assertRaises(ValueError):
            prm.hapus_prompt("bawaan")
        for tidak_ada in ("p00000000", "../x", "", "satu.json", "SATU", None):
            self.assertFalse(prm.hapus_prompt(tidak_ada), tidak_ada)
        self.assertTrue((self.dir / "satu.json").is_file())
        self.assertTrue(prm.hapus_prompt(a["id"]))
        self.assertFalse((self.dir / "satu.json").exists())
        self.assertEqual([p["id"] for p in prm.daftar_prompt()], ["bawaan"])
        self.assertFalse(prm.hapus_prompt(a["id"]))                                   # sudah tidak ada

    def test_hapus_tidak_mengikuti_symlink(self):
        self.dir.mkdir()
        luar = Path(self._tmp.name) / "luar.json"
        luar.write_text("{}", encoding="utf-8")
        (self.dir / "tautan.json").symlink_to(luar)
        self.assertFalse(prm.hapus_prompt("tautan"))
        self.assertTrue(luar.exists())

    def test_berlaku_hanya_untuk_skill_tanpa_tanpa_akses_sistem(self):
        self.assertTrue(prm.berlaku(("tanpa",)))
        self.assertTrue(prm.berlaku(("tanpa", "web", "kritis")))
        for skill in (("tanpa", "dasar"), ("tanpa", "kompleks"), ("web",), ("kritis",), ("kompleks",), (), None):
            self.assertFalse(prm.berlaku(skill), skill)


class TestMigrasi(DasarPrompt):
    def test_prompt_json_lama_dipecah_jadi_berkas_dan_dicadangkan(self):
        self.berkas.write_text(json.dumps({"prompt": [
            {"id": "p1a2b3c4d", "nama": "Penerjemah", "isi": "Terjemahkan."},
            {"id": "p00000002", "nama": "Singkat", "isi": "Jawab satu kalimat."},
            {"id": "p00000003", "nama": "singkat", "isi": "kembar"},                    # nama kembar: dilewati
            {"id": "p00000004", "nama": "", "isi": "tanpa nama"}, "bukan-objek"]}), encoding="utf-8")
        d = prm.daftar_prompt()
        self.assertEqual([p["nama"] for p in d], ["Bawaan (asisten ramah)", "Penerjemah", "Singkat"])
        self.assertEqual(sorted(f.name for f in self.dir.iterdir()), ["penerjemah.json", "singkat.json"])
        self.assertFalse(self.berkas.exists())
        self.assertTrue(Path(str(self.berkas) + ".migrasi").is_file())                 # cadangan tetap ada
        self.assertEqual(prm.daftar_prompt(), d)                                       # idempoten
        self.assertEqual(self.isi("singkat.json")["isi"], "Jawab satu kalimat.")

    def test_migrasi_tidak_menimpa_berkas_yang_sudah_ada(self):
        prm.tambah_prompt("Penerjemah", "isi baru")
        self.berkas.write_text(json.dumps({"prompt": [{"id": "p0000000a", "nama": "Penerjemah", "isi": "isi lama"}]}), encoding="utf-8")
        prm.daftar_prompt()
        self.assertEqual(self.isi("penerjemah.json")["isi"], "isi baru")
        self.assertEqual(len(list(self.dir.glob("*.json"))), 1)

    def test_prompt_json_rusak_tidak_menggagalkan_apa_pun(self):
        self.berkas.write_text("{rusak", encoding="utf-8")
        self.assertEqual(len(prm.daftar_prompt()), 1)
        self.assertTrue(Path(str(self.berkas) + ".migrasi").is_file())

    def test_tambah_pertama_kali_memigrasikan_dulu(self):
        self.berkas.write_text(json.dumps({"prompt": [{"id": "p0000000a", "nama": "Lama", "isi": "x"}]}), encoding="utf-8")
        prm.tambah_prompt("Baru", "y")
        self.assertEqual([p["nama"] for p in prm.daftar_prompt()], ["Bawaan (asisten ramah)", "Baru", "Lama"])


class TestBerbagi(DasarPrompt):
    def test_ekspor_isi_berkas_siap_bagikan(self):
        prm.tambah_prompt("Penerjemah", "Terjemahkan.", "uji di 3B")
        self.assertEqual(prm.ekspor("penerjemah"), {"format": "ai-asisten-prompt", "versi": 1, "nama": "Penerjemah",
                                                    "isi": "Terjemahkan.", "catatan": "uji di 3B"})
        for tidak_ada in ("bawaan", "tidak-ada", "../x", ""):
            self.assertIsNone(prm.ekspor(tidak_ada), tidak_ada)

    def test_bagikan_ke_instalasi_lain_bolak_balik(self):
        """Ekspor dari satu folder lalu impor ke folder lain menghasilkan prompt yang sama."""
        prm.tambah_prompt("Penerjemah", "Terjemahkan ke Inggris. {waktu}", "uji di 3B")
        teks = json.dumps(prm.ekspor("penerjemah"), ensure_ascii=False)
        lain = Path(self._tmp.name) / "instalasi-lain"
        with mock.patch.object(asisten, "PROMPT_DIR", lain):
            h = prm.impor(teks)
            self.assertEqual(h["dilewati"], [])
            self.assertEqual([(p["id"], p["nama"], p["isi"], p["catatan"]) for p in h["baru"]],
                             [("penerjemah", "Penerjemah", "Terjemahkan ke Inggris. {waktu}", "uji di 3B")])
            self.assertEqual((lain / "penerjemah.json").read_text(encoding="utf-8"),
                             (self.dir / "penerjemah.json").read_text(encoding="utf-8"))   # berkas identik

    def test_impor_satu_daftar_dan_bundel(self):
        satu = prm.impor(json.dumps({"nama": "A", "isi": "isi a"}))
        self.assertEqual([p["id"] for p in satu["baru"]], ["a"])
        daftar = prm.impor(json.dumps([{"nama": "B", "isi": "isi b"}, {"nama": "C", "isi": "isi c"}]))
        self.assertEqual([p["id"] for p in daftar["baru"]], ["b", "c"])
        bundel = prm.impor(json.dumps({"format": "ai-asisten-prompt", "prompt": [{"nama": "D", "isi": "isi d"}]}))
        self.assertEqual([p["id"] for p in bundel["baru"]], ["d"])
        self.assertEqual([p["id"] for p in prm.daftar_prompt()], ["bawaan", "a", "b", "c", "d"])

    def test_impor_isi_sama_dilewati_nama_sama_diberi_akhiran(self):
        prm.tambah_prompt("Penerjemah", "Terjemahkan.")
        h = prm.impor(json.dumps([{"nama": "Lain nama", "isi": "Terjemahkan."},                  # isi sama persis
                                  {"nama": "penerjemah", "isi": "Isi berbeda"},                  # nama sama, isi beda
                                  {"nama": "Penerjemah", "isi": "Isi berbeda lagi"}]))
        self.assertEqual([x["alasan"] for x in h["dilewati"]], ["sudah ada (isinya sama)"])
        self.assertEqual([p["nama"] for p in h["baru"]], ["penerjemah (2)", "Penerjemah (3)"])
        self.assertEqual([p["id"] for p in h["baru"]], ["penerjemah-2", "penerjemah-3"])
        self.assertEqual(prm.impor(json.dumps({"nama": "Bawaan (asisten ramah)", "isi": "x"}))["baru"][0]["nama"],
                         "Bawaan (asisten ramah) (2)"[:asisten.MAKS_NAMA_PROMPT])

    def test_impor_melaporkan_butir_yang_tidak_valid(self):
        h = prm.impor(json.dumps([{"nama": "", "isi": "x"}, {"nama": "Tanpa isi"}, "teks", 5, {"nama": "x" * 41, "isi": "y"},
                                  {"nama": "Baik", "isi": "ok", "catatan": "c" * 201}, {"nama": "Bagus", "isi": "ok2", "catatan": 7}]))
        self.assertEqual([p["nama"] for p in h["baru"]], ["Bagus"])                              # catatan bukan teks: diabaikan
        self.assertEqual(len(h["dilewati"]), 6)
        self.assertEqual(h["dilewati"][5]["alasan"], "Catatan maksimal 200 karakter")

    def test_impor_ditolak(self):
        for salah in ("{rusak", "", "123", '"teks"', json.dumps({"format": "lain", "nama": "a", "isi": "b"}),
                      json.dumps({"tidak": "dikenal"}), "x" * (asisten.MAKS_IMPOR_PROMPT + 1)):
            with self.assertRaises(ValueError, msg=salah[:30]):
                prm.impor(salah)
        self.assertFalse(self.dir.exists())

    def test_impor_menghormati_batas_jumlah(self):
        with mock.patch.object(asisten, "MAKS_PROMPT", 2):
            h = prm.impor(json.dumps([{"nama": n, "isi": "isi " + n} for n in "abcd"]))
        self.assertEqual(len(h["baru"]), 2)
        self.assertEqual([x["alasan"] for x in h["dilewati"]], ["melebihi batas", "melebihi batas"])


class TestLokasiFolder(unittest.TestCase):
    def jalankan(self, env):
        import os
        import subprocess
        e = {k: v for k, v in os.environ.items() if k != "ASISTEN_PROMPT_DIR"}
        e.update(env)
        r = subprocess.run([sys.executable, "-c", "from server import server_config as c; print(c.PROMPT_DIR)"],
                           capture_output=True, text=True, cwd=str(Path(__file__).resolve().parent.parent), env=e, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_folder_bawaan_dan_dari_lingkungan(self):
        root = Path(__file__).resolve().parent.parent
        self.assertEqual(self.jalankan({}), str(root / "prompt"))
        self.assertEqual(self.jalankan({"ASISTEN_PROMPT_DIR": "/tmp/prompt-bersama"}), "/tmp/prompt-bersama")


class TestRakit(DasarPrompt):
    def setUp(self):
        super().setUp()
        self.a = prm.tambah_prompt("Penerjemah", "Terjemahkan ke Inggris.")["id"]
        self.b = prm.tambah_prompt("Singkat", "Jawab satu kalimat.")["id"]

    def test_tidak_ada_pilihan_berarti_bawaan(self):
        self.assertEqual(prm.rakit(None), (None, ["Bawaan (asisten ramah)"]))

    def test_hanya_bawaan_memakai_jalur_lama(self):
        self.assertEqual(prm.rakit(["bawaan"]), (None, ["Bawaan (asisten ramah)"]))

    def test_tanpa_pilihan_adalah_murni(self):
        self.assertEqual(prm.rakit([]), ("", []))

    def test_satu_dan_beberapa_prompt_digabung_menurut_urutan_daftar(self):
        self.assertEqual(prm.rakit([self.a]), ("Terjemahkan ke Inggris.", ["Penerjemah"]))
        self.assertEqual(prm.rakit([self.b, self.a]), ("Terjemahkan ke Inggris.\n\nJawab satu kalimat.", ["Penerjemah", "Singkat"]))
        teks, nama = prm.rakit(["bawaan", self.b])
        self.assertEqual(teks, agen.SYSTEM_CHAT + "\n\nJawab satu kalimat.")
        self.assertEqual(nama, ["Bawaan (asisten ramah)", "Singkat"])

    def test_id_yang_sudah_dihapus_dilewati_dan_tidak_diam_diam_menjadi_murni(self):
        prm.hapus_prompt(self.a)
        self.assertEqual(prm.rakit([self.a, self.b]), ("Jawab satu kalimat.", ["Singkat"]))
        self.assertEqual(prm.rakit([self.a]), (None, ["Bawaan (asisten ramah)"]))   # semuanya hilang -> bawaan
        self.assertEqual(prm.rakit(["p00000000"]), (None, ["Bawaan (asisten ramah)"]))

    def test_rapikan_pilihan(self):
        self.assertIsNone(prm.rapikan_pilihan(None))
        self.assertEqual(prm.rapikan_pilihan([self.b, "bawaan", "p00000000", self.a]), ["bawaan", self.a, self.b])
        self.assertEqual(prm.rapikan_pilihan([]), [])
        for salah in ("bawaan", [1], {"a": 1}, [None]):
            with self.assertRaises(ValueError):
                prm.rapikan_pilihan(salah)


class TestPromptSistem(unittest.TestCase):
    def test_buat_system_bawaan_tidak_berubah(self):
        a = agen.buat_system("", ("tanpa",))
        self.assertEqual(a, agen.buat_system("", ("tanpa",), None))
        self.assertIn("Indonesia", a)
        self.assertRegex(a, r"\d{4}")                                             # tanggal terisi

    def test_prompt_kustom_dengan_waktu(self):
        teks = agen.buat_system("", ("tanpa",), "Kamu penerjemah. Sekarang {waktu}. Contoh {abc} tetap.")
        self.assertTrue(teks.startswith("Kamu penerjemah. Sekarang "))
        self.assertNotIn("{waktu}", teks)
        self.assertIn("{abc}", teks)                                              # kurung lain tidak disentuh
        self.assertNotIn(agen.SYSTEM_CHAT[:60], teks)

    def test_murni_tidak_punya_prompt_dasar_tetapi_skill_web_tetap_ikut(self):
        self.assertEqual(agen.buat_system("", ("tanpa",), "").strip(), "")
        web = agen.buat_system("", ("tanpa", "web"), "")
        self.assertIn(agen.PROMPT_WEB.strip()[:40], web)
        self.assertNotIn(agen.SYSTEM_CHAT[:60], web)

    def test_prompt_dasar_diabaikan_untuk_skill_dengan_akses_sistem(self):
        for skill in (("dasar",), ("kompleks",), ("tanpa", "kompleks")):
            self.assertEqual(agen.buat_system("", skill, "ABAIKAN INI"), agen.buat_system("", skill))
            self.assertNotIn("ABAIKAN INI", agen.buat_system("", skill, "ABAIKAN INI"))

    def test_dasar_dari_hanya_menerima_teks(self):
        self.assertIsNone(agen.dasar_dari(object()))
        self.assertEqual(agen.dasar_dari(mock.Mock(prompt_dasar="x")), "x")
        self.assertEqual(agen.dasar_dari(mock.Mock(prompt_dasar="")), "")
        self.assertIsNone(agen.dasar_dari(mock.Mock()))                           # atribut tiruan bukan teks
        self.assertIsNone(agen.dasar_dari(mock.Mock(prompt_dasar=5)))


class TestGiliranDenganPrompt(unittest.TestCase):
    def kirim(self, dasar):
        ctx = Ctx(("tanpa",))
        if dasar is not False:
            ctx.prompt_dasar = dasar
        palsu = Palsu([chunk("halo")])
        jalan(("tanpa",), [{"role": "user", "content": "hai"}], palsu, ctx)
        return palsu.panggilan[0]["pesan"]

    def test_bawaan(self):
        pesan = self.kirim(False)
        self.assertEqual(pesan[0]["role"], "system")
        self.assertIn("Indonesia", pesan[0]["content"])
        self.assertEqual(pesan[-1], {"role": "user", "content": "hai"})

    def test_prompt_pilihan(self):
        pesan = self.kirim("Kamu penerjemah.")
        self.assertEqual(pesan[0], {"role": "system", "content": "Kamu penerjemah."})
        self.assertEqual(len(pesan), 2)

    def test_murni_tanpa_pesan_system_sama_sekali(self):
        pesan = self.kirim("")
        self.assertEqual(pesan, [{"role": "user", "content": "hai"}])
        self.assertTrue(all(m["role"] != "system" for m in pesan))

    def test_murni_tidak_menyisipkan_ringkasan_riwayat(self):
        ctx = Ctx(("tanpa",))
        ctx.prompt_dasar = ""
        palsu = Palsu([chunk("halo")])
        asli_s, asli_g = agen.stream_chat, agen.GERBANG
        agen.stream_chat, agen.GERBANG = palsu, False
        try:
            list(agen.giliran([{"role": "user", "content": "hai"}], "m", ctx, None))     # server memberi memori=None
        finally:
            agen.stream_chat, agen.GERBANG = asli_s, asli_g
        self.assertTrue(all(m["role"] != "system" for m in palsu.panggilan[0]["pesan"]))


# ------------------------------------------------------------------ rute HTTP dan sesi
class DasarServerPrompt(DasarServer):
    def setUp(self):
        super().setUp()
        self.dir = Path(self._tmp.name) / "prompt"
        for nama, nilai in (("PROMPT_DIR", self.dir), ("PROMPT_FILE", Path(self._tmp.name) / "prompt.json")):
            p = mock.patch.object(asisten, nama, nilai)
            p.start()
            self.addCleanup(p.stop)
        q = mock.patch.object(asisten, "muat_model", lambda nama: None)
        q.start()
        self.addCleanup(q.stop)

    def daftar(self):
        return json.loads(self.req("GET", "/api/prompt")[1])["prompt"]

    def pilih(self, **tambahan):
        return self.req("POST", "/api/model/pilih", dict({"model": "A", "skill": ["tanpa"]}, **tambahan))

    def sesi_siap(self):
        with asisten.S_LOCK:
            asisten.S["status"] = "siap"


class TestRutePrompt(DasarServerPrompt):
    def test_wajib_token(self):
        self.assertEqual(self.req("GET", "/api/prompt", token=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "a", "isi": "b"}, token=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {"id": "p00000000"}, token=False)[0], 401)

    def test_daftar_tambah_hapus(self):
        d = json.loads(self.req("GET", "/api/prompt")[1])
        self.assertEqual(d["bawaan"], "bawaan")
        self.assertEqual([p["id"] for p in d["prompt"]], ["bawaan"])
        kode, isi = self.req("POST", "/api/prompt", {"nama": "Penerjemah", "isi": "Terjemahkan ke Inggris."})
        j = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual([p["nama"] for p in j["prompt"]], ["Bawaan (asisten ramah)", "Penerjemah"])
        self.assertEqual(j["baru"]["nama"], "Penerjemah")
        self.assertEqual([p["nama"] for p in self.daftar()], ["Bawaan (asisten ramah)", "Penerjemah"])   # tersimpan
        kode, isi = self.req("POST", "/api/prompt/hapus", {"id": j["baru"]["id"]})
        self.assertEqual((kode, json.loads(isi)["ok"]), (200, True))
        self.assertEqual(len(self.daftar()), 1)

    def test_penolakan(self):
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "", "isi": "b"})[0], 400)
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "a", "isi": ""})[0], 400)
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "a" * 41, "isi": "b"})[0], 400)
        self.req("POST", "/api/prompt", {"nama": "a", "isi": "b"})
        kode, isi = self.req("POST", "/api/prompt", {"nama": "A", "isi": "c"})
        self.assertEqual(kode, 400)
        self.assertIn("Sudah ada", json.loads(isi)["error"])
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {"id": "bawaan"})[0], 400)
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {"id": "p00000000"})[0], 404)
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {})[0], 404)

    def test_ubah(self):
        a = json.loads(self.req("POST", "/api/prompt", {"nama": "Satu", "isi": "lama"})[1])["baru"]["id"]
        kode, isi = self.req("POST", "/api/prompt/ubah", {"id": a, "nama": "Satu B", "isi": "baru"})
        j = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual((j["baru"]["id"], j["baru"]["nama"], j["baru"]["isi"]), (a, "Satu B", "baru"))
        self.assertEqual([p["nama"] for p in j["prompt"]], ["Bawaan (asisten ramah)", "Satu B"])
        self.assertEqual(self.daftar()[1]["isi"], "baru")

    def test_ubah_penolakan(self):
        a = json.loads(self.req("POST", "/api/prompt", {"nama": "Satu", "isi": "x"})[1])["baru"]["id"]
        self.req("POST", "/api/prompt", {"nama": "Dua", "isi": "y"})
        self.assertEqual(self.req("POST", "/api/prompt/ubah", {"id": a, "nama": "a", "isi": "b"}, token=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/prompt/ubah", {"id": "bawaan", "nama": "a", "isi": "b"})[0], 400)
        self.assertEqual(self.req("POST", "/api/prompt/ubah", {"id": a, "nama": "", "isi": "b"})[0], 400)
        kode, isi = self.req("POST", "/api/prompt/ubah", {"id": a, "nama": "dua", "isi": "b"})
        self.assertEqual(kode, 400)
        self.assertIn("Sudah ada", json.loads(isi)["error"])
        self.assertEqual(self.req("POST", "/api/prompt/ubah", {"id": "p00000000", "nama": "a", "isi": "b"})[0], 404)
        self.assertEqual(self.req("POST", "/api/prompt/ubah", {"nama": "a", "isi": "b"})[0], 404)

    def test_catatan_lewat_tambah_dan_ubah(self):
        j = json.loads(self.req("POST", "/api/prompt", {"nama": "Gaya", "isi": "formal", "catatan": "uji di 1B"})[1])
        self.assertEqual(j["baru"]["catatan"], "uji di 1B")
        self.assertEqual(json.loads((self.dir / "gaya.json").read_text(encoding="utf-8"))["catatan"], "uji di 1B")
        j = json.loads(self.req("POST", "/api/prompt/ubah", {"id": "gaya", "nama": "Gaya", "isi": "santai"})[1])
        self.assertEqual(j["baru"]["catatan"], "uji di 1B")                            # tidak disebut = tidak diubah
        j = json.loads(self.req("POST", "/api/prompt/ubah", {"id": "gaya", "nama": "Gaya", "isi": "santai", "catatan": ""})[1])
        self.assertEqual(j["baru"]["catatan"], "")
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "x", "isi": "y", "catatan": "c" * 201})[0], 400)

    def test_daftar_melaporkan_berkas_yang_dilewati(self):
        self.dir.mkdir()
        (self.dir / "rusak.json").write_text("{rusak", encoding="utf-8")
        (self.dir / "baik.json").write_text(json.dumps({"nama": "Baik", "isi": "ok"}), encoding="utf-8")
        d = json.loads(self.req("GET", "/api/prompt")[1])
        self.assertEqual([p["id"] for p in d["prompt"]], ["bawaan", "baik"])
        self.assertEqual([(x["berkas"], x["alasan"]) for x in d["abaikan"]], [("rusak.json", "bukan JSON yang valid")])

    def test_ekspor_mengunduh_berkas_json(self):
        import urllib.request
        self.req("POST", "/api/prompt", {"nama": "Penerjemah", "isi": "Terjemahkan.", "catatan": "uji"})
        r = urllib.request.Request("http://127.0.0.1:%d/api/prompt/ekspor?id=penerjemah" % self.port)
        r.add_header("Authorization", "Bearer " + self.TOKEN)
        with urllib.request.urlopen(r, timeout=10) as resp:
            self.assertEqual(resp.headers["Content-Type"], "application/json; charset=utf-8")
            self.assertEqual(resp.headers["Content-Disposition"], 'attachment; filename="penerjemah.json"')
            d = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(d, {"format": "ai-asisten-prompt", "versi": 1, "nama": "Penerjemah", "isi": "Terjemahkan.", "catatan": "uji"})
        self.assertEqual(self.req("GET", "/api/prompt/ekspor?id=penerjemah", token=False)[0], 401)
        for id_ in ("bawaan", "tidak-ada", "..%2Fx", ""):
            self.assertEqual(self.req("GET", "/api/prompt/ekspor?id=" + id_)[0], 404, id_)

    def test_impor(self):
        teks = json.dumps({"format": "ai-asisten-prompt", "versi": 1, "nama": "Dari Teman", "isi": "Jawab puitis.", "catatan": "uji"})
        kode, isi = self.req("POST", "/api/prompt/impor", {"teks": teks})
        j = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual([p["id"] for p in j["baru"]], ["dari-teman"])
        self.assertEqual([p["id"] for p in j["prompt"]], ["bawaan", "dari-teman"])
        self.assertTrue((self.dir / "dari-teman.json").is_file())
        j = json.loads(self.req("POST", "/api/prompt/impor", {"teks": teks})[1])             # kedua kali: isi sama
        self.assertEqual((j["baru"], j["dilewati"][0]["alasan"]), ([], "sudah ada (isinya sama)"))

    def test_impor_penolakan(self):
        self.assertEqual(self.req("POST", "/api/prompt/impor", {"teks": "{rusak"}, token=False)[0], 401)
        for body in ({"teks": "{rusak"}, {"teks": json.dumps({"format": "lain"})}, {"teks": ""}, {}, {"teks": 5}):
            self.assertEqual(self.req("POST", "/api/prompt/impor", body)[0], 400, body)

    def test_berkas_statis(self):
        for p, ket in (("/prompt.js", b"PromptPilih"),):
            kode, isi = self.req("GET", p, token=False)
            self.assertEqual(kode, 200)
            self.assertIn(ket, isi)


class TestSesiDenganPrompt(DasarServerPrompt):
    def buat(self, nama, isi):
        return json.loads(self.req("POST", "/api/prompt", {"nama": nama, "isi": isi})[1])["baru"]["id"]

    def test_pilihan_disimpan_di_sesi_dan_tampil_di_status(self):
        a = self.buat("Penerjemah", "Terjemahkan.")
        self.assertEqual(self.pilih(prompt=[a, "bawaan", "p00000000"])[0], 200)
        self.assertEqual(asisten.S["prompt"], ["bawaan", a])                         # id tak dikenal dibuang, urut daftar
        self.sesi_siap()
        st = json.loads(self.req("GET", "/api/status")[1])
        self.assertEqual(st["prompt"], ["Bawaan (asisten ramah)", "Penerjemah"])
        self.assertEqual(st["prompt_id"], ["bawaan", a])

    def test_tanpa_prompt_di_status_menjadi_daftar_kosong_murni(self):
        self.assertEqual(self.pilih(prompt=[])[0], 200)
        self.sesi_siap()
        self.assertEqual(json.loads(self.req("GET", "/api/status")[1])["prompt"], [])

    def test_tidak_menyebut_prompt_berarti_bawaan(self):
        self.pilih()
        self.sesi_siap()
        self.assertIsNone(asisten.S["prompt"])
        self.assertEqual(json.loads(self.req("GET", "/api/status")[1])["prompt"], ["Bawaan (asisten ramah)"])

    def test_status_tidak_memuat_prompt_untuk_skill_dengan_akses_sistem(self):
        self.pilih(skill=["kompleks"], prompt=["bawaan"])
        self.sesi_siap()
        self.assertIsNone(json.loads(self.req("GET", "/api/status")[1])["prompt"])

    def test_pilihan_tidak_valid_ditolak(self):
        for salah in ("bawaan", [1], {"a": 1}):
            self.assertEqual(self.pilih(prompt=salah)[0], 400, salah)


class TestKirimDenganPrompt(DasarServerPrompt):
    def kirim_dan_tangkap(self, skill, prompt, teks="halo"):
        self.assertEqual(self.pilih(skill=skill, **({"prompt": prompt} if prompt is not None else {}))[0], 200)
        self.sesi_siap()
        cid = json.loads(self.req("POST", "/api/chat/baru", {})[1])["id"]
        tangkap = {}

        def palsu(riwayat, model, ctx, memori=None):
            tangkap.update(dasar=agen.dasar_dari(ctx), memori=memori)
            yield {"t": "token", "d": "ok"}
        with mock.patch.object(agen, "giliran", palsu):
            kode, isi = self.req("POST", "/api/kirim", {"id": cid, "teks": teks})
        self.assertEqual(kode, 200, isi)
        return tangkap

    def test_bawaan_memakai_jalur_lama(self):
        t = self.kirim_dan_tangkap(["tanpa"], None)
        self.assertIsNone(t["dasar"])
        self.assertIsNotNone(t["memori"])                                           # ringkasan otomatis tetap ada

    def test_prompt_pilihan_menjadi_prompt_dasar(self):
        a = json.loads(self.req("POST", "/api/prompt", {"nama": "Penerjemah", "isi": "Terjemahkan {waktu}."})[1])["baru"]["id"]
        t = self.kirim_dan_tangkap(["tanpa"], [a])
        self.assertEqual(t["dasar"], "Terjemahkan {waktu}.")                         # {waktu} diganti saat prompt dibentuk
        self.assertIsNotNone(t["memori"])

    def test_murni_tanpa_prompt_dan_tanpa_memori(self):
        t = self.kirim_dan_tangkap(["tanpa"], [])
        self.assertEqual(t["dasar"], "")
        self.assertIsNone(t["memori"])                                              # tidak ada ringkasan yang disisipkan

    def test_skill_dengan_akses_sistem_tidak_memakai_prompt_pilihan(self):
        t = self.kirim_dan_tangkap(["tanpa", "kompleks"], [])
        self.assertIsNone(t["dasar"])
        self.assertIsNotNone(t["memori"])

    def test_prompt_yang_diubah_saat_sesi_berjalan_berlaku_di_pesan_berikutnya(self):
        a = json.loads(self.req("POST", "/api/prompt", {"nama": "Gaya", "isi": "Jawab formal."})[1])["baru"]["id"]
        self.assertEqual(self.pilih(prompt=[a])[0], 200)
        self.sesi_siap()
        cid = json.loads(self.req("POST", "/api/chat/baru", {})[1])["id"]
        dasar = []

        def palsu(riwayat, model, ctx, memori=None):
            dasar.append(agen.dasar_dari(ctx))
            yield {"t": "token", "d": "ok"}
        with mock.patch.object(agen, "giliran", palsu):
            self.req("POST", "/api/kirim", {"id": cid, "teks": "satu"})
            self.req("POST", "/api/prompt/ubah", {"id": a, "nama": "Gaya", "isi": "Jawab santai."})
            self.req("POST", "/api/kirim", {"id": cid, "teks": "dua"})
        self.assertEqual(dasar, ["Jawab formal.", "Jawab santai."])
        self.assertEqual(asisten.S["prompt"], [a])                                  # pilihan sesi tetap

    def test_prompt_yang_dihapus_saat_sesi_berjalan_kembali_ke_bawaan(self):
        a = json.loads(self.req("POST", "/api/prompt", {"nama": "Sementara", "isi": "x"})[1])["baru"]["id"]
        self.assertEqual(self.pilih(prompt=[a])[0], 200)
        self.sesi_siap()
        self.req("POST", "/api/prompt/hapus", {"id": a})
        cid = json.loads(self.req("POST", "/api/chat/baru", {})[1])["id"]
        tangkap = {}

        def palsu(riwayat, model, ctx, memori=None):
            tangkap["dasar"] = agen.dasar_dari(ctx)
            yield {"t": "token", "d": "ok"}
        with mock.patch.object(agen, "giliran", palsu):
            self.req("POST", "/api/kirim", {"id": cid, "teks": "halo"})
        self.assertIsNone(tangkap["dasar"])


class TestHalamanPrompt(unittest.TestCase):
    WEB = Path(__file__).resolve().parent.parent / "web"

    def test_html_punya_panel_dan_modul_dimuat_sebelum_index(self):
        html = (self.WEB / "index.html").read_text(encoding="utf-8")
        for pasti in ('id="promptBox"', 'id="btnPromptBaru"', 'id="promptForm"', 'id="promptNama"', 'id="promptIsi"',
                      'id="btnPromptSimpan"', 'id="btnPromptBatal"', 'id="promptFormJudul"', 'id="promptList"', 'id="promptKet"', 'id="btnPromptSelesai"',
                      'id="promptRingkas"', 'id="btnPromptUbah"', 'id="langkahModel"', "List prompt", "+ prompt"):
            self.assertIn(pasti, html)
        self.assertLess(html.index('src="prompt.js"'), html.index('src="index.js"'))
        self.assertLess(html.index('id="skillBox"'), html.index('id="promptBox"'))      # skill dulu, lalu prompt
        self.assertLess(html.index('id="promptBox"'), html.index('id="langkahModel"'))  # lalu model dan Mulai
        self.assertLess(html.index('id="btnPromptSimpan"'), html.index('id="promptList"'))
        self.assertLess(html.index('id="promptList"'), html.index('id="btnPromptSelesai"'))   # Selesai paling bawah

    def test_prompt_js_punya_tombol_ubah_dan_rute_ubah(self):
        js = (self.WEB / "prompt.js").read_text(encoding="utf-8")
        for pasti in ("(✎)", "/api/prompt/ubah", "'salin'", "btnPromptBatal"):
            self.assertIn(pasti, js)

    def test_index_js_memakai_modul_dan_mengirim_prompt(self):
        js = (self.WEB / "index.js").read_text(encoding="utf-8")
        for pasti in ("PromptPilih.pasang", "prm.atur(promptAktif())", "prompt: (prm && promptAktif()) ? prm.ids() : undefined"):
            self.assertIn(pasti, js)

    def test_logika_panel_dengan_dom_tiruan(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, str(Path(__file__).resolve().parent / "prompt_smoke.js")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "OK")


if __name__ == "__main__":
    unittest.main()
