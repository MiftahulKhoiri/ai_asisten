#!/usr/bin/env python3
"""ai_asisten - asisten AI lokal berbasis CLI untuk Raspberry Pi.

Terhubung ke llama-server (API kompatibel OpenAI) dan memakai function calling
supaya model bisa menjalankan perintah shell, membaca/menulis file, dan melihat
isi folder. Hanya memakai library standar Python (tanpa pip install).

Contoh:
    python3 asisten.py                          # mode interaktif
    python3 asisten.py "cek suhu CPU"           # sekali jalan
    python3 asisten.py --auto "lihat isi ~/projects"   # tanpa konfirmasi
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

BASE_URL = os.environ.get("LLAMA_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
if BASE_URL.endswith("/v1"):
    BASE_URL = BASE_URL[:-3]
DEFAULT_MODEL = os.environ.get("ASISTEN_MODEL", "Qwen_Qwen3-1.7B-Q4_K_M")
LOG_FILE = Path(__file__).resolve().parent / "aksi.log"

MAX_OUTPUT = 2000    # karakter maksimum hasil tool yang dikirim balik ke model
MAX_HISTORY = 12000  # karakter maksimum riwayat (konteks server hanya 8192 token)
MAX_STEPS = 8        # maksimum putaran tool per perintah
CMD_TIMEOUT = 60     # detik, batas waktu satu perintah shell

AUTO = False  # True = tidak tanya konfirmasi (sudo tetap selalu tanya)

# Perintah yang SELALU diblokir, bahkan dalam mode --auto.
BAHAYA = [
    r"\brm\s+(-\S+\s+)*(/|/\*|~|~/|\$HOME)(\s|$)",
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\b.*\bof=/dev/",
    r">\s*/dev/(sd|nvme|mmcblk)",
    r":\(\)\s*\{",
    r"\b(shutdown|reboot|poweroff|halt)\b",
    r"\bchmod\s+-R\s+\S+\s+/(\s|$)",
]

# Perintah yang SELALU minta konfirmasi, bahkan dalam mode --auto.
KONFIRMASI_SELALU = [
    r"\bsudo\b",
    r"\b(apt|apt-get|dpkg|pip3?|npm)\s+(install|remove|purge|uninstall|upgrade)\b",
]

SYSTEM_PROMPT = (
    "Kamu adalah asisten AI yang berjalan di Raspberry Pi 5 milik pengguna dan "
    "dapat mengakses sistemnya lewat tools.\n"
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
    "Tips Raspberry Pi: suhu CPU = `vcgencmd measure_temp`; RAM = `free -h`; "
    "disk = `df -h`; service = `systemctl status NAMA`; proses = "
    "`ps aux --sort=-%cpu | head`; throttling = `vcgencmd get_throttled`.\n"
    "Info: host={host}, user={user}, home={home}, waktu={waktu}."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "jalankan_perintah",
        "description": "Jalankan satu perintah shell (bash) di Raspberry Pi dan "
                       "kembalikan outputnya.",
        "parameters": {"type": "object", "properties": {
            "perintah": {"type": "string", "description": "perintah bash"}},
            "required": ["perintah"]}}},
    {"type": "function", "function": {
        "name": "baca_file",
        "description": "Baca isi file teks.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "path file"},
            "mulai": {"type": "integer", "description": "offset byte awal, default 0"},
            "panjang": {"type": "integer", "description": "jumlah byte, default 2000"}},
            "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "tulis_file",
        "description": "Tulis (timpa) file dengan isi lengkap. File lama dicadangkan "
                       "sebagai .bak.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "path file"},
            "isi": {"type": "string", "description": "isi file lengkap"}},
            "required": ["path", "isi"]}}},
    {"type": "function", "function": {
        "name": "daftar_folder",
        "description": "Tampilkan isi sebuah folder.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string", "description": "path folder, default home"}},
            "required": []}}},
]


# --------------------------------------------------------------------------
# Util
# --------------------------------------------------------------------------
def potong(teks, batas=MAX_OUTPUT):
    if len(teks) <= batas:
        return teks
    return teks[:batas] + f"\n...[dipotong, {len(teks) - batas} karakter lagi]"


def tanya(prompt):
    try:
        jawab = input(f"{prompt} [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return jawab in ("y", "ya", "yes")


def catat(nama, args, hasil):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {nama} "
                    f"{json.dumps(args, ensure_ascii=False)[:300]} -> "
                    f"{hasil[:120]!r}\n")
    except OSError:
        pass


def ringkas(nama, args):
    if nama == "jalankan_perintah":
        return "$ " + str(args.get("perintah", ""))
    if nama == "tulis_file":
        return f"tulis {args.get('path', '')} ({len(str(args.get('isi', '')))} karakter)"
    return f"{nama} {args.get('path', '')}".strip()


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
def t_jalankan_perintah(perintah):
    if not perintah.strip():
        return "ERROR: perintah kosong."
    for pola in BAHAYA:
        if re.search(pola, perintah):
            return "DITOLAK: perintah ini masuk daftar berbahaya dan diblokir."
    wajib = any(re.search(pola, perintah) for pola in KONFIRMASI_SELALU)
    if wajib or not AUTO:
        if not tanya("  Jalankan?"):
            return "DIBATALKAN oleh pengguna."
    try:
        p = subprocess.run(
            perintah, shell=True, executable="/bin/bash", capture_output=True,
            text=True, timeout=CMD_TIMEOUT, cwd=Path.home(),
            stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return f"GAGAL: melebihi batas waktu {CMD_TIMEOUT} detik."
    out = (p.stdout + p.stderr).strip() or "(tidak ada output)"
    return f"exit code {p.returncode}\n{out}"


def t_baca_file(path, mulai=0, panjang=MAX_OUTPUT):
    p = Path(path).expanduser()
    if not p.is_file():
        return f"ERROR: bukan file atau tidak ada: {p}"
    mulai = max(int(mulai), 0)
    panjang = min(int(panjang), MAX_OUTPUT)
    with open(p, "rb") as f:
        f.seek(mulai)
        data = f.read(panjang)
    total = p.stat().st_size
    return (f"[byte {mulai}-{mulai + len(data)} dari {total}]\n"
            + data.decode("utf-8", errors="replace"))


def t_tulis_file(path, isi):
    p = Path(path).expanduser()
    ada = p.exists()
    if not AUTO:
        info = "menimpa file lama" if ada else "file baru"
        if not tanya(f"  Tulis {len(isi)} karakter ke {p} ({info})?"):
            return "DIBATALKAN oleh pengguna."
    if ada:
        shutil.copy2(p, str(p) + ".bak")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(isi, encoding="utf-8")
    return f"Berhasil menulis {p} ({len(isi)} karakter)." + (
        " Cadangan: .bak" if ada else "")


def t_daftar_folder(path="."):
    p = Path(path or ".").expanduser()
    if not p.is_dir():
        return f"ERROR: bukan folder: {p}"
    item = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    if not item:
        return f"{p}: (kosong)"
    baris = [x.name + ("/" if x.is_dir() else "") for x in item[:200]]
    ekstra = f"\n... dan {len(item) - 200} lainnya" if len(item) > 200 else ""
    return f"{p}:\n" + "\n".join(baris) + ekstra


def eksekusi(nama, args):
    try:
        if nama == "jalankan_perintah":
            return t_jalankan_perintah(str(args.get("perintah", "")))
        if nama == "baca_file":
            return t_baca_file(args.get("path", ""), args.get("mulai", 0),
                               args.get("panjang", MAX_OUTPUT))
        if nama == "tulis_file":
            return t_tulis_file(args.get("path", ""), str(args.get("isi", "")))
        if nama == "daftar_folder":
            return t_daftar_folder(args.get("path", "."))
    except Exception as e:  # noqa: BLE001 - kirim error apa adanya ke model
        return f"ERROR: {type(e).__name__}: {e}"
    return f"ERROR: tool tidak dikenal: {nama}"


# --------------------------------------------------------------------------
# Server llama
# --------------------------------------------------------------------------
def http(path, data=None, timeout=300):
    req = urllib.request.Request(
        BASE_URL + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def status_model(model):
    daftar = http("/v1/models", timeout=10)["data"]
    info = next((m for m in daftar if m["id"] == model), None)
    if info is None:
        sys.exit("Model tidak ditemukan. Tersedia: "
                 + ", ".join(m["id"] for m in daftar))
    return (info.get("status") or {}).get("value")


def pastikan_model(model):
    """Muat model jika server berjalan di router mode (--no-models-autoload)."""
    try:
        status = status_model(model)
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"Tidak bisa terhubung ke llama-server di {BASE_URL}: {e}")
    if status in (None, "loaded"):
        return
    if status != "loading":
        print(f"Memuat model {model} ...")
        http("/models/load", {"model": model}, timeout=30)
    for _ in range(90):
        time.sleep(2)
        if status_model(model) == "loaded":
            print("Model siap.")
            return
    sys.exit("Model belum siap setelah 3 menit.")


def chat(model, pesan):
    return http("/v1/chat/completions", {
        "model": model, "messages": pesan, "tools": TOOLS,
        "tool_choice": "auto", "temperature": 0.3, "max_tokens": 700,
        "chat_template_kwargs": {"enable_thinking": False},
    }, timeout=600)


# --------------------------------------------------------------------------
# Riwayat & giliran
# --------------------------------------------------------------------------
def ukuran(riwayat):
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in riwayat)


def pangkas(riwayat):
    """Buang giliran tertua agar muat di konteks; sisakan system prompt."""
    while ukuran(riwayat) > MAX_HISTORY:
        idx = [i for i, m in enumerate(riwayat) if m["role"] == "user"]
        if len(idx) < 2:
            break
        del riwayat[idx[0]:idx[1]]
    if ukuran(riwayat) > MAX_HISTORY:
        for m in riwayat:
            if m["role"] == "tool" and len(m["content"]) > 300:
                m["content"] = m["content"][:300] + "...[dipotong]"
                if ukuran(riwayat) <= MAX_HISTORY:
                    break


def buat_system():
    return SYSTEM_PROMPT.format(
        host=socket.gethostname(), user=os.environ.get("USER", "?"),
        home=str(Path.home()), waktu=datetime.now().strftime("%Y-%m-%d %H:%M"))


def jalankan_giliran(model, riwayat):
    sudah = set()  # tool+argumen yang sudah dijalankan di giliran ini (anti-loop)
    for _ in range(MAX_STEPS):
        pangkas(riwayat)
        sys.stdout.write("  ... berpikir\r")
        sys.stdout.flush()
        resp = chat(model, riwayat)
        sys.stdout.write(" " * 20 + "\r")
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        entri = {"role": "assistant", "content": msg.get("content") or ""}
        if calls:
            entri["tool_calls"] = calls
        riwayat.append(entri)
        if not calls:
            teks = (msg.get("content") or "").strip()
            print(f"\n{teks}\n" if teks else "\n(model tidak memberi jawaban)\n")
            return
        for c in calls:
            fn = c.get("function", {})
            nama = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = None
            if not isinstance(args, dict):
                hasil = "ERROR: argumen bukan JSON object yang valid."
                args = {}
            else:
                kunci = nama + json.dumps(args, sort_keys=True, ensure_ascii=False)
                if kunci in sudah:
                    hasil = ("Tool dengan argumen yang sama sudah dijalankan, hasilnya "
                             "ada di atas. Jangan ulangi; berikan jawaban akhir sekarang.")
                else:
                    sudah.add(kunci)
                    print(f"  > {ringkas(nama, args)}")
                    hasil = eksekusi(nama, args)
            hasil = potong(hasil)
            catat(nama, args, hasil)
            riwayat.append({"role": "tool", "tool_call_id": c.get("id", ""),
                            "content": hasil})
    print("\n(Batas langkah tercapai. Beri perintah lanjutan jika perlu.)\n")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    global AUTO
    ap = argparse.ArgumentParser(
        description="Asisten AI lokal (llama-server) yang bisa mengakses Raspberry Pi.")
    ap.add_argument("perintah", nargs="*",
                    help="perintah sekali jalan; kosongkan untuk mode interaktif")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL,
                    help=f"id model di llama-server (default: {DEFAULT_MODEL})")
    ap.add_argument("--auto", action="store_true",
                    help="jalankan perintah & tulis file tanpa konfirmasi "
                         "(sudo & instal paket tetap tanya, perintah berbahaya tetap diblokir)")
    args = ap.parse_args()
    AUTO = args.auto

    os.chdir(Path.home())
    pastikan_model(args.model)
    riwayat = [{"role": "system", "content": buat_system()}]

    if args.perintah:
        riwayat.append({"role": "user", "content": " ".join(args.perintah)})
        try:
            jalankan_giliran(args.model, riwayat)
        except urllib.error.HTTPError as e:
            sys.exit(f"Error server {e.code}: {e.read().decode()[:300]}")
        return

    print(f"ai_asisten | model: {args.model} | server: {BASE_URL}")
    print(f"Mode: {'AUTO (tanpa konfirmasi)' if AUTO else 'konfirmasi sebelum aksi'}")
    print("Perintah: /reset  /auto  /keluar\n")
    while True:
        try:
            teks = input("kamu> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not teks:
            continue
        if teks in ("/keluar", "/exit", "/quit","/selesai",):
            break
        if teks == "/reset":
            riwayat = [{"role": "system", "content": buat_system()}]
            print("Riwayat dihapus.\n")
            continue
        if teks == "/auto":
            AUTO = not AUTO
            print(f"Mode AUTO: {'aktif' if AUTO else 'mati'}\n")
            continue
        riwayat.append({"role": "user", "content": teks})
        try:
            jalankan_giliran(args.model, riwayat)
        except KeyboardInterrupt:
            print("\nDibatalkan.\n")
        except urllib.error.HTTPError as e:
            print(f"Error server {e.code}: {e.read().decode()[:300]}\n")
        except Exception as e:  # noqa: BLE001
            print(f"Error: {type(e).__name__}: {e}\n")


if __name__ == "__main__":
    main()
