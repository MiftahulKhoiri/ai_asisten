"""Tahap kerja model: Perencana, Pelaksana, Pemeriksa, Penjelas (generator event).

Pelaksana hanya menulis. Pemeriksa yang menjalankan programnya (pemeriksa_menjalankan) dan yang
menentukan benar/salah (tahap_periksa).
"""
import json
from pathlib import Path

from . import tim_config as conf
from .tim_berkas import aman_nama, baca_json, baca_proyek, hash_proyek, tulis_berkas, urai_berkas
from .tim_cek import (cek_jalan, cek_statis, cocok_keluaran, nilai_cadangan, rapikan_nilai,
                      tebak_perintah)
from .tim_config import Batal
from .tim_laporan import blok_fakta, blok_fakta_bug
from .tim_llm import ambil_json, tanya
from .tim_prompt import (
    SYSTEM_DIAGNOSA,
    SYSTEM_PELAKSANA,
    SYSTEM_PEMERIKSA,
    SYSTEM_PENJELAS,
    SYSTEM_PENJELAS_BUG,
    SYSTEM_PERENCANA,
    pesan_chat,
    pesan_minta_masalah,
    pesan_ulang_json,
    prompt_diagnosa,
    prompt_jelas,
    prompt_jelas_bug,
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


def tahap_rencana(tugas, spec_lama, hasil_dir, folder, mp, ctx, pemuat, jejak, diagnosa=None):
    """Kembalian: (spec, pertanyaan). Bila Perencana butuh info: (None, pertanyaan).

    `diagnosa`: nilai Pemeriksa dari tahap Diagnosa (jalur perbaiki); temuannya jadi dasar lembar tugas."""
    yield event_tahap("rencana", mp)
    yield from pemuat.pakai(mp)
    ada = [n for n, _ in baca_proyek(hasil_dir, conf.MAKS_BACA)]    # kosong bila proses baru tanpa bahan
    user = prompt_rencana(tugas, spec_lama, ada, diagnosa=diagnosa)
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


def tahap_tulis(spec, koreksi, hasil_dir, me, ctx, jejak, putaran, batas_berkas=None):
    """Pelaksana menulis berkas. Kembalian: (nama_berkas_ditulis, daftar_masalah_format).

    `batas_berkas`: jumlah berkas maksimum di proyek (bawaan conf.MAKS_BERKAS_TOTAL; proses dengan
    berkas unggahan memberi batas lebih besar supaya berkas unggahan tidak menghabiskan jatah)."""
    batas_berkas = batas_berkas or conf.MAKS_BERKAS_TOTAL
    user = prompt_tulis(spec, koreksi, baca_proyek(hasil_dir, conf.MAKS_BACA))
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
        if not lengkap and terpotong:    # lupa '=== END ===' tanpa terpotong tetap diterima
            masalah.append("%s: keluaran terpotong (batas token tercapai); tulis lebih ringkas "
                           "atau pecah menjadi berkas yang lebih kecil." % nama)
            continue
        if not isi.strip():
            masalah.append("%s: isi berkas kosong." % nama)
            continue
        baru = not (Path(hasil_dir) / nama).exists()
        if baru and len(baca_proyek(hasil_dir, batas_berkas)) >= batas_berkas:
            masalah.append("%s: melebihi batas %d berkas per proyek." % (nama, batas_berkas))
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


def pemeriksa_menjalankan(spec, cfg, hasil_dir, ditulis, masalah):
    """Pemeriksa menjalankan hasil Pelaksana: berkas ada, sintaks benar, lalu uji jalan program
    (bila diizinkan di pengaturan). Kembalian: bukti {ok, baris, jalan, keluaran, harapan}.

    Ini hanya mengumpulkan FAKTA untuk Pemeriksa; keputusan benar/salah ada di tahap_periksa.
    Harapan Perencana juga hanya fakta tambahan (bisa keliru), bukan jalan pintas lolos."""
    yield {"t": "cek_mulai", "oleh": "Pemeriksa"}
    ok_statis, baris = cek_statis(hasil_dir, spec, ditulis)
    baris = ["GAGAL format: " + m for m in masalah] + baris
    ok = ok_statis and not masalah
    status_jalan, keluaran, harapan = "dilewati", None, None
    if ok:
        if spec["jalankan"] and cfg["uji"]:
            yield {"t": "uji_mulai", "d": " ".join(spec["jalankan"]), "oleh": "Pemeriksa"}
        status_jalan, jalan, keluaran = cek_jalan(hasil_dir, spec, cfg["uji"])
        baris += jalan
        ok = status_jalan != "gagal"
    if ok and keluaran is not None and spec["harapan"]:
        harapan, hilang = cocok_keluaran(keluaran, spec["harapan"])
        if harapan:
            baris.append("OK keluaran memuat harapan Perencana: " + ", ".join(spec["harapan"]))
        else:
            baris.append("CATATAN: keluaran tidak memuat harapan Perencana (%s); harapan "
                         "ini bisa keliru." % ", ".join(hilang))
    yield {"t": "cek", "ok": ok, "jalan": status_jalan, "harapan": harapan,
           "d": "\n".join(baris), "oleh": "Pemeriksa"}
    return {"ok": ok, "baris": baris, "jalan": status_jalan, "keluaran": keluaran,
            "harapan": harapan}


def tahap_periksa(spec, bukti, hasil_dir, mc, ctx, jejak, putaran):
    """Pemeriksa menentukan benar atau salah. Kembalian: nilai {ok, masalah, perbaikan, ...}.

    ok=True  -> hasil dinyatakan jadi.
    ok=False -> berisi masalah + perbaikan, dikirim ke Pelaksana sebagai koreksi.
    Kode tidak membalik keputusan itu. Pengecualian yang disengaja, semuanya tercatat di
    'ringkas': (1) tidak ada berkas sama sekali, tidak ada yang bisa dinilai; (2) jawaban tidak
    terbaca sebagai JSON dua kali, keputusan memakai hasil menjalankan program; (3) menolak
    tanpa menyebut satu masalah pun setelah ditanya ulang: bila program lolos dijalankan,
    diterima; bila program gagal, penolakan tetap berlaku dan masalahnya diambil dari hasil
    menjalankan (koreksi kosong tidak bisa dikirim ke Pelaksana)."""
    berkas = baca_proyek(hasil_dir, conf.MAKS_BACA)
    if not berkas:
        return {"ok": False, "dilihat": "", "masalah": ["Tidak ada berkas hasil untuk diperiksa."],
                "ringkas": "Pelaksana belum menghasilkan berkas.",
                "perbaikan": "Tulis semua berkas lembar tugas dengan format "
                             "=== FILE: nama === ... === END ==="}
    user = prompt_periksa(spec, bukti["baris"], berkas)
    pesan = pesan_chat(SYSTEM_PEMERIKSA, user)
    nilai = yield from _minta_nilai(mc, pesan, user, ctx, jejak, "periksa-%d" % putaran, bukti)
    return nilai


def _minta_nilai(mc, pesan, user, ctx, jejak, kunci, bukti):
    """Minta penilaian JSON dari Pemeriksa; dipakai tahap Periksa dan tahap Diagnosa.

    JSON tidak terbaca -> ditanya ulang sekali, lalu keputusan memakai hasil menjalankan (`bukti`).
    Menolak tanpa masalah konkret -> ditanya ulang sekali; bila tetap kosong: diterima bila hasil
    menjalankan baik, bila gagal masalahnya diambil dari hasil menjalankan."""
    teks, _ = yield from tanya(mc, pesan, ctx, conf.TOKEN_PERIKSA, 0.1, True)
    jejak.simpan(kunci, user, teks)
    d = ambil_json(teks)
    if d is None:
        pesan += pesan_ulang_json(teks)
        teks, _ = yield from tanya(mc, pesan, ctx, conf.TOKEN_PERIKSA, 0.1, True)
        jejak.simpan(kunci + "-ulang", "(permintaan ulang JSON)", teks)
        d = ambil_json(teks)
    if d is None:
        return nilai_cadangan(bukti)
    nilai = rapikan_nilai(d)
    if not nilai["ok"] and not nilai["masalah"]:
        pesan += pesan_minta_masalah(teks)
        teks, _ = yield from tanya(mc, pesan, ctx, conf.TOKEN_PERIKSA, 0.1, True)
        jejak.simpan(kunci + "-masalah", "(minta masalah konkret)", teks)
        d2 = ambil_json(teks)
        if d2 is not None:
            nilai = rapikan_nilai(d2)
        if not nilai["ok"] and not nilai["masalah"]:
            if bukti["ok"]:
                nilai.update(ok=True, perbaikan="", dilihat="",
                             ringkas=(nilai["ringkas"] + " (menolak tanpa menyebut masalah "
                                      "konkret; diterima)").strip())
            else:    # program gagal: penolakan tetap sah, masalahnya diambil dari hasil menjalankan
                gagal = [b[:300] for b in bukti["baris"] if b.startswith("GAGAL")][:5]
                nilai.update(masalah=gagal or ["Menjalankan program gagal."],
                             perbaikan=nilai["perbaikan"]
                             or "Perbaiki kesalahan yang tercatat di hasil menjalankan program.")
    return nilai


# ---------------------------------------------------------------------------
# Jalur perbaiki / cari_bug: Pemeriksa memeriksa kode yang SUDAH ADA lebih dulu
# ---------------------------------------------------------------------------
def diagnosa_menjalankan(cfg, hasil_dir, berkas):
    """Pemeriksa memeriksa proyek yang sudah ada: sintaks semua berkas teks yang tidak kosong,
    lalu (bila diizinkan di pengaturan) uji jalan pada titik masuk yang DITEBAK.

    Berkas kosong (mis. __init__.py) sah pada proyek nyata, jadi tidak dianggap salah. Hasil uji
    jalan tebakan hanya CATATAN, bukan bukti bug (program bisa butuh argumen atau berjalan terus).
    Kembalian: bukti {ok, baris, jalan, keluaran, harapan}; `ok` hanya dari pemeriksaan sintaks."""
    yield {"t": "cek_mulai", "oleh": "Pemeriksa"}
    tidak_kosong = [n for n, isi in berkas if isi.strip()]
    ok, baris = cek_statis(hasil_dir, {"berkas": [{"nama": n} for n in tidak_kosong]})
    gagal = [b for b in baris if b.startswith("GAGAL")]
    baris = gagal + ["OK sintaks: %d berkas diperiksa%s" % (
        len(tidak_kosong), (", %d bermasalah" % len(gagal)) if gagal else ", semuanya baik")]
    status_jalan, keluaran = "dilewati", None
    cmd = tebak_perintah(berkas) if (ok and cfg.get("uji")) else []
    if cmd:
        yield {"t": "uji_mulai", "d": " ".join(cmd), "oleh": "Pemeriksa"}
        status_jalan, jalan, keluaran = cek_jalan(hasil_dir, {"jalankan": cmd, "harapan": []}, True)
        baris += ["CATATAN tebakan titik masuk, tanpa argumen: " + jalan[0]] + ["  " + b for b in jalan[1:]]
    yield {"t": "cek", "ok": ok, "jalan": status_jalan, "harapan": None,
           "d": "\n".join(baris), "oleh": "Pemeriksa", "diagnosa": True}
    return {"ok": ok, "baris": baris, "jalan": status_jalan, "keluaran": keluaran, "harapan": None}


def tahap_diagnosa(tugas, cfg, hasil_dir, folder, mc, ctx, pemuat, jejak):
    """Pemeriksa mendiagnosa kode yang sudah ada. Kembalian: {nilai, baris, jalan, dilihat, total, hash}.

    nilai["ok"]=True berarti tidak ada bug nyata yang bisa ditunjuk. Satu-satunya penyesuaian dari
    kode: sintaks salah yang dicatat sistem tidak boleh dinyatakan 'tidak ada bug'."""
    yield event_tahap("diagnosa", mc)
    yield from pemuat.pakai(mc)
    berkas = baca_proyek(hasil_dir, conf.MAKS_BACA)
    bukti = yield from diagnosa_menjalankan(cfg, hasil_dir, berkas)
    user, dilihat, total = prompt_diagnosa(tugas, "\n".join(bukti["baris"]), berkas)
    pesan = pesan_chat(SYSTEM_DIAGNOSA, user)
    nilai = yield from _minta_nilai(mc, pesan, user, ctx, jejak, "diagnosa", bukti)
    if nilai["ok"] and not bukti["ok"]:
        gagal = [b[:300] for b in bukti["baris"] if b.startswith("GAGAL")][:5]
        nilai.update(ok=False, masalah=gagal,
                     perbaikan=nilai["perbaikan"] or "Perbaiki kesalahan sintaks yang dicatat sistem.",
                     ringkas=(nilai["ringkas"] + " (disesuaikan: sistem mencatat sintaks salah)").strip())
    hasil = {"nilai": nilai, "baris": bukti["baris"], "jalan": bukti["jalan"], "dilihat": dilihat,
             "total": total, "hash": hash_proyek(hasil_dir), "dipakai_ulang": False}
    simpan_diagnosa(folder, hasil)
    yield dict(nilai, t="diagnosa", diperiksa=dilihat, total=total, dipakai_ulang=False)
    return hasil


def simpan_diagnosa(folder, hasil):
    try:
        (Path(folder) / "diagnosa.json").write_text(json.dumps(hasil, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
    except OSError:
        pass


def diagnosa_lama(folder_lama, hasil_dir):
    """Diagnosa proses sebelumnya bila isi proyek sama persis dan ada temuan; selain itu None."""
    d = baca_json(Path(folder_lama) / "diagnosa.json")
    if (isinstance(d, dict) and isinstance(d.get("nilai"), dict) and d["nilai"].get("ok") is False
            and d["nilai"].get("masalah") and d.get("hash") == hash_proyek(hasil_dir)):
        return d
    return None


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


def tahap_jelaskan_bug(status, tugas, diag, hasil_dir, meta, mp, ctx, pemuat, jejak):
    """Penjelas menjelaskan hasil diagnosa dengan prosa singkat; daftar temuan dan status ditulis sistem."""
    yield event_tahap("jelaskan", mp)
    prosa = ""
    try:
        yield from pemuat.pakai(mp)
        user = prompt_jelas_bug(tugas, diag["nilai"], diag["dilihat"], diag["total"])
        pesan = pesan_chat(SYSTEM_PENJELAS_BUG, user)
        prosa, _ = yield from tanya(mp, pesan, ctx, conf.TOKEN_JELAS, 0.3, False, keluar="token")
        jejak.simpan("jelaskan", user, prosa)
        prosa = prosa.strip()
    except Batal:
        raise
    except Exception as e:  # noqa: BLE001 - penjelasan gagal bukan kegagalan proses
        yield {"t": "ringkas", "d": "Penjelasan otomatis gagal (%s); memakai ringkasan biasa." % e}
    if not prosa:
        prosa = diag["nilai"].get("ringkas") or "Diagnosa selesai."
        yield {"t": "token", "d": prosa}
    fakta = "\n\n" + blok_fakta_bug(status, diag, meta)
    yield {"t": "token", "d": fakta}
    return prosa + fakta
