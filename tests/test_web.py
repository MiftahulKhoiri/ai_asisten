"""Pemeriksaan statis tampilan web (tanpa browser)."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
