"""server_main.py - pintu masuk: argumen baris perintah, siklus hidup server, dan penutupan rapi."""

import argparse
import os
import signal
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
import agen
import tim
from . import server_akses as akses
from . import server_config as conf
from . import server_log as lg
from . import server_model as mdl
from . import server_state as state
from . import server_http as web


def keluar(*_):
    raise KeyboardInterrupt


def main():
    ap = argparse.ArgumentParser(description="AI Asisten: server web + log terminal.")
    ap.add_argument("--host", default="0.0.0.0", help="alamat bind (default 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8090, help="port (default 8090)")
    ap.add_argument("--idle", type=int, default=20,
                    help="menit tanpa aktivitas sebelum model dibongkar (0 = mati)")
    ap.add_argument("--auto", action="store_true",
                    help="awali dengan mode AUTO (tanpa konfirmasi, kecuali sudo/instal)")
    ap.add_argument("--token-baru", action="store_true", help="buat token baru")
    ap.add_argument("--tanpa-warna", action="store_true")
    a = ap.parse_args()
    if a.tanpa_warna:
        conf.WARNA = False
    conf.IDLE_MENIT = a.idle
    state.S["auto"] = a.auto

    conf.RIWAYAT.mkdir(exist_ok=True)
    os.chdir(Path.home())
    conf.TOKEN = akses.muat_token(a.token_baru)

    try:
        models = mdl.daftar_model()
    except Exception as e:  # noqa: BLE001
        lg.log("ERR", f"Tidak bisa terhubung ke llama-server di {agen.LLAMA_URL}: {e}")
        sys.exit(1)
    try:
        httpd = ThreadingHTTPServer((a.host, a.port), web.H)
    except OSError as e:
        lg.log("ERR", f"Tidak bisa membuka port {a.port}: {e}")
        sys.exit(1)

    ip = akses.ip_lan() if a.host == "0.0.0.0" else a.host
    lg.log("INFO", f"llama-server: {agen.LLAMA_URL} ({len(models)} model tersedia)")
    for m in models:
        if m["llama"] == "loaded":
            lg.log("WARN", f"{m['id']} sudah termuat (bukan oleh aplikasi ini), dibiarkan")
    lg.log("OK", f"Server jalan di http://{ip}:{a.port}")
    lg.log("OK", f"Alamar browser:\n http://{ip}:{a.port}/?token={conf.TOKEN}")
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


__all__ = ['keluar', 'main']
