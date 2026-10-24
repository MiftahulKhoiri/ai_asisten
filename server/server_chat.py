"""server_chat.py - penyimpanan riwayat obrolan (satu berkas JSON per obrolan)."""

import json
import os
import secrets
import shutil
import threading
from datetime import datetime
from . import server_config as conf


_KUNCI_TULIS = threading.Lock()


def tambah_pesan(cid, pesan, perbarui=None):
    """Tambahkan satu pesan ke obrolan; aman dipanggil dari thread lain (mis. thread Agent yang
    menulis hasilnya). `perbarui(chat)` boleh mengubah bagian lain obrolan sebelum disimpan."""
    with _KUNCI_TULIS:
        chat = baca_chat(cid)
        if perbarui:
            perbarui(chat)
        if pesan is not None:
            chat["pesan"].append(pesan)
        simpan_chat(chat)
        return chat


def hapus_lampiran(cid):
    """Hapus folder lampiran (bahan kerja) milik obrolan."""
    if conf.ID_RE.match(cid or ""):
        shutil.rmtree(conf.RIWAYAT / (cid + ".lampiran"), ignore_errors=True)


def path_chat(cid):
    if not conf.ID_RE.match(cid or ""):
        raise FileNotFoundError("id tidak valid")
    return conf.RIWAYAT / f"{cid}.json"


def simpan_chat(chat):
    chat["diubah"] = datetime.now().isoformat(timespec="seconds")
    p = path_chat(chat["id"])
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(chat, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def baca_chat(cid):
    return json.loads(path_chat(cid).read_text(encoding="utf-8"))


def baru_chat(model):
    cid = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    chat = {"id": cid, "judul": "Obrolan baru", "model": model,
            "dibuat": datetime.now().isoformat(timespec="seconds"), "pesan": []}
    simpan_chat(chat)
    return chat


def cuplikan_chat(chat, maks=80):
    """Ringkasan satu baris: jawaban asisten terakhir (atau pesan terakhir)."""
    for peran in ("assistant", "user"):
        for m in reversed(chat.get("pesan", [])):
            teks = m.get("content") if m.get("role") == peran else None
            if isinstance(teks, str) and teks.strip():
                teks = " ".join(teks.split())
                return teks if len(teks) <= maks else teks[:maks - 1] + "\u2026"
    return ""


def hapus_semua_chat(kecuali=None):
    """Hapus semua file riwayat (kecuali satu id). Kembalian: jumlah yang dihapus."""
    n = 0
    for f in conf.RIWAYAT.glob("*.json"):
        if f.stem == kecuali:
            continue
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
        hapus_lampiran(f.stem)
    return n


def daftar_chat():
    file = sorted(conf.RIWAYAT.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    hasil = []
    for p in file[:100]:
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            hasil.append({"id": c["id"], "judul": c.get("judul") or "Obrolan",
                          "diubah": c.get("diubah", ""), "model": c.get("model"),
                          "jumlah": sum(1 for m in c.get("pesan", []) if m.get("role") == "user"),
                          "cuplikan": cuplikan_chat(c)})
        except (OSError, ValueError, KeyError):
            continue
    return hasil


__all__ = ['tambah_pesan', 'hapus_lampiran', 'path_chat', 'simpan_chat', 'baca_chat', 'baru_chat', 'cuplikan_chat', 'hapus_semua_chat', 'daftar_chat']
