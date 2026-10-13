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


def hidup(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@unittest.skipUnless(BASH and sys.platform != "win32", "butuh bash di Linux/macOS")
class TestSintaks(unittest.TestCase):
    def test_bash_n(self):
        for f in (START, PASANG):
            with self.subTest(f=f.name):
                r = subprocess.run([BASH, "-n", str(f)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_bisa_dieksekusi(self):
        for f in (START, PASANG):
            self.assertTrue(os.access(f, os.X_OK), f"{f.name} belum chmod +x")


@unittest.skipUnless(BASH and sys.platform != "win32", "butuh bash di Linux/macOS")
class TestStart(unittest.TestCase):
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
        return subprocess.run([BASH, str(START), *arg], capture_output=True, text=True,
                              env=self.env(**env), timeout=60)

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
