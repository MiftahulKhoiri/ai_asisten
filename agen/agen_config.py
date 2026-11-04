"""agen_config.py - konfigurasi agen: alamat llama-server, batas, dan nilai dari variabel lingkungan.

Modul lain MEMBACA nilai di sini lewat `cfg.NAMA` saat dipakai (bukan menyalin saat impor),
sehingga mengubah `agen.GERBANG = ...` atau `agen.CTX_MAKS = ...` langsung berlaku.
"""
import os
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent    # folder proyek (berisi asisten.py, src/, agen/)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src import tolls  # noqa: E402 - kumpulan tool (src/tolls.py memuat semua tool_*.py)

_AKHIRAN_API = re.compile(r"/(v\d+[a-z0-9]*(?:/openai)?)$")


def pecah_alamat(alamat):
    """Pisahkan alamat yang diketik pengguna menjadi (alamat dasar, awalan API).

    http://127.0.0.1:8080/v1              -> ("http://127.0.0.1:8080", "/v1")
    https://api.groq.com/openai/v1        -> ("https://api.groq.com/openai", "/v1")
    https://host/v1beta/openai            -> ("https://host", "/v1beta/openai")
    http://192.168.1.5:8080 (tanpa akhiran) -> ("http://192.168.1.5:8080", "/v1")
    """
    a = (alamat or "").strip().rstrip("/")
    m = _AKHIRAN_API.search(a)
    if m:
        return a[:m.start()], "/" + m.group(1)
    return a, "/v1"


LLAMA_URL, LLAMA_V1 = pecah_alamat(os.environ.get("LLAMA_BASE_URL", "http://127.0.0.1:8080"))


def nama_otomatis(url, jenis, utama=False):
    """Nama tampil bila pengguna tidak mengisi: 'Lokal' untuk koneksi utama llama-server, selain itu nama host."""
    if utama and jenis != "online":
        return "Lokal"
    m = re.match(r"^[a-z]+://([^/]+)", url or "")
    host = m.group(1) if m else (url or "server")
    return host[4:] if host.startswith("api.") else host


def sambungan(cid=None):
    """Data koneksi: {"id","nama","url","v1","key","jenis"}. None atau 'lokal' = koneksi utama."""
    if not cid or cid == KONEKSI_UTAMA:
        return {"id": KONEKSI_UTAMA, "url": LLAMA_URL, "v1": LLAMA_V1, "key": LLAMA_KEY, "jenis": LLAMA_JENIS,
                "nama": LLAMA_NAMA or nama_otomatis(LLAMA_URL, LLAMA_JENIS, True)}
    s = LLAMA_EXTRA.get(cid)
    if s is None:
        raise KeyError("koneksi tidak dikenal: %s" % cid)
    return dict(s, id=cid)


def pecah_model(kunci):
    """Kunci model -> (id koneksi, nama model di server). Tanpa awalan yang dikenal = koneksi utama."""
    if isinstance(kunci, str) and PEMISAH_MODEL in kunci:
        cid, _, nama = kunci.partition(PEMISAH_MODEL)
        if cid in LLAMA_EXTRA and nama:
            return cid, nama
    return KONEKSI_UTAMA, kunci


def kunci_model(cid, nama):
    return nama if not cid or cid == KONEKSI_UTAMA else cid + PEMISAH_MODEL + nama


def sambungan_model(kunci):
    """Kunci model -> (data koneksi, nama model asli untuk dikirim ke server itu)."""
    cid, nama = pecah_model(kunci)
    return sambungan(cid), nama


def adalah_anthropic(url):
    """True bila alamat dasar koneksi adalah API Anthropic (Claude)."""
    try:
        h = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return False
    return h == "api.anthropic.com"


def saring_body(body, s):
    """Buang parameter yang ditolak server tujuan. `s` = data koneksi.
    - penyedia online: tanpa chat_template_kwargs (khusus llama.cpp)
    - Anthropic (Claude): tanpa temperature/top_p dan response_format json_object, yang ditolak (HTTP 400)
      oleh jalur kompatibel OpenAI pada model Claude terbaru."""
    b = dict(body)
    if s["jenis"] == "online":
        b.pop("chat_template_kwargs", None)
    if adalah_anthropic(s["url"]):
        b.pop("temperature", None)
        b.pop("top_p", None)
        rf = b.get("response_format")
        if isinstance(rf, dict) and rf.get("type") in ("json_object", "text"):
            b.pop("response_format")
    return b


def jalur_daftar_model(path, s):
    """Jalur untuk mengambil daftar model. Anthropic membatasi 20 model per halaman, jadi minta lebih banyak."""
    if path == "/v1/models" and adalah_anthropic(s["url"]):
        return path + "?limit=1000"
    return path


def kepala_daftar_model(s):
    """Header tambahan untuk daftar model: Anthropic memakai x-api-key + anthropic-version di jalur aslinya."""
    if adalah_anthropic(s["url"]) and s["key"]:
        return {"x-api-key": s["key"], "anthropic-version": "2023-06-01"}
    return {}
# Kunci API (penyedia online, atau llama-server yang dinyalakan dengan --api-key). Dikirim hanya
# sebagai header Authorization; tidak pernah dicatat di log atau dikirim ke browser.
LLAMA_KEY = os.environ.get("LLAMA_API_KEY", "").strip()
# "llama" = llama-server (lokal/LAN, mengerti chat_template_kwargs), "online" = penyedia OpenAI-compatible.
LLAMA_JENIS = "llama"
LLAMA_NAMA = ""      # nama tampil koneksi utama ("" = otomatis)

# Koneksi TAMBAHAN (mis. penyedia online di samping llama-server lokal), selain koneksi utama di atas.
# Isi: id -> {"nama", "url", "v1", "key", "jenis"}. Model dari koneksi tambahan diberi awalan id-nya,
# "<id>::<nama model>", supaya satu daftar bisa memuat model dari banyak server. Model koneksi utama
# tetap memakai nama polos (jadi riwayat, pilihan tersimpan, dan konfigurasi lama tetap berlaku).
KONEKSI_UTAMA = "lokal"
PEMISAH_MODEL = "::"
LLAMA_EXTRA = {}
LOG_AKSI = ROOT / "aksi.log"


MAX_OUTPUT = tolls.MAX_OUTPUT  # karakter maksimum hasil tool yang dikirim balik ke model
MAX_STEPS = 8        # maksimum putaran tool per pesan

# Peringkasan riwayat: pesan lama diganti ringkasan pendek (riwayat asli tetap utuh).
RINGKAS_AMBANG = 0.7        # mulai meringkas saat riwayat > 70% MAX_HISTORY
RINGKAS_SISA_GILIRAN = 2    # giliran terakhir yang selalu dikirim utuh
RINGKAS_MAKS_KARAKTER = 1200

# Gerbang tool: model kecil sering asal memanggil tool bahkan untuk "halo".
# Di langkah pertama tiap pesan, tool hanya dikirim ke model kalau pesan pengguna
# tampak butuh akses sistem. Matikan dengan ASISTEN_GERBANG=0.
GERBANG = os.environ.get("ASISTEN_GERBANG", "1") != "0"


def _env_int(nama, bawaan, minimum=1):
    """Baca bilangan bulat dari variabel lingkungan; nilai rusak -> bawaan."""
    try:
        return max(minimum, int(os.environ.get(nama, bawaan)))
    except ValueError:
        return bawaan


# Ukuran konteks model (samakan dengan -c di llama-server): dipakai untuk indikator pemakaian
# dan untuk menentukan seberapa banyak riwayat yang dikirim (lihat max_history).
CTX_MAKS = _env_int("ASISTEN_CTX", 8192, 512)


# Batas token satu jawaban/putaran. Terlalu kecil memotong jawaban dan isi file panjang.
MAX_TOKENS = _env_int("ASISTEN_MAX_TOKENS", 1400, 128)


CATATAN_TERPOTONG = ('\n\n[Jawaban terpotong: batas token tercapai. Ketik "lanjut" untuk '
                     'meneruskan, atau naikkan ASISTEN_MAX_TOKENS.]')


PESAN_TOOL_TERPOTONG = ("ERROR: panggilan tool terpotong karena batas token jawaban tercapai. "
                        "Ulangi dengan isi lebih pendek. Untuk file panjang, tulis bertahap: "
                        "tulis_file lalu tulis_file berikutnya dengan tambah=true.")


KRITIK_MIN = 80   # draf lebih pendek dari ini (sapaan, jawaban singkat) tidak diperiksa ulang


__all__ = ['ROOT', 'LLAMA_URL', 'LLAMA_V1', 'pecah_alamat', 'LLAMA_NAMA', 'KONEKSI_UTAMA', 'PEMISAH_MODEL', 'LLAMA_EXTRA', 'nama_otomatis', 'sambungan', 'pecah_model', 'kunci_model', 'sambungan_model', 'adalah_anthropic', 'saring_body', 'jalur_daftar_model', 'kepala_daftar_model', 'LLAMA_KEY', 'LLAMA_JENIS', 'LOG_AKSI', 'MAX_OUTPUT', 'MAX_STEPS', 'RINGKAS_AMBANG', 'RINGKAS_SISA_GILIRAN', 'RINGKAS_MAKS_KARAKTER', 'GERBANG', '_env_int', 'CTX_MAKS', 'MAX_TOKENS', 'CATATAN_TERPOTONG', 'PESAN_TOOL_TERPOTONG', 'KRITIK_MIN']
