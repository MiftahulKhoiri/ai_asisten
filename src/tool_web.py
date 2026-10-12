"""tool_web.py - tool internet: ambil_url, baca_halaman, berita, cari_web."""

import html
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .registri import tool
from .util import MAX_OUTPUT, _boleh_tulis, _fmt, _izin, _p, _tolak_tulis


@tool("ambil_url", "Ambil teks halaman web (http/https); simpan_ke = unduh jadi file.",
      {"url": ("string", "alamat"),
       "simpan_ke": ("string", "(opsional) path file")},
      wajib=["url"], ringkas=lambda a: f"ambil {a.get('url', '')}")
def ambil_url(ctx, url, simpan_ke=""):
    if not re.match(r"^https?://", url.strip(), re.I):
        return "ERROR: hanya alamat http/https yang didukung."
    url = url.strip()
    dst = None
    if simpan_ke:
        dst = _p(simpan_ke)
        if dst.exists():
            return f"ERROR: file tujuan sudah ada: {dst}"
        if not _boleh_tulis(dst):
            return _tolak_tulis(dst)
    t = _izin(ctx, "jaringan", f"GET {url}" + (f"\nsimpan ke {dst}" if dst else ""))
    if t:
        return t
    req = urllib.request.Request(url, headers={"User-Agent": "ai_asisten/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        if dst:
            batas, total = 50 * 1024 * 1024, 0
            dst.parent.mkdir(parents=True, exist_ok=True)
            sementara = dst.with_name(dst.name + ".part")
            try:
                with open(sementara, "wb") as f:
                    while True:
                        potong_ = r.read(65536)
                        if not potong_:
                            break
                        total += len(potong_)
                        if total > batas:
                            raise ValueError("file lebih dari 50 MB, dibatalkan")
                        f.write(potong_)
                sementara.rename(dst)
            finally:
                if sementara.exists():
                    sementara.unlink()
            return f"Terunduh: {dst} ({_fmt(total)})"
        ctype = r.headers.get("Content-Type", "")
        data = r.read(200_000)
        teks = data.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    if "html" in ctype.lower() or teks.lstrip().lower().startswith(("<!doctype", "<html")):
        teks = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", teks)
        teks = re.sub(r"(?s)<[^>]+>", " ", teks)
        teks = html.unescape(teks)
        teks = re.sub(r"[ \t\r\f\v]+", " ", teks)
        teks = re.sub(r"\n\s*\n+", "\n", teks).strip()
    return teks or "(halaman kosong)"


# Keamanan: hanya alamat PUBLIK yang boleh dibuka (alamat lokal/privat/loopback
# ditolak, termasuk lewat pengalihan), supaya isi halaman web tidak bisa menyuruh
# model membuka layanan di jaringan rumah. Isi halaman tetap diperlakukan sebagai
# DATA, bukan perintah (lihat PROMPT_WEB di agen.py).
UA_WEB = ("Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0 Safari/537.36")
WEB_MAKS_BYTE = 600_000


def _cek_publik(url):
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("hanya alamat http/https yang valid")
    try:
        info = socket.getaddrinfo(u.hostname, u.port or (443 if u.scheme == "https" else 80),
                                  proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"alamat tidak ditemukan: {u.hostname}") from None
    for i in info:
        ip = ipaddress.ip_address(i[4][0].split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise ValueError("alamat jaringan lokal/privat tidak diizinkan")


class _Alihan(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _cek_publik(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Alihan)


def _unduh(url, maks=WEB_MAKS_BYTE, timeout=15):
    """(content_type, teks) dari URL publik. ValueError bila ditolak atau gagal."""
    url = url.strip()
    _cek_publik(url)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA_WEB, "Accept-Language": "id,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml,text/plain;q=0.9,*/*;q=0.5"})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            ctype = r.headers.get("Content-Type", "")
            charset = r.headers.get_content_charset() or "utf-8"
            data = r.read(maks)
    except urllib.error.HTTPError as e:
        raise ValueError(f"server membalas HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise ValueError(f"tidak bisa terhubung ({e.reason})") from None
    except (TimeoutError, socket.timeout):
        raise ValueError("waktu habis") from None
    try:
        return ctype, data.decode(charset, errors="replace")
    except LookupError:
        return ctype, data.decode("utf-8", errors="replace")


# tag HTML; atribut bertanda kutip boleh berisi ">" (mis. data JSON di Wikipedia)
_TAG = re.compile(r"""<(?:[^>"']|"[^"]*"|'[^']*')*>""", re.S)


def _bersih(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(_TAG, " ", h))).strip()


def _html_ke_teks(h):
    """(judul, teks) dari HTML; membuang skrip, menu, dan baris pendek."""
    judul = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", h)
    if m:
        judul = _bersih(m.group(1))
    h = re.sub(r"(?is)<(script|style|noscript|svg|nav|header|footer|aside|form|iframe)\b.*?</\1>", " ", h)
    h = re.sub(r"(?s)<!--.*?-->", " ", h)
    h = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|section|article)>|<br\s*/?>", "\n", h)
    h = re.sub(_TAG, " ", h)
    h = html.unescape(h)
    baris = [re.sub(r"[ \t\r\f\v]+", " ", b).strip() for b in h.split("\n")]
    return judul, "\n".join(b for b in baris if len(b) >= 25)


@tool("baca_halaman",
      "Baca isi teks satu halaman web publik (hanya baca). mulai = lanjut dari karakter ke-N.",
      {"url": ("string", "alamat http/https"),
       "mulai": ("integer", "mulai dari karakter ke-N, default 0")},
      wajib=["url"], web=True, ringkas=lambda a: f"baca halaman {a.get('url', '')}")
def baca_halaman(ctx, url, mulai=0):
    try:
        ctype, isi = _unduh(url)
    except ValueError as e:
        return f"ERROR: {e}"
    ct = ctype.lower()
    if "html" in ct or isi.lstrip().lower().startswith(("<!doctype", "<html")):
        judul, teks = _html_ke_teks(isi)
    elif any(k in ct for k in ("text/", "json", "xml")):
        judul, teks = "", isi.strip()
    else:
        return f"(bukan halaman teks: {ctype or 'tipe tidak diketahui'})"
    if len(teks) < 80:
        return ("(halaman hampir kosong; mungkin butuh JavaScript atau diblokir)"
                + (f"\nJudul: {judul}" if judul else ""))
    mulai = max(0, int(mulai))
    if mulai >= len(teks):
        return "(sudah di akhir halaman)"
    potongan = teks[mulai:mulai + MAX_OUTPUT - 260]
    akhir = mulai + len(potongan)
    return ((f"Judul: {judul}\n" if judul and mulai == 0 else "")
            + f"[karakter {mulai}-{akhir} dari {len(teks)}]\n" + potongan
            + (f"\n...[lanjut dengan mulai={akhir}]" if akhir < len(teks) else ""))


def _parse_brave(h, maks):
    """[(judul, url, cuplikan)] dari halaman hasil Brave Search."""
    hasil = []
    for blok in re.split(r'<div class="snippet[^"]*"[^>]*data-type="web"', h)[1:]:
        m = re.search(r'<a href="(https?://[^"]+)"', blok)
        if not m:
            continue
        url = html.unescape(m.group(1))
        if (urllib.parse.urlsplit(url).hostname or "").endswith("brave.com"):
            continue
        t = (re.search(r'class="title[^"]*"[^>]*title="([^"]*)"', blok)
             or re.search(r'class="title[^"]*"[^>]*>(.*?)</div>', blok, re.S))
        if not t:
            continue
        s = re.search(r'class="content[^"]*"[^>]*>(.*?)</div>', blok, re.S)
        hasil.append((_bersih(t.group(1)), url, _bersih(s.group(1)) if s else ""))
        if len(hasil) >= maks:
            break
    return hasil


_PERIODE = {"hari_ini": "1d", "minggu_ini": "7d", "bulan_ini": "30d", "semua": ""}


def _ambil_berita(topik, periode, maks):
    """[(waktu, judul, sumber)] dari Google News RSS, terbaru dulu."""
    topik = (topik or "").strip()
    rentang = _PERIODE.get(periode, "")
    if topik:
        q = topik[:150] + (f" when:{rentang}" if rentang else "")
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
            {"q": q, "hl": "id", "gl": "ID", "ceid": "ID:id"})
    else:
        url = "https://news.google.com/rss?" + urllib.parse.urlencode(
            {"hl": "id", "gl": "ID", "ceid": "ID:id"})
    _, xml = _unduh(url, maks=1_500_000)
    if "<!ENTITY" in xml:
        raise ValueError("format berita tidak aman")
    try:
        akar = ET.fromstring(xml.encode("utf-8"))
    except ET.ParseError:
        raise ValueError("format berita tidak dikenali") from None
    item, lihat = [], set()
    for it in akar.iter("item"):
        judul = (it.findtext("title") or "").strip()
        sumber = (it.findtext("source") or "").strip()
        if sumber and judul.endswith(" - " + sumber):
            judul = judul[:-len(sumber) - 3]
        if not judul or judul.lower() in lihat:
            continue
        lihat.add(judul.lower())
        try:
            waktu = parsedate_to_datetime(it.findtext("pubDate") or "")
            if waktu.tzinfo is None:
                waktu = waktu.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            waktu = None
        item.append((waktu, judul, sumber))
    item.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return item[:maks]


def _umur(waktu, sekarang):
    d = max(0, int((sekarang - waktu).total_seconds()))
    if d < 3600:
        return f"{max(d // 60, 1)} menit lalu"
    if d < 86400:
        return f"{d // 3600} jam lalu"
    return f"{d // 86400} hari lalu"


def _format_berita(item):
    sekarang = datetime.now(timezone.utc)
    baris = []
    for i, (w, judul, sumber) in enumerate(item, 1):
        baris.append(f"{i}. {judul[:110]} - {sumber or 'sumber ?'}" + (f", {_umur(w, sekarang)}" if w else ""))
    return "\n".join(baris)


@tool("berita",
      "Berita terbaru (Google News Indonesia): judul, sumber, umur berita. Tanpa topik = berita utama.",
      {"topik": ("string", "(opsional) kata kunci, mis. banjir jakarta"),
       "periode": ("string", "rentang waktu, default hari_ini",
                   ["hari_ini", "minggu_ini", "bulan_ini", "semua"]),
       "maks": ("integer", "jumlah berita, default 8, maks 12")},
      web=True, ringkas=lambda a: "berita " + (a.get("topik") or "terbaru"))
def berita(ctx, topik="", periode="hari_ini", maks=8):
    maks = max(1, min(int(maks), 12))
    periode = periode if periode in _PERIODE else "hari_ini"
    try:
        item = _ambil_berita(topik, periode, maks)
        catatan = ""
        if not item and topik.strip() and periode == "hari_ini":
            item = _ambil_berita(topik, "minggu_ini", maks)
            catatan = "(tidak ada berita 24 jam terakhir; ini 7 hari terakhir)\n"
    except ValueError as e:
        return f"ERROR: tidak bisa mengambil berita ({e})"
    if not item:
        return "Tidak ada berita untuk topik itu. Coba kata kunci lain atau periode semua."
    return (catatan + _format_berita(item)
            + "\n(sumber: Google News; hanya judul. Isi lengkap: cari_web lalu baca_halaman)")


@tool("cari_web",
      "Cari informasi di internet. Hasil: judul, tautan, cuplikan. Untuk berita terbaru pakai tool berita.",
      {"kueri": ("string", "kata kunci pencarian"),
       "maks": ("integer", "jumlah hasil, default 5, maks 8")},
      wajib=["kueri"], web=True, ringkas=lambda a: f"cari web: {a.get('kueri', '')}")
def cari_web(ctx, kueri, maks=5):
    kueri = (kueri or "").strip()
    if not kueri:
        return "ERROR: kueri kosong."
    maks = max(1, min(int(maks), 8))
    url = "https://search.brave.com/search?" + urllib.parse.urlencode(
        {"q": kueri[:200], "source": "web", "country": "id"})
    galat, hasil = "", []
    try:
        _, h = _unduh(url, maks=900_000)
        hasil = _parse_brave(h, maks)
    except ValueError as e:
        galat = str(e)
    if not hasil:   # cadangan: berita terkait dari Google News
        try:
            item = _ambil_berita(kueri, "semua", maks)
        except ValueError as e:
            return f"ERROR: pencarian gagal ({galat or 'tidak ada hasil'}; cadangan berita: {e})"
        if not item:
            return f"Tidak ada hasil untuk: {kueri}" + (f" ({galat})" if galat else "")
        return "(mesin pencari tidak memberi hasil; ini berita terkait)\n" + _format_berita(item)
    per = (MAX_OUTPUT - 120) // len(hasil)
    baris = []
    for i, (judul, u, cup) in enumerate(hasil, 1):
        judul, u = judul[:80], u[:100]
        sisa = max(40, per - len(judul) - len(u) - 14)
        baris.append(f"{i}. {judul}\n   {u}\n   {cup[:sisa]}")
    return "\n".join(baris)
