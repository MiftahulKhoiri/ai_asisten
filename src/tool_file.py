"""tool_file.py - tool baca/tulis/ubah/pindah/hapus file dan arsip ZIP."""

import os
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .registri import tool
from .util import MAX_OUTPUT, TEMPAT_SAMPAH, _boleh_tulis, _fmt, _izin, _p, _rahasia, _teks_biner, _tolak_tulis


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
