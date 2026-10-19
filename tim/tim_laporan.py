"""Laporan akhir: bagian fakta yang ditulis kode dari data nyata.
"""
import agen  # noqa: F401 - memastikan folder proyek ada di sys.path untuk `src.util`
from src.util import _ekor_teks

from . import tim_config as conf
from .tim_berkas import baca_proyek


def blok_fakta(status, spec, hasil_dir, meta, akhir):
    """Bagian pasti dari laporan, ditulis KODE dari data nyata (bukan model), supaya laporan
    tidak mengarang status, keluaran, atau hasil pemeriksaan."""
    ikon = {"lolos": "✔", "belum": "⚠", "batal": "⏹", "error": "✖"}.get(status, "•")
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
    baris.append("**Pemeriksaan otomatis**: %s · uji jalan %s" % (
        ("GAGAL - " + gagal[0][:200]) if gagal else "lolos", jalan))
    if akhir.get("harapan") is True:
        baris.append("**Harapan Perencana**: terpenuhi (%s)" % ", ".join(spec["harapan"]))
    elif akhir.get("harapan") is False:
        baris.append("**Harapan Perencana**: tidak terpenuhi (bisa keliru)")
    nilai = akhir.get("nilai")
    if nilai:
        baris.append("**Penilaian Pemeriksa** (pendapat model, bisa keliru): %s%s" % (
            "OK" if nilai["ok"] else "perlu perbaikan", (" - " + nilai["ringkas"]) if nilai["ringkas"] else ""))
    elif status == "lolos" and akhir.get("harapan"):
        baris.append("**Pemeriksa**: dilewati karena keluaran sesuai harapan")
    if akhir.get("pulih"):
        baris.append("**Dipulihkan**: hasil putaran %d (terbaik dari semua putaran)" % akhir["pulih"])
    return "\n".join(baris)
