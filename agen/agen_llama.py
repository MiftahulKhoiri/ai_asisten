"""agen_llama.py - klien llama-server: permintaan biasa, stream SSE, dan pembaca jawaban satu putaran."""
import json
import urllib.error
import urllib.request

from . import agen_config as cfg


def llama(path, data=None, timeout=300):
    req = urllib.request.Request(
        cfg.LLAMA_URL + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def stream_chat(model, pesan, batal, tools=None):
    """Generator potongan JSON dari llama-server (stream SSE)."""
    body = {"model": model, "messages": pesan, "temperature": 0.3,
            "max_tokens": cfg.MAX_TOKENS, "stream": True,
            "chat_template_kwargs": {"enable_thinking": False}}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    req = urllib.request.Request(
        cfg.LLAMA_URL + "/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        for mentah in r:
            if batal.is_set():
                break  # keluar dari 'with' menutup koneksi dan menghentikan generasi
            baris = mentah.decode("utf-8", "replace").strip()
            if not baris.startswith("data:"):
                continue
            isi = baris[5:].strip()
            if isi == "[DONE]":
                break
            try:
                yield json.loads(isi)
            except json.JSONDecodeError:
                continue


def _gabung_tool_call(calls, tc):
    """Gabungkan satu potongan tool_call dari stream ke kamus `calls` (kunci: index)."""
    i = tc.get("index", 0)
    s = calls.setdefault(i, {"id": "", "type": "function",
                             "function": {"name": "", "arguments": ""}})
    if tc.get("id"):
        s["id"] = tc["id"]
    f = tc.get("function") or {}
    if f.get("name"):
        s["function"]["name"] = f["name"]
    if f.get("arguments"):
        s["function"]["arguments"] += f["arguments"]


def _baca_stream(model, kirim, ctx, tools, kritis):
    """Baca satu putaran jawaban model dari stream.

    Menghasilkan event pikir/token. Nilai akhir (lewat `yield from`) adalah
    (teks, calls, timings, selesai), atau None bila terjadi error (event error sudah dikirim).
    `selesai` adalah finish_reason dari llama-server; "length" = jawaban terpotong batas token.
    """
    teks, calls, timings, selesai = "", {}, None, None
    try:
        for ch in stream_chat(model, kirim, ctx.batal, tools):
            if ch.get("timings"):
                timings = ch["timings"]
            pil = (ch.get("choices") or [{}])[0]
            selesai = pil.get("finish_reason") or selesai
            d = pil.get("delta") or {}
            pikir = d.get("reasoning_content")
            if pikir:
                yield {"t": "pikir", "d": pikir}
            c = d.get("content")
            if c:
                teks += c
                # skill kritis: tahap pertama = draf, tampil sebagai "berpikir"
                yield {"t": "pikir" if kritis else "token", "d": c}
            for tc in d.get("tool_calls") or []:
                _gabung_tool_call(calls, tc)
    except urllib.error.HTTPError as e:
        yield {"t": "error",
               "d": f"Server llama {e.code}: {e.read().decode(errors='replace')[:300]}"}
        return None
    except Exception as e:  # noqa: BLE001
        yield {"t": "error", "d": f"{type(e).__name__}: {e}"}
        return None
    return teks, calls, timings, selesai


def _event_info(timings):
    """Event 'info' (kecepatan dan pemakaian konteks) dari timings server, atau None."""
    if not timings:
        return None
    gen = timings.get("predicted_n") or 0
    pakai = (timings.get("prompt_n") or 0) + (timings.get("cache_n") or 0) + gen
    return {"t": "info", "tok_s": round(timings.get("predicted_per_second") or 0, 1),
            "tok": gen, "pakai": pakai, "maks": cfg.CTX_MAKS}


__all__ = ['llama', 'stream_chat', '_gabung_tool_call', '_baca_stream', '_event_info']
