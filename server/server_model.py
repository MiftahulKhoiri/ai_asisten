"""server_model.py - daftar model, muat/bongkar di llama-server, idle, dan sesi."""

import re
import threading
import time
import urllib.error
import agen
from . import server_config as conf
from . import server_log as lg
from . import server_state as state


def _galat_singkat(e):
    """Penyebab singkat sebuah koneksi gagal (tanpa kunci atau isi jawaban)."""
    if isinstance(e, urllib.error.HTTPError):
        return ("ditolak (%d): periksa API key" % e.code) if e.code in (401, 403) else ("galat server %d" % e.code)
    if isinstance(e, urllib.error.URLError):
        return "tidak bisa terhubung"
    return type(e).__name__


def _daftar_satu(cid):
    """Model dari satu koneksi. Kunci model koneksi tambahan diberi awalan id koneksinya."""
    s = agen.sambungan(cid)
    if cid == agen.KONEKSI_UTAMA:
        data = agen.llama("/v1/models", timeout=10)["data"]
    else:
        data = agen.llama("/v1/models", timeout=10, koneksi=cid)["data"]
    hasil = []
    for m in data:
        if not isinstance(m, dict) or not isinstance(m.get("id"), str):
            continue
        mb = None
        if cid == agen.KONEKSI_UTAMA:       # folder model lokal hanya cocok untuk koneksi utama
            f = conf.MODELS_DIR / (m["id"] + ".gguf")
            mb = round(f.stat().st_size / 1048576) if f.exists() else None
        hasil.append({"id": agen.kunci_model(cid, m["id"]), "nama": m["id"], "mb": mb,
                      "llama": (m.get("status") or {}).get("value"),
                      "koneksi": cid, "jenis": s["jenis"], "sumber": s["nama"]})
    router = any(h["llama"] for h in hasil)
    for h in hasil:
        h["router"] = router
    hasil.sort(key=lambda x: x["mb"] or 0)
    return hasil


def daftar_model():
    """Semua model dari semua koneksi (utama dulu, lalu tambahan), dikelompokkan per koneksi.
    Koneksi yang gagal dilewati dan dicatat di state.KONEKSI_STATUS; bila SEMUA gagal, galat koneksi
    utama dilempar (perilaku lama, saat hanya ada satu koneksi)."""
    ids = [agen.KONEKSI_UTAMA] + list(agen.LLAMA_EXTRA)
    hasil_per, galat = {}, {}

    def ambil(cid):
        try:
            hasil_per[cid] = _daftar_satu(cid)
        except Exception as e:  # noqa: BLE001
            galat[cid] = e

    if len(ids) == 1:
        ambil(ids[0])
    else:
        ts = [threading.Thread(target=ambil, args=(c,), daemon=True) for c in ids]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
    status = {}
    for cid in ids:
        if cid in hasil_per:
            status[cid] = {"ok": True, "jumlah": len(hasil_per[cid]), "galat": ""}
        else:
            status[cid] = {"ok": False, "jumlah": 0, "galat": _galat_singkat(galat[cid])}
    state.KONEKSI_STATUS.clear()
    state.KONEKSI_STATUS.update(status)
    if not hasil_per:
        raise galat[ids[0]]
    hasil = []
    for cid in ids:
        hasil += hasil_per.get(cid, [])
    return hasil


def nama_tampil(kunci):
    """Nama model untuk ditampilkan: model koneksi utama (llama-server) apa adanya, selain itu diberi nama koneksinya."""
    if not kunci:
        return kunci
    cid, nama = agen.pecah_model(kunci)
    s = agen.sambungan(cid)
    return nama if cid == agen.KONEKSI_UTAMA and s["jenis"] != "online" else "%s · %s" % (nama, s["nama"])


def router_aktif(models):
    """True bila server punya mode router (tiap model membawa status loaded/unloaded dan bisa
    dimuat/dibongkar). Server satu-model dan penyedia online tidak punya status itu."""
    return any(m.get("llama") for m in models)


_POTONGAN_GGUF = re.compile(r"-(\d+)-of-\d+$")


def berkas_belum_dikenal(ids):
    """Nama berkas .gguf di MODELS_DIR yang belum terdaftar di llama-server.

    llama-server (mode router) membaca folder model saat dinyalakan, jadi berkas yang
    ditambahkan sesudahnya baru muncul setelah llama-server dijalankan ulang.
    """
    dikenal = set(ids)
    try:
        berkas = sorted(conf.MODELS_DIR.glob("*.gguf"))
    except OSError:
        return []
    hasil = []
    for f in berkas:
        nama = f.stem
        if nama.lower().startswith("mmproj"):   # berkas pendamping gambar, bukan model
            continue
        m = _POTONGAN_GGUF.search(nama)
        if m and int(m.group(1)) != 1:          # potongan ke-2 dst. dari model terbelah
            continue
        if nama not in dikenal:
            hasil.append(nama)
    return hasil


def status_llama(nama):
    for m in _daftar_satu(agen.pecah_model(nama)[0]):
        if m["id"] == nama:
            return m["llama"]
    return None


def _unload(nama):
    try:
        agen.llama("/models/unload", {"model": nama}, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code != 400:  # 400 = model memang tidak berjalan
            raise


def muat_model(nama):
    with state.S_LOCK:
        lama, lama_kita = state.S["model"], state.S["kita_muat"]
        state.S.update(status="memuat", target=nama, model=None,
                 pesan=f"Menyiapkan {nama} ...", kita_muat=False)
    dimuat_kita = False
    try:
        if lama and lama_kita and lama != nama:
            lg.log("INFO", f"Membongkar model sebelumnya: {lama}")
            _unload(lama)
        info = {m["id"]: m for m in daftar_model()}
        if nama not in info:
            raise RuntimeError("Model tidak ditemukan di llama-server")
        awal = info[nama]["llama"]
        if not info[nama].get("router", router_aktif(list(info.values()))):
            lg.log("INFO", f"Server tanpa mode router: {nama} dipakai langsung (tanpa muat/bongkar)")
        elif awal != "loaded":
            lg.log("INFO", f"Memuat model {nama} ...")
            if awal != "loading":
                agen.llama("/models/load", {"model": nama}, timeout=30)
            dimuat_kita = True
            mulai = time.time()
            while True:
                time.sleep(2)
                st = status_llama(nama)
                with state.S_LOCK:
                    state.S["pesan"] = f"Memuat {nama} ... {int(time.time() - mulai)} dtk"
                if st == "loaded":
                    break
                if st == "failed":
                    raise RuntimeError("llama-server gagal memuat model")
                if time.time() - mulai > 300:
                    raise RuntimeError("Model belum siap setelah 5 menit")
            lg.log("OK", f"Model siap: {nama} ({int(time.time() - mulai)} dtk)")
        elif lama == nama and lama_kita:
            dimuat_kita = True
        else:
            lg.log("INFO", f"{nama} sudah termuat oleh pihak lain; dipakai, tidak akan dibongkar")
        with state.S_LOCK:
            state.S.update(model=nama, status="siap", pesan="", target=None,
                     kita_muat=dimuat_kita, aktivitas=time.time())
    except Exception as e:  # noqa: BLE001
        lg.log("ERR", f"Gagal memuat {nama}: {e}")
        if dimuat_kita:
            try:
                _unload(nama)
            except Exception:  # noqa: BLE001
                pass
        with state.S_LOCK:
            state.S.update(model=None, status="error", pesan=str(e), target=None,
                     kita_muat=False)


def bongkar_model():
    with state.S_LOCK:
        nama, kita, target = state.S["model"], state.S["kita_muat"], state.S["target"]
    if nama and kita:
        try:
            _unload(nama)
            lg.log("OK", f"Model dibongkar dari memori: {nama}")
        except Exception as e:  # noqa: BLE001
            lg.log("ERR", f"Gagal membongkar {nama}: {e}")
    elif nama:
        lg.log("INFO", f"{nama} tidak dibongkar (bukan dimuat oleh aplikasi ini)")
    elif target:
        try:
            _unload(target)
            lg.log("OK", f"Pemuatan {target} dibatalkan")
        except Exception:  # noqa: BLE001
            pass
    with state.S_LOCK:
        state.S.update(model=None, status="kosong", pesan="", target=None, kita_muat=False)


def selesai_sesi():
    ctx = state.AKTIF.get("ctx")
    if ctx:
        ctx.batal.set()
        for _ in range(50):
            if not state.GEN_LOCK.locked():
                break
            time.sleep(0.1)
    bongkar_model()


def jaga_idle():
    while True:
        time.sleep(30)
        if conf.IDLE_MENIT <= 0:
            continue
        with state.S_LOCK:
            siap = state.S["status"] == "siap"
            idle = time.time() - state.S["aktivitas"]
        if siap and not state.GEN_LOCK.locked() and idle > conf.IDLE_MENIT * 60:
            lg.log("WARN", f"Tidak ada aktivitas {conf.IDLE_MENIT} menit, model dibongkar otomatis")
            bongkar_model()


def sentuh():
    with state.S_LOCK:
        state.S["aktivitas"] = time.time()


__all__ = ['daftar_model', 'nama_tampil', 'router_aktif', 'berkas_belum_dikenal', 'status_llama', '_unload', 'muat_model', 'bongkar_model', 'selesai_sesi', 'jaga_idle', 'sentuh', '_POTONGAN_GGUF']
