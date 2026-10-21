"""Pengujian susunan paket agen/: semua nama lama masih ada, perubahan lewat paket diteruskan
ke modul pemilik, tidak ada nama ganda, dan lokasi aksi.log tetap di folder proyek."""
import ast
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agen  # noqa: E402
from agen import agen_config, agen_giliran, agen_kritik, agen_llama, agen_memori, agen_prompt  # noqa: E402

# Semua nama tingkat-atas agen.py sebelum dipecah (kontrak untuk asisten.py, tim/, dan pengujian).
NAMA_LAMA = """
CATATAN_TERPOTONG CTX_MAKS GERBANG KATA_TOOL KATA_WEB KRITIK_MIN LLAMA_URL LOG_AKSI MAX_OUTPUT MAX_STEPS
MAX_TOKENS PESAN_TOOL_TERPOTONG PROMPT_KRITIK PROMPT_KRITIS PROMPT_RINGKAS PROMPT_WEB RINGKAS_AMBANG
RINGKAS_MAKS_KARAKTER RINGKAS_SISA_GILIRAN SYSTEM_CHAT SYSTEM_PROMPT _baca_stream _bersih_final _env_int
_event_info _gabung_tool_call _jalankan_tool_calls _kritik _luar _riwayat_tercemar _transkrip
_urut_tool_calls buat_ringkasan buat_system catat eksekusi giliran llama max_history mode_dari perlu_tool
potong ringkas ringkas_bila_perlu siapkan stream_chat tools_untuk ukuran tolls aksilog urllib
""".split()


class TestSusunanPaket(unittest.TestCase):
    def test_semua_nama_lama_masih_ada(self):
        hilang = [n for n in NAMA_LAMA if not hasattr(agen, n)]
        self.assertEqual(hilang, [])

    def test_paket_bukan_berkas_tunggal(self):
        self.assertTrue(agen.__file__.endswith("__init__.py"))
        self.assertFalse((ROOT / "agen.py").exists(), "agen.py lama harus dihapus")

    def test_tiap_nama_dimiliki_satu_modul(self):
        semua = [n for m in (agen_config, agen_prompt, agen_llama, agen_memori, agen_kritik, agen_giliran)
                 for n in m.__all__]
        self.assertEqual(len(semua), len(set(semua)))
        for n in semua:       # nama di paket = objek yang sama dengan di modul pemilik
            self.assertIs(getattr(agen, n), getattr(agen._PEMILIK[n], n), n)

    def test_aksi_log_tetap_di_folder_proyek(self):
        self.assertEqual(agen_config.LOG_AKSI, ROOT / "aksi.log")

    def test_impor_bersih_di_proses_baru(self):
        r = subprocess.run([sys.executable, "-c", "import agen; print(agen.giliran.__module__)"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "agen.agen_giliran")

    def test_tidak_ada_impor_melingkar_antar_modul(self):
        """Urutan ketergantungan: config <- prompt <- llama <- memori <- kritik <- giliran."""
        urutan = ["agen_config", "agen_prompt", "agen_llama", "agen_memori", "agen_kritik", "agen_giliran"]
        for i, nama in enumerate(urutan):
            tree = ast.parse((ROOT / "agen" / (nama + ".py")).read_text(encoding="utf-8"))
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom) and n.level == 1:
                    for a in n.names:
                        self.assertIn(a.name, urutan[:i], "%s mengimpor %s" % (nama, a.name))


class TestPerubahanLewatPaket(unittest.TestCase):
    def test_penetapan_diteruskan_ke_modul_pemilik(self):
        with mock.patch.object(agen, "GERBANG", False):
            self.assertIs(agen_config.GERBANG, False)
            self.assertTrue(agen.perlu_tool("halo", [], ("dasar",)))      # gerbang mati: selalu pakai tool
        self.assertIs(agen_config.GERBANG, agen.GERBANG)
        with mock.patch.object(agen, "CTX_MAKS", 4096), mock.patch.object(agen, "MAX_TOKENS", 300):
            kecil = agen.max_history([])
        self.assertLess(kecil, agen.max_history([]))                      # konteks kecil: jatah riwayat kecil

    def test_stream_chat_palsu_dipakai_semua_pemanggil(self):
        """_baca_stream (agen_llama) dan _kritik (agen_kritik) sama-sama memanggil agen_llama.stream_chat."""
        dipanggil = []

        def palsu(model, pesan, batal, tools=None):
            dipanggil.append(model)
            return iter([])
        with mock.patch.object(agen, "stream_chat", palsu):
            self.assertIs(agen_llama.stream_chat, palsu)
            list(agen._baca_stream("m1", [], mock.Mock(batal=mock.Mock()), None, False))
            ctx = mock.Mock()
            ctx.batal.is_set.return_value = False
            list(agen._kritik("m2", [], 9000, [], ("kritis",), "", "d" * 200, ctx))
        self.assertEqual(dipanggil, ["m1", "m2"])

    def test_log_aksi_diteruskan(self):
        with mock.patch.object(agen, "LOG_AKSI", Path("/tmp/aksi-uji.log")):
            self.assertEqual(agen_config.LOG_AKSI, Path("/tmp/aksi-uji.log"))
        self.assertEqual(agen_config.LOG_AKSI, agen.LOG_AKSI)


if __name__ == "__main__":
    unittest.main()
