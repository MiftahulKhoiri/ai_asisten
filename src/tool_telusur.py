"""tool_telusur.py - tool hanya-baca: menelusuri folder dan memeriksa file."""

import ast
import difflib
import fnmatch
import json
import os
import time
from datetime import datetime
from pathlib import Path

from .registri import tool
from .util import MAX_OUTPUT, NOISE, _baca_teks_aman, _ekor_teks, _fmt, _jalan_pohon, _p, _rahasia, _run, _teks_biner


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
