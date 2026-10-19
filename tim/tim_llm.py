"""Bicara dengan model: aliran jawaban (streaming), pengambilan JSON dari jawaban.
"""
import json
import re
import urllib.error
import urllib.request

import agen

from .tim_config import Batal


def _stream(model, pesan, batal, token, suhu=0.2, json_mode=False):
    """Generator potongan JSON dari llama-server (SSE). Diganti pada pengujian."""
    body = {"model": model, "messages": pesan, "temperature": suhu, "max_tokens": token,
            "stream": True, "chat_template_kwargs": {"enable_thinking": False}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        agen.LLAMA_URL + "/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        for mentah in r:
            if batal.is_set():
                break
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


def tanya(model, pesan, ctx, token, suhu=0.2, json_mode=False, keluar="isi"):
    """Generator event. Mengalirkan teks sebagai event `keluar`.
    Nilai akhir: (teks, terpotong)."""
    pakai_json = json_mode
    while True:
        teks, timings, selesai = "", None, None
        try:
            for ch in _stream(model, pesan, ctx.batal, token, suhu, pakai_json):
                if ch.get("timings"):
                    timings = ch["timings"]
                pil = (ch.get("choices") or [{}])[0]
                selesai = pil.get("finish_reason") or selesai
                c = (pil.get("delta") or {}).get("content")
                if c:
                    teks += c
                    yield {"t": keluar, "d": c}
            break
        except urllib.error.HTTPError as e:
            if e.code == 400 and pakai_json and not teks:
                pakai_json = False   # llama-server lama: tanpa response_format
                continue
            raise RuntimeError("Server llama %s: %s" % (
                e.code, e.read().decode(errors="replace")[:300]))
    if ctx.batal.is_set():
        raise Batal()
    info = agen._event_info(timings)
    if info:
        yield info
    return teks, selesai == "length"


def ambil_json(teks):
    """Ambil objek JSON dari jawaban model (boleh dibungkus ``` atau ada teks di sekitarnya)."""
    t = re.sub(r"<think>.*?</think>", "", teks or "", flags=re.S).strip()
    kandidat = [t]
    m = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if m:
        kandidat.append(m.group(1))
    a, z = t.find("{"), t.rfind("}")
    if a != -1 and z > a:
        kandidat.append(t[a:z + 1])
    for k in kandidat:
        try:
            d = json.loads(k.strip())
        except ValueError:
            continue
        if isinstance(d, dict):
            return d
    return None
