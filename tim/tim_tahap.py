"""Tahap kerja model: Perencana, Pelaksana, Pemeriksa, Penjelas (generator event).
"""
import json
from pathlib import Path

from . import tim_config as conf
from .tim_berkas import aman_nama, baca_proyek, tulis_berkas, urai_berkas
from .tim_cek import rapikan_nilai
from .tim_config import Batal
from .tim_laporan import blok_fakta
from .tim_llm import ambil_json, tanya
from .tim_prompt import (
    SYSTEM_PELAKSANA,
    SYSTEM_PEMERIKSA,
    SYSTEM_PENJELAS,
    SYSTEM_PERENCANA,
    pesan_chat,
    pesan_ulang_json,
    prompt_jelas,
    prompt_periksa,
    prompt_rencana,
    prompt_tulis,
)
from .tim_spec import rapikan_spec, spec_ke_md


class Jejak:
    """Menyimpan prompt dan keluaran mentah tiap tahap model ke folder jejak/ (untuk diagnosis:
    kenapa Pelaksana salah format, kenapa Pemeriksa menolak, dst.)."""

    def __init__(self, folder):
        self.dir = Path(folder) / "jejak"
        self.n = 0

    def simpan(self, nama, prompt, keluaran):
        try:
            self.dir.mkdir(exist_ok=True)
            self.n += 1
            (self.dir / ("%02d-%s.txt" % (self.n, nama))).write_text(
                "### PROMPT (user)\n%s\n\n### KELUARAN MODEL\n%s\n" % (prompt, keluaran),
                encoding="utf-8")
        except OSError:
            pass


def event_tahap(kunci, model, putaran=None):
    return {"t": "tahap", "tahap": kunci, "peran": conf.PERAN[kunci], "model": model,
            "putaran": putaran}


def tahap_rencana(tugas, spec_lama, hasil_dir, folder, mp, ctx, pemuat, jejak):
    """Kembalian: (spec, pertanyaan). Bila Perencana butuh info: (None, pertanyaan)."""
    yield event_tahap("rencana", mp)
    yield from pemuat.pakai(mp)
    ada = [n for n, _ in baca_proyek(hasil_dir)] if spec_lama else []
    user = prompt_rencana(tugas, spec_lama, ada)
    pesan = pesan_chat(SYSTEM_PERENCANA, user)
    teks, _ = yield from tanya(mp, pesan, ctx, conf.TOKEN_RENCANA, 0.2, True)
    jejak.simpan("rencana", user, teks)
    raw = ambil_json(teks)
    if raw is None:
        pesan += pesan_ulang_json(teks)
        teks, _ = yield from tanya(mp, pesan, ctx, conf.TOKEN_RENCANA, 0.1, True)
        jejak.simpan("rencana-ulang", "(permintaan ulang JSON)", teks)
        raw = ambil_json(teks)
    if raw is None:
        raw = {"catatan": "Lembar tugas dibuat otomatis: Perencana tidak memberi JSON yang valid."}
    pertanyaan = " ".join(str(raw.get("tanya") or "").split())[:400]
    if pertanyaan and not raw.get("berkas"):
        return None, pertanyaan
    spec = rapikan_spec(raw, tugas)
    (folder / "tugas.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    (folder / "tugas.md").write_text(spec_ke_md(spec), encoding="utf-8")
    yield {"t": "rencana", "d": spec}
    return spec, ""


def tahap_tulis(spec, koreksi, hasil_dir, me, ctx, jejak, putaran):
    """Pelaksana menulis berkas. Kembalian: (nama_berkas_ditulis, daftar_masalah_format)."""
    user = prompt_tulis(spec, koreksi, baca_proyek(hasil_dir))
    pesan = pesan_chat(SYSTEM_PELAKSANA, user)
    teks, terpotong = yield from tanya(me, pesan, ctx, conf.TOKEN_TAHAP, 0.2, False)
    jejak.simpan("tulis-%d" % putaran, user, teks)
    ditulis, masalah = [], []
    daftar = urai_berkas(teks, [b["nama"] for b in spec["berkas"]])
    if not daftar:
        masalah.append("Keluaranmu tidak berisi blok berkas. Pakai format "
                       "=== FILE: nama === ... === END ===.")
    for nama, isi, lengkap in daftar:
        try:
            nama = aman_nama(nama)
        except ValueError as e:
            masalah.append(str(e))
            continue
        if not lengkap:
            masalah.append("%s: keluaran terpotong (batas token tercapai); tulis lebih ringkas "
                           "atau pecah menjadi berkas yang lebih kecil." % nama)
            continue
        if not isi.strip():
            masalah.append("%s: isi berkas kosong." % nama)
            continue
        baru = not (Path(hasil_dir) / nama).exists()
        if baru and len(baca_proyek(hasil_dir)) >= conf.MAKS_BERKAS_TOTAL:
            masalah.append("%s: melebihi batas %d berkas per proyek." % (nama, conf.MAKS_BERKAS_TOTAL))
            continue
        try:
            tulis_berkas(hasil_dir, nama, isi)
        except ValueError as e:
            masalah.append(str(e))
            continue
        ditulis.append(nama)
        yield {"t": "berkas", "nama": nama, "baru": baru, "isi": isi[:20000],
               "dipotong": len(isi) > 20000}
    if terpotong and not any("terpotong" in m for m in masalah):
        masalah.append("Keluaran mencapai batas token; pastikan semua berkas ditulis lengkap.")
    return ditulis, masalah


def tahap_periksa(spec, cek_baris, hasil_dir, mc, ctx, keluaran, jejak, putaran):
    berkas = baca_proyek(hasil_dir)
    user = prompt_periksa(spec, cek_baris, berkas)
    pesan = pesan_chat(SYSTEM_PEMERIKSA, user)
    teks, _ = yield from tanya(mc, pesan, ctx, conf.TOKEN_PERIKSA, 0.1, True)
    jejak.simpan("periksa-%d" % putaran, user, teks)
    d = ambil_json(teks)
    if d is None:
        pesan += pesan_ulang_json(teks)
        teks, _ = yield from tanya(mc, pesan, ctx, conf.TOKEN_PERIKSA, 0.1, True)
        jejak.simpan("periksa-%d-ulang" % putaran, "(permintaan ulang JSON)", teks)
        d = ambil_json(teks)
    if d is None:
        return {"ok": True, "masalah": [], "perbaikan": "", "dilihat": "",
                "ringkas": "Pemeriksa tidak memberi penilaian yang terbaca; pemeriksaan "
                           "otomatis lolos sehingga hasil diterima."}
    sumber = None
    if keluaran is not None:      # kutipan Pemeriksa bisa dicocokkan dengan keluaran dan kode nyata
        sumber = keluaran + "\n" + "\n".join(isi for _, isi in berkas)
    return rapikan_nilai(d, sumber)


def tahap_jelaskan(status, spec, hasil_dir, meta, akhir, mp, ctx, pemuat, jejak):
    """Penjelas menulis prosa singkat tentang programnya; fakta status ditambahkan oleh sistem."""
    yield event_tahap("jelaskan", mp)
    prosa = ""
    try:
        yield from pemuat.pakai(mp)
        user = prompt_jelas(spec, baca_proyek(hasil_dir))
        pesan = pesan_chat(SYSTEM_PENJELAS, user)
        prosa, _ = yield from tanya(mp, pesan, ctx, conf.TOKEN_JELAS, 0.3, False, keluar="token")
        jejak.simpan("jelaskan", user, prosa)
        prosa = prosa.strip()
    except Batal:
        raise
    except Exception as e:  # noqa: BLE001 - penjelasan gagal bukan kegagalan proses
        yield {"t": "ringkas", "d": "Penjelasan otomatis gagal (%s); memakai ringkasan biasa." % e}
    if not prosa:
        prosa = spec["ringkasan"]
        yield {"t": "token", "d": prosa}
    fakta = "\n\n" + blok_fakta(status, spec, hasil_dir, meta, akhir)
    yield {"t": "token", "d": fakta}
    return prosa + fakta
