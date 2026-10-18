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
AKTIF_RUN = set()            # id proses yang sedang berjalan (tidak boleh dihapus)


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
    '- "langkah": maksimal 3 langkah garis besar, tanpa nama library dan tanpa potongan kode\n'
    '- "kriteria": daftar syarat selesai yang bisa diperiksa (maksimal 5); tidak boleh saling '
    "bertentangan\n"
    '- "jalankan": perintah uji berupa daftar, mis. ["python3", "main.py"]. Kosongkan [] bila '
    "programnya interaktif, butuh internet, atau berupa tampilan/GUI/web. Program yang diuji "
    "harus selesai sendiri dalam beberapa detik tanpa input keyboard (pakai data contoh bawaan).\n"
    '- "harapan": daftar teks pendek yang PASTI muncul di keluaran program bila benar, mis. ["88"] '
    "untuk jumlah 10 bilangan Fibonacci pertama (0+1+1+2+3+5+8+13+21+34). Isi HANYA bila kamu "
    '100% yakin dengan hasil hitungannya dan "jalankan" tidak kosong; selain itu [].\n'
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
    "meminta input keyboard dan mencetak hasilnya.\n"
    "5. Bila ada KOREKSI, perbaiki masalah yang disebut di dalamnya. Ubah HANYA bagian yang "
    "bermasalah; jangan merusak bagian yang sudah benar.\n"
    "6. Saran koreksi bisa keliru. Abaikan saran yang bertentangan dengan lembar tugas atau "
    "dengan keluaran program yang sudah benar.\n"
    "7. Utamakan library standar; jangan menginstal paket.")
SYSTEM_PEMERIKSA = (
    "Kamu PEMERIKSA dalam tim pembuat program. Periksa berkas buatan PELAKSANA terhadap lembar "
    "tugas. HASIL PEMERIKSAAN OTOMATIS adalah fakta (sintaks dan keluaran program yang benar-benar "
    "dijalankan).\n"
    "Balas HANYA dengan satu objek JSON:\n"
    '{"ok": true atau false, "ringkas": "satu kalimat penilaian", '
    '"masalah": ["berkas:baris - uraian bug nyata"], '
    '"dilihat": "kutipan PERSIS dari keluaran program atau baris kode yang salah", '
    '"perbaikan": "instruksi konkret untuk pelaksana"}\n'
    "Aturan:\n"
    "1. ok=true bila semua kriteria utama terpenuhi dan tidak ada bug nyata. Bila keluaran "
    "program sudah memenuhi kriteria, jawab ok=true.\n"
    "2. ok=false HANYA bila kamu bisa menunjuk kesalahan nyata. Isi \"dilihat\" dengan kutipan "
    "persis dari keluaran atau kode; penolakan tanpa kutipan yang benar akan diabaikan.\n"
    "3. Jangan menuntut gaya penulisan, fitur tambahan, atau hal di luar kriteria. Jangan "
    "mengarang masalah atau angka yang tidak ada di keluaran.\n"
    "4. Jangan menyarankan mengubah algoritma yang keluarannya sudah benar.\n"
    "5. Maksimal 5 masalah.")
SYSTEM_PENJELAS = (
    "Kamu PENJELAS: wajah tim bagi pengguna. Jelaskan dalam bahasa Indonesia yang ramah, "
    "3-5 kalimat, APA yang dibuat program dan cara kerjanya secara garis besar, berdasarkan "
    "lembar tugas dan kode. JANGAN menulis status lolos/gagal, hasil uji, angka keluaran, atau "
    "saran perbaikan: bagian itu ditulis oleh sistem. Jangan mengarang fitur yang tidak ada di kode.")
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
            yield {"t": "bongkar_mulai", "model": nama}   # tampil di log langsung sebelum menunggu
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


_HEAD = re.compile(
    r"^[ \t]*[=#*-]{2,}[ \t]*(?:FILE|BERKAS)[ \t]*:[ \t]*(.+?)[ \t]*[=#*-]*[ \t]*$", re.M | re.I)
_END = re.compile(
    r"^[ \t]*[=#*-]{2,}[ \t]*(?:END|SELESAI)(?:[ \t]+(?:FILE|BERKAS))?[ \t]*[=#*-]*[ \t]*$",
    re.M | re.I)
_PAGAR = re.compile(r"```[\w+-]*[ \t]*\n(.*?)```", re.S)
_PAGAR_BARIS = re.compile(r"^[ \t]*```[\w+-]*[ \t]*$")
_NAMA_DI_BARIS = re.compile(r"([A-Za-z0-9_][A-Za-z0-9_./-]*\.[A-Za-z0-9]{1,5})")


def _rapi(isi, nama=""):
    """Rapikan isi berkas dari model: buang baris pagar ``` yang nyasar di awal/akhir.
    (Berkas .md/.txt boleh berisi pagar, jadi hanya baris kosong di ujung yang dibuang.)"""
    baris = isi.replace("\r\n", "\n").split("\n")
    if Path(nama).suffix.lower() in (".md", ".txt"):
        teks = "\n".join(baris).strip("\n")
    else:
        while baris and (not baris[0].strip() or _PAGAR_BARIS.match(baris[0])):
            baris.pop(0)
        while baris and (not baris[-1].strip() or _PAGAR_BARIS.match(baris[-1])):
            baris.pop()
        teks = "\n".join(baris)
    return teks + "\n" if teks.strip() else ""


def _kode_valid(nama, isi):
    ext = Path(nama).suffix.lower()
    try:
        if ext == ".py":
            ast.parse(isi)
            return True
        if ext == ".json":
            json.loads(isi)
            return True
    except (SyntaxError, ValueError):
        return False
    return False


def urai_berkas(teks, nama_spec=()):
    """Urai keluaran Pelaksana menjadi [(nama, isi, lengkap)].

    Format utama:  === FILE: nama ===  ...  === END ===  (penanda longgar: ### FILE: x, **FILE: x**)
    `lengkap` False bila blok tidak ditutup (keluaran terpotong batas token).
    Cadangan: blok ``` dengan nama berkas di baris sebelumnya, satu blok ``` untuk lembar tugas
    satu berkas, atau seluruh jawaban bila lembar tugas satu berkas dan isinya kode yang valid.
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
            hasil.append((nama, _rapi(potongan[:e.start()], nama), True))
        else:
            hasil.append((nama, _rapi(potongan, nama), i + 1 < len(kepala)))
    if hasil:
        return hasil
    blok = list(_PAGAR.finditer(teks))
    if len(blok) == 1 and len(nama_spec) == 1:
        return [(nama_spec[0], _rapi(blok[0].group(1), nama_spec[0]), True)]
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
            hasil.append((nama, _rapi(b.group(1), nama), True))
    if not hasil and not blok and len(nama_spec) == 1 and teks.strip():
        isi = _rapi(teks, nama_spec[0])
        if _kode_valid(nama_spec[0], isi):
            return [(nama_spec[0], isi, True)]
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


def _rapikan_harapan(v):
    """Teks pendek yang harus muncul di keluaran program (oracle dari Perencana)."""
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    hasil = []
    for x in v:
        t = " ".join(str(x).split())[:60]
        if t and t not in hasil:
            hasil.append(t)
        if len(hasil) >= 5:
            break
    return hasil


def spec_model(spec):
    """Lembar tugas untuk Pelaksana/Pemeriksa. 'langkah' dibuang: langkah buatan model kecil
    sering keliru (algoritma/library salah) dan menyesatkan Pelaksana."""
    return {k: v for k, v in spec.items() if k != "langkah"}


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
    jalankan = _rapikan_jalankan(raw.get("jalankan"), [b["nama"] for b in berkas])
    return {
        "judul": judul,
        "ringkasan": " ".join(str(raw.get("ringkasan") or tugas).split())[:500],
        "bahasa": " ".join(str(raw.get("bahasa") or "python").split())[:20].lower(),
        "berkas": berkas,
        "langkah": _daftar_teks(raw.get("langkah"), 5, 200),
        "kriteria": (_daftar_teks(raw.get("kriteria"), 6)
                     or ["Program memenuhi permintaan pengguna.", "Tidak ada error saat dijalankan."]),
        "jalankan": jalankan,
        "harapan": _rapikan_harapan(raw.get("harapan")) if jalankan else [],
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
    if spec.get("harapan"):
        baris += ["", "## Harapan keluaran", "Keluaran harus memuat: " + ", ".join(spec["harapan"])]
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
    """Uji jalan program. Kembalian: (status, baris, keluaran); status: lolos / gagal / dilewati.
    `keluaran` adalah keluaran program yang sebenarnya (None bila tidak dijalankan).

    Program buatan model dijalankan HANYA setelah pengguna mengizinkan (ditanya sekali per
    proses, juga di mode AUTO), tanpa shell, di folder hasil/, dengan batas waktu."""
    if not spec.get("jalankan"):
        return "dilewati", ["Uji jalan dilewati: lembar tugas tidak punya perintah uji."], None
    if not boleh:
        return "dilewati", ["Uji jalan dilewati: dimatikan di pengaturan."], None
    cmd = perintah_uji(spec)
    tampil = " ".join(spec["jalankan"])
    if izin.get("nilai") is None:
        izin["nilai"] = bool(ctx.konfirmasi(
            "uji", "Jalankan program hasil agent: " + tampil,
            "Program ini ditulis oleh model AI, dijalankan di %s (batas %d detik, tanpa "
            "input keyboard). Periksa kodenya dulu bila ragu." % (hasil_dir, UJI_DETIK)))
    if not izin["nilai"]:
        return "dilewati", ["Uji jalan dilewati: pengguna tidak mengizinkan."], None
    kode, out = _run(cmd, timeout=UJI_DETIK, cwd=str(hasil_dir),
                     env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"})
    penuh = out or ""
    ringkas = _ekor_teks(penuh or "(tanpa keluaran)", 1500)
    if kode is None:
        return "gagal", ["GAGAL uji jalan `%s`: %s" % (tampil, ringkas)], penuh
    if kode != 0:
        return "gagal", ["GAGAL uji jalan `%s` (exit code %s):" % (tampil, kode), ringkas], penuh
    return "lolos", ["OK uji jalan `%s` (exit code 0):" % tampil, ringkas], penuh


def _norm(t):
    return " ".join(str(t or "").split()).lower()


def cocok_keluaran(keluaran, harapan):
    """Apakah keluaran program memuat semua teks harapan? Kembalian: (semua_cocok, yang_hilang).
    Angka dicocokkan utuh (88 tidak cocok dengan 188 atau 88.5)."""
    n = _norm(keluaran)
    hilang = []
    for h in harapan:
        hn = _norm(h)
        if re.fullmatch(r"-?\d+(?:\.\d+)?", hn):
            ada = re.search(r"(?<![\w.])" + re.escape(hn) + r"(?!\w|\.\d)", n) is not None
        else:
            ada = hn in n
        if not ada:
            hilang.append(h)
    return not hilang, hilang


# --------------------------------------------------------------------------
# Penilaian Pemeriksa
# --------------------------------------------------------------------------
def _masalah_bersih(m):
    """Satu masalah dari Pemeriksa, atau '' bila hanya kerangka kosong (mis. '?:? -')."""
    if isinstance(m, dict):
        uraian = " ".join(str(m.get("uraian") or m.get("masalah") or "").split())
        s = "%s:%s - %s" % (m.get("berkas") or "?", m.get("baris") or "?", uraian)
    else:
        s = uraian = " ".join(str(m).split())
    if len(re.findall(r"[A-Za-z]{3,}", uraian)) < 2:
        return ""
    return s[:300]


def rapikan_nilai(d, sumber=None):
    """Penilaian Pemeriksa yang sudah divalidasi.

    Model kecil sering menolak hasil yang benar, jadi penolakan hanya berlaku bila konkret:
    ada masalah yang bermakna dan (bila `sumber` = keluaran program + kode tersedia) kutipan
    "dilihat" benar-benar ada di sana. Selain itu hasil diterima dengan catatan."""
    ok = d.get("ok")
    if isinstance(ok, str):
        ok = ok.strip().lower() in ("true", "ya", "ok", "yes")
    masalah = [x for x in (_masalah_bersih(m) for m in (d.get("masalah") or [])) if x][:8]
    dilihat = " ".join(str(d.get("dilihat") or "").split())[:200]
    nilai = {"ok": bool(ok), "masalah": masalah, "dilihat": dilihat,
             "ringkas": " ".join(str(d.get("ringkas") or "").split())[:300],
             "perbaikan": " ".join(str(d.get("perbaikan") or "").split())[:600]}
    if not nilai["ok"]:
        alasan = ""
        if not masalah:
            alasan = "ditolak tanpa masalah yang konkret"
        elif sumber is not None and dilihat and _norm(dilihat) not in _norm(sumber):
            alasan = "kutipan Pemeriksa tidak ada di keluaran/kode, kemungkinan keliru"
        if alasan:
            nilai.update(ok=True, masalah=[], perbaikan="",
                         ringkas=(nilai["ringkas"] + " (" + alasan + "; diterima)").strip())
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
        if nilai.get("dilihat"):
            s += "\nKutipan: " + nilai["dilihat"]
        if nilai["perbaikan"]:
            s += "\nPerbaikan: " + nilai["perbaikan"]
        bagian.append(s)
    return "\n\n".join(bagian) or "Perbaiki hasil sebelumnya agar memenuhi semua kriteria."


# --------------------------------------------------------------------------
# Tahap-tahap (generator event)
# --------------------------------------------------------------------------
class Jejak:
    """Menyimpan prompt dan keluaran mentah tiap tahap model ke folder jejak/ (untuk diagnosis:
    kenapa Pelaksana salah format, kenapa Pemeriksa menolak, dst.)."""

    def __init__(self, folder):
        self.dir = Path(folder) / "jejak"
        self.n = 0

    def simpan(self, nama, prompt, keluaran):
        try:
            self.dir.mkdir(exist_ok=True)
            self.n += 1
            (self.dir / ("%02d-%s.txt" % (self.n, nama))).write_text(
                "### PROMPT (user)\n%s\n\n### KELUARAN MODEL\n%s\n" % (prompt, keluaran),
                encoding="utf-8")
        except OSError:
            pass


def _tahap(kunci, model, putaran=None):
    return {"t": "tahap", "tahap": kunci, "peran": PERAN[kunci], "model": model,
            "putaran": putaran}


def _rencana(tugas, spec_lama, hasil_dir, folder, mp, ctx, pemuat, jejak):
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
    jejak.simpan("rencana", user, teks)
    raw = ambil_json(teks)
    if raw is None:
        pesan += [{"role": "assistant", "content": teks[:1500]},
                  {"role": "user", "content": "Balasanmu bukan JSON valid. Balas ulang HANYA "
                                              "dengan objek JSON sesuai format."}]
        teks, _ = yield from tanya(mp, pesan, ctx, TOKEN_RENCANA, 0.1, True)
        jejak.simpan("rencana-ulang", "(permintaan ulang JSON)", teks)
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


def _tulis(spec, koreksi, hasil_dir, me, ctx, jejak, putaran):
    """Pelaksana menulis berkas. Kembalian: (nama_berkas_ditulis, daftar_masalah_format)."""
    anggaran = anggaran_prompt(TOKEN_TAHAP)
    user = "LEMBAR TUGAS:\n" + json.dumps(spec_model(spec), ensure_ascii=False, indent=1)
    ada = baca_proyek(hasil_dir)
    if ada:
        user += "\n\nBERKAS SAAT INI:\n" + blok_berkas(ada, max(1500, anggaran - len(user) - 3000))
    if koreksi:
        user += "\n\nKOREKSI YANG HARUS DIPERBAIKI:\n" + koreksi[:2500]
    user += ("\n\nTulis semua berkas yang tercantum di lembar tugas (isi LENGKAP) dengan "
             "format === FILE: nama === ... === END ===.")
    pesan = [{"role": "system", "content": SYSTEM_PELAKSANA}, {"role": "user", "content": user}]
    teks, terpotong = yield from tanya(me, pesan, ctx, TOKEN_TAHAP, 0.2, False)
    jejak.simpan("tulis-%d" % putaran, user, teks)
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


def _periksa(spec, cek_baris, hasil_dir, mc, ctx, keluaran, jejak, putaran):
    anggaran = anggaran_prompt(TOKEN_PERIKSA)
    berkas = baca_proyek(hasil_dir)
    user = ("LEMBAR TUGAS:\n" + json.dumps(spec_model(spec), ensure_ascii=False, indent=1)
            + "\n\nBERKAS (dengan nomor baris):\n"
            + blok_berkas(berkas, max(1500, anggaran - 2500), nomor=True)
            + "\n\nHASIL PEMERIKSAAN OTOMATIS (fakta, bukan pendapat):\n"
            + "\n".join(cek_baris)[:1800])
    pesan = [{"role": "system", "content": SYSTEM_PEMERIKSA}, {"role": "user", "content": user}]
    teks, _ = yield from tanya(mc, pesan, ctx, TOKEN_PERIKSA, 0.1, True)
    jejak.simpan("periksa-%d" % putaran, user, teks)
    d = ambil_json(teks)
    if d is None:
        pesan += [{"role": "assistant", "content": teks[:1500]},
                  {"role": "user", "content": "Balasanmu bukan JSON valid. Balas ulang HANYA "
                                              "dengan objek JSON sesuai format."}]
        teks, _ = yield from tanya(mc, pesan, ctx, TOKEN_PERIKSA, 0.1, True)
        jejak.simpan("periksa-%d-ulang" % putaran, "(permintaan ulang JSON)", teks)
        d = ambil_json(teks)
    if d is None:
        return {"ok": True, "masalah": [], "perbaikan": "", "dilihat": "",
                "ringkas": "Pemeriksa tidak memberi penilaian yang terbaca; pemeriksaan "
                           "otomatis lolos sehingga hasil diterima."}
    sumber = None
    if keluaran is not None:      # kutipan Pemeriksa bisa dicocokkan dengan keluaran dan kode nyata
        sumber = keluaran + "\n" + "\n".join(isi for _, isi in berkas)
    return rapikan_nilai(d, sumber)


def _pulihkan(hasil_dir, berkas):
    """Kembalikan folder hasil ke isi `berkas` ({nama: isi})."""
    for nama, isi in berkas.items():
        tulis_berkas(hasil_dir, nama, isi)
    for nama, _ in baca_proyek(hasil_dir):
        if nama not in berkas:
            try:
                (Path(hasil_dir) / nama).unlink()
            except OSError:
                pass


def _kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat, izin, akhir, jejak):
    """Putaran Pelaksana -> pemeriksaan -> koreksi. Kembalian: 'lolos' atau 'belum'.
    `akhir` (dict) diisi hasil pemeriksaan terakhir untuk penjelasan.

    Bukti dari kode lebih berat daripada pendapat model: keluaran yang memuat 'harapan'
    Perencana langsung lolos (Pemeriksa dilewati), dan bila akhirnya belum sempurna, hasil
    putaran terbaik dipulihkan supaya koreksi yang keliru tidak merusak hasil yang lebih baik."""
    mp, me, mc, maks = cfg["model_p"], cfg["model_e"], cfg["model_c"], cfg["maks"]
    koreksi = ""
    rekam = []    # per putaran: skor (2 lolos+harapan, 1 lolos, 0 gagal), isi berkas, hasil cek
    for putaran in range(1, maks + 1):
        meta["putaran"] = putaran
        yield {"t": "putaran", "n": putaran, "maks": maks}
        yield _tahap("tulis", me, putaran)
        yield from pemuat.pakai(me)
        ditulis, masalah = yield from _tulis(spec, koreksi, hasil_dir, me, ctx, jejak, putaran)

        # Pemeriksaan otomatis (kode): sintaks, berkas ada, uji jalan, harapan keluaran
        yield {"t": "cek_mulai"}
        ok_statis, baris = cek_statis(hasil_dir, spec, ditulis)
        baris = ["GAGAL format: " + m for m in masalah] + baris
        ok = ok_statis and not masalah
        status_jalan, keluaran, harapan = "dilewati", None, None
        if ok:
            if spec["jalankan"] and cfg["uji"]:
                yield {"t": "uji_mulai", "d": " ".join(spec["jalankan"])}
            status_jalan, jalan, keluaran = cek_jalan(hasil_dir, spec, ctx, izin, cfg["uji"])
            baris += jalan
            ok = status_jalan != "gagal"
        if ok and keluaran is not None and spec["harapan"]:
            harapan, hilang = cocok_keluaran(keluaran, spec["harapan"])
            if harapan:
                baris.append("OK keluaran memuat harapan Perencana: " + ", ".join(spec["harapan"]))
            else:
                baris.append("CATATAN: keluaran tidak memuat harapan Perencana (%s); harapan "
                             "ini bisa keliru." % ", ".join(hilang))
        akhir.clear()
        akhir.update(cek=baris, jalan=status_jalan, keluaran=keluaran, harapan=harapan,
                     nilai=None, pulih=None)
        rekam.append({"skor": ((2 if harapan else 1) if ok else 0), "putaran": putaran,
                      "berkas": dict(baca_proyek(hasil_dir)), "akhir": dict(akhir)})
        yield {"t": "cek", "ok": ok, "jalan": status_jalan, "harapan": harapan,
               "d": "\n".join(baris)}
        if ctx.batal.is_set():
            raise Batal()

        if ok and harapan:     # bukti cukup: Pemeriksa tidak perlu dimuat
            yield {"t": "ringkas", "d": "Keluaran sesuai harapan Perencana; Pemeriksa dilewati."}
            yield from pemuat.selesai_tahap(mp)
            return "lolos"

        berikut = mc if ok else (me if putaran < maks else mp)
        yield from pemuat.selesai_tahap(berikut)
        if not ok:   # kesalahan sudah pasti: langsung kembali ke Pelaksana tanpa memuat Pemeriksa
            koreksi = teks_koreksi(baris, None)
            (folder / ("koreksi_%d.md" % putaran)).write_text(koreksi, encoding="utf-8")
            continue

        yield _tahap("periksa", mc, putaran)
        yield from pemuat.pakai(mc)
        nilai = yield from _periksa(spec, baris, hasil_dir, mc, ctx, keluaran, jejak, putaran)
        akhir["nilai"] = nilai
        rekam[-1]["akhir"]["nilai"] = nilai
        yield dict(nilai, t="nilai")
        if nilai["ok"]:
            yield from pemuat.selesai_tahap(mp)
            return "lolos"
        koreksi = teks_koreksi(baris, nilai)
        (folder / ("koreksi_%d.md" % putaran)).write_text(koreksi, encoding="utf-8")
        yield from pemuat.selesai_tahap(me if putaran < maks else mp)

    terbaik = max(rekam, key=lambda r: (r["skor"], r["putaran"]))
    if terbaik["putaran"] != rekam[-1]["putaran"]:
        _pulihkan(hasil_dir, terbaik["berkas"])
        akhir.clear()
        akhir.update(terbaik["akhir"])
        akhir["pulih"] = terbaik["putaran"]
        yield {"t": "pulih", "putaran": terbaik["putaran"],
               "d": "Hasil putaran %d dipulihkan: lebih baik daripada putaran terakhir."
                    % terbaik["putaran"]}
    return "belum"


def _ringkasan_program(spec, hasil_dir):
    """Bahan untuk Penjelas: apa program ini (tanpa status uji, itu urusan sistem)."""
    bagian = ["RINGKASAN: " + spec["ringkasan"],
              "BERKAS: " + ", ".join("%s (%s)" % (b["nama"], b["fungsi"]) for b in spec["berkas"])]
    berkas = baca_proyek(hasil_dir)
    if berkas:
        bagian.append("KODE:\n" + blok_berkas(berkas, 3000))
    return "\n\n".join(bagian)


def blok_fakta(status, spec, hasil_dir, meta, akhir):
    """Bagian pasti dari laporan, ditulis KODE dari data nyata (bukan model), supaya laporan
    tidak mengarang status, keluaran, atau hasil pemeriksaan."""
    ikon = {"lolos": "✔", "belum": "⚠", "batal": "⏹", "error": "✖"}.get(status, "•")
    baris = ["%s **Status**: %s (putaran %d dari maks %d)"
             % (ikon, STATUS_TEKS.get(status, status), meta["putaran"], meta["maks"])]
    berkas = baca_proyek(hasil_dir)
    baris.append("**Berkas**: " + (", ".join(
        "`%s` (%d baris)" % (n, len(i.splitlines())) for n, i in berkas) or "-"))
    if spec["jalankan"]:
        baris.append("**Cara menjalankan**: `%s`" % " ".join(spec["jalankan"]))
    keluaran = akhir.get("keluaran")
    if keluaran is not None:
        baris.append("**Keluaran uji jalan**:\n```\n%s\n```" % _ekor_teks(keluaran.strip() or "(kosong)", 600))
    cek = akhir.get("cek") or []
    gagal = [b for b in cek if b.startswith("GAGAL")]
    jalan = akhir.get("jalan", "dilewati")
    baris.append("**Pemeriksaan otomatis**: %s · uji jalan %s" % (
        ("GAGAL - " + gagal[0][:200]) if gagal else "lolos", jalan))
    if akhir.get("harapan") is True:
        baris.append("**Harapan Perencana**: terpenuhi (%s)" % ", ".join(spec["harapan"]))
    elif akhir.get("harapan") is False:
        baris.append("**Harapan Perencana**: tidak terpenuhi (bisa keliru)")
    nilai = akhir.get("nilai")
    if nilai:
        baris.append("**Penilaian Pemeriksa** (pendapat model, bisa keliru): %s%s" % (
            "OK" if nilai["ok"] else "perlu perbaikan", (" - " + nilai["ringkas"]) if nilai["ringkas"] else ""))
    elif status == "lolos" and akhir.get("harapan"):
        baris.append("**Pemeriksa**: dilewati karena keluaran sesuai harapan")
    if akhir.get("pulih"):
        baris.append("**Dipulihkan**: hasil putaran %d (terbaik dari semua putaran)" % akhir["pulih"])
    return "\n".join(baris)


def _jelaskan(status, spec, hasil_dir, meta, akhir, mp, ctx, pemuat, jejak):
    """Penjelas menulis prosa singkat tentang programnya; fakta status ditambahkan oleh sistem."""
    yield _tahap("jelaskan", mp)
    prosa = ""
    try:
        yield from pemuat.pakai(mp)
        user = _ringkasan_program(spec, hasil_dir)
        pesan = [{"role": "system", "content": SYSTEM_PENJELAS},
                 {"role": "user", "content": user}]
        prosa, _ = yield from tanya(mp, pesan, ctx, TOKEN_JELAS, 0.3, False, keluar="token")
        jejak.simpan("jelaskan", user, prosa)
        prosa = prosa.strip()
    except Batal:
        raise
    except Exception as e:  # noqa: BLE001 - penjelasan gagal bukan kegagalan proses
        yield {"t": "ringkas", "d": "Penjelasan otomatis gagal (%s); memakai ringkasan biasa." % e}
    if not prosa:
        prosa = spec["ringkasan"]
        yield {"t": "token", "d": prosa}
    fakta = "\n\n" + blok_fakta(status, spec, hasil_dir, meta, akhir)
    yield {"t": "token", "d": fakta}
    return prosa + fakta


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


def _jalankan(tugas, cfg, ctx, lanjut=None):
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
    jejak = Jejak(folder)
    AKTIF_RUN.add(run_id)
    izin = {"nilai": None}
    akhir = {}
    status, spec = "error", None
    try:
        spec, pertanyaan = yield from _rencana(tugas, spec_lama, hasil_dir, folder,
                                               cfg["model_p"], ctx, pemuat, jejak)
        if spec is None:
            status = "butuh_info"
            meta["laporan"] = pertanyaan
            yield {"t": "tanya", "d": pertanyaan}
            yield from pemuat.lepas_semua()
        else:
            meta["spec"], meta["judul"] = spec, spec["judul"]
            yield from pemuat.selesai_tahap(cfg["model_e"])
            status = yield from _kerjakan(spec, cfg, hasil_dir, folder, meta, ctx, pemuat,
                                          izin, akhir, jejak)
            meta["laporan"] = yield from _jelaskan(status, spec, hasil_dir, meta, akhir,
                                                   cfg["model_p"], ctx, pemuat, jejak)
            yield from pemuat.lepas_semua()
    except Batal:
        status = "batal"
        yield {"t": "batal"}
    except Exception as e:  # noqa: BLE001
        status = "error"
        yield {"t": "error", "d": "%s: %s" % (type(e).__name__, e)}
    finally:
        AKTIF_RUN.discard(run_id)
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


def jalankan(tugas, cfg, ctx, lanjut=None):
    """Generator event satu proses Agent; juga mencatat log.jsonl di folder kerja
    (tanpa potongan teks per token) agar proses bisa ditinjau setelah halaman ditutup."""
    t0, log = time.time(), None
    try:
        for ev in _jalankan(tugas, cfg, ctx, lanjut):
            if ev["t"] == "mulai":
                try:
                    log = open(Path(ev["dir"]) / "log.jsonl", "a", encoding="utf-8")
                except OSError:
                    log = None
            if log and ev["t"] not in ("isi", "token", "muat"):
                try:
                    rapi = {k: v for k, v in ev.items() if k != "isi"}
                    log.write(json.dumps(dict(rapi, ts=round(time.time() - t0, 1)),
                                         ensure_ascii=False) + "\n")
                    log.flush()
                except (OSError, TypeError, ValueError):
                    pass
            yield ev
    finally:
        if log:
            log.close()


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


def _hapus_folder(d):
    shutil.rmtree(str(d))     # tidak mengikuti symlink di dalamnya: hanya tautannya yang terhapus


def hapus_run(run_id):
    """Hapus satu proses beserta berkas hasilnya.
    FileNotFoundError bila tidak ada, PermissionError bila prosesnya masih berjalan."""
    if not id_valid(run_id):
        raise FileNotFoundError("id tidak valid")
    if run_id in AKTIF_RUN:
        raise PermissionError("Proses ini masih berjalan")
    d = KERJA / run_id
    if d.is_symlink() or not d.is_dir():
        raise FileNotFoundError(run_id)
    _hapus_folder(d)


def hapus_semua_run():
    """Hapus semua proses kecuali yang masih berjalan. Kembalian: jumlah yang dihapus."""
    n = 0
    if not KERJA.is_dir():
        return n
    for d in list(KERJA.iterdir()):
        if d.is_symlink() or not d.is_dir() or not id_valid(d.name) or d.name in AKTIF_RUN:
            continue
        try:
            _hapus_folder(d)
            n += 1
        except OSError:
            pass
    return n


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
