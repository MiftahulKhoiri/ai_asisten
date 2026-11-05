"""Pemeriksaan statis tampilan web (tanpa browser)."""
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WEB = Path(__file__).resolve().parent.parent / "web"


class TestWeb(unittest.TestCase):
    def test_id_di_js_ada_di_html(self):
        js = (WEB / "index.js").read_text(encoding="utf-8")
        html = (WEB / "index.html").read_text(encoding="utf-8")
        dipakai = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", js))
        ada = set(re.findall(r'id="([^"]+)"', html))
        self.assertGreater(len(dipakai), 20)
        self.assertEqual(sorted(dipakai - ada), [])

    def test_layar_dinamis_ada(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for n in ("token", "model", "chat"):
            self.assertIn(f'id="layar_{n}"', html)

    def test_berkas_yang_dirujuk_ada(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="([^"]+)"', html):
            if ref == "/":       # tautan ke dasbor (rute server, bukan berkas)
                continue
            self.assertTrue((WEB / ref).is_file(), ref)

    def test_sintaks_js(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, "--check", str(WEB / "index.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestWebAgent(unittest.TestCase):
    def test_id_di_js_ada_di_html(self):
        js = (WEB / "agent.js").read_text(encoding="utf-8")
        html = (WEB / "agent.html").read_text(encoding="utf-8")
        dipakai = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", js))
        ada = set(re.findall(r'id="([^"]+)"', html))
        self.assertGreater(len(dipakai), 20)
        self.assertEqual(sorted(dipakai - ada), [])

    def test_id_dinamis_ada(self):
        html = (WEB / "agent.html").read_text(encoding="utf-8")
        for n in ("token", "setup", "kerja"):
            self.assertIn(f'id="layar_{n}"', html)
        for n in ("rencana", "tulis", "periksa", "jelaskan"):
            self.assertIn(f'id="st_{n}"', html)

    def test_berkas_yang_dirujuk_ada(self):
        html = (WEB / "agent.html").read_text(encoding="utf-8")
        refs = re.findall(r'(?:href|src)="([^"]+)"', html)
        self.assertIn("agent.js", refs)
        for ref in refs:
            if ref == "/":       # tautan ke dasbor (rute server, bukan berkas)
                continue
            self.assertTrue((WEB / ref).is_file(), ref)

    def test_tombol_agent_di_halaman_chat(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="agent.html"', html)

    def test_halaman_terdaftar_di_server(self):
        import asisten
        for rute, nama in (("/agent.html", "agent.html"), ("/agent.css", "agent.css"),
                           ("/agent.js", "agent.js")):
            self.assertEqual(asisten.STATIS[rute][0], nama)
            self.assertTrue((WEB / nama).is_file())

    def test_sintaks_js(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, "--check", str(WEB / "agent.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestLayarMulai(unittest.TestCase):
    """Layar awal chat: pilih skill -> pilih model -> tekan Mulai (model baru dimuat setelah Mulai)."""

    def test_html_memiliki_tiga_langkah_dan_tombol_mulai(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for pasti in ("1. Pilih skill", "2. Pilih model", "3. Mulai", 'id="btnMulai"', 'id="mulaiKet"',
                      'role="radiogroup"'):
            self.assertIn(pasti, html)
        self.assertLess(html.index('id="skillBox"'), html.index('id="daftarModel"'))
        self.assertLess(html.index('id="daftarModel"'), html.index('id="btnMulai"'))
        # daftar model ada di dalam panel tertutup di balik tombol
        self.assertLess(html.index('id="btnDaftarModel"'), html.index('id="modelPanel"'))
        self.assertLess(html.index('id="modelPanel"'), html.index('id="daftarModel"'))
        self.assertRegex(html, r'<div id="modelPanel" hidden>')

    def test_mengetuk_model_tidak_lagi_memuat_langsung(self):
        js = (WEB / "index.js").read_text(encoding="utf-8")
        self.assertIn("b.onclick = () => pilihTanpaMuat(m.id);", js)
        self.assertNotIn("b.onclick = () => pilihModel(m.id);", js)
        self.assertIn("$('btnMulai').onclick", js)

    def test_logika_pilihan_dengan_dom_tiruan(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        skrip = Path(__file__).resolve().parent / "index_smoke.js"
        r = subprocess.run([node, str(skrip)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "OK")

    def test_sintaks_index_js(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, "--check", str(WEB / "index.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class TestDasbor(unittest.TestCase):
    """Halaman awal: dua tombol besar (Sesi Agent, Sesi AI Asisten) dan navigasi kembali dari tiap sesi."""

    def test_dasbor_punya_dua_tombol_sesi(self):
        html = (WEB / "dasbor.html").read_text(encoding="utf-8")
        self.assertIn("Sesi Agent", html)
        self.assertIn("Sesi AI Asisten", html)
        self.assertRegex(html, r'id="kartuAgent"[^>]*href="agent\.html"')
        self.assertRegex(html, r'id="kartuChat"[^>]*href="chat"')

    def test_id_di_js_ada_di_html(self):
        js = (WEB / "dasbor.js").read_text(encoding="utf-8")
        html = (WEB / "dasbor.html").read_text(encoding="utf-8")
        dipakai = set(re.findall(r"\$\('([A-Za-z0-9_]+)'\)", js))
        ada = set(re.findall(r'id="([^"]+)"', html))
        self.assertGreater(len(dipakai), 10)
        self.assertEqual(sorted(dipakai - ada), [])

    def test_berkas_yang_dirujuk_ada(self):
        html = (WEB / "dasbor.html").read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="([^"]+)"', html):
            if ref in ("chat", "agent.html"):
                continue
            self.assertTrue((WEB / ref).is_file(), ref)

    def test_rute_server(self):
        from server import server_http
        S = server_http.STATIS
        self.assertEqual(S["/"][0], "dasbor.html")          # halaman pertama = dasbor
        self.assertEqual(S["/chat"][0], "index.html")
        self.assertEqual(S["/index.html"][0], "index.html")
        self.assertEqual(S["/agent"][0], "agent.html")
        for p in ("/dasbor", "/dasbor.html", "/dasbor.css", "/dasbor.js"):
            self.assertTrue((WEB / S[p][0]).is_file(), p)

    def test_chat_dan_agent_punya_tombol_kembali_ke_dasbor(self):
        chat = (WEB / "index.html").read_text(encoding="utf-8")
        agent = (WEB / "agent.html").read_text(encoding="utf-8")
        self.assertRegex(chat, r'id="btnDasbor"[^>]*href="/"')
        self.assertRegex(agent, r'id="btnChat"[^>]*href="/"')

    def test_agent_punya_tombol_selesai(self):
        html = (WEB / "agent.html").read_text(encoding="utf-8")
        js = (WEB / "agent.js").read_text(encoding="utf-8")
        self.assertIn('id="btnSelesai"', html)
        self.assertIn("$('btnSelesai').onclick", js)
        self.assertIn("$('btnSelesai').hidden = (nama !== 'kerja')", js)
        self.assertIn("/api/stop", js)

    def test_kelas_body_chat_tidak_bentrok_dengan_item_riwayat(self):
        # `.chat` sudah dipakai item daftar riwayat (display:flex + padding); body tidak boleh memakainya
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(html, r'<body[^>]*class="[^"]*(?<![\w-])chat(?![\w-])')

    def test_sintaks_js(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        for nama in ("dasbor.js", "agent.js", "index.js"):
            r = subprocess.run([node, "--check", str(WEB / nama)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, nama + ": " + r.stderr)


if __name__ == "__main__":
    unittest.main()
