#!/usr/bin/env python3
"""agen.py - inti agen AI Asisten.

Berisi: klien llama-server dengan streaming, riwayat, dan loop agen
(function calling). Semua tool ada di src/tolls.py. Hanya library standar Python.
Dipakai oleh asisten.py (server web).
"""
import json
import os
import re
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

# Peringkasan riwayat: pesan lama diganti ringkasan pendek (riwayat asli tetap utuh).
RINGKAS_AMBANG = 0.7        # mulai meringkas saat riwayat > 70% MAX_HISTORY
RINGKAS_SISA_GILIRAN = 2    # giliran terakhir yang selalu dikirim utuh
RINGKAS_MAKS_KARAKTER = 1200
PROMPT_RINGKAS = (
    "Kamu meringkas percakapan antara pengguna dan asisten AI untuk dijadikan ingatan. "
    "Tulis ringkasan padat dalam bahasa Indonesia, poin-poin singkat, maksimal 150 kata. "
    "Pertahankan: tujuan pengguna, path file dan nama penting, angka, keputusan, hasil "
    "tool yang penting, dan hal yang belum selesai. Buang basa-basi. "
    "Tulis hanya ringkasannya."
)

SYSTEM_PROMPT = (
    "Kamu adalah asisten AI yang berjalan di Raspberry Pi 5 milik pengguna dan "
    "dapat mengakses sistemnya lewat tools. Jawabanmu tampil di chat web di HP.\n"
    "Aturan:\n"
    "1. Jawab dalam bahasa Indonesia, singkat dan jelas.\n"
    "2. Panggil tool HANYA kalau pengguna meminta informasi atau tindakan di "
    "sistem (file, folder, perintah, suhu, RAM, git, dll). Untuk sapaan, "
    "ucapan terima kasih, pertanyaan umum, penjelasan, atau obrolan biasa, "
    "JAWAB LANGSUNG tanpa tool. Jangan menebak atau mengarang hasil.\n"
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

# Gerbang tool: model kecil sering asal memanggil tool bahkan untuk "halo".
# Di langkah pertama tiap pesan, tool hanya dikirim ke model kalau pesan pengguna
# tampak butuh akses sistem. Matikan dengan ASISTEN_GERBANG=0.
GERBANG = os.environ.get("ASISTEN_GERBANG", "1") != "0"
KATA_TOOL = re.compile(
    r"\b(file|berkas|folder|direktori|path|baca|buka|tulis|buat|edit|ubah|ganti|"
    r"hapus|salin|pindah|cari|temukan|jalankan|eksekusi|perintah|cek|periksa|"
    r"lihat|tampilkan|daftar|suhu|panas|cpu|memori|disk|proses|jaringan|wifi|"
    r"layanan|service|systemctl|commit|push|pull|repo|unduh|download|http|"
    r"arsip|ekstrak|hitung|instal|install|restart|reboot|sudo|script|skrip|"
    r"kode|baterai|kipas|uptime|sistem|raspberry|"
    r"(?:ram|ip|pi|git|log|port|zip|url|ups|pip|apt|kill|matikan)\b)"
    r"|\.(?:py|sh|txt|md|json|log|conf)\b|[/~$]", re.I)


def perlu_tool(teks, riwayat):
    """True jika pesan pengguna tampaknya butuh tool (atau lanjutan dari giliran bertool)."""
    if not GERBANG:
        return True
    if KATA_TOOL.search(teks or ""):
        return True
    # Pesan pendek ("lanjut", "ya", "coba lagi") setelah giliran yang memakai tool
    if len((teks or "").split()) <= 4:
        for m in riwayat[-8:-1]:
            if m.get("role") == "tool":
                return True
    return False


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


def buat_system(ringkasan=""):
    teks = SYSTEM_PROMPT.format(
        host=socket.gethostname(), user=os.environ.get("USER", "?"),
        home=str(Path.home()), waktu=datetime.now().strftime("%Y-%m-%d %H:%M"))
    if ringkasan:
        teks += ("\nRingkasan percakapan sebelumnya (pesan lama sudah diringkas, "
                 "gunakan sebagai ingatan):\n" + ringkasan)
    return teks


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


def stream_chat(model, pesan, batal, pakai_tools=True):
    """Generator potongan JSON dari llama-server (stream SSE)."""
    body = {"model": model, "messages": pesan, "temperature": 0.3,
            "max_tokens": 700, "stream": True,
            "chat_template_kwargs": {"enable_thinking": False}}
    if pakai_tools:
        body["tools"] = TOOLS
        body["tool_choice"] = "auto"
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


def _transkrip(pesan):
    """Ubah pesan menjadi teks polos untuk diringkas (bagian terbaru dipertahankan)."""
    baris = []
    for m in pesan:
        peran = m.get("role")
        isi = m.get("content") or ""
        if peran == "user":
            baris.append("Pengguna: " + isi[:600])
        elif peran == "assistant":
            teks = isi[:600]
            for c in m.get("tool_calls") or []:
                fn = c.get("function") or {}
                teks += " [tool %s %s]" % (fn.get("name"), (fn.get("arguments") or "")[:150])
            baris.append("Asisten: " + teks.strip())
        elif peran == "tool":
            baris.append("Hasil tool: " + isi[:250])
    return "\n".join(baris)[-7000:]


def buat_ringkasan(lama, pesan, model):
    """Minta model meringkas (ringkasan lama + pesan baru). Kosong jika gagal."""
    isi = ""
    if lama:
        isi += "Ringkasan sebelumnya:\n" + lama + "\n\n"
    isi += ("Percakapan baru:\n" + _transkrip(pesan)
            + "\n\nTulis ringkasan gabungan yang diperbarui.")
    body = {"model": model, "temperature": 0.2, "max_tokens": 350, "stream": False,
            "messages": [{"role": "system", "content": PROMPT_RINGKAS},
                         {"role": "user", "content": isi}],
            "chat_template_kwargs": {"enable_thinking": False}}
    try:
        d = llama("/v1/chat/completions", body, timeout=300)
        teks = (d["choices"][0]["message"].get("content") or "").strip()
    except Exception:  # noqa: BLE001 - gagal meringkas bukan error fatal
        return ""
    return teks[:RINGKAS_MAKS_KARAKTER]


def ringkas_bila_perlu(riwayat, model, memori, ctx):
    """Generator event. Meringkas pesan lama jika riwayat mendekati batas konteks.

    memori: dict obrolan; hasilnya disimpan di memori["ringkasan"] =
    {"teks": ..., "sampai": N} (N = jumlah pesan awal yang sudah diwakili ringkasan).
    Riwayat asli (riwayat) tidak diubah.
    """
    r = memori.get("ringkasan") or {}
    mulai = r.get("sampai", 0)
    if mulai > len(riwayat):  # riwayat berubah di luar dugaan: mulai ulang
        memori.pop("ringkasan", None)
        r, mulai = {}, 0
    if ukuran(riwayat[mulai:]) + len(r.get("teks", "")) <= RINGKAS_AMBANG * MAX_HISTORY:
        return
    idx = [i for i in range(mulai, len(riwayat)) if riwayat[i]["role"] == "user"]
    if len(idx) <= RINGKAS_SISA_GILIRAN:
        return  # tidak ada giliran lama yang bisa diringkas
    potong = idx[-RINGKAS_SISA_GILIRAN]
    gagal = memori.get("ringkas_gagal")
    if gagal is not None and len(riwayat) - gagal < 6:
        return  # baru saja gagal; jangan coba terus-menerus
    if ctx.batal.is_set():
        return
    yield {"t": "ringkas", "d": "Meringkas percakapan lama ..."}
    teks = buat_ringkasan(r.get("teks", ""), riwayat[mulai:potong], model)
    if not teks:
        memori["ringkas_gagal"] = len(riwayat)
        yield {"t": "ringkas", "d": "Gagal meringkas; riwayat lama dipangkas biasa."}
        return
    memori["ringkasan"] = {"teks": teks, "sampai": potong}
    memori.pop("ringkas_gagal", None)
    yield {"t": "ringkas",
           "d": f"Riwayat diringkas: {potong - mulai} pesan lama jadi {len(teks)} karakter."}


def giliran(riwayat, model, ctx, memori=None):
    """Generator event untuk satu pesan pengguna.

    riwayat: daftar pesan (tanpa system), diubah di tempat.
    ctx: .auto, .batal (threading.Event), .konfirmasi(jenis, ringkas, detail)
    memori: dict obrolan (opsional); jika diberikan, pesan lama diringkas otomatis
            dan ringkasannya disimpan di memori["ringkasan"].
    Event: ringkas, pikir, token, info, tool, hasil, error, batal, batas, selesai.
    """
    if memori is not None:
        yield from ringkas_bila_perlu(riwayat, model, memori, ctx)
    sudah = set()  # tool+argumen yang sudah dijalankan (anti-loop)
    teks_user = next((m.get("content") or "" for m in reversed(riwayat)
                      if m.get("role") == "user"), "")
    tool_aktif = perlu_tool(teks_user, riwayat)
    for langkah in range(MAX_STEPS):
        if ctx.batal.is_set():
            yield {"t": "batal"}
            return
        r = (memori or {}).get("ringkasan") or {}
        mulai = min(r.get("sampai", 0), len(riwayat))
        kirim = ([{"role": "system", "content": buat_system(r.get("teks", ""))}]
                 + siapkan(riwayat[mulai:]))
        teks, calls, timings = "", {}, None
        try:
            for ch in stream_chat(model, kirim, ctx.batal, tool_aktif):
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
