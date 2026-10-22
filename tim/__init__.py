"""tim/ - Agent tim model: beberapa model lokal bekerja bergiliran.

Dipakai oleh asisten.py (halaman web web/agent.html). Hanya library standar Python.

Peran (2 model: Perencana = Pemeriksa = model 1, Pelaksana = model 2;
       3 model: tiap peran punya model sendiri):

  Perencana  menerima perintah pengguna, menyusun "lembar tugas" (tugas.json + tugas.md)
             dan, di akhir, menjelaskan hasilnya kepada pengguna.
  Pelaksana  membaca lembar tugas lalu HANYA menulis program ke folder hasil/. Ia tidak
             menjalankan apa pun.
  Pemeriksa  menerima hasil Pelaksana langsung, MENJALANKAN programnya (berkas ada, sintaks
             Python/JSON/JS/Bash, uji jalan bila diizinkan di pengaturan), lalu MENENTUKAN benar
             atau salah: dinyatakan jadi (selesai) atau memberi koreksi yang dikirim balik ke
             Pelaksana. Batas putaran ditentukan pengguna.

Tidak ada jalan pintas dari kode yang melewati Pemeriksa: hasil menjalankan program dan
"harapan" Perencana hanya menjadi fakta bagi Pemeriksa. Pengecualian yang tercatat di
tim_tahap.tahap_periksa: tidak ada berkas sama sekali, atau jawaban Pemeriksa tidak terbaca.
Laporan akhir memberi peringatan bila Pemeriksa menyatakan jadi padahal program gagal.

Memori: model dimuat satu per satu lewat llama-server mode router (/models/load dan
/models/unload). Dengan "bongkar tiap tahap", model dibongkar begitu tahapnya selesai,
kecuali tahap berikutnya memakai model yang sama.

Folder kerja (ASISTEN_AGENT_DIR, bawaan ~/agent_kerja/<id>/):
  tugas.json, tugas.md   lembar tugas dari Perencana
  hasil/                 program buatan Pelaksana
  koreksi_N.md           masukan untuk putaran berikutnya
  laporan.md, run.json   penjelasan akhir dan ringkasan proses

Variabel lingkungan (opsional):
  ASISTEN_AGENT_DIR      folder kerja agent
  ASISTEN_AGENT_TOKENS   batas token tulis kode per tahap (bawaan 3000)
  ASISTEN_AGENT_UJI_DTK  batas waktu uji jalan program (bawaan 20 detik)

Susunan paket (tiap berkas satu tanggung jawab; lihat docstring masing-masing):
  tim_config   konstanta, batas, folder kerja, validasi pengaturan dari web
  tim_prompt   prompt tiap peran dan penyusun isi prompt
  tim_model    muat/bongkar model di llama-server
  tim_llm      aliran jawaban model dan pengambilan JSON
  tim_berkas   nama berkas aman, tulis/baca proyek, penguraian keluaran Pelaksana
  tim_spec     lembar tugas dari Perencana
  tim_cek      alat Pemeriksa: cek berkas/sintaks, uji jalan, perapian penilaian
  tim_laporan  bagian fakta laporan akhir
  tim_tahap    tahap kerja model: Pelaksana menulis, Pemeriksa menjalankan + menentukan
  tim_riwayat  riwayat proses: daftar, baca, hapus
  tim_alur     orkestrator dan pintu masuk jalankan()

Pemakaian dari luar cukup `import tim` lalu `tim.jalankan(...)`, `tim.daftar_run()`, dst.
Konstanta konfigurasi (tim.KERJA, tim.TOKEN_TAHAP, ...) dibaca langsung dari tim_config.
"""
from . import tim_config

from .tim_config import (
    Batal,
    id_valid,
    siapkan_cfg,
)
from .tim_prompt import (
    SYSTEM_PELAKSANA,
    SYSTEM_PEMERIKSA,
    SYSTEM_PENJELAS,
    SYSTEM_PERENCANA,
    anggaran_prompt,
    blok_berkas,
    pesan_chat,
    pesan_minta_masalah,
    pesan_ulang_json,
    prompt_jelas,
    prompt_periksa,
    prompt_rencana,
    prompt_tulis,
)
from .tim_model import (
    DIMUAT,
    Pemuat,
    bongkar,
    bongkar_sisa,
    muat,
    status_model,
)
from .tim_llm import (
    ambil_json,
    tanya,
)
from .tim_berkas import (
    aman_nama,
    baca_json,
    baca_proyek,
    pulihkan,
    masukkan_bahan,
    salin_proyek,
    tulis_berkas,
    urai_berkas,
)
from .tim_spec import (
    rapikan_spec,
    spec_ke_md,
    spec_model,
)
from .tim_cek import (
    cek_jalan,
    cek_statis,
    cocok_keluaran,
    nilai_cadangan,
    perintah_uji,
    rapikan_nilai,
    teks_koreksi,
)
from .tim_laporan import (
    blok_fakta,
)
from .tim_tahap import (
    Jejak,
    event_tahap,
    pemeriksa_menjalankan,
    tahap_jelaskan,
    tahap_periksa,
    tahap_rencana,
    tahap_tulis,
)
from .tim_riwayat import (
    AKTIF_RUN,
    baca_run,
    daftar_run,
    hapus_run,
    hapus_semua_run,
    tulis_meta,
)
from .tim_alur import (
    jalankan,
    kerjakan,
)


def __getattr__(nama):
    """Konstanta konfigurasi dibaca langsung dari tim_config (nilainya bisa berubah, mis. saat tes)."""
    try:
        return getattr(tim_config, nama)
    except AttributeError:
        raise AttributeError("module 'tim' has no attribute %r" % nama) from None
