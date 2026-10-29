"""server_http.py - penangan HTTP: rute /api, file statis web, dan proses generasi di thread."""

import hmac
import io
import json
import queue
import re
import secrets
import threading
import time
import traceback
import zipfile
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import agen
import tim
from . import server_agent as agt
from . import server_config as conf
from . import server_ctx as kts
from . import server_log as lg
from . import server_model as mdl
from . import server_prompt as prm
from . import server_chat as rwy
from . import server_handoff as ho
from . import server_state as state
from . import server_status as sts
from . import server_unggah as ung


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
    "/prompt.js": ("prompt.js", "application/javascript; charset=utf-8"),
    "/serahkan.css": ("serahkan.css", "text/css; charset=utf-8"),
    "/serahkan.js": ("serahkan.js", "application/javascript; charset=utf-8"),
    "/unggah.css": ("unggah.css", "text/css; charset=utf-8"),
    "/unggah.js": ("unggah.js", "application/javascript; charset=utf-8"),
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
        mu = re.fullmatch(r"/api/agent/run/([0-9]{8}-[0-9]{6}-[0-9a-f]{4})/unduh", path)
        if metode == "GET" and mu:
            return self.agent_unduh(mu.group(1))
        if metode == "DELETE" and m:
            try:
                tim.hapus_run(m.group(1))
            except PermissionError as e:
                return self._json(409, {"error": str(e)})
            lg.log("INFO", f"Proses Agent dihapus: {m.group(1)}")
            return self._json(200, {"ok": True})
        if path == "/api/prompt" and metode == "GET":
            return self._json(200, {"prompt": prm.daftar_prompt(), "bawaan": conf.PROMPT_BAWAAN,
                                    "abaikan": prm.berkas_diabaikan()})
        if path == "/api/prompt/ekspor" and metode == "GET":
            return self.prompt_ekspor()
        if path == "/api/unggah" and metode == "POST":
            return self.unggah()
        if path == "/api/unggah" and metode == "GET":
            return self.unggah_daftar()
        if path == "/api/unggah/hapus" and metode == "POST":
            return self.unggah_hapus()
        if metode == "POST":
            b = self._body()
            if path == "/api/prompt":
                try:
                    return self._json(200, {"ok": True, "baru": prm.tambah_prompt(b.get("nama"), b.get("isi"), b.get("catatan")),
                                            "prompt": prm.daftar_prompt()})
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
            if path == "/api/prompt/ubah":
                try:
                    baru = prm.ubah_prompt(str(b.get("id") or ""), b.get("nama"), b.get("isi"), b.get("catatan"))
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
                if baru is None:
                    return self._json(404, {"error": "Prompt tidak ditemukan"})
                return self._json(200, {"ok": True, "baru": baru, "prompt": prm.daftar_prompt()})
            if path == "/api/prompt/impor":
                try:
                    hasil = prm.impor(b.get("teks") if isinstance(b.get("teks"), str) else "")
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
                return self._json(200, dict(hasil, ok=True, prompt=prm.daftar_prompt()))
            if path == "/api/prompt/hapus":
                try:
                    ada = prm.hapus_prompt(str(b.get("id") or ""))
                except ValueError as e:
                    return self._json(400, {"error": str(e)})
                return self._json(200 if ada else 404, {"ok": ada, "prompt": prm.daftar_prompt()})
            if path == "/api/handoff/ringkas":
                return self.handoff_ringkas(b)
            if path == "/api/handoff/kirim":
                return self.handoff_kirim(b)
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
                rwy.hapus_lampiran(cid)
                lg.log("INFO", f"Obrolan dihapus: {cid}")
                return self._json(200, {"ok": True})
        self._json(404, {"error": "Tidak ditemukan"})

    # ------------------------------------------------------------ serah terima chat -> Agent
    def handoff_ringkas(self, b):
        """Susun brief dari diskusi obrolan untuk disetujui pengguna (belum menjalankan apa pun)."""
        cid = b.get("id")
        try:
            chat = rwy.baca_chat(cid)
        except FileNotFoundError:
            return self._json(404, {"error": "Obrolan tidak ditemukan"})
        with state.S_LOCK:
            siap, model = state.S["status"] == "siap", state.S["model"]
        if not siap:
            return self._json(409, {"error": "Model belum dimuat. Pilih model dulu."})
        if not any(m.get("role") == "user" for m in chat.get("pesan", [])):
            return self._json(400, {"error": "Belum ada diskusi yang bisa diringkas."})
        if not state.GEN_LOCK.acquire(blocking=False):
            return self._json(409, {"error": "Model sedang menjawab. Tunggu sebentar."})
        try:
            mdl.sentuh()
            isi, otomatis = ho.ringkas_diskusi(chat, model)
        finally:
            state.GEN_LOCK.release()
        lamp = ho.lampiran_chat(cid)
        jalur, alasan = tim.pilih_jalur(isi, "otomatis", bool(lamp))
        self._json(200, {"ringkasan": isi, "otomatis": otomatis, "lampiran": lamp, "jalur": jalur,
                         "jalur_label": tim.JALUR[jalur]["label"], "alasan": alasan,
                         "lanjut": ho.hasil_terakhir(chat)})

    def handoff_kirim(self, b):
        """Serahkan brief yang sudah disetujui ke Agent; hasilnya ditulis balik ke obrolan."""
        cid = b.get("id")
        tugas = (b.get("tugas") or "").strip()
        if not tugas:
            return self._json(400, {"error": "Brief kosong"})
        if len(tugas) > tim.MAKS_TUGAS:
            return self._json(400, {"error": f"Brief terlalu panjang (maks {tim.MAKS_TUGAS} karakter)"})
        try:
            tersedia = {m["id"] for m in mdl.daftar_model()}
        except Exception:  # noqa: BLE001
            return self._json(502, {"error": "Tidak bisa menghubungi llama-server"})
        cfg, err = tim.siapkan_cfg(b, tersedia)
        if err:
            return self._json(400, {"error": err})
        lanjut = b.get("lanjut") or None
        if lanjut and not (tim.id_valid(lanjut) and (Path(tim.KERJA) / lanjut / "hasil").is_dir()):
            return self._json(400, {"error": "Hasil Agent sebelumnya tidak ditemukan"})
        try:
            sesi = ho.serahkan(cid, tugas, cfg, b.get("muat_ulang") is not False, lanjut)
        except FileNotFoundError:
            return self._json(404, {"error": "Obrolan tidak ditemukan"})
        except agt.ProsesGagal as e:
            return self._json(e.kode, {"error": e.pesan})
        self._json(200, {"ok": True, "sesi": sesi})

    def prompt_ekspor(self):
        """Unduh satu prompt sebagai berkas JSON yang siap dibagikan (?id=...)."""
        pid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
        d = prm.ekspor(pid)
        if d is None:
            return self._json(404, {"error": "Prompt tidak ditemukan"})
        self._kirim_unduhan((json.dumps(d, ensure_ascii=False, indent=1) + "\n").encode("utf-8"),
                            "application/json; charset=utf-8", pid + ".json")

    def agent_unduh(self, run_id):
        """Unduh hasil sebuah proses Agent: satu berkas (?berkas=nama) atau semuanya sebagai zip."""
        folder = Path(tim.KERJA) / run_id / "hasil"
        if not folder.is_dir():
            return self._json(404, {"error": "Hasil tidak ditemukan"})
        berkas = tim.baca_proyek(folder, tim.MAKS_BACA)
        nama = (parse_qs(urlparse(self.path).query).get("berkas") or [""])[0]
        if nama:
            try:
                nama = tim.aman_nama(nama)
            except ValueError:
                return self._json(400, {"error": "Nama berkas tidak valid"})
            isi = dict(berkas).get(nama)
            if isi is None:
                return self._json(404, {"error": "Berkas tidak ditemukan"})
            return self._kirim_unduhan(isi.encode("utf-8"), "text/plain; charset=utf-8", nama.replace("/", "_"))
        if not berkas:
            return self._json(404, {"error": "Hasil kosong"})
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for rel, isi in berkas:
                z.writestr(rel, isi)
        judul = ""
        try:
            judul = tim.baca_run(run_id).get("judul") or ""
        except (FileNotFoundError, OSError, ValueError):
            pass
        slug = re.sub(r"[^A-Za-z0-9_-]+", "-", judul).strip("-")[:40] or run_id
        self._kirim_unduhan(buf.getvalue(), "application/zip", slug + ".zip")

    def _kirim_unduhan(self, data, tipe, nama):
        try:
            self.send_response(200)
            self.send_header("Content-Type", tipe)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % nama)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def _id_paket(self):
        return (parse_qs(urlparse(self.path).query).get("paket") or [""])[0]

    def unggah(self):
        """Terima satu berkas (teks/kode atau zip) sebagai byte mentah.

        POST /api/unggah[?paket=ID] dengan header X-Nama (nama berkas, URL-encoded). Tanpa paket,
        paket baru dibuat. Jawaban: paket, berkas (isi paket), baru, dilewati (beserta alasan)."""
        try:
            n = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            n = -1
        if n < 0:
            return self._json(411, {"error": "Content-Length wajib ada"})
        if n > conf.MAKS_UNGGAH_BYTE:
            return self._json(413, {"error": "Unggahan terlalu besar (maks %d MB)"
                                             % (conf.MAKS_UNGGAH_BYTE // 1_000_000)})
        data = self.rfile.read(n)
        nama = unquote(self.headers.get("X-Nama", ""))
        paket, baru = self._id_paket(), False
        try:
            if not paket:
                paket, baru = ung.baru_paket(), True
            hasil = ung.terima(paket, nama, data)
        except FileNotFoundError:
            return self._json(404, {"error": "Paket unggahan tidak ditemukan (sudah kedaluwarsa). Unggah lagi."})
        except ValueError as e:
            if baru:
                ung.buang(paket)
            return self._json(400, {"error": str(e)})
        berkas = ung.daftar(paket)
        if baru and not berkas:                  # tidak ada yang diterima: jangan tinggalkan paket kosong
            ung.buang(paket)
            paket = None
        lg.log("INFO", f"Unggahan {nama[:60]}: {len(hasil['baru'])} berkas diterima, "
                       f"{len(hasil['dilewati']) + hasil.get('lainnya', 0)} dilewati")
        self._json(200, dict(hasil, paket=paket, berkas=berkas))

    def unggah_daftar(self):
        paket = self._id_paket()
        try:
            return self._json(200, {"paket": paket, "berkas": ung.daftar(paket)})
        except (FileNotFoundError, ValueError):
            return self._json(404, {"error": "Paket unggahan tidak ditemukan"})

    def unggah_hapus(self):
        b = self._body()
        try:
            ung.hapus(b.get("paket"), b.get("nama") or None)
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        try:
            berkas = ung.daftar(b.get("paket"))
        except (FileNotFoundError, ValueError):
            berkas = []
        self._json(200, {"ok": True, "berkas": berkas})

    def pilih(self, b):
        nama = b.get("model")
        skill = b.get("skill")
        skill = agen.tolls.normal_skill(skill)   # boleh beberapa skill sekaligus
        try:
            pilihan_prompt = prm.rapikan_pilihan(b.get("prompt"))
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        with state.S_LOCK:
            if state.S["status"] == "memuat":
                return self._json(409, {"error": "Model sedang dimuat"})
            if state.GEN_LOCK.locked():
                return self._json(409, {"error": "Masih ada proses berjalan"})
            state.S["status"] = "memuat"
            state.S["pesan"] = f"Menyiapkan {nama} ..."
            state.S["skill"] = skill
            state.S["prompt"] = pilihan_prompt
        lg.log("INFO", f"Skill dipilih: {'+'.join(skill)} ({len(agen.tools_untuk(skill))} tool)"
                       + (f", prompt: {', '.join(prm.rakit(pilihan_prompt)[1]) or 'tanpa prompt (murni)'}"
                          if prm.berlaku(skill) else ""))
        mdl.sentuh()
        threading.Thread(target=mdl.muat_model, args=(nama,), daemon=True).start()
        self._json(200, {"ok": True})

    def kirim(self, b):
        cid, teks = b.get("id"), (b.get("teks") or "").strip()
        paket = b.get("unggahan") or None
        with state.S_LOCK:
            siap, model, skill = state.S["status"] == "siap", state.S["model"], state.S["skill"]
            pilihan_prompt = state.S["prompt"]
        if not siap:
            return self._json(409, {"error": "Model belum dimuat. Pilih model dulu."})
        if not teks and not paket:
            return self._json(400, {"error": "Pesan kosong"})
        entri, ringkas = {"role": "user", "content": teks}, []
        if paket:       # lampiran dibaca sebelum kunci diambil: galat di sini tidak perlu melepas apa pun
            try:
                teks = teks or "Tolong baca berkas terlampir."
                isi, ringkas = ung.susun_lampiran_chat(paket, ung.anggaran_chat(skill, teks))
            except FileNotFoundError:
                return self._json(404, {"error": "Berkas unggahan tidak ditemukan (kedaluwarsa). Unggah lagi."})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            entri = {"role": "user", "content": teks + "\n\n" + isi, "tampil": teks, "lampiran": ringkas}
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
            chat["pesan"].append(entri)
            if chat.get("judul") in (None, "", "Obrolan baru"):
                chat["judul"] = teks[:40]
            rwy.simpan_chat(chat)
            if paket:
                try:
                    ho.simpan_lampiran(cid, paket)      # disimpan: bahan kerja bila obrolan diserahkan ke Agent
                except Exception as e:  # noqa: BLE001 - gagal menyimpan lampiran tidak membatalkan pesan
                    lg.log("WARN", f"Lampiran tidak disimpan: {type(e).__name__}: {e}")
                ung.buang(paket)
            mdl.sentuh()
            lg.log("CHAT", f"kamu: {teks[:100]}" + (f" (+{len(ringkas)} berkas)" if ringkas else ""))

            q = queue.Queue()
            if ringkas:
                q.put({"t": "lampiran", "berkas": ringkas})
            ctx = kts.Ctx(q, threading.Event())
            ctx.skill = skill
            # prompt pilihan hanya berlaku untuk skill tanpa akses sistem (lihat server_prompt.berlaku)
            ctx.prompt_dasar = prm.rakit(pilihan_prompt)[0] if prm.berlaku(skill) else None
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
                # tanpa prompt sama sekali (murni) = tanpa ringkasan otomatis juga: tidak ada yang disisipkan
                memori = None if agen.dasar_dari(ctx) == "" else chat
                for ev in agen.giliran(chat["pesan"], model, ctx, memori):
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
        paket, bahan = b.get("unggahan") or None, None
        if paket:
            try:
                bahan = ung.bahan_dir(paket)
            except FileNotFoundError:
                return self._json(404, {"error": "Berkas unggahan tidak ditemukan (kedaluwarsa). Unggah lagi."})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
        try:
            tersedia = {m["id"] for m in mdl.daftar_model()}
        except Exception:  # noqa: BLE001
            return self._json(502, {"error": "Tidak bisa menghubungi llama-server"})
        cfg, err = tim.siapkan_cfg(b, tersedia)
        if err:
            return self._json(400, {"error": err})
        try:
            sesi = agt.mulai_proses(tugas, cfg, lanjut, bahan, paket)
        except agt.ProsesGagal as e:
            return self._json(e.kode, {"error": e.pesan})
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
