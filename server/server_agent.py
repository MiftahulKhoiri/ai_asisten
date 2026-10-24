"""server_agent.py - buffer event proses Agent yang berjalan di latar belakang.

Event disimpan di state.AGENT; halaman web (yang baru dibuka lagi, atau dari HP lain) membacanya
lewat long-poll /api/agent/event dan menampilkan ulang semua yang sudah terjadi.
"""

import queue
import secrets
import threading
import time

import tim
from . import server_config as conf
from . import server_ctx as kts
from . import server_log as lg
from . import server_model as mdl
from . import server_state as state
from . import server_unggah as ung


def agent_proses():
    """Ringkasan proses Agent di buffer (sedang berjalan atau yang terakhir selesai); None bila belum ada."""
    with state.AGENT_COND:
        if not state.AGENT["sesi"]:
            return None
        return {"sesi": state.AGENT["sesi"], "id": state.AGENT["id"], "tugas": state.AGENT["tugas"],
                "aktif": state.AGENT["aktif"], "status": state.AGENT["status"],
                "chat_id": state.AGENT.get("chat_id"),
                "lalu": round(time.time() - state.AGENT["mulai"], 1)}


def agent_tambah(sesi, ev):
    """Catat satu event proses Agent: ke log terminal dan ke buffer yang dibaca halaman web."""
    lg.catat_event(ev)
    if ev.get("t") == "ping":
        return
    with state.AGENT_COND:
        if state.AGENT["sesi"] != sesi:
            return
        if ev.get("t") == "mulai":
            state.AGENT["id"] = ev.get("id")
        elif ev.get("t") == "selesai":
            state.AGENT["status"] = ev.get("status")
        state.AGENT["events"].append(dict(ev, ts=round(time.time() - state.AGENT["mulai"], 1)))
        lebih = len(state.AGENT["events"]) - conf.AGENT_MAKS_EVENT
        if lebih > 0:
            del state.AGENT["events"][:lebih]
            state.AGENT["awal"] += lebih
        state.AGENT_COND.notify_all()


def _gabung_potongan(events):
    """Potongan teks beruntun (isi/token) digabung jadi satu event: jawaban lebih kecil dan cepat."""
    hasil = []
    for ev in events:
        if (hasil and ev.get("t") in ("isi", "token") and hasil[-1].get("t") == ev["t"]
                and isinstance(ev.get("d"), str) and isinstance(hasil[-1].get("d"), str)):
            hasil[-1] = dict(hasil[-1], d=hasil[-1]["d"] + ev["d"])
        else:
            hasil.append(ev)
    return hasil


def agent_baca(sesi, dari, tunggu):
    """Event proses Agent mulai nomor `dari`. Menunggu (long-poll) sampai ada event baru atau
    `tunggu` detik. None bila `sesi` bukan buffer yang sekarang (server dimulai ulang / proses baru)."""
    with state.AGENT_COND:
        if sesi != state.AGENT["sesi"]:
            return None
        mulai = max(dari, state.AGENT["awal"])
        total = lambda: state.AGENT["awal"] + len(state.AGENT["events"])    # noqa: E731
        if total() <= mulai and state.AGENT["aktif"] and tunggu > 0:
            state.AGENT_COND.wait_for(lambda: total() > mulai or not state.AGENT["aktif"] or state.AGENT["sesi"] != sesi,
                                timeout=tunggu)
            if state.AGENT["sesi"] != sesi:
                return None
            ada_baru = total() > mulai and state.AGENT["aktif"]
        else:
            ada_baru = False
    if ada_baru:
        time.sleep(0.25)        # kumpulkan beberapa potongan token dalam satu jawaban
    with state.AGENT_COND:
        if sesi != state.AGENT["sesi"]:
            return None
        mulai = max(dari, state.AGENT["awal"])
        potong = state.AGENT["events"][mulai - state.AGENT["awal"]: mulai - state.AGENT["awal"] + conf.AGENT_BATCH]
        akhir = mulai + len(potong)
        habis = (not state.AGENT["aktif"]) and akhir >= state.AGENT["awal"] + len(state.AGENT["events"])
        return {"sesi": sesi, "id": state.AGENT["id"], "aktif": state.AGENT["aktif"], "habis": habis,
                "dari": mulai, "next": akhir, "status": state.AGENT["status"],
                "lalu": round(time.time() - state.AGENT["mulai"], 1),
                "events": _gabung_potongan(potong)}


class ProsesGagal(Exception):
    """Proses Agent tidak bisa dimulai (kode HTTP + pesan untuk pengguna)."""

    def __init__(self, kode, pesan):
        super().__init__(pesan)
        self.kode, self.pesan = kode, pesan


def mulai_proses(tugas, cfg, lanjut=None, bahan=None, paket=None, chat_id=None, sesudah=None):
    """Mulai satu proses Agent (beberapa model bergiliran) di latar belakang. Kembalian: id sesi.

    `paket`: paket unggahan yang dibuang setelah dipakai. `chat_id`: obrolan asal bila diserahkan
    dari chat. `sesudah(status, run_id)`: dipanggil di thread kerja SETELAH proses selesai tetapi
    SEBELUM halaman diberi tahu bahwa proses berakhir (tempat menulis hasil ke obrolan); boleh
    mengembalikan fungsi tanpa argumen yang dijalankan setelah kunci dilepas (mis. muat ulang model).
    ProsesGagal bila model chat masih dimuat atau ada proses lain."""
    with state.S_LOCK:
        if state.S["status"] in ("siap", "memuat"):
            raise ProsesGagal(409, "Sesi chat masih memuat model. Akhiri dulu di halaman Chat "
                                   "(tombol Selesai).")
    if not state.GEN_LOCK.acquire(blocking=False):
        raise ProsesGagal(409, "Masih ada proses berjalan")
    diserahkan = False   # True setelah thread kerja berjalan: dialah yang melepas kunci
    sesi = None
    try:
        mdl.sentuh()
        lg.log("CHAT", f"agent: {tugas[:100]}")
        lg.log("INFO", f"Agent {cfg['mode']} model: perencana={cfg['model_p']}, "
                       f"pelaksana={cfg['model_e']}, pemeriksa={cfg['model_c']}, "
                       f"maks {cfg['maks']} putaran, uji jalan "
                       + ("DIIZINKAN" if cfg["uji"] else "mati")
                       + (f", dari obrolan {chat_id}" if chat_id else ""))
        ctx = kts.Ctx(queue.Queue(), threading.Event())
        ctx.skill = ("tanpa",)
        state.AKTIF["ctx"] = ctx
        with state.AGENT_COND:      # buffer baru hanya setelah kunci didapat: 409 tidak menghapus yang lama
            sesi = secrets.token_hex(4)
            state.AGENT.update(sesi=sesi, id=None, tugas=" ".join(tugas.split())[:200], events=[],
                               awal=0, aktif=True, mulai=time.time(), status=None, chat_id=chat_id)

        def kerja():
            akhir = {"id": None, "status": None}
            lanjutan = None
            try:
                for ev in tim.jalankan(tugas, cfg, ctx, lanjut, bahan):
                    agent_tambah(sesi, ev)
                    if ev.get("t") == "mulai":
                        akhir["id"] = ev.get("id")
                    elif ev.get("t") == "selesai":
                        akhir["status"] = ev.get("status")
            except Exception as e:  # noqa: BLE001
                agent_tambah(sesi, {"t": "error", "d": f"{type(e).__name__}: {e}"})
            finally:
                if paket:
                    ung.buang(paket)       # sudah disalin ke folder kerja
                if sesudah:
                    try:
                        lanjutan = sesudah(akhir["status"] or "error", akhir["id"])
                    except Exception as e:  # noqa: BLE001 - gagal menulis ke obrolan tidak boleh menahan kunci
                        lg.log("ERR", f"Gagal menyerahkan hasil ke obrolan: {type(e).__name__}: {e}")
                with state.AGENT_COND:   # kunci dilepas sebelum 'aktif' dimatikan: klien bisa langsung mulai lagi
                    state.AKTIF["ctx"] = None
                    mdl.sentuh()
                    state.GEN_LOCK.release()
                    if state.AGENT["sesi"] == sesi:
                        state.AGENT["aktif"] = False
                    state.AGENT_COND.notify_all()
            if callable(lanjutan):
                try:
                    lanjutan()
                except Exception as e:  # noqa: BLE001
                    lg.log("ERR", f"Tindak lanjut setelah Agent gagal: {type(e).__name__}: {e}")

        threading.Thread(target=kerja, daemon=True).start()
        diserahkan = True
    finally:
        if not diserahkan:
            state.AKTIF["ctx"] = None
            with state.AGENT_COND:
                if sesi and state.AGENT["sesi"] == sesi:
                    state.AGENT["aktif"] = False
            state.GEN_LOCK.release()
    return sesi


__all__ = ['agent_proses', 'agent_tambah', 'agent_baca', '_gabung_potongan']
