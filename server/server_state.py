"""server_state.py - keadaan bersama server: model aktif, kunci generasi, izin menunggu, buffer Agent.

Semua objek di sini dimutasi di tempat (tidak pernah diganti), jadi aman diimpor dari mana saja.
"""

import threading
import time


S = {"model": None, "target": None, "status": "kosong", "pesan": "",
     "kita_muat": False, "auto": False, "aktivitas": time.time(),
     "skill": None}   # tuple skill (tanpa/web/dasar/kompleks/kritis), dipilih di web
S_LOCK = threading.RLock()
GEN_LOCK = threading.Lock()   # hanya satu proses generasi pada satu waktu
AKTIF = {"ctx": None}
KONF = {}                     # kid -> [Event, setuju]

# Proses Agent berjalan di latar belakang, terlepas dari halaman web: semua event disimpan di
# buffer ini. Halaman (yang baru dibuka lagi, atau dari HP lain) membaca buffer lewat
# /api/agent/event dan menampilkan ulang semua yang sudah terjadi.
AGENT = {"sesi": None, "id": None, "tugas": "", "events": [], "awal": 0,
         "aktif": False, "mulai": 0.0, "status": None}
AGENT_COND = threading.Condition()


__all__ = ['S', 'S_LOCK', 'GEN_LOCK', 'AKTIF', 'KONF', 'AGENT', 'AGENT_COND']
