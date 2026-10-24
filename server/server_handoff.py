"""server_handoff.py - serah terima antara chat dan Agent.

Alurnya (tiap langkah atas persetujuan pengguna di halaman chat):
  1. Pengguna berdiskusi di chat; saat idenya matang, model chat menyusun BRIEF dari diskusi itu
     (ringkas_diskusi). Pengguna boleh mengubah brief sebelum menyetujuinya.
  2. serahkan(): model chat dibongkar dari memori (Pi hanya muat satu-dua model), lalu Agent mengerjakan
     brief itu di latar belakang, dengan berkas yang dilampirkan di obrolan sebagai bahan kerja.
  3. Begitu Agent selesai, hasilnya (laporan + daftar berkas yang bisa diunduh) ditulis ke obrolan
     yang sama, oleh server, jadi tersimpan walau halaman sedang ditutup. Model chat dimuat ulang
     supaya diskusi bisa dilanjutkan.
"""
import os
import threading
from pathlib import Path

import agen
import tim
from . import server_agent as agt
from . import server_chat as rwy
from . import server_config as conf
from . import server_log as lg
from . import server_model as mdl
from . import server_state as state
from . import server_unggah as ung

PROMPT_BRIEF = (
    "Kamu merangkum diskusi antara pengguna dan asisten menjadi BRIEF singkat untuk tim pembuat "
    "program (Perencana, Pelaksana, Pemeriksa). Tim hanya membaca brief ini, bukan diskusinya.\n"
    "Tulis dalam bahasa Indonesia, teks biasa (tanpa tabel, tanpa kode), maksimal 200 kata, dengan "
    "bagian berikut:\n"
    "Tujuan: satu kalimat tentang apa yang akan dibuat atau diperbaiki.\n"
    "Yang diminta: poin-poin kebutuhan yang SUDAH DISEPAKATI dalam diskusi.\n"
    "Batasan: bahasa pemrograman, pustaka, gaya, atau hal yang tidak boleh.\n"
    "Berkas yang ada: nama berkas yang dibahas (bila ada).\n"
    "Kriteria selesai: bagaimana pengguna tahu hasilnya benar.\n"
    "Aturan: hanya tulis yang benar-benar ada di diskusi; jangan menambah fitur atau asumsi; bila "
    "suatu bagian tidak dibahas tulis \"tidak disebut\"."
)
_MAKS_TRANSKRIP = 9000        # karakter diskusi yang dikirim ke model (bagian terbaru didahulukan)
_IKON = {"lolos": "✔", "belum": "⚠", "analisis": "🔎", "batal": "⏹", "error": "✖", "butuh_info": "❓"}


# ---------------------------------------------------------------- lampiran obrolan
def lampiran_dir(cid):
    """Folder tempat berkas lampiran obrolan disimpan (bahan kerja bila diserahkan ke Agent)."""
    rwy.path_chat(cid)                                  # memvalidasi id
    return conf.RIWAYAT / (cid + ".lampiran")


def lampiran_chat(cid):
    """[{nama, ukuran}] lampiran obrolan ini."""
    d = lampiran_dir(cid)
    if not d.is_dir():
        return []
    return [{"nama": rel, "ukuran": len(isi.encode("utf-8"))}
            for rel, isi in tim.baca_proyek(d, conf.MAKS_BERKAS_PAKET)]


def simpan_lampiran(cid, paket):
    """Salin berkas paket unggahan ke folder lampiran obrolan. Kembalian: jumlah berkas yang disalin."""
    sumber, tujuan = ung.ada(paket), lampiran_dir(cid)
    tujuan.mkdir(parents=True, exist_ok=True)
    n = 0
    for rel, isi in tim.baca_proyek(sumber, conf.MAKS_BERKAS_PAKET):
        ada = (tujuan / rel).exists()
        if not ada and len(tim.baca_proyek(tujuan, conf.MAKS_BERKAS_PAKET)) >= conf.MAKS_BERKAS_PAKET:
            continue
        try:
            tim.tulis_berkas(tujuan, rel, isi)
            n += 1
        except ValueError:
            continue
    return n


# ---------------------------------------------------------------- 1. ringkasan diskusi
def _transkrip(chat):
    bagian = []
    for m in chat.get("pesan", []):
        if m.get("role") == "user":
            isi = (m.get("tampil") if m.get("tampil") is not None else m.get("content")) or ""
            nama = [x.get("nama") for x in (m.get("lampiran") or []) if isinstance(x, dict)]
            bagian.append("Pengguna: " + isi.strip()[:1500] + (" [berkas terlampir: %s]" % ", ".join(nama) if nama else ""))
        elif m.get("role") == "assistant" and isinstance(m.get("content"), str) and m["content"].strip() \
                and not m.get("hasil") and not m.get("agent"):
            bagian.append("Asisten: " + m["content"].strip()[:1200])
    teks, total = [], 0
    for b in reversed(bagian):
        if total + len(b) > _MAKS_TRANSKRIP and teks:
            break
        teks.append(b)
        total += len(b)
    return "\n\n".join(reversed(teks))


def _brief_cadangan(chat):
    """Bila model gagal menyusun brief: pesan pengguna terbaru apa adanya (pengguna tetap bisa mengubahnya)."""
    user = [((m.get("tampil") if m.get("tampil") is not None else m.get("content")) or "").strip()
            for m in chat.get("pesan", []) if m.get("role") == "user"]
    user = [u for u in user if u][-3:]
    return "Tujuan: " + (user[-1][:300] if user else "-") + "\nYang diminta: " + " | ".join(u[:300] for u in user)


def ringkas_diskusi(chat, model):
    """Brief dari diskusi. Kembalian: (teks, otomatis); otomatis=False bila memakai brief cadangan."""
    body = {"model": model, "temperature": 0.2, "max_tokens": 450, "stream": False,
            "messages": [{"role": "system", "content": PROMPT_BRIEF},
                         {"role": "user", "content": "DISKUSI:\n" + _transkrip(chat)
                          + "\n\nTulis brief sesuai format."}],
            "chat_template_kwargs": {"enable_thinking": False}}
    try:
        d = agen.llama("/v1/chat/completions", body, timeout=300)
        teks = (d["choices"][0]["message"].get("content") or "").strip()
    except Exception as e:  # noqa: BLE001 - gagal meringkas bukan galat fatal
        lg.log("WARN", f"Brief otomatis gagal ({type(e).__name__}); memakai pesan pengguna")
        teks = ""
    if len(teks) < 20:
        return _brief_cadangan(chat), False
    return teks[:tim.MAKS_TUGAS], True


def hasil_terakhir(chat):
    """Hasil Agent terbaru di obrolan yang masih bisa dilanjutkan: {run, judul, status} atau None."""
    for m in reversed(chat.get("pesan", [])):
        h = m.get("hasil")
        if isinstance(h, dict) and h.get("run") and h.get("status") in ("lolos", "belum", "analisis"):
            if tim.id_valid(h["run"]) and (Path(tim.KERJA) / h["run"] / "hasil").is_dir():
                return {"run": h["run"], "judul": h.get("judul") or "", "status": h["status"]}
            return None
    return None


# ---------------------------------------------------------------- 3. hasil kembali ke obrolan
def pesan_hasil(run_id, status, tugas):
    """Pesan asisten berisi hasil proses Agent: laporan dan daftar berkas yang bisa diunduh."""
    meta = {}
    if run_id:
        try:
            meta = tim.baca_run(run_id)
        except (FileNotFoundError, OSError, ValueError):
            meta = {}
    dicantum = [b.get("nama") for b in ((meta.get("spec") or {}).get("berkas") or []) if isinstance(b, dict)]
    ada = {}
    if run_id and status != "analisis":
        for rel, isi in tim.baca_proyek(Path(tim.KERJA) / run_id / "hasil", conf.MAKS_BERKAS_PAKET):
            ada[rel] = len(isi.encode("utf-8"))
    berkas = [{"nama": n, "ukuran": ada[n]} for n in dicantum if n in ada]       # yang ditulis tim
    berkas += [{"nama": n, "ukuran": u} for n, u in ada.items() if n not in {b["nama"] for b in berkas}]
    laporan = (meta.get("laporan") or "").strip()
    teks = "%s Agent selesai: %s." % (_IKON.get(status, "•"), tim.STATUS_TEKS.get(status, status))
    if laporan:
        teks += "\n\n" + laporan[:3500]
    if berkas and status in ("lolos", "belum"):
        teks += "\n\nBerkas hasil: " + ", ".join(b["nama"] for b in berkas[:20])
    return {"role": "assistant", "content": teks,
            "hasil": {"run": run_id, "judul": meta.get("judul") or " ".join(tugas.split())[:40],
                      "status": status, "jalur": meta.get("jalur"), "putaran": meta.get("putaran"),
                      "berkas": berkas[:60] if status in ("lolos", "belum") else []}}


def _sesudah(cid, tugas, model_lama, skill_lama, muat_ulang):
    """Fungsi `sesudah` untuk agt.mulai_proses: tulis hasil ke obrolan, lalu muat ulang model chat."""
    def sesudah(status, run_id):
        def tandai(chat):                      # pesan serah terima: dari "berjalan" ke status akhir
            for m in reversed(chat.get("pesan", [])):
                if isinstance(m.get("agent"), dict) and m["agent"].get("status") == "berjalan":
                    m["agent"].update(status=status, run=run_id)
                    break
        rwy.tambah_pesan(cid, pesan_hasil(run_id, status, tugas), tandai)
        lg.log("OK", f"Hasil Agent diserahkan ke obrolan {cid} ({status})")
        if not (model_lama and muat_ulang):
            return None

        def lanjutan():
            with state.S_LOCK:
                if state.S["status"] in ("siap", "memuat"):
                    return                       # pengguna sudah memuat model sendiri
                state.S["skill"] = skill_lama
            mdl.muat_model(model_lama)
        return lanjutan
    return sesudah


# ---------------------------------------------------------------- 2. serahkan ke Agent
def serahkan(cid, tugas, cfg, muat_ulang=True, lanjut=None):
    """Serahkan brief ke Agent atas nama obrolan `cid`. Kembalian: id sesi.

    `lanjut`: id proses Agent sebelumnya yang dilanjutkan (hasilnya jadi dasar; lampiran obrolan tidak
    ditimpakan lagi supaya perbaikan sebelumnya tidak tertimpa berkas asli).
    ProsesGagal bila Agent tidak bisa mulai (model chat dimuat ulang lagi bila sudah sempat dibongkar).
    FileNotFoundError bila obrolan tidak ada."""
    rwy.baca_chat(cid)
    if state.GEN_LOCK.locked():
        raise agt.ProsesGagal(409, "Masih ada proses berjalan (model sedang menjawab atau Agent bekerja).")
    with state.S_LOCK:
        model_lama = state.S["model"] if state.S["status"] == "siap" else None
        skill_lama = state.S["skill"]
    d = lampiran_dir(cid)
    bahan = None if lanjut else (d if d.is_dir() and any(f for _, _, f in os.walk(str(d))) else None)
    if model_lama:
        mdl.bongkar_model()                     # lepaskan memori untuk model-model Agent
    ringkas = " ".join(tugas.split())
    rwy.tambah_pesan(cid, {"role": "assistant", "agent": {"status": "berjalan", "jalur": cfg.get("jalur")},
                           "content": "🏭 Diserahkan ke Agent: " + (ringkas[:160] + ("…" if len(ringkas) > 160 else ""))})
    try:
        return agt.mulai_proses(tugas, cfg, lanjut, bahan, None, cid,
                                _sesudah(cid, tugas, model_lama, skill_lama, muat_ulang))
    except Exception:
        def batalkan(chat):                     # gagal mulai: tarik kembali pesan serah terima
            if chat["pesan"] and isinstance(chat["pesan"][-1].get("agent"), dict):
                chat["pesan"].pop()
        rwy.tambah_pesan(cid, None, batalkan)
        if model_lama:
            def muat():
                with state.S_LOCK:
                    state.S["skill"] = skill_lama
                mdl.muat_model(model_lama)
            threading.Thread(target=muat, daemon=True).start()
        raise


__all__ = ["PROMPT_BRIEF", "lampiran_dir", "lampiran_chat", "simpan_lampiran", "ringkas_diskusi",
           "pesan_hasil", "hasil_terakhir", "serahkan"]
