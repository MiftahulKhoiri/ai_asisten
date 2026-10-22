"""agen_memori.py - riwayat percakapan: pemangkasan agar muat di konteks, dan peringkasan pesan lama."""
import json

from . import agen_config as cfg
from . import agen_llama as llm
from . import agen_prompt as prompt


def ukuran(pesan):
    return sum(len(json.dumps(m, ensure_ascii=False)) for m in pesan)


def siapkan(riwayat, batas, tanpa_tool=False):
    """Salinan riwayat yang dipangkas supaya muat di konteks model.
    tanpa_tool=True: buang jejak tool dari riwayat (mode chat saja)."""
    pesan = json.loads(json.dumps(riwayat))
    for m in pesan:                  # kunci tampilan web; isi lampiran sudah ada di 'content'
        m.pop("tampil", None)
        m.pop("lampiran", None)
    if tanpa_tool:
        pesan = [m for m in pesan if m.get("role") != "tool"]
        for m in pesan:
            m.pop("tool_calls", None)
        pesan = [m for m in pesan
                 if not (m.get("role") == "assistant" and not (m.get("content") or "").strip())]
    while ukuran(pesan) > batas:
        idx = [i for i, m in enumerate(pesan) if m["role"] == "user"]
        if len(idx) < 2:
            break
        del pesan[idx[0]:idx[1]]
    if ukuran(pesan) > batas:
        for m in pesan:
            if m["role"] == "tool" and len(m["content"]) > 300:
                m["content"] = m["content"][:300] + "...[dipotong]"
                if ukuran(pesan) <= batas:
                    break
    return pesan


def _transkrip(pesan):
    """Ubah pesan menjadi teks polos untuk diringkas (bagian terbaru dipertahankan)."""
    baris = []
    for m in pesan:
        peran = m.get("role")
        isi = m.get("content") or ""
        if peran == "user":
            baris.append("Pengguna: " + isi[:600])
        elif peran == "assistant":
            teks = isi[:600]
            for c in m.get("tool_calls") or []:
                fn = c.get("function") or {}
                teks += " [tool %s %s]" % (fn.get("name"), (fn.get("arguments") or "")[:150])
            baris.append("Asisten: " + teks.strip())
        elif peran == "tool":
            baris.append("Hasil tool: " + isi[:250])
    return "\n".join(baris)[-7000:]


def buat_ringkasan(lama, pesan, model):
    """Minta model meringkas (ringkasan lama + pesan baru). Kosong jika gagal."""
    isi = ""
    if lama:
        isi += "Ringkasan sebelumnya:\n" + lama + "\n\n"
    isi += ("Percakapan baru:\n" + _transkrip(pesan)
            + "\n\nTulis ringkasan gabungan yang diperbarui.")
    body = {"model": model, "temperature": 0.2, "max_tokens": 350, "stream": False,
            "messages": [{"role": "system", "content": prompt.PROMPT_RINGKAS},
                         {"role": "user", "content": isi}],
            "chat_template_kwargs": {"enable_thinking": False}}
    try:
        d = llm.llama("/v1/chat/completions", body, timeout=300)
        teks = (d["choices"][0]["message"].get("content") or "").strip()
    except Exception:  # noqa: BLE001 - gagal meringkas bukan error fatal
        return ""
    return teks[:cfg.RINGKAS_MAKS_KARAKTER]


def ringkas_bila_perlu(riwayat, model, memori, ctx):
    """Generator event. Meringkas pesan lama jika riwayat mendekati batas konteks.

    memori: dict obrolan; hasilnya disimpan di memori["ringkasan"] =
    {"teks": ..., "sampai": N} (N = jumlah pesan awal yang sudah diwakili ringkasan).
    Riwayat asli (riwayat) tidak diubah.
    """
    r = memori.get("ringkasan") or {}
    mulai = r.get("sampai", 0)
    if mulai > len(riwayat):  # riwayat berubah di luar dugaan: mulai ulang
        memori.pop("ringkasan", None)
        r, mulai = {}, 0
    batas = prompt.max_history(prompt.tools_untuk(prompt.mode_dari(ctx)))
    if ukuran(riwayat[mulai:]) + len(r.get("teks", "")) <= cfg.RINGKAS_AMBANG * batas:
        return
    idx = [i for i in range(mulai, len(riwayat)) if riwayat[i]["role"] == "user"]
    if len(idx) <= cfg.RINGKAS_SISA_GILIRAN:
        return  # tidak ada giliran lama yang bisa diringkas
    potong = idx[-cfg.RINGKAS_SISA_GILIRAN]
    gagal = memori.get("ringkas_gagal")
    if gagal is not None and len(riwayat) - gagal < 6:
        return  # baru saja gagal; jangan coba terus-menerus
    if ctx.batal.is_set():
        return
    yield {"t": "ringkas", "d": "Meringkas percakapan lama ..."}
    teks = buat_ringkasan(r.get("teks", ""), riwayat[mulai:potong], model)
    if not teks:
        memori["ringkas_gagal"] = len(riwayat)
        yield {"t": "ringkas", "d": "Gagal meringkas; riwayat lama dipangkas biasa."}
        return
    memori["ringkasan"] = {"teks": teks, "sampai": potong}
    memori.pop("ringkas_gagal", None)
    yield {"t": "ringkas",
           "d": f"Riwayat diringkas: {potong - mulai} pesan lama jadi {len(teks)} karakter."}


__all__ = ['ukuran', 'siapkan', '_transkrip', 'buat_ringkasan', 'ringkas_bila_perlu']
