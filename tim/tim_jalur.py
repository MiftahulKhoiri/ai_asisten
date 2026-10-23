"""tim_jalur.py - jalur kerja tim: urutan tahap yang berbeda menurut jenis tugas.

  buat      Perencana -> [Pelaksana -> Pemeriksa]* -> Penjelas            (program baru / pengembangan)
  perbaiki  Diagnosa -> Perencana -> [Pelaksana -> Pemeriksa]* -> Penjelas (perbaiki kode yang sudah ada)
  cari_bug  Diagnosa -> Penjelas                                          (hanya mencari bug, tanpa mengubah)

Diagnosa adalah Pemeriksa yang memeriksa kode yang SUDAH ADA lebih dulu. Hasilnya menentukan
jalannya proses: tidak ada bug -> berhenti dengan laporan; ada bug -> Perencana menyusun lembar
tugas perbaikan dan temuan itu menjadi koreksi pertama untuk Pelaksana.

Pemilihan jalur sengaja memakai aturan kata kunci (bukan model): cepat, tanpa memuat model, dan
hasilnya bisa diramalkan. Pengguna selalu bisa memilih jalur sendiri di halaman Agent.
"""
import re

from . import tim_config as conf

JALUR = {
    "buat": {"label": "Buat / kembangkan", "urut": ["rencana", "tulis", "periksa", "jelaskan"]},
    "perbaiki": {"label": "Perbaiki kode",
                 "urut": ["diagnosa", "rencana", "tulis", "periksa", "jelaskan"]},
    "cari_bug": {"label": "Cari bug", "urut": ["diagnosa", "jelaskan"]},
}

_AKSI_PERBAIKI = re.compile(
    r"\b(perbaiki|perbaikan|betulkan|betulin|benerin|benahi|fix|debug|atasi|tambal|patch|"
    r"hilangkan error|selesaikan (masalah|bug|error))\b")
_CARI = re.compile(
    r"\b(cari|carikan|temukan|deteksi|periksa|cek|audit|review|tinjau|analisis|analisa|telusuri|"
    r"scan|inspeksi)\w*\b[^.\n]{0,40}\b(bug|kesalahan|error|eror|masalah|celah|kerentanan|kelemahan)\w*")
_TANYA_BUG = re.compile(
    r"\b(ada bug|adakah bug|bug apa|apa (saja )?(bug|kesalahan|masalah)\w*|apa yang salah)\b|"
    r"\b(kenapa|mengapa|kok)\b[^.\n]{0,40}\b(error|eror|gagal|salah|bug|crash|rusak|macet)\b")
_BANGUN = re.compile(r"\b(tambah|tambahkan|buat|buatkan|bikin|bikinin|kembangkan|ubah|ganti|"
                     r"implementasi\w*|refactor|rapikan)\b")
_GEJALA = re.compile(
    r"\b(bug|error|eror|galat|crash|rusak|gagal|exception|traceback|macet|hang|salah|"
    r"(tidak|gak|ga|nggak|enggak) (jalan|bisa|berfungsi|muncul|keluar))\b")


def pilih_jalur(tugas, pilihan="otomatis", ada_berkas=False):
    """Jalur untuk satu tugas. Kembalian: (jalur, alasan).

    `pilihan`: "buat" / "perbaiki" / "cari_bug" dari pengguna, atau "otomatis". Jalur perbaiki
    dan cari_bug butuh kode yang sudah ada (`ada_berkas`): tanpa itu otomatis jatuh ke "buat"
    (pilihan eksplisit tetap dihormati; pemeriksaan berkas ada di pemanggil)."""
    if pilihan in JALUR:
        return pilihan, "dipilih pengguna"
    t = " ".join(str(tugas or "").lower().split())
    if not ada_berkas:
        return "buat", "tidak ada berkas yang sudah ada, jadi membuat dari awal"
    if _AKSI_PERBAIKI.search(t):
        return "perbaiki", "tugas meminta perbaikan dan sudah ada berkas"
    if _CARI.search(t) or _TANYA_BUG.search(t):
        return "cari_bug", "tugas meminta mencari masalah/bug di kode yang sudah ada"
    if _BANGUN.search(t):
        return "buat", "tugas meminta menambah atau mengubah"
    if _GEJALA.search(t):
        return "perbaiki", "tugas menyebut gejala masalah pada kode yang sudah ada"
    return "buat", "tidak ada tanda perbaikan atau pencarian bug"


def info_jalur(jalur, alasan=""):
    """Isi event "jalur" untuk halaman web: label dan urutan tahap."""
    j = JALUR[jalur]
    return {"t": "jalur", "jalur": jalur, "label": j["label"], "alasan": alasan,
            "urut": [{"kunci": k, "peran": conf.PERAN[k]} for k in j["urut"]]}


__all__ = ["JALUR", "pilih_jalur", "info_jalur"]
