"""util.py - konstanta dan fungsi bantu bersama semua tool (path, izin, proses, format).

Tiga lapis perlindungan jalur file:
  _rahasia   file kredensial: TIDAK boleh dibaca model (baca/cari/arsip/salin).
  _boleh_tulis  batas folder yang boleh diubah (home, /tmp, ASISTEN_AKAR_TULIS).
  _sensitif  jalur yang bisa mengubah perilaku sistem atau asisten sendiri (.bashrc,
             unit systemd user, .git/hooks, kode asisten, kredensial). Mengubahnya
             SELALU minta izin, juga di mode AUTO (lihat _izin_jalur).
"""

import os
import signal
import subprocess
from pathlib import Path


MAX_OUTPUT = 2000   # karakter maksimum hasil tool yang dikirim balik ke model
CMD_TIMEOUT = 60    # detik, batas waktu satu perintah shell
HOME = Path.home()
APP_DIR = Path(__file__).resolve().parent.parent   # folder proyek (asisten.py, src/, web/)
TEMPAT_SAMPAH = HOME / ".sampah_asisten"
NOISE = {".git", "__pycache__", "node_modules", ".venv", "venv", ".cache",
         ".mypy_cache", ".pytest_cache"}
AKAR_TULIS = [HOME.resolve(), Path("/tmp").resolve()] + [
    Path(x).expanduser().resolve()
    for x in os.environ.get("ASISTEN_AKAR_TULIS", "").split(":") if x.strip()]


def _p(path):
    """Path relatif dihitung dari home (sama seperti shell tool)."""
    p = Path(str(path or "").strip() or ".").expanduser()
    return p if p.is_absolute() else HOME / p


def _resolve(p):
    try:
        return p.resolve()
    except OSError:
        return p


_NAMA_RAHASIA = {".token", ".git-credentials", ".netrc", "_netrc", ".pgpass", ".my.cnf",
                 ".pypirc", ".npmrc", ".bash_history", ".zsh_history", ".python_history",
                 ".mysql_history", ".psql_history", "ai_asisten.env"}
_CONTOH_ENV = (".example", ".sample", ".template", ".dist")
_BAGIAN_RAHASIA = ("/.aws/", "/.gnupg/", "/.kube/", "/.azure/", "/.docker/",
                   "/.config/gh/", "/.config/gcloud/", "/.config/rclone/")


def _rahasia_inti(r):
    """Inti: token asisten dan kunci pribadi ~/.ssh. `r` sudah di-resolve."""
    if r.name == ".token":
        return True
    return (".ssh" in r.parts and not r.name.endswith(".pub")
            and r.name not in ("known_hosts", "config"))


def _kredensial(r):
    """File kredensial lain: .env, .git-credentials, .netrc, ~/.aws, ~/.config/gh, dst."""
    n = r.name
    if n in _NAMA_RAHASIA or n == ".env":
        return True
    if n.startswith(".env.") and not n.endswith(_CONTOH_ENV):
        return True
    s = "/" + "/".join(x for x in r.parts if x != "/") + "/"
    return any(b in s for b in _BAGIAN_RAHASIA)


def _rahasia(p):
    """True bila file berisi rahasia yang tidak boleh dibaca model."""
    r = _resolve(p)
    return _rahasia_inti(r) or _kredensial(r)


_RC_HOME = {".bashrc", ".bash_profile", ".bash_login", ".bash_logout", ".profile",
            ".zshrc", ".zprofile", ".zshenv", ".zlogin", ".xprofile", ".xsession",
            ".pam_environment", ".inputrc", ".gitconfig"}
_DIR_SENSITIF = (".config/systemd", ".config/autostart", ".config/environment.d",
                 ".config/git", ".local/bin", "bin")


def _sensitif(p):
    """True bila mengubah `p` bisa mengubah perilaku sistem atau asisten sendiri.

    Dicek pada jalur asli dan jalur setelah link diikuti: skrip login (~/.bashrc, ...),
    unit systemd/autostart, ~/.local/bin, .git/hooks dan .git/config, kode asisten
    sendiri (kecuali riwayat/), serta semua file kredensial.
    """
    kandidat = {_resolve(p)}
    try:
        kandidat.add(p.parent.resolve() / p.name)
    except OSError:
        pass
    home = _resolve(HOME)
    app = _resolve(APP_DIR)
    for r in kandidat:
        if _rahasia_inti(r) or _kredensial(r):
            return True
        if r.parent == home and r.name in _RC_HOME:
            return True
        for d in _DIR_SENSITIF:
            akar = home / d
            if r == akar or akar in r.parents:
                return True
        bag = r.parts
        if any(x == ".git" and i + 1 < len(bag) and bag[i + 1] in ("hooks", "config")
               for i, x in enumerate(bag)):
            return True
        if r == app or app in r.parents:
            if r.relative_to(app).parts[:1] != ("riwayat",):
                return True
    return False


def _boleh_tulis(p, ikuti_link=True):
    try:
        r = p.resolve() if ikuti_link else p.parent.resolve() / p.name
    except OSError:
        return False
    if _rahasia_inti(r) or ".ssh" in r.parts:
        return False
    for akar in AKAR_TULIS:
        if r == akar:
            return False  # folder akar itu sendiri tidak boleh ditimpa/dihapus
        if akar in r.parents:
            return True
    return False


def _tolak_tulis(p):
    return ("DITOLAK: hanya boleh mengubah file di home, /tmp, atau folder dari "
            f"ASISTEN_AKAR_TULIS (dan bukan ~/.ssh): {p}")


def _izin(ctx, jenis, ringkas_, detail="", selalu=False):
    """None jika diizinkan; pesan DIBATALKAN jika pengguna menolak.

    Mode AUTO tidak berlaku (selalu bertanya) bila ctx.tercemar: obrolan sudah memakai tool
    web, jadi teks dari internet bisa saja berisi perintah terselubung (prompt injection).
    """
    tercemar = bool(getattr(ctx, "tercemar", False))
    if selalu or tercemar or not ctx.auto:
        if tercemar and ctx.auto and not selalu:
            ringkas_ += "   [setelah tool web: izin wajib walau AUTO]"
        if not ctx.konfirmasi(jenis, ringkas_, detail):
            return "DIBATALKAN: pengguna tidak mengizinkan tindakan ini."
    return None


def _izin_jalur(ctx, jenis, ringkas_, detail="", *jalur):
    """Seperti _izin, tetapi SELALU bertanya (juga di mode AUTO) bila ada jalur sensitif."""
    sens = any(_sensitif(j) for j in jalur)
    if sens:
        ringkas_ += "   [LOKASI SENSITIF]"
    return _izin(ctx, jenis, ringkas_, detail, selalu=sens)


def _run(cmd, timeout=15, cwd=None, env=None, shell=False):
    """Jalankan perintah. Kembalian (kode, output); kode None = melebihi waktu."""
    e = dict(os.environ)
    e.update(env or {})
    try:
        p = subprocess.Popen(
            cmd, shell=shell, executable="/bin/bash" if shell else None,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, text=True, errors="replace",
            cwd=cwd, env=e, start_new_session=True)
    except FileNotFoundError:
        return 127, f"perintah tidak ditemukan: {cmd[0] if isinstance(cmd, list) else cmd}"
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        return None, f"melebihi batas waktu {timeout} detik"
    return p.returncode, (out + err).strip()


def _fmt(n):
    n = float(n)
    for sat in ("B", "KB", "MB", "GB"):
        if n < 1024 or sat == "GB":
            return f"{n:.0f} {sat}" if sat == "B" else f"{n:.1f} {sat}"
        n /= 1024


def _ekor_teks(teks, batas=MAX_OUTPUT - 120):
    """Ambil bagian AKHIR teks (agar pemotongan umum tidak membuang baris terbaru)."""
    if len(teks) <= batas:
        return teks
    sisa = teks[-batas:]
    i = sisa.find("\n")
    if i != -1:
        sisa = sisa[i + 1:]
    return "...[bagian awal dipotong]\n" + sisa


def _baca(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _teks_biner(data):
    return b"\0" in data[:1024]


def _jalan_pohon(akar, dalam=None):
    """Telusuri folder, lewati folder noise. Menghasilkan (folder, nama_file[])."""
    for d, subs, files in os.walk(akar):
        subs[:] = [s for s in subs if s not in NOISE]
        yield d, subs, files


def _baca_teks_aman(p, batas=1_000_000):
    """(baris[], None) bila file teks biasa; (None, pesan_error) bila tidak boleh dibaca."""
    if not p.is_file():
        return None, f"ERROR: bukan file atau tidak ada: {p}"
    if _rahasia(p):
        return None, "DITOLAK: file ini berisi rahasia (token/kunci pribadi)."
    if p.stat().st_size > batas:
        return None, f"ERROR: file terlalu besar (> {_fmt(batas)}): {p}"
    data = p.read_bytes()
    if _teks_biner(data):
        return None, f"ERROR: file biner: {p}"
    return data.decode("utf-8", errors="replace").splitlines(), None
