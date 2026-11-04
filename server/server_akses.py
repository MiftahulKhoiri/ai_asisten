"""server_akses.py - token akses, alamat IP jaringan lokal, penyaring alamat klien, dan pembatas token salah."""

import ipaddress
import os
import secrets
import socket
import threading
import time
from . import server_config as conf

_CGNAT = ipaddress.ip_network("100.64.0.0/10")    # rentang VPN seperti Tailscale: dianggap jaringan lokal


def muat_token(baru=False):
    if conf.TOKEN_FILE.exists() and not baru:
        t = conf.TOKEN_FILE.read_text().strip()
        if len(t) >= 16:
            return t
    t = secrets.token_urlsafe(18)
    fd = os.open(conf.TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(t)
    return t


def ip_lan():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def _ip(teks):
    """Teks -> objek alamat IP (IPv4-mapped IPv6 dipetakan ke IPv4), atau None bila bukan alamat."""
    try:
        a = ipaddress.ip_address(str(teks).split("%", 1)[0])    # buang zona IPv6: fe80::1%eth0
    except ValueError:
        return None
    return getattr(a, "ipv4_mapped", None) or a


def ip_loopback(teks):
    a = _ip(teks)
    return bool(a and a.is_loopback)


def ip_lokal(teks):
    """True untuk perangkat ini, jaringan rumah/kantor (10.x, 172.16-31.x, 192.168.x, fc00::/7),
    link-local, dan rentang VPN 100.64.0.0/10. Alamat internet publik -> False."""
    a = _ip(teks)
    if a is None:
        return False
    return a.is_loopback or a.is_private or a.is_link_local or (a.version == 4 and a in _CGNAT)


_cache_izin = {}


def jaringan_tambahan(teks=None):
    """(jaringan, salah) dari ASISTEN_IZIN_IP: entri dipisah koma/spasi, tiap entri IP atau CIDR."""
    teks = conf.IZIN_IP if teks is None else teks
    if teks not in _cache_izin:
        ok, salah = [], []
        for e in teks.replace(",", " ").split():
            try:
                ok.append(ipaddress.ip_network(e, strict=False))
            except ValueError:
                salah.append(e)
        if len(_cache_izin) > 8:
            _cache_izin.clear()
        _cache_izin[teks] = (tuple(ok), tuple(salah))
    return _cache_izin[teks]


def alamat_diizinkan(teks):
    """Boleh terhubung? Jaringan lokal selalu boleh; alamat publik hanya bila ASISTEN_IZIN_PUBLIK=1
    atau ada di ASISTEN_IZIN_IP. Alamat yang tidak bisa dibaca ditolak."""
    if ip_lokal(teks):
        return True
    if conf.IZIN_PUBLIK:
        return _ip(teks) is not None
    a = _ip(teks)
    return bool(a and any(a in n for n in jaringan_tambahan()[0]))


class PembatasGagal:
    """Menghitung token salah per alamat. Terlalu sering dalam satu jendela -> dikunci sementara,
    dan kunci berikutnya berlipat dua (maks `conf.GAGAL_KUNCI_MAKS`). Token benar menghapus catatan.

    Perangkat ini sendiri (loopback) tidak pernah dikunci: yang punya akses ke berkas `.token` tidak
    perlu menebak. Selama terkunci, token TIDAK diperiksa sama sekali (tebakan benar pun ditolak),
    dan permintaan yang ditolak tidak memperpanjang kunci."""

    MAKS_CATATAN = 1024

    def __init__(self, jam=time.monotonic):
        self._jam = jam
        self._kunci = threading.Lock()
        self._data = {}

    def sisa_kunci(self, ip):
        """Detik tersisa sampai kunci berakhir (0 = tidak terkunci)."""
        if ip_loopback(ip):
            return 0.0
        with self._kunci:
            d = self._data.get(ip)
            return max(0.0, d["sampai"] - self._jam()) if d else 0.0

    def catat_gagal(self, ip):
        """Catat satu token salah. Mengembalikan lama kunci BARU dalam detik (0 = belum terkunci)."""
        if ip_loopback(ip):
            return 0
        now = self._jam()
        with self._kunci:
            d = self._data.get(ip)
            if d is None:
                self._sisihkan(now)
                d = self._data[ip] = {"waktu": [], "sampai": 0.0, "tingkat": 0, "terakhir": now}
            elif now - d["terakhir"] > 4 * conf.GAGAL_KUNCI_MAKS:
                d.update(waktu=[], tingkat=0)                       # sudah lama tenang: mulai dari awal
            d["terakhir"] = now
            d["waktu"] = [t for t in d["waktu"] if now - t < conf.GAGAL_JENDELA]
            d["waktu"].append(now)
            if len(d["waktu"]) < conf.GAGAL_MAKS:
                return 0
            lama = min(conf.GAGAL_KUNCI * (2 ** d["tingkat"]), conf.GAGAL_KUNCI_MAKS)
            d.update(waktu=[], sampai=now + lama, tingkat=d["tingkat"] + 1)
            return lama

    def catat_berhasil(self, ip):
        with self._kunci:
            self._data.pop(ip, None)

    def _sisihkan(self, now):
        """Jaga memori: buang catatan lama; bila masih penuh, buang yang paling lama tidak aktif."""
        if len(self._data) < self.MAKS_CATATAN:
            return
        for k in [k for k, d in self._data.items() if d["sampai"] < now and now - d["terakhir"] > conf.GAGAL_JENDELA]:
            del self._data[k]
        while len(self._data) >= self.MAKS_CATATAN:
            del self._data[min(self._data, key=lambda k: self._data[k]["terakhir"])]


PEMBATAS = PembatasGagal()


__all__ = ['muat_token', 'ip_lan', 'ip_loopback', 'ip_lokal', 'jaringan_tambahan', 'alamat_diizinkan',
           'PembatasGagal', 'PEMBATAS']
