"""agen - inti agen AI Asisten (dulu satu berkas agen.py).

Berisi: klien llama-server dengan streaming, riwayat, dan loop agen (function calling).
Semua tool ada di paket src/ (pintu masuknya src/tolls.py). Hanya library standar Python.
Dipakai oleh asisten.py (server web) dan paket tim/.

Pembagian modul (urutan impor = urutan ketergantungan):
  agen_config   konfigurasi: LLAMA_URL, CTX_MAKS, MAX_TOKENS, GERBANG, LOG_AKSI, ...
  agen_prompt   prompt sistem, gerbang tool (perlu_tool), jatah riwayat (max_history)
  agen_llama    klien llama-server: llama(), stream_chat(), _baca_stream()
  agen_memori   pemangkasan riwayat (siapkan) dan peringkasan pesan lama
  agen_kritik   skill berpikir kritis tahap 2 (_kritik)
  agen_giliran  loop agen: giliran() dan eksekusi tool calls

Semua nama lama tetap bisa dipakai lewat `import agen` (agen.giliran, agen.llama, agen.CTX_MAKS,
agen._env_int, ...). Mengubah nilai lewat paket, mis. `agen.GERBANG = False` atau
`agen.stream_chat = palsu` (atau mock.patch.object(agen, ...)), diteruskan ke modul pemiliknya
sehingga tetap berlaku. Kode baru sebaiknya langsung memakai modul pemilik (mis. agen_config).
"""
import sys
import types
import urllib.error    # noqa: F401 - agen.urllib dipakai pengujian
import urllib.request  # noqa: F401

from src import aksilog, tolls  # noqa: F401 - agen.tolls dipakai asisten.py

from . import agen_config, agen_giliran, agen_kritik, agen_llama, agen_memori, agen_prompt

_MODUL = (agen_config, agen_prompt, agen_llama, agen_memori, agen_kritik, agen_giliran)
_PEMILIK = {}
for _m in _MODUL:
    for _nama in _m.__all__:
        if _nama in _PEMILIK:
            raise ImportError("nama ganda di paket agen: %s (%s dan %s)"
                              % (_nama, _PEMILIK[_nama].__name__, _m.__name__))
        _PEMILIK[_nama] = _m
        globals()[_nama] = getattr(_m, _nama)
del _m, _nama


class _Paket(types.ModuleType):
    """Penetapan nilai lewat paket (agen.X = ...) diteruskan ke modul yang memiliki X."""

    def __setattr__(self, nama, nilai):
        pemilik = _PEMILIK.get(nama)
        if pemilik is not None:
            setattr(pemilik, nama, nilai)
        super().__setattr__(nama, nilai)


sys.modules[__name__].__class__ = _Paket
