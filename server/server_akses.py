"""server_akses.py - token akses dan alamat IP jaringan lokal."""

import os
import secrets
import socket
from . import server_config as conf


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


__all__ = ['muat_token', 'ip_lan']
