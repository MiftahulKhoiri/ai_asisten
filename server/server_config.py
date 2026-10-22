"""server_config.py - folder, token, dan batas-batas server.

Modul lain MEMBACA nilai di sini lewat `conf.NAMA` saat dipakai (bukan menyalin saat impor).
"""

import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent   # folder proyek (berisi asisten.py, web/, riwayat/)
WEB = BASE / "web"
RIWAYAT = BASE / "riwayat"
TOKEN_FILE = BASE / ".token"
MODELS_DIR = Path(os.environ.get("ASISTEN_MODELS_DIR", str(Path.home() / "models")))
ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")

TOKEN = ""
IDLE_MENIT = 20
WARNA = sys.stdout.isatty()

# Proses Agent berjalan di latar belakang, terlepas dari halaman web (lihat server_agent.py).
AGENT_MAKS_EVENT = 20000      # event tertua dibuang bila buffer melebihi ini
AGENT_BATCH = 4000            # event paling banyak per jawaban /api/agent/event
AGENT_TUNGGU_MAKS = 25        # detik paling lama satu long-poll menunggu event baru


# Unggahan berkas (teks/kode dan zip) untuk chat dan Agent: ditampung dulu di UNGGAH/<paket>/.
UNGGAH = BASE / "unggahan"
ID_PAKET = re.compile(r"^[0-9a-f]{12}$")
MAKS_UNGGAH_BYTE = int(os.environ.get("ASISTEN_UNGGAH_MB", "10")) * 1_000_000   # satu unggahan (zip)
MAKS_ZIP_TOTAL = 30_000_000     # byte hasil ekstrak satu zip (penangkal zip bomb)
MAKS_ZIP_ENTRI = 3000           # entri zip yang diperiksa
MAKS_BERKAS_PAKET = 100         # berkas dalam satu paket
UNGGAH_UMUR_JAM = 24            # paket yang tidak dipakai dibersihkan setelah ini

__all__ = ['UNGGAH', 'ID_PAKET', 'MAKS_UNGGAH_BYTE', 'MAKS_ZIP_TOTAL', 'MAKS_ZIP_ENTRI',
           'MAKS_BERKAS_PAKET', 'UNGGAH_UMUR_JAM', 'BASE', 'WEB', 'RIWAYAT', 'TOKEN_FILE', 'MODELS_DIR', 'ID_RE', 'TOKEN', 'IDLE_MENIT', 'WARNA', 'AGENT_MAKS_EVENT', 'AGENT_BATCH', 'AGENT_TUNGGU_MAKS']
