"""Orkestrator: putaran Pelaksana -> pemeriksaan -> koreksi, serta pintu masuk jalankan().
"""
import json
import secrets
import time
from datetime import datetime
from pathlib import Path

from . import tim_config as conf
from .tim_berkas import baca_json, baca_proyek, pulihkan, salin_proyek
from .tim_cek import cek_jalan, cek_statis, cocok_keluaran, teks_koreksi
from .tim_config import Batal
from .tim_model import Pemuat
from .tim_riwayat import AKTIF_RUN
from .tim_tahap import (
    Jejak,
    event_tahap,
    tahap_jelaskan,
    tahap_periksa,
    tahap_rencana,
    tahap_tulis,
)


def kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat, izin, akhir, jejak):
    """Putaran Pelaksana -> pemeriksaan -> koreksi. Kembalian: 'lolos' atau 'belum'.
    `akhir` (dict) diisi hasil pemeriksaan terakhir untuk penjelasan.

    Bukti dari kode lebih berat daripada pendapat model: keluaran yang memuat 'harapan'
    Perencana langsung lolos (Pemeriksa dilewati), dan bila akhirnya belum sempurna, hasil
    putaran terbaik dipulihkan supaya koreksi yang keliru tidak merusak hasil yang lebih baik."""
    mp, me, mc, maks = cfg["model_p"], cfg["model_e"], cfg["model_c"], cfg["maks"]
    koreksi = ""
    rekam = []    # per putaran: skor (2 lolos+harapan, 1 lolos, 0 gagal), isi berkas, hasil cek
    for putaran in range(1, maks + 1):
        meta["putaran"] = putaran
        yield {"t": "putaran", "n": putaran, "maks": maks}
        yield event_tahap("tulis", me, putaran)
        yield from pemuat.pakai(me)
        ditulis, masalah = yield from tahap_tulis(spec, koreksi, hasil_dir, me, ctx, jejak, putaran)

        # Pemeriksaan otomatis (kode): sintaks, berkas ada, uji jalan, harapan keluaran
        yield {"t": "cek_mulai"}
        ok_statis, baris = cek_statis(hasil_dir, spec, ditulis)
        baris = ["GAGAL format: " + m for m in masalah] + baris
        ok = ok_statis and not masalah
        status_jalan, keluaran, harapan = "dilewati", None, None
        if ok:
            if spec["jalankan"] and cfg["uji"]:
                yield {"t": "uji_mulai", "d": " ".join(spec["jalankan"])}
            status_jalan, jalan, keluaran = cek_jalan(hasil_dir, spec, ctx, izin, cfg["uji"])
            baris += jalan
            ok = status_jalan != "gagal"
        if ok and keluaran is not None and spec["harapan"]:
            harapan, hilang = cocok_keluaran(keluaran, spec["harapan"])
            if harapan:
                baris.append("OK keluaran memuat harapan Perencana: " + ", ".join(spec["harapan"]))
            else:
                baris.append("CATATAN: keluaran tidak memuat harapan Perencana (%s); harapan "
                             "ini bisa keliru." % ", ".join(hilang))
        akhir.clear()
        akhir.update(cek=baris, jalan=status_jalan, keluaran=keluaran, harapan=harapan,
                     nilai=None, pulih=None)
        rekam.append({"skor": ((2 if harapan else 1) if ok else 0), "putaran": putaran,
                      "berkas": dict(baca_proyek(hasil_dir)), "akhir": dict(akhir)})
        yield {"t": "cek", "ok": ok, "jalan": status_jalan, "harapan": harapan,
               "d": "\n".join(baris)}
        if ctx.batal.is_set():
            raise Batal()

        if ok and harapan:     # bukti cukup: Pemeriksa tidak perlu dimuat
            yield {"t": "ringkas", "d": "Keluaran sesuai harapan Perencana; Pemeriksa dilewati."}
            yield from pemuat.selesai_tahap(mp)
            return "lolos"

        berikut = mc if ok else (me if putaran < maks else mp)
        yield from pemuat.selesai_tahap(berikut)
        if not ok:   # kesalahan sudah pasti: langsung kembali ke Pelaksana tanpa memuat Pemeriksa
            koreksi = teks_koreksi(baris, None)
            (folder / ("koreksi_%d.md" % putaran)).write_text(koreksi, encoding="utf-8")
            continue

        yield event_tahap("periksa", mc, putaran)
        yield from pemuat.pakai(mc)
        nilai = yield from tahap_periksa(spec, baris, hasil_dir, mc, ctx, keluaran, jejak, putaran)
        akhir["nilai"] = nilai
        rekam[-1]["akhir"]["nilai"] = nilai
        yield dict(nilai, t="nilai")
        if nilai["ok"]:
            yield from pemuat.selesai_tahap(mp)
            return "lolos"
        koreksi = teks_koreksi(baris, nilai)
        (folder / ("koreksi_%d.md" % putaran)).write_text(koreksi, encoding="utf-8")
        yield from pemuat.selesai_tahap(me if putaran < maks else mp)

    terbaik = max(rekam, key=lambda r: (r["skor"], r["putaran"]))
    if terbaik["putaran"] != rekam[-1]["putaran"]:
        pulihkan(hasil_dir, terbaik["berkas"])
        akhir.clear()
        akhir.update(terbaik["akhir"])
        akhir["pulih"] = terbaik["putaran"]
        yield {"t": "pulih", "putaran": terbaik["putaran"],
               "d": "Hasil putaran %d dipulihkan: lebih baik daripada putaran terakhir."
                    % terbaik["putaran"]}
    return "belum"


def _jalankan(tugas, cfg, ctx, lanjut=None):
    """Generator event untuk satu proses Agent (satu perintah pengguna)."""
    tugas = (tugas or "").strip()[:conf.MAKS_TUGAS]
    conf.KERJA.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    folder = conf.KERJA / run_id
    hasil_dir = folder / "hasil"
    hasil_dir.mkdir(parents=True)
    meta = {"id": run_id, "tugas": tugas, "judul": " ".join(tugas.split())[:40],
            "status": "error", "dibuat": datetime.now().isoformat(timespec="seconds"),
            "model": {"perencana": cfg["model_p"], "pelaksana": cfg["model_e"],
                      "pemeriksa": cfg["model_c"]},
            "putaran": 0, "maks": cfg["maks"], "lanjut": None, "laporan": "", "spec": None}
    spec_lama = None
    if lanjut and conf.ID_RUN.match(str(lanjut)) and (conf.KERJA / lanjut).is_dir():
        salin_proyek(conf.KERJA / lanjut / "hasil", hasil_dir)
        spec_lama = baca_json(conf.KERJA / lanjut / "tugas.json")
        meta["lanjut"] = lanjut
    yield {"t": "mulai", "id": run_id, "dir": str(folder), "maks": cfg["maks"],
           "model": meta["model"], "lanjut": meta["lanjut"]}

    pemuat = Pemuat(ctx, cfg["bongkar"])
    jejak = Jejak(folder)
    AKTIF_RUN.add(run_id)
    izin = {"nilai": None}
    akhir = {}
    status, spec = "error", None
    try:
        spec, pertanyaan = yield from tahap_rencana(tugas, spec_lama, hasil_dir, folder,
                                               cfg["model_p"], ctx, pemuat, jejak)
        if spec is None:
            status = "butuh_info"
            meta["laporan"] = pertanyaan
            yield {"t": "tanya", "d": pertanyaan}
            yield from pemuat.lepas_semua()
        else:
            meta["spec"], meta["judul"] = spec, spec["judul"]
            yield from pemuat.selesai_tahap(cfg["model_e"])
            status = yield from kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat,
                                          izin, akhir, jejak)
            meta["laporan"] = yield from tahap_jelaskan(status, spec, hasil_dir, meta, akhir,
                                                   cfg["model_p"], ctx, pemuat, jejak)
            yield from pemuat.lepas_semua()
    except Batal:
        status = "batal"
        yield {"t": "batal"}
    except Exception as e:  # noqa: BLE001
        status = "error"
        yield {"t": "error", "d": "%s: %s" % (type(e).__name__, e)}
    finally:
        AKTIF_RUN.discard(run_id)
        pemuat.lepas_diam()
        meta["status"] = status
        try:
            if meta["laporan"]:
                (folder / "laporan.md").write_text(meta["laporan"], encoding="utf-8")
            (folder / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        except OSError:
            pass
    yield {"t": "selesai", "status": status, "id": run_id,
           "teks": conf.STATUS_TEKS.get(status, status), "dir": str(folder)}


def jalankan(tugas, cfg, ctx, lanjut=None):
    """Generator event satu proses Agent; juga mencatat log.jsonl di folder kerja
    (tanpa potongan teks per token) agar proses bisa ditinjau setelah halaman ditutup."""
    t0, log = time.time(), None
    try:
        for ev in _jalankan(tugas, cfg, ctx, lanjut):
            if ev["t"] == "mulai":
                try:
                    log = open(Path(ev["dir"]) / "log.jsonl", "a", encoding="utf-8")
                except OSError:
                    log = None
            if log and ev["t"] not in ("isi", "token", "muat"):
                try:
                    rapi = {k: v for k, v in ev.items() if k != "isi"}
                    log.write(json.dumps(dict(rapi, ts=round(time.time() - t0, 1)),
                                         ensure_ascii=False) + "\n")
                    log.flush()
                except (OSError, TypeError, ValueError):
                    pass
            yield ev
    finally:
        if log:
            log.close()
