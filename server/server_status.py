"""server_status.py - isi /api/status dan /api/agent/status."""

import agen
import tim
from . import server_agent as agt
from . import server_koneksi as kon
from . import server_model as mdl
from . import server_prompt as prm
from . import server_state as state


def status_json():
    with state.S_LOCK:
        sk = state.S["skill"]
        ids = agen.tolls.SKILL_IDS
        d = {"model": state.S["model"], "status": state.S["status"], "pesan": state.S["pesan"],
             "auto": state.S["auto"], "sibuk": state.GEN_LOCK.locked(),
             "skill": list(sk) if sk else None,
             "tool_aktif": len(agen.tools_untuk(sk)) if sk else None,
             "skill_bawaan": list(agen.tolls.normal_skill(None)),
             "skills": {m: len(agen.tools_untuk(m)) for m in ids},
             "skill_tools": {m: agen.tolls.nama_tool_aktif(m) for m in ids}}
    d["prompt_mode"] = prm.mode(sk)
    # nama prompt yang dipakai sesi ini: yang menggantikan bawaan, atau yang ditambahkan ke prompt sistem skill
    d["prompt"] = prm.rakit_tambahan(state.S["prompt"])[1] if d["prompt_mode"] == "tambah" else prm.rakit(state.S["prompt"])[1]
    d["prompt_id"] = state.S["prompt"]
    d["agent"] = agt.agent_proses()       # proses Agent (juga yang diserahkan dari obrolan)
    d["model_tampil"] = mdl.nama_tampil(d["model"])    # model koneksi online diberi nama koneksinya
    if d["status"] != "siap":
        try:
            d["models"] = mdl.daftar_model()
            utama = [m for m in d["models"] if m.get("koneksi", agen.KONEKSI_UTAMA) == agen.KONEKSI_UTAMA]
            d["router"] = mdl.router_aktif(utama)
            d["belum_dikenal"] = (mdl.berkas_belum_dikenal([m["id"] for m in utama])
                                  if d["router"] else [])   # folder model lokal hanya relevan untuk router lokal
        except Exception:  # noqa: BLE001
            d["models"] = []
            d["belum_dikenal"] = []
            d["pesan"] = d["pesan"] or "Tidak bisa menghubungi llama-server"
    d["koneksi"] = kon.koneksi_ringkas()  # semua koneksi + status terakhirnya (kunci API tidak dikirim)
    return d


def agent_status():
    """Data untuk halaman Agent: daftar model dan apakah Agent boleh dijalankan sekarang."""
    d = {"models": [], "pesan": "", "folder": str(tim.KERJA),
         "langkah": {"min": tim.LANGKAH_MIN, "maks": tim.LANGKAH_MAKS,
                     "bawaan": tim.LANGKAH_BAWAAN},
         "token_tahap": tim.TOKEN_TAHAP, "uji_detik": tim.UJI_DETIK}
    try:
        d["models"] = mdl.daftar_model()
        d["router"] = mdl.router_aktif(d["models"])
    except Exception:  # noqa: BLE001
        d["pesan"] = "Tidak bisa menghubungi llama-server"
    with state.S_LOCK:
        d["chat_aktif"] = state.S["status"] in ("siap", "memuat")
        d["model_chat"] = state.S["model"] or state.S["target"]
    d["sibuk"] = state.GEN_LOCK.locked()
    d["proses"] = agt.agent_proses()
    d["koneksi"] = kon.koneksi_ringkas()
    return d


__all__ = ['status_json', 'agent_status']
