"""tool_sistem.py - tool perintah shell, info sistem, proses, dan git."""

import os
import re
import shlex
import shutil
import signal
import socket

from .pengaman import cek_perintah
from .registri import tool
from .util import CMD_TIMEOUT, HOME, _baca, _ekor_teks, _fmt, _izin, _p, _run


@tool("jalankan_perintah", "Jalankan satu perintah bash. Hanya jika tool lain tidak cukup.",
      {"perintah": ("string", "perintah bash")}, wajib=["perintah"], dasar=True,
      ringkas=lambda a: "$ " + str(a.get("perintah", "")))
def jalankan_perintah(ctx, perintah):
    if not perintah.strip():
        return "ERROR: perintah kosong."
    hasil = cek_perintah(perintah)
    if hasil == "blokir":
        return "DITOLAK: perintah ini masuk daftar berbahaya dan diblokir."
    wajib = hasil == "izin"
    t = _izin(ctx, "shell", perintah, selalu=wajib)
    if t:
        return t.replace("tindakan ini", "perintah ini")
    kode, out = _run(perintah, timeout=CMD_TIMEOUT, cwd=HOME, shell=True)
    if kode is None:
        return f"GAGAL: {out}."
    return f"exit code {kode}\n{out or '(tidak ada output)'}"


_NAMA_LAYANAN = re.compile(r"^[A-Za-z0-9@._:\-]{1,100}$")


@tool("info_sistem",
      "Info sistem Pi. aspek: ringkas (suhu, CPU, RAM, disk), proses, port, jaringan, disk, "
      "layanan, log_layanan.",
      {"aspek": ("string", "jenis info", ["ringkas", "proses", "port", "jaringan", "disk",
                                          "layanan", "log_layanan"]),
       "nama": ("string", "nama service (layanan/log_layanan)")},
      ringkas=lambda a: f"info sistem: {a.get('aspek', 'ringkas')} {a.get('nama', '')}".strip())
def info_sistem(ctx, aspek="ringkas", nama=""):
    aspek = (aspek or "ringkas").strip().lower()
    if aspek == "ringkas":
        return _ringkas_sistem()
    perintah = {
        "proses": ["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"],
        "port": ["ss", "-tln"],
        "jaringan": ["ip", "-br", "addr"],
        "disk": ["df", "-h", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"],
    }
    if aspek in perintah:
        kode, out = _run(perintah[aspek])
        if aspek == "proses":
            out = "\n".join(out.splitlines()[:11])
        return out or "(tidak ada output)"
    if aspek in ("layanan", "log_layanan"):
        if not _NAMA_LAYANAN.match(nama or ""):
            return "ERROR: isi 'nama' dengan nama service yang valid, mis. ssh."
        if aspek == "layanan":
            _, aktif = _run(["systemctl", "is-active", nama])
            _, status = _run(["systemctl", "status", nama, "--no-pager", "-n", "8"])
            return f"status: {aktif}\n{status}"
        _, out = _run(["journalctl", "-u", nama, "-n", "40", "--no-pager"])
        return _ekor_teks(out) or "(tidak ada log)"
    return "ERROR: aspek tidak dikenal: " + aspek


def _ringkas_sistem():
    baris = [f"host: {socket.gethostname()}"]
    up = _baca("/proc/uptime")
    if up:
        d = int(float(up.split()[0]))
        baris.append(f"uptime: {d // 86400} hari {d % 86400 // 3600} jam {d % 3600 // 60} menit")
    la = _baca("/proc/loadavg")
    if la:
        baris.append(f"beban CPU (1/5/15 mnt): {' '.join(la.split()[:3])} dari {os.cpu_count()} core")
    mem = _baca("/proc/meminfo")
    if mem:
        m = {}
        for b in mem.splitlines():
            k, _, v = b.partition(":")
            m[k] = int(v.split()[0]) * 1024 if v.split() else 0
        total, avail = m.get("MemTotal", 0), m.get("MemAvailable", 0)
        baris.append(f"RAM: terpakai {_fmt(total - avail)} dari {_fmt(total)}")
        if m.get("SwapTotal"):
            baris.append(f"swap: terpakai {_fmt(m['SwapTotal'] - m.get('SwapFree', 0))} "
                         f"dari {_fmt(m['SwapTotal'])}")
    for label, lokasi in (("disk /", "/"), ("disk home", str(HOME))):
        try:
            du = shutil.disk_usage(lokasi)
            baris.append(f"{label}: terpakai {_fmt(du.used)} dari {_fmt(du.total)} "
                         f"({du.used * 100 // du.total}%)")
        except OSError:
            pass
    suhu = _baca("/sys/class/thermal/thermal_zone0/temp")
    if suhu and suhu.lstrip("-").isdigit():
        baris.append(f"suhu CPU: {int(suhu) / 1000:.1f} C")
    if shutil.which("vcgencmd"):
        kode, out = _run(["vcgencmd", "get_throttled"])
        if kode == 0:
            baris.append(f"throttled: {out.split('=')[-1]} (0x0 = normal)")
    return "\n".join(baris)


GIT_ENV = {"GIT_PAGER": "cat", "GIT_TERMINAL_PROMPT": "0", "GIT_EDITOR": "true"}
GIT_BOLEH = {"add", "commit", "fetch", "pull", "push", "switch", "checkout", "branch",
             "merge", "stash", "tag", "clone", "init", "remote"}
GIT_JARINGAN = {"fetch", "pull", "push", "clone"}
GIT_FLAG_DILARANG = {"--force", "-f", "--force-with-lease", "--hard", "-D", "--delete",
                     "--no-verify"}
GIT_AWALAN_DILARANG = ("--upload-pack", "--receive-pack", "--exec", "--config")


@tool("git_baca", "Info repo git. diff + file = perubahan file itu.",
      {"path": ("string", "folder repo, default home"),
       "aksi": ("string", "jenis info", ["status", "log", "diff", "branch", "remote"]),
       "file": ("string", "(opsional) file")},
      ringkas=lambda a: f"git {a.get('aksi', 'status')} {a.get('path', '~')}")
def git_baca(ctx, path=".", aksi="status", file=""):
    repo = _p(path)
    if not repo.is_dir():
        return f"ERROR: bukan folder: {repo}"
    dasar = ["git", "--no-pager", "-C", str(repo)]
    if aksi == "status":
        cmd = dasar + ["status", "-sb"]
    elif aksi == "log":
        cmd = dasar + ["log", "--oneline", "-n", "15"] + (["--", file] if file else [])
    elif aksi == "diff":
        cmd = dasar + (["diff", "--", file] if file else ["diff", "--stat"])
    elif aksi == "branch":
        cmd = dasar + ["branch", "-vv"]
    elif aksi == "remote":
        cmd = dasar + ["remote", "-v"]
    else:
        return "ERROR: aksi harus salah satu: status, log, diff, branch, remote."
    kode, out = _run(cmd, timeout=20, env=GIT_ENV)
    return out or "(tidak ada output; tidak ada perubahan)"


@tool("git_tulis",
      "Git pengubah: add, commit -m, fetch, pull, push, switch, checkout, branch, merge, stash, "
      "tag, clone, init, remote. Force/hard dilarang.",
      {"path": ("string", "folder repo (clone: folder induk)"),
       "perintah": ("string", "argumen git tanpa 'git', mis. commit -m \"pesan\"")},
      wajib=["path", "perintah"], ringkas=lambda a: f"git {a.get('perintah', '')}")
def git_tulis(ctx, path, perintah):
    repo = _p(path)
    if not repo.is_dir():
        return f"ERROR: bukan folder: {repo}"
    try:
        args = shlex.split(perintah)
    except ValueError as e:
        return f"ERROR: tanda kutip tidak seimbang ({e})"
    if args and args[0] == "git":
        args = args[1:]
    if not args:
        return "ERROR: perintah git kosong."
    sub = args[0]
    if sub not in GIT_BOLEH:
        return "DITOLAK: subperintah git tidak diizinkan. Boleh: " + ", ".join(sorted(GIT_BOLEH))
    for a in args[1:]:
        if a in GIT_FLAG_DILARANG or a.startswith(GIT_AWALAN_DILARANG):
            return f"DITOLAK: opsi berbahaya tidak diizinkan: {a}"
    if sub == "push" and any(a.startswith((":", "+")) for a in args[1:]):
        return "DITOLAK: push dengan refspec ':' atau '+' (hapus/force) tidak diizinkan."
    if sub == "checkout" and any(a in ("--", ".") for a in args[1:]):
        return "DITOLAK: checkout yang membuang perubahan file tidak diizinkan."
    if sub == "stash" and any(a in ("drop", "clear") for a in args[1:]):
        return "DITOLAK: stash drop/clear tidak diizinkan."
    if sub == "commit" and not any(a in ("-m", "--message") or a.startswith(("-m", "--message=", "-am"))
                                   for a in args[1:]):
        return "ERROR: commit harus memakai -m \"pesan\"."
    t = _izin(ctx, "git", f"git {shlex.join(args)}   (di {repo})", selalu=(sub == "push"))
    if t:
        return t
    kode, out = _run(["git", "--no-pager"] + args, cwd=repo, env=GIT_ENV,
                     timeout=120 if sub in GIT_JARINGAN else 30)
    if kode is None:
        return f"GAGAL: {out}."
    return f"exit code {kode}\n{out or '(tidak ada output)'}"


_SINYAL = {"TERM": signal.SIGTERM, "KILL": signal.SIGKILL, "HUP": signal.SIGHUP,
           "INT": signal.SIGINT}


@tool("matikan_proses", "Hentikan proses menurut PID (lihat info_sistem proses). Selalu minta izin.",
      {"pid": ("integer", "nomor PID"),
       "sinyal": ("string", "TERM (halus) atau KILL", ["TERM", "KILL", "HUP", "INT"])},
      wajib=["pid"], ringkas=lambda a: f"matikan PID {a.get('pid', '')} ({a.get('sinyal', 'TERM')})")
def matikan_proses(ctx, pid, sinyal="TERM"):
    pid, sinyal = int(pid), (sinyal or "TERM").upper()
    if sinyal not in _SINYAL:
        return "ERROR: sinyal harus salah satu: TERM, KILL, HUP, INT."
    if pid <= 1 or pid in (os.getpid(), os.getppid()):
        return "DITOLAK: PID ini tidak boleh dihentikan (sistem atau asisten ini sendiri)."
    nama = _baca(f"/proc/{pid}/comm")
    if nama is None:
        return f"ERROR: proses {pid} tidak ada."
    cmd = (_baca(f"/proc/{pid}/cmdline") or "").replace("\0", " ")[:200]
    t = _izin(ctx, "proses", f"kirim SIG{sinyal} ke PID {pid} ({nama})", cmd, selalu=True)
    if t:
        return t
    os.kill(pid, _SINYAL[sinyal])
    return f"Sinyal {sinyal} dikirim ke PID {pid} ({nama})."
