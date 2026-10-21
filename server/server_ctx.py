"""server_ctx.py - konteks satu proses generasi: mode AUTO, pembatalan, dan minta izin lewat web."""

import secrets
import threading
from . import server_state as state


class Ctx:
    def __init__(self, q, batal):
        self.q = q
        self.batal = batal
        self.tercemar = False   # True setelah tool web dipakai: AUTO tidak berlaku (lihat util._izin)

    @property
    def auto(self):
        return state.S["auto"]

    def konfirmasi(self, jenis, ringkas, detail=""):
        kid = secrets.token_hex(4)
        ev = threading.Event()
        state.KONF[kid] = [ev, False]
        self.q.put({"t": "konfirmasi", "kid": kid, "jenis": jenis,
                    "ringkas": ringkas, "detail": detail})
        for _ in range(120):  # tunggu maksimal 2 menit
            if ev.wait(1) or self.batal.is_set():
                break
        item = state.KONF.pop(kid, None)
        return bool(item and item[0].is_set() and item[1])


__all__ = ['Ctx']
