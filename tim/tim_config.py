"""Konfigurasi Agent: batas, folder kerja, konstanta, dan validasi pengaturan dari web.
"""
import os
import re
from pathlib import Path

import agen


KERJA = Path(os.environ.get("ASISTEN_AGENT_DIR", str(Path.home() / "agent_kerja")))


TOKEN_TAHAP = agen._env_int("ASISTEN_AGENT_TOKENS", 3000, 256)   # tahap Pelaksana (menulis kode)


TOKEN_RENCANA = 1500


TOKEN_PERIKSA = 1000


TOKEN_JELAS = 800


UJI_DETIK = agen._env_int("ASISTEN_AGENT_UJI_DTK", 20, 2)


LANGKAH_MIN, LANGKAH_MAKS, LANGKAH_BAWAAN = 1, 10, 3


MAKS_BERKAS_RENCANA = 5     # berkas per lembar tugas


MAKS_BERKAS_TOTAL = 12      # berkas per proyek


MAKS_UKURAN = 200_000       # byte per berkas


MAKS_TUGAS = 4000           # karakter perintah pengguna


BATAS_MUAT = 300            # detik menunggu satu model siap


EKSTENSI = {".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".sh", ".c", ".cpp",
            ".h", ".hpp", ".ini", ".toml", ".yaml", ".yml", ".csv", ".cfg"}


INTERPRETER = {"python3", "python", "node"}


ID_RUN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


PERAN = {"rencana": "Perencana", "tulis": "Pelaksana", "periksa": "Pemeriksa",
         "jelaskan": "Penjelas"}


STATUS_TEKS = {"berjalan": "sedang berjalan",
               "terhenti": "terhenti (aplikasi dimatikan saat proses berjalan)",
               "lolos": "dinyatakan jadi oleh Pemeriksa",
               "belum": "belum sempurna (batas putaran tercapai)",
               "butuh_info": "menunggu info tambahan dari pengguna",
               "batal": "dibatalkan", "error": "berhenti karena error"}


class Batal(Exception):
    """Pengguna menekan Stop."""


def siapkan_cfg(b, tersedia):
    """Validasi pengaturan dari web. Kembalian: (cfg, pesan_error)."""
    try:
        mode = 3 if int(b.get("mode") or 2) == 3 else 2
    except (TypeError, ValueError):
        mode = 2
    mp, me = b.get("model_p"), b.get("model_e")
    mc = b.get("model_c") if mode == 3 else mp
    for n in (mp, me, mc):
        if n not in tersedia:
            return None, "Model tidak dikenal: %s" % (n,)
    if len({mp, me, mc}) < 2:
        return None, "Pilih minimal 2 model yang berbeda."
    try:
        maks = int(b.get("maks") or LANGKAH_BAWAAN)
    except (TypeError, ValueError):
        maks = LANGKAH_BAWAAN
    maks = max(LANGKAH_MIN, min(LANGKAH_MAKS, maks))
    return {"mode": mode, "model_p": mp, "model_e": me, "model_c": mc, "maks": maks,
            "bongkar": bool(b.get("bongkar", True)), "uji": b.get("uji") is True}, ""


def id_valid(run_id):
    return bool(ID_RUN.match(str(run_id or "")))
