#!/usr/bin/env python3
"""asisten.py - AI Asisten: server web + log di terminal.

Jalankan:   python3 asisten.py
Lalu buka alamat yang tampil di terminal dari HP (satu jaringan Wi-Fi).

- Terminal hanya untuk menyalakan aplikasi dan menampilkan log.
- Model BARU dimuat setelah dipilih di tampilan web, dan otomatis dibongkar
  saat sesi diakhiri, setelah idle, atau saat aplikasi ditutup (Ctrl+C).
- Halaman Agent (web/agent.html): beberapa model bekerja bergiliran (lihat paket tim/).
- Semua endpoint /api wajib token (disimpan di .token).
Hanya memakai library standar Python.
"""
import sys

import agen  # noqa: F401 - asisten.agen dipakai pengujian
import tim  # noqa: F401
import server
from server import server_shim

# Isi server dipecah ke paket server/. Semua nama lama tetap bisa dipakai lewat `import asisten`;
# penetapan nilai (asisten.TOKEN = ..., mock.patch.object(asisten, ...)) diteruskan ke modul pemilik.
for _nama, _modul in server._PEMILIK.items():
    globals()[_nama] = getattr(_modul, _nama)
server_shim.pasang(sys.modules[__name__], server._PEMILIK)

if __name__ == "__main__":
    server.main()
