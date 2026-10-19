"""Riwayat proses Agent: daftar, baca, dan hapus folder proses.
"""
import shutil

from . import tim_config as conf
from .tim_berkas import baca_json, baca_proyek
from .tim_config import id_valid


AKTIF_RUN = set()            # id proses yang sedang berjalan (tidak boleh dihapus)


def daftar_run(maks=30):
    hasil = []
    if not conf.KERJA.is_dir():
        return hasil
    for d in sorted(conf.KERJA.iterdir(), reverse=True):
        if not (d.is_dir() and conf.ID_RUN.match(d.name)):
            continue
        m = baca_json(d / "run.json")
        if not isinstance(m, dict):
            continue
        hasil.append({k: m.get(k) for k in ("id", "judul", "status", "dibuat", "putaran", "maks")})
        if len(hasil) >= maks:
            break
    return hasil


def _hapus_folder(d):
    shutil.rmtree(str(d))     # tidak mengikuti symlink di dalamnya: hanya tautannya yang terhapus


def hapus_run(run_id):
    """Hapus satu proses beserta berkas hasilnya.
    FileNotFoundError bila tidak ada, PermissionError bila prosesnya masih berjalan."""
    if not id_valid(run_id):
        raise FileNotFoundError("id tidak valid")
    if run_id in AKTIF_RUN:
        raise PermissionError("Proses ini masih berjalan")
    d = conf.KERJA / run_id
    if d.is_symlink() or not d.is_dir():
        raise FileNotFoundError(run_id)
    _hapus_folder(d)


def hapus_semua_run():
    """Hapus semua proses kecuali yang masih berjalan. Kembalian: jumlah yang dihapus."""
    n = 0
    if not conf.KERJA.is_dir():
        return n
    for d in list(conf.KERJA.iterdir()):
        if d.is_symlink() or not d.is_dir() or not id_valid(d.name) or d.name in AKTIF_RUN:
            continue
        try:
            _hapus_folder(d)
            n += 1
        except OSError:
            pass
    return n


def baca_run(run_id):
    """Ringkasan proses + isi berkas hasilnya. FileNotFoundError bila tidak ada."""
    if not conf.ID_RUN.match(str(run_id or "")):
        raise FileNotFoundError("id tidak valid")
    d = conf.KERJA / run_id
    m = baca_json(d / "run.json")
    if not isinstance(m, dict):
        raise FileNotFoundError(run_id)
    m["berkas"] = [{"nama": n, "isi": isi[:60000]} for n, isi in baca_proyek(d / "hasil")]
    m["dir"] = str(d)
    return m
