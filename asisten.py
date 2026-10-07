#!/usr/bin/env python3
"""asisten.py - AI Asisten: server web + log di terminal.

Jalankan:   python3 asisten.py
Lalu buka alamat yang tampil di terminal dari HP (satu jaringan Wi-Fi).

- Terminal hanya untuk menyalakan aplikasi dan menampilkan log.
- Model BARU dimuat setelah dipilih di tampilan web, dan otomatis dibongkar
  saat sesi diakhiri, setelah idle, atau saat aplikasi ditutup (Ctrl+C).
- Semua endpoint /api wajib token (disimpan di .token).
Hanya memakai library standar Python.
"""
import argparse
import hmac
import json
import os
import queue
import re
import secrets
import signal
import socket
import sys
import threading
import time
import traceback
import urllib.error
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import agen

BASE = Path(__file__).resolve().parent
WEB = BASE / "web"
RIWAYAT = BASE / "riwayat"
TOKEN_FILE = BASE / ".token"
MODELS_DIR = Path(os.environ.get("ASISTEN_MODELS_DIR", str(Path.home() / "models")))
ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")

TOKEN = ""
IDLE_MENIT = 20
WARNA = sys.stdout.isatty()

S = {"model": None, "target": None, "status": "kosong", "pesan": "",
     "kita_muat": False, "auto": False, "aktivitas": time.time(),
     "skill": None}   # tuple skill (tanpa/web/dasar/kompleks/kritis), dipilih di web
S_LOCK = threading.RLock()
GEN_LOCK = threading.Lock()   # hanya satu proses generasi pada satu waktu
AKTIF = {"ctx": None}
KONF = {}                     # kid -> [Event, setuju]


# --------------------------------------------------------------------------
# Log terminal
# --------------------------------------------------------------------------
LEVEL_WARNA = {"INFO": "36", "OK": "32", "WARN": "33", "ERR": "31",
               "TOOL": "35", "CHAT": "34", "KONF": "33"}


def w(kode, teks):
    return f"\033[{kode}m{teks}\033[0m" if WARNA else teks


def log(level, pesan):
    jam = datetime.now().strftime("%H:%M:%S")
    print(f"{w('90', jam)} {w(LEVEL_WARNA.get(level, '0'), f'{level:<5}')} {pesan}",
          flush=True)


# --------------------------------------------------------------------------
# Token
# --------------------------------------------------------------------------
def muat_token(baru=False):
    if TOKEN_FILE.exists() and not baru:
        t = TOKEN_FILE.read_text().strip()
        if len(t) >= 16:
            return t
    t = secrets.token_urlsafe(18)
    fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    return t


def ip_lan():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# --------------------------------------------------------------------------
# Model: daftar, muat, bongkar
# --------------------------------------------------------------------------
def daftar_model():
    data = agen.llama("/v1/models", timeout=10)["data"]
    hasil = []
    for m in data:
        f = MODELS_DIR / (m["id"] + ".gguf")
        mb = round(f.stat().st_size / 1048576) if f.exists() else None
        hasil.append({"id": m["id"], "mb": mb,
                      "llama": (m.get("status") or {}).get("value")})
    hasil.sort(key=lambda x: x["mb"] or 0)
    return hasil


def status_llama(nama):
    for m in daftar_model():
        if m["id"] == nama:
            return m["llama"]
    return None


def _unload(nama):
    try:
        agen.llama("/models/unload", {"model": nama}, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code != 400:  # 400 = model memang tidak berjalan
            raise


def muat_model(nama):
    with S_LOCK:
        lama, lama_kita = S["model"], S["kita_muat"]
        S.update(status="memuat", target=nama, model=None,
                 pesan=f"Menyiapkan {nama} ...", kita_muat=False)
    dimuat_kita = False
    try:
        if lama and lama_kita and lama != nama:
            log("INFO", f"Membongkar model sebelumnya: {lama}")
            _unload(lama)
        info = {m["id"]: m for m in daftar_model()}
        if nama not in info:
            raise RuntimeError("Model tidak ditemukan di llama-server")
        awal = info[nama]["llama"]
        if awal != "loaded":
            log("INFO", f"Memuat model {nama} ...")
            if awal != "loading":
                agen.llama("/models/load", {"model": nama}, timeout=30)
            dimuat_kita = True
            mulai = time.time()
            while True:
                time.sleep(2)
                st = status_llama(nama)
                with S_LOCK:
                    S["pesan"] = f"Memuat {nama} ... {int(time.time() - mulai)} dtk"
                if st == "loaded":
                    break
                if st == "failed":
                    raise RuntimeError("llama-server gagal memuat model")
                if time.time() - mulai > 300:
                    raise RuntimeError("Model belum siap setelah 5 menit")
            log("OK", f"Model siap: {nama} ({int(time.time() - mulai)} dtk)")
        elif lama == nama and lama_kita:
            dimuat_kita = True
        else:
            log("INFO", f"{nama} sudah termuat oleh pihak lain; dipakai, tidak akan dibongkar")
        with S_LOCK:
            S.update(model=nama, status="siap", pesan="", target=None,
                     kita_muat=dimuat_kita, aktivitas=time.time())
    except Exception as e:  # noqa: BLE001
        log("ERR", f"Gagal memuat {nama}: {e}")
        if dimuat_kita:
            try:
                _unload(nama)
            except Exception:  # noqa: BLE001
                pass
        with S_LOCK:
            S.update(model=None, status="error", pesan=str(e), target=None,
                     kita_muat=False)


def bongkar_model():
    with S_LOCK:
        nama, kita, target = S["model"], S["kita_muat"], S["target"]
    if nama and kita:
        try:
            _unload(nama)
            log("OK", f"Model dibongkar dari memori: {nama}")
        except Exception as e:  # noqa: BLE001
            log("ERR", f"Gagal membongkar {nama}: {e}")
    elif nama:
        log("INFO", f"{nama} dimuat pihak lain, dibiarkan")
    elif target:
        try:
            _unload(target)
            log("OK", f"Pemuatan {target} dibatalkan")
        except Exception:  # noqa: BLE001
            pass
    with S_LOCK:
        S.update(model=None, status="kosong", pesan="", target=None, kita_muat=False)


def selesai_sesi():
    ctx = AKTIF.get("ctx")
    if ctx:
        ctx.batal.set()
        for _ in range(50):
            if not GEN_LOCK.locked():
                break
            time.sleep(0.1)
    bongkar_model()


def jaga_idle():
    while True:
        time.sleep(30)
        if IDLE_MENIT <= 0:
            continue
        with S_LOCK:
            siap = S["status"] == "siap"
            idle = time.time() - S["aktivitas"]
        if siap and not GEN_LOCK.locked() and idle > IDLE_MENIT * 60:
            log("WARN", f"Tidak ada aktivitas {IDLE_MENIT} menit, model dibongkar otomatis")
            bongkar_model()


def sentuh():
    with S_LOCK:
        S["aktivitas"] = time.time()


# --------------------------------------------------------------------------
# Riwayat chat (JSON per obrolan)
# --------------------------------------------------------------------------
def path_chat(cid):
    if not ID_RE.match(cid or ""):
        raise FileNotFoundError("id tidak valid")
    return RIWAYAT / f"{cid}.json"


def simpan_chat(chat):
    chat["diubah"] = datetime.now().isoformat(timespec="seconds")
    p = path_chat(chat["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(chat, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def baca_chat(cid):
    return json.loads(path_chat(cid).read_text(encoding="utf-8"))


def baru_chat(model):
    cid = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    chat = {"id": cid, "judul": "Obrolan baru", "model": model,
            "dibuat": datetime.now().isoformat(timespec="seconds"), "pesan": []}
    simpan_chat(chat)
    return chat


def cuplikan_chat(chat, maks=80):
    """Ringkasan satu baris: jawaban asisten terakhir (atau pesan terakhir)."""
    for peran in ("assistant", "user"):
        for m in reversed(chat.get("pesan", [])):
            teks = m.get("content") if m.get("role") == peran else None
            if isinstance(teks, str) and teks.strip():
                teks = " ".join(teks.split())
                return teks if len(teks) <= maks else teks[:maks - 1] + "\u2026"
    return ""


def hapus_semua_chat(kecuali=None):
    """Hapus semua file riwayat (kecuali satu id). Kembalian: jumlah yang dihapus."""
    n = 0
    for f in RIWAYAT.glob("*.json"):
        if f.stem == kecuali:
            continue
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    return n


def daftar_chat():
    file = sorted(RIWAYAT.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    hasil = []
    for p in file[:100]:
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            hasil.append({"id": c["id"], "judul": c.get("judul") or "Obrolan",
                          "diubah": c.get("diubah", ""), "model": c.get("model"),
                          "jumlah": sum(1 for m in c.get("pesan", []) if m.get("role") == "user"),
                          "cuplikan": cuplikan_chat(c)})
        except (OSError, ValueError, KeyError):
            continue
    return hasil


# --------------------------------------------------------------------------
# Konteks untuk agen (izin lewat web)
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, q, batal):
        self.q = q
        self.batal = batal

    @property
    def auto(self):
        return S["auto"]

    def konfirmasi(self, jenis, ringkas, detail=""):
        kid = secrets.token_hex(4)
        ev = threading.Event()
        KONF[kid] = [ev, False]
        self.q.put({"t": "konfirmasi", "kid": kid, "jenis": jenis,
                    "ringkas": ringkas, "detail": detail})
        for _ in range(120):  # tunggu maksimal 2 menit
            if ev.wait(1) or self.batal.is_set():
                break
        item = KONF.pop(kid, None)
        return bool(item and item[0].is_set() and item[1])


def status_json():
    with S_LOCK:
        sk = S["skill"]
        ids = agen.tolls.SKILL_IDS
        d = {"model": S["model"], "status": S["status"], "pesan": S["pesan"],
             "auto": S["auto"], "sibuk": GEN_LOCK.locked(),
             "skill": list(sk) if sk else None,
             "tool_aktif": len(agen.tools_untuk(sk)) if sk else None,
             "skill_bawaan": list(agen.tolls.normal_skill(None)),
             "skills": {m: len(agen.tools_untuk(m)) for m in ids},
             "skill_tools": {m: agen.tolls.nama_tool_aktif(m) for m in ids}}
    if d["status"] != "siap":
        try:
            d["models"] = daftar_model()
        except Exception:  # noqa: BLE001
            d["models"] = []
            d["pesan"] = d["pesan"] or "Tidak bisa menghubungi llama-server"
    return d


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
# File statis tampilan web (hanya yang ada di daftar ini yang boleh diakses)
STATIS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/index.css": ("index.css", "text/css; charset=utf-8"),
    "/index.js": ("index.js", "application/javascript; charset=utf-8"),
}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, kode, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        try:
            self.send_response(kode)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 1_000_000:
            raise ValueError("body terlalu besar")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _auth(self):
        h = self.headers.get("Authorization", "")
        tok = h[7:] if h.startswith("Bearer ") else ""
        return hmac.compare_digest(tok, TOKEN)

    def _tangani(self, metode):
        path = urlparse(self.path).path
        try:
            if metode == "GET" and path in STATIS:
                nama, tipe = STATIS[path]
                data = (WEB / nama).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", tipe)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            if not path.startswith("/api/"):
                return self._json(404, {"error": "Tidak ditemukan"})
            if not self._auth():
                log("WARN", f"Akses ditolak dari {self.client_address[0]} (token salah)")
                return self._json(401, {"error": "Token salah"})
            self.rute(metode, path)
        except FileNotFoundError:
            self._json(404, {"error": "Tidak ditemukan"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            log("ERR", f"{metode} {path}: {type(e).__name__}: {e}")
            log("ERR", traceback.format_exc().strip().splitlines()[-2][:200])
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self._tangani("GET")

    def do_POST(self):
        self._tangani("POST")

    def do_DELETE(self):
        self._tangani("DELETE")

    def rute(self, metode, path):
        if metode == "GET" and path == "/api/status":
            return self._json(200, status_json())
        if metode == "GET" and path == "/api/chat":
            return self._json(200, {"chat": daftar_chat()})
        if metode == "POST":
            b = self._body()
            if path == "/api/chat/baru":
                with S_LOCK:
                    model = S["model"]
                sentuh()
                return self._json(200, baru_chat(model))
            if path == "/api/chat/hapus-semua":
                kecuali = b.get("kecuali")
                if kecuali is not None and not ID_RE.match(str(kecuali)):
                    return self._json(400, {"error": "id tidak valid"})
                n = hapus_semua_chat(kecuali)
                log("INFO", f"{n} obrolan dihapus")
                return self._json(200, {"ok": True, "dihapus": n})
            if path == "/api/model/pilih":
                return self.pilih(b)
            if path == "/api/model/selesai":
                log("INFO", "Sesi diakhiri dari web")
                selesai_sesi()
                return self._json(200, {"ok": True})
            if path == "/api/auto":
                S["auto"] = bool(b.get("aktif"))
                log("WARN" if S["auto"] else "INFO",
                    "Mode AUTO " + ("AKTIF (tanpa konfirmasi, kecuali sudo/instal)"
                                    if S["auto"] else "dimatikan"))
                return self._json(200, {"auto": S["auto"]})
            if path == "/api/kirim":
                return self.kirim(b)
            if path == "/api/konfirmasi":
                item = KONF.get(b.get("kid"))
                if not item:
                    return self._json(404, {"error": "Permintaan izin sudah kedaluwarsa"})
                item[1] = bool(b.get("setuju"))
                item[0].set()
                sentuh()
                log("KONF", "diizinkan" if item[1] else "ditolak")
                return self._json(200, {"ok": True})
            if path == "/api/stop":
                ctx = AKTIF.get("ctx")
                if ctx:
                    ctx.batal.set()
                return self._json(200, {"ok": bool(ctx)})
        m = re.fullmatch(r"/api/chat/([A-Za-z0-9_-]+)", path)
        if m:
            cid = m.group(1)
            if metode == "GET":
                sentuh()
                return self._json(200, baca_chat(cid))
            if metode == "DELETE":
                path_chat(cid).unlink()
                log("INFO", f"Obrolan dihapus: {cid}")
                return self._json(200, {"ok": True})
        self._json(404, {"error": "Tidak ditemukan"})

    def pilih(self, b):
        nama = b.get("model")
        skill = b.get("skill")
        skill = agen.tolls.normal_skill(skill)   # boleh beberapa skill sekaligus
        with S_LOCK:
            if S["status"] == "memuat":
                return self._json(409, {"error": "Model sedang dimuat"})
            if GEN_LOCK.locked():
                return self._json(409, {"error": "Masih ada proses berjalan"})
            S["status"] = "memuat"
            S["pesan"] = f"Menyiapkan {nama} ..."
            S["skill"] = skill
        log("INFO", f"Skill dipilih: {'+'.join(skill)} ({len(agen.tools_untuk(skill))} tool)")
        sentuh()
        threading.Thread(target=muat_model, args=(nama,), daemon=True).start()
        self._json(200, {"ok": True})

    def kirim(self, b):
        cid, teks = b.get("id"), (b.get("teks") or "").strip()
        with S_LOCK:
            siap, model, skill = S["status"] == "siap", S["model"], S["skill"]
        if not siap:
            return self._json(409, {"error": "Model belum dimuat. Pilih model dulu."})
        if not teks:
            return self._json(400, {"error": "Pesan kosong"})
        if not GEN_LOCK.acquire(blocking=False):
            return self._json(409, {"error": "Masih ada proses berjalan"})
        try:
            chat = baca_chat(cid)
        except Exception:  # noqa: BLE001
            GEN_LOCK.release()
            return self._json(404, {"error": "Obrolan tidak ditemukan"})
        chat["model"] = model
        chat["pesan"].append({"role": "user", "content": teks})
        if chat.get("judul") in (None, "", "Obrolan baru"):
            chat["judul"] = teks[:40]
        simpan_chat(chat)
        sentuh()
        log("CHAT", f"kamu: {teks[:100]}")

        q = queue.Queue()
        ctx = Ctx(q, threading.Event())
        ctx.skill = skill
        AKTIF["ctx"] = ctx

        def kerja():
            try:
                for ev in agen.giliran(chat["pesan"], model, ctx, chat):
                    q.put(ev)
            except Exception as e:  # noqa: BLE001
                q.put({"t": "error", "d": f"{type(e).__name__}: {e}"})
            finally:
                try:
                    simpan_chat(chat)
                except OSError as e:
                    log("ERR", f"Gagal menyimpan obrolan: {e}")
                AKTIF["ctx"] = None
                sentuh()
                GEN_LOCK.release()
                q.put(None)

        threading.Thread(target=kerja, daemon=True).start()
        self.alirkan(q, ctx)

    def alirkan(self, q, ctx):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        hidup = True
        while True:
            try:
                ev = q.get(timeout=10)
            except queue.Empty:
                ev = {"t": "ping"}
            if ev is None:
                break
            catat_event(ev)
            if hidup:
                try:
                    self.wfile.write((json.dumps(ev, ensure_ascii=False) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    hidup = False
                    ctx.batal.set()
                    log("WARN", "Klien terputus, proses dibatalkan")


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


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def keluar(*_):
    raise KeyboardInterrupt


def main():
    global TOKEN, IDLE_MENIT, WARNA
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
        WARNA = False
    IDLE_MENIT = a.idle
    S["auto"] = a.auto

    RIWAYAT.mkdir(exist_ok=True)
    os.chdir(Path.home())
    TOKEN = muat_token(a.token_baru)

    try:
        models = daftar_model()
    except Exception as e:  # noqa: BLE001
        log("ERR", f"Tidak bisa terhubung ke llama-server di {agen.LLAMA_URL}: {e}")
        sys.exit(1)
    try:
        server = ThreadingHTTPServer((a.host, a.port), H)
    except OSError as e:
        log("ERR", f"Tidak bisa membuka port {a.port}: {e}")
        sys.exit(1)

    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, keluar)

    ip = ip_lan() if a.host == "0.0.0.0" else a.host
    log("INFO", f"llama-server: {agen.LLAMA_URL} ({len(models)} model tersedia)")
    for m in models:
        if m["llama"] == "loaded":
            log("WARN", f"{m['id']} sudah termuat (bukan oleh aplikasi ini), dibiarkan")
    log("OK", f"Server jalan di http://{ip}:{a.port}")
    log("OK", f"Buka dari HP: http://{ip}:{a.port}/?token={TOKEN}")
    log("INFO", "Model belum dimuat. Pilih model dari tampilan web.")
    log("INFO", "Model dibongkar otomatis: tombol Selesai, "
                + (f"idle {IDLE_MENIT} menit, " if IDLE_MENIT > 0 else "")
                + "atau Ctrl+C di terminal")
    if S["auto"]:
        log("WARN", "Mode AUTO aktif: perintah dijalankan tanpa konfirmasi")
    log("INFO", "Tekan Ctrl+C untuk berhenti")

    threading.Thread(target=jaga_idle, daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        log("INFO", "Menutup aplikasi ...")
    finally:
        ctx = AKTIF.get("ctx")
        if ctx:
            ctx.batal.set()
        try:
            bongkar_model()
        except Exception as e:  # noqa: BLE001
            log("ERR", f"Gagal membongkar model saat keluar: {e}")
        server.server_close()
        log("OK", "Selesai")


if __name__ == "__main__":
    main()
