"""agen_config.py - konfigurasi agen: alamat llama-server, batas, dan nilai dari variabel lingkungan.

Modul lain MEMBACA nilai di sini lewat `cfg.NAMA` saat dipakai (bukan menyalin saat impor),
sehingga mengubah `agen.GERBANG = ...` atau `agen.CTX_MAKS = ...` langsung berlaku.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent    # folder proyek (berisi asisten.py, src/, agen/)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src import tolls  # noqa: E402 - kumpulan tool (src/tolls.py memuat semua tool_*.py)

LLAMA_URL = os.environ.get("LLAMA_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
if LLAMA_URL.endswith("/v1"):
    LLAMA_URL = LLAMA_URL[:-3]
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


__all__ = ['ROOT', 'LLAMA_URL', 'LOG_AKSI', 'MAX_OUTPUT', 'MAX_STEPS', 'RINGKAS_AMBANG', 'RINGKAS_SISA_GILIRAN', 'RINGKAS_MAKS_KARAKTER', 'GERBANG', '_env_int', 'CTX_MAKS', 'MAX_TOKENS', 'CATATAN_TERPOTONG', 'PESAN_TOOL_TERPOTONG', 'KRITIK_MIN']
