"""server - server web AI Asisten (dulu bagian dari asisten.py).

Pembagian modul (urutan impor = urutan ketergantungan):
  server_config   folder, token, batas
  server_state    keadaan bersama: model aktif, kunci generasi, izin menunggu, buffer Agent
  server_log      log berwarna di terminal, ringkasan event
  server_akses    token akses dan alamat IP lokal
  server_model    daftar model, muat/bongkar di llama-server, idle, sesi
  server_chat     penyimpanan riwayat obrolan
  server_unggah   unggahan berkas (teks/kode, zip) untuk chat dan Agent
  server_ctx      konteks satu proses generasi (mode AUTO, batal, izin lewat web)
  server_agent    buffer event Agent di latar belakang dan mulai_proses()
  server_handoff  serah terima chat -> Agent -> chat (brief, lampiran obrolan, hasil)
  server_status   isi /api/status dan /api/agent/status
  server_http     penangan HTTP (rute /api, file statis)
  server_main     pintu masuk: argumen, siklus hidup, penutupan rapi

Pintu masuk tetap `python3 asisten.py`. Semua nama lama tersedia lewat `import asisten`
(asisten.GEN_LOCK, asisten.H, asisten.daftar_model, ...); penetapan nilai lewat asisten atau
paket ini diteruskan ke modul pemiliknya (lihat server_shim.py). Kode baru sebaiknya memakai
modul pemilik langsung.
"""
from . import (server_config, server_state, server_log, server_akses, server_model, server_chat,
               server_unggah, server_ctx, server_agent, server_handoff, server_status, server_http, server_main,
               server_shim)

_MODUL = (server_config, server_state, server_log, server_akses, server_model, server_chat,
          server_unggah, server_ctx, server_agent, server_handoff, server_status, server_http, server_main)
_PEMILIK = {}
for _m in _MODUL:
    for _nama in _m.__all__:
        if _nama in _PEMILIK:
            raise ImportError("nama ganda di paket server: %s (%s dan %s)"
                              % (_nama, _PEMILIK[_nama].__name__, _m.__name__))
        _PEMILIK[_nama] = _m
        globals()[_nama] = getattr(_m, _nama)
del _m, _nama

import sys  # noqa: E402

server_shim.pasang(sys.modules[__name__], _PEMILIK)
 