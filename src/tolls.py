#!/usr/bin/env python3
"""tolls.py - kumpulan tool AI Asisten (letakkan di src/tolls.py).

Cara menambah tool baru: tulis satu fungsi dengan dekorator @tool di bawah.
Skema untuk model dibuat otomatis, agen.py tidak perlu diubah.

    @tool("nama_tool", "deskripsi singkat",
          {"param": ("string", "penjelasan"),
           "mode": ("string", "pilihan", ["a", "b"])},      # enum opsional
          wajib=["param"])
    def nama_tool(ctx, param, mode="a"):
        return "teks hasil"

Kebijakan izin (ctx datang dari asisten.py):
  tool hanya-baca  -> tanpa izin
  tool pengubah    -> _izin(...)             : tanya kecuali mode AUTO
  tool berisiko    -> _izin(..., selalu=True): tanya SELALU, juga di mode AUTO

Variabel lingkungan (opsional):
  ASISTEN_TOOLS=dasar        skill bawaan: hanya 4 tool inti (hemat konteks model)
                             (di web, skill dipilih saat memilih model; boleh lebih dari satu)

Skill (bisa digabung): tanpa (chat saja), web (cari info/berita di internet),
dasar (4 tool inti), kompleks (semua tool), kritis (periksa & perbaiki jawaban).
Tool aktif = gabungan tool dari semua skill yang dipilih. "kritis" tidak punya tool;
ia mengubah cara model menjawab (ditangani agen.py).
  ASISTEN_AKAR_TULIS=/a:/b   folder tambahan yang boleh ditulis/dihapus
Hanya memakai library standar Python.
"""
import ast
import difflib
import fnmatch
import html
import ipaddress
import json
import math
import operator
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

MAX_OUTPUT = 2000   # karakter maksimum hasil tool yang dikirim balik ke model
CMD_TIMEOUT = 60    # detik, batas waktu satu perintah shell
HOME = Path.home()
TEMPAT_SAMPAH = HOME / ".sampah_asisten"
NOISE = {".git", "__pycache__", "node_modules", ".venv", "venv", ".cache",
         ".mypy_cache", ".pytest_cache"}
AKAR_TULIS = [HOME.resolve(), Path("/tmp").resolve()] + [
    Path(x).expanduser().resolve()
    for x in os.environ.get("ASISTEN_AKAR_TULIS", "").split(":") if x.strip()]

# Perintah yang SELALU diblokir, bahkan dalam mode AUTO.
BAHAYA = [
    r"\brm\s+(-\S+\s+)*(/|/\*|~|~/|\$HOME)(\s|$)",
    r"\bmkfs(\.\w+)?\b",
    r"\bdd\b.*\bof=/dev/",
    r">\s*/dev/(sd|nvme|mmcblk)",
    r":\(\)\s*\{",
    r"\b(shutdown|reboot|poweroff|halt)\b",
    r"\bchmod\s+-R\s+\S+\s+/(\s|$)",
]

# Perintah yang SELALU minta konfirmasi, bahkan dalam mode AUTO.
KONFIRMASI_SELALU = [
    r"\bsudo\b",
    r"\b(apt|apt-get|dpkg|pip3?|npm)\s+(install|remove|purge|uninstall|upgrade)\b",
]

# --------------------------------------------------------------------------
# Registri tool
# --------------------------------------------------------------------------
REGISTRY = {}


def tool(nama, deskripsi, params=None, wajib=(), ringkas=None, dasar=False, web=False):
    params = params or {}
    props = {}
    for k, spec in params.items():
        p = {"type": spec[0], "description": spec[1]}
        if len(spec) > 2:
            p["enum"] = list(spec[2])
        props[k] = p
    skema_ = {"type": "function", "function": {
        "name": nama, "description": deskripsi,
        "parameters": {"type": "object", "properties": props,
                       "required": list(wajib)}}}

    def dekor(fn):
        REGISTRY[nama] = {"fn": fn, "skema": skema_, "params": params,
                          "wajib": list(wajib), "ringkas": ringkas, "dasar": dasar,
                          "web": web}
        return fn
    return dekor


def _mode_dasar():
    return os.environ.get("ASISTEN_TOOLS", "kompleks").strip().lower() == "dasar"


SKILL_IDS = ("tanpa", "web", "dasar", "kompleks", "kritis")   # urutan kanonik
SKILL_ALIAS = {"semua": "kompleks"}                          # nama lama
MODE_SKILL = SKILL_IDS


def mode_awal():
    """Skill bawaan (dari ASISTEN_TOOLS) bila web belum memilih."""
    return "dasar" if _mode_dasar() else "kompleks"


def normal_skill(nilai=None):
    """Rapikan pilihan skill (teks 'web+kritis', daftar, atau None) menjadi tuple
    berurutan kanonik. Nama tak dikenal dibuang; kosong = skill bawaan."""
    if isinstance(nilai, str):
        bagian = re.split(r"[\s,+]+", nilai.strip().lower())
    elif nilai is None:
        bagian = []
    else:
        try:
            bagian = [str(x).strip().lower() for x in nilai]
        except TypeError:
            bagian = []
    ada = {SKILL_ALIAS.get(b, b) for b in bagian} & set(SKILL_IDS)
    if not ada:
        ada = {mode_awal()}
    return tuple(i for i in SKILL_IDS if i in ada)


def nama_tool_aktif(skill=None):
    """Nama tool yang aktif untuk gabungan skill (union)."""
    s = normal_skill(skill)
    return [n for n, t in REGISTRY.items()
            if "kompleks" in s or ("dasar" in s and t["dasar"]) or ("web" in s and t["web"])]


def mode_ctx(ctx=None):
    """Skill aktif untuk ctx (atribut ctx.skill diisi asisten.py), sebagai tuple."""
    return normal_skill(getattr(ctx, "skill", None))


def skema(mode=None):
    """Daftar tool (format function calling) yang dikirim ke model."""
    return [REGISTRY[n]["skema"] for n in nama_tool_aktif(mode)]


def _koersi(tipe, nilai):
    if tipe == "integer":
        return int(float(nilai))
    if tipe == "boolean":
        if isinstance(nilai, str):
            return nilai.strip().lower() in ("true", "1", "ya", "yes", "y")
        return bool(nilai)
    return nilai if isinstance(nilai, str) else str(nilai)


def eksekusi(nama, args, ctx):
    t = REGISTRY.get(nama)
    if not t or nama not in nama_tool_aktif(mode_ctx(ctx)):
        return f"ERROR: tool tidak dikenal: {nama}"
    kw = {}
    try:
        for k, spec in t["params"].items():
            if k in args and args[k] is not None:
                kw[k] = _koersi(spec[0], args[k])
    except (ValueError, TypeError) as e:
        return f"ERROR: argumen tidak valid ({e})"
    hilang = [k for k in t["wajib"] if k not in kw]
    if hilang:
        return "ERROR: argumen wajib belum diisi: " + ", ".join(hilang)
    try:
        return str(t["fn"](ctx, **kw))
    except Exception as e:  # noqa: BLE001 - kirim error apa adanya ke model
        return f"ERROR: {type(e).__name__}: {e}"


def ringkas(nama, args):
    """Satu baris ringkasan untuk kartu tool di web."""
    t = REGISTRY.get(nama)
    try:
        if t and t["ringkas"]:
            return str(t["ringkas"](args))[:200]
    except Exception:  # noqa: BLE001
        pass
    nilai = ", ".join(str(v)[:60] for v in list(args.values())[:2])
    return f"{nama} {nilai}".strip()


# --------------------------------------------------------------------------
# Util
# --------------------------------------------------------------------------
def _p(path):
    """Path relatif dihitung dari home (sama seperti shell tool)."""
    p = Path(str(path or "").strip() or ".").expanduser()
    return p if p.is_absolute() else HOME / p


def _rahasia(p):
    try:
        r = p.resolve()
    except OSError:
        r = p
    if r.name == ".token":
        return True
    return (".ssh" in r.parts and not r.name.endswith(".pub")
            and r.name not in ("known_hosts", "config"))


def _boleh_tulis(p, ikuti_link=True):
    try:
        r = p.resolve() if ikuti_link else p.parent.resolve() / p.name
    except OSError:
        return False
    if _rahasia(r) or ".ssh" in r.parts:
        return False
    for akar in AKAR_TULIS:
        if r == akar:
            return False  # folder akar itu sendiri tidak boleh ditimpa/dihapus
        if akar in r.parents:
            return True
    return False


def _tolak_tulis(p):
    return ("DITOLAK: hanya boleh mengubah file di home, /tmp, atau folder dari "
            f"ASISTEN_AKAR_TULIS (dan bukan ~/.ssh): {p}")


def _izin(ctx, jenis, ringkas_, detail="", selalu=False):
    """None jika diizinkan; pesan DIBATALKAN jika pengguna menolak."""
    if selalu or not ctx.auto:
        if not ctx.konfirmasi(jenis, ringkas_, detail):
            return "DIBATALKAN: pengguna tidak mengizinkan tindakan ini."
    return None


def _run(cmd, timeout=15, cwd=None, env=None, shell=False):
    """Jalankan perintah. Kembalian (kode, output); kode None = melebihi waktu."""
    e = dict(os.environ)
    e.update(env or {})
    try:
        p = subprocess.Popen(
            cmd, shell=shell, executable="/bin/bash" if shell else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, errors="replace",
            cwd=cwd, env=e, start_new_session=True)
    except FileNotFoundError:
        return 127, f"perintah tidak ditemukan: {cmd[0] if isinstance(cmd, list) else cmd}"
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        return None, f"melebihi batas waktu {timeout} detik"
    return p.returncode, (out + err).strip()


def _fmt(n):
    n = float(n)
    for sat in ("B", "KB", "MB", "GB"):
        if n < 1024 or sat == "GB":
            return f"{n:.0f} {sat}" if sat == "B" else f"{n:.1f} {sat}"
        n /= 1024


def _ekor_teks(teks, batas=MAX_OUTPUT - 120):
    """Ambil bagian AKHIR teks (agar pemotongan umum tidak membuang baris terbaru)."""
    if len(teks) <= batas:
        return teks
    sisa = teks[-batas:]
    i = sisa.find("\n")
    if i != -1:
        sisa = sisa[i + 1:]
    return "...[bagian awal dipotong]\n" + sisa


def _baca(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _teks_biner(data):
    return b"\0" in data[:1024]


def _jalan_pohon(akar, dalam=None):
    """Telusuri folder, lewati folder noise. Menghasilkan (folder, nama_file[])."""
    for d, subs, files in os.walk(akar):
        subs[:] = [s for s in subs if s not in NOISE]
        yield d, subs, files


# --------------------------------------------------------------------------
# Tool inti
# --------------------------------------------------------------------------
@tool("jalankan_perintah", "Jalankan satu perintah bash. Hanya jika tool lain tidak cukup.",
      {"perintah": ("string", "perintah bash")}, wajib=["perintah"], dasar=True,
      ringkas=lambda a: "$ " + str(a.get("perintah", "")))
def jalankan_perintah(ctx, perintah):
    if not perintah.strip():
        return "ERROR: perintah kosong."
    for pola in BAHAYA:
        if re.search(pola, perintah):
            return "DITOLAK: perintah ini masuk daftar berbahaya dan diblokir."
    wajib = any(re.search(pola, perintah) for pola in KONFIRMASI_SELALU)
    t = _izin(ctx, "shell", perintah, selalu=wajib)
    if t:
        return t.replace("tindakan ini", "perintah ini")
    kode, out = _run(perintah, timeout=CMD_TIMEOUT, cwd=HOME, shell=True)
    if kode is None:
        return f"GAGAL: {out}."
    return f"exit code {kode}\n{out or '(tidak ada output)'}"


@tool("baca_file", "Baca file teks. dari_baris/sampai_baris untuk bagian tertentu (bernomor).",
      {"path": ("string", "path file"),
       "mulai": ("integer", "offset byte"),
       "panjang": ("integer", "jumlah byte"),
       "dari_baris": ("integer", "baris awal (mulai 1)"),
       "sampai_baris": ("integer", "baris akhir")},
      wajib=["path"], dasar=True,
      ringkas=lambda a: f"baca {a.get('path', '')}"
      + (f" baris {a.get('dari_baris')}" if a.get("dari_baris") else ""))
def baca_file(ctx, path, mulai=0, panjang=MAX_OUTPUT, dari_baris=0, sampai_baris=0):
    p = _p(path)
    if not p.is_file():
        return f"ERROR: bukan file atau tidak ada: {p}"
    if _rahasia(p):
        return "DITOLAK: file ini berisi rahasia (token/kunci pribadi)."
    if dari_baris and dari_baris > 0:
        a = max(int(dari_baris), 1)
        b = int(sampai_baris) if int(sampai_baris) >= a else a + 59
        keluar, pakai, terakhir, lanjut = [], 0, 0, False
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for n, baris in enumerate(f, 1):
                if n < a:
                    continue
                if n > b:
                    lanjut = True
                    break
                s = f"{n}: {baris.rstrip()[:300]}"
                if pakai + len(s) + 1 > MAX_OUTPUT - 200:
                    keluar.append(f"...[dipotong; lanjutkan dari baris {n}]")
                    break
                keluar.append(s)
                pakai += len(s) + 1
                terakhir = n
        if not terakhir:
            return f"(tidak ada baris {a}; file lebih pendek)"
        return (f"[{p.name} baris {a}-{terakhir}]\n" + "\n".join(keluar)
                + ("\n...[masih ada baris berikutnya]" if lanjut else ""))
    mulai = max(int(mulai), 0)
    panjang = min(int(panjang), MAX_OUTPUT)
    with open(p, "rb") as f:
        f.seek(mulai)
        data = f.read(panjang)
    if _teks_biner(data):
        return f"(file biner, {_fmt(p.stat().st_size)}; tidak ditampilkan)"
    total = p.stat().st_size
    return (f"[byte {mulai}-{mulai + len(data)} dari {total}]\n"
            + data.decode("utf-8", errors="replace"))


@tool("tulis_file", "Tulis file (menimpa, cadangan .bak). tambah=true untuk menambah di akhir.",
      {"path": ("string", "path file"),
       "isi": ("string", "isi lengkap"),
       "tambah": ("boolean", "true = tambah di akhir")},
      wajib=["path", "isi"], dasar=True,
      ringkas=lambda a: (f"{'tambah ke' if a.get('tambah') else 'tulis'} "
                         f"{a.get('path', '')} ({len(str(a.get('isi', '')))} karakter)"))
def tulis_file(ctx, path, isi, tambah=False):
    p = _p(path)
    if not _boleh_tulis(p):
        return _tolak_tulis(p)
    ada = p.exists()
    if ada and not p.is_file():
        return f"ERROR: bukan file: {p}"
    info = ("menambah di akhir file" if tambah and ada
            else "menimpa file lama" if ada else "file baru")
    t = _izin(ctx, "tulis", f"{p} ({len(isi)} karakter, {info})", isi[:600])
    if t:
        return t
    if ada and not tambah:
        shutil.copy2(p, str(p) + ".bak")
    p.parent.mkdir(parents=True, exist_ok=True)
    if tambah:
        with open(p, "a", encoding="utf-8") as f:
            f.write(isi)
    else:
        p.write_text(isi, encoding="utf-8")
    return (f"Berhasil {'menambah ke' if tambah and ada else 'menulis'} {p} "
            f"({len(isi)} karakter)." + (" Cadangan: .bak" if ada and not tambah else ""))


@tool("daftar_folder", "Isi folder beserta ukuran file.",
      {"path": ("string", "folder, default home")}, dasar=True,
      ringkas=lambda a: f"daftar {a.get('path', '~')}")
def daftar_folder(ctx, path="."):
    p = _p(path)
    if not p.is_dir():
        return f"ERROR: bukan folder: {p}"
    item = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    if not item:
        return f"{p}: (kosong)"
    baris = []
    for x in item[:100]:
        if x.is_dir():
            baris.append(x.name + "/")
        else:
            try:
                baris.append(f"{x.name} ({_fmt(x.stat().st_size)})")
            except OSError:
                baris.append(x.name)
    ekstra = f"\n... dan {len(item) - 100} lainnya" if len(item) > 100 else ""
    return f"{p}:\n" + "\n".join(baris) + ekstra


# --------------------------------------------------------------------------
# Tool baca / cari (tanpa izin)
# --------------------------------------------------------------------------
@tool("pohon_folder", "Struktur folder bertingkat.",
      {"path": ("string", "folder, default home"),
       "kedalaman": ("integer", "1-4, default 2")},
      ringkas=lambda a: f"pohon {a.get('path', '~')}")
def pohon_folder(ctx, path=".", kedalaman=2):
    akar = _p(path)
    if not akar.is_dir():
        return f"ERROR: bukan folder: {akar}"
    kedalaman = max(1, min(int(kedalaman), 4))
    baris, sisa = [f"{akar}/"], [150]

    def jalan(d, tingkat):
        indent = "  " * tingkat
        try:
            item = sorted(d.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except OSError as e:
            baris.append(f"{indent}[tidak bisa dibuka: {e.strerror}]")
            return
        for x in item:
            if sisa[0] <= 0:
                return
            adalah = x.is_dir() and not x.is_symlink()
            if adalah and x.name in NOISE:
                baris.append(f"{indent}{x.name}/ (dilewati)")
                sisa[0] -= 1
                continue
            baris.append(indent + x.name + ("/" if adalah else ""))
            sisa[0] -= 1
            if adalah and tingkat < kedalaman:
                jalan(x, tingkat + 1)

    jalan(akar, 1)
    if sisa[0] <= 0:
        baris.append("... (dipotong, terlalu banyak item)")
    return "\n".join(baris)


@tool("info_file", "Info file/folder: ukuran, waktu ubah, izin, jumlah baris.",
      {"path": ("string", "path")}, wajib=["path"],
      ringkas=lambda a: f"info {a.get('path', '')}")
def info_file(ctx, path):
    p = _p(path)
    try:
        st = p.lstat()
    except OSError as e:
        return f"ERROR: {e.strerror}: {p}"
    jenis = "symlink" if p.is_symlink() else "folder" if p.is_dir() else "file"
    try:
        import pwd
        pemilik = pwd.getpwuid(st.st_uid).pw_name
    except Exception:  # noqa: BLE001
        pemilik = str(st.st_uid)
    baris = [f"path: {p}", f"jenis: {jenis}", f"ukuran: {_fmt(st.st_size)} ({st.st_size} byte)",
             f"diubah: {datetime.fromtimestamp(st.st_mtime):%Y-%m-%d %H:%M:%S}",
             f"izin: {oct(st.st_mode & 0o777)}", f"pemilik: {pemilik}"]
    if p.is_symlink():
        baris.append(f"menuju: {os.readlink(p)}")
    elif p.is_dir():
        try:
            baris.append(f"isi: {sum(1 for _ in p.iterdir())} item")
        except OSError:
            pass
    elif p.is_file() and st.st_size < 2_000_000:
        with open(p, "rb") as f:
            data = f.read()
        if _teks_biner(data):
            baris.append("tipe: biner")
        else:
            n_baris = data.count(b"\n") + (0 if data.endswith(b"\n") or not data else 1)
            baris.append(f"baris: {n_baris}")
    return "\n".join(baris)


@tool("cari_file", "Cari file/folder menurut nama (pola * ?).",
      {"pola": ("string", "nama atau pola, mis. *.py"),
       "path": ("string", "folder awal, default home"),
       "maks": ("integer", "default 50")},
      wajib=["pola"], ringkas=lambda a: f"cari file '{a.get('pola', '')}' di {a.get('path', '~')}")
def cari_file(ctx, pola, path=".", maks=50):
    akar = _p(path)
    if not akar.is_dir():
        return f"ERROR: bukan folder: {akar}"
    maks = max(1, min(int(maks), 200))
    pola = pola.lower() if any(c in pola for c in "*?[") else f"*{pola.lower()}*"
    hasil, batas = [], time.time() + 10
    habis_waktu = False
    for d, subs, files in _jalan_pohon(akar):
        for nama in subs + files:
            if fnmatch.fnmatch(nama.lower(), pola):
                rel = os.path.relpath(os.path.join(d, nama), akar)
                hasil.append(rel + ("/" if nama in subs else ""))
                if len(hasil) >= maks:
                    break
        if len(hasil) >= maks:
            break
        if time.time() > batas:
            habis_waktu = True
            break
    if not hasil:
        return "(tidak ada yang cocok)" + (" [pencarian dihentikan: waktu habis]" if habis_waktu else "")
    return (f"{len(hasil)} hasil di {akar}:\n" + "\n".join(hasil)
            + ("\n...[batas hasil tercapai]" if len(hasil) >= maks else "")
            + ("\n...[pencarian dihentikan: waktu habis]" if habis_waktu else ""))


@tool("cari_teks", "Cari teks di dalam file; hasil file:baris: isi.",
      {"teks": ("string", "teks dicari"),
       "path": ("string", "folder atau file, default home"),
       "pola_file": ("string", "filter nama, mis. *.py"),
       "maks": ("integer", "default 30")},
      wajib=["teks"], ringkas=lambda a: f"cari teks '{a.get('teks', '')}' di {a.get('path', '~')}")
def cari_teks(ctx, teks, path=".", pola_file="*", maks=30):
    akar = _p(path)
    if not akar.exists():
        return f"ERROR: tidak ada: {akar}"
    if not teks:
        return "ERROR: teks pencarian kosong."
    maks = max(1, min(int(maks), 100))
    kunci, pola_file = teks.lower(), (pola_file or "*").lower()
    hasil, batas, diperiksa, habis_waktu = [], time.time() + 15, 0, False

    def periksa(fp):
        try:
            if fp.stat().st_size > 1_000_000:
                return
            with open(fp, "rb") as f:
                awal = f.read(1024)
                if _teks_biner(awal):
                    return
                f.seek(0)
                for n, mentah in enumerate(f, 1):
                    baris = mentah.decode("utf-8", errors="replace")
                    if kunci in baris.lower():
                        rel = os.path.relpath(fp, akar if akar.is_dir() else akar.parent)
                        hasil.append(f"{rel}:{n}: {baris.strip()[:150]}")
                        if len(hasil) >= maks:
                            return
        except OSError:
            return

    if akar.is_file():
        periksa(akar)
    else:
        for d, subs, files in _jalan_pohon(akar):
            for nama in files:
                if fnmatch.fnmatch(nama.lower(), pola_file):
                    diperiksa += 1
                    periksa(Path(d) / nama)
                    if len(hasil) >= maks:
                        break
            if len(hasil) >= maks:
                break
            if time.time() > batas:
                habis_waktu = True
                break
    if not hasil:
        return "(tidak ditemukan)" + (" [pencarian dihentikan: waktu habis]" if habis_waktu else "")
    return ("\n".join(hasil) + ("\n...[batas hasil tercapai]" if len(hasil) >= maks else "")
            + ("\n...[pencarian dihentikan: waktu habis]" if habis_waktu else ""))


@tool("baca_ekor", "N baris terakhir file (log).",
      {"path": ("string", "path file"), "baris": ("integer", "default 40")},
      wajib=["path"], ringkas=lambda a: f"ekor {a.get('path', '')}")
def baca_ekor(ctx, path, baris=40):
    p = _p(path)
    if not p.is_file():
        return f"ERROR: bukan file atau tidak ada: {p}"
    if _rahasia(p):
        return "DITOLAK: file ini berisi rahasia (token/kunci pribadi)."
    baris = max(1, min(int(baris), 200))
    with open(p, "rb") as f:
        f.seek(0, os.SEEK_END)
        ukuran = f.tell()
        f.seek(max(0, ukuran - 65536))
        data = f.read()
    if _teks_biner(data):
        return "(file biner)"
    teks = "\n".join(data.decode("utf-8", errors="replace").splitlines()[-baris:])
    return _ekor_teks(teks) or "(file kosong)"


_NAMA_LAYANAN = re.compile(r"^[A-Za-z0-9@._:\-]{1,100}$")


@tool("info_sistem",
      "Info sistem Pi. aspek: ringkas (suhu, CPU, RAM, disk), proses, port, jaringan, disk, "
      "layanan, log_layanan.",
      {"aspek": ("string", "jenis info", ["ringkas", "proses", "port", "jaringan", "disk",
                                          "layanan", "log_layanan"]),
       "nama": ("string", "nama service (layanan/log_layanan)")},
      ringkas=lambda a: f"info sistem: {a.get('aspek', 'ringkas')} {a.get('nama', '')}".strip())
def info_sistem(ctx, aspek="ringkas", nama=""):
    aspek = (aspek or "ringkas").strip().lower()
    if aspek == "ringkas":
        return _ringkas_sistem()
    perintah = {
        "proses": ["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"],
        "port": ["ss", "-tln"],
        "jaringan": ["ip", "-br", "addr"],
        "disk": ["df", "-h", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"],
    }
    if aspek in perintah:
        kode, out = _run(perintah[aspek])
        if aspek == "proses":
            out = "\n".join(out.splitlines()[:11])
        return out or "(tidak ada output)"
    if aspek in ("layanan", "log_layanan"):
        if not _NAMA_LAYANAN.match(nama or ""):
            return "ERROR: isi 'nama' dengan nama service yang valid, mis. ssh."
        if aspek == "layanan":
            _, aktif = _run(["systemctl", "is-active", nama])
            _, status = _run(["systemctl", "status", nama, "--no-pager", "-n", "8"])
            return f"status: {aktif}\n{status}"
        _, out = _run(["journalctl", "-u", nama, "-n", "40", "--no-pager"])
        return _ekor_teks(out) or "(tidak ada log)"
    return "ERROR: aspek tidak dikenal: " + aspek


def _ringkas_sistem():
    baris = [f"host: {socket.gethostname()}"]
    up = _baca("/proc/uptime")
    if up:
        d = int(float(up.split()[0]))
        baris.append(f"uptime: {d // 86400} hari {d % 86400 // 3600} jam {d % 3600 // 60} menit")
    la = _baca("/proc/loadavg")
    if la:
        baris.append(f"beban CPU (1/5/15 mnt): {' '.join(la.split()[:3])} dari {os.cpu_count()} core")
    mem = _baca("/proc/meminfo")
    if mem:
        m = {}
        for b in mem.splitlines():
            k, _, v = b.partition(":")
            m[k] = int(v.split()[0]) * 1024 if v.split() else 0
        total, avail = m.get("MemTotal", 0), m.get("MemAvailable", 0)
        baris.append(f"RAM: terpakai {_fmt(total - avail)} dari {_fmt(total)}")
        if m.get("SwapTotal"):
            baris.append(f"swap: terpakai {_fmt(m['SwapTotal'] - m.get('SwapFree', 0))} "
                         f"dari {_fmt(m['SwapTotal'])}")
    for label, lokasi in (("disk /", "/"), ("disk home", str(HOME))):
        try:
            du = shutil.disk_usage(lokasi)
            baris.append(f"{label}: terpakai {_fmt(du.used)} dari {_fmt(du.total)} "
                         f"({du.used * 100 // du.total}%)")
        except OSError:
            pass
    suhu = _baca("/sys/class/thermal/thermal_zone0/temp")
    if suhu and suhu.lstrip("-").isdigit():
        baris.append(f"suhu CPU: {int(suhu) / 1000:.1f} C")
    if shutil.which("vcgencmd"):
        kode, out = _run(["vcgencmd", "get_throttled"])
        if kode == 0:
            baris.append(f"throttled: {out.split('=')[-1]} (0x0 = normal)")
    return "\n".join(baris)


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------
GIT_ENV = {"GIT_PAGER": "cat", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
GIT_BOLEH = {"add", "commit", "fetch", "pull", "push", "switch", "checkout", "branch",
             "merge", "stash", "tag", "clone", "init", "remote"}
GIT_JARINGAN = {"fetch", "pull", "push", "clone"}
GIT_FLAG_DILARANG = {"--force", "-f", "--force-with-lease", "--hard", "-D", "--delete",
                     "--no-verify"}
GIT_AWALAN_DILARANG = ("--upload-pack", "--receive-pack", "--exec", "--config")


@tool("git_baca", "Info repo git. diff + file = perubahan file itu.",
      {"path": ("string", "folder repo, default home"),
       "aksi": ("string", "jenis info", ["status", "log", "diff", "branch", "remote"]),
       "file": ("string", "(opsional) file")},
      ringkas=lambda a: f"git {a.get('aksi', 'status')} {a.get('path', '~')}")
def git_baca(ctx, path=".", aksi="status", file=""):
    repo = _p(path)
    if not repo.is_dir():
        return f"ERROR: bukan folder: {repo}"
    dasar = ["git", "--no-pager", "-C", str(repo)]
    if aksi == "status":
        cmd = dasar + ["status", "-sb"]
    elif aksi == "log":
        cmd = dasar + ["log", "--oneline", "-n", "15"] + (["--", file] if file else [])
    elif aksi == "diff":
        cmd = dasar + (["diff", "--", file] if file else ["diff", "--stat"])
    elif aksi == "branch":
        cmd = dasar + ["branch", "-vv"]
    elif aksi == "remote":
        cmd = dasar + ["remote", "-v"]
    else:
        return "ERROR: aksi harus salah satu: status, log, diff, branch, remote."
    kode, out = _run(cmd, timeout=20, env=GIT_ENV)
    return out or "(tidak ada output; tidak ada perubahan)"


@tool("git_tulis",
      "Git pengubah: add, commit -m, fetch, pull, push, switch, checkout, branch, merge, stash, "
      "tag, clone, init, remote. Force/hard dilarang.",
      {"path": ("string", "folder repo (clone: folder induk)"),
       "perintah": ("string", "argumen git tanpa 'git', mis. commit -m \"pesan\"")},
      wajib=["path", "perintah"], ringkas=lambda a: f"git {a.get('perintah', '')}")
def git_tulis(ctx, path, perintah):
    repo = _p(path)
    if not repo.is_dir():
        return f"ERROR: bukan folder: {repo}"
    try:
        args = shlex.split(perintah)
    except ValueError as e:
        return f"ERROR: tanda kutip tidak seimbang ({e})"
    if args and args[0] == "git":
        args = args[1:]
    if not args:
        return "ERROR: perintah git kosong."
    sub = args[0]
    if sub not in GIT_BOLEH:
        return "DITOLAK: subperintah git tidak diizinkan. Boleh: " + ", ".join(sorted(GIT_BOLEH))
    for a in args[1:]:
        if a in GIT_FLAG_DILARANG or a.startswith(GIT_AWALAN_DILARANG):
            return f"DITOLAK: opsi berbahaya tidak diizinkan: {a}"
    if sub == "push" and any(a.startswith((":", "+")) for a in args[1:]):
        return "DITOLAK: push dengan refspec ':' atau '+' (hapus/force) tidak diizinkan."
    if sub == "checkout" and any(a in ("--", ".") for a in args[1:]):
        return "DITOLAK: checkout yang membuang perubahan file tidak diizinkan."
    if sub == "stash" and any(a in ("drop", "clear") for a in args[1:]):
        return "DITOLAK: stash drop/clear tidak diizinkan."
    if sub == "commit" and not any(a in ("-m", "--message") or a.startswith(("-m", "--message=", "-am"))
                                   for a in args[1:]):
        return "ERROR: commit harus memakai -m \"pesan\"."
    t = _izin(ctx, "git", f"git {shlex.join(args)}   (di {repo})", selalu=(sub == "push"))
    if t:
        return t
    kode, out = _run(["git", "--no-pager"] + args, cwd=repo, env=GIT_ENV,
                     timeout=120 if sub in GIT_JARINGAN else 30)
    if kode is None:
        return f"GAGAL: {out}."
    return f"exit code {kode}\n{out or '(tidak ada output)'}"


# --------------------------------------------------------------------------
# Tool pengubah file (izin kecuali mode AUTO; hapus selalu izin)
# --------------------------------------------------------------------------
@tool("edit_file", "Ganti satu potongan teks unik 'lama' dengan 'baru' di file (cadangan .bak).",
      {"path": ("string", "path file"),
       "lama": ("string", "teks persis dan unik"),
       "baru": ("string", "teks pengganti")},
      wajib=["path", "lama"], ringkas=lambda a: f"edit {a.get('path', '')}")
def edit_file(ctx, path, lama, baru=""):
    p = _p(path)
    if not p.is_file():
        return f"ERROR: bukan file atau tidak ada: {p}"
    if not _boleh_tulis(p):
        return _tolak_tulis(p)
    if not lama:
        return "ERROR: 'lama' tidak boleh kosong."
    teks = p.read_bytes().decode("utf-8")
    n = teks.count(lama)
    if n == 0:
        return "ERROR: teks 'lama' tidak ditemukan (harus sama persis, termasuk spasi)."
    if n > 1:
        return f"ERROR: teks 'lama' muncul {n} kali; tambahkan baris di sekitarnya agar unik."
    t = _izin(ctx, "ubah", f"edit {p}", f"- {lama[:300]}\n+ {baru[:300]}")
    if t:
        return t
    shutil.copy2(p, str(p) + ".bak")
    p.write_bytes(teks.replace(lama, baru, 1).encode("utf-8"))
    return f"Berhasil mengubah {p} (1 bagian diganti). Cadangan: .bak"


@tool("buat_folder", "Buat folder.",
      {"path": ("string", "path folder")}, wajib=["path"],
      ringkas=lambda a: f"buat folder {a.get('path', '')}")
def buat_folder(ctx, path):
    p = _p(path)
    if p.is_dir():
        return f"Folder sudah ada: {p}"
    if p.exists():
        return f"ERROR: sudah ada file dengan nama itu: {p}"
    if not _boleh_tulis(p):
        return _tolak_tulis(p)
    t = _izin(ctx, "ubah", f"buat folder {p}")
    if t:
        return t
    p.mkdir(parents=True)
    return f"Folder dibuat: {p}"


@tool("salin_pindah", "Salin atau pindah file/folder; tujuan harus belum ada.",
      {"aksi": ("string", "salin atau pindah", ["salin", "pindah"]),
       "sumber": ("string", "path asal"), "tujuan": ("string", "path tujuan")},
      wajib=["aksi", "sumber", "tujuan"],
      ringkas=lambda a: f"{a.get('aksi', '')} {a.get('sumber', '')} -> {a.get('tujuan', '')}")
def salin_pindah(ctx, aksi, sumber, tujuan):
    if aksi not in ("salin", "pindah"):
        return "ERROR: aksi harus 'salin' atau 'pindah'."
    s, d = _p(sumber), _p(tujuan)
    if not (s.exists() or s.is_symlink()):
        return f"ERROR: sumber tidak ada: {s}"
    if _rahasia(s):
        return "DITOLAK: sumber berisi rahasia (token/kunci pribadi)."
    if d.is_dir():
        d = d / s.name
    if d.exists() or d.is_symlink():
        return f"ERROR: tujuan sudah ada: {d}"
    if not _boleh_tulis(d):
        return _tolak_tulis(d)
    if aksi == "pindah" and not _boleh_tulis(s, ikuti_link=False):
        return _tolak_tulis(s)
    t = _izin(ctx, "ubah", f"{aksi} {s} -> {d}")
    if t:
        return t
    d.parent.mkdir(parents=True, exist_ok=True)
    if aksi == "pindah":
        shutil.move(str(s), str(d))
    elif s.is_dir():
        shutil.copytree(s, d, symlinks=True)
    else:
        shutil.copy2(s, d)
    return f"Berhasil {aksi}: {s} -> {d}"


@tool("hapus", "Pindahkan ke ~/.sampah_asisten (bisa dipulihkan). Selalu minta izin.",
      {"path": ("string", "path")}, wajib=["path"],
      ringkas=lambda a: f"hapus {a.get('path', '')}")
def hapus(ctx, path):
    p = _p(path)
    if not (p.exists() or p.is_symlink()):
        return f"ERROR: tidak ada: {p}"
    if not _boleh_tulis(p, ikuti_link=False):
        return _tolak_tulis(p)
    if TEMPAT_SAMPAH in p.resolve().parents or p.resolve() == TEMPAT_SAMPAH:
        return "ERROR: itu sudah di tempat sampah."
    detail = ""
    if p.is_dir() and not p.is_symlink():
        n, total = 0, 0
        for d, _, files in os.walk(p):
            for nama in files:
                n += 1
                try:
                    total += os.lstat(os.path.join(d, nama)).st_size
                except OSError:
                    pass
            if n > 5000:
                break
        detail = f"folder berisi {n}{'+' if n > 5000 else ''} file, {_fmt(total)}"
    else:
        try:
            detail = f"ukuran {_fmt(p.lstat().st_size)}"
        except OSError:
            pass
    t = _izin(ctx, "hapus", f"HAPUS {p}", detail + "\n(dipindahkan ke ~/.sampah_asisten)",
              selalu=True)
    if t:
        return t
    TEMPAT_SAMPAH.mkdir(parents=True, exist_ok=True)
    tujuan = TEMPAT_SAMPAH / f"{datetime.now():%Y%m%d-%H%M%S}_{p.name}"
    shutil.move(str(p), str(tujuan))
    return f"Dipindahkan ke tempat sampah: {tujuan}"


# --------------------------------------------------------------------------
# Jaringan, proses, arsip, hitung
# --------------------------------------------------------------------------
@tool("ambil_url", "Ambil teks halaman web (http/https); simpan_ke = unduh jadi file.",
      {"url": ("string", "alamat"),
       "simpan_ke": ("string", "(opsional) path file")},
      wajib=["url"], ringkas=lambda a: f"ambil {a.get('url', '')}")
def ambil_url(ctx, url, simpan_ke=""):
    if not re.match(r"^https?://", url.strip(), re.I):
        return "ERROR: hanya alamat http/https yang didukung."
    url = url.strip()
    dst = None
    if simpan_ke:
        dst = _p(simpan_ke)
        if dst.exists():
            return f"ERROR: file tujuan sudah ada: {dst}"
        if not _boleh_tulis(dst):
            return _tolak_tulis(dst)
    t = _izin(ctx, "jaringan", f"GET {url}" + (f"\nsimpan ke {dst}" if dst else ""))
    if t:
        return t
    req = urllib.request.Request(url, headers={"User-Agent": "ai_asisten/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if dst:
            batas, total = 50 * 1024 * 1024, 0
            dst.parent.mkdir(parents=True, exist_ok=True)
            sementara = dst.with_name(dst.name + ".part")
            try:
                with open(sementara, "wb") as f:
                    while True:
                        potong_ = r.read(65536)
                        if not potong_:
                            break
                        total += len(potong_)
                        if total > batas:
                            raise ValueError("file lebih dari 50 MB, dibatalkan")
                        f.write(potong_)
                sementara.rename(dst)
            finally:
                if sementara.exists():
                    sementara.unlink()
            return f"Terunduh: {dst} ({_fmt(total)})"
        ctype = r.headers.get("Content-Type", "")
        data = r.read(200_000)
        teks = data.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    if "html" in ctype.lower() or teks.lstrip().lower().startswith(("<!doctype", "<html")):
        teks = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", teks)
        teks = re.sub(r"(?s)<[^>]+>", " ", teks)
        teks = html.unescape(teks)
        teks = re.sub(r"[ \t\r\f\v]+", " ", teks)
        teks = re.sub(r"\n\s*\n+", "\n", teks).strip()
    return teks or "(halaman kosong)"


_SINYAL = {"TERM": signal.SIGTERM, "KILL": signal.SIGKILL, "HUP": signal.SIGHUP,
           "INT": signal.SIGINT}


@tool("matikan_proses", "Hentikan proses menurut PID (lihat info_sistem proses). Selalu minta izin.",
      {"pid": ("integer", "nomor PID"),
       "sinyal": ("string", "TERM (halus) atau KILL", ["TERM", "KILL", "HUP", "INT"])},
      wajib=["pid"], ringkas=lambda a: f"matikan PID {a.get('pid', '')} ({a.get('sinyal', 'TERM')})")
def matikan_proses(ctx, pid, sinyal="TERM"):
    pid, sinyal = int(pid), (sinyal or "TERM").upper()
    if sinyal not in _SINYAL:
        return "ERROR: sinyal harus salah satu: TERM, KILL, HUP, INT."
    if pid <= 1 or pid in (os.getpid(), os.getppid()):
        return "DITOLAK: PID ini tidak boleh dihentikan (sistem atau asisten ini sendiri)."
    nama = _baca(f"/proc/{pid}/comm")
    if nama is None:
        return f"ERROR: proses {pid} tidak ada."
    cmd = (_baca(f"/proc/{pid}/cmdline") or "").replace("\0", " ")[:200]
    t = _izin(ctx, "proses", f"kirim SIG{sinyal} ke PID {pid} ({nama})", cmd, selalu=True)
    if t:
        return t
    os.kill(pid, _SINYAL[sinyal])
    return f"Sinyal {sinyal} dikirim ke PID {pid} ({nama})."


_ZIP_MAKS_FILE, _ZIP_MAKS_BYTE = 5000, 500 * 1024 * 1024


@tool("arsip", "File ZIP: daftar isi, buat dari file/folder, atau ekstrak.",
      {"aksi": ("string", "daftar, buat, atau ekstrak", ["daftar", "buat", "ekstrak"]),
       "path": ("string", "zip (daftar/ekstrak) atau sumber (buat)"),
       "tujuan": ("string", "(opsional) hasil .zip / folder tujuan")},
      wajib=["aksi", "path"], ringkas=lambda a: f"zip {a.get('aksi', '')} {a.get('path', '')}")
def arsip(ctx, aksi, path, tujuan=""):
    p = _p(path)
    if not (p.exists()):
        return f"ERROR: tidak ada: {p}"
    if aksi == "daftar":
        with zipfile.ZipFile(p) as z:
            info = z.infolist()
            baris = [f"{i.filename} ({_fmt(i.file_size)})" for i in info[:60]]
            return (f"{len(info)} entri, total {_fmt(sum(i.file_size for i in info))}\n"
                    + "\n".join(baris) + (f"\n... dan {len(info) - 60} lainnya" if len(info) > 60 else ""))
    if aksi == "buat":
        d = _p(tujuan) if tujuan else p.with_name(p.name + ".zip")
        if d.suffix.lower() != ".zip":
            d = d.with_name(d.name + ".zip")
        if d.exists():
            return f"ERROR: tujuan sudah ada: {d}"
        if not _boleh_tulis(d):
            return _tolak_tulis(d)
        if _rahasia(p):
            return "DITOLAK: sumber berisi rahasia."
        berkas = []
        if p.is_dir():
            for dir_, subs, files in os.walk(p):
                subs[:] = [s for s in subs if s != "__pycache__" and not _rahasia(Path(dir_) / s)]
                berkas += [Path(dir_) / f for f in files if not _rahasia(Path(dir_) / f)]
        else:
            berkas = [p]
        if len(berkas) > _ZIP_MAKS_FILE:
            return f"ERROR: terlalu banyak file ({len(berkas)} > {_ZIP_MAKS_FILE})."
        total = sum(f.stat().st_size for f in berkas if f.exists())
        if total > _ZIP_MAKS_BYTE:
            return f"ERROR: ukuran total terlalu besar ({_fmt(total)})."
        t = _izin(ctx, "ubah", f"buat zip {d} dari {p} ({len(berkas)} file, {_fmt(total)})")
        if t:
            return t
        d.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(d, "w", zipfile.ZIP_DEFLATED) as z:
            for f in berkas:
                if f == d:
                    continue
                z.write(f, f.relative_to(p.parent))
        return f"Zip dibuat: {d} ({len(berkas)} file, {_fmt(d.stat().st_size)})"
    if aksi == "ekstrak":
        if not p.is_file():
            return f"ERROR: bukan file zip: {p}"
        d = _p(tujuan) if tujuan else p.with_suffix("")
        if d.exists() and (not d.is_dir() or any(d.iterdir())):
            return f"ERROR: folder tujuan sudah ada dan tidak kosong: {d}"
        if not _boleh_tulis(d):
            return _tolak_tulis(d)
        with zipfile.ZipFile(p) as z:
            info = z.infolist()
            if len(info) > _ZIP_MAKS_FILE or sum(i.file_size for i in info) > _ZIP_MAKS_BYTE:
                return "ERROR: isi zip terlalu besar (maks 5000 file / 500 MB)."
            akar = d.resolve()
            for i in info:
                tgt = (akar / i.filename).resolve()
                if tgt != akar and akar not in tgt.parents:
                    return f"DITOLAK: zip berisi path berbahaya: {i.filename}"
            t = _izin(ctx, "ubah", f"ekstrak {p} -> {d} ({len(info)} entri)")
            if t:
                return t
            d.mkdir(parents=True, exist_ok=True)
            z.extractall(d)
            for i in info:  # pulihkan bit eksekusi (zipfile tidak melakukannya)
                if (i.external_attr >> 16) & 0o100 and not i.is_dir():
                    os.chmod(akar / i.filename, 0o755)
        return f"Diekstrak ke {d} ({len(info)} entri)"
    return "ERROR: aksi harus daftar, buat, atau ekstrak."


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow}
_FUNGSI = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
           "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log,
           "log10": math.log10, "exp": math.exp, "floor": math.floor, "ceil": math.ceil}
_KONSTAN = {"pi": math.pi, "e": math.e}


def _hitung(n):
    if isinstance(n, ast.Expression):
        return _hitung(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
            and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        a, b = _hitung(n.left), _hitung(n.right)
        if isinstance(n.op, ast.Pow):
            if abs(b) > 1000 or (isinstance(a, int) and isinstance(b, int)
                                 and b > 0 and a.bit_length() * b > 20000):
                raise ValueError("pangkat terlalu besar")
        return _OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
        v = _hitung(n.operand)
        return v if isinstance(n.op, ast.UAdd) else -v
    if isinstance(n, ast.Name) and n.id in _KONSTAN:
        return _KONSTAN[n.id]
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
            and n.func.id in _FUNGSI and not n.keywords:
        return _FUNGSI[n.func.id](*[_hitung(a) for a in n.args])
    raise ValueError("ekspresi tidak didukung")


@tool("hitung", "Hitung ekspresi matematika (+ - * / // % ** sqrt abs round min max sin cos tan "
      "log exp floor ceil pi e).",
      {"ekspresi": ("string", "mis. (12.5*8)/3")}, wajib=["ekspresi"],
      ringkas=lambda a: f"hitung {a.get('ekspresi', '')}")
def hitung(ctx, ekspresi):
    if len(ekspresi) > 200:
        return "ERROR: ekspresi terlalu panjang."
    try:
        hasil = _hitung(ast.parse(ekspresi.strip().replace("^", "**"), mode="eval"))
    except ZeroDivisionError:
        return "ERROR: pembagian dengan nol."
    except (SyntaxError, ValueError, OverflowError, TypeError) as e:
        return f"ERROR: tidak bisa dihitung ({e})"
    return f"{ekspresi.strip()} = " + (str(hasil) if isinstance(hasil, int) else format(hasil, ".12g"))


# --------------------------------------------------------------------------
# Tool hanya-baca tambahan (tanpa izin)
# --------------------------------------------------------------------------
_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


@tool("waktu_sekarang", "Tanggal, jam, dan zona waktu Pi saat ini.",
      web=True, ringkas=lambda a: "waktu sekarang")
def waktu_sekarang(ctx):
    n = datetime.now().astimezone()
    return f"{_HARI[n.weekday()]}, {n:%Y-%m-%d %H:%M:%S} ({n.tzname()}, UTC{n:%z})"


def _baca_teks_aman(p, batas=1_000_000):
    """(baris[], None) bila file teks biasa; (None, pesan_error) bila tidak boleh dibaca."""
    if not p.is_file():
        return None, f"ERROR: bukan file atau tidak ada: {p}"
    if _rahasia(p):
        return None, "DITOLAK: file ini berisi rahasia (token/kunci pribadi)."
    if p.stat().st_size > batas:
        return None, f"ERROR: file terlalu besar (> {_fmt(batas)}): {p}"
    data = p.read_bytes()
    if _teks_biner(data):
        return None, f"ERROR: file biner: {p}"
    return data.decode("utf-8", errors="replace").splitlines(), None


@tool("bandingkan_file", "Selisih (diff) dua file teks.",
      {"file_a": ("string", "path file lama"), "file_b": ("string", "path file baru")},
      wajib=["file_a", "file_b"],
      ringkas=lambda a: f"bandingkan {a.get('file_a', '')} {a.get('file_b', '')}")
def bandingkan_file(ctx, file_a, file_b):
    a, b = _p(file_a), _p(file_b)
    baris_a, err = _baca_teks_aman(a)
    if err:
        return err
    baris_b, err = _baca_teks_aman(b)
    if err:
        return err
    selisih = list(difflib.unified_diff(baris_a, baris_b, str(a), str(b), lineterm="", n=2))
    if not selisih:
        return "Kedua file identik."
    out = "\n".join(selisih)
    batas = MAX_OUTPUT - 120
    if len(out) > batas:
        out = out[:batas].rsplit("\n", 1)[0] + f"\n...[dipotong, total {len(selisih)} baris selisih]"
    return out


@tool("ukuran_folder", "Total ukuran folder dan 10 isi terbesarnya.",
      {"path": ("string", "folder, default home")},
      ringkas=lambda a: f"ukuran {a.get('path', '~')}")
def ukuran_folder(ctx, path="."):
    p = _p(path)
    if not p.is_dir():
        return f"ERROR: bukan folder: {p}"
    mulai, terpotong = time.time(), False
    hasil, total = [], 0
    try:
        anak = sorted(p.iterdir())
    except OSError as e:
        return f"ERROR: tidak bisa membaca folder: {e}"
    for c in anak:
        if terpotong:
            break
        ukuran = 0
        try:
            if c.is_symlink():
                continue
            if c.is_file():
                ukuran = c.stat().st_size
            elif c.is_dir():
                for d, _, files in os.walk(c):
                    for nama in files:
                        try:
                            ukuran += os.lstat(os.path.join(d, nama)).st_size
                        except OSError:
                            pass
                    if time.time() - mulai > 8:
                        terpotong = True
                        break
        except OSError:
            continue
        total += ukuran
        hasil.append((ukuran, c.name + ("/" if c.is_dir() else "")))
    hasil.sort(reverse=True)
    baris = [f"{p}: total {_fmt(total)} dalam {len(hasil)} entri"
             + (" (dihitung sebagian: waktu habis)" if terpotong else "")]
    baris += [f"{_fmt(u):>9}  {nama}" for u, nama in hasil[:10]]
    return "\n".join(baris)


@tool("cek_sintaks", "Periksa sintaks file .py, .json, atau .sh tanpa menjalankannya.",
      {"path": ("string", "path file")}, wajib=["path"],
      ringkas=lambda a: f"cek sintaks {a.get('path', '')}")
def cek_sintaks(ctx, path):
    p = _p(path)
    baris, err = _baca_teks_aman(p)
    if err:
        return err
    ekst = p.suffix.lower()
    if ekst == ".py":
        try:
            ast.parse("\n".join(baris), str(p))
        except SyntaxError as e:
            return f"SINTAKS SALAH di baris {e.lineno}: {e.msg}"
    elif ekst == ".json":
        try:
            json.loads("\n".join(baris))
        except ValueError as e:
            return f"JSON TIDAK VALID: {e}"
    elif ekst == ".sh":
        kode, out = _run(["bash", "-n", str(p)])
        if kode != 0:
            return f"SINTAKS SALAH: {out}"
    else:
        return "ERROR: hanya mendukung file .py, .json, dan .sh."
    return f"Sintaks OK: {p.name} ({len(baris)} baris)"


# --------------------------------------------------------------------------
# Skill WEB: cari informasi di internet (hanya-baca, tanpa izin)
# --------------------------------------------------------------------------
# Keamanan: hanya alamat PUBLIK yang boleh dibuka (alamat lokal/privat/loopback
# ditolak, termasuk lewat pengalihan), supaya isi halaman web tidak bisa menyuruh
# model membuka layanan di jaringan rumah. Isi halaman tetap diperlakukan sebagai
# DATA, bukan perintah (lihat PROMPT_WEB di agen.py).
UA_WEB = ("Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0 Safari/537.36")
WEB_MAKS_BYTE = 600_000


def _cek_publik(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("hanya alamat http/https yang valid")
    try:
        info = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80),
                                  proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"alamat tidak ditemukan: {u.hostname}") from None
    for i in info:
        ip = ipaddress.ip_address(i[4][0].split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ValueError("alamat jaringan lokal/privat tidak diizinkan")


class _Alihan(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _cek_publik(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Alihan)


def _unduh(url, maks=WEB_MAKS_BYTE, timeout=15):
    """(content_type, teks) dari URL publik. ValueError bila ditolak atau gagal."""
    url = url.strip()
    _cek_publik(url)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_WEB, "Accept-Language": "id,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.5"})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            charset = r.headers.get_content_charset() or "utf-8"
            data = r.read(maks)
    except urllib.error.HTTPError as e:
        raise ValueError(f"server membalas HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise ValueError(f"tidak bisa terhubung ({e.reason})") from None
    except (TimeoutError, socket.timeout):
        raise ValueError("waktu habis") from None
    try:
        return ctype, data.decode(charset, errors="replace")
    except LookupError:
        return ctype, data.decode("utf-8", errors="replace")


# tag HTML; atribut bertanda kutip boleh berisi ">" (mis. data JSON di Wikipedia)
_TAG = re.compile(r"""<(?:[^>"']|"[^"]*"|'[^']*')*>""", re.S)


def _bersih(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(_TAG, " ", h))).strip()


def _html_ke_teks(h):
    """(judul, teks) dari HTML; membuang skrip, menu, dan baris pendek."""
    judul = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", h)
    if m:
        judul = _bersih(m.group(1))
    h = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|aside|form|iframe)\b.*?</\1>", " ", h)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|section|article)>|<br\s*/?>", "\n", h)
    h = re.sub(_TAG, " ", h)
    h = html.unescape(h)
    baris = [re.sub(r"[ \t\r\f\v]+", " ", b).strip() for b in h.split("\n")]
    return judul, "\n".join(b for b in baris if len(b) >= 25)


@tool("baca_halaman",
      "Baca isi teks satu halaman web publik (hanya baca). mulai = lanjut dari karakter ke-N.",
      {"url": ("string", "alamat http/https"),
       "mulai": ("integer", "mulai dari karakter ke-N, default 0")},
      wajib=["url"], web=True, ringkas=lambda a: f"baca halaman {a.get('url', '')}")
def baca_halaman(ctx, url, mulai=0):
    try:
        ctype, isi = _unduh(url)
    except ValueError as e:
        return f"ERROR: {e}"
    ct = ctype.lower()
    if "html" in ct or isi.lstrip().lower().startswith(("<!doctype", "<html")):
        judul, teks = _html_ke_teks(isi)
    elif any(k in ct for k in ("text/", "json", "xml")):
        judul, teks = "", isi.strip()
    else:
        return f"(bukan halaman teks: {ctype or 'tipe tidak diketahui'})"
    if len(teks) < 80:
        return ("(halaman hampir kosong; mungkin butuh JavaScript atau diblokir)"
                + (f"\nJudul: {judul}" if judul else ""))
    mulai = max(0, int(mulai))
    if mulai >= len(teks):
        return "(sudah di akhir halaman)"
    potongan = teks[mulai:mulai + MAX_OUTPUT - 260]
    akhir = mulai + len(potongan)
    return ((f"Judul: {judul}\n" if judul and mulai == 0 else "")
            + f"[karakter {mulai}-{akhir} dari {len(teks)}]\n" + potongan
            + (f"\n...[lanjut dengan mulai={akhir}]" if akhir < len(teks) else ""))


def _parse_brave(h, maks):
    """[(judul, url, cuplikan)] dari halaman hasil Brave Search."""
    hasil = []
    for blok in re.split(r'<div class="snippet[^"]*"[^>]*data-type="web"', h)[1:]:
        m = re.search(r'<a href="(https?://[^"]+)"', blok)
        if not m:
            continue
        url = html.unescape(m.group(1))
        if (urllib.parse.urlsplit(url).hostname or "").endswith("brave.com"):
            continue
        t = (re.search(r'class="title[^"]*"[^>]*title="([^"]*)"', blok)
             or re.search(r'class="title[^"]*"[^>]*>(.*?)</div>', blok, re.S))
        if not t:
            continue
        s = re.search(r'class="content[^"]*"[^>]*>(.*?)</div>', blok, re.S)
        hasil.append((_bersih(t.group(1)), url, _bersih(s.group(1)) if s else ""))
        if len(hasil) >= maks:
            break
    return hasil


_PERIODE = {"hari_ini": "1d", "minggu_ini": "7d", "bulan_ini": "30d", "semua": ""}


def _ambil_berita(topik, periode, maks):
    """[(waktu, judul, sumber)] dari Google News RSS, terbaru dulu."""
    topik = (topik or "").strip()
    rentang = _PERIODE.get(periode, "")
    if topik:
        q = topik[:150] + (f" when:{rentang}" if rentang else "")
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": q, "hl": "id", "gl": "ID", "ceid": "ID:id"})
    else:
        url = "https://news.google.com/rss?" + urllib.parse.urlencode(
            {"hl": "id", "gl": "ID", "ceid": "ID:id"})
    _, xml = _unduh(url, maks=1_500_000)
    if "<!ENTITY" in xml:
        raise ValueError("format berita tidak aman")
    try:
        akar = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError:
        raise ValueError("format berita tidak dikenali") from None
    item, lihat = [], set()
    for it in akar.iter("item"):
        judul = (it.findtext("title") or "").strip()
        sumber = (it.findtext("source") or "").strip()
        if sumber and judul.endswith(" - " + sumber):
            judul = judul[:-len(sumber) - 3]
        if not judul or judul.lower() in lihat:
            continue
        lihat.add(judul.lower())
        try:
            waktu = parsedate_to_datetime(it.findtext("pubDate") or "")
            if waktu.tzinfo is None:
                waktu = waktu.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            waktu = None
        item.append((waktu, judul, sumber))
    item.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return item[:maks]


def _umur(waktu, sekarang):
    d = max(0, int((sekarang - waktu).total_seconds()))
    if d < 3600:
        return f"{max(d // 60, 1)} menit lalu"
    if d < 86400:
        return f"{d // 3600} jam lalu"
    return f"{d // 86400} hari lalu"


def _format_berita(item):
    sekarang = datetime.now(timezone.utc)
    baris = []
    for i, (w, judul, sumber) in enumerate(item, 1):
        baris.append(f"{i}. {judul[:110]} - {sumber or 'sumber ?'}" + (f", {_umur(w, sekarang)}" if w else ""))
    return "\n".join(baris)


@tool("berita",
      "Berita terbaru (Google News Indonesia): judul, sumber, umur berita. Tanpa topik = berita utama.",
      {"topik": ("string", "(opsional) kata kunci, mis. banjir jakarta"),
       "periode": ("string", "rentang waktu, default hari_ini",
                   ["hari_ini", "minggu_ini", "bulan_ini", "semua"]),
       "maks": ("integer", "jumlah berita, default 8, maks 12")},
      web=True, ringkas=lambda a: "berita " + (a.get("topik") or "terbaru"))
def berita(ctx, topik="", periode="hari_ini", maks=8):
    maks = max(1, min(int(maks), 12))
    periode = periode if periode in _PERIODE else "hari_ini"
    try:
        item = _ambil_berita(topik, periode, maks)
        catatan = ""
        if not item and topik.strip() and periode == "hari_ini":
            item = _ambil_berita(topik, "minggu_ini", maks)
            catatan = "(tidak ada berita 24 jam terakhir; ini 7 hari terakhir)\n"
    except ValueError as e:
        return f"ERROR: tidak bisa mengambil berita ({e})"
    if not item:
        return "Tidak ada berita untuk topik itu. Coba kata kunci lain atau periode semua."
    return (catatan + _format_berita(item)
            + "\n(sumber: Google News; hanya judul. Isi lengkap: cari_web lalu baca_halaman)")


@tool("cari_web",
      "Cari informasi di internet. Hasil: judul, tautan, cuplikan. Untuk berita terbaru pakai tool berita.",
      {"kueri": ("string", "kata kunci pencarian"),
       "maks": ("integer", "jumlah hasil, default 5, maks 8")},
      wajib=["kueri"], web=True, ringkas=lambda a: f"cari web: {a.get('kueri', '')}")
def cari_web(ctx, kueri, maks=5):
    kueri = (kueri or "").strip()
    if not kueri:
        return "ERROR: kueri kosong."
    maks = max(1, min(int(maks), 8))
    url = "https://search.brave.com/search?" + urllib.parse.urlencode(
        {"q": kueri[:200], "source": "web", "country": "id"})
    galat, hasil = "", []
    try:
        _, h = _unduh(url, maks=900_000)
        hasil = _parse_brave(h, maks)
    except ValueError as e:
        galat = str(e)
    if not hasil:   # cadangan: berita terkait dari Google News
        try:
            item = _ambil_berita(kueri, "semua", maks)
        except ValueError as e:
            return f"ERROR: pencarian gagal ({galat or 'tidak ada hasil'}; cadangan berita: {e})"
        if not item:
            return f"Tidak ada hasil untuk: {kueri}" + (f" ({galat})" if galat else "")
        return "(mesin pencari tidak memberi hasil; ini berita terkait)\n" + _format_berita(item)
    per = (MAX_OUTPUT - 120) // len(hasil)
    baris = []
    for i, (judul, u, cup) in enumerate(hasil, 1):
        judul, u = judul[:80], u[:100]
        sisa = max(40, per - len(judul) - len(u) - 14)
        baris.append(f"{i}. {judul}\n   {u}\n   {cup[:sisa]}")
    return "\n".join(baris)
