#!/usr/bin/env python3
"""agen.py - inti agen AI Asisten.

Berisi: klien llama-server dengan streaming, riwayat, dan loop agen
(function calling). Semua tool ada di src/tolls.py. Hanya library standar Python.
Dipakai oleh asisten.py (server web).
"""
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src import tolls  # noqa: E402 - kumpulan tool (src/tolls.py)

LLAMA_URL = os.environ.get("LLAMA_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
if LLAMA_URL.endswith("/v1"):
    LLAMA_URL = LLAMA_URL[:-3]
LOG_AKSI = Path(__file__).resolve().parent / "aksi.log"

MAX_OUTPUT = tolls.MAX_OUTPUT  # karakter maksimum hasil tool yang dikirim balik ke model
MAX_STEPS = 8        # maksimum putaran tool per pesan

SYSTEM_PROMPT = (
    "Kamu adalah asisten AI yang berjalan di Raspberry Pi 5 milik pengguna dan "
    "dapat mengakses sistemnya lewat tools. Jawabanmu tampil di chat web di HP.\n"
    "Aturan:\n"
    "1. Jawab dalam bahasa Indonesia, singkat dan jelas.\n"
    "2. Kalau butuh informasi atau tindakan di sistem, panggil tool. Jangan "
    "menebak atau mengarang hasil.\n"
    "3. Kerjakan langkah kecil satu per satu, lalu periksa hasilnya.\n"
    "4. Untuk tindakan berisiko (hapus, ubah konfigurasi, sudo) jelaskan dulu "
    "singkat.\n"
    "5. Setelah mendapat hasil tool, rangkum untuk pengguna.\n"
    "6. Jangan menginstal paket kecuali diminta pengguna. Kalau satu perintah "
    "gagal, coba cara lain yang sudah ada di sistem.\n"
    "7. Boleh memakai `kode` dan blok ``` untuk perintah atau kode.\n"
    "8. Pilih tool yang paling spesifik: cari_teks/cari_file untuk mencari, "
    "baca_file dengan dari_baris untuk bagian kode, edit_file untuk ubah kecil, "
    "tulis_file untuk file baru, info_sistem untuk suhu/RAM/disk, git_baca untuk "
    "status repo, hitung untuk angka. jalankan_perintah hanya jika tool lain tidak cukup.\n"
    "9. hapus hanya memindahkan ke ~/.sampah_asisten (bisa dipulihkan). Tool yang "
    "mengubah sesuatu meminta izin pengguna dulu.\n"
    "Tips Raspberry Pi: suhu CPU = `vcgencmd measure_temp`; RAM = `free -h`; "
    "disk = `df -h`; service = `systemctl status NAMA`; proses = "
    "`ps aux --sort=-%cpu | head`; throttling = `vcgencmd get_throttled`.\n"
    "Info: host={host}, user={user}, home={home}, waktu={waktu}."
)

TOOLS = tolls.skema()  # dibuat otomatis dari dekorator @tool di src/tolls.py

# Konteks 8192 token ~ 24000 karakter. Riwayat dibatasi menyesuaikan ukuran skema tool
# (makin banyak tool aktif, makin sedikit ruang riwayat), disisakan ruang untuk system
# prompt, jawaban (max_tokens 700), dan margin.
MAX_HISTORY = max(5000, min(12000, 24000 - 1800 - len(json.dumps(TOOLS)) - 2100 - 3000))


# --------------------------------------------------------------------------
# Util
# --------------------------------------------------------------------------
def potong(teks, batas=MAX_OUTPUT):
    if len(teks) <= batas:
        return teks
    return teks[:batas] + f"\n...[dipotong, {len(teks) - batas} karakter lagi]"


def catat(nama, args, hasil):
    try:
        with open(LOG_AKSI, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {nama} "
                    f"{json.dumps(args, ensure_ascii=False)[:300]} -> "
                    f"{hasil[:120]!r}\n")
    except OSError:
        pass


ringkas = tolls.ringkas


def buat_system():
    return SYSTEM_PROMPT.format(
        host=socket.gethostname(), user=os.environ.get("USER", "?"),
        home=str(Path.home()), waktu=datetime.now().strftime("%Y-%m-%d %H:%M"))


eksekusi = tolls.eksekusi  # eksekusi(nama, args, ctx) -> teks hasil


# --------------------------------------------------------------------------
# llama-server
# --------------------------------------------------------------------------
def llama(path, data=None, timeout=300):
    req = urllib.request.Request(
        LLAMA_URL + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def stream_chat(model, pesan, batal):
    """Generator potongan JSON dari llama-server (stream SSE)."""
    body = {"model": model, "messages": pesan, "tools": TOOLS,
            "tool_choice": "auto", "temperature": 0.3, "max_tokens": 700,
            "stream": True, "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(
        LLAMA_URL + "/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        for mentah in r:
            if batal.is_set():
                break  # keluar dari 'with' menutup koneksi dan menghentikan generasi
            baris = mentah.decode("utf-8", "replace").strip()
            if not baris.startswith("data:"):
                continue
            isi = baris[5:].strip()
            if isi == "[DONE]":
                break
            try:
                yield json.loads(isi)
            except json.JSONDecodeError:
                continue


# --------------------------------------------------------------------------
# Riwayat & loop agen
# --------------------------------------------------------------------------
def ukuran(pesan):
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in pesan)


def siapkan(riwayat):
    """Salinan riwayat yang dipangkas supaya muat di konteks model."""
    pesan = json.loads(json.dumps(riwayat))
    while ukuran(pesan) > MAX_HISTORY:
        idx = [i for i, m in enumerate(pesan) if m["role"] == "user"]
        if len(idx) < 2:
            break
        del pesan[idx[0]:idx[1]]
    if ukuran(pesan) > MAX_HISTORY:
        for m in pesan:
            if m["role"] == "tool" and len(m["content"]) > 300:
                m["content"] = m["content"][:300] + "...[dipotong]"
                if ukuran(pesan) <= MAX_HISTORY:
                    break
    return pesan


def giliran(riwayat, model, ctx):
    """Generator event untuk satu pesan pengguna.

    riwayat: daftar pesan (tanpa system), diubah di tempat.
    ctx: .auto, .batal (threading.Event), .konfirmasi(jenis, ringkas, detail)
    Event: pikir, token, info, tool, hasil, error, batal, batas, selesai.
    """
    sudah = set()  # tool+argumen yang sudah dijalankan (anti-loop)
    for langkah in range(MAX_STEPS):
        if ctx.batal.is_set():
            yield {"t": "batal"}
            return
        kirim = [{"role": "system", "content": buat_system()}] + siapkan(riwayat)
        teks, calls, timings = "", {}, None
        try:
            for ch in stream_chat(model, kirim, ctx.batal):
                if ch.get("timings"):
                    timings = ch["timings"]
                pil = (ch.get("choices") or [{}])[0]
                d = pil.get("delta") or {}
                r = d.get("reasoning_content")
                if r:
                    yield {"t": "pikir", "d": r}
                c = d.get("content")
                if c:
                    teks += c
                    yield {"t": "token", "d": c}
                for tc in d.get("tool_calls") or []:
                    i = tc.get("index", 0)
                    s = calls.setdefault(i, {"id": "", "type": "function",
                                             "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        s["id"] = tc["id"]
                    f = tc.get("function") or {}
                    if f.get("name"):
                        s["function"]["name"] = f["name"]
                    if f.get("arguments"):
                        s["function"]["arguments"] += f["arguments"]
        except urllib.error.HTTPError as e:
            yield {"t": "error",
                   "d": f"Server llama {e.code}: {e.read().decode(errors='replace')[:300]}"}
            return
        except Exception as e:  # noqa: BLE001
            yield {"t": "error", "d": f"{type(e).__name__}: {e}"}
            return

        if timings:
            yield {"t": "info", "tok_s": round(timings.get("predicted_per_second") or 0, 1),
                   "tok": timings.get("predicted_n") or 0}

        daftar = []
        for i in sorted(calls):
            c = calls[i]
            if not c["id"]:
                c["id"] = f"call_{langkah}_{i}"
            daftar.append(c)
        entri = {"role": "assistant", "content": teks}
        if daftar:
            entri["tool_calls"] = daftar
        if teks or daftar:
            riwayat.append(entri)

        if not daftar:
            if ctx.batal.is_set():
                yield {"t": "batal"}
            else:
                if not teks:
                    yield {"t": "error", "d": "Model tidak memberi jawaban."}
                yield {"t": "selesai"}
            return

        for c in daftar:
            nama = c["function"]["name"]
            try:
                args = json.loads(c["function"]["arguments"] or "{}")
            except json.JSONDecodeError:
                args = None
            ring = ringkas(nama, args) if isinstance(args, dict) else nama
            yield {"t": "tool", "id": c["id"], "nama": nama, "ringkas": ring}
            if ctx.batal.is_set():
                hasil = "DIBATALKAN oleh pengguna."
            elif not isinstance(args, dict):
                hasil = "ERROR: argumen bukan JSON object yang valid."
            else:
                kunci = nama + json.dumps(args, sort_keys=True, ensure_ascii=False)
                if kunci in sudah:
                    hasil = ("Tool dengan argumen yang sama sudah dijalankan, hasilnya "
                             "ada di atas. Jangan ulangi; berikan jawaban akhir sekarang.")
                else:
                    sudah.add(kunci)
                    hasil = eksekusi(nama, args, ctx)
            hasil = potong(hasil)
            catat(nama, args if isinstance(args, dict) else {}, hasil)
            yield {"t": "hasil", "id": c["id"], "d": hasil}
            riwayat.append({"role": "tool", "tool_call_id": c["id"], "content": hasil})

        if ctx.batal.is_set():
            yield {"t": "batal"}
            return
    yield {"t": "batas"}
