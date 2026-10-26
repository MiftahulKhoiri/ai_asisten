"""agen_giliran.py - loop agen (function calling): satu pesan pengguna jadi aliran event."""
import json
from datetime import datetime

from . import agen_config as cfg
from . import agen_kritik as kritik
from . import agen_llama as llm
from . import agen_memori as mem
from . import agen_prompt as prompt
from src import aksilog, tolls


# --------------------------------------------------------------------------
# Util
# --------------------------------------------------------------------------
def potong(teks, batas=cfg.MAX_OUTPUT):
    if len(teks) <= batas:
        return teks
    return teks[:batas] + f"\n...[dipotong, {len(teks) - batas} karakter lagi]"


def catat(nama, args, hasil):
    aksilog.tulis(cfg.LOG_AKSI, f"{datetime.now().isoformat(timespec='seconds')} {nama} "
                            f"{json.dumps(args, ensure_ascii=False)[:300]} -> "
                            f"{hasil[:120]!r}\n")


ringkas = tolls.ringkas


eksekusi = tolls.eksekusi  # eksekusi(nama, args, ctx) -> teks hasil


def _urut_tool_calls(calls, langkah):
    """Ubah kamus calls jadi daftar berurutan; beri id bila server tidak memberinya."""
    daftar = []
    for i in sorted(calls):
        c = calls[i]
        if not c["id"]:
            c["id"] = f"call_{langkah}_{i}"
        daftar.append(c)
    return daftar


def _luar(nama):
    """True bila tool mengambil teks dari luar (web) yang tidak dipercaya."""
    return bool(tolls.REGISTRY.get(nama, {}).get("luar"))


def _riwayat_tercemar(riwayat):
    """True bila obrolan ini memuat isi dari luar: hasil tool sumber luar (web) atau berkas
    unggahan pengguna (isinya bisa berisi instruksi tersembunyi). Sesudah itu aksi pengubah
    selalu minta izin, juga di mode AUTO."""
    return any(m.get("lampiran") or any(_luar((c.get("function") or {}).get("name"))
                                        for c in (m.get("tool_calls") or []))
               for m in riwayat)


def _jalankan_tool_calls(daftar, riwayat, ctx, sudah, terpotong=False):
    """Jalankan tiap tool call: kirim event tool/hasil, lalu catat hasilnya di riwayat.

    `sudah` berisi kunci tool+argumen yang pernah dijalankan (anti-loop). `terpotong`: putaran
    ini berhenti karena batas token, jadi argumen yang tidak valid berarti terpotong.
    Memakai tool sumber luar menandai ctx.tercemar: sesudah itu aksi pengubah selalu minta
    izin walau mode AUTO (lindungan terhadap prompt injection dari halaman web).
    """
    for c in daftar:
        nama = c["function"]["name"]
        try:
            args = json.loads(c["function"]["arguments"] or "{}")
        except json.JSONDecodeError:
            args = None
        ring = ringkas(nama, args) if isinstance(args, dict) else nama
        yield {"t": "tool", "id": c["id"], "nama": nama, "ringkas": ring}
        if ctx.batal.is_set():
            hasil = "DIBATALKAN oleh pengguna."
        elif not isinstance(args, dict):
            hasil = cfg.PESAN_TOOL_TERPOTONG if terpotong else "ERROR: argumen bukan JSON object yang valid."
        else:
            kunci = nama + json.dumps(args, sort_keys=True, ensure_ascii=False)
            if kunci in sudah:
                hasil = ("Tool dengan argumen yang sama sudah dijalankan, hasilnya "
                         "ada di atas. Jangan ulangi; berikan jawaban akhir sekarang.")
            else:
                sudah.add(kunci)
                hasil = eksekusi(nama, args, ctx)
                if _luar(nama):
                    ctx.tercemar = True
        hasil = potong(hasil)
        catat(nama, args if isinstance(args, dict) else {}, hasil)
        yield {"t": "hasil", "id": c["id"], "d": hasil}
        riwayat.append({"role": "tool", "tool_call_id": c["id"], "content": hasil})


def giliran(riwayat, model, ctx, memori=None):
    """Generator event untuk satu pesan pengguna.

    riwayat: daftar pesan (tanpa system), diubah di tempat.
    ctx: .auto, .batal (threading.Event), .konfirmasi(jenis, ringkas, detail)
    memori: dict obrolan (opsional); jika diberikan, pesan lama diringkas otomatis
            dan ringkasannya disimpan di memori["ringkasan"].
    Event: ringkas, kritik, pikir, token, info, tool, hasil, error, batal, batas, selesai,
    terpotong (jawaban/tool terpotong batas token).
    """
    if memori is not None:
        yield from mem.ringkas_bila_perlu(riwayat, model, memori, ctx)
    sudah = set()  # tool+argumen yang sudah dijalankan (anti-loop)
    teks_user = next((m.get("content") or "" for m in reversed(riwayat)
                      if m.get("role") == "user"), "")
    skill = prompt.mode_dari(ctx)
    tools = prompt.tools_untuk(skill)
    kritis = "kritis" in skill
    batas = prompt.max_history(tools)
    tool_aktif = bool(tools) and prompt.perlu_tool(teks_user, riwayat, skill)
    if _riwayat_tercemar(riwayat):   # tool web sudah dipakai di obrolan ini
        ctx.tercemar = True
    for langkah in range(cfg.MAX_STEPS):
        if ctx.batal.is_set():
            yield {"t": "batal"}
            return
        r = (memori or {}).get("ringkasan") or {}
        mulai = min(r.get("sampai", 0), len(riwayat))
        ringk = r.get("teks", "")
        sistem = prompt.buat_system(ringk, skill, prompt.dasar_dari(ctx))
        kirim = ([{"role": "system", "content": sistem}] if sistem.strip() else []) \
            + mem.siapkan(riwayat[mulai:], batas, not tools)

        putaran = yield from llm._baca_stream(model, kirim, ctx,
                                              tools if tool_aktif else None, kritis)
        if putaran is None:       # error sudah dilaporkan
            return
        teks, calls, timings, selesai = putaran
        terpotong = selesai == "length"
        info = llm._event_info(timings)
        if info:
            yield info

        daftar = _urut_tool_calls(calls, langkah)
        entri = {"role": "assistant", "content": teks}
        if daftar:
            entri["tool_calls"] = daftar
        elif kritis and teks.strip() and not ctx.batal.is_set():
            entri["content"] = yield from kritik._kritik(
                model, riwayat[mulai:], batas, tools, skill, ringk, teks, ctx)
        elif terpotong and teks.strip():
            yield {"t": "terpotong"}
            yield {"t": "token", "d": cfg.CATATAN_TERPOTONG}
            entri["content"] = teks + cfg.CATATAN_TERPOTONG
        if entri["content"] or daftar:
            riwayat.append(entri)

        if not daftar:
            if ctx.batal.is_set():
                yield {"t": "batal"}
            else:
                if not teks:
                    yield {"t": "error", "d": "Model tidak memberi jawaban."}
                yield {"t": "selesai"}
            return

        if terpotong:
            yield {"t": "terpotong"}
        yield from _jalankan_tool_calls(daftar, riwayat, ctx, sudah, terpotong)

        if ctx.batal.is_set():
            yield {"t": "batal"}
            return
    yield {"t": "batas"}


__all__ = ['potong', 'catat', 'ringkas', 'eksekusi', '_urut_tool_calls', '_luar', '_riwayat_tercemar', '_jalankan_tool_calls', 'giliran']
