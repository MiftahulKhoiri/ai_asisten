"""Kotak uji: menjalankan program buatan model dengan pembatasan.

Program hasil model bukan kode tepercaya. Pemeriksa menjalankannya dengan:
  - environment BERSIH (tanpa LLAMA_API_KEY, token, atau variabel rahasia lain dari proses server);
    HOME dan TMPDIR menunjuk ke folder sementara yang dihapus sesudahnya;
  - batas memori (RLIMIT_AS), waktu CPU, ukuran berkas yang ditulis, jumlah berkas terbuka, dan
    jumlah proses baru (menahan fork bomb);
  - jaringan diputus (namespace jaringan kosong lewat `unshare -rn`) bila sistemnya mendukung;
  - keluaran ditulis ke berkas sementara dan hanya ekornya yang dibaca, jadi program yang
    mencetak tanpa henti tidak menghabiskan RAM server (penting di perangkat RAM 1 GB).

Pembatasan dipasang oleh peluncur kecil (interpreter baru yang memasang batas lalu `exec`), bukan
`preexec_fn`, karena server ini memakai banyak thread dan `preexec_fn` tidak aman di sana.

Ini pengurungan dasar, bukan sandbox penuh. Yang tidak dicegah: membaca berkas milik pengguna yang
sama lewat jalur absolut (mis. ~/.token). Untuk itu tetap nyalakan "uji jalan" hanya untuk tugas
yang kamu percaya.

Pengaturan (variabel lingkungan, semuanya opsional):
  ASISTEN_UJI_RAM_MB     batas memori program uji, MB (bawaan 512; 0 = tanpa batas)
  ASISTEN_UJI_JARINGAN   "putus" (bawaan) atau "boleh"
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


def jaringan_bisa_diputus():
    """True bila `unshare -rn` berfungsi di sistem ini (hasilnya di-cache)."""
    global _JARINGAN_BISA
    if _JARINGAN_BISA is None:
        ok = False
        if shutil.which("unshare"):
            try:
                ok = subprocess.run(["unshare", "-rn", "true"], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=5).returncode == 0
            except (OSError, subprocess.SubprocessError):
                ok = False
        _JARINGAN_BISA = ok
    return _JARINGAN_BISA


def _putus_jaringan():
    return os.environ.get("ASISTEN_UJI_JARINGAN", "putus").strip().lower() != "boleh" \
        and jaringan_bisa_diputus()


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
    """Environment minimal untuk program uji. Tidak mewarisi apa pun dari proses server selain PATH."""
    return {"PATH": os.environ.get("PATH") or "/usr/local/bin:/usr/bin:/bin",
            "LANG": "C.UTF-8", "HOME": str(rumah), "TMPDIR": str(rumah),
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}


def ringkas_isolasi(cmd):
    """Satu kalimat tentang pengurungan yang berlaku, untuk dicatat di hasil pemeriksaan."""
    bagian = ["environment bersih"]
    ram = batas_ram_mb()
    bagian.append("RAM maks %d MB" % ram if ram and not _node(cmd)
                  else ("RAM tanpa batas (node)" if ram else "RAM tanpa batas"))
    bagian.append("jaringan diputus" if _putus_jaringan() else
                  "jaringan TIDAK diputus (%s)" % (
                      "diatur boleh" if os.environ.get("ASISTEN_UJI_JARINGAN", "").strip().lower() == "boleh"
                      else "unshare tidak tersedia"))
    return ", ".join(bagian)


def _petunjuk(kode):
    return {-24: "dihentikan sistem: melebihi batas waktu CPU",
            -25: "dihentikan sistem: menulis berkas atau keluaran melebihi %d MB" % FSIZE_MB,
            -9: "dimatikan (kemungkinan kehabisan memori atau melebihi batas)"}.get(kode, "")


def jalankan_terkurung(cmd, cwd, timeout):
    """Jalankan `cmd` (list) terkurung. Kembalian (kode, keluaran) seperti src.util._run:
    kode None = melebihi batas waktu; 127 = perintah tidak ada."""
    if not cmd:
        return 127, "perintah kosong"
    if os.sep not in cmd[0] and not shutil.which(cmd[0]):
        return 127, "perintah tidak ditemukan: %s" % cmd[0]
    rumah = tempfile.mkdtemp(prefix="uji_")
    try:
        keluar_path = Path(rumah) / ".keluaran"
        dasar = [sys.executable or "python3", "-I", "-c", _PELUNCUR,
                 json.dumps(batas_rlimit(cmd, timeout))]
        if _putus_jaringan():
            dasar += ["unshare", "-rn", "--"]
        with open(keluar_path, "wb") as f:
            try:
                p = subprocess.Popen(dasar + list(cmd), stdin=subprocess.DEVNULL, stdout=f,
                                     stderr=subprocess.STDOUT, cwd=cwd, env=env_bersih(rumah),
                                     start_new_session=True)
            except FileNotFoundError:
                return 127, "perintah tidak ditemukan: %s" % cmd[0]
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
            teks = "...[keluaran dipotong, %d KB awal dibuang]\n%s" % ((ukuran - maks) // 1000, teks)
        petunjuk = _petunjuk(kode)
        if not petunjuk and ukuran >= FSIZE_MB * 1_000_000:
            # Python mengabaikan SIGXFSZ: program hanya melihat OSError saat menulis, lalu berhenti
            petunjuk = _petunjuk(-25)
        if petunjuk:
            teks = (teks + "\n[" + petunjuk + "]").strip()
        return kode, teks
    finally:
        shutil.rmtree(rumah, ignore_errors=True)
