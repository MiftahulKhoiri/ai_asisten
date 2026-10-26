"""Pengujian pilihan prompt untuk skill Tanpa: penyimpanan (tambah/hapus/rakit), pemakaian di agen
(prompt sistem kustom, tanpa prompt = murni), rute /api/prompt, dan alurnya dari pilih sesi sampai kirim."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402
import asisten  # noqa: E402
from server import server_prompt as prm  # noqa: E402
from test_batas_dan_taint import Ctx, Palsu, chunk, jalan  # noqa: E402
from test_unggah import DasarServer  # noqa: E402
from test_unggah import setUpModule as _unggah_setUp, tearDownModule as _unggah_tear  # noqa: E402


def setUpModule():
    _unggah_setUp()


def tearDownModule():
    _unggah_tear()


class DasarPrompt(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.berkas = Path(self._tmp.name) / "prompt.json"
        p = mock.patch.object(asisten, "PROMPT_FILE", self.berkas)
        p.start()
        self.addCleanup(p.stop)


class TestPenyimpanan(DasarPrompt):
    def test_awal_hanya_bawaan(self):
        d = prm.daftar_prompt()
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["id"], d[0]["bawaan"]), ("bawaan", True))
        self.assertEqual(d[0]["isi"], agen.SYSTEM_CHAT)
        self.assertFalse(self.berkas.exists())

    def test_tambah_tersimpan_dan_urutan_dibuat(self):
        a = prm.tambah_prompt("  Penerjemah  ", "Terjemahkan ke Inggris.")
        b = prm.tambah_prompt("Singkat", "Jawab satu kalimat.")
        self.assertRegex(a["id"], r"^p[0-9a-f]{8}$")
        self.assertEqual([p["nama"] for p in prm.daftar_prompt()], ["Bawaan (asisten ramah)", "Penerjemah", "Singkat"])
        d = json.loads(self.berkas.read_text(encoding="utf-8"))
        self.assertEqual([p["nama"] for p in d["prompt"]], ["Penerjemah", "Singkat"])
        self.assertFalse(Path(str(self.berkas) + ".tmp").exists())               # penulisan atomik
        self.assertNotEqual(a["id"], b["id"])

    def test_validasi(self):
        kasus = [("", "isi", "Nama prompt wajib diisi"), ("   ", "isi", "Nama prompt wajib diisi"),
                 ("nama", "  ", "Isi prompt wajib diisi"), ("x" * (asisten.MAKS_NAMA_PROMPT + 1), "isi", "maksimal"),
                 ("nama", "x" * (asisten.MAKS_ISI_PROMPT + 1), "maksimal")]
        for nama, isi, pesan in kasus:
            with self.assertRaises(ValueError) as c:
                prm.tambah_prompt(nama, isi)
            self.assertIn(pesan, str(c.exception))
        prm.tambah_prompt("Satu", "a")
        for kembar in ("satu", "SATU", " Satu ", "bawaan (asisten ramah)"):
            with self.assertRaises(ValueError) as c:
                prm.tambah_prompt(kembar, "b")
            self.assertIn("Sudah ada", str(c.exception))
        self.assertEqual(len(prm.daftar_prompt()), 2)

    def test_batas_jumlah(self):
        with mock.patch.object(asisten, "MAKS_PROMPT", 2):
            prm.tambah_prompt("a", "1")
            prm.tambah_prompt("b", "2")
            with self.assertRaises(ValueError) as c:
                prm.tambah_prompt("c", "3")
            self.assertIn("penuh", str(c.exception))

    def test_berkas_rusak_dianggap_kosong(self):
        for isi in ("{rusak", "[]", json.dumps({"prompt": [{"id": "../x", "nama": "a", "isi": "b"}, {"nama": 1}, "x"]})):
            self.berkas.write_text(isi, encoding="utf-8")
            self.assertEqual(len(prm.daftar_prompt()), 1, isi)                    # hanya bawaan; tidak melempar galat
        self.berkas.write_text("{rusak", encoding="utf-8")
        prm.tambah_prompt("Baru", "isi")                                          # menulis ulang berkas yang rusak
        self.assertEqual(len(prm.daftar_prompt()), 2)

    def test_hapus(self):
        a = prm.tambah_prompt("Satu", "a")
        with self.assertRaises(ValueError):
            prm.hapus_prompt("bawaan")
        self.assertFalse(prm.hapus_prompt("p00000000"))
        self.assertFalse(prm.hapus_prompt("../x"))
        self.assertTrue(prm.hapus_prompt(a["id"]))
        self.assertEqual([p["id"] for p in prm.daftar_prompt()], ["bawaan"])

    def test_berlaku_hanya_untuk_skill_tanpa_tanpa_akses_sistem(self):
        self.assertTrue(prm.berlaku(("tanpa",)))
        self.assertTrue(prm.berlaku(("tanpa", "web", "kritis")))
        for skill in (("tanpa", "dasar"), ("tanpa", "kompleks"), ("web",), ("kritis",), ("kompleks",), (), None):
            self.assertFalse(prm.berlaku(skill), skill)


class TestRakit(DasarPrompt):
    def setUp(self):
        super().setUp()
        self.a = prm.tambah_prompt("Penerjemah", "Terjemahkan ke Inggris.")["id"]
        self.b = prm.tambah_prompt("Singkat", "Jawab satu kalimat.")["id"]

    def test_tidak_ada_pilihan_berarti_bawaan(self):
        self.assertEqual(prm.rakit(None), (None, ["Bawaan (asisten ramah)"]))

    def test_hanya_bawaan_memakai_jalur_lama(self):
        self.assertEqual(prm.rakit(["bawaan"]), (None, ["Bawaan (asisten ramah)"]))

    def test_tanpa_pilihan_adalah_murni(self):
        self.assertEqual(prm.rakit([]), ("", []))

    def test_satu_dan_beberapa_prompt_digabung_menurut_urutan_daftar(self):
        self.assertEqual(prm.rakit([self.a]), ("Terjemahkan ke Inggris.", ["Penerjemah"]))
        self.assertEqual(prm.rakit([self.b, self.a]), ("Terjemahkan ke Inggris.\n\nJawab satu kalimat.", ["Penerjemah", "Singkat"]))
        teks, nama = prm.rakit(["bawaan", self.b])
        self.assertEqual(teks, agen.SYSTEM_CHAT + "\n\nJawab satu kalimat.")
        self.assertEqual(nama, ["Bawaan (asisten ramah)", "Singkat"])

    def test_id_yang_sudah_dihapus_dilewati_dan_tidak_diam_diam_menjadi_murni(self):
        prm.hapus_prompt(self.a)
        self.assertEqual(prm.rakit([self.a, self.b]), ("Jawab satu kalimat.", ["Singkat"]))
        self.assertEqual(prm.rakit([self.a]), (None, ["Bawaan (asisten ramah)"]))   # semuanya hilang -> bawaan
        self.assertEqual(prm.rakit(["p00000000"]), (None, ["Bawaan (asisten ramah)"]))

    def test_rapikan_pilihan(self):
        self.assertIsNone(prm.rapikan_pilihan(None))
        self.assertEqual(prm.rapikan_pilihan([self.b, "bawaan", "p00000000", self.a]), ["bawaan", self.a, self.b])
        self.assertEqual(prm.rapikan_pilihan([]), [])
        for salah in ("bawaan", [1], {"a": 1}, [None]):
            with self.assertRaises(ValueError):
                prm.rapikan_pilihan(salah)


class TestPromptSistem(unittest.TestCase):
    def test_buat_system_bawaan_tidak_berubah(self):
        a = agen.buat_system("", ("tanpa",))
        self.assertEqual(a, agen.buat_system("", ("tanpa",), None))
        self.assertIn("Indonesia", a)
        self.assertRegex(a, r"\d{4}")                                             # tanggal terisi

    def test_prompt_kustom_dengan_waktu(self):
        teks = agen.buat_system("", ("tanpa",), "Kamu penerjemah. Sekarang {waktu}. Contoh {abc} tetap.")
        self.assertTrue(teks.startswith("Kamu penerjemah. Sekarang "))
        self.assertNotIn("{waktu}", teks)
        self.assertIn("{abc}", teks)                                              # kurung lain tidak disentuh
        self.assertNotIn(agen.SYSTEM_CHAT[:60], teks)

    def test_murni_tidak_punya_prompt_dasar_tetapi_skill_web_tetap_ikut(self):
        self.assertEqual(agen.buat_system("", ("tanpa",), "").strip(), "")
        web = agen.buat_system("", ("tanpa", "web"), "")
        self.assertIn(agen.PROMPT_WEB.strip()[:40], web)
        self.assertNotIn(agen.SYSTEM_CHAT[:60], web)

    def test_prompt_dasar_diabaikan_untuk_skill_dengan_akses_sistem(self):
        for skill in (("dasar",), ("kompleks",), ("tanpa", "kompleks")):
            self.assertEqual(agen.buat_system("", skill, "ABAIKAN INI"), agen.buat_system("", skill))
            self.assertNotIn("ABAIKAN INI", agen.buat_system("", skill, "ABAIKAN INI"))

    def test_dasar_dari_hanya_menerima_teks(self):
        self.assertIsNone(agen.dasar_dari(object()))
        self.assertEqual(agen.dasar_dari(mock.Mock(prompt_dasar="x")), "x")
        self.assertEqual(agen.dasar_dari(mock.Mock(prompt_dasar="")), "")
        self.assertIsNone(agen.dasar_dari(mock.Mock()))                           # atribut tiruan bukan teks
        self.assertIsNone(agen.dasar_dari(mock.Mock(prompt_dasar=5)))


class TestGiliranDenganPrompt(unittest.TestCase):
    def kirim(self, dasar):
        ctx = Ctx(("tanpa",))
        if dasar is not False:
            ctx.prompt_dasar = dasar
        palsu = Palsu([chunk("halo")])
        jalan(("tanpa",), [{"role": "user", "content": "hai"}], palsu, ctx)
        return palsu.panggilan[0]["pesan"]

    def test_bawaan(self):
        pesan = self.kirim(False)
        self.assertEqual(pesan[0]["role"], "system")
        self.assertIn("Indonesia", pesan[0]["content"])
        self.assertEqual(pesan[-1], {"role": "user", "content": "hai"})

    def test_prompt_pilihan(self):
        pesan = self.kirim("Kamu penerjemah.")
        self.assertEqual(pesan[0], {"role": "system", "content": "Kamu penerjemah."})
        self.assertEqual(len(pesan), 2)

    def test_murni_tanpa_pesan_system_sama_sekali(self):
        pesan = self.kirim("")
        self.assertEqual(pesan, [{"role": "user", "content": "hai"}])
        self.assertTrue(all(m["role"] != "system" for m in pesan))

    def test_murni_tidak_menyisipkan_ringkasan_riwayat(self):
        ctx = Ctx(("tanpa",))
        ctx.prompt_dasar = ""
        palsu = Palsu([chunk("halo")])
        asli_s, asli_g = agen.stream_chat, agen.GERBANG
        agen.stream_chat, agen.GERBANG = palsu, False
        try:
            list(agen.giliran([{"role": "user", "content": "hai"}], "m", ctx, None))     # server memberi memori=None
        finally:
            agen.stream_chat, agen.GERBANG = asli_s, asli_g
        self.assertTrue(all(m["role"] != "system" for m in palsu.panggilan[0]["pesan"]))


# ------------------------------------------------------------------ rute HTTP dan sesi
class DasarServerPrompt(DasarServer):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(asisten, "PROMPT_FILE", Path(self._tmp.name) / "prompt.json")
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(asisten, "muat_model", lambda nama: None)
        q.start()
        self.addCleanup(q.stop)

    def daftar(self):
        return json.loads(self.req("GET", "/api/prompt")[1])["prompt"]

    def pilih(self, **tambahan):
        return self.req("POST", "/api/model/pilih", dict({"model": "A", "skill": ["tanpa"]}, **tambahan))

    def sesi_siap(self):
        with asisten.S_LOCK:
            asisten.S["status"] = "siap"


class TestRutePrompt(DasarServerPrompt):
    def test_wajib_token(self):
        self.assertEqual(self.req("GET", "/api/prompt", token=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "a", "isi": "b"}, token=False)[0], 401)
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {"id": "p00000000"}, token=False)[0], 401)

    def test_daftar_tambah_hapus(self):
        d = json.loads(self.req("GET", "/api/prompt")[1])
        self.assertEqual(d["bawaan"], "bawaan")
        self.assertEqual([p["id"] for p in d["prompt"]], ["bawaan"])
        kode, isi = self.req("POST", "/api/prompt", {"nama": "Penerjemah", "isi": "Terjemahkan ke Inggris."})
        j = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual([p["nama"] for p in j["prompt"]], ["Bawaan (asisten ramah)", "Penerjemah"])
        self.assertEqual(j["baru"]["nama"], "Penerjemah")
        self.assertEqual([p["nama"] for p in self.daftar()], ["Bawaan (asisten ramah)", "Penerjemah"])   # tersimpan
        kode, isi = self.req("POST", "/api/prompt/hapus", {"id": j["baru"]["id"]})
        self.assertEqual((kode, json.loads(isi)["ok"]), (200, True))
        self.assertEqual(len(self.daftar()), 1)

    def test_penolakan(self):
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "", "isi": "b"})[0], 400)
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "a", "isi": ""})[0], 400)
        self.assertEqual(self.req("POST", "/api/prompt", {"nama": "a" * 41, "isi": "b"})[0], 400)
        self.req("POST", "/api/prompt", {"nama": "a", "isi": "b"})
        kode, isi = self.req("POST", "/api/prompt", {"nama": "A", "isi": "c"})
        self.assertEqual(kode, 400)
        self.assertIn("Sudah ada", json.loads(isi)["error"])
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {"id": "bawaan"})[0], 400)
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {"id": "p00000000"})[0], 404)
        self.assertEqual(self.req("POST", "/api/prompt/hapus", {})[0], 404)

    def test_berkas_statis(self):
        for p, ket in (("/prompt.js", b"PromptPilih"),):
            kode, isi = self.req("GET", p, token=False)
            self.assertEqual(kode, 200)
            self.assertIn(ket, isi)


class TestSesiDenganPrompt(DasarServerPrompt):
    def buat(self, nama, isi):
        return json.loads(self.req("POST", "/api/prompt", {"nama": nama, "isi": isi})[1])["baru"]["id"]

    def test_pilihan_disimpan_di_sesi_dan_tampil_di_status(self):
        a = self.buat("Penerjemah", "Terjemahkan.")
        self.assertEqual(self.pilih(prompt=[a, "bawaan", "p00000000"])[0], 200)
        self.assertEqual(asisten.S["prompt"], ["bawaan", a])                         # id tak dikenal dibuang, urut daftar
        self.sesi_siap()
        st = json.loads(self.req("GET", "/api/status")[1])
        self.assertEqual(st["prompt"], ["Bawaan (asisten ramah)", "Penerjemah"])
        self.assertEqual(st["prompt_id"], ["bawaan", a])

    def test_tanpa_prompt_di_status_menjadi_daftar_kosong_murni(self):
        self.assertEqual(self.pilih(prompt=[])[0], 200)
        self.sesi_siap()
        self.assertEqual(json.loads(self.req("GET", "/api/status")[1])["prompt"], [])

    def test_tidak_menyebut_prompt_berarti_bawaan(self):
        self.pilih()
        self.sesi_siap()
        self.assertIsNone(asisten.S["prompt"])
        self.assertEqual(json.loads(self.req("GET", "/api/status")[1])["prompt"], ["Bawaan (asisten ramah)"])

    def test_status_tidak_memuat_prompt_untuk_skill_dengan_akses_sistem(self):
        self.pilih(skill=["kompleks"], prompt=["bawaan"])
        self.sesi_siap()
        self.assertIsNone(json.loads(self.req("GET", "/api/status")[1])["prompt"])

    def test_pilihan_tidak_valid_ditolak(self):
        for salah in ("bawaan", [1], {"a": 1}):
            self.assertEqual(self.pilih(prompt=salah)[0], 400, salah)


class TestKirimDenganPrompt(DasarServerPrompt):
    def kirim_dan_tangkap(self, skill, prompt, teks="halo"):
        self.assertEqual(self.pilih(skill=skill, **({"prompt": prompt} if prompt is not None else {}))[0], 200)
        self.sesi_siap()
        cid = json.loads(self.req("POST", "/api/chat/baru", {})[1])["id"]
        tangkap = {}

        def palsu(riwayat, model, ctx, memori=None):
            tangkap.update(dasar=agen.dasar_dari(ctx), memori=memori)
            yield {"t": "token", "d": "ok"}
        with mock.patch.object(agen, "giliran", palsu):
            kode, isi = self.req("POST", "/api/kirim", {"id": cid, "teks": teks})
        self.assertEqual(kode, 200, isi)
        return tangkap

    def test_bawaan_memakai_jalur_lama(self):
        t = self.kirim_dan_tangkap(["tanpa"], None)
        self.assertIsNone(t["dasar"])
        self.assertIsNotNone(t["memori"])                                           # ringkasan otomatis tetap ada

    def test_prompt_pilihan_menjadi_prompt_dasar(self):
        a = json.loads(self.req("POST", "/api/prompt", {"nama": "Penerjemah", "isi": "Terjemahkan {waktu}."})[1])["baru"]["id"]
        t = self.kirim_dan_tangkap(["tanpa"], [a])
        self.assertEqual(t["dasar"], "Terjemahkan {waktu}.")                         # {waktu} diganti saat prompt dibentuk
        self.assertIsNotNone(t["memori"])

    def test_murni_tanpa_prompt_dan_tanpa_memori(self):
        t = self.kirim_dan_tangkap(["tanpa"], [])
        self.assertEqual(t["dasar"], "")
        self.assertIsNone(t["memori"])                                              # tidak ada ringkasan yang disisipkan

    def test_skill_dengan_akses_sistem_tidak_memakai_prompt_pilihan(self):
        t = self.kirim_dan_tangkap(["tanpa", "kompleks"], [])
        self.assertIsNone(t["dasar"])
        self.assertIsNotNone(t["memori"])

    def test_prompt_yang_dihapus_saat_sesi_berjalan_kembali_ke_bawaan(self):
        a = json.loads(self.req("POST", "/api/prompt", {"nama": "Sementara", "isi": "x"})[1])["baru"]["id"]
        self.assertEqual(self.pilih(prompt=[a])[0], 200)
        self.sesi_siap()
        self.req("POST", "/api/prompt/hapus", {"id": a})
        cid = json.loads(self.req("POST", "/api/chat/baru", {})[1])["id"]
        tangkap = {}

        def palsu(riwayat, model, ctx, memori=None):
            tangkap["dasar"] = agen.dasar_dari(ctx)
            yield {"t": "token", "d": "ok"}
        with mock.patch.object(agen, "giliran", palsu):
            self.req("POST", "/api/kirim", {"id": cid, "teks": "halo"})
        self.assertIsNone(tangkap["dasar"])


class TestHalamanPrompt(unittest.TestCase):
    WEB = Path(__file__).resolve().parent.parent / "web"

    def test_html_punya_panel_dan_modul_dimuat_sebelum_index(self):
        html = (self.WEB / "index.html").read_text(encoding="utf-8")
        for pasti in ('id="promptBox"', 'id="btnPromptBaru"', 'id="promptForm"', 'id="promptNama"', 'id="promptIsi"',
                      'id="btnPromptSimpan"', 'id="promptList"', 'id="promptKet"', 'id="btnPromptSelesai"',
                      'id="promptRingkas"', 'id="btnPromptUbah"', 'id="langkahModel"', "List prompt", "+ prompt"):
            self.assertIn(pasti, html)
        self.assertLess(html.index('src="prompt.js"'), html.index('src="index.js"'))
        self.assertLess(html.index('id="skillBox"'), html.index('id="promptBox"'))      # skill dulu, lalu prompt
        self.assertLess(html.index('id="promptBox"'), html.index('id="langkahModel"'))  # lalu model dan Mulai
        self.assertLess(html.index('id="btnPromptSimpan"'), html.index('id="promptList"'))
        self.assertLess(html.index('id="promptList"'), html.index('id="btnPromptSelesai"'))   # Selesai paling bawah

    def test_index_js_memakai_modul_dan_mengirim_prompt(self):
        js = (self.WEB / "index.js").read_text(encoding="utf-8")
        for pasti in ("PromptPilih.pasang", "prm.atur(promptAktif())", "prompt: (prm && promptAktif()) ? prm.ids() : undefined"):
            self.assertIn(pasti, js)

    def test_logika_panel_dengan_dom_tiruan(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, str(Path(__file__).resolve().parent / "prompt_smoke.js")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "OK")


if __name__ == "__main__":
    unittest.main()
