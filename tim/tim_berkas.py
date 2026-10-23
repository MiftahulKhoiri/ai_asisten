"""Berkas hasil: nama aman, tulis/baca proyek, dan penguraian keluaran Pelaksana.
"""
import ast
import hashlib
import json
import os
import re
from pathlib import Path

from . import tim_config as conf


_BAGIAN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,60}$")


def aman_nama(nama):
    """Nama berkas relatif yang aman (maks 3 tingkat, tanpa titik di depan, ekstensi dikenal)."""
    n = str(nama or "").strip().replace("\\", "/")
    while n.startswith("./"):
        n = n[2:]
    bagian = n.split("/")
    if (not n or len(n) > 80 or len(bagian) > 3
            or any(not _BAGIAN.match(b) or b in (".", "..") for b in bagian)):
        raise ValueError("nama berkas tidak aman: %r" % (nama,))
    if Path(n).suffix.lower() not in conf.EKSTENSI:
        raise ValueError("jenis berkas tidak diizinkan: %s" % n)
    return n


def tulis_berkas(hasil_dir, nama, isi):
    nama = aman_nama(nama)
    if len(isi.encode("utf-8")) > conf.MAKS_UKURAN:
        raise ValueError("%s terlalu besar (maks %d KB)" % (nama, conf.MAKS_UKURAN // 1000))
    akar = os.path.realpath(str(hasil_dir))
    p = Path(hasil_dir) / nama
    induk = os.path.realpath(str(p.parent))
    if induk != akar and not induk.startswith(akar + os.sep):
        raise ValueError("jalur di luar folder hasil: " + nama)
    if p.is_symlink():
        raise ValueError("berkas berupa symlink: " + nama)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(isi, encoding="utf-8")
    return nama


def baca_proyek(hasil_dir, maks=30):
    """[(nama, isi)] semua berkas teks di folder hasil (tanpa symlink)."""
    hasil, akar = [], Path(hasil_dir)
    if not akar.is_dir():
        return hasil
    for d, subs, files in os.walk(str(akar)):
        subs[:] = sorted(s for s in subs if not s.startswith(".") and s != "__pycache__")
        for f in sorted(files):
            p = Path(d) / f
            rel = p.relative_to(akar).as_posix()
            try:
                aman_nama(rel)
                if p.is_symlink() or p.stat().st_size > conf.MAKS_UKURAN:
                    continue
                hasil.append((rel, p.read_text(encoding="utf-8", errors="replace")))
            except (ValueError, OSError):
                continue
            if len(hasil) >= maks:
                return hasil
    return hasil


def salin_proyek(sumber, tujuan, maks=None):
    """Salin berkas proyek lama (untuk melanjutkan). Symlink dan berkas tak dikenal dilewati."""
    n = 0
    for rel, isi in baca_proyek(sumber, maks or conf.MAKS_BERKAS_TOTAL * 3):
        try:
            tulis_berkas(tujuan, rel, isi)
            n += 1
        except ValueError:
            continue
    return n


def hash_proyek(hasil_dir):
    """Sidik jari isi proyek (nama + isi, akhir baris dinormalkan): dipakai untuk mengenali bahwa
    proyek tidak berubah sejak diagnosa, sehingga diagnosa lama boleh dipakai ulang."""
    h = hashlib.sha1()
    for nama, isi in baca_proyek(hasil_dir, conf.MAKS_BACA):
        h.update(nama.encode("utf-8") + b"\0" + isi.replace("\r\n", "\n").rstrip().encode("utf-8") + b"\0")
    return h.hexdigest()


def masukkan_bahan(sumber, tujuan):
    """Salin berkas unggahan pengguna ke folder kerja. Kembalian: (nama yang masuk, [(nama, alasan)]).

    Setiap berkas tetap lewat tulis_berkas (nama aman, jenis dikenal, ukuran, tanpa symlink),
    jadi paket unggahan yang tidak tepercaya pun tidak bisa menulis di luar folder hasil."""
    masuk, lewat = [], []
    for rel, isi in baca_proyek(sumber, conf.MAKS_BAHAN):
        try:
            masuk.append(tulis_berkas(tujuan, rel, isi))
        except ValueError as e:
            lewat.append((rel, str(e)))
    return masuk, lewat


_HEAD = re.compile(
    r"^[ \t]*[=#*-]{2,}[ \t]*(?:FILE|BERKAS)[ \t]*:[ \t]*(.+?)[ \t]*[=#*-]*[ \t]*$", re.M | re.I)


_END = re.compile(
    r"^[ \t]*[=#*-]{2,}[ \t]*(?:END|SELESAI)(?:[ \t]+(?:FILE|BERKAS))?[ \t]*[=#*-]*[ \t]*$",
    re.M | re.I)


_PAGAR = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.S)


_PAGAR_BARIS = re.compile(r"^[ \t]*```[\w+-]*[ \t]*$")


_NAMA_DI_BARIS = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,5})")


def _rapi(isi, nama=""):
    """Rapikan isi berkas dari model: buang baris pagar ``` yang nyasar di awal/akhir.
    (Berkas .md/.txt boleh berisi pagar, jadi hanya baris kosong di ujung yang dibuang.)"""
    baris = isi.replace("\r\n", "\n").split("\n")
    if Path(nama).suffix.lower() in (".md", ".txt"):
        teks = "\n".join(baris).strip("\n")
    else:
        while baris and (not baris[0].strip() or _PAGAR_BARIS.match(baris[0])):
            baris.pop(0)
        while baris and (not baris[-1].strip() or _PAGAR_BARIS.match(baris[-1])):
            baris.pop()
        teks = "\n".join(baris)
    return teks + "\n" if teks.strip() else ""


def _kode_valid(nama, isi):
    ext = Path(nama).suffix.lower()
    try:
        if ext == ".py":
            ast.parse(isi)
            return True
        if ext == ".json":
            json.loads(isi)
            return True
    except (SyntaxError, ValueError):
        return False
    return False


def urai_berkas(teks, nama_spec=()):
    """Urai keluaran Pelaksana menjadi [(nama, isi, lengkap)].

    Format utama:  === FILE: nama ===  ...  === END ===  (penanda longgar: ### FILE: x, **FILE: x**)
    `lengkap` False bila blok tidak ditutup (keluaran terpotong batas token).
    Cadangan: blok ``` dengan nama berkas di baris sebelumnya, satu blok ``` untuk lembar tugas
    satu berkas, atau seluruh jawaban bila lembar tugas satu berkas dan isinya kode yang valid.
    """
    teks = teks or ""
    kepala = list(_HEAD.finditer(teks))
    hasil = []
    for i, h in enumerate(kepala):
        batas = kepala[i + 1].start() if i + 1 < len(kepala) else len(teks)
        potongan = teks[h.end():batas]
        e = _END.search(potongan)
        nama = h.group(1).strip("`'\"* ")
        if e:
            hasil.append((nama, _rapi(potongan[:e.start()], nama), True))
        else:
            hasil.append((nama, _rapi(potongan, nama), i + 1 < len(kepala)))
    if hasil:
        return hasil
    blok = list(_PAGAR.finditer(teks))
    if len(blok) == 1 and len(nama_spec) == 1:
        return [(nama_spec[0], _rapi(blok[0].group(1), nama_spec[0]), True)]
    pos = 0
    for b in blok:
        sebelum = teks[pos:b.start()].strip().splitlines()
        pos = b.end()
        nama = None
        for baris in reversed(sebelum[-2:]):
            for kand in _NAMA_DI_BARIS.findall(baris):
                try:
                    nama = aman_nama(kand)
                    break
                except ValueError:
                    continue
            if nama:
                break
        if nama:
            hasil.append((nama, _rapi(b.group(1), nama), True))
    if not hasil and not blok and len(nama_spec) == 1 and teks.strip():
        isi = _rapi(teks, nama_spec[0])
        if _kode_valid(nama_spec[0], isi):
            return [(nama_spec[0], isi, True)]
    return hasil


def baca_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pulihkan(hasil_dir, berkas):
    """Kembalikan folder hasil ke isi `berkas` ({nama: isi})."""
    for nama, isi in berkas.items():
        tulis_berkas(hasil_dir, nama, isi)
    for nama, _ in baca_proyek(hasil_dir, conf.MAKS_BACA):
        if nama not in berkas:
            try:
                (Path(hasil_dir) / nama).unlink()
            except OSError:
                pass
