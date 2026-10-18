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


if __name__ == "__main__":
    unittest.main()
