"""Pengujian tim_agen.py (Agent multi-model) dan endpoint /api/agent.

llama-server dan model dipalsukan: yang diuji adalah urutan muat/bongkar model, alur
putaran koreksi, pemeriksaan otomatis, keamanan nama berkas, dan keluaran event.
"""
import json
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402
import asisten  # noqa: E402
import tim_agen as tim  # noqa: E402

RENCANA = json.dumps({
    "judul": "Halo", "ringkasan": "Cetak halo", "bahasa": "python",
    "berkas": [{"nama": "main.py", "fungsi": "mencetak halo"}],
    "langkah": ["tulis kode"], "kriteria": ["mencetak halo"],
    "jalankan": ["python3", "main.py"], "catatan": "", "tanya": ""})
KODE_BAIK = "=== FILE: main.py ===\nprint('halo')\n=== END ===\n"
KODE_RUSAK = "=== FILE: main.py ===\ndef x(:\n    pass\n=== END ===\n"
NILAI_OK = json.dumps({"ok": True, "ringkas": "bagus", "masalah": [], "perbaikan": ""})
NILAI_TOLAK = json.dumps({"ok": False, "ringkas": "kurang", "masalah": ["main.py:1 - salah"],
                          "perbaikan": "perbaiki baris 1"})


class LlamaPalsu:
    """Pengganti agen.llama: mencatat urutan muat/bongkar model."""

    def __init__(self, *nama):
        self.state = {n: "unloaded" for n in nama}
        self.log = []

    def __call__(self, path, data=None, timeout=0):
        if path == "/v1/models":
            return {"data": [{"id": n, "status": {"value": s}} for n, s in self.state.items()]}
        if path == "/models/load":
            self.state[data["model"]] = "loaded"
            self.log.append("muat " + data["model"])
            return {}
        if path == "/models/unload":
            self.state[data["model"]] = "unloaded"
            self.log.append("bongkar " + data["model"])
            return {}
        raise AssertionError(path)


class StreamPalsu:
    """Pengganti tim_agen._stream: jawaban berurutan per peran (dikenali dari system prompt)."""

    def __init__(self, rencana=(), tulis=(), periksa=(), jelaskan=("Selesai dibuat.",)):
        self.antrian = {"PERENCANA": list(rencana), "PELAKSANA": list(tulis),
                        "PEMERIKSA": list(periksa), "PENJELAS": list(jelaskan)}
        self.panggilan = []     # (peran, model)
        self.sebelum = None     # fungsi(peran) dipanggil sebelum menjawab

    def __call__(self, model, pesan, batal, token, suhu=0.2, json_mode=False):
        peran = next(p for p in self.antrian if re.match(r"Kamu %s\b" % p, pesan[0]["content"]))
        self.panggilan.append((peran, model))
        if self.sebelum:
            self.sebelum(peran)
        jawaban = self.antrian[peran].pop(0)
        if isinstance(jawaban, Exception):
            raise jawaban
        tengah = len(jawaban) // 2
        yield {"choices": [{"delta": {"content": jawaban[:tengah]}}]}
        yield {"choices": [{"delta": {"content": jawaban[tengah:]}, "finish_reason": "stop"}],
               "timings": {"predicted_n": 5, "predicted_per_second": 2.0, "prompt_n": 10}}


class CtxPalsu:
    def __init__(self, izin=True):
        self.batal = threading.Event()
        self.izin = izin
        self.ditanya = []

    def konfirmasi(self, jenis, ringkas, detail=""):
        self.ditanya.append(jenis)
        return self.izin


class DasarAgent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        for nama, nilai in (("KERJA", Path(self._tmp.name)), ("_TIDUR", lambda s: None)):
            p = mock.patch.object(tim, nama, nilai)
            p.start()
            self.addCleanup(p.stop)
        tim.DIMUAT.clear()

    def pasang(self, llama, stream):
        for obj, nama, nilai in ((agen, "llama", llama), (tim, "_stream", stream)):
            p = mock.patch.object(obj, nama, nilai)
            p.start()
            self.addCleanup(p.stop)

    def cfg(self, mode=2, maks=3, bongkar=True, uji=True, c="C"):
        return {"mode": mode, "model_p": "A", "model_e": "B",
                "model_c": c if mode == 3 else "A", "maks": maks, "bongkar": bongkar, "uji": uji}

    def jalan(self, cfg, ctx=None, tugas="buat halo", lanjut=None):
        ctx = ctx or CtxPalsu()
        return list(tim.jalankan(tugas, cfg, ctx, lanjut)), ctx


def jenis(ev):
    return [e["t"] for e in ev]


class TestNamaBerkas(unittest.TestCase):
    def test_nama_aman(self):
        for n in ("main.py", "src/app.js", "a/b/c.json", "./x.md"):
            tim.aman_nama(n)

    def test_nama_tidak_aman(self):
        for n in ("../x.py", "/etc/passwd.py", "a/../b.py", ".bashrc.sh", "a b.py", "x.exe",
                  "", None, "a/b/c/d.py", "x" * 90 + ".py", "..\\x.py"):
            with self.assertRaises(ValueError, msg=repr(n)):
                tim.aman_nama(n)

    def test_tulis_tidak_keluar_folder(self):
        with tempfile.TemporaryDirectory() as t:
            hasil = Path(t) / "hasil"
            hasil.mkdir()
            tim.tulis_berkas(hasil, "sub/a.py", "x = 1\n")
            self.assertEqual((hasil / "sub" / "a.py").read_text(), "x = 1\n")
            with self.assertRaises(ValueError):
                tim.tulis_berkas(hasil, "../luar.py", "x")
            (Path(t) / "target").mkdir()
            (hasil / "tautan").symlink_to(Path(t) / "target")
            with self.assertRaises(ValueError):
                tim.tulis_berkas(hasil, "tautan/a.py", "x")
            with self.assertRaises(ValueError):
                tim.tulis_berkas(hasil, "besar.txt", "x" * (tim.MAKS_UKURAN + 1))

    def test_baca_proyek_lewati_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            hasil = Path(t) / "hasil"
            hasil.mkdir()
            (hasil / "a.py").write_text("x\n")
            (Path(t) / "rahasia.txt").write_text("rahasia")
            (hasil / "b.txt").symlink_to(Path(t) / "rahasia.txt")
            self.assertEqual([n for n, _ in tim.baca_proyek(hasil)], ["a.py"])


class TestUrai(unittest.TestCase):
    def test_dua_berkas(self):
        teks = "=== FILE: a.py ===\nx = 1\n=== END ===\n\n=== FILE: b/c.js ===\nlet y;\n=== END ===\n"
        self.assertEqual(tim.urai_berkas(teks), [("a.py", "x = 1\n", True), ("b/c.js", "let y;\n", True)])

    def test_terpotong_tanpa_end(self):
        teks = "=== FILE: a.py ===\nx = 1\n=== END ===\n=== FILE: b.py ===\ndef f():\n    retu"
        hasil = tim.urai_berkas(teks)
        self.assertTrue(hasil[0][2])
        self.assertFalse(hasil[1][2])

    def test_lupa_end_tapi_ada_berkas_berikutnya(self):
        hasil = tim.urai_berkas("=== FILE: a.py ===\nx\n=== FILE: b.py ===\ny\n=== END ===")
        self.assertEqual([h[2] for h in hasil], [True, True])

    def test_pagar_di_dalam_blok_dibuka(self):
        teks = "=== FILE: a.py ===\n```python\nx = 1\n```\n=== END ==="
        self.assertEqual(tim.urai_berkas(teks)[0][1], "x = 1\n")

    def test_cadangan_satu_pagar_satu_berkas(self):
        self.assertEqual(tim.urai_berkas("Ini:\n```python\nprint(1)\n```", ["main.py"]),
                         [("main.py", "print(1)\n", True)])

    def test_cadangan_nama_di_baris_sebelumnya(self):
        teks = "**a.py**\n```python\nx=1\n```\nlalu `b.js`:\n```js\nlet y\n```"
        self.assertEqual([h[0] for h in tim.urai_berkas(teks, ["a.py", "b.js"])], ["a.py", "b.js"])

    def test_tanpa_berkas(self):
        self.assertEqual(tim.urai_berkas("maaf saya tidak bisa"), [])

    def test_ambil_json(self):
        self.assertEqual(tim.ambil_json('{"a": 1}'), {"a": 1})
        self.assertEqual(tim.ambil_json('Ini:\n```json\n{"a": 2}\n```'), {"a": 2})
        self.assertEqual(tim.ambil_json('<think>x</think>teks {"a": 3} akhir'), {"a": 3})
        self.assertIsNone(tim.ambil_json("bukan json"))
        self.assertIsNone(tim.ambil_json("[1, 2]"))


class TestSpec(unittest.TestCase):
    def test_rapikan_nama_dan_batas(self):
        raw = {"berkas": [{"nama": "../x.py"}, {"nama": "ok.py", "fungsi": "f"}, "ok.py", "b.js",
                          "c.js", "d.js", "e.js", "f.js"]}
        spec = tim.rapikan_spec(raw, "tugas")
        self.assertEqual([b["nama"] for b in spec["berkas"]], ["ok.py", "b.js", "c.js", "d.js", "e.js"])

    def test_bawaan_bila_kosong(self):
        spec = tim.rapikan_spec({}, "buat kalkulator")
        self.assertEqual(spec["berkas"][0]["nama"], "main.py")
        self.assertTrue(spec["kriteria"])
        self.assertEqual(spec["jalankan"], [])

    def test_perintah_uji_dibatasi(self):
        b = [{"nama": "main.py"}]
        bagus = tim.rapikan_spec({"berkas": b, "jalankan": ["python", "main.py", "--demo"]}, "t")
        self.assertEqual(bagus["jalankan"], ["python3", "main.py", "--demo"])
        for buruk in (["bash", "main.py"], ["python3", "-c", "import os"], ["python3", "lain.py"],
                      ["python3", "main.py", "; rm -rf ~"], "rm -rf /", ["python3"], 5):
            self.assertEqual(tim.rapikan_spec({"berkas": b, "jalankan": buruk}, "t")["jalankan"], [],
                             msg=repr(buruk))

    def test_nilai_ditolak_tanpa_alasan_diterima(self):
        n = tim.rapikan_nilai({"ok": False, "ringkas": "kurang"})
        self.assertTrue(n["ok"])
        self.assertFalse(tim.rapikan_nilai({"ok": "false", "masalah": ["x"]})["ok"])
        self.assertTrue(tim.rapikan_nilai({"ok": "ya"})["ok"])

    def test_siapkan_cfg(self):
        ada = {"A", "B", "C"}
        cfg, err = tim.siapkan_cfg({"mode": 2, "model_p": "A", "model_e": "B", "maks": 99}, ada)
        self.assertEqual((err, cfg["maks"], cfg["model_c"]), ("", 10, "A"))
        self.assertIn("minimal 2", tim.siapkan_cfg({"mode": 2, "model_p": "A", "model_e": "A"}, ada)[1])
        self.assertIn("tidak dikenal", tim.siapkan_cfg({"model_p": "A", "model_e": "Z"}, ada)[1])
        cfg, err = tim.siapkan_cfg({"mode": 3, "model_p": "A", "model_e": "B", "model_c": "C",
                                    "maks": -5, "bongkar": False}, ada)
        self.assertEqual((err, cfg["maks"], cfg["bongkar"], cfg["model_c"]), ("", 1, False, "C"))


class TestPemeriksaanOtomatis(DasarAgent):
    def spec(self):
        return tim.rapikan_spec({"berkas": [{"nama": "main.py"}], "jalankan": ["python3", "main.py"]}, "t")

    def test_statis(self):
        hasil = Path(self._tmp.name) / "hasil"
        hasil.mkdir()
        ok, baris = tim.cek_statis(hasil, self.spec())
        self.assertFalse(ok)
        self.assertIn("belum dibuat", baris[0])
        (hasil / "main.py").write_text("def x(:\n")
        ok, baris = tim.cek_statis(hasil, self.spec())
        self.assertFalse(ok)
        self.assertIn("baris 1", baris[0])
        (hasil / "main.py").write_text("print(1)\n")
        self.assertTrue(tim.cek_statis(hasil, self.spec())[0])
        (hasil / "x.json").write_text("{rusak")
        self.assertFalse(tim.cek_statis(hasil, self.spec(), ["x.json"])[0])

    def test_jalan_perlu_izin_dan_ditanya_sekali(self):
        hasil = Path(self._tmp.name) / "hasil"
        hasil.mkdir()
        (hasil / "main.py").write_text("print('ok-jalan')\n")
        ctx, izin = CtxPalsu(True), {"nilai": None}
        st, baris = tim.cek_jalan(hasil, self.spec(), ctx, izin, True)
        self.assertEqual(st, "lolos")
        self.assertIn("ok-jalan", "\n".join(baris))
        tim.cek_jalan(hasil, self.spec(), ctx, izin, True)
        self.assertEqual(ctx.ditanya, ["uji"])       # hanya sekali per proses

    def test_jalan_ditolak_atau_dimatikan(self):
        hasil = Path(self._tmp.name) / "hasil"
        hasil.mkdir()
        (hasil / "main.py").write_text("open('dibuat.txt', 'w')\n")
        self.assertEqual(tim.cek_jalan(hasil, self.spec(), CtxPalsu(False), {"nilai": None}, True)[0],
                         "dilewati")
        ctx = CtxPalsu(True)
        self.assertEqual(tim.cek_jalan(hasil, self.spec(), ctx, {"nilai": None}, False)[0], "dilewati")
        self.assertEqual(ctx.ditanya, [])
        self.assertFalse((hasil / "dibuat.txt").exists())   # tidak pernah dijalankan

    def test_jalan_gagal_dan_timeout(self):
        hasil = Path(self._tmp.name) / "hasil"
        hasil.mkdir()
        (hasil / "main.py").write_text("raise SystemExit(3)\n")
        st, baris = tim.cek_jalan(hasil, self.spec(), CtxPalsu(), {"nilai": True}, True)
        self.assertEqual(st, "gagal")
        self.assertIn("exit code 3", baris[0])
        (hasil / "main.py").write_text("import time\ntime.sleep(30)\n")
        with mock.patch.object(tim, "UJI_DETIK", 1):
            st, baris = tim.cek_jalan(hasil, self.spec(), CtxPalsu(), {"nilai": True}, True)
        self.assertEqual(st, "gagal")
        self.assertIn("batas waktu", baris[0])


class TestAlur(DasarAgent):
    def test_dua_model_perbaiki_sendiri_lalu_lolos(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_RUSAK, KODE_BAIK], [NILAI_OK])
        self.pasang(llama, s)
        ev, ctx = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")
        # sintaks rusak -> kembali ke Pelaksana tanpa memuat Pemeriksa
        self.assertEqual([p for p, _ in s.panggilan],
                         ["PERENCANA", "PELAKSANA", "PELAKSANA", "PEMERIKSA", "PENJELAS"])
        # tiap model dibongkar begitu tahapnya selesai
        self.assertEqual(llama.log, ["muat A", "bongkar A", "muat B", "bongkar B",
                                     "muat A", "bongkar A"])
        self.assertEqual(ctx.ditanya, ["uji"])
        self.assertEqual(set(llama.state.values()), {"unloaded"})
        self.assertFalse(tim.DIMUAT)
        run = tim.baca_run(ev[-1]["id"])
        self.assertEqual(run["status"], "lolos")
        self.assertEqual(run["berkas"][0]["isi"], "print('halo')\n")
        self.assertTrue((Path(self._tmp.name) / ev[-1]["id"] / "koreksi_1.md").is_file())
        self.assertTrue((Path(self._tmp.name) / ev[-1]["id"] / "tugas.json").is_file())

    def test_tiga_model_pemeriksa_menolak_lalu_menerima(self):
        llama = LlamaPalsu("A", "B", "C")
        s = StreamPalsu([RENCANA], [KODE_BAIK, KODE_BAIK], [NILAI_TOLAK, NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(mode=3))
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(s.panggilan, [("PERENCANA", "A"), ("PELAKSANA", "B"), ("PEMERIKSA", "C"),
                                       ("PELAKSANA", "B"), ("PEMERIKSA", "C"), ("PENJELAS", "A")])
        self.assertEqual(llama.log, ["muat A", "bongkar A", "muat B", "bongkar B", "muat C",
                                     "bongkar C", "muat B", "bongkar B", "muat C", "bongkar C",
                                     "muat A", "bongkar A"])
        nilai = [e for e in ev if e["t"] == "nilai"]
        self.assertEqual([n["ok"] for n in nilai], [False, True])

    def test_koreksi_masuk_ke_prompt_pelaksana(self):
        llama = LlamaPalsu("A", "B", "C")
        s = StreamPalsu([RENCANA], [KODE_BAIK, KODE_BAIK], [NILAI_TOLAK, NILAI_OK])
        isi = []
        asli = s.__call__

        def rekam(model, pesan, batal, token, suhu=0.2, json_mode=False):
            isi.append(pesan[1]["content"])
            return asli(model, pesan, batal, token, suhu, json_mode)
        self.pasang(llama, rekam)
        self.jalan(self.cfg(mode=3))
        pelaksana = [t for t in isi if "LEMBAR TUGAS" in t and "BERKAS (dengan" not in t]
        self.assertNotIn("KOREKSI", pelaksana[0])
        self.assertIn("perbaiki baris 1", pelaksana[1])
        self.assertIn("print('halo')", pelaksana[1])    # berkas saat ini ikut dikirim

    def test_batas_putaran_tercapai(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_RUSAK, KODE_RUSAK], [])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(maks=2))
        self.assertEqual(ev[-1]["status"], "belum")
        self.assertEqual([p for p, _ in s.panggilan],
                         ["PERENCANA", "PELAKSANA", "PELAKSANA", "PENJELAS"])
        self.assertEqual([e["n"] for e in ev if e["t"] == "putaran"], [1, 2])
        self.assertEqual(set(llama.state.values()), {"unloaded"})

    def test_perencana_butuh_info(self):
        llama = LlamaPalsu("A", "B")
        tanya = json.dumps({"tanya": "Untuk platform apa?", "berkas": []})
        s = StreamPalsu([tanya])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "butuh_info")
        self.assertIn("tanya", jenis(ev))
        self.assertEqual([p for p, _ in s.panggilan], ["PERENCANA"])
        self.assertEqual(set(llama.state.values()), {"unloaded"})

    def test_json_rencana_rusak_dicoba_lagi_lalu_bawaan(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu(["bukan json", "tetap bukan"], [KODE_BAIK], [NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(uji=False))
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual([p for p, _ in s.panggilan][:2], ["PERENCANA", "PERENCANA"])

    def test_pemeriksa_tanpa_json_diterima_bila_otomatis_lolos(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_BAIK], ["ngawur", "ngawur"])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertIn("tidak memberi penilaian", [e for e in ev if e["t"] == "nilai"][0]["ringkas"])

    def test_uji_jalan_gagal_dikembalikan_tanpa_pemeriksa(self):
        llama = LlamaPalsu("A", "B")
        gagal = "=== FILE: main.py ===\nraise SystemExit(2)\n=== END ===\n"
        s = StreamPalsu([RENCANA], [gagal, KODE_BAIK], [NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "lolos")
        cek = [e for e in ev if e["t"] == "cek"]
        self.assertEqual([c["ok"] for c in cek], [False, True])
        self.assertEqual(cek[0]["jalan"], "gagal")

    def test_tanpa_bongkar_tiap_tahap_semua_dibongkar_di_akhir(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_BAIK], [NILAI_OK])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(bongkar=False))
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertEqual(llama.log[:2], ["muat A", "muat B"])
        self.assertEqual(sorted(llama.log[2:]), ["bongkar A", "bongkar B"])

    def test_stop_membongkar_model(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [KODE_BAIK])
        ctx = CtxPalsu()
        s.sebelum = lambda peran: ctx.batal.set() if peran == "PELAKSANA" else None
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg(), ctx)
        self.assertEqual(ev[-1]["status"], "batal")
        self.assertIn("batal", jenis(ev))
        self.assertEqual(set(llama.state.values()), {"unloaded"})
        self.assertFalse(tim.DIMUAT)

    def test_error_model_membongkar_model(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA], [RuntimeError("server mati")])
        self.pasang(llama, s)
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "error")
        self.assertIn("server mati", [e for e in ev if e["t"] == "error"][0]["d"])
        self.assertEqual(set(llama.state.values()), {"unloaded"})

    def test_model_dimuat_pihak_lain_tidak_dibongkar(self):
        llama = LlamaPalsu("A", "B")
        llama.state["A"] = "loaded"
        s = StreamPalsu([RENCANA], [KODE_BAIK], [NILAI_OK])
        self.pasang(llama, s)
        self.jalan(self.cfg())
        self.assertNotIn("bongkar A", llama.log)
        self.assertEqual(llama.state["A"], "loaded")

    def test_gagal_muat(self):
        llama = LlamaPalsu("A", "B")
        asli = llama.__call__

        def gagal(path, data=None, timeout=0):
            if path == "/models/load":
                llama.state[data["model"]] = "failed"
                return {}
            return asli(path, data, timeout)
        self.pasang(gagal, StreamPalsu([RENCANA]))
        ev, _ = self.jalan(self.cfg())
        self.assertEqual(ev[-1]["status"], "error")

    def test_lanjut_menyalin_proyek_lama(self):
        llama = LlamaPalsu("A", "B")
        s = StreamPalsu([RENCANA, RENCANA], [KODE_BAIK, KODE_BAIK], [NILAI_OK, NILAI_OK],
                        ["Satu.", "Dua."])
        self.pasang(llama, s)
        ev1, _ = self.jalan(self.cfg())
        id1 = ev1[-1]["id"]
        ev2, _ = self.jalan(self.cfg(), tugas="tambah fitur", lanjut=id1)
        self.assertEqual(ev2[0]["lanjut"], id1)
        run2 = tim.baca_run(ev2[-1]["id"])
        self.assertEqual(run2["lanjut"], id1)
        self.assertIn("main.py", [b["nama"] for b in run2["berkas"]])
        ids = [r["id"] for r in tim.daftar_run()]
        self.assertEqual(set(ids), {id1, ev2[-1]["id"]})

    def test_baca_run_id_tidak_valid(self):
        for buruk in ("../x", "", None, "20260101-000000-zzzz"):
            with self.assertRaises(FileNotFoundError):
                tim.baca_run(buruk)


class TestEndpoint(DasarAgent):
    TOKEN = "token-uji-agent"

    def setUp(self):
        super().setUp()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), asisten.H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        for obj, nama, nilai in ((asisten, "TOKEN", self.TOKEN),
                                 (asisten, "daftar_model", lambda: [{"id": "A", "mb": 1000, "llama": None},
                                                                    {"id": "B", "mb": 2000, "llama": None}])):
            p = mock.patch.object(obj, nama, nilai)
            p.start()
            self.addCleanup(p.stop)
        with asisten.S_LOCK:
            self._s = dict(asisten.S)
            asisten.S.update(model=None, target=None, status="kosong")
        self.addCleanup(lambda: asisten.S.update(self._s))

    def req(self, metode, path, body=None, token=True):
        r = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), method=metode,
                                   data=json.dumps(body).encode() if body is not None else None)
        if token:
            r.add_header("Authorization", "Bearer " + self.TOKEN)
        r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=20) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_halaman_statis_dan_token(self):
        for p, ket in (("/agent.html", b"AI Agent"), ("/agent.css", b"Agent"), ("/agent.js", b"api/agent")):
            kode, isi = self.req("GET", p, token=False)
            self.assertEqual(kode, 200, p)
            self.assertIn(ket, isi)
        self.assertEqual(self.req("GET", "/api/agent/status", token=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/agent/jalankan", {}, token=False)[0], 401)

    def test_status(self):
        kode, isi = self.req("GET", "/api/agent/status")
        d = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual([m["id"] for m in d["models"]], ["A", "B"])
        self.assertFalse(d["chat_aktif"])
        self.assertEqual(d["langkah"]["bawaan"], 3)

    def test_validasi(self):
        dasar = {"teks": "buat halo", "mode": 2, "model_p": "A", "model_e": "B"}
        self.assertEqual(self.req("POST", "/api/agent/jalankan", dict(dasar, teks=" "))[0], 400)
        self.assertEqual(self.req("POST", "/api/agent/jalankan", dict(dasar, model_e="A"))[0], 400)
        self.assertEqual(self.req("POST", "/api/agent/jalankan", dict(dasar, model_e="Z"))[0], 400)
        self.assertEqual(self.req("POST", "/api/agent/jalankan", dict(dasar, lanjut="../x"))[0], 400)
        self.assertFalse(asisten.GEN_LOCK.locked())

    def test_ditolak_saat_chat_memuat_model(self):
        asisten.S["status"] = "siap"
        kode, isi = self.req("POST", "/api/agent/jalankan", {"teks": "x", "model_p": "A", "model_e": "B"})
        self.assertEqual(kode, 409)
        self.assertIn("Chat", json.loads(isi)["error"])
        self.assertFalse(asisten.GEN_LOCK.locked())

    def test_jalan_penuh_lewat_http(self):
        llama = LlamaPalsu("A", "B")
        self.pasang(llama, StreamPalsu([RENCANA], [KODE_BAIK], [NILAI_OK]))
        ctx_dasar = {"teks": "buat halo", "mode": 2, "model_p": "A", "model_e": "B", "maks": 2,
                     "uji": False}
        kode, isi = self.req("POST", "/api/agent/jalankan", ctx_dasar)
        self.assertEqual(kode, 200)
        ev = [json.loads(b) for b in isi.splitlines() if b.strip()]
        self.assertEqual(ev[0]["t"], "mulai")
        self.assertEqual(ev[-1]["t"], "selesai")
        self.assertEqual(ev[-1]["status"], "lolos")
        self.assertIn("berkas", jenis(ev))
        for _ in range(50):     # kunci dilepas oleh thread kerja sesaat setelah aliran habis
            if not asisten.GEN_LOCK.locked():
                break
            time.sleep(0.05)
        self.assertFalse(asisten.GEN_LOCK.locked())
        kode, isi = self.req("GET", "/api/agent/riwayat")
        self.assertEqual(json.loads(isi)["run"][0]["id"], ev[-1]["id"])
        kode, isi = self.req("GET", "/api/agent/run/" + ev[-1]["id"])
        self.assertEqual(json.loads(isi)["berkas"][0]["nama"], "main.py")
        self.assertEqual(self.req("GET", "/api/agent/run/20260101-000000-abcd")[0], 404)


if __name__ == "__main__":
    unittest.main()
