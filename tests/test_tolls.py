"""Pengujian src/tolls.py. Jalankan: python3 -m unittest discover -s tests -v"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import pengaman, registri, tolls, tool_sistem, tool_web  # noqa: E402


class Ctx:
    """Pengganti ctx dari asisten.py."""

    def __init__(self, auto=True, izin=True, skill="semua"):
        self.auto, self.izin, self.skill = auto, izin, skill
        self.ditanya = []

    def konfirmasi(self, jenis, ringkas, detail=""):
        self.ditanya.append(jenis)
        return self.izin


def jalan(nama, args=None, **kw):
    return tolls.eksekusi(nama, args or {}, Ctx(**kw))


class TestRegistri(unittest.TestCase):
    def test_skema_valid(self):
        for s in tolls.skema("semua"):
            f = s["function"]
            self.assertTrue(f["name"] and f["description"])
            props = f["parameters"]["properties"]
            for wajib in f["parameters"]["required"]:
                self.assertIn(wajib, props, f["name"])

    def test_jumlah_per_mode(self):
        self.assertEqual(tolls.skema("tanpa"), [])
        self.assertEqual(len(tolls.skema("dasar")), 4)
        self.assertEqual(len(tolls.skema("semua")), len(tolls.REGISTRY))
        dasar = {s["function"]["name"] for s in tolls.skema("dasar")}
        self.assertEqual(dasar, {"jalankan_perintah", "baca_file", "tulis_file", "daftar_folder"})

    def test_tool_baru_terdaftar(self):
        for n in ("waktu_sekarang", "bandingkan_file", "ukuran_folder", "cek_sintaks"):
            self.assertIn(n, tolls.REGISTRY)

    def test_mode_membatasi_eksekusi(self):
        self.assertTrue(jalan("hitung", {"ekspresi": "1+1"}, skill="tanpa").startswith("ERROR"))
        self.assertTrue(jalan("hitung", {"ekspresi": "1+1"}, skill="dasar").startswith("ERROR"))
        self.assertIn("= 2", jalan("hitung", {"ekspresi": "1+1"}))

    def test_tool_tak_dikenal_dan_argumen_hilang(self):
        self.assertTrue(jalan("tidak_ada").startswith("ERROR"))
        self.assertIn("wajib", jalan("baca_file"))


class TestHitung(unittest.TestCase):
    def test_hitung(self):
        self.assertIn("= 14", jalan("hitung", {"ekspresi": "2+3*4"}))
        self.assertIn("= 1024", jalan("hitung", {"ekspresi": "2^10"}))
        self.assertIn("= 4", jalan("hitung", {"ekspresi": "sqrt(16)"}))

    def test_hitung_ditolak(self):
        self.assertIn("nol", jalan("hitung", {"ekspresi": "1/0"}))
        self.assertTrue(jalan("hitung", {"ekspresi": "__import__('os')"}).startswith("ERROR"))
        self.assertTrue(jalan("hitung", {"ekspresi": "2**100000"}).startswith("ERROR"))


class TestFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_tulis_baca_edit(self):
        f = self.d / "a.txt"
        self.assertIn("Berhasil", jalan("tulis_file", {"path": str(f), "isi": "satu\ndua\n"}))
        self.assertIn("dua", jalan("baca_file", {"path": str(f)}))
        self.assertIn("Berhasil", jalan("edit_file", {"path": str(f), "lama": "dua", "baru": "tiga"}))
        self.assertIn("tiga", f.read_text())
        self.assertTrue((self.d / "a.txt.bak").exists())

    def test_edit_tidak_unik(self):
        f = self.d / "b.txt"
        f.write_text("x x")
        self.assertIn("2 kali", jalan("edit_file", {"path": str(f), "lama": "x", "baru": "y"}))

    def test_tulis_di_luar_akar_ditolak(self):
        r = jalan("tulis_file", {"path": "/etc/asisten_tes.txt", "isi": "x"})
        self.assertTrue(r.startswith("DITOLAK"))

    def test_tulis_dibatalkan_bila_izin_ditolak(self):
        f = self.d / "c.txt"
        ctx = Ctx(auto=False, izin=False)
        r = tolls.eksekusi("tulis_file", {"path": str(f), "isi": "x"}, ctx)
        self.assertTrue(r.startswith("DIBATALKAN"))
        self.assertFalse(f.exists())

    def test_token_tidak_bisa_dibaca(self):
        f = self.d / ".token"
        f.write_text("rahasia")
        self.assertTrue(jalan("baca_file", {"path": str(f)}).startswith("DITOLAK"))
        self.assertTrue(jalan("cek_sintaks", {"path": str(f)}).startswith("DITOLAK"))

    def test_hapus_selalu_minta_izin(self):
        f = self.d / "d.txt"
        f.write_text("x")
        ctx = Ctx(auto=True, izin=False)   # AUTO aktif, tetap harus bertanya
        r = tolls.eksekusi("hapus", {"path": str(f)}, ctx)
        self.assertTrue(r.startswith("DIBATALKAN"))
        self.assertEqual(ctx.ditanya, ["hapus"])
        self.assertTrue(f.exists())


class TestShellDanGit(unittest.TestCase):
    def test_perintah_berbahaya_diblokir(self):
        self.assertTrue(jalan("jalankan_perintah", {"perintah": "rm -rf /"}).startswith("DITOLAK"))

    def test_perintah_biasa(self):
        self.assertEqual(jalan("jalankan_perintah", {"perintah": "echo halo"}), "exit code 0\nhalo")

    def test_sudo_selalu_tanya(self):
        ctx = Ctx(auto=True, izin=False)
        r = tolls.eksekusi("jalankan_perintah", {"perintah": "sudo true"}, ctx)
        self.assertTrue(r.startswith("DIBATALKAN"))
        self.assertEqual(ctx.ditanya, ["shell"])

    def test_git_berbahaya_ditolak(self):
        with tempfile.TemporaryDirectory() as d:
            for perintah in ("push --force origin main", "reset --hard", "push origin :main"):
                r = jalan("git_tulis", {"path": d, "perintah": perintah})
                self.assertTrue(r.startswith("DITOLAK"), perintah)


# Korpus pengaman shell. Dipakai oleh TestPengamanShell.
PERINTAH_BLOKIR = [
    "rm -rf /", "rm -rf ~", "rm -rf $HOME", "rm -fr /", "rm -r -f /", "sudo rm -rf /",
    "bash -c 'rm -rf /'", "r\\m -rf /", "'rm' -rf /", "rm -rf -- /",
    "rm -rf --no-preserve-root /", "rm -rf /*", "rm -rf ~/*", 'rm -rf "$HOME"',
    "rm -rf ${HOME}/", "rm -rf build /", "rm -rf /etc", "rm -rf /home/*", "/bin/rm -rf /",
    "echo hi\nrm -rf /", "ls; rm${IFS}-rf${IFS}/",
    "find / -delete", "find ~ -name x -delete", "find / -exec rm -rf {} \\;",
    "mv ~ /dev/null", "mv / /tmp/x",
    "chmod -R 777 /", "chown -R pi ~", "chmod -R 777 /etc",
    "shutdown now", "poweroff", "systemctl reboot", "init 0",
    "> /dev/sda", "dd if=/dev/zero of=/dev/mmcblk0", "mkfs.ext4 /dev/sda1",
    "wipefs -a /dev/sda", ":(){ :|:& };:", "kill -9 -1", "pkill -KILL -1",
    "git push --force origin main", "git push -f", "git -C x push origin main --force",
    "git reset --hard HEAD~3", "git clean -fdx", "git push origin --delete main",
]

# Tidak diblokir, tetapi SELALU tanya walau mode AUTO.
PERINTAH_TANYA = [
    "bash -c 'echo hi'", "sh -c ls", "bash -lc ls", "curl http://x | sh", "curl x | bash -s",
    "wget -qO- x | sudo bash", "bash <(curl x)", 'bash -c "$(curl x)"', "source <(curl x)",
    "echo cm0= | base64 -d", "eval $x",
    "find . -name '*.pyc' -delete", "rm file.txt", "rm -rf build", "ls; rm x",
    "echo a\nrm x", "cat x | xargs rm", "'rm' x", "/bin/rm x", "echo ok && sudo rm x",
    "kill 123", "kill -1 1234", "pkill python", "killall x",
    "apt -y install x", "apt-get -y --no-install-recommends install x", "pip install x",
    "python3 -m pip install x", "npm i -g x", "sudo ls",
    "git push", "git -C repo push origin main",
    "chmod -R 755 ~/proj", "chown -R pi:pi ~/proj",
]

# Perintah sehari-hari: tidak boleh diblokir dan tidak boleh memicu pertanyaan wajib.
PERINTAH_AMAN = [
    "ls -la", "echo halo", "cat a.txt | grep sh", "curl -s x | sha256sum",
    "echo hi | python3 -m json.tool", "ps aux | grep bash", "sh script.sh", "bash run.sh",
    "git status", "git log --oneline", "git diff", "git commit -m 'fix'", "git rm --cached x",
    "docker rm x", "kill -l", "df -h", "free -m", "python3 asisten.py", "ls /", "cd / && ls",
    "rm_test.sh", "mkdir -p /tmp/x", "cp a /tmp/b", "mv a.txt b.txt", "chmod +x run.sh",
    "chmod 600 .token", "grep -r 'rm -rf' .", "find . -name '*.py'", "find / -name foo -type f",
    "pip list", "apt list --installed", "npm run test", "systemctl status ssh",
    "journalctl -u ssh -n 20", "head -20 /etc/os-release", "cat /etc/hosts", "ls /home",
    "du -sh /var/log", "echo $HOME", "tail -f /var/log/syslog", "arm-none-eabi-gcc x.c",
    "ssh pi@host ls", "tar -czf a.tgz ~/proj", "cd ~ && ls",
]


class TestPengamanShell(unittest.TestCase):
    """Pengaman jalankan_perintah. `_run` dipalsukan: tidak ada perintah yang sungguh jalan."""

    def test_klasifikasi(self):
        for daftar, harap in ((PERINTAH_BLOKIR, "blokir"), (PERINTAH_TANYA, "izin"),
                              (PERINTAH_AMAN, None)):
            for perintah in daftar:
                with self.subTest(perintah=perintah):
                    self.assertEqual(tolls.cek_perintah(perintah), harap)

    def test_blokir_tidak_dijalankan(self):
        for perintah in PERINTAH_BLOKIR:
            with self.subTest(perintah=perintah):
                with mock.patch.object(tool_sistem, "_run", return_value=(0, "")) as run:
                    ctx = Ctx(auto=True, izin=True)
                    r = tolls.eksekusi("jalankan_perintah", {"perintah": perintah}, ctx)
                self.assertTrue(r.startswith("DITOLAK"), r)
                run.assert_not_called()
                self.assertEqual(ctx.ditanya, [])   # ditolak tanpa bertanya

    def test_tanya_wajib_walau_auto(self):
        for perintah in PERINTAH_TANYA:
            with self.subTest(perintah=perintah):
                with mock.patch.object(tool_sistem, "_run", return_value=(0, "")) as run:
                    ctx = Ctx(auto=True, izin=False)   # AUTO aktif, pengguna menolak
                    r = tolls.eksekusi("jalankan_perintah", {"perintah": perintah}, ctx)
                self.assertTrue(r.startswith("DIBATALKAN"), r)
                self.assertEqual(ctx.ditanya, ["shell"])
                run.assert_not_called()

    def test_tanya_lalu_setuju_dijalankan(self):
        with mock.patch.object(tool_sistem, "_run", return_value=(0, "ok")) as run:
            ctx = Ctx(auto=True, izin=True)
            r = tolls.eksekusi("jalankan_perintah", {"perintah": "rm file.txt"}, ctx)
        self.assertEqual(ctx.ditanya, ["shell"])
        run.assert_called_once()
        self.assertEqual(r, "exit code 0\nok")

    def test_aman_di_auto_tidak_bertanya(self):
        with mock.patch.object(tool_sistem, "_run", return_value=(0, "ok")):
            ctx = Ctx(auto=True, izin=False)
            r = tolls.eksekusi("jalankan_perintah", {"perintah": "ls -la"}, ctx)
        self.assertEqual(ctx.ditanya, [])
        self.assertEqual(r, "exit code 0\nok")

    def test_mode_biasa_selalu_tanya(self):
        with mock.patch.object(tool_sistem, "_run", return_value=(0, "ok")):
            ctx = Ctx(auto=False, izin=False)
            r = tolls.eksekusi("jalankan_perintah", {"perintah": "ls -la"}, ctx)
        self.assertTrue(r.startswith("DIBATALKAN"))
        self.assertEqual(ctx.ditanya, ["shell"])


class TestStruktur(unittest.TestCase):
    """Susunan modul src/: fasad tolls.py, urutan tool, dan arah impor antar modul."""
    SRC = Path(__file__).resolve().parent.parent / "src"
    URUTAN = ["jalankan_perintah", "baca_file", "tulis_file", "daftar_folder", "pohon_folder",
              "info_file", "cari_file", "cari_teks", "baca_ekor", "info_sistem", "git_baca",
              "git_tulis", "edit_file", "buat_folder", "salin_pindah", "hapus", "ambil_url",
              "matikan_proses", "arsip", "hitung", "waktu_sekarang", "bandingkan_file",
              "ukuran_folder", "cek_sintaks", "baca_halaman", "berita", "cari_web"]

    def test_urutan_tool_tetap(self):
        # urutan memengaruhi skema yang dikirim ke model, jangan berubah diam-diam
        self.assertEqual(list(tolls.REGISTRY)[:len(self.URUTAN)], self.URUTAN)

    def test_fasad_membuka_nama_publik(self):
        for nama in ("REGISTRY", "MAX_OUTPUT", "SKILL_IDS", "eksekusi", "ringkas", "skema",
                     "mode_ctx", "mode_awal", "normal_skill", "nama_tool_aktif",
                     "cek_perintah"):
            self.assertTrue(hasattr(tolls, nama), nama)
        self.assertIs(tolls.cek_perintah, pengaman.cek_perintah)
        self.assertIs(tolls.REGISTRY, registri.REGISTRY)

    def test_tiap_tool_hidup_di_modul_tool(self):
        for nama, entri in tolls.REGISTRY.items():
            self.assertRegex(entri["fn"].__module__, r"^src\.tool_", nama)

    def test_tool_di_luar_daftar_ditaruh_di_belakang(self):
        @registri.tool("tool_uji_sementara", "hanya untuk pengujian")
        def tool_uji_sementara(ctx):
            return "ok"
        try:
            tolls._urutkan_registri()
            self.assertEqual(list(tolls.REGISTRY)[-1], "tool_uji_sementara")
            self.assertEqual(list(tolls.REGISTRY)[:len(self.URUTAN)], self.URUTAN)
        finally:
            tolls.REGISTRY.pop("tool_uji_sementara", None)

    def test_arah_impor_tanpa_lingkaran(self):
        dasar = {"pengaman", "registri", "util"}
        for f in self.SRC.glob("*.py"):
            teks = f.read_text(encoding="utf-8")
            if f.stem == "tolls":
                continue
            self.assertNotRegex(teks, r"from \.tolls import|from \. import[^\n]*\btolls\b|import tolls",
                                f.name)       # hanya fasad yang boleh mengenal semua modul
            if f.stem in dasar:               # lapisan dasar tidak boleh mengimpor tool_*
                self.assertNotRegex(teks, r"from \.tool_|import tool_", f.name)
        self.assertNotIn("from .registri", (self.SRC / "pengaman.py").read_text(encoding="utf-8"))


class TestToolBaru(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_waktu_sekarang(self):
        self.assertRegex(jalan("waktu_sekarang"), r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

    def test_cek_sintaks(self):
        ok, salah = self.d / "ok.py", self.d / "salah.py"
        ok.write_text("x = 1\n")
        salah.write_text("def f(:\n")
        self.assertIn("Sintaks OK", jalan("cek_sintaks", {"path": str(ok)}))
        self.assertIn("SINTAKS SALAH di baris 1", jalan("cek_sintaks", {"path": str(salah)}))
        j = self.d / "x.json"
        j.write_text("{bukan json")
        self.assertIn("TIDAK VALID", jalan("cek_sintaks", {"path": str(j)}))
        j.write_text('{"a": 1}')
        self.assertIn("Sintaks OK", jalan("cek_sintaks", {"path": str(j)}))
        sh = self.d / "s.sh"
        sh.write_text("if then\n")
        self.assertIn("SINTAKS SALAH", jalan("cek_sintaks", {"path": str(sh)}))
        t = self.d / "x.txt"
        t.write_text("x")
        self.assertTrue(jalan("cek_sintaks", {"path": str(t)}).startswith("ERROR"))

    def test_bandingkan_file(self):
        a, b = self.d / "a.txt", self.d / "b.txt"
        a.write_text("satu\ndua\n")
        b.write_text("satu\ntiga\n")
        self.assertEqual(jalan("bandingkan_file", {"file_a": str(a), "file_b": str(a)}),
                         "Kedua file identik.")
        r = jalan("bandingkan_file", {"file_a": str(a), "file_b": str(b)})
        self.assertIn("-dua", r)
        self.assertIn("+tiga", r)

    def test_bandingkan_file_biner(self):
        a, b = self.d / "a.bin", self.d / "b.txt"
        a.write_bytes(b"\0\1\2")
        b.write_text("x")
        self.assertIn("biner", jalan("bandingkan_file", {"file_a": str(a), "file_b": str(b)}))

    def test_ukuran_folder(self):
        (self.d / "besar.txt").write_text("x" * 5000)
        (self.d / "sub").mkdir()
        (self.d / "sub" / "kecil.txt").write_text("y" * 10)
        r = jalan("ukuran_folder", {"path": str(self.d)})
        self.assertIn("2 entri", r)
        self.assertLess(r.index("besar.txt"), r.index("sub/"))   # terbesar di atas
        self.assertTrue(jalan("ukuran_folder", {"path": str(self.d / "tidak_ada")}).startswith("ERROR"))


class TestSkill(unittest.TestCase):
    def test_normal_skill(self):
        self.assertEqual(tolls.normal_skill("semua"), ("kompleks",))
        self.assertEqual(tolls.normal_skill("kritis+web"), ("web", "kritis"))
        self.assertEqual(tolls.normal_skill(["kritis", "tanpa"]), ("tanpa", "kritis"))
        self.assertEqual(tolls.normal_skill("ngawur"), (tolls.mode_awal(),))
        self.assertEqual(tolls.normal_skill(None), (tolls.mode_awal(),))

    def test_gabungan_tool(self):
        web = set(tolls.nama_tool_aktif("web"))
        dasar = set(tolls.nama_tool_aktif("dasar"))
        self.assertEqual(web, {"cari_web", "berita", "baca_halaman", "waktu_sekarang"})
        self.assertEqual(set(tolls.nama_tool_aktif(["web", "dasar"])), web | dasar)
        self.assertEqual(tolls.nama_tool_aktif(["tanpa", "web"]), tolls.nama_tool_aktif("web"))
        self.assertEqual(tolls.nama_tool_aktif("kritis"), [])
        self.assertEqual(tolls.nama_tool_aktif(["tanpa", "kritis"]), [])
        self.assertEqual(len(tolls.nama_tool_aktif("kompleks")), len(tolls.REGISTRY))

    def test_eksekusi_mengikuti_skill(self):
        self.assertTrue(jalan("hitung", {"ekspresi": "1+1"}, skill=("web",)).startswith("ERROR"))
        self.assertRegex(jalan("waktu_sekarang", skill=("web", "kritis")), r"\d{4}-\d{2}-\d{2}")
        self.assertIn("= 2", jalan("hitung", {"ekspresi": "1+1"}, skill=("dasar", "kompleks")))
        self.assertTrue(jalan("waktu_sekarang", skill=("tanpa", "kritis")).startswith("ERROR"))


def _rss(*item):
    isi = "".join(f"<item><title>{j}</title><pubDate>{format_datetime(w, usegmt=True)}</pubDate>"
                  f"<source url='https://x.id'>{s}</source></item>" for j, s, w in item)
    return f'<?xml version="1.0" encoding="UTF-8"?><rss><channel>{isi}</channel></rss>'


BRAVE = (
    '<div class="snippet svelte-x" data-pos="1" data-type="web" data-keynav="true"><div class="result-body">'
    '<a href="https://contoh.id/emas" class="l1"><div class="title search-snippet-title svelte-y" '
    'title="Harga Emas &amp; Perak">Harga Emas</div></a><div class="generic-snippet">'
    '<div class="content desktop-default-regular t-primary"><span>1 hari lalu -</span> Harga '
    '<strong>naik</strong> hari ini.</div></div></div></div>'
    '<div class="snippet svelte-x" data-pos="2" data-type="web"><a href="https://search.brave.com/iklan" '
    'class="l1"><div class="title" title="Iklan">Iklan</div></a></div>'
    '<div class="snippet svelte-x" data-pos="3" data-type="web"><a href="https://kedua.com/x">'
    '<div class="title svelte" title="Kedua">Kedua</div></a><div class="content">Cuplikan kedua</div></div>')


class TestWeb(unittest.TestCase):
    def test_hanya_alamat_publik(self):
        for u in ("http://127.0.0.1:8080/", "http://localhost/", "http://192.168.1.1/", "http://10.0.0.5",
                  "http://[::1]/", "http://169.254.169.254/", "file:///etc/passwd", "ftp://contoh.com/a"):
            with self.assertRaises(ValueError, msg=u):
                tool_web._cek_publik(u)

    def test_baca_halaman_menolak_alamat_lokal(self):
        r = jalan("baca_halaman", {"url": "http://127.0.0.1:8080"}, skill=("web",))
        self.assertTrue(r.startswith("ERROR"))
        self.assertIn("lokal", r)

    def test_html_ke_teks(self):
        judul, teks = tool_web._html_ke_teks(
            '<html><head><title>Judul Uji</title><script>var x=1;</script></head><body>'
            '<nav>menu menu menu menu menu menu menu</nav>'
            '<p>Ini paragraf pertama yang cukup panjang untuk dibaca.</p>'
            '<p data-x="a>b">Paragraf kedua juga cukup panjang untuk dipertahankan.</p></body></html>')
        self.assertEqual(judul, "Judul Uji")
        self.assertIn("paragraf pertama", teks)
        self.assertIn("Paragraf kedua", teks)
        self.assertNotIn("var x", teks)
        self.assertNotIn("menu menu", teks)
        self.assertNotIn("a>b", teks)

    def test_parse_brave(self):
        hasil = tool_web._parse_brave(BRAVE, 5)
        self.assertEqual(len(hasil), 2)   # iklan brave.com dilewati
        self.assertEqual(hasil[0], ("Harga Emas & Perak", "https://contoh.id/emas",
                                    "1 hari lalu - Harga naik hari ini."))
        self.assertEqual(hasil[1][2], "Cuplikan kedua")

    def test_cari_web(self):
        with mock.patch.object(tool_web, "_unduh", return_value=("text/html", BRAVE)):
            r = jalan("cari_web", {"kueri": "harga emas"}, skill=("web",))
        self.assertIn("1. Harga Emas & Perak", r)
        self.assertIn("https://contoh.id/emas", r)
        self.assertLessEqual(len(r), tolls.MAX_OUTPUT)
        self.assertTrue(jalan("cari_web", {"kueri": "  "}, skill=("web",)).startswith("ERROR"))

    def test_berita_terbaru_dulu_tanpa_duplikat(self):
        sekarang = datetime.now(timezone.utc)
        rss = _rss(("Berita lama - Kompas", "Kompas", sekarang - timedelta(hours=5)),
                   ("Berita baru - Detik", "Detik", sekarang - timedelta(hours=2)),
                   ("Berita baru - Detik", "Detik", sekarang - timedelta(hours=2)))
        with mock.patch.object(tool_web, "_unduh", return_value=("application/xml", rss)):
            r = jalan("berita", {}, skill=("web",))
        baris = r.splitlines()
        self.assertTrue(baris[0].startswith("1. Berita baru - Detik, 2 jam lalu"), baris[0])
        self.assertTrue(baris[1].startswith("2. Berita lama - Kompas, 5 jam lalu"), baris[1])
        self.assertEqual(sum(1 for b in baris if b[:2] in ("1.", "2.", "3.")), 2)

    def test_berita_gagal_jaringan(self):
        with mock.patch.object(tool_web, "_unduh", side_effect=ValueError("waktu habis")):
            self.assertTrue(jalan("berita", {}, skill=("web",)).startswith("ERROR"))

    def test_cari_web_cadangan_berita(self):
        sekarang = datetime.now(timezone.utc)
        rss = _rss(("Kabar emas - Antara", "Antara", sekarang - timedelta(hours=1)))

        def palsu(url, maks=0, timeout=0):
            if "brave" in url:
                raise ValueError("server membalas HTTP 429")
            return "application/xml", rss
        with mock.patch.object(tool_web, "_unduh", side_effect=palsu):
            r = jalan("cari_web", {"kueri": "emas"}, skill=("web",))
        self.assertTrue(r.startswith("(mesin pencari tidak memberi hasil"))
        self.assertIn("Kabar emas", r)


if __name__ == "__main__":
    unittest.main()
