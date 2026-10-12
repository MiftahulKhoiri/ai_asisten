"""registri.py - registri tool (@tool), skill, skema untuk model, dan eksekusi tool."""

import os
import re


REGISTRY = {}


def tool(nama, deskripsi, params=None, wajib=(), ringkas=None, dasar=False, web=False):
    params = params or {}
    props = {}
    for k, spec in params.items():
        p = {"type": spec[0], "description": spec[1]}
        if len(spec) > 2:
            p["enum"] = list(spec[2])
        props[k] = p
    skema_ = {"type": "function", "function": {
        "name": nama, "description": deskripsi,
        "parameters": {"type": "object", "properties": props,
                       "required": list(wajib)}}}

    def dekor(fn):
        REGISTRY[nama] = {"fn": fn, "skema": skema_, "params": params,
                          "wajib": list(wajib), "ringkas": ringkas, "dasar": dasar,
                          "web": web}
        return fn
    return dekor


def _mode_dasar():
    return os.environ.get("ASISTEN_TOOLS", "kompleks").strip().lower() == "dasar"


SKILL_IDS = ("tanpa", "web", "dasar", "kompleks", "kritis")   # urutan kanonik
SKILL_ALIAS = {"semua": "kompleks"}                          # nama lama
MODE_SKILL = SKILL_IDS


def mode_awal():
    """Skill bawaan (dari ASISTEN_TOOLS) bila web belum memilih."""
    return "dasar" if _mode_dasar() else "kompleks"


def normal_skill(nilai=None):
    """Rapikan pilihan skill (teks 'web+kritis', daftar, atau None) menjadi tuple
    berurutan kanonik. Nama tak dikenal dibuang; kosong = skill bawaan."""
    if isinstance(nilai, str):
        bagian = re.split(r"[\s,+]+", nilai.strip().lower())
    elif nilai is None:
        bagian = []
    else:
        try:
            bagian = [str(x).strip().lower() for x in nilai]
        except TypeError:
            bagian = []
    ada = {SKILL_ALIAS.get(b, b) for b in bagian} & set(SKILL_IDS)
    if not ada:
        ada = {mode_awal()}
    return tuple(i for i in SKILL_IDS if i in ada)


def nama_tool_aktif(skill=None):
    """Nama tool yang aktif untuk gabungan skill (union)."""
    s = normal_skill(skill)
    return [n for n, t in REGISTRY.items()
            if "kompleks" in s or ("dasar" in s and t["dasar"]) or ("web" in s and t["web"])]


def mode_ctx(ctx=None):
    """Skill aktif untuk ctx (atribut ctx.skill diisi asisten.py), sebagai tuple."""
    return normal_skill(getattr(ctx, "skill", None))


def skema(mode=None):
    """Daftar tool (format function calling) yang dikirim ke model."""
    return [REGISTRY[n]["skema"] for n in nama_tool_aktif(mode)]


def _koersi(tipe, nilai):
    if tipe == "integer":
        return int(float(nilai))
    if tipe == "boolean":
        if isinstance(nilai, str):
            return nilai.strip().lower() in ("true", "1", "ya", "yes", "y")
        return bool(nilai)
    return nilai if isinstance(nilai, str) else str(nilai)


def eksekusi(nama, args, ctx):
    t = REGISTRY.get(nama)
    if not t or nama not in nama_tool_aktif(mode_ctx(ctx)):
        return f"ERROR: tool tidak dikenal: {nama}"
    kw = {}
    try:
        for k, spec in t["params"].items():
            if k in args and args[k] is not None:
                kw[k] = _koersi(spec[0], args[k])
    except (ValueError, TypeError) as e:
        return f"ERROR: argumen tidak valid ({e})"
    hilang = [k for k in t["wajib"] if k not in kw]
    if hilang:
        return "ERROR: argumen wajib belum diisi: " + ", ".join(hilang)
    try:
        return str(t["fn"](ctx, **kw))
    except Exception as e:  # noqa: BLE001 - kirim error apa adanya ke model
        return f"ERROR: {type(e).__name__}: {e}"


def ringkas(nama, args):
    """Satu baris ringkasan untuk kartu tool di web."""
    t = REGISTRY.get(nama)
    try:
        if t and t["ringkas"]:
            return str(t["ringkas"](args))[:200]
    except Exception:  # noqa: BLE001
        pass
    nilai = ", ".join(str(v)[:60] for v in list(args.values())[:2])
    return f"{nama} {nilai}".strip()
