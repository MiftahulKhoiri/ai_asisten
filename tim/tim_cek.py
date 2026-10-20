"""Alat Pemeriksa: pemeriksaan berkas/sintaks, uji jalan program, dan perapian penilaian.

Semua fungsi di sini hanya mengumpulkan fakta atau merapikan bentuk jawaban. Keputusan benar/salah
ada pada Pemeriksa (lihat tim_tahap.tahap_periksa).
"""
import ast
import json
import re
import shutil
import sys
from pathlib import Path

import agen  # noqa: F401 - memastikan folder proyek ada di sys.path untuk `src.util`
from src.util import _ekor_teks, _run

from . import tim_config as conf


def cek_statis(hasil_dir, spec, ekstra=()):
    """Kembalian: (ok, baris). Berkas diminta ada, tidak kosong, dan sintaksnya benar.
    `ekstra`: nama berkas lain yang ditulis Pelaksana (ikut diperiksa sintaksnya)."""
    baris, ok = [], True
    daftar = [b["nama"] for b in spec["berkas"]]
    daftar += [n for n in ekstra if n not in daftar]
    for nama in daftar:
        p = Path(hasil_dir) / nama
        if not p.is_file():
            baris.append("GAGAL %s: berkas belum dibuat" % nama)
            ok = False
            continue
        isi = p.read_text(encoding="utf-8", errors="replace")
        galat = None
        ext = p.suffix.lower()
        if not isi.strip():
            galat = "berkas kosong"
        elif ext == ".py":
            try:
                ast.parse(isi, filename=nama)
            except SyntaxError as e:
                galat = "sintaks Python salah di baris %s: %s" % (e.lineno, e.msg)
            except ValueError as e:
                galat = "berkas Python tidak valid: %s" % e
        elif ext == ".json":
            try:
                json.loads(isi)
            except ValueError as e:
                galat = "JSON tidak valid: %s" % e
        elif ext == ".js" and shutil.which("node"):
            kode, out = _run(["node", "--check", str(p)], timeout=15)
            if kode != 0:
                galat = "sintaks JavaScript salah: " + _ekor_teks(out, 400)
        elif ext == ".sh" and shutil.which("bash"):
            kode, out = _run(["bash", "-n", str(p)], timeout=15)
            if kode != 0:
                galat = "sintaks Bash salah: " + _ekor_teks(out, 400)
        if galat:
            baris.append("GAGAL %s: %s" % (nama, galat))
            ok = False
        else:
            baris.append("OK %s: sintaks baik" % nama)
    return ok, baris


def perintah_uji(spec):
    cmd = list(spec.get("jalankan") or [])
    if cmd and cmd[0] == "python3":
        cmd[0] = sys.executable or "python3"
    return cmd


def cek_jalan(hasil_dir, spec, ctx, izin, boleh):
    """Uji jalan program. Kembalian: (status, baris, keluaran); status: lolos / gagal / dilewati.
    `keluaran` adalah keluaran program yang sebenarnya (None bila tidak dijalankan).

    Dijalankan oleh Pemeriksa. Program buatan model dijalankan HANYA setelah pengguna
    mengizinkan (ditanya sekali per proses, juga di mode AUTO), tanpa shell, di folder hasil/,
    dengan batas waktu."""
    if not spec.get("jalankan"):
        return "dilewati", ["Uji jalan dilewati: lembar tugas tidak punya perintah uji."], None
    if not boleh:
        return "dilewati", ["Uji jalan dilewati: dimatikan di pengaturan."], None
    cmd = perintah_uji(spec)
    tampil = " ".join(spec["jalankan"])
    if izin.get("nilai") is None:
        izin["nilai"] = bool(ctx.konfirmasi(
            "uji", "Pemeriksa akan menjalankan program hasil Pelaksana: " + tampil,
            "Program ini ditulis oleh model AI (Pelaksana) dan dijalankan oleh Pemeriksa di %s "
            "(batas %d detik, tanpa input keyboard). Periksa kodenya dulu bila ragu."
            % (hasil_dir, conf.UJI_DETIK)))
    if not izin["nilai"]:
        return "dilewati", ["Uji jalan dilewati: pengguna tidak mengizinkan."], None
    kode, out = _run(cmd, timeout=conf.UJI_DETIK, cwd=str(hasil_dir),
                     env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
    penuh = out or ""
    ringkas = _ekor_teks(penuh or "(tanpa keluaran)", 1500)
    if kode is None:
        return "gagal", ["GAGAL uji jalan `%s`: %s" % (tampil, ringkas)], penuh
    if kode != 0:
        return "gagal", ["GAGAL uji jalan `%s` (exit code %s):" % (tampil, kode), ringkas], penuh
    return "lolos", ["OK uji jalan `%s` (exit code 0):" % tampil, ringkas], penuh


def _norm(t):
    return " ".join(str(t or "").split()).lower()


def cocok_keluaran(keluaran, harapan):
    """Apakah keluaran program memuat semua teks harapan? Kembalian: (semua_cocok, yang_hilang).
    Angka dicocokkan utuh (88 tidak cocok dengan 188 atau 88.5)."""
    n = _norm(keluaran)
    hilang = []
    for h in harapan:
        hn = _norm(h)
        if re.fullmatch(r"-?\d+(?:\.\d+)?", hn):
            ada = re.search(r"(?<![\w.])" + re.escape(hn) + r"(?!\w|\.\d)", n) is not None
        else:
            ada = hn in n
        if not ada:
            hilang.append(h)
    return not hilang, hilang


def _masalah_bersih(m):
    """Satu masalah dari Pemeriksa, atau '' bila hanya kerangka kosong (mis. '?:? -')."""
    if isinstance(m, dict):
        uraian = " ".join(str(m.get("uraian") or m.get("masalah") or "").split())
        s = "%s:%s - %s" % (m.get("berkas") or "?", m.get("baris") or "?", uraian)
    else:
        s = uraian = " ".join(str(m).split())
    if len(re.findall(r"[A-Za-z]{3,}", uraian)) < 2:
        return ""
    return s[:300]


def rapikan_nilai(d):
    """Penilaian Pemeriksa yang dirapikan bentuknya (tipe data, panjang, kerangka kosong).
    Keputusan ok/tidak ok TIDAK diubah di sini: itu hak Pemeriksa."""
    ok = d.get("ok")
    if isinstance(ok, str):
        ok = ok.strip().lower() in ("true", "ya", "ok", "yes")
    masalah = [x for x in (_masalah_bersih(m) for m in (d.get("masalah") or [])) if x][:8]
    nilai = {"ok": bool(ok), "masalah": masalah,
             "dilihat": " ".join(str(d.get("dilihat") or "").split())[:200],
             "ringkas": " ".join(str(d.get("ringkas") or "").split())[:300],
             "perbaikan": " ".join(str(d.get("perbaikan") or "").split())[:600]}
    if nilai["ok"]:      # dinyatakan jadi: daftar masalah/perbaikan hanya membingungkan
        nilai.update(masalah=[], perbaikan="", dilihat="")
    return nilai


def nilai_cadangan(bukti):
    """Dipakai hanya bila Pemeriksa dua kali tidak memberi JSON yang terbaca: keputusan
    mengikuti hasil menjalankan program (`bukti`), dan ini dicatat jelas di 'ringkas'."""
    if bukti["ok"]:
        return {"ok": True, "masalah": [], "dilihat": "", "perbaikan": "",
                "ringkas": "Pemeriksa tidak memberi penilaian yang terbaca; keputusan memakai "
                           "hasil menjalankan program (tanpa kesalahan)."}
    gagal = [b[:300] for b in bukti["baris"] if b.startswith("GAGAL")][:5]
    return {"ok": False, "masalah": gagal or ["Menjalankan program gagal."], "dilihat": "",
            "perbaikan": "Perbaiki kesalahan yang tercatat di hasil menjalankan program.",
            "ringkas": "Pemeriksa tidak memberi penilaian yang terbaca; hasil menjalankan "
                       "program gagal."}


def teks_koreksi(cek_baris, nilai):
    bagian = []
    gagal = [b for b in cek_baris if not b.startswith("OK ")]
    if gagal:
        bagian.append("HASIL PEMERIKSA MENJALANKAN PROGRAM:\n" + "\n".join(cek_baris))
    if nilai and not nilai["ok"]:
        s = "MASUKAN PEMERIKSA:\n" + (nilai["ringkas"] or "")
        if nilai["masalah"]:
            s += "\nMasalah:\n" + "\n".join("- " + m for m in nilai["masalah"])
        if nilai.get("dilihat"):
            s += "\nKutipan: " + nilai["dilihat"]
        if nilai["perbaikan"]:
            s += "\nPerbaikan: " + nilai["perbaikan"]
        bagian.append(s)
    return "\n\n".join(bagian) or "Perbaiki hasil sebelumnya agar memenuhi semua kriteria."
