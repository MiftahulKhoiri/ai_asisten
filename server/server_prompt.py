"""server_prompt.py - prompt pilihan pengguna untuk skill Tanpa.

SATU PROMPT = SATU BERKAS JSON di folder prompt/ (ASISTEN_PROMPT_DIR untuk memindahkannya), supaya
prompt yang berhasil mudah dibagikan: cukup kirim berkasnya, atau lewat tombol ekspor/impor di web.

  prompt/penerjemah.json
  {"format": "ai-asisten-prompt", "versi": 1, "nama": "Penerjemah", "isi": "Terjemahkan ...",
   "catatan": "cocok untuk model kecil"}

Aturan pemakaian:
  - Nama berkas (tanpa .json) menjadi id prompt dan tidak berubah walau namanya diganti.
  - Berkas yang disalin ke folder itu langsung muncul di daftar (tanpa restart). Berkas yang tidak
    valid dilewati dan dilaporkan (lihat berkas_diabaikan).
  - "Bawaan" = SYSTEM_CHAT, bukan berkas: selalu ada, tidak bisa diubah atau dihapus.
  - Prompt yang dicentang digabung berurutan sesuai daftar (urut nama). Tidak ada yang dicentang =
    model berjalan TANPA prompt sistem sama sekali (murni).
  - Teks prompt boleh memuat {waktu}, diganti tanggal dan jam saat dipakai.
Penulisan berkas atomik; berkas lama prompt.json (versi awal) dimigrasikan otomatis.
"""
import json
import os
import re
import threading
import unicodedata

import agen
from . import server_config as conf

FORMAT = "ai-asisten-prompt"
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
_KUNCI = threading.Lock()


def bawaan():
    return {"id": conf.PROMPT_BAWAAN, "nama": "Bawaan (asisten ramah)", "isi": agen.SYSTEM_CHAT,
            "catatan": "", "bawaan": True}


# ---------------------------------------------------------------- validasi
def _periksa(nama, isi, catatan=""):
    """(nama, isi, catatan) yang sudah dirapikan. ValueError bila kosong atau melebihi batas."""
    nama, isi = " ".join(str(nama or "").split()), str(isi or "").strip()
    catatan = " ".join(str(catatan or "").split())
    if not nama:
        raise ValueError("Nama prompt wajib diisi")
    if len(nama) > conf.MAKS_NAMA_PROMPT:
        raise ValueError("Nama prompt maksimal %d karakter" % conf.MAKS_NAMA_PROMPT)
    if not isi:
        raise ValueError("Isi prompt wajib diisi")
    if len(isi) > conf.MAKS_ISI_PROMPT:
        raise ValueError("Isi prompt maksimal %d karakter" % conf.MAKS_ISI_PROMPT)
    if len(catatan) > conf.MAKS_CATATAN_PROMPT:
        raise ValueError("Catatan maksimal %d karakter" % conf.MAKS_CATATAN_PROMPT)
    return nama, isi, catatan


def _slug(nama):
    s = unicodedata.normalize("NFKD", nama).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40].strip("-")
    return s or "prompt"


def _id_baru(nama, dipakai):
    """Id (nama berkas) unik dari nama prompt; 'bawaan' dicadangkan."""
    dasar = _slug(nama)
    if dasar == conf.PROMPT_BAWAAN:
        dasar = "bawaan-prompt"
    calon, i = dasar, 2
    while calon in dipakai:
        akhiran = "-%d" % i
        calon = dasar[:40 - len(akhiran)].rstrip("-") + akhiran
        i += 1
    return calon


def _nama_unik(nama, namas):
    """Nama yang belum dipakai: 'Nama', 'Nama (2)', 'Nama (3)' ..."""
    calon, i = nama, 2
    while calon.lower() in namas:
        akhiran = " (%d)" % i
        calon = nama[:conf.MAKS_NAMA_PROMPT - len(akhiran)].rstrip() + akhiran
        i += 1
    return calon


# ---------------------------------------------------------------- berkas
def _path(pid):
    return conf.PROMPT_DIR / (pid + ".json")


def _tulis_item(item):
    conf.PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    isi = {"format": FORMAT, "versi": 1, "nama": item["nama"], "isi": item["isi"]}
    if item.get("catatan"):
        isi["catatan"] = item["catatan"]
    tujuan = _path(item["id"])
    tmp = tujuan.with_name(tujuan.name + ".tmp")
    tmp.write_text(json.dumps(isi, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(tujuan))


def _item_dari_berkas(f):
    """(item, alasan_dilewati). Berkas dibaca dengan ketat: kecil, bukan symlink, bentuk dan batas valid."""
    try:
        if f.is_symlink() or not f.is_file():
            return None, "bukan berkas biasa"
        if f.stat().st_size > conf.MAKS_BERKAS_PROMPT:
            return None, "terlalu besar"
        if not _ID.match(f.stem) or f.stem == conf.PROMPT_BAWAAN:
            return None, "nama berkas tidak valid (huruf kecil, angka, - dan _)"
        d = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "bukan JSON yang valid"
    if not isinstance(d, dict):
        return None, "bukan objek JSON"
    if "format" in d and d["format"] != FORMAT:
        return None, "format tidak dikenal"
    if not isinstance(d.get("nama"), str) or not isinstance(d.get("isi"), str):
        return None, "nama dan isi harus teks"
    try:
        nama, isi, catatan = _periksa(d["nama"], d["isi"], d.get("catatan") if isinstance(d.get("catatan"), str) else "")
    except ValueError as e:
        return None, str(e)
    return {"id": f.stem, "nama": nama, "isi": isi, "catatan": catatan}, None


def _baca_semua():
    """(prompt valid urut nama, [{berkas, alasan}] yang dilewati)."""
    ada, abaikan = [], []
    if not conf.PROMPT_DIR.is_dir():
        return ada, abaikan
    for f in sorted(conf.PROMPT_DIR.glob("*.json")):
        item, alasan = _item_dari_berkas(f)
        if item:
            ada.append(item)
        else:
            abaikan.append({"berkas": f.name, "alasan": alasan})
    ada.sort(key=lambda p: (p["nama"].lower(), p["id"]))
    return ada, abaikan


def _migrasi():
    """Pindahkan prompt dari prompt.json lama (versi awal, semua dalam satu berkas) ke berkas terpisah."""
    lama = conf.PROMPT_FILE
    if not lama.is_file():
        return
    with _KUNCI:
        if not lama.is_file():
            return
        try:
            d = json.loads(lama.read_text(encoding="utf-8"))
            butir = (d.get("prompt") if isinstance(d, dict) else None) or []
        except (OSError, ValueError):
            butir = []
        ada, _ = _baca_semua()
        ids, namas = {p["id"] for p in ada}, {p["nama"].lower() for p in ada}
        for p in butir:
            try:
                nama, isi, _c = _periksa(p.get("nama"), p.get("isi"))
            except (ValueError, AttributeError):
                continue
            if nama.lower() in namas:
                continue
            item = {"id": _id_baru(nama, ids), "nama": nama, "isi": isi, "catatan": ""}
            _tulis_item(item)
            ids.add(item["id"])
            namas.add(nama.lower())
        try:
            os.replace(str(lama), str(lama.with_name(lama.name + ".migrasi")))   # disimpan sebagai cadangan
        except OSError:
            pass


# ---------------------------------------------------------------- API
def daftar_prompt():
    """Semua prompt: bawaan lebih dulu, lalu berkas di folder prompt/ urut nama."""
    _migrasi()
    return [bawaan()] + [dict(p, bawaan=False) for p in _baca_semua()[0]]


def berkas_diabaikan():
    """[{berkas, alasan}] berkas di folder prompt/ yang dilewati karena tidak valid."""
    _migrasi()
    return _baca_semua()[1]


def tambah_prompt(nama, isi, catatan=""):
    """Simpan prompt baru sebagai berkas. ValueError bila tidak valid, nama kembar, atau daftar penuh."""
    nama, isi, catatan = _periksa(nama, isi, catatan)
    _migrasi()
    with _KUNCI:
        ada, _ = _baca_semua()
        if len(ada) >= conf.MAKS_PROMPT:
            raise ValueError("Daftar prompt penuh (maks %d). Hapus yang tidak dipakai." % conf.MAKS_PROMPT)
        if any(p["nama"].lower() == nama.lower() for p in ada) or nama.lower() == bawaan()["nama"].lower():
            raise ValueError("Sudah ada prompt dengan nama itu")
        item = {"id": _id_baru(nama, {p["id"] for p in ada}), "nama": nama, "isi": isi, "catatan": catatan}
        _tulis_item(item)
    return dict(item, bawaan=False)


def ubah_prompt(pid, nama, isi, catatan=None):
    """Ubah nama, isi, dan catatan prompt buatan pengguna (id/nama berkas tetap, jadi centangnya tidak hilang).

    `catatan` None = tidak diubah. Kembalian: prompt yang sudah diubah, atau None bila id tidak ada.
    ValueError untuk prompt bawaan, nama/isi tidak valid, atau nama yang sudah dipakai prompt lain.
    Berlaku mulai pesan berikutnya, termasuk di sesi yang sedang berjalan."""
    if pid == conf.PROMPT_BAWAAN:
        raise ValueError("Prompt bawaan tidak bisa diubah. Buat salinannya lewat tombol ubah, lalu simpan.")
    _migrasi()
    with _KUNCI:
        ada, _ = _baca_semua()
        target = next((p for p in ada if p["id"] == pid), None)
        if target is None:
            return None
        nama, isi, catatan = _periksa(nama, isi, target["catatan"] if catatan is None else catatan)
        if (any(p["id"] != pid and p["nama"].lower() == nama.lower() for p in ada)
                or nama.lower() == bawaan()["nama"].lower()):
            raise ValueError("Sudah ada prompt dengan nama itu")
        target.update(nama=nama, isi=isi, catatan=catatan)
        _tulis_item(target)
    return dict(target, bawaan=False)


def hapus_prompt(pid):
    """Hapus berkas prompt. True bila ada yang terhapus. ValueError untuk bawaan."""
    if pid == conf.PROMPT_BAWAAN:
        raise ValueError("Prompt bawaan tidak bisa dihapus")
    if not _ID.match(str(pid or "")):
        return False
    _migrasi()
    with _KUNCI:
        f = _path(pid)
        if f.is_symlink() or not f.is_file():
            return False
        try:
            f.unlink()
        except OSError:
            return False
    return True


# ---------------------------------------------------------------- berbagi
def ekspor(pid):
    """Isi berkas untuk dibagikan: {format, versi, nama, isi, catatan}. None bila tidak ada."""
    _migrasi()
    p = next((x for x in _baca_semua()[0] if x["id"] == pid), None)
    if p is None:
        return None
    d = {"format": FORMAT, "versi": 1, "nama": p["nama"], "isi": p["isi"]}
    if p["catatan"]:
        d["catatan"] = p["catatan"]
    return d


def impor(teks):
    """Impor prompt dari teks JSON: satu prompt ({nama, isi}), daftar, atau {"prompt": [...]}.

    Kembalian: {"baru": [prompt], "dilewati": [{"nama", "alasan"}]}. Isi yang sama persis dengan yang
    sudah ada dilewati; nama yang sudah dipakai diberi akhiran '(2)'. ValueError bila bukan JSON/format."""
    if len(teks or "") > conf.MAKS_IMPOR_PROMPT:
        raise ValueError("Berkas impor terlalu besar")
    try:
        d = json.loads(teks)
    except (ValueError, TypeError):
        raise ValueError("Bukan berkas JSON yang valid") from None
    if isinstance(d, dict) and "format" in d and d["format"] != FORMAT:
        raise ValueError("Format berkas tidak dikenal (bukan prompt AI Asisten)")
    if isinstance(d, dict) and isinstance(d.get("prompt"), list):
        butir = d["prompt"]
    elif isinstance(d, dict) and "nama" in d:
        butir = [d]
    elif isinstance(d, list):
        butir = d
    else:
        raise ValueError("Isi berkas bukan prompt (butuh nama dan isi)")
    _migrasi()
    baru, lewat = [], []

    def tampil(x):
        return str(x.get("nama") if isinstance(x, dict) else x)[:conf.MAKS_NAMA_PROMPT]
    with _KUNCI:
        ada, _ = _baca_semua()
        ids = {p["id"] for p in ada}
        namas = {p["nama"].lower() for p in ada} | {bawaan()["nama"].lower()}
        for x in butir[:conf.MAKS_PROMPT]:
            try:
                if not isinstance(x, dict):
                    raise ValueError("bukan objek prompt")
                nama, isi, catatan = _periksa(x.get("nama"), x.get("isi"),
                                              x.get("catatan") if isinstance(x.get("catatan"), str) else "")
            except ValueError as e:
                lewat.append({"nama": tampil(x), "alasan": str(e)})
                continue
            if any(p["isi"] == isi for p in ada):
                lewat.append({"nama": nama, "alasan": "sudah ada (isinya sama)"})
                continue
            if len(ada) >= conf.MAKS_PROMPT:
                lewat.append({"nama": nama, "alasan": "daftar prompt penuh"})
                continue
            item = {"id": _id_baru(nama, ids), "nama": _nama_unik(nama, namas), "isi": isi, "catatan": catatan}
            _tulis_item(item)
            ada.append(item)
            ids.add(item["id"])
            namas.add(item["nama"].lower())
            baru.append(dict(item, bawaan=False))
        for x in butir[conf.MAKS_PROMPT:]:
            lewat.append({"nama": tampil(x), "alasan": "melebihi batas"})
    return {"baru": baru, "dilewati": lewat}


# ---------------------------------------------------------------- pemakaian di sesi
def berlaku(skill):
    """Prompt pilihan dipakai hanya bila skill 'tanpa' aktif dan tidak ada skill dengan akses sistem
    (dasar/kompleks), karena skill itu memakai prompt sistem bertool sendiri."""
    s = set(skill or ())
    return "tanpa" in s and not (s & {"dasar", "kompleks"})


def rapikan_pilihan(ids):
    """Daftar id yang valid (yang masih ada) menurut urutan daftar. None bila `ids` None."""
    if ids is None:
        return None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ValueError("Pilihan prompt tidak valid")
    semua = daftar_prompt()
    pilih = set(ids) & {p["id"] for p in semua}
    return [p["id"] for p in semua if p["id"] in pilih]


def rakit(ids):
    """Teks dasar untuk agen.buat_system(dasar=...) dan nama prompt yang dipakai.

    Kembalian: (dasar, nama). dasar None = pakai SYSTEM_CHAT bawaan (cara lama); "" = tanpa prompt;
    selain itu gabungan teks prompt terpilih. Id yang sudah dihapus dilewati; bila pilihan tidak
    kosong tetapi semuanya sudah dihapus, kembali ke bawaan (bukan diam-diam menjadi murni)."""
    if ids is None:
        return None, [bawaan()["nama"]]
    semua = daftar_prompt()
    ada = {p["id"] for p in semua}
    pilih = [i for i in ids if i in ada]
    if ids and not pilih:
        return None, [bawaan()["nama"]]
    urut = [p for p in semua if p["id"] in set(pilih)]
    nama = [p["nama"] for p in urut]
    if not urut:
        return "", []
    if [p["id"] for p in urut] == [conf.PROMPT_BAWAAN]:
        return None, nama
    return "\n\n".join(p["isi"] for p in urut), nama


__all__ = ["FORMAT", "bawaan", "daftar_prompt", "berkas_diabaikan", "tambah_prompt", "ubah_prompt",
           "hapus_prompt", "ekspor", "impor", "berlaku", "rapikan_pilihan", "rakit"]
