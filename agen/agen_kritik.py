"""agen_kritik.py - skill berpikir kritis, tahap 2: model memeriksa drafnya lalu menulis jawaban final."""
import re

from . import agen_config as cfg
from . import agen_llama as llm
from . import agen_memori as mem
from . import agen_prompt as prompt


def _bersih_final(akhir, draf):
    """Buang label seperti 'JAWABAN FINAL:' (dan draf yang disalin sebelumnya) dari hasil tahap 2."""
    t = akhir.strip()
    cocok = list(re.finditer(r"(?im)^[\W_]*jawaban\s+(?:final|akhir)\s*:[*\s]*", t))
    if cocok:
        t = t[cocok[-1].end():].strip()
    return t or draf


def _kritik(model, pesan_riwayat, batas, tools, skill, ringkasan, draf, ctx):
    """Tahap 2 skill berpikir kritis. Generator event; draf sudah tampil sebagai 'pikir'.

    Model diminta memeriksa drafnya lalu menulis jawaban final. Hasilnya ditampung dulu
    (agar label atau salinan draf bisa dibuang) lalu dikirim sekali sebagai 'token'. Kembalian: teks final (draf bila pemeriksaan gagal atau draf terlalu pendek)."""
    if len(draf.strip()) < cfg.KRITIK_MIN:
        yield {"t": "token", "d": draf}
        return draf
    yield {"t": "kritik", "d": "Memeriksa dan memperbaiki jawaban ..."}
    pesan = ([{"role": "system", "content": prompt.buat_system(ringkasan, skill)}]
             + mem.siapkan(pesan_riwayat, max(3000, batas - 3500), not tools)
             + [{"role": "assistant", "content": draf},
                {"role": "user", "content": prompt.PROMPT_KRITIK}])
    akhir, timings, selesai = "", None, None
    try:
        for ch in llm.stream_chat(model, pesan, ctx.batal, None):
            if ch.get("timings"):
                timings = ch["timings"]
            pil = (ch.get("choices") or [{}])[0]
            selesai = pil.get("finish_reason") or selesai
            d = pil.get("delta") or {}
            if d.get("reasoning_content"):
                yield {"t": "pikir", "d": d["reasoning_content"]}
            akhir += d.get("content") or ""
    except Exception:  # noqa: BLE001 - gagal memeriksa bukan error fatal: pakai draf
        pass
    if timings:
        gen = timings.get("predicted_n") or 0
        pakai = (timings.get("prompt_n") or 0) + (timings.get("cache_n") or 0) + gen
        yield {"t": "info", "tok_s": round(timings.get("predicted_per_second") or 0, 1),
               "tok": gen, "pakai": pakai, "maks": cfg.CTX_MAKS}
    akhir = _bersih_final(akhir, draf)
    if selesai == "length":
        yield {"t": "terpotong"}
        akhir += cfg.CATATAN_TERPOTONG
    yield {"t": "token", "d": akhir}
    return akhir


__all__ = ['_bersih_final', '_kritik']
