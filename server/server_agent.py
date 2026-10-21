"""server_agent.py - buffer event proses Agent yang berjalan di latar belakang.

Event disimpan di state.AGENT; halaman web (yang baru dibuka lagi, atau dari HP lain) membacanya
lewat long-poll /api/agent/event dan menampilkan ulang semua yang sudah terjadi.
"""

import time
from . import server_config as conf
from . import server_log as lg
from . import server_state as state


def agent_proses():
    """Ringkasan proses Agent di buffer (sedang berjalan atau yang terakhir selesai); None bila belum ada."""
    with state.AGENT_COND:
        if not state.AGENT["sesi"]:
            return None
        return {"sesi": state.AGENT["sesi"], "id": state.AGENT["id"], "tugas": state.AGENT["tugas"],
                "aktif": state.AGENT["aktif"], "status": state.AGENT["status"],
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


__all__ = ['agent_proses', 'agent_tambah', 'agent_baca', '_gabung_potongan']
