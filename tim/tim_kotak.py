"""Kotak uji: menjalankan program buatan model dalam sandbox OS.

Eksekusi hanya diizinkan bila bubblewrap (bwrap) tersedia. Sandbox memakai namespace
user/PID/IPC/UTS/jaringan, filesystem minimal read-only untuk runtime, dan hanya folder
hasil proyek yang dapat ditulis. HOME/TMPDIR berada di tmpfs. Jika bwrap tidak tersedia
atau namespace ditolak kernel, eksekusi GAGAL TERTUTUP (tidak ada fallback tanpa isolasi).

Batas tambahan: RLIMIT_CPU, RLIMIT_FSIZE, RLIMIT_NOFILE, RLIMIT_NPROC dan RLIMIT_AS
(untuk selain Node.js). Node.js memakai --max-old-space-size; ini batas heap, bukan
batas RSS/cgroup yang keras. Untuk batas memori keras lintas runtime, jalankan layanan
di container/cgroup dengan MemoryMax.

Pengaturan:
  ASISTEN_UJI_RAM_MB       batas memori/heap, MB (bawaan 512; 0 = tanpa batas tambahan)
  ASISTEN_UJI_JARINGAN     "putus" (bawaan) atau "boleh" (berbagi jaringan secara eksplisit)
  ASISTEN_UJI_KELUARAN_KB  keluaran yang dibaca kembali, KB (bawaan 200)
"""
import json
import os
import resource
import shutil
import subprocess
import signal
import sys
import tempfile
from pathlib import Path

RAM_MB_BAWAAN = 512
FSIZE_MB = 20          # ukuran satu berkas yang boleh ditulis program (juga membatasi keluaran)
NOFILE = 256
PROSES_TAMBAHAN = 128  # task (proses/thread) baru yang boleh dibuat program, di atas yang sudah ada milik pengguna ini

_PELUNCUR = (
    "import json, os, resource, sys\n"
    "for nama, nilai in json.loads(sys.argv[1]).items():\n"
    "    try:\n"
    "        resource.setrlimit(getattr(resource, nama), (nilai, nilai))\n"
    "    except (ValueError, OSError):\n"
    "        pass\n"
    "os.execvp(sys.argv[2], sys.argv[2:])\n"
)

_JARINGAN_BISA = None   # cache hasil uji `unshare -rn true`


def _int_env(nama, bawaan):
    try:
        return max(0, int(os.environ.get(nama, bawaan)))
    except ValueError:
        return bawaan


def batas_ram_mb():
    return _int_env("ASISTEN_UJI_RAM_MB", RAM_MB_BAWAAN)


def bwrap_tersedia():
    """Apakah bubblewrap tersedia? Tanpa bwrap, program tidak boleh dijalankan."""
    return shutil.which("bwrap") is not None


def argumen_isolasi(cmd, cwd):
    """Bangun perintah bubblewrap; folder proyek adalah satu-satunya mount tulis.

    Tidak me-mount /home, /root, /run, /var, atau root filesystem host. Runtime
    sistem dipasang read-only. Namespace jaringan diputus secara default.
    """
    bwrap = shutil.which("bwrap")
    if not bwrap:
        raise FileNotFoundError("bubblewrap (bwrap) tidak terpasang; uji jalan ditolak demi keamanan")

    args = [bwrap, "--unshare-all", "--die-with-parent", "--new-session",
            "--cap-drop", "ALL", "--ro-bind", "/usr", "/usr"]

    # FHS berbeda antar distro: direktori ini bisa berupa symlink ke /usr atau
    # direktori nyata. Pertahankan bentuknya agar executable dan dynamic loader ditemukan.
    for path in ("/bin", "/sbin", "/lib", "/lib64"):
        if os.path.islink(path):
            args += ["--symlink", os.readlink(path), path]
        elif os.path.isdir(path):
            args += ["--ro-bind", path, path]

    # Hanya sertifikat publik; jangan mount /etc/ssl/private yang dapat berisi private key.
    if os.path.isdir("/etc/ssl/certs"):
        args += ["--ro-bind", "/etc/ssl/certs", "/etc/ssl/certs"]
    if os.path.isdir("/etc/pki/tls/certs"):
        args += ["--ro-bind", "/etc/pki/tls/certs", "/etc/pki/tls/certs"]
    if os.path.isfile("/etc/ld.so.cache"):
        args += ["--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache"]

    if os.environ.get("ASISTEN_UJI_JARINGAN", "putus").strip().lower() == "boleh":
        args += ["--share-net"]

    hasil = str(Path(cwd).resolve(strict=True))
    if not os.path.isdir(hasil):
        raise ValueError("folder hasil proyek bukan direktori")
    args += ["--dir", "/workspace", "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
             "--bind", hasil, "/workspace", "--chdir", "/workspace",
             "--setenv", "HOME", "/tmp",
             "--setenv", "TMPDIR", "/tmp",
             "--setenv", "PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
             "--setenv", "LANG", "C.UTF-8",
             "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
             "--setenv", "PYTHONUNBUFFERED", "1",
             "--"]
    return args


def ringkas_isolasi(cmd):
    """Ringkasan batas yang benar-benar diminta untuk proses uji."""
    bagian = ["bubblewrap: filesystem runtime read-only, folder hasil saja yang dapat ditulis",
              "namespace proses dan user terisolasi"]
    if os.environ.get("ASISTEN_UJI_JARINGAN", "putus").strip().lower() == "boleh":
        bagian.append("jaringan diizinkan oleh pengaturan")
    else:
        bagian.append("namespace jaringan diputus")
    ram = batas_ram_mb()
    if ram:
        bagian.append("RAM maks %d MB" % ram if not _node(cmd)
                      else "heap Node.js maks %d MB (bukan batas RSS keras)" % ram)
    else:
        bagian.append("batas RAM tambahan dimatikan")
    return ", ".join(bagian)

def _node(cmd):
    return os.path.basename(cmd[0]) in ("node", "nodejs")


def _proses_milik_sendiri():
    """Jumlah TASK (proses + thread) milik pengguna ini. RLIMIT_NPROC di Linux menghitung thread juga:
    menghitung proses saja membuat batas lebih kecil dari yang sudah terpakai (mis. Raspberry Pi OS
    dengan desktop: puluhan proses, ratusan thread), sehingga program uji tidak bisa membuat
    proses maupun thread sama sekali."""
    uid, n = os.getuid(), 0
    try:
        for d in os.listdir("/proc"):
            if d.isdigit():
                try:
                    if os.stat("/proc/" + d).st_uid == uid:
                        n += len(os.listdir("/proc/%s/task" % d)) or 1
                except OSError:
                    continue
    except OSError:
        return 0
    return n


def batas_rlimit(cmd, timeout):
    """Nama RLIMIT_* -> nilai, untuk perintah ini."""
    lim = {"RLIMIT_CPU": int(timeout) + 2, "RLIMIT_FSIZE": FSIZE_MB * 1_000_000,
           "RLIMIT_NOFILE": NOFILE, "RLIMIT_CORE": 0}
    ram = batas_ram_mb()
    if ram and not _node(cmd):          # V8 (node) memesan ruang alamat besar: RLIMIT_AS membuatnya gagal
        lim["RLIMIT_AS"] = ram * 1024 * 1024
    n = _proses_milik_sendiri()
    if n:
        lim["RLIMIT_NPROC"] = n + PROSES_TAMBAHAN
    return lim


def env_bersih(rumah):
    """Environment minimum; rahasia proses server tidak diwariskan ke child."""
    return {"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": "C.UTF-8", "HOME": str(rumah), "TMPDIR": str(rumah),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}


def _petunjuk(kode):
    return {-24: "dihentikan sistem: melebihi batas waktu CPU",
            -25: "dihentikan sistem: menulis berkas atau keluaran melebihi %d MB" % FSIZE_MB,
            -9: "dimatikan (kemungkinan kehabisan memori atau melebihi batas)"}.get(kode, "")


def jalankan_terkurung(cmd, cwd, timeout):
    """Jalankan perintah hanya di bubblewrap. kode 126 berarti sandbox tidak tersedia."""
    if not cmd:
        return 127, "perintah kosong"
    if os.sep not in cmd[0] and not shutil.which(cmd[0]):
        return 127, "perintah tidak ditemukan: %s" % cmd[0]

    try:
        dasar = [sys.executable or "python3", "-I", "-c", _PELUNCUR,
                 json.dumps(batas_rlimit(cmd, timeout))]
        dasar += argumen_isolasi(cmd, cwd)
    except (FileNotFoundError, OSError, ValueError) as e:
        return 126, "UJI DITOLAK: %s" % e

    # Node V8 memakai ruang alamat besar sehingga RLIMIT_AS tidak aman untuknya.
    # Batas ini mengendalikan heap JS, bukan seluruh RSS/native memory.
    perintah = list(cmd)
    if _node(perintah) and batas_ram_mb():
        perintah.insert(1, "--max-old-space-size=%d" % batas_ram_mb())

    rumah = tempfile.mkdtemp(prefix="uji_")
    try:
        keluar_path = Path(rumah) / ".keluaran"
        with open(keluar_path, "wb") as f:
            try:
                p = subprocess.Popen(dasar + perintah, stdin=subprocess.DEVNULL,
                                     stdout=f, stderr=subprocess.STDOUT,
                                     cwd=str(Path(cwd).resolve()), env=env_bersih(rumah),
                                     start_new_session=True)
            except FileNotFoundError as e:
                return 127, "perintah sandbox tidak ditemukan: %s" % e
            try:
                kode = p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except OSError:
                    pass
                p.wait()
                return None, "melebihi batas waktu %d detik" % timeout
        maks = _int_env("ASISTEN_UJI_KELUARAN_KB", 200) * 1000
        with open(keluar_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            ukuran = f.tell()
            f.seek(max(0, ukuran - maks))
            data = f.read()
        teks = data.decode("utf-8", "replace").strip()
        if ukuran > maks:
            teks = "...[keluaran dipotong, %d KB awal dibuang]\\n%s" % ((ukuran - maks) // 1000, teks)
        petunjuk = _petunjuk(kode)
        if not petunjuk and ukuran >= FSIZE_MB * 1_000_000:
            petunjuk = _petunjuk(-25)
        if petunjuk:
            teks = (teks + "\\n[" + petunjuk + "]").strip()
        return kode, teks
    finally:
        shutil.rmtree(rumah, ignore_errors=True)
