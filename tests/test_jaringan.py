"""Tes akses jaringan server: penyaring alamat, pembatas token salah, dan header aman."""
import json
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import asisten  # noqa: E402
from server import server_akses as akses  # noqa: E402
from server import server_config as conf  # noqa: E402
from server import server_log, server_main  # noqa: E402

LOKAL = ["127.0.0.1", "127.5.5.5", "::1", "10.1.2.3", "172.16.0.1", "172.31.255.254", "192.168.1.5",
         "169.254.10.10", "100.64.0.1", "100.127.255.254", "fd00::1", "fe80::1%eth0", "::ffff:192.168.1.5"]
PUBLIK = ["8.8.8.8", "1.1.1.1", "93.184.216.34", "172.32.0.1", "100.128.0.1", "2001:4860:4860::8888",
          "::ffff:8.8.8.8", "", "bukan-ip", "999.1.1.1"]


class TestIpLokal(unittest.TestCase):
    def test_alamat_lokal(self):
        for ip in LOKAL:
            with self.subTest(ip=ip):
                self.assertTrue(akses.ip_lokal(ip))

    def test_alamat_publik_atau_rusak(self):
        for ip in PUBLIK:
            with self.subTest(ip=ip):
                self.assertFalse(akses.ip_lokal(ip))

    def test_loopback_saja(self):
        self.assertTrue(akses.ip_loopback("127.0.0.1"))
        self.assertTrue(akses.ip_loopback("::1"))
        self.assertTrue(akses.ip_loopback("::ffff:127.0.0.1"))
        self.assertFalse(akses.ip_loopback("192.168.1.5"))


class TestAlamatDiizinkan(unittest.TestCase):
    def test_bawaan_lokal_boleh_publik_ditolak(self):
        with mock.patch.object(conf, "IZIN_PUBLIK", False), mock.patch.object(conf, "IZIN_IP", ""):
            self.assertTrue(akses.alamat_diizinkan("192.168.1.9"))
            self.assertFalse(akses.alamat_diizinkan("8.8.8.8"))
            self.assertFalse(akses.alamat_diizinkan("bukan-ip"))

    def test_izin_publik_membuka_semua_alamat_sah(self):
        with mock.patch.object(conf, "IZIN_PUBLIK", True):
            self.assertTrue(akses.alamat_diizinkan("8.8.8.8"))
            self.assertTrue(akses.alamat_diizinkan("2001:4860:4860::8888"))
            self.assertFalse(akses.alamat_diizinkan("bukan-ip"))      # yang rusak tetap ditolak

    def test_izin_ip_tambahan(self):
        with mock.patch.object(conf, "IZIN_PUBLIK", False), \
                mock.patch.object(conf, "IZIN_IP", "8.8.8.0/24, 1.1.1.1 bukan-cidr"):
            self.assertTrue(akses.alamat_diizinkan("8.8.8.200"))
            self.assertTrue(akses.alamat_diizinkan("1.1.1.1"))
            self.assertFalse(akses.alamat_diizinkan("1.1.1.2"))
            self.assertFalse(akses.alamat_diizinkan("9.9.9.9"))
            self.assertEqual(akses.jaringan_tambahan()[1], ("bukan-cidr",))


class Jam:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TestPembatasGagal(unittest.TestCase):
    IP = "192.168.1.50"

    def setUp(self):
        self.jam = Jam()
        self.p = akses.PembatasGagal(jam=self.jam)
        for nama, nilai in (("GAGAL_MAKS", 5), ("GAGAL_KUNCI", 30), ("GAGAL_JENDELA", 60), ("GAGAL_KUNCI_MAKS", 100)):
            m = mock.patch.object(conf, nama, nilai)
            m.start()
            self.addCleanup(m.stop)

    def gagal(self, n, ip=None):
        return [self.p.catat_gagal(ip or self.IP) for _ in range(n)]

    def test_terkunci_tepat_pada_percobaan_ke_maks(self):
        self.assertEqual(self.gagal(4), [0, 0, 0, 0])
        self.assertEqual(self.p.sisa_kunci(self.IP), 0)
        self.assertEqual(self.p.catat_gagal(self.IP), 30)
        self.assertAlmostEqual(self.p.sisa_kunci(self.IP), 30)

    def test_kunci_berakhir_lalu_berlipat_dua_bila_terulang(self):
        self.gagal(5)
        self.jam.t += 31
        self.assertEqual(self.p.sisa_kunci(self.IP), 0)
        self.assertEqual(self.gagal(5)[-1], 60)            # kunci kedua: 2x
        self.jam.t += 61
        self.assertEqual(self.gagal(5)[-1], 100)           # 120 dipangkas ke GAGAL_KUNCI_MAKS

    def test_percobaan_lambat_tidak_pernah_mengunci(self):
        for _ in range(40):
            self.assertEqual(self.p.catat_gagal(self.IP), 0)
            self.jam.t += 20                               # 3 percobaan per jendela 60 dtk < 5
        self.assertEqual(self.p.sisa_kunci(self.IP), 0)

    def test_token_benar_menghapus_catatan(self):
        self.gagal(4)
        self.p.catat_berhasil(self.IP)
        self.assertEqual(self.gagal(4), [0, 0, 0, 0])      # hitungan mulai lagi dari nol

    def test_alamat_lain_tidak_terpengaruh(self):
        self.gagal(5)
        self.assertGreater(self.p.sisa_kunci(self.IP), 0)
        self.assertEqual(self.p.sisa_kunci("192.168.1.51"), 0)
        self.assertEqual(self.p.catat_gagal("192.168.1.51"), 0)

    def test_loopback_tidak_pernah_dikunci(self):
        self.assertEqual(self.gagal(50, ip="127.0.0.1"), [0] * 50)
        self.assertEqual(self.p.sisa_kunci("127.0.0.1"), 0)

    def test_memori_dibatasi(self):
        with mock.patch.object(akses.PembatasGagal, "MAKS_CATATAN", 50):
            for i in range(400):
                self.jam.t += 0.01
                self.p.catat_gagal("10.0.%d.%d" % (i // 250, i % 250))
        self.assertLessEqual(len(self.p._data), 50)


class TestHttpKunciDanTajuk(unittest.TestCase):
    TOKEN = "token-uji-1234567890"

    @classmethod
    def setUpClass(cls):
        cls._tok = conf.TOKEN
        conf.TOKEN = cls.TOKEN
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), asisten.H)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        conf.TOKEN = cls._tok

    def setUp(self):
        self.jam = Jam()
        pembatas = akses.PembatasGagal(jam=self.jam)
        for patcher in (mock.patch.object(akses, "PEMBATAS", pembatas),
                        mock.patch.object(akses, "ip_loopback", lambda ip: False),   # uji dari "alamat luar"
                        mock.patch.object(conf, "GAGAL_MAKS", 3),
                        mock.patch.object(conf, "GAGAL_KUNCI", 30),
                        mock.patch.object(server_log, "log", lambda *a, **k: None)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def req(self, path="/api/chat/xx", token=None):
        r = urllib.request.Request(self.base + path)
        if token:
            r.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_token_salah_berulang_dikunci_dengan_429(self):
        self.assertEqual([self.req(token="salah")[0] for _ in range(3)], [401, 401, 401])
        kode, tajuk, isi = self.req(token="salah")
        self.assertEqual(kode, 429)
        self.assertEqual(tajuk["Retry-After"], "31")
        self.assertIn("Terlalu banyak", json.loads(isi)["error"])

    def test_selama_terkunci_token_benar_pun_ditolak_dan_kunci_tidak_diperpanjang(self):
        for _ in range(3):
            self.req(token="salah")
        self.jam.t += 10
        self.assertEqual(self.req(token=self.TOKEN)[0], 429)
        self.assertEqual(self.req(token="salah")[0], 429)
        self.jam.t += 21                                    # total 31 dtk sejak terkunci
        self.assertEqual(self.req(token=self.TOKEN)[0], 404)     # lolos auth; rutenya sendiri 404

    def test_token_benar_menghapus_hitungan(self):
        for _ in range(2):
            self.req(token="salah")
        self.assertEqual(self.req(token=self.TOKEN)[0], 404)
        self.assertEqual([self.req(token="salah")[0] for _ in range(2)], [401, 401])    # belum terkunci

    def test_halaman_statis_tidak_terkena_kunci(self):
        for _ in range(3):
            self.req(token="salah")
        self.assertEqual(self.req("/")[0], 200)

    def test_tajuk_aman_di_semua_jenis_jawaban(self):
        for path, token in (("/", None), ("/api/chat/xx", None), ("/api/chat/xx", self.TOKEN), ("/tidak-ada", None)):
            with self.subTest(path=path, token=bool(token)):
                _, tajuk, _ = self.req(path, token)
                self.assertEqual(tajuk["X-Content-Type-Options"], "nosniff")
                self.assertEqual(tajuk["X-Frame-Options"], "DENY")
                self.assertEqual(tajuk["Referrer-Policy"], "no-referrer")


class SoketPalsu:
    def __init__(self):
        self.dikirim, self.ditutup = b"", False

    def settimeout(self, t):
        pass

    def sendall(self, b):
        self.dikirim += b

    def shutdown(self, how):
        pass

    def close(self):
        self.ditutup = True


class TestServerTolakAsing(unittest.TestCase):
    def buat(self):
        srv = server_main.ServerTerbatas(("127.0.0.1", 0), asisten.H)
        self.addCleanup(srv.server_close)
        return srv

    def test_alamat_publik_dijawab_403_tanpa_membuat_thread(self):
        srv = self.buat()
        s = SoketPalsu()
        with mock.patch.object(conf, "IZIN_PUBLIK", False), mock.patch.object(conf, "IZIN_IP", ""), \
                mock.patch.object(server_main.threading, "Thread") as thread, \
                mock.patch.object(server_log, "log"):
            srv.process_request(s, ("8.8.8.8", 4444))
        self.assertTrue(s.dikirim.startswith(b"HTTP/1.1 403"))
        self.assertTrue(s.ditutup)
        self.assertEqual(srv.ditolak_asing, 1)
        thread.assert_not_called()

    def test_pencatatan_log_tidak_banjir(self):
        srv = self.buat()
        with mock.patch.object(conf, "IZIN_PUBLIK", False), mock.patch.object(conf, "IZIN_IP", ""), \
                mock.patch.object(server_log, "log") as log:
            for _ in range(5):
                srv.process_request(SoketPalsu(), ("8.8.8.8", 4444))
            srv.process_request(SoketPalsu(), ("9.9.9.9", 4444))
        self.assertEqual(srv.ditolak_asing, 6)
        self.assertEqual(log.call_count, 2)                # satu per alamat, bukan per koneksi

    def test_izin_publik_membiarkan_koneksi_lewat_ke_pemrosesan_biasa(self):
        srv = self.buat()
        s = SoketPalsu()
        with mock.patch.object(conf, "IZIN_PUBLIK", True), \
                mock.patch.object(server_main.ThreadingHTTPServer, "process_request") as lanjut:
            srv.process_request(s, ("8.8.8.8", 4444))
        lanjut.assert_called_once()
        self.assertEqual(srv.ditolak_asing, 0)
        self.assertEqual(s.dikirim, b"")


class TestOpsiBaris(unittest.TestCase):
    def test_help_memuat_lokal_dan_host_env(self):
        r = subprocess.run([sys.executable, str(ROOT / "asisten.py"), "--help"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--lokal", r.stdout)
        self.assertIn("ASISTEN_HOST", r.stdout)


if __name__ == "__main__":
    unittest.main()
