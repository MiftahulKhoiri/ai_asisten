"""server_koneksi.py - alamat llama-server atau penyedia online + API key, diatur dari web.

Disimpan di pengaturan.json (izin 0600) dan diterapkan ke paket agen (agen.LLAMA_URL, LLAMA_V1,
LLAMA_KEY, LLAMA_JENIS). Kunci API tidak pernah dikirim balik ke browser atau ditulis di log.
Tanpa berkas pengaturan, nilai awal datang dari variabel lingkungan LLAMA_BASE_URL dan LLAMA_API_KEY.
"""

import json
import os
import re
import urllib.error
from urllib.parse import urlsplit

import agen
import tim
from . import server_config as conf
from . import server_log as lg
from . import server_model as mdl
from . import server_state as state

JENIS = ("llama", "online")
MAKS_ALAMAT = 300
MAKS_KUNCI = 500
_LOKAL = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|\[?::1\]?|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
                    r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|[^.]+|[^/]+\.local)$")   # nama tanpa titik / .local = jaringan lokal

# nilai dari lingkungan (sebelum pengaturan web diterapkan); dipakai saat pengaturan web dihapus
_AWAL = {"alamat": agen.LLAMA_URL + ("" if agen.LLAMA_V1 == "/v1" else agen.LLAMA_V1),
         "key": agen.LLAMA_KEY, "jenis": agen.LLAMA_JENIS}
SUMBER = {"nilai": "bawaan"}      # "bawaan" | "lingkungan" | "web"
if os.environ.get("LLAMA_BASE_URL") or os.environ.get("LLAMA_API_KEY"):
    SUMBER["nilai"] = "lingkungan"


def rapikan_alamat(teks):
    """Alamat yang diketik pengguna -> (alamat bersih, galat). Awalan http:// ditambahkan bila tak ada."""
    a = (teks or "").strip() if isinstance(teks, str) else ""
    if not a:
        return "", "Alamat belum diisi"
    if len(a) > MAKS_ALAMAT or re.search(r"\s", a):
        return "", "Alamat tidak valid (ada spasi atau terlalu panjang)"
    if "://" not in a:
        a = "http://" + a
    u = urlsplit(a)
    if u.scheme not in ("http", "https") or not u.hostname:
        return "", "Alamat harus berawalan http:// atau https://"
    if u.username or u.password:
        return "", "Jangan menaruh kunci di alamat; isi di kolom API key"
    if u.query or u.fragment:
        return "", "Alamat tidak boleh memuat ? atau #"
    return a.rstrip("/"), ""


def _peringatan(alamat, kunci):
    u = urlsplit(alamat)
    if kunci and u.scheme == "http" and not _LOKAL.match(u.hostname or ""):
        return "Kunci API dikirim tanpa enkripsi (http) ke server di internet. Pakai alamat https://"
    return ""


def koneksi_terapkan(alamat, kunci, jenis):
    """Pakai pengaturan ini untuk semua permintaan berikutnya (chat dan Agent)."""
    dasar, v1 = agen.pecah_alamat(alamat)
    agen.LLAMA_URL, agen.LLAMA_V1 = dasar, v1
    agen.LLAMA_KEY = kunci or ""
    agen.LLAMA_JENIS = jenis if jenis in JENIS else "llama"


def koneksi_alamat():
    """Alamat yang sedang dipakai, seperti yang diketik pengguna."""
    return agen.LLAMA_URL + ("" if agen.LLAMA_V1 == "/v1" else agen.LLAMA_V1)


def koneksi_muat():
    """Terapkan pengaturan.json bila ada. Mengembalikan peringatan/galat berupa teks, atau ''."""
    try:
        d = json.loads(conf.PENGATURAN_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as e:
        return f"pengaturan.json tidak terbaca ({type(e).__name__}); memakai nilai bawaan"
    k = d.get("koneksi") if isinstance(d, dict) else None
    if not isinstance(k, dict):
        return ""
    alamat, galat = rapikan_alamat(k.get("alamat"))
    if galat:
        return "pengaturan.json: " + galat + "; memakai nilai bawaan"
    kunci = k.get("key") if isinstance(k.get("key"), str) else ""
    koneksi_terapkan(alamat, kunci, k.get("jenis"))
    SUMBER["nilai"] = "web"
    return ""


def _tulis(koneksi):
    """Tulis pengaturan.json secara atomik dengan izin 0600 (berisi kunci API)."""
    isi = json.dumps({"koneksi": koneksi}, ensure_ascii=False, indent=2)
    sementara = conf.PENGATURAN_FILE.with_name(conf.PENGATURAN_FILE.name + ".tmp")
    fd = os.open(sementara, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(isi)
    os.replace(sementara, conf.PENGATURAN_FILE)
    os.chmod(conf.PENGATURAN_FILE, 0o600)


def koneksi_ringkas():
    """Data untuk tampilan web. TIDAK memuat kunci API."""
    return {"alamat": koneksi_alamat(), "jenis": agen.LLAMA_JENIS, "key_ada": bool(agen.LLAMA_KEY),
            "sumber": SUMBER["nilai"], "peringatan": _peringatan(koneksi_alamat(), agen.LLAMA_KEY)}


def _sibuk():
    with state.AGENT_COND:
        agen_aktif = bool(state.AGENT["aktif"])
    return state.GEN_LOCK.locked() or agen_aktif


def _masukan(b):
    """Baca kolom dari body. Kolom kunci yang tidak dikirim = pakai kunci yang sedang dipakai.
    Mengembalikan (alamat, kunci, jenis, galat)."""
    if not isinstance(b, dict):
        return "", "", "", "Isi permintaan tidak valid"
    alamat = b["alamat"] if "alamat" in b else koneksi_alamat()
    alamat, galat = rapikan_alamat(alamat)
    if galat:
        return "", "", "", galat
    if isinstance(b.get("key"), str):
        kunci = b["key"].strip()
        if len(kunci) > MAKS_KUNCI or re.search(r"[\r\n\x00]", kunci):
            return "", "", "", "API key tidak valid (terlalu panjang atau ada baris baru)"
    else:
        kunci = agen.LLAMA_KEY      # tidak dikirim = tetap pakai yang tersimpan
    jenis = b.get("jenis") if b.get("jenis") in JENIS else agen.LLAMA_JENIS
    return alamat, kunci, jenis, ""


def _pesan_galat(e, kunci):
    """Teks galat yang membantu pengguna. Tidak pernah memuat kunci."""
    if isinstance(e, urllib.error.HTTPError):
        k = e.code
        if k in (401, 403):
            return (f"Ditolak server ({k}): API key salah atau belum diisi" if kunci
                    else f"Ditolak server ({k}): server ini butuh API key")
        if k == 404:
            return ("Server terjangkau tapi /models tidak ada (404). Periksa alamatnya; untuk penyedia "
                    "online biasanya berakhiran /v1")
        if 300 <= k < 400:
            tujuan = e.headers.get("Location", "") if e.headers else ""
            return (f"Server mengalihkan ke alamat lain ({k}{': ' + tujuan[:120] if tujuan else ''}). "
                    "Pakai alamat tujuan itu langsung (sering cukup mengganti http:// dengan https://)")
        return f"Server menjawab galat {k}"
    if isinstance(e, urllib.error.URLError):
        return f"Tidak bisa terhubung: {e.reason}"
    if isinstance(e, ValueError):
        return "Jawaban server bukan JSON; ini sepertinya bukan llama-server/penyedia yang kompatibel OpenAI"
    return f"{type(e).__name__}: {e}"


def koneksi_uji(b):
    """Coba hubungi alamat/kunci dari formulir TANPA menerapkannya. (kode HTTP, isi JSON)."""
    alamat, kunci, jenis, galat = _masukan(b)
    if galat:
        return 400, {"ok": False, "error": galat}
    dasar, v1 = agen.pecah_alamat(alamat)
    try:
        data = agen.llama_uji(dasar, v1, kunci)
        daftar = data.get("data") if isinstance(data, dict) else None
        if not isinstance(daftar, list):
            raise ValueError("bukan daftar model")
    except Exception as e:  # noqa: BLE001
        return 200, {"ok": False, "error": _pesan_galat(e, kunci)}
    ids = [m["id"] for m in daftar if isinstance(m, dict) and isinstance(m.get("id"), str)]
    router = any(isinstance(m, dict) and (m.get("status") or {}).get("value") for m in daftar)
    return 200, {"ok": True, "jumlah": len(ids), "contoh": ids[:8], "router": router,
                 "peringatan": _peringatan(alamat, kunci)}


def koneksi_simpan(b):
    """Simpan lalu terapkan. Ditolak bila ada proses berjalan. (kode HTTP, isi JSON)."""
    alamat, kunci, jenis, galat = _masukan(b)
    if galat:
        return 400, {"ok": False, "error": galat}
    if _sibuk():
        return 409, {"ok": False, "error": "Sedang ada proses berjalan. Tunggu selesai atau hentikan dulu."}
    _ganti(alamat, kunci, jenis)
    try:
        _tulis({"alamat": alamat, "key": kunci, "jenis": jenis})
    except OSError as e:
        lg.log("ERR", f"Gagal menyimpan pengaturan.json: {e}")
        return 200, {"ok": True, "tersimpan": False, "koneksi": koneksi_ringkas(),
                     "peringatan": "Berlaku sekarang, tapi gagal disimpan ke berkas; hilang saat aplikasi dimulai ulang"}
    SUMBER["nilai"] = "web"
    return 200, {"ok": True, "tersimpan": True, "koneksi": koneksi_ringkas(),
                 "peringatan": _peringatan(alamat, kunci)}


def koneksi_reset():
    """Hapus pengaturan web; kembali ke nilai lingkungan/bawaan. (kode HTTP, isi JSON)."""
    if _sibuk():
        return 409, {"ok": False, "error": "Sedang ada proses berjalan. Tunggu selesai atau hentikan dulu."}
    _ganti(_AWAL["alamat"], _AWAL["key"], _AWAL["jenis"])
    try:
        conf.PENGATURAN_FILE.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        return 500, {"ok": False, "error": f"Gagal menghapus pengaturan.json: {e}"}
    SUMBER["nilai"] = "lingkungan" if (os.environ.get("LLAMA_BASE_URL") or os.environ.get("LLAMA_API_KEY")) else "bawaan"
    return 200, {"ok": True, "koneksi": koneksi_ringkas()}


def _ganti(alamat, kunci, jenis):
    """Beralih ke server lain: model yang dimuat aplikasi ini di server lama dibongkar dulu
    (memakai alamat lama), lalu keadaan dikosongkan agar pengguna memilih model dari server baru."""
    sama = (alamat == koneksi_alamat() and kunci == agen.LLAMA_KEY)
    if not sama:
        try:
            mdl.bongkar_model()
            for nama in tim.bongkar_sisa():
                lg.log("OK", f"Model Agent dibongkar dari memori: {nama}")
        except Exception as e:  # noqa: BLE001
            lg.log("WARN", f"Gagal membongkar model di server lama: {e}")
        with state.S_LOCK:
            state.S.update(model=None, status="kosong", pesan="", target=None, kita_muat=False)
    koneksi_terapkan(alamat, kunci, jenis)
    lg.log("INFO", f"Koneksi diatur: {koneksi_alamat()} (jenis: {agen.LLAMA_JENIS}, "
                   f"API key: {'ada' if agen.LLAMA_KEY else 'tidak ada'})")


__all__ = ['JENIS', 'rapikan_alamat', 'koneksi_terapkan', 'koneksi_alamat', 'koneksi_muat',
           'koneksi_ringkas', 'koneksi_uji', 'koneksi_simpan', 'koneksi_reset']
