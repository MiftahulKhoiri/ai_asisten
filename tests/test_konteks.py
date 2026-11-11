"""Pengujian batas konteks per sesi (tombol "Konteks" di layar Mulai sesi):
isian dari web, batas model dari llama-server, dan nilai per thread di agen."""
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import agen  # noqa: E402
from agen import agen_config as cfg  # noqa: E402
from agen import agen_prompt  # noqa: E402
from server import server_model as mdl  # noqa: E402
from server import server_state as state  # noqa: E402


class TestArgsLlama(unittest.TestCase):
    def test_ctx_size_dari_args_router(self):
        args = ["/bin/llama-server", "--host", "127.0.0.1", "--ctx-size", "8192", "--model", "/m/a.gguf"]
        self.assertEqual(mdl._ctx_dari_args(args), 8192)

    def test_ctx_pendek_dan_kosong(self):
        self.assertEqual(mdl._ctx_dari_args(["x", "-c", "4096"]), 4096)
        self.assertIsNone(mdl._ctx_dari_args(["x", "--model", "a"]))
        self.assertIsNone(mdl._ctx_dari_args(None))
        self.assertIsNone(mdl._ctx_dari_args(["x", "--ctx-size", "abc"]))
        self.assertIsNone(mdl._ctx_dari_args(["x", "--ctx-size"]))   # nilai hilang di ujung

    def test_batas_model(self):
        self.assertEqual(mdl.batas_ctx_model({"ctx": 8192, "ctx_latih": 131072}), 8192)
        self.assertEqual(mdl.batas_ctx_model({"ctx": 0, "ctx_latih": 131072}), 131072)   # 0 = konteks latih
        self.assertIsNone(mdl.batas_ctx_model({"ctx": None, "ctx_latih": None}))
        self.assertIsNone(mdl.batas_ctx_model({}))


class TestIsianWeb(unittest.TestCase):
    def test_kosong_berarti_bawaan(self):
        for v in (None, "", 0, "0"):
            self.assertIsNone(mdl.rapikan_ctx(v))

    def test_angka_valid(self):
        self.assertEqual(mdl.rapikan_ctx(4096), 4096)
        self.assertEqual(mdl.rapikan_ctx(" 16384 "), 16384)

    def test_tidak_valid(self):
        for v in ("abc", 100, 2_000_000, True, [1], "4k"):
            with self.assertRaises(ValueError):
                mdl.rapikan_ctx(v)


class TestEfektif(unittest.TestCase):
    def setUp(self):
        self.lama = dict(state.S)

    def tearDown(self):
        state.S.clear()
        state.S.update(self.lama)

    def atur(self, pilih, server):
        with state.S_LOCK:
            state.S["ctx"], state.S["ctx_server"] = pilih, server

    def test_bawaan_tanpa_batas(self):
        self.atur(None, None)
        self.assertEqual(mdl.ctx_efektif(), agen.CTX_MAKS)

    def test_pilihan_dipakai(self):
        self.atur(4096, 8192)
        self.assertEqual(mdl.ctx_efektif(), 4096)

    def test_dipangkas_ke_batas_model(self):
        self.atur(32768, 8192)
        self.assertEqual(mdl.ctx_efektif(), 8192)

    def test_online_tanpa_info_batas(self):
        self.atur(65536, None)
        self.assertEqual(mdl.ctx_efektif(), 65536)


class TestPerThread(unittest.TestCase):
    def tearDown(self):
        cfg.atur_ctx(None)

    def test_atur_dan_kembali(self):
        self.assertEqual(cfg.ctx_maks(), cfg.CTX_MAKS)
        cfg.atur_ctx(4096)
        self.assertEqual(cfg.ctx_maks(), 4096)
        cfg.atur_ctx(None)
        self.assertEqual(cfg.ctx_maks(), cfg.CTX_MAKS)

    def test_thread_lain_tidak_terpengaruh(self):
        """Proses Agent (thread lain) tetap memakai CTX_MAKS saat sesi chat memakai konteks lain."""
        cfg.atur_ctx(2048)
        hasil = []
        t = threading.Thread(target=lambda: hasil.append(cfg.ctx_maks()))
        t.start()
        t.join()
        self.assertEqual(hasil, [cfg.CTX_MAKS])
        self.assertEqual(cfg.ctx_maks(), 2048)

    def test_patch_ctx_maks_lewat_paket_tetap_berlaku(self):
        with mock.patch.object(agen, "CTX_MAKS", 16384):
            self.assertEqual(cfg.ctx_maks(), 16384)

    def test_jatah_riwayat_mengikuti_konteks(self):
        kecil = agen_prompt.max_history([])
        cfg.atur_ctx(cfg.CTX_MAKS * 4)
        besar = agen_prompt.max_history([])
        self.assertGreater(besar, kecil)


if __name__ == "__main__":
    unittest.main()
