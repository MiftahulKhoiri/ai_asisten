"""server_koneksi.py - koneksi ke server model: llama-server lokal dan/atau penyedia online, diatur dari web.

Ada satu koneksi UTAMA (id "lokal", biasanya llama-server di Pi) dan sampai MAKS_TAMBAHAN koneksi
TAMBAHAN (mis. OpenRouter, OpenAI). Daftar model memuat model dari semuanya; model koneksi tambahan
diberi awalan id-nya ("k1a2b3c::gpt-4o") dan tiap permintaan dikirim ke koneksinya masing-masing.

Disimpan di pengaturan.json (izin 0600) dan diterapkan ke paket agen. Kunci API tidak pernah dikirim balik
ke browser atau ditulis di log. Tanpa berkas pengaturan, koneksi utama berasal dari variabel lingkungan
LLAMA_BASE_URL dan LLAMA_API_KEY.
"""

import json
import os
import re
import secrets
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
MAKS_NAMA = 40
MAKS_TAMBAHAN = 8
ID_KONEKSI = re.compile(r"^k[0-9a-f]{6}$")
_LOKAL = re.compile(r"^(localhost|127\.\d+\.\d+\.\d+|\[?::1\]?|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|"
                    r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|[^.]+|[^/]+\.local)$")   # nama tanpa titik / .local = jaringan lokal

# nilai koneksi utama dari lingkungan (sebelum pengaturan web diterapkan); dipakai saat pengaturan web dihapus
_AWAL = {"alamat": agen.LLAMA_URL + ("" if agen.LLAMA_V1 == "/v1" else agen.LLAMA_V1),
         "key": agen.LLAMA_KEY, "jenis": agen.LLAMA_JENIS, "nama": ""}
SUMBER = {"nilai": "bawaan"}      # sumber koneksi utama: "bawaan" | "lingkungan" | "web"
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


def _alamat_dari(dasar, v1):
    return dasar + ("" if v1 == "/v1" else v1)


def koneksi_alamat():
    """Alamat koneksi utama, seperti yang diketik pengguna."""
    return _alamat_dari(agen.LLAMA_URL, agen.LLAMA_V1)


def koneksi_terapkan(alamat, kunci, jenis, nama=None):
    """Pakai pengaturan ini untuk koneksi UTAMA."""
    dasar, v1 = agen.pecah_alamat(alamat)
    agen.LLAMA_URL, agen.LLAMA_V1 = dasar, v1
    agen.LLAMA_KEY = kunci or ""
    agen.LLAMA_JENIS = jenis if jenis in JENIS else "llama"
    agen.LLAMA_NAMA = (nama or "").strip()[:MAKS_NAMA]


def _terapkan_tambahan(cid, nama, alamat, kunci, jenis):
    dasar, v1 = agen.pecah_alamat(alamat)
    jenis = jenis if jenis in JENIS else "online"
    agen.LLAMA_EXTRA[cid] = {"nama": (nama or "").strip()[:MAKS_NAMA] or agen.nama_otomatis(dasar, jenis),
                             "url": dasar, "v1": v1, "key": kunci or "", "jenis": jenis}


def _data_koneksi(cid):
    """Isi koneksi (termasuk kunci) untuk disimpan: {"id","nama","alamat","key","jenis"}."""
    s = agen.sambungan(cid)
    return {"id": s["id"], "nama": s["nama"] if cid != agen.KONEKSI_UTAMA else agen.LLAMA_NAMA,
            "alamat": _alamat_dari(s["url"], s["v1"]), "key": s["key"], "jenis": s["jenis"]}


def koneksi_muat():
    """Terapkan pengaturan.json bila ada. Mengembalikan peringatan/galat berupa teks, atau ''."""
    try:
        d = json.loads(conf.PENGATURAN_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ""
    except (OSError, ValueError) as e:
        return f"pengaturan.json tidak terbaca ({type(e).__name__}); memakai nilai bawaan"
    if not isinstance(d, dict):
        return ""
    pesan = []
    k = d.get("koneksi")
    if isinstance(k, dict):
        alamat, galat = rapikan_alamat(k.get("alamat"))
        if galat:
            pesan.append("pengaturan.json (koneksi utama): " + galat + "; memakai nilai bawaan")
        else:
            koneksi_terapkan(alamat, k.get("key") if isinstance(k.get("key"), str) else "", k.get("jenis"),
                             k.get("nama") if isinstance(k.get("nama"), str) else "")
            SUMBER["nilai"] = "web"
    agen.LLAMA_EXTRA.clear()
    for t in (d.get("tambahan") if isinstance(d.get("tambahan"), list) else [])[:MAKS_TAMBAHAN]:
        if not isinstance(t, dict) or not isinstance(t.get("id"), str) or not ID_KONEKSI.match(t["id"]):
            pesan.append("pengaturan.json: satu koneksi tambahan dilewati (id tidak valid)")
            continue
        alamat, galat = rapikan_alamat(t.get("alamat"))
        if galat:
            pesan.append(f"pengaturan.json: koneksi {t['id']} dilewati ({galat})")
            continue
        _terapkan_tambahan(t["id"], t.get("nama") if isinstance(t.get("nama"), str) else "", alamat,
                           t.get("key") if isinstance(t.get("key"), str) else "", t.get("jenis"))
    return "; ".join(pesan)


def _tulis():
    """Tulis pengaturan.json secara atomik dengan izin 0600 (berisi kunci API). Koneksi utama hanya
    ditulis bila berasal dari web; bila tidak ada yang perlu disimpan, berkas dihapus."""
    d = {}
    if SUMBER["nilai"] == "web":
        u = _data_koneksi(agen.KONEKSI_UTAMA)
        d["koneksi"] = {k: u[k] for k in ("nama", "alamat", "key", "jenis")}
    if agen.LLAMA_EXTRA:
        d["tambahan"] = [_data_koneksi(c) for c in agen.LLAMA_EXTRA]
    if not d:
        try:
            conf.PENGATURAN_FILE.unlink()
        except FileNotFoundError:
            pass
        return
    isi = json.dumps(d, ensure_ascii=False, indent=2)
    sementara = conf.PENGATURAN_FILE.with_name(conf.PENGATURAN_FILE.name + ".tmp")
    fd = os.open(sementara, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(isi)
    os.replace(sementara, conf.PENGATURAN_FILE)
    os.chmod(conf.PENGATURAN_FILE, 0o600)


def koneksi_ringkas():
    """Data untuk tampilan web. TIDAK memuat kunci API. Kolom tingkat-atas (alamat, jenis, key_ada, ...)
    adalah koneksi utama; `daftar` memuat semua koneksi."""
    daftar = []
    for cid in [agen.KONEKSI_UTAMA] + list(agen.LLAMA_EXTRA):
        s = agen.sambungan(cid)
        st = state.KONEKSI_STATUS.get(cid) or {}
        daftar.append({"id": cid, "nama": s["nama"], "jenis": s["jenis"], "alamat": _alamat_dari(s["url"], s["v1"]),
                       "key_ada": bool(s["key"]), "utama": cid == agen.KONEKSI_UTAMA,
                       "peringatan": _peringatan(_alamat_dari(s["url"], s["v1"]), s["key"]),
                       "ok": st.get("ok"), "jumlah": st.get("jumlah"), "galat": st.get("galat", "")})
    u = daftar[0]
    return {"alamat": u["alamat"], "jenis": u["jenis"], "key_ada": u["key_ada"], "nama": u["nama"],
            "sumber": SUMBER["nilai"], "peringatan": u["peringatan"], "daftar": daftar,
            "maks_tambahan": MAKS_TAMBAHAN}


def _sibuk():
    with state.AGENT_COND:
        agen_aktif = bool(state.AGENT["aktif"])
    return state.GEN_LOCK.locked() or agen_aktif


_SIBUK = {"ok": False, "error": "Sedang ada proses berjalan. Tunggu selesai atau hentikan dulu."}


def _masukan(b):
    """Baca kolom dari body. Kolom yang tidak dikirim = pakai nilai koneksi itu sekarang (kunci juga).
    Mengembalikan (id, alamat, kunci, jenis, nama, galat); id 'baru' = koneksi tambahan baru."""
    if not isinstance(b, dict):
        return "", "", "", "", "", "Isi permintaan tidak valid"
    cid = b.get("id") or agen.KONEKSI_UTAMA
    if not isinstance(cid, str):
        return "", "", "", "", "", "id koneksi tidak valid"
    baru = cid == "baru"
    if not baru and cid != agen.KONEKSI_UTAMA and cid not in agen.LLAMA_EXTRA:
        return "", "", "", "", "", "Koneksi tidak ditemukan"
    kini = None if baru else _data_koneksi(cid)
    alamat = b["alamat"] if "alamat" in b else (kini["alamat"] if kini else "")
    alamat, galat = rapikan_alamat(alamat)
    if galat:
        return "", "", "", "", "", galat
    if isinstance(b.get("key"), str):
        kunci = b["key"].strip()
        if len(kunci) > MAKS_KUNCI or re.search(r"[\r\n\x00]", kunci):
            return "", "", "", "", "", "API key tidak valid (terlalu panjang atau ada baris baru)"
    else:
        kunci = kini["key"] if kini else ""      # tidak dikirim = tetap pakai yang tersimpan
    jenis = b.get("jenis") if b.get("jenis") in JENIS else (kini["jenis"] if kini else "online")
    nama = b["nama"] if isinstance(b.get("nama"), str) else (kini["nama"] if kini else "")
    nama = nama.strip()
    if len(nama) > MAKS_NAMA or re.search(r"[\r\n\x00]", nama):
        return "", "", "", "", "", "Nama terlalu panjang (maks %d huruf)" % MAKS_NAMA
    return cid, alamat, kunci, jenis, nama, ""


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
    cid, alamat, kunci, jenis, nama, galat = _masukan(b)
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


def _lepaskan(cid):
    """Bongkar model milik koneksi `cid` yang dimuat aplikasi ini (memakai koneksi yang LAMA), dan
    kosongkan sesi bila sesinya memakai model koneksi itu."""
    try:
        with state.S_LOCK:
            m = state.S["model"] or state.S["target"]
        if m and agen.pecah_model(m)[0] == cid:
            mdl.bongkar_model()
            with state.S_LOCK:
                state.S.update(model=None, status="kosong", pesan="", target=None, kita_muat=False)
        for nama in list(tim.DIMUAT):
            if agen.pecah_model(nama)[0] == cid:
                tim.bongkar(nama)
                lg.log("OK", f"Model Agent dibongkar dari memori: {nama}")
    except Exception as e:  # noqa: BLE001
        lg.log("WARN", f"Gagal membongkar model di server lama: {e}")


def _catat(cid):
    s = agen.sambungan(cid)
    lg.log("INFO", f"Koneksi {'utama' if cid == agen.KONEKSI_UTAMA else cid} diatur: {s['nama']} "
                   f"{_alamat_dari(s['url'], s['v1'])} (jenis: {s['jenis']}, API key: {'ada' if s['key'] else 'tidak ada'})")


def koneksi_simpan(b):
    """Simpan lalu terapkan; id 'baru' menambah koneksi. Ditolak bila ada proses berjalan. (kode HTTP, isi JSON)."""
    cid, alamat, kunci, jenis, nama, galat = _masukan(b)
    if galat:
        return 400, {"ok": False, "error": galat}
    if _sibuk():
        return 409, dict(_SIBUK)
    if cid == "baru":
        if len(agen.LLAMA_EXTRA) >= MAKS_TAMBAHAN:
            return 400, {"ok": False, "error": "Koneksi tambahan sudah mencapai batas (%d)" % MAKS_TAMBAHAN}
        while True:
            cid = "k" + secrets.token_hex(3)
            if cid not in agen.LLAMA_EXTRA:
                break
        _terapkan_tambahan(cid, nama, alamat, kunci, jenis)
    elif cid == agen.KONEKSI_UTAMA:
        sama = (alamat == koneksi_alamat() and kunci == agen.LLAMA_KEY)
        if not sama:
            _lepaskan(cid)
        koneksi_terapkan(alamat, kunci, jenis, nama)
        SUMBER["nilai"] = "web"
    else:
        lama = agen.LLAMA_EXTRA[cid]
        if alamat != _alamat_dari(lama["url"], lama["v1"]) or kunci != lama["key"]:
            _lepaskan(cid)
        _terapkan_tambahan(cid, nama, alamat, kunci, jenis)
    _catat(cid)
    try:
        _tulis()
    except OSError as e:
        lg.log("ERR", f"Gagal menyimpan pengaturan.json: {e}")
        return 200, {"ok": True, "tersimpan": False, "id": cid, "koneksi": koneksi_ringkas(),
                     "peringatan": "Berlaku sekarang, tapi gagal disimpan ke berkas; hilang saat aplikasi dimulai ulang"}
    return 200, {"ok": True, "tersimpan": True, "id": cid, "koneksi": koneksi_ringkas(),
                 "peringatan": _peringatan(alamat, kunci)}


def koneksi_hapus(b):
    """Hapus satu koneksi tambahan. Koneksi utama tidak bisa dihapus. (kode HTTP, isi JSON)."""
    cid = b.get("id") if isinstance(b, dict) else None
    if cid == agen.KONEKSI_UTAMA:
        return 400, {"ok": False, "error": "Koneksi utama tidak bisa dihapus; ubah saja alamatnya atau pakai bawaan."}
    if not isinstance(cid, str) or cid not in agen.LLAMA_EXTRA:
        return 404, {"ok": False, "error": "Koneksi tidak ditemukan"}
    if _sibuk():
        return 409, dict(_SIBUK)
    _lepaskan(cid)
    nama = agen.LLAMA_EXTRA.pop(cid)["nama"]
    state.KONEKSI_STATUS.pop(cid, None)
    lg.log("INFO", f"Koneksi dihapus: {nama}")
    try:
        _tulis()
    except OSError as e:
        return 500, {"ok": False, "error": f"Gagal menyimpan pengaturan.json: {e}"}
    return 200, {"ok": True, "koneksi": koneksi_ringkas()}


def koneksi_reset():
    """Koneksi UTAMA kembali ke nilai lingkungan/bawaan (koneksi tambahan tetap). (kode HTTP, isi JSON)."""
    if _sibuk():
        return 409, dict(_SIBUK)
    sama = (_AWAL["alamat"] == koneksi_alamat() and _AWAL["key"] == agen.LLAMA_KEY)
    if not sama:
        _lepaskan(agen.KONEKSI_UTAMA)
    koneksi_terapkan(_AWAL["alamat"], _AWAL["key"], _AWAL["jenis"], _AWAL["nama"])
    SUMBER["nilai"] = "lingkungan" if (os.environ.get("LLAMA_BASE_URL") or os.environ.get("LLAMA_API_KEY")) else "bawaan"
    lg.log("INFO", f"Koneksi utama kembali ke bawaan: {koneksi_alamat()}")
    try:
        _tulis()
    except OSError as e:
        return 500, {"ok": False, "error": f"Gagal menghapus pengaturan.json: {e}"}
    return 200, {"ok": True, "koneksi": koneksi_ringkas()}


__all__ = ['JENIS', 'MAKS_TAMBAHAN', 'rapikan_alamat', 'koneksi_terapkan', 'koneksi_alamat', 'koneksi_muat',
           'koneksi_ringkas', 'koneksi_uji', 'koneksi_simpan', 'koneksi_hapus', 'koneksi_reset']
