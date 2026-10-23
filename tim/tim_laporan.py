"""Laporan akhir: bagian fakta yang ditulis kode dari data nyata.
"""
import agen  # noqa: F401 - memastikan folder proyek ada di sys.path untuk `src.util`
from src.util import _ekor_teks

from . import tim_config as conf
from .tim_berkas import baca_proyek


def blok_fakta_bug(status, diag, meta):
    """Bagian pasti dari laporan diagnosa (jalur cari_bug / perbaiki tanpa temuan), ditulis KODE
    dari hasil Pemeriksa yang sebenarnya, bukan oleh model."""
    nilai = diag["nilai"]
    bug = nilai.get("masalah") or []
    baris = ["%s **Status**: %s" % ("⚠" if bug else "✔", conf.STATUS_TEKS.get(status, status))]
    if bug:
        baris.append("**Temuan Pemeriksa** (%d):\n%s" % (
            len(bug), "\n".join("%d. %s" % (i, m) for i, m in enumerate(bug, 1))))
        if nilai.get("dilihat"):
            baris.append("**Bukti**: `%s`" % nilai["dilihat"])
        if nilai.get("perbaikan"):
            baris.append("**Saran perbaikan**: " + nilai["perbaikan"])
    else:
        baris.append("**Temuan**: tidak ada bug nyata yang bisa ditunjuk%s. Ini bukan jaminan bebas bug."
                     % ((" - " + nilai["ringkas"]) if nilai.get("ringkas") else ""))
    gagal = [b for b in diag.get("baris") or [] if b.startswith("GAGAL")]
    baris.append("**Dijalankan Pemeriksa**: %s · uji jalan %s" % (
        ("GAGAL - " + gagal[0][:200]) if gagal else "sintaks berkas yang diperiksa baik",
        diag.get("jalan", "dilewati")))
    if diag.get("dilihat", 0) < diag.get("total", 0):
        baris.append("**Cakupan**: isi %d dari %d berkas dibaca Pemeriksa (konteks model terbatas; sisanya "
                     "hanya disebut namanya). Sebut nama berkas di tugas untuk memfokuskan pemeriksaan."
                     % (diag["dilihat"], diag["total"]))
    if diag.get("dipakai_ulang"):
        baris.append("**Catatan**: memakai diagnosa dari proses sebelumnya (isi proyek tidak berubah).")
    if bug and status == "analisis":
        baris.append("**Langkah berikut**: untuk memperbaiki temuan ini pilih jalur **Perbaiki** lalu kirim; "
                     "proyek ini otomatis dilanjutkan dan diagnosa ini dipakai ulang tanpa memeriksa lagi.")
    return "\n".join(baris)


def blok_fakta(status, spec, hasil_dir, meta, akhir):
    """Bagian pasti dari laporan, ditulis KODE dari data nyata (bukan model), supaya laporan
    tidak mengarang status, keluaran, atau hasil pemeriksaan."""
    ikon = {"lolos": "✔", "belum": "⚠", "batal": "⏹", "error": "✖", "analisis": "🔎"}.get(status, "•")
    baris = ["%s **Status**: %s (putaran %d dari maks %d)"
             % (ikon, conf.STATUS_TEKS.get(status, status), meta["putaran"], meta["maks"])]
    berkas = baca_proyek(hasil_dir)
    baris.append("**Berkas**: " + (", ".join(
        "`%s` (%d baris)" % (n, len(i.splitlines())) for n, i in berkas) or "-"))
    if spec["jalankan"]:
        baris.append("**Cara menjalankan**: `%s`" % " ".join(spec["jalankan"]))
    keluaran = akhir.get("keluaran")
    if keluaran is not None:
        baris.append("**Keluaran uji jalan**:\n```\n%s\n```" % _ekor_teks(keluaran.strip() or "(kosong)", 600))
    cek = akhir.get("cek") or []
    gagal = [b for b in cek if b.startswith("GAGAL")]
    jalan = akhir.get("jalan", "dilewati")
    baris.append("**Dijalankan Pemeriksa**: %s · uji jalan %s" % (
        ("GAGAL - " + gagal[0][:200]) if gagal else "tanpa kesalahan", jalan))
    if akhir.get("harapan") is True:
        baris.append("**Harapan Perencana**: terpenuhi (%s)" % ", ".join(spec["harapan"]))
    elif akhir.get("harapan") is False:
        baris.append("**Harapan Perencana**: tidak terpenuhi (bisa keliru)")
    nilai = akhir.get("nilai")
    if nilai:
        baris.append("**Keputusan Pemeriksa**: %s%s" % (
            "jadi" if nilai["ok"] else "perlu perbaikan",
            (" - " + nilai["ringkas"]) if nilai["ringkas"] else ""))
        if nilai["ok"] and gagal:    # keputusan tetap milik Pemeriksa, tapi pengguna harus tahu
            baris.append("⚠ **Perhatian**: Pemeriksa menyatakan jadi, padahal hasil menjalankan "
                         "program mencatat GAGAL. Periksa sendiri sebelum dipakai.")
    if akhir.get("pulih"):
        baris.append("**Dipulihkan**: hasil putaran %d (terbaik dari semua putaran)" % akhir["pulih"])
    return "\n".join(baris)
