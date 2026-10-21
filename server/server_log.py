"""server_log.py - log berwarna di terminal dan ringkasan event untuk log."""

from datetime import datetime
from . import server_config as conf


LEVEL_WARNA = {"INFO": "36", "OK": "32", "WARN": "33", "ERR": "31",
               "TOOL": "35", "CHAT": "34", "KONF": "33"}


def w(kode, teks):
    return f"\033[{kode}m{teks}\033[0m" if conf.WARNA else teks


def log(level, pesan):
    jam = datetime.now().strftime("%H:%M:%S")
    print(f"{w('90', jam)} {w(LEVEL_WARNA.get(level, '0'), f'{level:<5}')} {pesan}",
          flush=True)


def catat_event(ev):
    t = ev.get("t")
    if t == "tool":
        log("TOOL", ev["ringkas"])
    elif t == "konfirmasi":
        log("KONF", f"menunggu izin: {ev['ringkas'][:100]}")
    elif t == "info":
        log("CHAT", f"jawaban: {ev['tok']} token, {ev['tok_s']} tok/s")
    elif t == "ringkas":
        log("CHAT", ev["d"])
    elif t == "error":
        log("ERR", ev["d"])
    elif t == "batal":
        log("WARN", "proses dibatalkan")
    elif t == "batas":
        log("WARN", "batas langkah tercapai")
    elif t == "terpotong":
        log("WARN", "jawaban terpotong: batas token tercapai (naikkan ASISTEN_MAX_TOKENS)")
    elif t == "mulai":
        log("INFO", f"Agent mulai: folder kerja {ev['dir']}")
    elif t == "tahap":
        n = f" (putaran {ev['putaran']})" if ev.get("putaran") else ""
        log("INFO", f"Agent - {ev['peran']}{n}: {ev['model']}")
    elif t == "muat_selesai":
        log("OK", f"Model siap: {ev['model']} ({ev['detik']} dtk)")
    elif t == "bongkar":
        log("OK", f"Model dibongkar dari memori: {ev['model']}")
    elif t == "pulih":
        log("WARN", ev["d"])
    elif t == "uji_mulai":
        log("TOOL", f"agent menjalankan uji: {ev['d']}")
    elif t == "berkas":
        log("TOOL", f"agent {'membuat' if ev.get('baru') else 'mengubah'} {ev['nama']}")
    elif t == "cek":
        log("OK" if ev["ok"] else "WARN",
            "pemeriksa menjalankan program: " + ("tanpa kesalahan" if ev["ok"] else "GAGAL"))
    elif t == "nilai":
        log("OK" if ev["ok"] else "WARN",
            "keputusan pemeriksa: " + ("jadi" if ev["ok"] else "perlu perbaikan") + " - " + ev.get("ringkas", "")[:100])
    elif t == "putaran":
        log("INFO", f"Agent putaran {ev['n']}/{ev['maks']}")
    elif t == "tanya":
        log("CHAT", "agent butuh info: " + ev["d"][:100])
    elif t == "selesai" and ev.get("status"):
        log("OK" if ev["status"] == "lolos" else "WARN", f"Agent selesai: {ev['teks']}")


__all__ = ['LEVEL_WARNA', 'w', 'log', 'catat_event']
