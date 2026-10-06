"""Pengujian src/tolls.py. Jalankan: python3 -m unittest discover -s tests -v"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import tolls  # noqa: E402


class Ctx:
    """Pengganti ctx dari asisten.py."""

    def __init__(self, auto=True, izin=True, skill="semua"):
        self.auto, self.izin, self.skill = auto, izin, skill
        self.ditanya = []

    def konfirmasi(self, jenis, ringkas, detail=""):
        self.ditanya.append(jenis)
        return self.izin


def jalan(nama, args=None, **kw):
    return tolls.eksekusi(nama, args or {}, Ctx(**kw))


class TestRegistri(unittest.TestCase):
    def test_skema_valid(self):
        for s in tolls.skema("semua"):
            f = s["function"]
            self.assertTrue(f["name"] and f["description"])
            props = f["parameters"]["properties"]
            for wajib in f["parameters"]["required"]:
                self.assertIn(wajib, props, f["name"])

    def test_jumlah_per_mode(self):
        self.assertEqual(tolls.skema("tanpa"), [])
        self.assertEqual(len(tolls.skema("dasar")), 4)
        self.assertEqual(len(tolls.skema("semua")), len(tolls.REGISTRY))
        dasar = {s["function"]["name"] for s in tolls.skema("dasar")}
        self.assertEqual(dasar, {"jalankan_perintah", "baca_file", "tulis_file", "daftar_folder"})

    def test_tool_baru_terdaftar(self):
        for n in ("waktu_sekarang", "bandingkan_file", "ukuran_folder", "cek_sintaks"):
            self.assertIn(n, tolls.REGISTRY)

    def test_mode_membatasi_eksekusi(self):
        self.assertTrue(jalan("hitung", {"ekspresi": "1+1"}, skill="tanpa").startswith("ERROR"))
        self.assertTrue(jalan("hitung", {"ekspresi": "1+1"}, skill="dasar").startswith("ERROR"))
        self.assertIn("= 2", jalan("hitung", {"ekspresi": "1+1"}))

    def test_tool_tak_dikenal_dan_argumen_hilang(self):
        self.assertTrue(jalan("tidak_ada").startswith("ERROR"))
        self.assertIn("wajib", jalan("baca_file"))


class TestHitung(unittest.TestCase):
    def test_hitung(self):
        self.assertIn("= 14", jalan("hitung", {"ekspresi": "2+3*4"}))
        self.assertIn("= 1024", jalan("hitung", {"ekspresi": "2^10"}))
        self.assertIn("= 4", jalan("hitung", {"ekspresi": "sqrt(16)"}))

    def test_hitung_ditolak(self):
        self.assertIn("nol", jalan("hitung", {"ekspresi": "1/0"}))
        self.assertTrue(jalan("hitung", {"ekspresi": "__import__('os')"}).startswith("ERROR"))
        self.assertTrue(jalan("hitung", {"ekspresi": "2**100000"}).startswith("ERROR"))


class TestFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_tulis_baca_edit(self):
        f = self.d / "a.txt"
        self.assertIn("Berhasil", jalan("tulis_file", {"path": str(f), "isi": "satu\ndua\n"}))
        self.assertIn("dua", jalan("baca_file", {"path": str(f)}))
        self.assertIn("Berhasil", jalan("edit_file", {"path": str(f), "lama": "dua", "baru": "tiga"}))
        self.assertIn("tiga", f.read_text())
        self.assertTrue((self.d / "a.txt.bak").exists())

    def test_edit_tidak_unik(self):
        f = self.d / "b.txt"
        f.write_text("x x")
        self.assertIn("2 kali", jalan("edit_file", {"path": str(f), "lama": "x", "baru": "y"}))

    def test_tulis_di_luar_akar_ditolak(self):
        r = jalan("tulis_file", {"path": "/etc/asisten_tes.txt", "isi": "x"})
        self.assertTrue(r.startswith("DITOLAK"))

    def test_tulis_dibatalkan_bila_izin_ditolak(self):
        f = self.d / "c.txt"
        ctx = Ctx(auto=False, izin=False)
        r = tolls.eksekusi("tulis_file", {"path": str(f), "isi": "x"}, ctx)
        self.assertTrue(r.startswith("DIBATALKAN"))
        self.assertFalse(f.exists())

    def test_token_tidak_bisa_dibaca(self):
        f = self.d / ".token"
        f.write_text("rahasia")
        self.assertTrue(jalan("baca_file", {"path": str(f)}).startswith("DITOLAK"))
        self.assertTrue(jalan("cek_sintaks", {"path": str(f)}).startswith("DITOLAK"))

    def test_hapus_selalu_minta_izin(self):
        f = self.d / "d.txt"
        f.write_text("x")
        ctx = Ctx(auto=True, izin=False)   # AUTO aktif, tetap harus bertanya
        r = tolls.eksekusi("hapus", {"path": str(f)}, ctx)
        self.assertTrue(r.startswith("DIBATALKAN"))
        self.assertEqual(ctx.ditanya, ["hapus"])
        self.assertTrue(f.exists())


class TestShellDanGit(unittest.TestCase):
    def test_perintah_berbahaya_diblokir(self):
        self.assertTrue(jalan("jalankan_perintah", {"perintah": "rm -rf /"}).startswith("DITOLAK"))

    def test_perintah_biasa(self):
        self.assertEqual(jalan("jalankan_perintah", {"perintah": "echo halo"}), "exit code 0\nhalo")

    def test_sudo_selalu_tanya(self):
        ctx = Ctx(auto=True, izin=False)
        r = tolls.eksekusi("jalankan_perintah", {"perintah": "sudo true"}, ctx)
        self.assertTrue(r.startswith("DIBATALKAN"))
        self.assertEqual(ctx.ditanya, ["shell"])

    def test_git_berbahaya_ditolak(self):
        with tempfile.TemporaryDirectory() as d:
            for perintah in ("push --force origin main", "reset --hard", "push origin :main"):
                r = jalan("git_tulis", {"path": d, "perintah": perintah})
                self.assertTrue(r.startswith("DITOLAK"), perintah)


class TestToolBaru(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_waktu_sekarang(self):
        self.assertRegex(jalan("waktu_sekarang"), r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_cek_sintaks(self):
        ok, salah = self.d / "ok.py", self.d / "salah.py"
        ok.write_text("x = 1\n")
        salah.write_text("def f(:\n")
        self.assertIn("Sintaks OK", jalan("cek_sintaks", {"path": str(ok)}))
        self.assertIn("SINTAKS SALAH di baris 1", jalan("cek_sintaks", {"path": str(salah)}))
        j = self.d / "x.json"
        j.write_text("{bukan json")
        self.assertIn("TIDAK VALID", jalan("cek_sintaks", {"path": str(j)}))
        j.write_text('{"a": 1}')
        self.assertIn("Sintaks OK", jalan("cek_sintaks", {"path": str(j)}))
        sh = self.d / "s.sh"
        sh.write_text("if then\n")
        self.assertIn("SINTAKS SALAH", jalan("cek_sintaks", {"path": str(sh)}))
        t = self.d / "x.txt"
        t.write_text("x")
        self.assertTrue(jalan("cek_sintaks", {"path": str(t)}).startswith("ERROR"))

    def test_bandingkan_file(self):
        a, b = self.d / "a.txt", self.d / "b.txt"
        a.write_text("satu\ndua\n")
        b.write_text("satu\ntiga\n")
        self.assertEqual(jalan("bandingkan_file", {"file_a": str(a), "file_b": str(a)}),
                         "Kedua file identik.")
        r = jalan("bandingkan_file", {"file_a": str(a), "file_b": str(b)})
        self.assertIn("-dua", r)
        self.assertIn("+tiga", r)

    def test_bandingkan_file_biner(self):
        a, b = self.d / "a.bin", self.d / "b.txt"
        a.write_bytes(b"\0\1\2")
        b.write_text("x")
        self.assertIn("biner", jalan("bandingkan_file", {"file_a": str(a), "file_b": str(b)}))

    def test_ukuran_folder(self):
        (self.d / "besar.txt").write_text("x" * 5000)
        (self.d / "sub").mkdir()
        (self.d / "sub" / "kecil.txt").write_text("y" * 10)
        r = jalan("ukuran_folder", {"path": str(self.d)})
        self.assertIn("2 entri", r)
        self.assertLess(r.index("besar.txt"), r.index("sub/"))   # terbesar di atas
        self.assertTrue(jalan("ukuran_folder", {"path": str(self.d / "tidak_ada")}).startswith("ERROR"))


if __name__ == "__main__":
    unittest.main()
