"""server_prompt.py - prompt pilihan pengguna untuk skill Tanpa.

Pengguna boleh menyimpan prompt dengan nama, lalu mencentang satu atau beberapa prompt untuk sesi
(prompt yang dipilih digabung berurutan sesuai daftar). Aturannya:
  - "Bawaan" = SYSTEM_CHAT, selalu ada dan tidak bisa dihapus; dicentang secara bawaan.
  - tidak ada yang dicentang = model berjalan TANPA prompt sistem sama sekali (murni).
  - teks prompt boleh memuat {waktu}, diganti tanggal dan jam saat dipakai.
Disimpan di prompt.json (satu berkas untuk semua perangkat), ditulis secara atomik.
"""
import json
import os
import re
import secrets
import threading

import agen
from . import server_config as conf

_ID = re.compile(r"^p[0-9a-f]{8}$")
_KUNCI = threading.Lock()


def bawaan():
    return {"id": conf.PROMPT_BAWAAN, "nama": "Bawaan (asisten ramah)", "isi": agen.SYSTEM_CHAT, "bawaan": True}


def _baca():
    """Prompt buatan pengguna dari berkas; berkas hilang atau rusak = daftar kosong."""
    try:
        d = json.loads(conf.PROMPT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    hasil = []
    for p in (d.get("prompt") if isinstance(d, dict) else None) or []:
        if (isinstance(p, dict) and _ID.match(str(p.get("id", ""))) and isinstance(p.get("nama"), str)
                and isinstance(p.get("isi"), str)):
            hasil.append({"id": p["id"], "nama": p["nama"], "isi": p["isi"]})
    return hasil


def _tulis(daftar):
    tmp = conf.PROMPT_FILE.with_name(conf.PROMPT_FILE.name + ".tmp")
    tmp.write_text(json.dumps({"prompt": daftar}, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(str(tmp), str(conf.PROMPT_FILE))


def daftar_prompt():
    """Semua prompt: bawaan lebih dulu, lalu buatan pengguna sesuai urutan dibuat."""
    return [bawaan()] + [dict(p, bawaan=False) for p in _baca()]


def tambah_prompt(nama, isi):
    """Simpan prompt baru. ValueError bila nama/isi tidak valid atau daftar penuh."""
    nama, isi = " ".join(str(nama or "").split()), str(isi or "").strip()
    if not nama:
        raise ValueError("Nama prompt wajib diisi")
    if len(nama) > conf.MAKS_NAMA_PROMPT:
        raise ValueError("Nama prompt maksimal %d karakter" % conf.MAKS_NAMA_PROMPT)
    if not isi:
        raise ValueError("Isi prompt wajib diisi")
    if len(isi) > conf.MAKS_ISI_PROMPT:
        raise ValueError("Isi prompt maksimal %d karakter" % conf.MAKS_ISI_PROMPT)
    with _KUNCI:
        ada = _baca()
        if len(ada) >= conf.MAKS_PROMPT:
            raise ValueError("Daftar prompt penuh (maks %d). Hapus yang tidak dipakai." % conf.MAKS_PROMPT)
        if any(p["nama"].lower() == nama.lower() for p in ada) or nama.lower() == bawaan()["nama"].lower():
            raise ValueError("Sudah ada prompt dengan nama itu")
        item = {"id": "p" + secrets.token_hex(4), "nama": nama, "isi": isi}
        _tulis(ada + [item])
    return dict(item, bawaan=False)


def hapus_prompt(pid):
    """Hapus prompt buatan pengguna. Kembalian: True bila ada yang terhapus. ValueError untuk bawaan."""
    if pid == conf.PROMPT_BAWAAN:
        raise ValueError("Prompt bawaan tidak bisa dihapus")
    with _KUNCI:
        ada = _baca()
        sisa = [p for p in ada if p["id"] != pid]
        if len(sisa) == len(ada):
            return False
        _tulis(sisa)
    return True


def berlaku(skill):
    """Prompt pilihan dipakai hanya bila skill 'tanpa' aktif dan tidak ada skill dengan akses sistem
    (dasar/kompleks), karena skill itu memakai prompt sistem bertool sendiri."""
    s = set(skill or ())
    return "tanpa" in s and not (s & {"dasar", "kompleks"})


def rapikan_pilihan(ids):
    """Daftar id yang valid (yang masih ada) menurut urutan daftar. None bila `ids` None."""
    if ids is None:
        return None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ValueError("Pilihan prompt tidak valid")
    ada = {p["id"] for p in daftar_prompt()}
    pilih = set(ids) & ada
    return [p["id"] for p in daftar_prompt() if p["id"] in pilih]


def rakit(ids):
    """Teks dasar untuk agen.buat_system(dasar=...) dan nama prompt yang dipakai.

    Kembalian: (dasar, nama). dasar None = pakai SYSTEM_CHAT bawaan (cara lama); "" = tanpa prompt;
    selain itu gabungan teks prompt terpilih. Id yang sudah dihapus dilewati; bila pilihan tidak
    kosong tetapi semuanya sudah dihapus, kembali ke bawaan (bukan diam-diam menjadi murni)."""
    if ids is None:
        return None, [bawaan()["nama"]]
    semua = {p["id"]: p for p in daftar_prompt()}
    pilih = [i for i in ids if i in semua]
    if ids and not pilih:
        return None, [bawaan()["nama"]]
    urut = [p for p in daftar_prompt() if p["id"] in set(pilih)]
    nama = [p["nama"] for p in urut]
    if not urut:
        return "", []
    if [p["id"] for p in urut] == [conf.PROMPT_BAWAAN]:
        return None, nama
    return "\n\n".join(p["isi"] for p in urut), nama


__all__ = ["bawaan", "daftar_prompt", "tambah_prompt", "hapus_prompt", "berlaku", "rapikan_pilihan", "rakit"]
