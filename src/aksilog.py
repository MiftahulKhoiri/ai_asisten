"""aksilog.py - menulis aksi.log dengan rotasi sederhana.

Saat ukuran file mencapai batas, aksi.log diganti nama menjadi aksi.log.1, yang lama
menjadi aksi.log.2, dan seterusnya. Salinan tertua dibuang. Total pemakaian disk
paling banyak (salinan + 1) x batas.

Batas ukuran: ASISTEN_LOG_MAKS_KB (bawaan 1024 = 1 MB, 0 = tanpa rotasi).
"""
import os
import threading
from pathlib import Path

SALINAN = 3          # aksi.log.1 .. aksi.log.3
_KUNCI = threading.Lock()   # server web menulis dari banyak thread


def _maks_byte():
    try:
        return max(0, int(os.environ.get("ASISTEN_LOG_MAKS_KB", "1024"))) * 1024
    except ValueError:
        return 1024 * 1024


def _putar(path, maks, salinan):
    try:
        if path.stat().st_size < maks:
            return
    except OSError:
        return
    for i in range(max(1, salinan), 0, -1):
        asal = path if i == 1 else path.with_name(f"{path.name}.{i - 1}")
        if asal.exists():
            os.replace(asal, path.with_name(f"{path.name}.{i}"))


def tulis(path, baris, maks=None, salinan=SALINAN):
    """Tambahkan `baris` ke file log; putar dulu bila sudah mencapai `maks` byte.

    Kegagalan menulis (disk penuh, izin) tidak pernah mengganggu pemanggil.
    """
    path = Path(path)
    maks = _maks_byte() if maks is None else maks
    try:
        with _KUNCI:
            if maks > 0:
                _putar(path, maks, salinan)
            with open(path, "a", encoding="utf-8") as f:
                f.write(baris)
    except OSError:
        pass
