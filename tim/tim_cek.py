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
from .tim_kotak import jalankan_terkurung, ringkas_isolasi


def _baris_ke(isi, nomor, maks=120):
    """Isi baris ke-`nomor` (mulai 1) yang sudah dirapikan; "" bila tidak ada. Pagar ` diganti ' agar
    tidak bentrok dengan pembungkus `...` di pesan."""
    try:
        baris = isi.splitlines()[int(nomor) - 1]
    except (TypeError, ValueError, IndexError):
        return ""
    return baris.strip().replace("`", "'")[:maks]


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
                rusak = _baris_ke(isi, e.lineno)
                if rusak:    # Pemeriksa model kecil sering salah menunjuk baris; beri isi barisnya
                    galat += " | isi baris %s: `%s`" % (e.lineno, rusak)
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


def cek_jalan(hasil_dir, spec, boleh):
    """Uji jalan program. Kembalian: (status, baris, keluaran); status: lolos / gagal / dilewati.
    `keluaran` adalah keluaran program yang sebenarnya (None bila tidak dijalankan).

    Dijalankan oleh Pemeriksa. Izin ada di pengaturan (`boleh`, dikirim dari web): proses Agent
    bisa berjalan lama di latar belakang, jadi tidak ada lagi pertanyaan di tengah jalan.
    Program buatan model dijalankan tanpa shell, di folder hasil/, tanpa input keyboard, dengan
    batas waktu, environment bersih, batas memori/CPU/proses, dan jaringan diputus bila bisa
    (lihat tim_kotak.py)."""
    if not spec.get("jalankan"):
        return "dilewati", ["Uji jalan dilewati: lembar tugas tidak punya perintah uji."], None
    if not boleh:
        return "dilewati", ["Uji jalan dilewati: belum diizinkan di pengaturan."], None
    cmd = perintah_uji(spec)
    tampil = " ".join(spec["jalankan"])
    kode, out = jalankan_terkurung(cmd, str(hasil_dir), conf.UJI_DETIK)
    penuh = out or ""
    ringkas = _ekor_teks(penuh or "(tanpa keluaran)", 1500)
    # Catatan untuk Pemeriksa: kegagalan akibat pengurungan (mis. akses jaringan) bukan bug program.
    catatan = "CATATAN isolasi uji jalan: " + ringkas_isolasi(cmd) + "."
    if kode is None:
        return "gagal", ["GAGAL uji jalan `%s`: %s" % (tampil, ringkas), catatan], penuh
    if kode != 0:
        return "gagal", ["GAGAL uji jalan `%s` (exit code %s):" % (tampil, kode), ringkas, catatan], penuh
    return "lolos", ["OK uji jalan `%s` (exit code 0):" % tampil, ringkas, catatan], penuh


def tebak_perintah(berkas):
    """Tebakan perintah untuk menjalankan proyek yang sudah ada (tanpa argumen): [] bila ragu.

    Python: berkas dengan `if __name__ == "__main__"` (main.py didahulukan bila ada beberapa);
    JavaScript: main.js / index.js. Hanya TEBAKAN: hasilnya dicatat sebagai catatan, bukan bukti bug."""
    isi = dict(berkas)
    py = [n for n in isi if n.endswith(".py") and "/" not in n and "__main__" in isi[n]
          and re.search(r"__name__\s*==\s*[\"']__main__[\"']", isi[n])]
    if len(py) == 1:
        return ["python3", py[0]]
    if "main.py" in py:
        return ["python3", "main.py"]
    for n in ("main.js", "index.js"):
        if n in isi:
            return ["node", n]
    return []


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
    mentah = d.get("masalah") or []
    if isinstance(mentah, (str, dict)):
        mentah = [mentah]
    if not isinstance(mentah, (list, tuple)):
        mentah = []
    masalah = [x for x in (_masalah_bersih(m) for m in mentah) if x][:8]
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
                "lemah": "Pemeriksa tidak memberi penilaian yang terbaca; diterima hanya karena "
                         "tidak ada kesalahan saat menjalankan/memeriksa program.",
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
        if nilai.get("kutipan") is False:
            s += ("\nCATATAN SISTEM: kutipan/berkas yang disebut Pemeriksa TIDAK ditemukan di kode atau "
                  "keluaran program, jadi temuan ini mungkin keliru. Periksa sendiri; bila kodenya "
                  "sudah benar, jangan diubah.")
        bagian.append(s)
    return "\n\n".join(bagian) or "Perbaiki hasil sebelumnya agar memenuhi semua kriteria."


# ---------------------------------------------------------------------------
# Verifikasi mekanis temuan Pemeriksa (tidak menilai benar/salah, hanya memastikan temuannya
# menunjuk sesuatu yang memang ada)
# ---------------------------------------------------------------------------
_NOMOR_AWAL = re.compile(r"^\s*\d{1,5}\s*[:|)]\s?")
_NOMOR_DALAM = re.compile(r"(?:(?<=\s)|^)\d{1,5}:\s")
_BERKAS_BARIS = re.compile(r"^\s*[\w./-]+\.\w{1,5}\s*:\s*\d+\s*[-–:]?\s*")


def _lurus(t):
    return " ".join(str(t or "").split()).lower()


def kutipan_ditemukan(kutipan, berkas, tambahan=()):
    """Apakah kutipan Pemeriksa (`dilihat`) benar-benar ada di isi berkas atau di teks tambahan
    (hasil/keluaran menjalankan program)? Kembalian True / False; None bila tidak ada kutipan yang
    bisa dicek (kosong atau terlalu pendek). Spasi dan huruf besar/kecil diabaikan, awalan nomor baris
    ("12: ") dan "berkas:baris -" dibuang, "..." memisahkan beberapa potongan yang semuanya harus ada."""
    k = str(kutipan or "").strip().strip("`'\"")
    if not k:
        return None
    korpus = _lurus("\n".join(isi for _, isi in berkas) + "\n" + "\n".join(str(t) for t in tambahan if t))
    varian = {k, _NOMOR_DALAM.sub("", k)}
    pernah_dinilai = False
    for v in varian:
        bagian = []
        for b in re.split(r"\n|\s\.{3}\s|…", v):
            b = _lurus(_BERKAS_BARIS.sub("", _NOMOR_AWAL.sub("", b)))
            if len(b) >= 4:
                bagian.append(b)
        if not bagian:
            continue
        pernah_dinilai = True
        if all(b in korpus for b in bagian):
            return True
    return False if pernah_dinilai else None


def masalah_tanpa_berkas(masalah, nama_berkas):
    """Masalah ("berkas:baris - uraian") yang menyebut berkas yang TIDAK ada di proyek."""
    ada = {n for n in nama_berkas} | {n.rsplit("/", 1)[-1] for n in nama_berkas}
    hasil = []
    for m in masalah or []:
        mm = re.match(r"\s*([\w./-]+\.\w{1,5})\s*:", str(m))
        if mm and mm.group(1) not in ada and mm.group(1).rsplit("/", 1)[-1] not in ada:
            hasil.append(m)
    return hasil


def periksa_dasar(nilai, berkas, tambahan=()):
    """Verifikasi temuan penolakan: True = kutipan terbukti ada, False = kutipan tidak ada atau SEMUA
    masalah menyebut berkas yang tidak ada, None = tidak ada yang bisa dicek."""
    if nilai.get("ok"):
        return None
    kut = kutipan_ditemukan(nilai.get("dilihat"), berkas, tambahan)
    masalah = nilai.get("masalah") or []
    tanpa = masalah_tanpa_berkas(masalah, [n for n, _ in berkas])
    if masalah and len(tanpa) == len(masalah):
        return False
    return kut


_KUTIP_KODE = re.compile(r"`([^`\n]{8,})`")


def perbaikan_sia_sia(perbaikan, berkas):
    """True bila saran `perbaikan` meminta kode yang SUDAH persis ada di berkas (isi `berkas`: [(nama, isi)]).
    Contoh nyata: kode salah di baris 4, Pemeriksa menyuruh 'ubah baris 4 menjadi `return ...`' padahal
    itu isi baris 2. Saran begini tidak mengubah apa pun dan membuat Pelaksana menulis ulang kode yang sama."""
    baris_ada = {b.strip() for _, isi in berkas for b in isi.splitlines() if len(b.strip()) >= 8}
    snippet = [s.strip() for s in _KUTIP_KODE.findall(str(perbaikan or ""))]
    return bool(snippet) and all(s in baris_ada for s in snippet)


def _kata(t):
    return set(re.findall(r"[a-z0-9_]{3,}", str(t).lower()))


def mirip(a, b, batas=0.6):
    """Dua uraian masalah dianggap sama bila kata-katanya (Jaccard) cukup beririsan."""
    ka, kb = _kata(a), _kata(b)
    if not ka or not kb:
        return False
    return len(ka & kb) / len(ka | kb) >= batas


def gabung_masalah(*daftar, maks=8):
    """Gabungan beberapa daftar masalah tanpa pengulangan (yang mirip dianggap sama)."""
    hasil = []
    for d in daftar:
        for m in d or []:
            if not any(mirip(m, x) for x in hasil):
                hasil.append(m)
    return hasil[:maks]


def masalah_berulang(baru, lama):
    """True bila sebagian besar masalah `baru` sudah ada di `lama` (koreksi tidak membuahkan hasil)."""
    if not baru or not lama:
        return False
    sama = sum(1 for m in baru if any(mirip(m, x) for x in lama))
    return sama * 2 >= len(baru)
