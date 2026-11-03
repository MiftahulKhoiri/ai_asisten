"""Pengujian start.sh dan deploy/pasang-layanan.sh.

llama-server dan systemctl diganti program palsu, jadi tidak butuh model atau systemd.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = ROOT / "start.sh"
LLAMA_SH = ROOT / "llama_server.sh"
PASANG = ROOT / "deploy" / "pasang-layanan.sh"
BASH = shutil.which("bash")

LLAMA_PALSU = """#!/usr/bin/env python3
import json, os, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
port = int(sys.argv[sys.argv.index("--port") + 1])
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        b = json.dumps({"data": [{"id": "m1"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def log_message(self, *a):
        pass
open(os.environ["STUB_PID"], "w").write(str(os.getpid()))
open(os.environ["STUB_PID"] + ".args", "w").write(json.dumps(sys.argv[1:]))
open(os.environ["STUB_PID"] + ".key", "w").write(os.environ.get("LLAMA_API_KEY", ""))
HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


def port_bebas(selain=()):
    """Port TCP yang sedang bebas, dijamin tidak sama dengan salah satu port di `selain`."""
    while True:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        if port not in selain:
            return port


def fs_mendukung_izin_eksekusi(folder):
    """False pada sistem berkas yang tidak menyimpan izin eksekusi (mis. penyimpanan bersama Android)."""
    try:
        with tempfile.NamedTemporaryFile(dir=folder) as f:
            os.chmod(f.name, 0o755)
            return bool(os.stat(f.name).st_mode & 0o111) and os.access(f.name, os.X_OK)
    except OSError:
        return False


def hidup(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@unittest.skipUnless(BASH and sys.platform != "win32", "butuh bash di Linux/macOS")
class TestSintaks(unittest.TestCase):
    def test_bash_n(self):
        for f in (START, LLAMA_SH, PASANG):
            with self.subTest(f=f.name):
                r = subprocess.run([BASH, "-n", str(f)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_bisa_dieksekusi(self):
        if not fs_mendukung_izin_eksekusi(ROOT):
            self.skipTest("sistem berkas ini tidak menyimpan izin eksekusi")
        for f in (START, LLAMA_SH, PASANG):
            self.assertTrue(
                os.access(f, os.X_OK),
                f"{f.name} belum bisa dieksekusi. Jalankan: chmod +x start.sh llama_server.sh deploy/pasang-layanan.sh "
                "(dan, bila repo di-git: git update-index --chmod=+x start.sh llama_server.sh deploy/pasang-layanan.sh)")


@unittest.skipUnless(BASH and sys.platform != "win32", "butuh bash di Linux/macOS")
class DasarSkrip(unittest.TestCase):
    SKRIP = START

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.llama = self.dir / "llama-server"
        self.llama.write_text(LLAMA_PALSU)
        self.llama.chmod(0o755)
        (self.dir / "models").mkdir()
        (self.dir / "models" / "uji.gguf").write_bytes(b"x")
        self.pidfile = self.dir / "pid"

    def tearDown(self):
        if self.pidfile.exists():
            try:
                os.kill(int(self.pidfile.read_text()), 9)
            except (OSError, ValueError):
                pass
        self._tmp.cleanup()

    def env(self, **tambahan):
        e = {k: v for k, v in os.environ.items() if not k.startswith(("LLAMA_", "ASISTEN_"))}
        self.port_llama = port_bebas()
        e.update(LLAMA_BIN=str(self.llama), ASISTEN_MODELS_DIR=str(self.dir / "models"),
                 LLAMA_PORT=str(self.port_llama), STUB_PID=str(self.pidfile),
                 LLAMA_TUNGGU="20", LLAMA_LOG=str(self.dir / "llama.log"))
        e.update(tambahan)
        return e

    def jalan(self, *arg, **env):
        return subprocess.run([BASH, str(self.SKRIP), *arg], capture_output=True, text=True,
                              env=self.env(**env), timeout=60)


@unittest.skipUnless(BASH and sys.platform != "win32", "butuh bash di Linux/macOS")
class TestStart(DasarSkrip):
    def test_menyalakan_lalu_menghentikan_llama(self):
        r = self.jalan("--help")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("menyalakan llama-server", r.stdout)
        self.assertIn("llama-server siap", r.stdout)
        self.assertIn("usage", r.stdout)                 # asisten.py benar-benar dijalankan
        self.assertIn("llama-server dihentikan", r.stdout)
        pid = int(self.pidfile.read_text())
        time.sleep(0.3)
        self.assertFalse(hidup(pid), "llama-server palsu masih hidup")

    def test_argumen_llama_diteruskan(self):
        r = self.jalan("--help", LLAMA_ARGS="-t 4 --no-mmap", ASISTEN_CTX="4096")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        arg = json.loads(Path(str(self.pidfile) + ".args").read_text())
        self.assertEqual(arg[arg.index("--models-dir") + 1], str(self.dir / "models"))
        self.assertEqual(arg[arg.index("--host") + 1], "127.0.0.1")
        self.assertEqual(arg[arg.index("-c") + 1], "4096")
        self.assertIn("--jinja", arg)
        self.assertEqual(arg[-3:], ["-t", "4", "--no-mmap"])

    def test_tanpa_llama_args_tidak_ada_argumen_kosong(self):
        r = self.jalan("--help")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        arg = json.loads(Path(str(self.pidfile) + ".args").read_text())
        self.assertNotIn("", arg)
        self.assertEqual(arg[-1], "--jinja")

    def test_memakai_llama_yang_sudah_hidup(self):
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                b = json.dumps({"data": []}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def log_message(self, *a):
                pass
        port = port_bebas()
        srv = HTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = self.jalan("--help", LLAMA_PORT=str(port), LLAMA_BIN="/tidak/ada")
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sudah hidup", r.stdout)
        self.assertNotIn("dihentikan", r.stdout)         # bukan milik skrip, jangan dimatikan
        self.assertFalse(self.pidfile.exists())

    def test_llama_bin_tidak_ada(self):
        r = self.jalan("--help", LLAMA_BIN="/tidak/ada", PATH="/usr/bin:/bin")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("llama-server tidak ditemukan", r.stderr)

    def test_llama_berhenti_saat_dinyalakan(self):
        mati = self.dir / "mati"
        mati.write_text("#!/bin/sh\necho 'model rusak' >&2\nexit 3\n")
        mati.chmod(0o755)
        r = self.jalan("--help", LLAMA_BIN=str(mati))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("berhenti saat dinyalakan", r.stderr)
        self.assertIn("model rusak", r.stderr)           # isi log ditampilkan
        self.assertIn("model rusak", (self.dir / "llama.log").read_text())   # LLAMA_LOG dipakai

    def test_sigterm_menghentikan_asisten_lalu_llama(self):
        repo = self.dir / "repo"                     # salinan, supaya .token/riwayat tidak mengotori repo
        shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "riwayat", ".token", "aksi.log*", "llama-server.log"))
        env = self.env(HOME=str(self.dir))
        port_web = port_bebas(selain=(self.port_llama,))     # jangan bentrok dengan llama palsu
        p = subprocess.Popen(
            [BASH, str(repo / "start.sh"), "--host", "127.0.0.1", "--port", str(port_web),
             "--tanpa-warna"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            env=env, start_new_session=True)
        try:
            keluaran, siap, mulai = [], False, time.time()
            while time.time() - mulai < 30:
                baris = p.stdout.readline()
                if not baris:
                    break
                keluaran.append(baris)
                if "Tekan Ctrl+C untuk berhenti" in baris:
                    siap = True
                    break
            self.assertTrue(siap, "".join(keluaran))
            llama_pid = int(self.pidfile.read_text())
            p.terminate()                              # hanya ke skrip, bukan ke grup proses
            p.wait(timeout=20)
            sisa = p.stdout.read()
        finally:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=10)
            p.stdout.close()
        self.assertIn("Selesai", sisa)                 # asisten.py menutup diri dengan rapi
        self.assertIn("llama-server dihentikan", sisa)
        self.assertLess(sisa.index("Selesai"), sisa.index("llama-server dihentikan"))
        time.sleep(0.3)
        self.assertFalse(hidup(llama_pid), "llama-server palsu masih hidup")

    def test_llama_base_url_tidak_menyalakan_lokal(self):
        r = self.jalan("--help", LLAMA_BASE_URL="http://192.0.2.1:8080")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tidak menyalakan yang lokal", r.stdout)
        self.assertFalse(self.pidfile.exists())


    def test_tanpa_llama_hanya_menyalakan_asisten(self):
        r = self.jalan("--tanpa-llama", "--help", LLAMA_BIN="/tidak/ada")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("tanpa llama-server", r.stdout)
        self.assertIn("usage", r.stdout)
        self.assertFalse(self.pidfile.exists())

    def test_start_meneruskan_port_dan_kunci_ke_llama_server(self):
        r = self.jalan("--help", LLAMA_API_KEY="kunci-uji-123")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        args = json.loads(Path(str(self.pidfile) + ".args").read_text())
        self.assertEqual(args[args.index("--port") + 1], str(self.port_llama))
        self.assertEqual(Path(str(self.pidfile) + ".key").read_text(), "kunci-uji-123")
        self.assertNotIn("kunci-uji-123", r.stdout + r.stderr)
        self.assertNotIn("kunci-uji-123", " ".join(args), "kunci tidak boleh ada di daftar proses")


@unittest.skipUnless(BASH and sys.platform != "win32", "butuh bash di Linux/macOS")
class TestLlamaServer(DasarSkrip):
    """llama_server.sh: dijalankan di terminal sendiri, log lengkap, port/alamat bisa diatur."""
    SKRIP = LLAMA_SH

    def mulai(self, *arg, **env):
        """Jalankan di latar belakang; kembalikan (proses, keluaran sampai 'Ctrl+C' tampil)."""
        p = subprocess.Popen([BASH, str(LLAMA_SH), *arg], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env=self.env(**env), start_new_session=True)
        keluaran, mulai = [], time.time()
        while time.time() - mulai < 30:
            baris = p.stdout.readline()
            if not baris:
                break
            keluaran.append(baris)
            if "tekan Ctrl+C" in baris:
                break
        return p, "".join(keluaran)

    def hentikan(self, p, sinyal="TERM"):
        p.send_signal(getattr(__import__("signal"), "SIG" + sinyal))
        try:
            sisa = p.stdout.read()
            p.wait(timeout=20)
        finally:
            if p.poll() is None:
                p.kill()
            p.stdout.close()
        return sisa

    def test_bantuan(self):
        r = self.jalan("--help")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for kata in ("--port", "--host", "--models-dir", "--ctx", "--api-key", "--log"):
            self.assertIn(kata, r.stdout)
        self.assertFalse(self.pidfile.exists(), "--help tidak boleh menyalakan llama-server")

    def test_banner_alamat_dan_port_lalu_berhenti_dengan_rapi(self):
        p, keluar = self.mulai()
        try:
            self.assertIn("llama-server siap", keluar, keluar)
            self.assertIn("http://127.0.0.1:%d" % self.port_llama, keluar)
            self.assertIn("ISI ALAMAT INI", keluar)
            self.assertIn("127.0.0.1:%d" % self.port_llama, keluar)
            self.assertIn("1 berkas .gguf", keluar)
            self.assertIn("tidak dipakai", keluar)                  # API key
            pid = int(self.pidfile.read_text())
            args = json.loads(Path(str(self.pidfile) + ".args").read_text())
            self.assertEqual(args[args.index("--models-dir") + 1], str(self.dir / "models"))
            self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")
            self.assertEqual(args[args.index("-c") + 1], "8192")
            self.assertIn("--jinja", args)
        finally:
            sisa = self.hentikan(p)
        self.assertIn("llama-server dihentikan", sisa)
        time.sleep(0.3)
        self.assertFalse(hidup(pid), "llama-server palsu masih hidup")

    def test_ctrl_c_juga_menghentikan(self):
        p, _ = self.mulai()
        pid = int(self.pidfile.read_text())
        self.hentikan(p, "INT")
        time.sleep(0.3)
        self.assertFalse(hidup(pid))

    def test_opsi_port_host_ctx_dan_folder(self):
        port = port_bebas()
        folder = self.dir / "lain"
        folder.mkdir()
        (folder / "a.gguf").write_bytes(b"x")
        (folder / "b.gguf").write_bytes(b"x")
        p, keluar = self.mulai("--port", str(port), "--host", "127.0.0.1", "--ctx", "4096",
                               "--models-dir", str(folder), LLAMA_PORT="1")
        try:
            args = json.loads(Path(str(self.pidfile) + ".args").read_text())
            self.assertEqual(args[args.index("--port") + 1], str(port))
            self.assertEqual(args[args.index("-c") + 1], "4096")
            self.assertEqual(args[args.index("--models-dir") + 1], str(folder))
            self.assertIn("2 berkas .gguf", keluar)
            self.assertIn("http://127.0.0.1:%d" % port, keluar)       # opsi menang atas LLAMA_PORT
        finally:
            self.hentikan(p)

    def test_argumen_sesudah_pemisah_diteruskan_ke_llama_server(self):
        p, _ = self.mulai("--", "-t", "4", "--no-mmap", LLAMA_ARGS="-ngl 0")
        try:
            args = json.loads(Path(str(self.pidfile) + ".args").read_text())
            self.assertEqual(args[-5:], ["-ngl", "0", "-t", "4", "--no-mmap"])
        finally:
            self.hentikan(p)

    def test_host_terbuka_menampilkan_alamat_jaringan_dan_memperingatkan_tanpa_kunci(self):
        p, keluar = self.mulai("--host", "0.0.0.0")
        try:
            self.assertIn("terbuka untuk seluruh jaringan TANPA kunci", keluar)
            alamat = [b for b in keluar.splitlines() if "ISI ALAMAT INI" in b][0]
            self.assertIn(":%d" % self.port_llama, alamat)
            args = json.loads(Path(str(self.pidfile) + ".args").read_text())
            self.assertEqual(args[args.index("--host") + 1], "0.0.0.0")
        finally:
            self.hentikan(p)

    def test_api_key_lewat_lingkungan_bukan_argumen(self):
        p, keluar = self.mulai("--host", "0.0.0.0", "--api-key", "kunci-rahasia-77")
        try:
            self.assertEqual(Path(str(self.pidfile) + ".key").read_text(), "kunci-rahasia-77")
            args = json.loads(Path(str(self.pidfile) + ".args").read_text())
            self.assertNotIn("kunci-rahasia-77", " ".join(args))       # tidak tampil di daftar proses
            self.assertNotIn("kunci-rahasia-77", keluar)               # tidak dicetak ke terminal
            self.assertIn("API key", keluar)
            self.assertNotIn("TANPA kunci", keluar)
        finally:
            self.hentikan(p)

    def test_log_ke_berkas(self):
        log = self.dir / "log-llama.txt"
        noisy = self.dir / "berisik"
        noisy.write_text("#!/bin/sh\necho 'baris-log-llama'\nexec python3 \"%s\" \"$@\"\n" % self.llama)
        noisy.chmod(0o755)
        p, keluar = self.mulai("--log", str(log), LLAMA_BIN=str(noisy))
        try:
            self.assertNotIn("baris-log-llama", keluar)               # tidak di terminal
            self.assertIn(str(log), keluar)
        finally:
            self.hentikan(p)
        self.assertIn("baris-log-llama", log.read_text())

    def test_log_llama_tampil_di_terminal_bila_tanpa_log(self):
        noisy = self.dir / "berisik"
        noisy.write_text("#!/bin/sh\necho 'baris-log-llama'\nexec python3 \"%s\" \"$@\"\n" % self.llama)
        noisy.chmod(0o755)
        p, keluar = self.mulai(LLAMA_BIN=str(noisy), LLAMA_LOG="")   # tanpa berkas log
        try:
            self.assertIn("baris-log-llama", keluar)
        finally:
            self.hentikan(p)

    def test_port_sudah_dipakai(self):
        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(401)
                self.send_header("Content-Length", "0")
                self.end_headers()      # server yang butuh kunci pun dianggap hidup

            def log_message(self, *a):
                pass
        port = port_bebas()
        srv = HTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            r = self.jalan("--port", str(port))
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(r.returncode, 1)
        self.assertIn("sudah dipakai", r.stderr)
        self.assertFalse(self.pidfile.exists())

    def test_llama_bin_tidak_ada(self):
        r = self.jalan(LLAMA_BIN="/tidak/ada", PATH="/usr/bin:/bin")
        self.assertEqual(r.returncode, 1)
        self.assertIn("llama-server tidak ditemukan", r.stderr)

    def test_llama_berhenti_saat_dinyalakan(self):
        mati = self.dir / "mati"
        mati.write_text("#!/bin/sh\necho 'model rusak' >&2\nexit 3\n")
        mati.chmod(0o755)
        r = self.jalan("--log", str(self.dir / "l.txt"), LLAMA_BIN=str(mati))
        self.assertEqual(r.returncode, 1)
        self.assertIn("berhenti saat dinyalakan (kode 3)", r.stderr)
        self.assertIn("model rusak", r.stderr)

    def test_opsi_salah(self):
        for arg, pesan in ((("--ngawur",), "opsi tidak dikenal"), (("--port", "abc"), "harus berupa angka"),
                           (("--port",), "butuh nilai"), (("--ctx", "1;ls"), "harus berupa angka")):
            r = self.jalan(*arg)
            self.assertEqual(r.returncode, 2, arg)
            self.assertIn(pesan, r.stderr, arg)
        self.assertFalse(self.pidfile.exists())


@unittest.skipUnless(BASH and sys.platform != "win32", "butuh bash di Linux/macOS")
class TestPasangLayanan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.llama = self.dir / "llama-server"
        self.llama.write_text("#!/bin/sh\nexit 0\n")
        self.llama.chmod(0o755)
        self.ctl = self.dir / "fakectl"
        self.ctl.write_text(f'#!/bin/sh\necho "$@" >> {self.dir}/panggilan.txt\n')
        self.ctl.chmod(0o755)
        self.unit_dir = self.dir / "unit"

    def tearDown(self):
        self._tmp.cleanup()

    def jalan(self, *arg, **env):
        e = {k: v for k, v in os.environ.items() if not k.startswith(("LLAMA_", "ASISTEN_"))}
        e.update(SYSTEMCTL=str(self.ctl), LOGINCTL=str(self.ctl),
                 SYSTEMD_USER_DIR=str(self.unit_dir), LLAMA_BIN=str(self.llama),
                 ASISTEN_MODELS_DIR=str(self.dir / "models"))
        e.update(env)
        return subprocess.run([BASH, str(PASANG), *arg], capture_output=True, text=True, env=e)

    def panggilan(self):
        p = self.dir / "panggilan.txt"
        return p.read_text().splitlines() if p.exists() else []

    def test_memasang_unit_dan_mengaktifkan(self):
        r = self.jalan(LLAMA_PORT="8123", ASISTEN_CTX="4096")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        llama = (self.unit_dir / "llama-server.service").read_text()
        asisten = (self.unit_dir / "ai-asisten.service").read_text()
        self.assertNotIn("@", llama + asisten)            # semua placeholder terisi
        self.assertIn(f"ExecStart={self.llama} --models-dir {self.dir}/models "
                      "--host 127.0.0.1 --port 8123 -c 4096 --jinja", llama)
        self.assertIn("Environment=LLAMA_BASE_URL=http://127.0.0.1:8123", asisten)
        self.assertIn(f"WorkingDirectory={ROOT}", asisten)
        self.assertIn(f"{ROOT}/asisten.py --tanpa-warna", asisten)
        self.assertEqual(self.panggilan()[:2], [
            "--user daemon-reload",
            "--user enable --now llama-server.service ai-asisten.service"])
        self.assertTrue(self.panggilan()[2].startswith("enable-linger"))

    def test_hapus(self):
        self.jalan()
        r = self.jalan("--hapus")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(list(self.unit_dir.glob("*.service")), [])
        self.assertIn("--user disable --now ai-asisten.service llama-server.service",
                      self.panggilan())

    def test_menolak_jalur_berspasi(self):
        r = self.jalan(ASISTEN_MODELS_DIR=str(self.dir / "model saya"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("spasi", r.stderr)
        self.assertEqual(self.panggilan(), [])            # tidak menyentuh systemctl

    def test_menolak_llama_tidak_ada_dan_port_bukan_angka(self):
        r = self.jalan(LLAMA_BIN="/tidak/ada")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("llama-server tidak ditemukan", r.stderr)
        r = self.jalan(LLAMA_PORT="80a")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("harus berupa angka", r.stderr)

    def test_opsi_tidak_dikenal(self):
        r = self.jalan("--aneh")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("opsi tidak dikenal", r.stderr)


if __name__ == "__main__":
    unittest.main()
