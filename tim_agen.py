#!/usr/bin/env python3
"""tim_agen.py - Agent tim model: beberapa model lokal bekerja bergiliran.

Dipakai oleh asisten.py (halaman web web/agent.html). Hanya library standar Python.

Peran (2 model: Perencana = Pemeriksa = model 1, Pelaksana = model 2;
       3 model: tiap peran punya model sendiri):

  Perencana  menerima perintah pengguna, menyusun "lembar tugas" (tugas.json + tugas.md)
             dan, di akhir, menjelaskan hasilnya kepada pengguna.
  Pelaksana  membaca lembar tugas lalu menulis program ke folder hasil/.
  Pemeriksa  memeriksa hasilnya. Lolos -> selesai; belum -> koreksi dikirim balik ke
             Pelaksana. Batas putaran ditentukan pengguna.

Pemeriksaan tidak hanya mengandalkan model: orkestrator (kode ini, bukan model) selalu
menjalankan pemeriksaan otomatis dulu (sintaks Python/JSON/JS/Bash, berkas yang diminta ada,
dan uji jalan bila pengguna mengizinkan). Bila pemeriksaan otomatis gagal, hasilnya langsung
dikembalikan ke Pelaksana tanpa memuat model Pemeriksa (hemat waktu muat model di Pi).

Memori: model dimuat satu per satu lewat llama-server mode router (/models/load dan
/models/unload). Dengan "bongkar tiap tahap", model dibongkar begitu tahapnya selesai,
kecuali tahap berikutnya memakai model yang sama.

Folder kerja (ASISTEN_AGENT_DIR, bawaan ~/agent_kerja/<id>/):
  tugas.json, tugas.md   lembar tugas dari Perencana
  hasil/                 program buatan Pelaksana
  koreksi_N.md           masukan untuk putaran berikutnya
  laporan.md, run.json   penjelasan akhir dan ringkasan proses

Variabel lingkungan (opsional):
  ASISTEN_AGENT_DIR      folder kerja agent
  ASISTEN_AGENT_TOKENS   batas token tulis kode per tahap (bawaan 3000)
  ASISTEN_AGENT_UJI_DTK  batas waktu uji jalan program (bawaan 20 detik)
"""
import ast
import json
import os
import re
import secrets
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import agen
from src.util import _ekor_teks, _run  # noqa: E402 - agen.py sudah menambah folder proyek ke sys.path

KERJA = Path(os.environ.get("ASISTEN_AGENT_DIR", str(Path.home() / "agent_kerja")))
TOKEN_TAHAP = agen._env_int("ASISTEN_AGENT_TOKENS", 3000, 256)   # tahap Pelaksana (menulis kode)
TOKEN_RENCANA = 1000
TOKEN_PERIKSA = 800
TOKEN_JELAS = 800
UJI_DETIK = agen._env_int("ASISTEN_AGENT_UJI_DTK", 20, 2)
LANGKAH_MIN, LANGKAH_MAKS, LANGKAH_BAWAAN = 1, 10, 3
MAKS_BERKAS_RENCANA = 5     # berkas per lembar tugas
MAKS_BERKAS_TOTAL = 12      # berkas per proyek
MAKS_UKURAN = 200_000       # byte per berkas
MAKS_TUGAS = 4000           # karakter perintah pengguna
BATAS_MUAT = 300            # detik menunggu satu model siap
EKSTENSI = {".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".sh", ".c", ".cpp",
            ".h", ".hpp", ".ini", ".toml", ".yaml", ".yml", ".csv", ".cfg"}
INTERPRETER = {"python3", "python", "node"}
ID_RUN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
PERAN = {"rencana": "Perencana", "tulis": "Pelaksana", "periksa": "Pemeriksa",
         "jelaskan": "Penjelas"}
STATUS_TEKS = {"lolos": "lolos pemeriksaan",
               "belum": "belum sempurna (batas putaran tercapai)",
               "butuh_info": "menunggu info tambahan dari pengguna",
               "batal": "dibatalkan", "error": "berhenti karena error"}

_TIDUR = time.sleep          # diganti pada pengujian
DIMUAT = set()               # model yang dimuat oleh Agent (dibongkar saat aplikasi ditutup)


class Batal(Exception):
    """Pengguna menekan Stop."""


# --------------------------------------------------------------------------
# Prompt per peran
# --------------------------------------------------------------------------
SYSTEM_PERENCANA = (
    "Kamu PERENCANA dalam tim pembuat program. Tugasmu mengubah permintaan pengguna menjadi "
    "lembar tugas untuk PELAKSANA (model lain yang menulis kode). Kamu TIDAK menulis kode.\n"
    "Balas HANYA dengan satu objek JSON, tanpa teks lain, dengan kunci:\n"
    '- "judul": judul singkat (maksimal 6 kata)\n'
    '- "ringkasan": 1-2 kalimat tentang apa yang harus dibuat\n'
    '- "bahasa": python, javascript, html, bash, atau lainnya\n'
    '- "berkas": daftar {"nama": "main.py", "fungsi": "tugas berkas ini"}; maksimal 5 berkas, '
    "nama sederhana tanpa spasi\n"
    '- "langkah": daftar langkah pengerjaan yang singkat\n'
    '- "kriteria": daftar syarat selesai yang bisa diperiksa (maksimal 5)\n'
    '- "jalankan": perintah uji berupa daftar, mis. ["python3", "main.py"]. Kosongkan [] bila '
    "programnya interaktif, butuh internet, atau berupa tampilan/GUI/web. Program yang diuji "
    "harus selesai sendiri dalam beberapa detik tanpa input keyboard (pakai data contoh bawaan).\n"
    '- "catatan": asumsi yang kamu ambil\n'
    '- "tanya": isi HANYA bila permintaan benar-benar tidak bisa dikerjakan tanpa info tambahan '
    '(satu pertanyaan singkat) dan biarkan "berkas" kosong. Selain itu isi "" dan buat asumsi '
    "sendiri.\n"
    "Pilih rancangan paling sederhana yang memenuhi permintaan. Utamakan library standar.")

SYSTEM_PELAKSANA = (
    "Kamu PELAKSANA dalam tim pembuat program. Tulis kode sesuai lembar tugas dari PERENCANA.\n"
    "Format keluaran WAJIB, untuk setiap berkas:\n"
    "=== FILE: nama_berkas ===\n"
    "(isi LENGKAP berkas)\n"
    "=== END ===\n"
    "Aturan:\n"
    "1. Tulis isi berkas LENGKAP dan siap jalan, bukan potongan, juga saat hanya memperbaiki "
    "satu bagian.\n"
    "2. Jangan memakai pagar ``` dan jangan menulis penjelasan di luar blok berkas.\n"
    "3. Tulis berkas yang tercantum di lembar tugas; berkas lain hanya bila benar-benar perlu.\n"
    "4. Bila lembar tugas punya perintah \"jalankan\", program harus selesai sendiri tanpa "
    "meminta input keyboard.\n"
    "5. Bila ada KOREKSI, perbaiki semua masalah yang disebut di dalamnya.\n"
    "6. Utamakan library standar; jangan menginstal paket.")

SYSTEM_PEMERIKSA = (
    "Kamu PEMERIKSA dalam tim pembuat program. Periksa berkas buatan PELAKSANA terhadap "
    "lembar tugas dan hasil pemeriksaan otomatis.\n"
    "Balas HANYA dengan satu objek JSON:\n"
    '{"ok": true atau false, "ringkas": "satu kalimat penilaian", '
    '"masalah": ["berkas:baris - uraian bug nyata"], '
    '"perbaikan": "instruksi konkret untuk pelaksana"}\n'
    "Aturan:\n"
    "1. ok=true bila semua kriteria utama terpenuhi dan tidak ada bug nyata.\n"
    "2. ok=false bila ada kriteria yang tidak terpenuhi, logika salah, atau uji otomatis gagal.\n"
    "3. Jangan menuntut gaya penulisan, fitur tambahan, atau hal di luar kriteria. "
    "Jangan mengarang masalah.\n"
    "4. Sebut masalah dengan nama berkas dan nomor baris bila bisa; maksimal 5 masalah.")

SYSTEM_PENJELAS = (
    "Kamu PENJELAS: wajah tim bagi pengguna. Jelaskan hasil kerja tim dalam bahasa Indonesia "
    "yang ramah dan ringkas (sekitar 10 baris), dengan bagian:\n"
    "**Hasil**: apa yang dibuat.\n"
    "**Berkas**: nama berkas dan fungsinya.\n"
    "**Cara menjalankan**: perintah singkat dalam `kode`.\n"
    "**Pemeriksaan**: lolos atau belum, jujur sesuai data. Jangan mengaku sudah diuji jalan "
    "bila uji jalan dilewati.\n"
    "**Catatan**: masalah yang tersisa atau saran lanjutan, bila ada.\n"
    "Pakai hanya data yang diberikan; jangan mengarang.")


# --------------------------------------------------------------------------
# Model: muat dan bongkar (llama-server mode router)
# --------------------------------------------------------------------------
def status_model(nama):
    """'loaded' / 'loading' / 'unloaded' / 'failed', atau None bila model tidak ada."""
    for m in agen.llama("/v1/models", timeout=10)["data"]:
        if m["id"] == nama:
            return (m.get("status") or {}).get("value") or "unloaded"
    return None


def bongkar(nama):
    try:
        agen.llama("/models/unload", {"model": nama}, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code != 400:   # 400 = model memang tidak berjalan
            raise
    DIMUAT.discard(nama)


def bongkar_sisa():
    """Bongkar semua model yang dimuat Agent (dipanggil saat aplikasi ditutup)."""
    hasil = []
    for nama in list(DIMUAT):
        try:
            bongkar(nama)
            hasil.append(nama)
        except Exception:  # noqa: BLE001
            pass
    return hasil


def muat(nama, ctx):
    """Generator event. Nilai akhir: True bila model dimuat oleh kita (boleh dibongkar)."""
    st = status_model(nama)
    if st is None:
        raise RuntimeError("Model tidak ditemukan di llama-server: " + nama)
    if st == "loaded":
        return nama in DIMUAT
    mulai = time.time()
    if st != "loading":
        agen.llama("/models/load", {"model": nama}, timeout=30)
    DIMUAT.add(nama)
    yield {"t": "muat", "model": nama, "d": "Memuat %s ..." % nama}
    try:
        while True:
            _TIDUR(2)
            if ctx.batal.is_set():
                raise Batal()
            st = status_model(nama)
            detik = int(time.time() - mulai)
            if st == "loaded":
                break
            if st == "failed":
                raise RuntimeError("llama-server gagal memuat " + nama)
            if detik > BATAS_MUAT:
                raise RuntimeError("%s belum siap setelah %d detik" % (nama, BATAS_MUAT))
            yield {"t": "muat", "model": nama, "d": "Memuat %s ... %d dtk" % (nama, detik)}
    except BaseException:
        try:
            bongkar(nama)
        except Exception:  # noqa: BLE001
            pass
        raise
    yield {"t": "muat_selesai", "model": nama, "detik": int(time.time() - mulai)}
    return True


class Pemuat:
    """Mengatur model mana yang sedang termuat selama satu proses Agent."""

    def __init__(self, ctx, bongkar_tiap):
        self.ctx = ctx
        self.bongkar_tiap = bongkar_tiap
        self.milik = {}      # nama -> True bila kita yang memuat (boleh dibongkar)

    def pakai(self, nama):
        if nama not in self.milik:
            self.milik[nama] = yield from muat(nama, self.ctx)

    def lepas(self, nama):
        if self.milik.pop(nama, False):
            bongkar(nama)
            yield {"t": "bongkar", "model": nama}

    def selesai_tahap(self, berikutnya=None):
        """Bongkar model yang sudah tidak dipakai (kecuali yang dipakai tahap berikutnya)."""
        if not self.bongkar_tiap:
            return
        for nama in list(self.milik):
            if nama != berikutnya:
                yield from self.lepas(nama)

    def lepas_semua(self):
        for nama in list(self.milik):
            yield from self.lepas(nama)

    def lepas_diam(self):
        """Jaring pengaman (tanpa event): dipanggil di 'finally'."""
        for nama in list(self.milik):
            try:
                if self.milik.pop(nama):
                    bongkar(nama)
            except Exception:  # noqa: BLE001
                pass


# --------------------------------------------------------------------------
# Bicara dengan model
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Berkas: nama aman, tulis, baca, urai keluaran model
# --------------------------------------------------------------------------
_BAGIAN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,60}$")


def aman_nama(nama):
    """Nama berkas relatif yang aman (maks 3 tingkat, tanpa titik di depan, ekstensi dikenal)."""
    n = str(nama or "").strip().replace("\\", "/")
    while n.startswith("./"):
        n = n[2:]
    bagian = n.split("/")
    if (not n or len(n) > 80 or len(bagian) > 3
            or any(not _BAGIAN.match(b) or b in (".", "..") for b in bagian)):
        raise ValueError("nama berkas tidak aman: %r" % (nama,))
    if Path(n).suffix.lower() not in EKSTENSI:
        raise ValueError("jenis berkas tidak diizinkan: %s" % n)
    return n


def tulis_berkas(hasil_dir, nama, isi):
    nama = aman_nama(nama)
    if len(isi.encode("utf-8")) > MAKS_UKURAN:
        raise ValueError("%s terlalu besar (maks %d KB)" % (nama, MAKS_UKURAN // 1000))
    akar = os.path.realpath(str(hasil_dir))
    p = Path(hasil_dir) / nama
    induk = os.path.realpath(str(p.parent))
    if induk != akar and not induk.startswith(akar + os.sep):
        raise ValueError("jalur di luar folder hasil: " + nama)
    if p.is_symlink():
        raise ValueError("berkas berupa symlink: " + nama)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(isi, encoding="utf-8")
    return nama


def baca_proyek(hasil_dir, maks=30):
    """[(nama, isi)] semua berkas teks di folder hasil (tanpa symlink)."""
    hasil, akar = [], Path(hasil_dir)
    if not akar.is_dir():
        return hasil
    for d, subs, files in os.walk(str(akar)):
        subs[:] = sorted(s for s in subs if not s.startswith(".") and s != "__pycache__")
        for f in sorted(files):
            p = Path(d) / f
            rel = p.relative_to(akar).as_posix()
            try:
                aman_nama(rel)
                if p.is_symlink() or p.stat().st_size > MAKS_UKURAN:
                    continue
                hasil.append((rel, p.read_text(encoding="utf-8", errors="replace")))
            except (ValueError, OSError):
                continue
            if len(hasil) >= maks:
                return hasil
    return hasil


def salin_proyek(sumber, tujuan):
    """Salin berkas proyek lama (untuk melanjutkan). Symlink dan berkas tak dikenal dilewati."""
    n = 0
    for rel, isi in baca_proyek(sumber, MAKS_BERKAS_TOTAL * 3):
        try:
            tulis_berkas(tujuan, rel, isi)
            n += 1
        except ValueError:
            continue
    return n


_HEAD = re.compile(r"^[ \t]*=+ *FILE: *(.+?) *=+ *$", re.M)
_END = re.compile(r"^[ \t]*=+ *END(?: FILE)? *=+ *$", re.M)
_PAGAR = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.S)
_NAMA_DI_BARIS = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,5})")


def _buka_pagar(isi):
    m = re.fullmatch(r"\s*```[\w+-]*[ \t]*\n(.*?)\n?```\s*", isi, re.S)
    return m.group(1) if m else isi


def _rapi(isi):
    isi = _buka_pagar(isi.replace("\r\n", "\n")).strip("\n")
    return isi + "\n" if isi else ""


def urai_berkas(teks, nama_spec=()):
    """Urai keluaran Pelaksana menjadi [(nama, isi, lengkap)].

    Format utama:  === FILE: nama ===  ...  === END ===
    `lengkap` False bila blok tidak ditutup (keluaran terpotong batas token).
    Cadangan: blok ``` dengan nama berkas di baris sebelumnya, atau satu blok ``` untuk
    lembar tugas yang hanya berisi satu berkas.
    """
    teks = teks or ""
    kepala = list(_HEAD.finditer(teks))
    hasil = []
    for i, h in enumerate(kepala):
        batas = kepala[i + 1].start() if i + 1 < len(kepala) else len(teks)
        potongan = teks[h.end():batas]
        e = _END.search(potongan)
        nama = h.group(1).strip("`'\"* ")
        if e:
            hasil.append((nama, _rapi(potongan[:e.start()]), True))
        else:
            hasil.append((nama, _rapi(potongan), i + 1 < len(kepala)))
    if hasil:
        return hasil
    blok = list(_PAGAR.finditer(teks))
    if len(blok) == 1 and len(nama_spec) == 1:
        return [(nama_spec[0], _rapi(blok[0].group(1)), True)]
    pos = 0
    for b in blok:
        sebelum = teks[pos:b.start()].strip().splitlines()
        pos = b.end()
        nama = None
        for baris in reversed(sebelum[-2:]):
            for kand in _NAMA_DI_BARIS.findall(baris):
                try:
                    nama = aman_nama(kand)
                    break
                except ValueError:
                    continue
            if nama:
                break
        if nama:
            hasil.append((nama, _rapi(b.group(1)), True))
    return hasil


def blok_berkas(berkas, anggaran, nomor=False):
    """Teks berkas untuk prompt, dipotong rata bila melebihi anggaran karakter."""
    if not berkas:
        return "(belum ada berkas)"
    per = max(500, anggaran // len(berkas))
    bagian = []
    for nama, isi in berkas:
        teks = isi
        if nomor:
            teks = "\n".join("%d: %s" % (i, b) for i, b in enumerate(isi.splitlines(), 1))
        if len(teks) > per:
            teks = teks[:per] + "\n...[dipotong]"
        bagian.append("--- %s ---\n%s" % (nama, teks))
    return "\n".join(bagian)


def anggaran_prompt(token_keluar):
    """Karakter yang aman untuk isi prompt, menurut konteks model (ASISTEN_CTX)."""
    return max(3000, (agen.CTX_MAKS - token_keluar - 900) * 3)


# --------------------------------------------------------------------------
# Lembar tugas
# --------------------------------------------------------------------------
def _daftar_teks(v, maks, panjang=300):
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    hasil = []
    for x in v:
        s = " ".join(str(x).split())[:panjang]
        if s:
            hasil.append(s)
        if len(hasil) >= maks:
            break
    return hasil


def _rapikan_jalankan(v, nama_berkas):
    """Perintah uji hanya: python3/node + berkas dari lembar tugas + argumen sederhana."""
    if isinstance(v, str):
        v = v.split()
    if not isinstance(v, list) or not 2 <= len(v) <= 6:
        return []
    v = [str(x) for x in v]
    if v[0] not in INTERPRETER or v[1] not in nama_berkas:
        return []
    if any(not re.fullmatch(r"[\w./=:,+-]{1,60}", a) for a in v[2:]):
        return []
    if v[0] == "python":
        v[0] = "python3"
    return v


def rapikan_spec(raw, tugas):
    """Lembar tugas yang sudah divalidasi dari JSON mentah buatan Perencana."""
    raw = raw if isinstance(raw, dict) else {}
    berkas = []
    for b in raw.get("berkas") or []:
        if isinstance(b, str):
            b = {"nama": b}
        if not isinstance(b, dict):
            continue
        try:
            nama = aman_nama(b.get("nama"))
        except ValueError:
            continue
        if any(x["nama"] == nama for x in berkas):
            continue
        berkas.append({"nama": nama, "fungsi": " ".join(str(b.get("fungsi") or "").split())[:300]})
        if len(berkas) >= MAKS_BERKAS_RENCANA:
            break
    if not berkas:
        berkas = [{"nama": "main.py", "fungsi": " ".join(tugas.split())[:300]}]
    judul = " ".join(str(raw.get("judul") or "").split())[:60] or " ".join(tugas.split())[:40]
    return {
        "judul": judul,
        "ringkasan": " ".join(str(raw.get("ringkasan") or tugas).split())[:500],
        "bahasa": " ".join(str(raw.get("bahasa") or "python").split())[:20].lower(),
        "berkas": berkas,
        "langkah": _daftar_teks(raw.get("langkah"), 10),
        "kriteria": (_daftar_teks(raw.get("kriteria"), 6)
                     or ["Program memenuhi permintaan pengguna.", "Tidak ada error saat dijalankan."]),
        "jalankan": _rapikan_jalankan(raw.get("jalankan"), [b["nama"] for b in berkas]),
        "catatan": " ".join(str(raw.get("catatan") or "").split())[:400],
    }


def spec_ke_md(spec):
    baris = ["# " + spec["judul"], "", spec["ringkasan"], "", "## Berkas"]
    baris += ["- `%s`: %s" % (b["nama"], b["fungsi"]) for b in spec["berkas"]]
    if spec["langkah"]:
        baris += ["", "## Langkah"] + ["%d. %s" % (i, s) for i, s in enumerate(spec["langkah"], 1)]
    baris += ["", "## Kriteria selesai"] + ["- " + k for k in spec["kriteria"]]
    baris += ["", "## Uji jalan", "`" + " ".join(spec["jalankan"]) + "`" if spec["jalankan"]
              else "(tidak ada)"]
    if spec["catatan"]:
        baris += ["", "## Catatan", spec["catatan"]]
    return "\n".join(baris) + "\n"


def _baca_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# Pemeriksaan otomatis (kode, bukan model)
# --------------------------------------------------------------------------
def cek_statis(hasil_dir, spec, ekstra=()):
    """Kembalian: (ok, baris). Berkas diminta ada, tidak kosong, dan sintaksnya benar.
    `ekstra`: nama berkas lain yang ditulis Pelaksana (ikut diperiksa sintaksnya)."""
    baris, ok = [], True
    daftar = [b["nama"] for b in spec["berkas"]]
    daftar += [n for n in ekstra if n not in daftar]
    for nama in daftar:
        p = Path(hasil_dir) / nama
        if not p.is_file():
            baris.append("GAGAL %s: berkas belum dibuat" % nama)
            ok = False
            continue
        isi = p.read_text(encoding="utf-8", errors="replace")
        galat = None
        ext = p.suffix.lower()
        if not isi.strip():
            galat = "berkas kosong"
        elif ext == ".py":
            try:
                ast.parse(isi, filename=nama)
            except SyntaxError as e:
                galat = "sintaks Python salah di baris %s: %s" % (e.lineno, e.msg)
            except ValueError as e:
                galat = "berkas Python tidak valid: %s" % e
        elif ext == ".json":
            try:
                json.loads(isi)
            except ValueError as e:
                galat = "JSON tidak valid: %s" % e
        elif ext == ".js" and shutil.which("node"):
            kode, out = _run(["node", "--check", str(p)], timeout=15)
            if kode != 0:
                galat = "sintaks JavaScript salah: " + _ekor_teks(out, 400)
        elif ext == ".sh" and shutil.which("bash"):
            kode, out = _run(["bash", "-n", str(p)], timeout=15)
            if kode != 0:
                galat = "sintaks Bash salah: " + _ekor_teks(out, 400)
        if galat:
            baris.append("GAGAL %s: %s" % (nama, galat))
            ok = False
        else:
            baris.append("OK %s: sintaks baik" % nama)
    return ok, baris


def perintah_uji(spec):
    cmd = list(spec.get("jalankan") or [])
    if cmd and cmd[0] == "python3":
        cmd[0] = sys.executable or "python3"
    return cmd


def cek_jalan(hasil_dir, spec, ctx, izin, boleh):
    """Uji jalan program. Kembalian: (status, baris); status: lolos / gagal / dilewati.

    Program buatan model dijalankan HANYA setelah pengguna mengizinkan (ditanya sekali per
    proses, juga di mode AUTO), tanpa shell, di folder hasil/, dengan batas waktu."""
    if not spec.get("jalankan"):
        return "dilewati", ["Uji jalan dilewati: lembar tugas tidak punya perintah uji."]
    if not boleh:
        return "dilewati", ["Uji jalan dilewati: dimatikan di pengaturan."]
    cmd = perintah_uji(spec)
    tampil = " ".join(spec["jalankan"])
    if izin.get("nilai") is None:
        izin["nilai"] = bool(ctx.konfirmasi(
            "uji", "Jalankan program hasil agent: " + tampil,
            "Program ini ditulis oleh model AI, dijalankan di %s (batas %d detik, tanpa "
            "input keyboard). Periksa kodenya dulu bila ragu." % (hasil_dir, UJI_DETIK)))
    if not izin["nilai"]:
        return "dilewati", ["Uji jalan dilewati: pengguna tidak mengizinkan."]
    kode, out = _run(cmd, timeout=UJI_DETIK, cwd=str(hasil_dir),
                     env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
    out = _ekor_teks(out or "(tanpa keluaran)", 1500)
    if kode is None:
        return "gagal", ["GAGAL uji jalan `%s`: %s" % (tampil, out)]
    if kode != 0:
        return "gagal", ["GAGAL uji jalan `%s` (exit code %s):" % (tampil, kode), out]
    return "lolos", ["OK uji jalan `%s` (exit code 0):" % tampil, out]


# --------------------------------------------------------------------------
# Penilaian Pemeriksa
# --------------------------------------------------------------------------
def rapikan_nilai(d):
    ok = d.get("ok")
    if isinstance(ok, str):
        ok = ok.strip().lower() in ("true", "ya", "ok", "yes")
    masalah = []
    for m in d.get("masalah") or []:
        if isinstance(m, dict):
            m = "%s:%s - %s" % (m.get("berkas", "?"), m.get("baris", "?"), m.get("uraian", ""))
        s = " ".join(str(m).split())[:300]
        if s:
            masalah.append(s)
        if len(masalah) >= 8:
            break
    nilai = {"ok": bool(ok), "masalah": masalah,
             "ringkas": " ".join(str(d.get("ringkas") or "").split())[:300],
             "perbaikan": " ".join(str(d.get("perbaikan") or "").split())[:600]}
    if not nilai["ok"] and not masalah and not nilai["perbaikan"]:
        # Menolak tanpa alasan tidak bisa ditindaklanjuti Pelaksana: terima, tapi beri tanda.
        nilai.update(ok=True, ringkas=(nilai["ringkas"] + " (ditolak tanpa alasan konkret, diterima)").strip())
    return nilai


def teks_koreksi(cek_baris, nilai):
    bagian = []
    gagal = [b for b in cek_baris if not b.startswith("OK ")]
    if gagal:
        bagian.append("HASIL PEMERIKSAAN OTOMATIS:\n" + "\n".join(cek_baris))
    if nilai and not nilai["ok"]:
        s = "MASUKAN PEMERIKSA:\n" + (nilai["ringkas"] or "")
        if nilai["masalah"]:
            s += "\nMasalah:\n" + "\n".join("- " + m for m in nilai["masalah"])
        if nilai["perbaikan"]:
            s += "\nPerbaikan: " + nilai["perbaikan"]
        bagian.append(s)
    return "\n\n".join(bagian) or "Perbaiki hasil sebelumnya agar memenuhi semua kriteria."


# --------------------------------------------------------------------------
# Tahap-tahap (generator event)
# --------------------------------------------------------------------------
def _tahap(kunci, model, putaran=None):
    return {"t": "tahap", "tahap": kunci, "peran": PERAN[kunci], "model": model,
            "putaran": putaran}


def _rencana(tugas, spec_lama, hasil_dir, folder, mp, ctx, pemuat):
    """Kembalian: (spec, pertanyaan). Bila Perencana butuh info: (None, pertanyaan)."""
    yield _tahap("rencana", mp)
    yield from pemuat.pakai(mp)
    user = "PERMINTAAN PENGGUNA:\n" + tugas
    if spec_lama:
        ada = [n for n, _ in baca_proyek(hasil_dir)]
        user += ("\n\nPROYEK SEBELUMNYA (lembar tugas lama):\n"
                 + json.dumps(spec_lama, ensure_ascii=False)[:2500]
                 + "\nBerkas yang sudah ada: " + (", ".join(ada) or "-")
                 + "\nBuat lembar tugas BARU yang mencakup perubahan yang diminta; daftar "
                   "\"berkas\" berisi semua berkas yang perlu ditulis ulang.")
    pesan = [{"role": "system", "content": SYSTEM_PERENCANA}, {"role": "user", "content": user}]
    teks, _ = yield from tanya(mp, pesan, ctx, TOKEN_RENCANA, 0.2, True)
    raw = ambil_json(teks)
    if raw is None:
        pesan += [{"role": "assistant", "content": teks[:1500]},
                  {"role": "user", "content": "Balasanmu bukan JSON valid. Balas ulang HANYA "
                                              "dengan objek JSON sesuai format."}]
        teks, _ = yield from tanya(mp, pesan, ctx, TOKEN_RENCANA, 0.1, True)
        raw = ambil_json(teks)
    if raw is None:
        raw = {"catatan": "Lembar tugas dibuat otomatis: Perencana tidak memberi JSON yang valid."}
    pertanyaan = " ".join(str(raw.get("tanya") or "").split())[:400]
    if pertanyaan and not raw.get("berkas"):
        return None, pertanyaan
    spec = rapikan_spec(raw, tugas)
    (folder / "tugas.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    (folder / "tugas.md").write_text(spec_ke_md(spec), encoding="utf-8")
    yield {"t": "rencana", "d": spec}
    return spec, ""


def _tulis(spec, koreksi, hasil_dir, me, ctx):
    """Pelaksana menulis berkas. Kembalian: (nama_berkas_ditulis, daftar_masalah_format)."""
    anggaran = anggaran_prompt(TOKEN_TAHAP)
    user = "LEMBAR TUGAS:\n" + json.dumps(spec, ensure_ascii=False, indent=1)
    ada = baca_proyek(hasil_dir)
    if ada:
        user += "\n\nBERKAS SAAT INI:\n" + blok_berkas(ada, max(1500, anggaran - len(user) - 3000))
    if koreksi:
        user += "\n\nKOREKSI YANG HARUS DIPERBAIKI:\n" + koreksi[:2500]
    user += ("\n\nTulis semua berkas yang tercantum di lembar tugas (isi LENGKAP) dengan "
             "format === FILE: nama === ... === END ===.")
    pesan = [{"role": "system", "content": SYSTEM_PELAKSANA}, {"role": "user", "content": user}]
    teks, terpotong = yield from tanya(me, pesan, ctx, TOKEN_TAHAP, 0.2, False)
    ditulis, masalah = [], []
    daftar = urai_berkas(teks, [b["nama"] for b in spec["berkas"]])
    if not daftar:
        masalah.append("Keluaranmu tidak berisi blok berkas. Pakai format "
                       "=== FILE: nama === ... === END ===.")
    for nama, isi, lengkap in daftar:
        try:
            nama = aman_nama(nama)
        except ValueError as e:
            masalah.append(str(e))
            continue
        if not lengkap:
            masalah.append("%s: keluaran terpotong (batas token tercapai); tulis lebih ringkas "
                           "atau pecah menjadi berkas yang lebih kecil." % nama)
            continue
        if not isi.strip():
            masalah.append("%s: isi berkas kosong." % nama)
            continue
        baru = not (Path(hasil_dir) / nama).exists()
        if baru and len(baca_proyek(hasil_dir)) >= MAKS_BERKAS_TOTAL:
            masalah.append("%s: melebihi batas %d berkas per proyek." % (nama, MAKS_BERKAS_TOTAL))
            continue
        try:
            tulis_berkas(hasil_dir, nama, isi)
        except ValueError as e:
            masalah.append(str(e))
            continue
        ditulis.append(nama)
        yield {"t": "berkas", "nama": nama, "baru": baru, "isi": isi[:20000],
               "dipotong": len(isi) > 20000}
    if terpotong and not any("terpotong" in m for m in masalah):
        masalah.append("Keluaran mencapai batas token; pastikan semua berkas ditulis lengkap.")
    return ditulis, masalah


def _periksa(spec, cek_baris, hasil_dir, mc, ctx):
    anggaran = anggaran_prompt(TOKEN_PERIKSA)
    user = ("LEMBAR TUGAS:\n" + json.dumps(spec, ensure_ascii=False, indent=1)
            + "\n\nBERKAS (dengan nomor baris):\n"
            + blok_berkas(baca_proyek(hasil_dir), max(1500, anggaran - 2500), nomor=True)
            + "\n\nHASIL PEMERIKSAAN OTOMATIS:\n" + "\n".join(cek_baris)[:1800])
    pesan = [{"role": "system", "content": SYSTEM_PEMERIKSA}, {"role": "user", "content": user}]
    teks, _ = yield from tanya(mc, pesan, ctx, TOKEN_PERIKSA, 0.1, True)
    d = ambil_json(teks)
    if d is None:
        pesan += [{"role": "assistant", "content": teks[:1500]},
                  {"role": "user", "content": "Balasanmu bukan JSON valid. Balas ulang HANYA "
                                              "dengan objek JSON sesuai format."}]
        teks, _ = yield from tanya(mc, pesan, ctx, TOKEN_PERIKSA, 0.1, True)
        d = ambil_json(teks)
    if d is None:
        return {"ok": True, "masalah": [], "perbaikan": "",
                "ringkas": "Pemeriksa tidak memberi penilaian yang terbaca; pemeriksaan "
                           "otomatis lolos sehingga hasil diterima."}
    return rapikan_nilai(d)


def _kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat, izin, akhir):
    """Putaran Pelaksana -> pemeriksaan -> koreksi. Kembalian: 'lolos' atau 'belum'.
    `akhir` (dict) diisi hasil pemeriksaan terakhir untuk penjelasan."""
    mp, me, mc, maks = cfg["model_p"], cfg["model_e"], cfg["model_c"], cfg["maks"]
    koreksi = ""
    for putaran in range(1, maks + 1):
        meta["putaran"] = putaran
        yield {"t": "putaran", "n": putaran, "maks": maks}
        yield _tahap("tulis", me, putaran)
        yield from pemuat.pakai(me)
        ditulis, masalah = yield from _tulis(spec, koreksi, hasil_dir, me, ctx)

        # Pemeriksaan otomatis (kode): sintaks, berkas ada, uji jalan
        ok_statis, baris = cek_statis(hasil_dir, spec, ditulis)
        baris = ["GAGAL format: " + m for m in masalah] + baris
        ok = ok_statis and not masalah
        status_jalan = "dilewati"
        if ok:
            status_jalan, jalan = cek_jalan(hasil_dir, spec, ctx, izin, cfg["uji"])
            baris += jalan
            ok = status_jalan != "gagal"
        akhir.update(cek=baris, jalan=status_jalan, nilai=None)
        yield {"t": "cek", "ok": ok, "jalan": status_jalan, "d": "\n".join(baris)}
        if ctx.batal.is_set():
            raise Batal()

        berikut = mc if ok else (me if putaran < maks else mp)
        yield from pemuat.selesai_tahap(berikut)
        if not ok:   # model Pemeriksa tidak perlu dimuat: kesalahan sudah pasti
            koreksi = teks_koreksi(baris, None)
            (folder / ("koreksi_%d.md" % putaran)).write_text(koreksi, encoding="utf-8")
            continue

        yield _tahap("periksa", mc, putaran)
        yield from pemuat.pakai(mc)
        nilai = yield from _periksa(spec, baris, hasil_dir, mc, ctx)
        akhir["nilai"] = nilai
        yield dict(nilai, t="nilai")
        if nilai["ok"]:
            yield from pemuat.selesai_tahap(mp)
            return "lolos"
        koreksi = teks_koreksi(baris, nilai)
        (folder / ("koreksi_%d.md" % putaran)).write_text(koreksi, encoding="utf-8")
        yield from pemuat.selesai_tahap(me if putaran < maks else mp)
    return "belum"


def _data_penjelasan(status, spec, hasil_dir, meta, akhir):
    bagian = ["STATUS: " + STATUS_TEKS.get(status, status),
              "PUTARAN DIPAKAI: %d dari maksimal %d" % (meta["putaran"], meta["maks"]),
              "LEMBAR TUGAS: " + json.dumps(spec, ensure_ascii=False)[:1800]]
    berkas = baca_proyek(hasil_dir)
    if berkas:
        bagian.append("BERKAS HASIL (awal isi):\n" + blok_berkas(berkas, 2500))
    if akhir.get("cek"):
        bagian.append("PEMERIKSAAN OTOMATIS TERAKHIR (uji jalan: %s):\n%s" % (
            akhir.get("jalan", "dilewati"), "\n".join(akhir["cek"])[:1200]))
    n = akhir.get("nilai")
    if n:
        bagian.append("PENILAIAN PEMERIKSA: %s %s %s" % (
            "OK" if n["ok"] else "BELUM OK", n["ringkas"], "; ".join(n["masalah"])))
    return "\n\n".join(bagian)


def _teks_cadangan(status, spec, hasil_dir):
    nama = ", ".join(n for n, _ in baca_proyek(hasil_dir)) or "-"
    cara = " ".join(spec["jalankan"]) if spec["jalankan"] else "(lihat berkas hasil)"
    return ("**Hasil**: %s\n**Berkas**: %s\n**Cara menjalankan**: `%s`\n**Pemeriksaan**: %s\n"
            % (spec["ringkasan"], nama, cara, STATUS_TEKS.get(status, status)))


def _jelaskan(status, spec, hasil_dir, meta, akhir, mp, ctx, pemuat):
    yield _tahap("jelaskan", mp)
    try:
        yield from pemuat.pakai(mp)
        pesan = [{"role": "system", "content": SYSTEM_PENJELAS},
                 {"role": "user", "content": _data_penjelasan(status, spec, hasil_dir, meta, akhir)}]
        teks, _ = yield from tanya(mp, pesan, ctx, TOKEN_JELAS, 0.4, False, keluar="token")
        teks = teks.strip()
        if teks:
            return teks
    except Batal:
        raise
    except Exception as e:  # noqa: BLE001 - penjelasan gagal bukan kegagalan proses
        yield {"t": "ringkas", "d": "Penjelasan otomatis gagal (%s); memakai ringkasan biasa." % e}
    teks = _teks_cadangan(status, spec, hasil_dir)
    yield {"t": "token", "d": teks}
    return teks


# --------------------------------------------------------------------------
# Pintu masuk
# --------------------------------------------------------------------------
def siapkan_cfg(b, tersedia):
    """Validasi pengaturan dari web. Kembalian: (cfg, pesan_error)."""
    try:
        mode = 3 if int(b.get("mode") or 2) == 3 else 2
    except (TypeError, ValueError):
        mode = 2
    mp, me = b.get("model_p"), b.get("model_e")
    mc = b.get("model_c") if mode == 3 else mp
    for n in (mp, me, mc):
        if n not in tersedia:
            return None, "Model tidak dikenal: %s" % (n,)
    if len({mp, me, mc}) < 2:
        return None, "Pilih minimal 2 model yang berbeda."
    try:
        maks = int(b.get("maks") or LANGKAH_BAWAAN)
    except (TypeError, ValueError):
        maks = LANGKAH_BAWAAN
    maks = max(LANGKAH_MIN, min(LANGKAH_MAKS, maks))
    return {"mode": mode, "model_p": mp, "model_e": me, "model_c": mc, "maks": maks,
            "bongkar": bool(b.get("bongkar", True)), "uji": bool(b.get("uji", True))}, ""


def jalankan(tugas, cfg, ctx, lanjut=None):
    """Generator event untuk satu proses Agent (satu perintah pengguna)."""
    tugas = (tugas or "").strip()[:MAKS_TUGAS]
    KERJA.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)
    folder = KERJA / run_id
    hasil_dir = folder / "hasil"
    hasil_dir.mkdir(parents=True)
    meta = {"id": run_id, "tugas": tugas, "judul": " ".join(tugas.split())[:40],
            "status": "error", "dibuat": datetime.now().isoformat(timespec="seconds"),
            "model": {"perencana": cfg["model_p"], "pelaksana": cfg["model_e"],
                      "pemeriksa": cfg["model_c"]},
            "putaran": 0, "maks": cfg["maks"], "lanjut": None, "laporan": "", "spec": None}
    spec_lama = None
    if lanjut and ID_RUN.match(str(lanjut)) and (KERJA / lanjut).is_dir():
        salin_proyek(KERJA / lanjut / "hasil", hasil_dir)
        spec_lama = _baca_json(KERJA / lanjut / "tugas.json")
        meta["lanjut"] = lanjut
    yield {"t": "mulai", "id": run_id, "dir": str(folder), "maks": cfg["maks"],
           "model": meta["model"], "lanjut": meta["lanjut"]}

    pemuat = Pemuat(ctx, cfg["bongkar"])
    izin = {"nilai": None}
    akhir = {}
    status, spec = "error", None
    try:
        spec, pertanyaan = yield from _rencana(tugas, spec_lama, hasil_dir, folder,
                                               cfg["model_p"], ctx, pemuat)
        if spec is None:
            status = "butuh_info"
            meta["laporan"] = pertanyaan
            yield {"t": "tanya", "d": pertanyaan}
            yield from pemuat.lepas_semua()
        else:
            meta["spec"], meta["judul"] = spec, spec["judul"]
            yield from pemuat.selesai_tahap(cfg["model_e"])
            status = yield from _kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat,
                                          izin, akhir)
            meta["laporan"] = yield from _jelaskan(status, spec, hasil_dir, meta, akhir,
                                                   cfg["model_p"], ctx, pemuat)
            yield from pemuat.lepas_semua()
    except Batal:
        status = "batal"
        yield {"t": "batal"}
    except Exception as e:  # noqa: BLE001
        status = "error"
        yield {"t": "error", "d": "%s: %s" % (type(e).__name__, e)}
    finally:
        pemuat.lepas_diam()
        meta["status"] = status
        try:
            if meta["laporan"]:
                (folder / "laporan.md").write_text(meta["laporan"], encoding="utf-8")
            (folder / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        except OSError:
            pass
    yield {"t": "selesai", "status": status, "id": run_id,
           "teks": STATUS_TEKS.get(status, status), "dir": str(folder)}


# --------------------------------------------------------------------------
# Riwayat proses
# --------------------------------------------------------------------------
def id_valid(run_id):
    return bool(ID_RUN.match(str(run_id or "")))


def daftar_run(maks=30):
    hasil = []
    if not KERJA.is_dir():
        return hasil
    for d in sorted(KERJA.iterdir(), reverse=True):
        if not (d.is_dir() and ID_RUN.match(d.name)):
            continue
        m = _baca_json(d / "run.json")
        if not isinstance(m, dict):
            continue
        hasil.append({k: m.get(k) for k in ("id", "judul", "status", "dibuat", "putaran", "maks")})
        if len(hasil) >= maks:
            break
    return hasil


def baca_run(run_id):
    """Ringkasan proses + isi berkas hasilnya. FileNotFoundError bila tidak ada."""
    if not ID_RUN.match(str(run_id or "")):
        raise FileNotFoundError("id tidak valid")
    d = KERJA / run_id
    m = _baca_json(d / "run.json")
    if not isinstance(m, dict):
        raise FileNotFoundError(run_id)
    m["berkas"] = [{"nama": n, "isi": isi[:60000]} for n, isi in baca_proyek(d / "hasil")]
    m["dir"] = str(d)
    return m
