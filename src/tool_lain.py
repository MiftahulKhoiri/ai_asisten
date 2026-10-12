"""tool_lain.py - tool kecil (kalkulator, waktu). Tempat termudah untuk tool baru."""

import ast
import math
import operator
from datetime import datetime

from .registri import tool


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow}
_FUNGSI = {"sqrt": math.sqrt, "abs": abs, "round": round, "min": min, "max": max,
           "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log,
           "log10": math.log10, "exp": math.exp, "floor": math.floor, "ceil": math.ceil}
_KONSTAN = {"pi": math.pi, "e": math.e}


def _hitung(n):
    if isinstance(n, ast.Expression):
        return _hitung(n.body)
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) \
            and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
        a, b = _hitung(n.left), _hitung(n.right)
        if isinstance(n.op, ast.Pow):
            if abs(b) > 1000 or (isinstance(a, int) and isinstance(b, int)
                                 and b > 0 and a.bit_length() * b > 20000):
                raise ValueError("pangkat terlalu besar")
        return _OPS[type(n.op)](a, b)
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.UAdd, ast.USub)):
        v = _hitung(n.operand)
        return v if isinstance(n.op, ast.UAdd) else -v
    if isinstance(n, ast.Name) and n.id in _KONSTAN:
        return _KONSTAN[n.id]
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
            and n.func.id in _FUNGSI and not n.keywords:
        return _FUNGSI[n.func.id](*[_hitung(a) for a in n.args])
    raise ValueError("ekspresi tidak didukung")


@tool("hitung", "Hitung ekspresi matematika (+ - * / // % ** sqrt abs round min max sin cos tan "
      "log exp floor ceil pi e).",
      {"ekspresi": ("string", "mis. (12.5*8)/3")}, wajib=["ekspresi"],
      ringkas=lambda a: f"hitung {a.get('ekspresi', '')}")
def hitung(ctx, ekspresi):
    if len(ekspresi) > 200:
        return "ERROR: ekspresi terlalu panjang."
    try:
        hasil = _hitung(ast.parse(ekspresi.strip().replace("^", "**"), mode="eval"))
    except ZeroDivisionError:
        return "ERROR: pembagian dengan nol."
    except (SyntaxError, ValueError, OverflowError, TypeError) as e:
        return f"ERROR: tidak bisa dihitung ({e})"
    return f"{ekspresi.strip()} = " + (str(hasil) if isinstance(hasil, int) else format(hasil, ".12g"))


_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


@tool("waktu_sekarang", "Tanggal, jam, dan zona waktu Pi saat ini.",
      web=True, ringkas=lambda a: "waktu sekarang")
def waktu_sekarang(ctx):
    n = datetime.now().astimezone()
    return f"{_HARI[n.weekday()]}, {n:%Y-%m-%d %H:%M:%S} ({n.tzname()}, UTC{n:%z})"
