"""Pengujian susunan paket server/: asisten.py tinggal pintu masuk, semua nama lama masih ada,
penetapan nilai lewat asisten diteruskan ke modul pemilik, dan urutan impor tidak melingkar."""
import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import asisten  # noqa: E402
import server  # noqa: E402
from server import (server_agent, server_chat, server_config, server_http, server_model,  # noqa: E402
                    server_state)

# Semua nama tingkat-atas asisten.py sebelum dipecah (kontrak untuk pengujian dan pemakai lain).
NAMA_LAMA = """
BASE WEB RIWAYAT TOKEN_FILE MODELS_DIR ID_RE TOKEN IDLE_MENIT WARNA S S_LOCK GEN_LOCK AKTIF KONF AGENT
AGENT_COND AGENT_MAKS_EVENT AGENT_BATCH AGENT_TUNGGU_MAKS LEVEL_WARNA w log muat_token ip_lan daftar_model
berkas_belum_dikenal status_llama _unload muat_model bongkar_model selesai_sesi jaga_idle sentuh path_chat
simpan_chat baca_chat baru_chat cuplikan_chat hapus_semua_chat daftar_chat Ctx status_json agent_status
agent_proses agent_tambah _gabung_potongan agent_baca STATIS H catat_event keluar main agen tim
""".split()

URUTAN = ["server_config", "server_state", "server_log", "server_akses", "server_model", "server_chat",
          "server_ctx", "server_agent", "server_status", "server_http", "server_main"]


class TestSusunanPaket(unittest.TestCase):
    def test_semua_nama_lama_masih_ada(self):
        self.assertEqual([n for n in NAMA_LAMA if not hasattr(asisten, n)], [])

    def test_asisten_py_hanya_pintu_masuk(self):
        pohon = ast.parse((ROOT / "asisten.py").read_text(encoding="utf-8"))
        self.assertEqual([n.name for n in pohon.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))], [])
        self.assertLess(len((ROOT / "asisten.py").read_text().splitlines()), 40)

    def test_nama_di_fasad_sama_dengan_modul_pemilik(self):
        for nama, modul in server._PEMILIK.items():
            self.assertIs(getattr(asisten, nama), getattr(modul, nama), nama)

    def test_folder_proyek_dan_web_tetap_benar(self):
        self.assertEqual(server_config.BASE, ROOT)
        self.assertTrue((server_config.WEB / "index.html").is_file())
        self.assertEqual(server_config.RIWAYAT, ROOT / "riwayat")
        self.assertEqual(server_config.TOKEN_FILE, ROOT / ".token")

    def test_urutan_impor_tidak_melingkar(self):
        for i, nama in enumerate(URUTAN):
            pohon = ast.parse((ROOT / "server" / (nama + ".py")).read_text(encoding="utf-8"))
            for n in ast.walk(pohon):
                if isinstance(n, ast.ImportFrom) and n.level == 1:
                    for a in n.names:
                        self.assertIn(a.name, URUTAN[:i], "%s mengimpor %s" % (nama, a.name))

    def test_dijalankan_sebagai_skrip(self):
        r = subprocess.run([sys.executable, str(ROOT / "asisten.py"), "--help"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--port", r.stdout)


class TestPenetapanLewatFasad(unittest.TestCase):
    def test_token_dan_riwayat_diteruskan(self):
        asli_t, asli_r = server_config.TOKEN, server_config.RIWAYAT
        try:
            asisten.TOKEN, asisten.RIWAYAT = "tokenuji-1234567890", Path("/tmp/riwayat-uji")
            self.assertEqual(server_config.TOKEN, "tokenuji-1234567890")
            self.assertEqual(server_chat.path_chat("abcdef12"), Path("/tmp/riwayat-uji/abcdef12.json"))
        finally:
            asisten.TOKEN, asisten.RIWAYAT = asli_t, asli_r
        self.assertEqual(server_config.TOKEN, asli_t)

    def test_patch_fungsi_dipakai_modul_lain(self):
        """H memanggil daftar_model lewat modul pemilik, jadi patch lewat asisten berlaku di sana."""
        palsu = lambda: [{"id": "m1", "mb": 1, "llama": None}]    # noqa: E731
        with mock.patch.object(asisten, "daftar_model", palsu):
            self.assertIs(server_model.daftar_model, palsu)
            self.assertEqual(server_http.mdl.daftar_model(), palsu())
        self.assertIsNot(server_model.daftar_model, palsu)

    def test_kunci_dan_buffer_adalah_objek_yang_sama(self):
        self.assertIs(asisten.GEN_LOCK, server_state.GEN_LOCK)
        self.assertIs(asisten.AGENT, server_state.AGENT)
        self.assertIs(server_agent.state.AGENT_COND, asisten.AGENT_COND)

    def test_ctx_palsu_dipakai_handler(self):
        with mock.patch.object(asisten, "Ctx", side_effect=RuntimeError("x")):
            with self.assertRaises(RuntimeError):
                server_http.kts.Ctx(None, None)


if __name__ == "__main__":
    unittest.main()
