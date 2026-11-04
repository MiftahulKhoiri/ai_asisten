"""Tes kotak uji (tim/tim_kotak.py): environment bersih, batas sumber daya, jaringan, keluaran."""
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tim import tim_cek, tim_kotak  # noqa: E402


class DasarKotak(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)

    def jalan(self, kode_py, timeout=10, env=None):
        (self.dir / "p.py").write_text(textwrap.dedent(kode_py), encoding="utf-8")
        with mock.patch.dict(os.environ, env or {}):
            return tim_kotak.jalankan_terkurung([sys.executable, "p.py"], str(self.dir), timeout)


class TestEnvironment(DasarKotak):
    def test_rahasia_dari_proses_server_tidak_terbawa(self):
        kode, out = self.jalan("""
            import os
            print("KEY=" + str(os.environ.get("LLAMA_API_KEY")))
            print("TOKEN=" + str(os.environ.get("ASISTEN_RAHASIA")))
            """, env={"LLAMA_API_KEY": "rahasia123", "ASISTEN_RAHASIA": "x"})
        self.assertEqual(kode, 0)
        self.assertIn("KEY=None", out)
        self.assertIn("TOKEN=None", out)
        self.assertNotIn("rahasia123", out)

    def test_home_sementara_dan_dihapus(self):
        kode, out = self.jalan("""
            import os
            h = os.environ["HOME"]
            open(os.path.join(h, "coba.txt"), "w").write("x")
            print(h)
            """)
        self.assertEqual(kode, 0)
        self.assertTrue(out.strip().startswith(tempfile.gettempdir()))
        self.assertFalse(Path(out.strip()).exists())            # folder sementara sudah dibersihkan
        self.assertNotEqual(out.strip(), str(Path.home()))

    def test_berjalan_di_folder_hasil(self):
        (self.dir / "data.txt").write_text("isi-data", encoding="utf-8")
        kode, out = self.jalan("print(open('data.txt').read())")
        self.assertEqual((kode, out), (0, "isi-data"))

    def test_perintah_tidak_ada(self):
        kode, out = tim_kotak.jalankan_terkurung(["tidak-ada-perintah-ini"], str(self.dir), 5)
        self.assertEqual(kode, 127)
        self.assertIn("tidak ditemukan", out)


class TestBatas(DasarKotak):
    def test_batas_memori(self):
        kode, out = self.jalan("""
            try:
                x = bytearray(900 * 1024 * 1024)
                print("LOLOS")
            except MemoryError:
                print("MEMORYERROR")
            """, env={"ASISTEN_UJI_RAM_MB": "256"})
        self.assertIn("MEMORYERROR", out)
        self.assertNotIn("LOLOS", out)

    def test_ram_tanpa_batas_bila_nol(self):
        self.assertNotIn("RLIMIT_AS", self._lim({"ASISTEN_UJI_RAM_MB": "0"}))
        self.assertIn("RLIMIT_AS", self._lim({"ASISTEN_UJI_RAM_MB": "300"}))
        self.assertEqual(self._lim({"ASISTEN_UJI_RAM_MB": "300"})["RLIMIT_AS"], 300 * 1024 * 1024)

    def _lim(self, env, cmd=None):
        with mock.patch.dict(os.environ, env):
            return tim_kotak.batas_rlimit(cmd or ["python3", "x.py"], 20)

    def test_node_tidak_dibatasi_ruang_alamat(self):
        self.assertNotIn("RLIMIT_AS", self._lim({}, ["node", "main.js"]))

    def test_waktu_cpu_dan_nproc_masuk_batas(self):
        lim = self._lim({})
        self.assertEqual(lim["RLIMIT_CPU"], 22)
        self.assertEqual(lim["RLIMIT_CORE"], 0)
        self.assertGreaterEqual(lim["RLIMIT_NPROC"], tim_kotak.PROSES_TAMBAHAN)

    def test_hitungan_task_memasukkan_thread(self):
        """RLIMIT_NPROC menghitung thread: hitungan harus ikut naik ketika thread bertambah."""
        import threading
        sebelum = tim_kotak._proses_milik_sendiri()
        berhenti = threading.Event()
        ts = [threading.Thread(target=berhenti.wait, daemon=True) for _ in range(150)]
        try:
            for t in ts:
                t.start()
            self.assertGreaterEqual(tim_kotak._proses_milik_sendiri(), sebelum + 150)
        finally:
            berhenti.set()
            for t in ts:
                t.join(5)

    def test_program_masih_bisa_membuat_proses_dan_thread_saat_server_banyak_thread(self):
        """Regresi: di sistem dengan banyak thread, batas lama (hanya menghitung proses) lebih kecil dari
        yang sudah terpakai sehingga fork/thread di program uji gagal (BlockingIOError / can't start new thread)."""
        import threading
        berhenti = threading.Event()
        ts = [threading.Thread(target=berhenti.wait, daemon=True) for _ in range(150)]
        try:
            for t in ts:
                t.start()
            kode, out = self.jalan("""
                import subprocess, threading
                print(subprocess.run(["echo", "anak"], capture_output=True, text=True).stdout.strip())
                hasil = []
                ts = [threading.Thread(target=lambda: hasil.append(1)) for _ in range(20)]
                for t in ts: t.start()
                for t in ts: t.join()
                print("THREAD", len(hasil))
                """)
        finally:
            berhenti.set()
            for t in ts:
                t.join(5)
        self.assertEqual(kode, 0, out)
        self.assertIn("anak", out)
        self.assertIn("THREAD 20", out)

    def test_ukuran_berkas_dibatasi(self):
        with mock.patch.object(tim_kotak, "FSIZE_MB", 1):
            kode, out = self.jalan("""
                with open("besar.bin", "wb") as f:
                    f.write(b"x" * 5_000_000)
                print("LOLOS")
                """)
        self.assertNotEqual(kode, 0)
        self.assertNotIn("LOLOS", out)

    def test_timeout_mematikan_seluruh_proses(self):
        kode, out = self.jalan("""
            import subprocess, time
            subprocess.Popen(["sleep", "30"])
            time.sleep(30)
            """, timeout=1)
        self.assertIsNone(kode)
        self.assertIn("batas waktu", out)

    def test_keluaran_tak_berujung_hanya_ekornya(self):
        with mock.patch.object(tim_kotak, "FSIZE_MB", 3):
            kode, out = self.jalan("""
                import sys
                for i in range(1_000_000):
                    sys.stdout.write("baris %d\\n" % i)
                """, timeout=20, env={"ASISTEN_UJI_KELUARAN_KB": "10"})
        self.assertNotEqual(kode, 0)                       # dihentikan sistem (SIGXFSZ)
        self.assertLess(len(out), 12_000)                  # RAM server aman: hanya ekor yang dibaca
        self.assertIn("dihentikan sistem", out[-200:])

class TestJaringan(DasarKotak):
    KODE = """
        print("NET=" + ",".join(sorted(l.split(":")[0].strip() for l in open("/proc/net/dev").read().splitlines()[2:])))
        """

    @unittest.skipUnless(tim_kotak.jaringan_bisa_diputus(), "unshare -rn tidak tersedia di sistem ini")
    def test_jaringan_diputus_secara_bawaan(self):
        kode, out = self.jalan(self.KODE)
        self.assertEqual(kode, 0)
        self.assertEqual(out.strip(), "NET=lo")             # hanya loopback di namespace kosong

    @unittest.skipUnless(tim_kotak.jaringan_bisa_diputus(), "unshare -rn tidak tersedia di sistem ini")
    def test_jaringan_boleh_lewat_pengaturan(self):
        asli = set(l.split(":")[0].strip() for l in open("/proc/net/dev").read().splitlines()[2:])
        kode, out = self.jalan(self.KODE, env={"ASISTEN_UJI_JARINGAN": "boleh"})
        self.assertEqual(kode, 0)
        self.assertEqual(set(out.strip()[4:].split(",")), asli)

    def test_tanpa_unshare_tetap_jalan_dan_dicatat(self):
        with mock.patch.object(tim_kotak, "jaringan_bisa_diputus", return_value=False):
            kode, out = self.jalan("print('tetap-jalan')")
            self.assertEqual((kode, out), (0, "tetap-jalan"))
            self.assertIn("TIDAK diputus", tim_kotak.ringkas_isolasi(["python3", "x.py"]))


class TestCekJalan(DasarKotak):
    def spec(self):
        return {"jalankan": ["python3", "main.py"], "harapan": []}

    def test_hasil_memuat_catatan_isolasi(self):
        (self.dir / "main.py").write_text("print('ok')\n")
        status, baris, out = tim_cek.cek_jalan(self.dir, self.spec(), True)
        self.assertEqual(status, "lolos")
        self.assertTrue(baris[-1].startswith("CATATAN isolasi uji jalan:"))
        self.assertEqual(out, "ok")
        # CATATAN bukan kegagalan dan tidak ikut dihitung sebagai kesalahan oleh teks_koreksi
        self.assertFalse(any(b.startswith("GAGAL") for b in baris))

    def test_kegagalan_tetap_gagal_dengan_catatan(self):
        (self.dir / "main.py").write_text("raise SystemExit(3)\n")
        status, baris, _ = tim_cek.cek_jalan(self.dir, self.spec(), True)
        self.assertEqual(status, "gagal")
        self.assertIn("exit code 3", baris[0])
        self.assertTrue(baris[-1].startswith("CATATAN isolasi"))

    def test_program_tidak_bisa_membaca_kunci_server(self):
        (self.dir / "main.py").write_text("import os\nprint(os.environ.get('LLAMA_API_KEY'))\n")
        with mock.patch.dict(os.environ, {"LLAMA_API_KEY": "kunci-rahasia"}):
            _, baris, out = tim_cek.cek_jalan(self.dir, self.spec(), True)
        self.assertEqual(out, "None")
        self.assertNotIn("kunci-rahasia", "\n".join(baris))


if __name__ == "__main__":
    unittest.main()
