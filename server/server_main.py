"""server_main.py - pintu masuk: argumen baris perintah, siklus hidup server, dan penutupan rapi."""

import argparse
import os
import signal
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
import agen
import tim
from . import server_akses as akses
from . import server_config as conf
from . import server_koneksi as kon
from . import server_log as lg
from . import server_model as mdl
from . import server_state as state
from . import server_http as web


def keluar(*_):
    raise KeyboardInterrupt


class ServerTerbatas(ThreadingHTTPServer):
    """ThreadingHTTPServer dengan batas koneksi serentak (`conf.MAKS_KONEKSI`).

    Satu koneksi = satu thread (± beberapa MB di perangkat RAM kecil). Tanpa batas, banyak koneksi
    terbuka (tab yang lupa ditutup, long-poll, atau pemindai jaringan) bisa menghabiskan RAM.
    Koneksi di atas batas langsung dijawab 503 dan ditutup; halaman web mencoba lagi sendiri."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._slot = threading.BoundedSemaphore(conf.MAKS_KONEKSI)
        self.ditolak = 0
        self.ditolak_asing = 0        # koneksi dari alamat di luar jaringan lokal (lihat server_akses.alamat_diizinkan)
        self._dilog_asing = {}        # alamat -> kapan terakhir dicatat di log (agar log tidak banjir)

    def _tolak_asing(self, request, ip):
        self.ditolak_asing += 1
        jam = time.monotonic()
        if jam - self._dilog_asing.get(ip, -1e9) > 600:
            if len(self._dilog_asing) > 256:
                self._dilog_asing.clear()
            self._dilog_asing[ip] = jam
            lg.log("WARN", f"Koneksi dari {ip} ditolak: bukan alamat jaringan lokal "
                           "(izinkan dengan ASISTEN_IZIN_IP=alamat atau ASISTEN_IZIN_PUBLIK=1)")
        try:
            request.settimeout(2)
            pesan = b"Ditolak: alamat di luar jaringan lokal.\n"
            request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Type: text/plain; charset=utf-8\r\n"
                            b"Content-Length: " + str(len(pesan)).encode() + b"\r\nConnection: close\r\n\r\n" + pesan)
        except OSError:
            pass
        self.shutdown_request(request)

    def process_request(self, request, client_address):
        if not akses.alamat_diizinkan(client_address[0]):
            return self._tolak_asing(request, client_address[0])
        if not self._slot.acquire(blocking=False):
            self.ditolak += 1
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 2\r\n"
                                b"Content-Length: 0\r\nConnection: close\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:         # thread gagal dibuat: slot jangan bocor
            self._slot.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slot.release()


def main():
    ap = argparse.ArgumentParser(description="AI Asisten: server web + log terminal.")
    ap.add_argument("--host", default=os.environ.get("ASISTEN_HOST", "0.0.0.0"),
                    help="alamat bind (default 0.0.0.0, atau ASISTEN_HOST)")
    ap.add_argument("--lokal", action="store_true",
                    help="hanya bisa diakses dari perangkat ini (sama dengan --host 127.0.0.1)")
    ap.add_argument("--port", type=int, default=8090, help="port (default 8090)")
    ap.add_argument("--idle", type=int, default=20,
                    help="menit tanpa aktivitas sebelum model dibongkar (0 = mati)")
    ap.add_argument("--auto", action="store_true",
                    help="awali dengan mode AUTO (tanpa konfirmasi, kecuali sudo/instal)")
    ap.add_argument("--token-baru", action="store_true", help="buat token baru")
    ap.add_argument("--tanpa-warna", action="store_true")
    a = ap.parse_args()
    if a.lokal:
        a.host = "127.0.0.1"
    if a.tanpa_warna:
        conf.WARNA = False
    conf.IDLE_MENIT = a.idle
    state.S["auto"] = a.auto

    conf.RIWAYAT.mkdir(exist_ok=True)
    os.chdir(Path.home())
    conf.TOKEN = akses.muat_token(a.token_baru)

    peringatan = kon.koneksi_muat()
    if peringatan:
        lg.log("WARN", peringatan)
    try:
        models = mdl.daftar_model()
    except Exception as e:  # noqa: BLE001
        # Tidak lagi berhenti: llama-server dinyalakan terpisah (./llama_server.sh) dan alamatnya
        # bisa diisi atau diperbaiki dari web (Pengaturan koneksi).
        models = None
        galat_llama = f"{type(e).__name__}: {e}"
    try:
        httpd = ServerTerbatas((a.host, a.port), web.H)
    except OSError as e:
        lg.log("ERR", f"Tidak bisa membuka port {a.port}: {e}")
        sys.exit(1)

    for salah in akses.jaringan_tambahan()[1]:
        lg.log("WARN", f"ASISTEN_IZIN_IP: \"{salah}\" bukan alamat IP/CIDR yang sah, diabaikan")
    if a.host in ("127.0.0.1", "localhost", "::1"):
        lg.log("INFO", "Hanya bisa diakses dari perangkat ini (bind lokal)")
    else:
        lg.log("WARN", "Server terbuka di jaringan lewat HTTP polos: token tidak terenkripsi, pakai hanya di "
                       "jaringan tepercaya (atau lewat VPN/terowongan HTTPS)")
        if conf.IZIN_PUBLIK:
            lg.log("WARN", "ASISTEN_IZIN_PUBLIK=1: alamat dari internet juga DITERIMA. Pastikan port ini tidak "
                           "diteruskan (port-forward) ke internet tanpa pelindung lain")
        else:
            lg.log("INFO", "Hanya alamat jaringan lokal/VPN yang diterima; alamat internet ditolak (403)")
    ip = akses.ip_lan() if a.host == "0.0.0.0" else a.host
    if models is None:
        lg.log("WARN", f"Belum bisa menghubungi llama-server di {kon.koneksi_alamat()} ({galat_llama})")
        lg.log("WARN", "Nyalakan dengan ./llama_server.sh (terminal lain), atau isi alamat/API key di web: "
                       "tombol \"Atur koneksi\"")
    else:
        lg.log("INFO", f"Server model di:\n {kon.koneksi_alamat()} (jumlah model tersedia:{len(models)}"
                       f"{', ada API key' if agen.LLAMA_KEY else ''})")
        for m in models:
            if m["llama"] == "loaded":
                lg.log("WARN", f"{m['id']} sudah termuat (bukan oleh aplikasi ini), dibiarkan")
    lg.log("OK", f"Server jalan di:\n http://{ip}:{a.port}")
    lg.log("OK", f"Alamat browser dapat di akses di:\n http://{ip}:{a.port}/?token={conf.TOKEN}")
    lg.log("INFO", "Model belum dimuat. Pilih model dari tampilan web.")
    lg.log("INFO", "Model dibongkar otomatis: tombol Selesai, "
                + (f"idle {conf.IDLE_MENIT} menit, " if conf.IDLE_MENIT > 0 else "")
                + "atau Ctrl+C di terminal")
    if state.S["auto"]:
        lg.log("WARN", "Mode AUTO aktif: perintah dijalankan tanpa konfirmasi")
    try:
        # Handler dipasang di dalam try, dan pesan "siap" dicetak sesudahnya: begitu pesan itu
        # terlihat, sinyal (Ctrl+C, kill, systemctl stop) pasti ditutup dengan rapi.
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, keluar)
        lg.log("INFO", "Tekan Ctrl+C untuk berhenti")
        threading.Thread(target=mdl.jaga_idle, daemon=True).start()
        httpd.serve_forever()
    except KeyboardInterrupt:
        print()
        lg.log("INFO", "Menutup aplikasi ...")
    finally:
        ctx = state.AKTIF.get("ctx")
        if ctx:
            ctx.batal.set()
        try:
            mdl.bongkar_model()
        except Exception as e:  # noqa: BLE001
            lg.log("ERR", f"Gagal membongkar model saat keluar: {e}")
        for nama in tim.bongkar_sisa():
            lg.log("OK", f"Model Agent dibongkar dari memori: {nama}")
        httpd.server_close()
        lg.log("OK", "Selesai")


__all__ = ['keluar', 'main', 'ServerTerbatas']
