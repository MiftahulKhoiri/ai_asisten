#!/usr/bin/env python3
"""tolls.py - pintu masuk kumpulan tool AI Asisten.

File ini hanya menggabungkan modul-modul di bawah. Kodenya ada di:

  pengaman.py     daftar perintah shell yang diblokir / wajib izin
  registri.py     dekorator @tool, skill, skema untuk model, eksekusi tool
  util.py         konstanta dan fungsi bantu bersama (path, izin, proses)
  tool_file.py    baca/tulis/ubah/pindah/hapus file, arsip ZIP
  tool_telusur.py tool hanya-baca: daftar/cari/info folder dan file
  tool_sistem.py  perintah shell, info sistem, proses, git
  tool_web.py     ambil_url, baca_halaman, berita, cari_web
  tool_lain.py    kalkulator dan waktu (tempat termudah untuk tool baru)

Cara menambah tool baru: tulis satu fungsi dengan dekorator @tool di salah satu
modul tool_*.py (atau modul baru, lalu tambahkan `from . import nama_modul` di bawah).
Skema untuk model dibuat otomatis, paket agen/ tidak perlu diubah.

    from .registri import tool

    @tool("nama_tool", "deskripsi singkat",
          {"param": ("string", "penjelasan"),
           "mode": ("string", "pilihan", ["a", "b"])},      # enum opsional
          wajib=["param"])
    def nama_tool(ctx, param, mode="a"):
        return "teks hasil"

Kebijakan izin (ctx datang dari asisten.py):
  tool hanya-baca  -> tanpa izin
  tool pengubah    -> _izin(...)             : tanya kecuali mode AUTO
  tool berisiko    -> _izin(..., selalu=True): tanya SELALU, juga di mode AUTO
  tool yang menyentuh jalur -> _izin_jalur(...): SELALU tanya bila jalurnya sensitif (util._sensitif)
  Setelah tool sumber luar (@tool(..., luar=True), mis. web) dipakai di sebuah obrolan, ctx.tercemar
  menjadi True dan _izin selalu bertanya walau mode AUTO (lindungan prompt injection).

Variabel lingkungan (opsional):
  ASISTEN_TOOLS=dasar        skill bawaan: hanya 4 tool inti (hemat konteks model)
                             (di web, skill dipilih saat memilih model; boleh lebih dari satu)
  ASISTEN_AKAR_TULIS=/a:/b   folder tambahan yang boleh ditulis/dihapus
  ASISTEN_CTX / ASISTEN_MAX_TOKENS   ukuran konteks dan batas token jawaban (lihat agen/agen_config.py)

Skill (bisa digabung): tanpa (chat saja), web (cari info/berita di internet),
dasar (4 tool inti), kompleks (semua tool), kritis (periksa & perbaiki jawaban).
Tool aktif = gabungan tool dari semua skill yang dipilih. "kritis" tidak punya tool;
ia mengubah cara model menjawab (ditangani paket agen/).
Hanya memakai library standar Python.
"""
# Nama-nama publik yang dipakai paket agen/, asisten.py, dan pengujian.
from .pengaman import BAHAYA, KONFIRMASI_SELALU, cek_perintah  # noqa: F401
from .registri import (  # noqa: F401
    MODE_SKILL, REGISTRY, SKILL_ALIAS, SKILL_IDS, eksekusi, mode_awal, mode_ctx,
    nama_tool_aktif, normal_skill, ringkas, skema, tool)
from .util import MAX_OUTPUT  # noqa: F401

# Mengimpor modul menjalankan dekorator @tool, jadi inilah yang mengisi REGISTRY.
from . import tool_file, tool_lain, tool_sistem, tool_telusur, tool_web  # noqa: F401,E402

# Urutan tool di skema memengaruhi prompt ke model, jadi dipertahankan seperti sebelum
# kode dipecah. Tool baru yang tidak tercantum di sini ditaruh di belakang.
_URUTAN = (
    "jalankan_perintah", "baca_file", "tulis_file", "daftar_folder", "pohon_folder",
    "info_file", "cari_file", "cari_teks", "baca_ekor", "info_sistem", "git_baca",
    "git_tulis", "edit_file", "buat_folder", "salin_pindah", "hapus", "ambil_url",
    "matikan_proses", "arsip", "hitung", "waktu_sekarang", "bandingkan_file",
    "ukuran_folder", "cek_sintaks", "baca_halaman", "berita", "cari_web",
)


def _urutkan_registri():
    isi = dict(REGISTRY)
    REGISTRY.clear()
    for nama in _URUTAN:
        if nama in isi:
            REGISTRY[nama] = isi.pop(nama)
    REGISTRY.update(isi)


_urutkan_registri()
