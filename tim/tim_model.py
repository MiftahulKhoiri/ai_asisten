"""Muat dan bongkar model di llama-server (mode router), satu per satu bergiliran.
"""
import time
import urllib.error

import agen

from . import tim_config as conf
from .tim_config import Batal


_TIDUR = time.sleep          # diganti pada pengujian


DIMUAT = set()               # model yang dimuat oleh Agent (dibongkar saat aplikasi ditutup)


def status_model(nama):
    """'loaded' / 'loading' / 'unloaded' / 'failed', atau None bila model tidak ada."""
    for m in agen.llama("/v1/models", timeout=10)["data"]:
        if m["id"] == nama:
            return (m.get("status") or {}).get("value") or "unloaded"
    return None


def bongkar(nama):
    try:
        agen.llama("/models/unload", {"model": nama}, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code != 400:   # 400 = model memang tidak berjalan
            raise
    DIMUAT.discard(nama)


def bongkar_sisa():
    """Bongkar semua model yang dimuat Agent (dipanggil saat aplikasi ditutup)."""
    hasil = []
    for nama in list(DIMUAT):
        try:
            bongkar(nama)
            hasil.append(nama)
        except Exception:  # noqa: BLE001
            pass
    return hasil


def muat(nama, ctx):
    """Generator event. Nilai akhir: True bila model dimuat oleh kita (boleh dibongkar)."""
    st = status_model(nama)
    if st is None:
        raise RuntimeError("Model tidak ditemukan di llama-server: " + nama)
    if st == "loaded":
        return nama in DIMUAT
    mulai = time.time()
    if st != "loading":
        agen.llama("/models/load", {"model": nama}, timeout=30)
    DIMUAT.add(nama)
    yield {"t": "muat", "model": nama, "d": "Memuat %s ..." % nama}
    try:
        while True:
            _TIDUR(2)
            if ctx.batal.is_set():
                raise Batal()
            st = status_model(nama)
            detik = int(time.time() - mulai)
            if st == "loaded":
                break
            if st == "failed":
                raise RuntimeError("llama-server gagal memuat " + nama)
            if detik > conf.BATAS_MUAT:
                raise RuntimeError("%s belum siap setelah %d detik" % (nama, conf.BATAS_MUAT))
            yield {"t": "muat", "model": nama, "d": "Memuat %s ... %d dtk" % (nama, detik)}
    except BaseException:
        try:
            bongkar(nama)
        except Exception:  # noqa: BLE001
            pass
        raise
    yield {"t": "muat_selesai", "model": nama, "detik": int(time.time() - mulai)}
    return True


class Pemuat:
    """Mengatur model mana yang sedang termuat selama satu proses Agent."""

    def __init__(self, ctx, bongkar_tiap):
        self.ctx = ctx
        self.bongkar_tiap = bongkar_tiap
        self.milik = {}      # nama -> True bila kita yang memuat (boleh dibongkar)

    def pakai(self, nama):
        if nama not in self.milik:
            self.milik[nama] = yield from muat(nama, self.ctx)

    def lepas(self, nama):
        if self.milik.pop(nama, False):
            yield {"t": "bongkar_mulai", "model": nama}   # tampil di log langsung sebelum menunggu
            bongkar(nama)
            yield {"t": "bongkar", "model": nama}

    def selesai_tahap(self, berikutnya=None):
        """Bongkar model yang sudah tidak dipakai (kecuali yang dipakai tahap berikutnya)."""
        if not self.bongkar_tiap:
            return
        for nama in list(self.milik):
            if nama != berikutnya:
                yield from self.lepas(nama)

    def lepas_semua(self):
        for nama in list(self.milik):
            yield from self.lepas(nama)

    def lepas_diam(self):
        """Jaring pengaman (tanpa event): dipanggil di 'finally'."""
        for nama in list(self.milik):
            try:
                if self.milik.pop(nama):
                    bongkar(nama)
            except Exception:  # noqa: BLE001
                pass
