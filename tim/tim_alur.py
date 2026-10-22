"""Orkestrator: putaran Pelaksana (menulis) -> Pemeriksa (menjalankan + menentukan) -> koreksi,
serta pintu masuk jalankan().
"""
import json
import secrets
import time
from datetime import datetime
from pathlib import Path

from . import tim_config as conf
from .tim_berkas import baca_json, baca_proyek, masukkan_bahan, pulihkan, salin_proyek
from .tim_cek import teks_koreksi
from .tim_config import Batal
from .tim_model import Pemuat
from .tim_riwayat import AKTIF_RUN, tulis_meta
from .tim_tahap import (
    Jejak,
    event_tahap,
    pemeriksa_menjalankan,
    tahap_jelaskan,
    tahap_periksa,
    tahap_rencana,
    tahap_tulis,
)


def kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat, akhir, jejak):
    """Putaran Pelaksana -> Pemeriksa -> koreksi. Kembalian: 'lolos' atau 'belum'.
    `akhir` (dict) diisi hasil pemeriksaan terakhir untuk penjelasan.

    Pembagian tugas:
      Pelaksana  hanya MENULIS program. Ia tidak menjalankan apa pun.
      Pemeriksa  menerima hasil Pelaksana langsung, MENJALANKAN programnya, lalu MENENTUKAN
                 benar atau salah: dinyatakan jadi (selesai) atau memberi koreksi yang dikirim
                 balik ke Pelaksana. Tidak ada jalan pintas dari kode yang melewati Pemeriksa.

    Bila akhirnya belum sempurna, hasil putaran terbaik dipulihkan supaya koreksi yang keliru
    tidak merusak hasil yang lebih baik."""
    mp, me, mc, maks = cfg["model_p"], cfg["model_e"], cfg["model_c"], cfg["maks"]
    koreksi = ""
    rekam = []    # per putaran: skor, isi berkas, hasil pemeriksaan
    for putaran in range(1, maks + 1):
        meta["putaran"] = putaran
        tulis_meta(folder, meta)       # pemantau yang membuka halaman lagi melihat putaran terbaru
        yield {"t": "putaran", "n": putaran, "maks": maks}

        # 1. Pelaksana: menulis berkas (tidak menjalankan apa pun)
        yield event_tahap("tulis", me, putaran)
        yield from pemuat.pakai(me)
        batas = conf.MAKS_BERKAS_TOTAL + len(meta.get("bahan") or [])   # berkas unggahan tidak dihitung
        ditulis, masalah = yield from tahap_tulis(spec, koreksi, hasil_dir, me, ctx, jejak, putaran,
                                                  batas)

        # 2. Hasilnya langsung ke Pemeriksa
        yield from pemuat.selesai_tahap(mc)
        yield event_tahap("periksa", mc, putaran)
        yield from pemuat.pakai(mc)

        # 2a. Pemeriksa menjalankan program (sintaks, berkas ada, uji jalan)
        bukti = yield from pemeriksa_menjalankan(spec, cfg, hasil_dir, ditulis, masalah)
        akhir.clear()
        akhir.update(cek=bukti["baris"], jalan=bukti["jalan"], keluaran=bukti["keluaran"],
                     harapan=bukti["harapan"], fakta_ok=bukti["ok"], nilai=None, pulih=None)
        if ctx.batal.is_set():
            raise Batal()

        # 2b. Pemeriksa menentukan benar atau salah
        nilai = yield from tahap_periksa(spec, bukti, hasil_dir, mc, ctx, jejak, putaran)
        akhir["nilai"] = nilai
        rekam.append({"skor": (2 if nilai["ok"] else 0) + (1 if bukti["ok"] else 0)
                              + (1 if bukti["harapan"] else 0),
                      "putaran": putaran, "berkas": dict(baca_proyek(hasil_dir, conf.MAKS_BACA)),
                      "akhir": dict(akhir)})
        yield dict(nilai, t="nilai")

        # 3. Keputusan Pemeriksa: jadi -> selesai; belum -> koreksi ke Pelaksana
        if nilai["ok"]:
            yield from pemuat.selesai_tahap(mp)
            return "lolos"
        koreksi = teks_koreksi(bukti["baris"], nilai)
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


def _jalankan(tugas, cfg, ctx, lanjut=None, bahan=None):
    """Generator event untuk satu proses Agent (satu perintah pengguna).

    `bahan`: folder berisi berkas unggahan pengguna; isinya disalin ke folder kerja sebelum
    Perencana mulai (di atas hasil proses lama bila `lanjut` juga diberikan)."""
    tugas = (tugas or "").strip()[:conf.MAKS_TUGAS]
    conf.KERJA.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    folder = conf.KERJA / run_id
    hasil_dir = folder / "hasil"
    hasil_dir.mkdir(parents=True)
    meta = {"id": run_id, "tugas": tugas, "judul": " ".join(tugas.split())[:40],
            "status": "berjalan", "dibuat": datetime.now().isoformat(timespec="seconds"),
            "model": {"perencana": cfg["model_p"], "pelaksana": cfg["model_e"],
                      "pemeriksa": cfg["model_c"]},
            "putaran": 0, "maks": cfg["maks"], "lanjut": None, "laporan": "", "spec": None,
            "bahan": []}
    spec_lama = None
    if lanjut and conf.ID_RUN.match(str(lanjut)) and (conf.KERJA / lanjut).is_dir():
        salin_proyek(conf.KERJA / lanjut / "hasil", hasil_dir)
        spec_lama = baca_json(conf.KERJA / lanjut / "tugas.json")
        meta["lanjut"] = lanjut
    lewat = []
    if bahan and Path(bahan).is_dir():
        meta["bahan"], lewat = masukkan_bahan(Path(bahan), hasil_dir)
    yield {"t": "mulai", "id": run_id, "dir": str(folder), "maks": cfg["maks"],
           "model": meta["model"], "lanjut": meta["lanjut"]}
    if meta["bahan"] or lewat:
        yield {"t": "bahan", "nama": meta["bahan"][:60],
               "dilewati": ["%s: %s" % (n, a) for n, a in lewat[:20]]}

    pemuat = Pemuat(ctx, cfg["bongkar"])
    jejak = Jejak(folder)
    AKTIF_RUN.add(run_id)
    akhir = {}
    tulis_meta(folder, meta)       # langsung tercatat di riwayat dengan status "berjalan"
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
            tulis_meta(folder, meta)
            yield from pemuat.selesai_tahap(cfg["model_e"])
            status = yield from kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat,
                                          akhir, jejak)
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
        except OSError:
            pass
        tulis_meta(folder, meta)
    yield {"t": "selesai", "status": status, "id": run_id,
           "teks": conf.STATUS_TEKS.get(status, status), "dir": str(folder)}


def jalankan(tugas, cfg, ctx, lanjut=None, bahan=None):
    """Generator event satu proses Agent; juga mencatat log.jsonl di folder kerja
    (tanpa potongan teks per token) agar proses bisa ditinjau setelah halaman ditutup."""
    t0, log = time.time(), None
    try:
        for ev in _jalankan(tugas, cfg, ctx, lanjut, bahan):
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
