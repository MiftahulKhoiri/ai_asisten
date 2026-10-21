"""server_shim.py - penerus penetapan nilai: `asisten.X = nilai` (atau mock.patch.object) diteruskan
ke modul yang memiliki X, supaya tetap berlaku setelah server dipecah jadi beberapa modul.

Dipakai oleh asisten.py dan server/__init__.py. Pembacaan nilai dari modul pemilik selalu lewat
atribut modul (mis. conf.TOKEN) saat dipakai, jadi nilai baru langsung terlihat oleh semua modul.
"""
import types


def pasang(modul, pemilik):
    """Ubah `modul` agar penetapan atribut miliknya diteruskan ke modul pemilik (nama -> modul)."""

    class _Penerus(types.ModuleType):
        def __setattr__(self, nama, nilai):
            m = pemilik.get(nama)
            if m is not None:
                setattr(m, nama, nilai)
            super().__setattr__(nama, nilai)

    modul.__class__ = _Penerus


__all__ = ["pasang"]
