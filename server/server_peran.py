"""server_peran.py - prompt pilihan pengguna untuk tiap peran Agent (tombol "+ prompt" di halaman Agent).

Sama seperti prompt chat: SATU PROMPT = SATU BERKAS JSON (format ai-asisten-prompt), tetapi disimpan
terpisah per peran supaya daftar tiap peran berisi prompt yang memang untuk perannya:

  prompt/agent/perencana/*.json     prompt/agent/pelaksana/*.json
  prompt/agent/pemeriksa/*.json     prompt/agent/penjelas/*.json

(folder induknya mengikuti ASISTEN_PROMPT_DIR). Berkas dari teman cukup disalin ke folder peran yang
cocok, atau diimpor lewat tombol "Impor" di panel peran itu. Aturan nama, batas, ekspor, dan impor
sama dengan prompt chat (lihat server_prompt).

Cara prompt dipakai, dipilih per peran:
  tambah  prompt bawaan peran TETAP dipakai; prompt yang dicentang ditambahkan di bawahnya (bawaan)
  ganti   prompt yang dicentang menggantikan perilaku bawaan peran

Dalam kedua cara, FORMAT KELUARAN peran (JSON Perencana/Pemeriksa, blok === FILE === Pelaksana) selalu
ikut, karena program membaca keluaran model dengan format itu (lihat tim_prompt.rakit_sistem).
Tidak ada yang dicentang = prompt bawaan peran apa adanya.
"""
import tim
from . import server_config as conf
from . import server_prompt as prm

NAMA_FOLDER = "agent"


def peran_valid(peran):
    return peran in tim.PERAN_AGENT


def _periksa_peran(peran):
    if not peran_valid(peran):
        raise ValueError("Peran tidak dikenal: %s" % (str(peran)[:30],))
    return peran


def folder_peran(peran):
    """Folder prompt satu peran (dibuat saat prompt pertama disimpan)."""
    return conf.PROMPT_DIR / NAMA_FOLDER / _periksa_peran(peran)


def bawaan_peran(peran):
    """Prompt bawaan peran sebagai butir daftar: hanya bagian perilaku (format keluaran tidak ikut
    karena selalu ditambahkan program). Tidak bisa diubah atau dihapus; bisa disalin untuk diubah."""
    label = tim.PERAN_LABEL[_periksa_peran(peran)]
    return {"id": conf.PROMPT_BAWAAN, "nama": "Bawaan (%s)" % label, "isi": tim.perilaku_peran(peran),
            "catatan": "Perilaku bawaan. Format keluaran yang dibaca program selalu ikut.", "bawaan": True}


def _ruang(peran):
    return prm.Ruang(folder_peran(peran), bawaan_peran(peran)["nama"])


# ---------------------------------------------------------------- API per peran
def daftar_prompt_peran(peran):
    """Bawaan peran lebih dulu, lalu berkas di folder peran urut nama."""
    return prm.ruang_daftar(_ruang(peran), bawaan_peran(peran))


def abaikan_prompt_peran(peran):
    """[{berkas, alasan}] berkas di folder peran yang dilewati karena tidak valid."""
    return prm.ruang_abaikan(_ruang(peran))


def tambah_prompt_peran(peran, nama, isi, catatan=""):
    return prm.ruang_tambah(_ruang(peran), nama, isi, catatan)


def ubah_prompt_peran(peran, pid, nama, isi, catatan=None):
    return prm.ruang_ubah(_ruang(peran), pid, nama, isi, catatan)


def hapus_prompt_peran(peran, pid):
    return prm.ruang_hapus(_ruang(peran), pid)


def ekspor_prompt_peran(peran, pid):
    return prm.ruang_ekspor(_ruang(peran), pid)


def impor_prompt_peran(peran, teks):
    return prm.ruang_impor(_ruang(peran), teks)


# ---------------------------------------------------------------- pemakaian di proses Agent
def rakit_prompt_peran(pilihan):
    """Ubah pilihan dari web menjadi isi prompt per peran untuk cfg Agent.

    `pilihan`: {peran: {"ids": [id prompt], "mode": "tambah"|"ganti"}} atau None.
    Kembalian: {peran: {"mode", "teks", "nama": [nama prompt]}}; peran tanpa prompt terpilih tidak
    dimasukkan (memakai prompt bawaan). Id yang sudah dihapus dilewati. ValueError bila bentuknya salah
    atau gabungan isi satu peran melebihi tim.MAKS_TEKS_PERAN."""
    if pilihan is None:
        return {}
    if not isinstance(pilihan, dict):
        raise ValueError("Pilihan prompt peran tidak valid")
    hasil = {}
    for peran, x in pilihan.items():
        if not peran_valid(peran):
            raise ValueError("Peran tidak dikenal: %s" % (str(peran)[:30],))
        if not isinstance(x, dict) or not isinstance(x.get("ids", []), list) \
                or not all(isinstance(i, str) for i in x.get("ids", [])):
            raise ValueError("Pilihan prompt peran %s tidak valid" % peran)
        ids = set(x.get("ids", []))
        if not ids:
            continue
        ada = [p for p in daftar_prompt_peran(peran) if not p.get("bawaan") and p["id"] in ids]
        if not ada:
            continue
        teks = "\n\n".join(p["isi"] for p in ada)
        if len(teks) > tim.MAKS_TEKS_PERAN:
            raise ValueError("Prompt peran %s terlalu panjang (%d karakter, maks %d). Kurangi yang dicentang."
                             % (tim.PERAN_LABEL[peran], len(teks), tim.MAKS_TEKS_PERAN))
        hasil[peran] = {"mode": "ganti" if x.get("mode") == "ganti" else "tambah",
                        "teks": teks, "nama": [p["nama"] for p in ada]}
    return hasil


__all__ = ["peran_valid", "folder_peran", "bawaan_peran", "daftar_prompt_peran", "abaikan_prompt_peran",
           "tambah_prompt_peran", "ubah_prompt_peran", "hapus_prompt_peran", "ekspor_prompt_peran",
           "impor_prompt_peran", "rakit_prompt_peran"]
