"""Lembar tugas (spec) dari Perencana: validasi, perintah uji, harapan keluaran.
"""
import re

from . import tim_config as conf
from .tim_berkas import aman_nama


def _daftar_teks(v, maks, panjang=300):
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    hasil = []
    for x in v:
        s = " ".join(str(x).split())[:panjang]
        if s:
            hasil.append(s)
        if len(hasil) >= maks:
            break
    return hasil


def _rapikan_harapan(v):
    """Teks pendek yang harus muncul di keluaran program (oracle dari Perencana)."""
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    hasil = []
    for x in v:
        t = " ".join(str(x).split())[:60]
        if t and t not in hasil:
            hasil.append(t)
        if len(hasil) >= 5:
            break
    return hasil


def spec_model(spec):
    """Lembar tugas untuk Pelaksana/Pemeriksa. 'langkah' dibuang: langkah buatan model kecil
    sering keliru (algoritma/library salah) dan menyesatkan Pelaksana."""
    return {k: v for k, v in spec.items() if k != "langkah"}


def _rapikan_jalankan(v, nama_berkas):
    """Perintah uji hanya: python3/node + berkas dari lembar tugas + argumen sederhana."""
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    # Model kecil sering menulis ["python3 main.py"] (satu string) alih-alih ["python3", "main.py"].
    v = [t for x in v for t in str(x).split()]
    if not 2 <= len(v) <= 6:
        return []
    if v[0] not in conf.INTERPRETER or v[1] not in nama_berkas:
        return []
    if any(not re.fullmatch(r"[\w./=:,+*%-]{1,60}", a) for a in v[2:]):
        return []
    if v[0] == "python":
        v[0] = "python3"
    return v


def rapikan_spec(raw, tugas):
    """Lembar tugas yang sudah divalidasi dari JSON mentah buatan Perencana."""
    raw = raw if isinstance(raw, dict) else {}
    berkas = []
    for b in raw.get("berkas") or []:
        if isinstance(b, str):
            b = {"nama": b}
        if not isinstance(b, dict):
            continue
        try:
            nama = aman_nama(b.get("nama"))
        except ValueError:
            continue
        if any(x["nama"] == nama for x in berkas):
            continue
        berkas.append({"nama": nama, "fungsi": " ".join(str(b.get("fungsi") or "").split())[:300]})
        if len(berkas) >= conf.MAKS_BERKAS_RENCANA:
            break
    if not berkas:
        berkas = [{"nama": "main.py", "fungsi": " ".join(tugas.split())[:300]}]
    judul = " ".join(str(raw.get("judul") or "").split())[:60] or " ".join(tugas.split())[:40]
    jalankan = _rapikan_jalankan(raw.get("jalankan"), [b["nama"] for b in berkas])
    return {
        "judul": judul,
        "ringkasan": " ".join(str(raw.get("ringkasan") or tugas).split())[:500],
        "bahasa": " ".join(str(raw.get("bahasa") or "python").split())[:20].lower(),
        "berkas": berkas,
        "langkah": _daftar_teks(raw.get("langkah"), 5, 200),
        "kriteria": (_daftar_teks(raw.get("kriteria"), 6)
                     or ["Program memenuhi permintaan pengguna.", "Tidak ada error saat dijalankan."]),
        "jalankan": jalankan,
        "harapan": _rapikan_harapan(raw.get("harapan")) if jalankan else [],
        "catatan": " ".join(str(raw.get("catatan") or "").split())[:400],
    }


def spec_ke_md(spec):
    baris = ["# " + spec["judul"], "", spec["ringkasan"], "", "## Berkas"]
    baris += ["- `%s`: %s" % (b["nama"], b["fungsi"]) for b in spec["berkas"]]
    if spec["langkah"]:
        baris += ["", "## Langkah"] + ["%d. %s" % (i, s) for i, s in enumerate(spec["langkah"], 1)]
    baris += ["", "## Kriteria selesai"] + ["- " + k for k in spec["kriteria"]]
    baris += ["", "## Uji jalan", "`" + " ".join(spec["jalankan"]) + "`" if spec["jalankan"]
              else "(tidak ada)"]
    if spec.get("harapan"):
        baris += ["", "## Harapan keluaran", "Keluaran harus memuat: " + ", ".join(spec["harapan"])]
    if spec["catatan"]:
        baris += ["", "## Catatan", spec["catatan"]]
    return "\n".join(baris) + "\n"
