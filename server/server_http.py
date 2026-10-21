"""server_http.py - penangan HTTP: rute /api, file statis web, dan proses generasi di thread."""

import hmac
import json
import queue
import re
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import agen
import tim
from . import server_agent as agt
from . import server_config as conf
from . import server_ctx as kts
from . import server_log as lg
from . import server_model as mdl
from . import server_chat as rwy
from . import server_state as state
from . import server_status as sts


# File statis tampilan web (hanya yang ada di daftar ini yang boleh diakses)
STATIS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/index.css": ("index.css", "text/css; charset=utf-8"),
    "/index.js": ("index.js", "application/javascript; charset=utf-8"),
    "/agent": ("agent.html", "text/html; charset=utf-8"),
    "/agent.html": ("agent.html", "text/html; charset=utf-8"),
    "/agent.css": ("agent.css", "text/css; charset=utf-8"),
    "/agent.js": ("agent.js", "application/javascript; charset=utf-8"),
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
        return hmac.compare_digest(tok, conf.TOKEN)

    def _tangani(self, metode):
        path = urlparse(self.path).path
        try:
            if metode == "GET" and path in STATIS:
                nama, tipe = STATIS[path]
                data = (conf.WEB / nama).read_bytes()
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
                lg.log("WARN", f"Akses ditolak dari {self.client_address[0]} (token salah)")
                return self._json(401, {"error": "Token salah"})
            self.rute(metode, path)
        except FileNotFoundError:
            self._json(404, {"error": "Tidak ditemukan"})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            lg.log("ERR", f"{metode} {path}: {type(e).__name__}: {e}")
            lg.log("ERR", traceback.format_exc().strip().splitlines()[-2][:200])
            self._json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        self._tangani("GET")

    def do_POST(self):
        self._tangani("POST")

    def do_DELETE(self):
        self._tangani("DELETE")

    def rute(self, metode, path):
        if metode == "GET" and path == "/api/status":
            return self._json(200, sts.status_json())
        if metode == "GET" and path == "/api/chat":
            return self._json(200, {"chat": rwy.daftar_chat()})
        if metode == "GET" and path == "/api/agent/status":
            return self._json(200, sts.agent_status())
        if metode == "GET" and path == "/api/agent/riwayat":
            return self._json(200, {"run": tim.daftar_run()})
        if metode == "GET" and path == "/api/agent/event":
            return self.agent_event()
        m = re.fullmatch(r"/api/agent/run/([0-9]{8}-[0-9]{6}-[0-9a-f]{4})", path)
        if metode == "GET" and m:
            return self._json(200, tim.baca_run(m.group(1)))
        if metode == "DELETE" and m:
            try:
                tim.hapus_run(m.group(1))
            except PermissionError as e:
                return self._json(409, {"error": str(e)})
            lg.log("INFO", f"Proses Agent dihapus: {m.group(1)}")
            return self._json(200, {"ok": True})
        if metode == "POST":
            b = self._body()
            if path == "/api/chat/baru":
                with state.S_LOCK:
                    model = state.S["model"]
                mdl.sentuh()
                return self._json(200, rwy.baru_chat(model))
            if path == "/api/chat/hapus-semua":
                kecuali = b.get("kecuali")
                if kecuali is not None and not conf.ID_RE.match(str(kecuali)):
                    return self._json(400, {"error": "id tidak valid"})
                n = rwy.hapus_semua_chat(kecuali)
                lg.log("INFO", f"{n} obrolan dihapus")
                return self._json(200, {"ok": True, "dihapus": n})
            if path == "/api/model/pilih":
                return self.pilih(b)
            if path == "/api/model/selesai":
                lg.log("INFO", "Sesi diakhiri dari web")
                mdl.selesai_sesi()
                return self._json(200, {"ok": True})
            if path == "/api/model/muat-ulang":
                try:
                    models = mdl.daftar_model()
                except Exception as e:  # noqa: BLE001
                    lg.log("ERR", f"Muat ulang daftar model gagal: {e}")
                    return self._json(502, {"error": "Tidak bisa menghubungi llama-server"})
                baru = mdl.berkas_belum_dikenal([m["id"] for m in models])
                lg.log("INFO", f"Daftar model dimuat ulang: {len(models)} model"
                    + (f"; berkas belum dikenal llama-server: {', '.join(baru)}" if baru else ""))
                return self._json(200, {"models": models, "belum_dikenal": baru})
            if path == "/api/auto":
                state.S["auto"] = bool(b.get("aktif"))
                lg.log("WARN" if state.S["auto"] else "INFO",
                    "Mode AUTO " + ("AKTIF (tanpa konfirmasi, kecuali sudo/instal)"
                                    if state.S["auto"] else "dimatikan"))
                return self._json(200, {"auto": state.S["auto"]})
            if path == "/api/kirim":
                return self.kirim(b)
            if path == "/api/agent/jalankan":
                return self.agent_jalankan(b)
            if path == "/api/agent/riwayat/hapus-semua":
                n = tim.hapus_semua_run()
                lg.log("INFO", f"{n} proses Agent dihapus")
                return self._json(200, {"ok": True, "dihapus": n})
            if path == "/api/konfirmasi":
                item = state.KONF.get(b.get("kid"))
                if not item:
                    return self._json(404, {"error": "Permintaan izin sudah kedaluwarsa"})
                item[1] = bool(b.get("setuju"))
                item[0].set()
                mdl.sentuh()
                lg.log("KONF", "diizinkan" if item[1] else "ditolak")
                return self._json(200, {"ok": True})
            if path == "/api/stop":
                ctx = state.AKTIF.get("ctx")
                if ctx:
                    ctx.batal.set()
                return self._json(200, {"ok": bool(ctx)})
        m = re.fullmatch(r"/api/chat/([A-Za-z0-9_-]+)", path)
        if m:
            cid = m.group(1)
            if metode == "GET":
                mdl.sentuh()
                return self._json(200, rwy.baca_chat(cid))
            if metode == "DELETE":
                rwy.path_chat(cid).unlink()
                lg.log("INFO", f"Obrolan dihapus: {cid}")
                return self._json(200, {"ok": True})
        self._json(404, {"error": "Tidak ditemukan"})

    def pilih(self, b):
        nama = b.get("model")
        skill = b.get("skill")
        skill = agen.tolls.normal_skill(skill)   # boleh beberapa skill sekaligus
        with state.S_LOCK:
            if state.S["status"] == "memuat":
                return self._json(409, {"error": "Model sedang dimuat"})
            if state.GEN_LOCK.locked():
                return self._json(409, {"error": "Masih ada proses berjalan"})
            state.S["status"] = "memuat"
            state.S["pesan"] = f"Menyiapkan {nama} ..."
            state.S["skill"] = skill
        lg.log("INFO", f"Skill dipilih: {'+'.join(skill)} ({len(agen.tools_untuk(skill))} tool)")
        mdl.sentuh()
        threading.Thread(target=mdl.muat_model, args=(nama,), daemon=True).start()
        self._json(200, {"ok": True})

    def kirim(self, b):
        cid, teks = b.get("id"), (b.get("teks") or "").strip()
        with state.S_LOCK:
            siap, model, skill = state.S["status"] == "siap", state.S["model"], state.S["skill"]
        if not siap:
            return self._json(409, {"error": "Model belum dimuat. Pilih model dulu."})
        if not teks:
            return self._json(400, {"error": "Pesan kosong"})
        if not state.GEN_LOCK.acquire(blocking=False):
            return self._json(409, {"error": "Masih ada proses berjalan"})
        # Kunci generasi dipegang mulai dari sini. Bila ada yang gagal sebelum thread kerja()
        # berjalan (disk penuh saat menyimpan, thread tak bisa dibuat, dst.), kunci HARUS
        # dilepas; kalau tidak, semua pesan berikutnya ditolak 409 sampai aplikasi dimulai ulang.
        diserahkan = False   # True bila kunci tidak perlu dilepas lagi di 'finally' (kerja() yang melepas)
        try:
            try:
                chat = rwy.baca_chat(cid)
            except Exception:  # noqa: BLE001
                # Lepas kunci SEBELUM membalas: klien yang langsung mengirim lagi tidak boleh
                # menabrak kunci yang belum sempat dilepas (balapan yang memunculkan 409).
                state.AKTIF["ctx"] = None
                state.GEN_LOCK.release()
                diserahkan = True
                return self._json(404, {"error": "Obrolan tidak ditemukan"})
            chat["model"] = model
            chat["pesan"].append({"role": "user", "content": teks})
            if chat.get("judul") in (None, "", "Obrolan baru"):
                chat["judul"] = teks[:40]
            rwy.simpan_chat(chat)
            mdl.sentuh()
            lg.log("CHAT", f"kamu: {teks[:100]}")

            q = queue.Queue()
            ctx = kts.Ctx(q, threading.Event())
            ctx.skill = skill
            state.AKTIF["ctx"] = ctx
            self._mulai_kerja(chat, model, ctx, q)
            diserahkan = True
        finally:
            if not diserahkan:
                state.AKTIF["ctx"] = None
                state.GEN_LOCK.release()
        self.alirkan(q, ctx)

    def _mulai_kerja(self, chat, model, ctx, q):
        """Jalankan giliran agen di thread sendiri; thread itu yang melepas GEN_LOCK."""
        def kerja():
            try:
                for ev in agen.giliran(chat["pesan"], model, ctx, chat):
                    q.put(ev)
            except Exception as e:  # noqa: BLE001
                q.put({"t": "error", "d": f"{type(e).__name__}: {e}"})
            finally:
                try:
                    rwy.simpan_chat(chat)
                except OSError as e:
                    lg.log("ERR", f"Gagal menyimpan obrolan: {e}")
                state.AKTIF["ctx"] = None
                mdl.sentuh()
                state.GEN_LOCK.release()
                q.put(None)

        threading.Thread(target=kerja, daemon=True).start()

    def agent_jalankan(self, b):
        """Mulai satu proses Agent (beberapa model bergiliran) di latar belakang.

        Jawaban langsung berisi {"sesi": ...}; event-nya dibaca lewat GET /api/agent/event. Proses
        tetap berjalan walau halaman web ditutup; menutup halaman tidak membatalkannya (Stop
        lewat /api/stop)."""
        tugas = (b.get("teks") or "").strip()
        if not tugas:
            return self._json(400, {"error": "Perintah kosong"})
        if len(tugas) > tim.MAKS_TUGAS:
            return self._json(400, {"error": f"Perintah terlalu panjang (maks {tim.MAKS_TUGAS} karakter)"})
        lanjut = b.get("lanjut")
        if lanjut is not None and not tim.id_valid(lanjut):
            return self._json(400, {"error": "id proyek tidak valid"})
        try:
            tersedia = {m["id"] for m in mdl.daftar_model()}
        except Exception:  # noqa: BLE001
            return self._json(502, {"error": "Tidak bisa menghubungi llama-server"})
        cfg, err = tim.siapkan_cfg(b, tersedia)
        if err:
            return self._json(400, {"error": err})
        with state.S_LOCK:
            if state.S["status"] in ("siap", "memuat"):
                return self._json(409, {"error": "Sesi chat masih memuat model. Akhiri dulu "
                                                 "di halaman Chat (tombol Selesai)."})
        if not state.GEN_LOCK.acquire(blocking=False):
            return self._json(409, {"error": "Masih ada proses berjalan"})
        diserahkan = False   # True setelah thread kerja berjalan: dialah yang melepas kunci
        sesi = None
        try:
            mdl.sentuh()
            lg.log("CHAT", f"agent: {tugas[:100]}")
            lg.log("INFO", f"Agent {cfg['mode']} model: perencana={cfg['model_p']}, "
                        f"pelaksana={cfg['model_e']}, pemeriksa={cfg['model_c']}, "
                        f"maks {cfg['maks']} putaran, uji jalan "
                        + ("DIIZINKAN" if cfg["uji"] else "mati"))
            ctx = kts.Ctx(queue.Queue(), threading.Event())
            ctx.skill = ("tanpa",)
            state.AKTIF["ctx"] = ctx
            with state.AGENT_COND:      # buffer baru hanya setelah kunci didapat: 409 tidak menghapus yang lama
                sesi = secrets.token_hex(4)
                state.AGENT.update(sesi=sesi, id=None, tugas=" ".join(tugas.split())[:200], events=[],
                             awal=0, aktif=True, mulai=time.time(), status=None)

            def kerja():
                try:
                    for ev in tim.jalankan(tugas, cfg, ctx, lanjut):
                        agt.agent_tambah(sesi, ev)
                except Exception as e:  # noqa: BLE001
                    agt.agent_tambah(sesi, {"t": "error", "d": f"{type(e).__name__}: {e}"})
                finally:
                    with state.AGENT_COND:   # kunci dilepas sebelum 'aktif' dimatikan: klien bisa langsung mulai lagi
                        state.AKTIF["ctx"] = None
                        mdl.sentuh()
                        state.GEN_LOCK.release()
                        if state.AGENT["sesi"] == sesi:
                            state.AGENT["aktif"] = False
                        state.AGENT_COND.notify_all()

            threading.Thread(target=kerja, daemon=True).start()
            diserahkan = True
        finally:
            if not diserahkan:
                state.AKTIF["ctx"] = None
                with state.AGENT_COND:
                    if sesi and state.AGENT["sesi"] == sesi:
                        state.AGENT["aktif"] = False
                state.GEN_LOCK.release()
        self._json(200, {"ok": True, "sesi": sesi})

    def agent_event(self):
        """Long-poll event proses Agent: ?sesi=..&dari=N&tunggu=detik."""
        q = parse_qs(urlparse(self.path).query)

        def angka(nama, bawaan):
            try:
                return max(0, int((q.get(nama) or [bawaan])[0]))
            except (TypeError, ValueError):
                return bawaan
        sesi = (q.get("sesi") or [""])[0]
        hasil = agt.agent_baca(sesi, angka("dari", 0), min(angka("tunggu", 0), conf.AGENT_TUNGGU_MAKS))
        if hasil is None:
            return self._json(410, {"error": "Proses itu sudah tidak ada di server (aplikasi "
                                              "dimulai ulang atau proses baru sudah berjalan). "
                                              "Lihat hasilnya di Riwayat."})
        mdl.sentuh()
        self._json(200, hasil)

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
            lg.catat_event(ev)
            if hidup:
                try:
                    self.wfile.write((json.dumps(ev, ensure_ascii=False) + "\n").encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    hidup = False
                    ctx.batal.set()
                    lg.log("WARN", "Klien terputus, proses dibatalkan")


__all__ = ['STATIS', 'H']
