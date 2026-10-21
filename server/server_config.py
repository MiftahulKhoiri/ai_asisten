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


__all__ = ['BASE', 'WEB', 'RIWAYAT', 'TOKEN_FILE', 'MODELS_DIR', 'ID_RE', 'TOKEN', 'IDLE_MENIT', 'WARNA', 'AGENT_MAKS_EVENT', 'AGENT_BATCH', 'AGENT_TUNGGU_MAKS']
