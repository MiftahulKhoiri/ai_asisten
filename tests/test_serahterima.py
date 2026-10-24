"""Pengujian serah terima chat -> Agent -> chat: brief dari diskusi, penyerahan atas persetujuan,
hasil yang kembali ke obrolan, unduhan hasil, dan lampiran obrolan sebagai bahan kerja."""
import io
import json
import sys
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agen  # noqa: E402
import asisten  # noqa: E402
import tim  # noqa: E402
from server import server_agent, server_chat, server_handoff  # noqa: E402
from test_jalur import DIAG_BUG, MAIN_BUG, StreamCatat  # noqa: E402
from test_tim import KODE_BAIK, LlamaPalsu, NILAI_OK, RENCANA  # noqa: E402
from test_unggah import DasarServer, setUpModule as _unggah_setUp, tearDownModule as _unggah_tear  # noqa: E402


def setUpModule():
    _unggah_setUp()


def tearDownModule():
    _unggah_tear()


BRIEF = ("Tujuan: kalkulator sederhana.\nYang diminta: tambah dan kurang.\nBatasan: Python.\n"
         "Berkas yang ada: tidak disebut.\nKriteria selesai: 2+3 menghasilkan 5.")


def llama_palsu(teks=BRIEF, galat=None, rekam=None):
    def f(path, data=None, timeout=300):
        if rekam is not None:
            rekam.append((path, data))
        if galat:
            raise galat
        return {"choices": [{"message": {"content": teks}}]}
    return f


class DasarSerah(DasarServer):
    DASAR = {"mode": 2, "model_p": "A", "model_e": "B", "maks": 2, "uji": False}

    def setUp(self):
        super().setUp()
        with asisten.AGENT_COND:
            asisten.AGENT.update(sesi=None, id=None, tugas="", events=[], awal=0, aktif=False, mulai=0.0,
                                 status=None, chat_id=None)
        self.dimuat = []
        p = mock.patch.object(asisten, "muat_model", lambda nama: self.dimuat.append(nama))
        p.start()
        self.addCleanup(p.stop)
        self.cid = None

    def siap(self, model="A"):
        with asisten.S_LOCK:
            asisten.S.update(model=model, status="siap", skill=("tanpa",), kita_muat=False)
        kode, isi = self.req("POST", "/api/chat/baru", {})
        self.cid = json.loads(isi)["id"]
        return self.cid

    def diskusi(self, *pasang):
        for peran, teks in pasang:
            server_chat.tambah_pesan(self.cid, {"role": peran, "content": teks})

    def chat(self):
        return json.loads(self.req("GET", "/api/chat/" + self.cid)[1])

    def baca_event(self, sesi):
        ev, nomor = [], 0
        for _ in range(100):
            kode, isi = self.req("GET", "/api/agent/event?sesi=%s&dari=%d&tunggu=5" % (sesi, nomor))
            d = json.loads(isi)
            ev += d["events"]
            nomor = d["next"]
            if d["habis"]:
                return ev
        self.fail("proses tidak selesai")

    def tunggu(self, kondisi, detik=5):
        mulai = time.time()
        while time.time() - mulai < detik:
            if kondisi():
                return True
            time.sleep(0.02)
        return False

    def kirim_agent(self, **tambahan):
        body = dict(self.DASAR, id=self.cid, tugas=BRIEF)
        body.update(tambahan)
        return self.req("POST", "/api/handoff/kirim", body)


class TestRingkasDiskusi(DasarSerah):
    def test_brief_disusun_dari_diskusi_dan_lampiran(self):
        self.siap()
        paket = self.unggah("main.py", MAIN_BUG.encode())[1]["paket"]
        with mock.patch.object(agen, "giliran", lambda *a, **k: iter([{"t": "token", "d": "ok"}])):
            self.req("POST", "/api/kirim", {"id": self.cid, "teks": "tolong lihat kode ini", "unggahan": paket})
        self.diskusi(("assistant", "Boleh, apa yang ingin diperbaiki?"), ("user", "perbaiki pembagian nol"))
        rekam = []
        with mock.patch.object(agen, "llama", llama_palsu(rekam=rekam)):
            kode, isi = self.req("POST", "/api/handoff/ringkas", {"id": self.cid})
        d = json.loads(isi)
        self.assertEqual(kode, 200)
        self.assertEqual(d["ringkasan"], BRIEF)
        self.assertTrue(d["otomatis"])
        self.assertEqual([x["nama"] for x in d["lampiran"]], ["main.py"])
        self.assertEqual(d["jalur"], "buat")                       # BRIEF tidak menyebut perbaikan
        kirim = rekam[0][1]["messages"][1]["content"]
        for ada in ("Pengguna: tolong lihat kode ini", "[berkas terlampir: main.py]", "Asisten: Boleh",
                    "Pengguna: perbaiki pembagian nol"):
            self.assertIn(ada, kirim)
        self.assertNotIn("<berkas", kirim)                         # isi berkas tidak ikut diringkas
        self.assertFalse(asisten.GEN_LOCK.locked())
        self.assertEqual(asisten.S["status"], "siap")              # ringkas tidak membongkar model

    def test_jalur_disarankan_dari_brief(self):
        self.siap()
        self.diskusi(("user", "kode saya error"))
        server_handoff.simpan_lampiran  # noqa: B018 - fungsi tersedia
        paket = self.unggah("a.py", b"x = 1\n")[1]["paket"]
        server_handoff.simpan_lampiran(self.cid, paket)
        with mock.patch.object(agen, "llama", llama_palsu("Tujuan: perbaiki bug pembagian nol di a.py.\n" * 2)):
            d = json.loads(self.req("POST", "/api/handoff/ringkas", {"id": self.cid})[1])
        self.assertEqual((d["jalur"], d["jalur_label"]), ("perbaiki", "Perbaiki kode"))

    def test_model_gagal_memakai_pesan_pengguna_sebagai_brief(self):
        self.siap()
        self.diskusi(("user", "buat program halo dunia"), ("assistant", "siap"), ("user", "pakai Python ya"))
        with mock.patch.object(agen, "llama", llama_palsu(galat=OSError("putus"))):
            d = json.loads(self.req("POST", "/api/handoff/ringkas", {"id": self.cid})[1])
        self.assertFalse(d["otomatis"])
        self.assertIn("pakai Python ya", d["ringkasan"])
        self.assertIn("buat program halo dunia", d["ringkasan"])
        with mock.patch.object(agen, "llama", llama_palsu("pendek")):                   # keluaran terlalu pendek
            d = json.loads(self.req("POST", "/api/handoff/ringkas", {"id": self.cid})[1])
        self.assertFalse(d["otomatis"])

    def test_penolakan(self):
        self.assertEqual(self.req("POST", "/api/handoff/ringkas", {"id": "20260101-000000-abcd"})[0], 404)
        self.siap()
        self.assertEqual(self.req("POST", "/api/handoff/ringkas", {"id": self.cid})[0], 400)   # belum ada diskusi
        self.diskusi(("user", "halo"))
        with asisten.S_LOCK:
            asisten.S["status"] = "kosong"
        self.assertEqual(self.req("POST", "/api/handoff/ringkas", {"id": self.cid})[0], 409)   # model belum dimuat
        with asisten.S_LOCK:
            asisten.S["status"] = "siap"
        asisten.GEN_LOCK.acquire()
        try:
            self.assertEqual(self.req("POST", "/api/handoff/ringkas", {"id": self.cid})[0], 409)   # sedang menjawab
        finally:
            asisten.GEN_LOCK.release()
        self.assertEqual(self.req("POST", "/api/handoff/ringkas", {"id": self.cid}, token=False)[0], 401)

    def test_pesan_agent_tidak_masuk_transkrip(self):
        chat = {"pesan": [{"role": "user", "content": "buat x"},
                          {"role": "assistant", "content": "🏭 Diserahkan ke Agent: x", "agent": {"status": "berjalan"}},
                          {"role": "assistant", "content": "✔ Agent selesai", "hasil": {"run": "r"}},
                          {"role": "assistant", "content": "jawaban biasa"}]}
        t = server_handoff._transkrip(chat)
        self.assertIn("Pengguna: buat x", t)
        self.assertIn("Asisten: jawaban biasa", t)
        self.assertNotIn("Diserahkan", t)
        self.assertNotIn("Agent selesai", t)


class TestSerahkan(DasarSerah):
    def jalankan_penuh(self, stream, **tambahan):
        self.pasang(LlamaPalsu("A", "B"), stream)
        kode, isi = self.kirim_agent(**tambahan)
        self.assertEqual(kode, 200, isi)
        return json.loads(isi)["sesi"]

    def test_hasil_kembali_ke_obrolan_dan_model_chat_dimuat_ulang(self):
        self.siap("A")
        self.diskusi(("user", "buat program halo"), ("assistant", "baik"))
        stream = StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], jelaskan=["Selesai dibuat."])
        sesi = self.jalankan_penuh(stream)
        # sesudah diserahkan: model chat dilepas dari memori, status Agent mencatat obrolan asal
        status = json.loads(self.req("GET", "/api/status")[1])
        self.assertEqual(status["agent"]["chat_id"], self.cid)
        ev = self.baca_event(sesi)
        self.assertEqual(ev[-1]["status"], "lolos")
        # hasil sudah ada di obrolan begitu halaman diberi tahu proses berakhir (tidak ada celah balapan)
        pesan = self.chat()["pesan"]
        self.assertEqual([m["role"] for m in pesan], ["user", "assistant", "assistant", "assistant"])
        serah, hasil = pesan[2], pesan[3]
        self.assertIn("Diserahkan ke Agent", serah["content"])
        self.assertEqual((serah["agent"]["status"], serah["agent"]["run"]), ("lolos", hasil["hasil"]["run"]))
        self.assertEqual(hasil["hasil"]["status"], "lolos")
        self.assertEqual([b["nama"] for b in hasil["hasil"]["berkas"]], ["main.py"])
        self.assertIn("Agent selesai: dinyatakan jadi", hasil["content"])
        self.assertIn("Berkas hasil: main.py", hasil["content"])
        self.assertGreater(len(hasil["content"]), 80)                              # laporan Penjelas ikut
        # model chat dimuat ulang sesudahnya, dengan skill semula
        self.assertTrue(self.tunggu(lambda: self.dimuat == ["A"]), self.dimuat)
        self.assertEqual(asisten.S["skill"], ("tanpa",))
        self.assertFalse(asisten.GEN_LOCK.locked())

    def test_model_chat_dibongkar_sebelum_agent_jalan(self):
        self.siap("A")
        self.diskusi(("user", "buat program halo"))
        keadaan = []
        asli = server_agent.mulai_proses

        def pantau(*a, **k):
            keadaan.append(asisten.S["status"])
            return asli(*a, **k)
        with mock.patch.object(server_agent, "mulai_proses", pantau):
            sesi = self.jalankan_penuh(StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK],
                                                    jelaskan=["x"]))
        self.assertEqual(keadaan, ["kosong"])                                       # sudah dibongkar saat Agent mulai
        self.baca_event(sesi)

    def test_lampiran_obrolan_menjadi_bahan_kerja_agent(self):
        self.siap("A")
        paket = self.unggah("lama.zip", __import__("test_unggah").zip_bytes(
            {"p/util.py": "def dua():\n    return 2\n", "p/data.csv": "a,b\n1,2\n"}))[1]["paket"]
        with mock.patch.object(agen, "giliran", lambda *a, **k: iter([{"t": "token", "d": "ok"}])):
            self.req("POST", "/api/kirim", {"id": self.cid, "teks": "ini proyek saya", "unggahan": paket})
        self.assertEqual(sorted(x["nama"] for x in server_handoff.lampiran_chat(self.cid)), ["data.csv", "util.py"])
        self.assertFalse((self.unggah_dir / paket).exists())                       # paket sementara dibuang
        stream = StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], jelaskan=["x"])
        sesi = self.jalankan_penuh(stream)
        ev = self.baca_event(sesi)
        self.assertEqual(sorted([e for e in ev if e["t"] == "bahan"][0]["nama"]), ["data.csv", "util.py"])
        self.assertIn("util.py", stream.user["PERENCANA"][0])
        hasil = Path(self._tmp.name) / [e for e in ev if e["t"] == "mulai"][0]["id"] / "hasil"
        self.assertEqual(sorted(p.name for p in hasil.iterdir()), ["data.csv", "main.py", "util.py"])
        self.assertEqual(len(server_handoff.lampiran_chat(self.cid)), 2)           # lampiran obrolan tetap ada

    def test_cari_bug_dari_obrolan_hanya_melapor(self):
        self.siap("A")
        server_handoff.simpan_lampiran  # noqa: B018
        paket = self.unggah("main.py", MAIN_BUG.encode())[1]["paket"]
        server_handoff.simpan_lampiran(self.cid, paket)
        self.diskusi(("user", "cek kodenya"))
        stream = StreamCatat(periksa=[DIAG_BUG], jelaskan=["Ada pembagian nol."])
        sesi = self.jalankan_penuh(stream, jalur="cari_bug")
        self.baca_event(sesi)
        hasil = self.chat()["pesan"][-1]
        self.assertEqual(hasil["hasil"]["status"], "analisis")
        self.assertEqual(hasil["hasil"]["berkas"], [])                              # tidak ada berkas yang diubah
        self.assertIn("pembagian dengan nol", hasil["content"])

    def test_agent_butuh_info_dikembalikan_sebagai_pertanyaan(self):
        self.siap("A")
        self.diskusi(("user", "buat sesuatu"))
        pertanyaan = json.dumps({"tanya": "Bahasa apa yang dipakai?"})
        sesi = self.jalankan_penuh(StreamCatat(rencana=[pertanyaan]))
        self.baca_event(sesi)
        hasil = self.chat()["pesan"][-1]
        self.assertEqual(hasil["hasil"]["status"], "butuh_info")
        self.assertIn("Bahasa apa yang dipakai?", hasil["content"])

    def test_ditolak_saat_sibuk_tanpa_membongkar_model(self):
        self.siap("A")
        self.diskusi(("user", "buat program"))
        asisten.GEN_LOCK.acquire()
        try:
            kode, isi = self.kirim_agent()
        finally:
            asisten.GEN_LOCK.release()
        self.assertEqual(kode, 409)
        self.assertEqual(asisten.S["status"], "siap")                               # model chat tidak disentuh
        self.assertEqual(len(self.chat()["pesan"]), 1)                              # tidak ada pesan serah terima

    def test_gagal_mulai_menarik_pesan_dan_memuat_ulang_model(self):
        self.siap("A")
        self.diskusi(("user", "buat program"))

        def gagal(*a, **k):
            raise server_agent.ProsesGagal(409, "Masih ada proses berjalan")
        with mock.patch.object(server_agent, "mulai_proses", gagal):
            kode, isi = self.kirim_agent()
        self.assertEqual(kode, 409)
        self.assertEqual(len(self.chat()["pesan"]), 1)                              # pesan serah terima ditarik
        self.assertTrue(self.tunggu(lambda: self.dimuat == ["A"]), self.dimuat)

    def test_validasi_permintaan(self):
        self.siap("A")
        self.assertEqual(self.kirim_agent(tugas="  ")[0], 400)
        self.assertEqual(self.req("POST", "/api/handoff/kirim", dict(self.DASAR, id="20260101-000000-abcd", tugas="x"))[0], 404)
        self.assertEqual(self.kirim_agent(model_p="tidak-ada")[0], 400)
        self.assertEqual(self.kirim_agent(tugas="x" * (tim.MAKS_TUGAS + 1))[0], 400)
        self.assertEqual(self.req("POST", "/api/handoff/kirim", dict(self.DASAR, id=self.cid, tugas="x"), token=False)[0], 401)
        self.assertEqual(asisten.S["status"], "siap")

    def test_tanpa_muat_ulang_bila_diminta(self):
        self.siap("A")
        self.diskusi(("user", "buat program halo"))
        sesi = self.jalankan_penuh(StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK],
                                                jelaskan=["x"]), muat_ulang=False)
        self.baca_event(sesi)
        time.sleep(0.3)
        self.assertEqual(self.dimuat, [])

    def test_halaman_lain_tidak_bisa_memuat_model_saat_agent_bekerja(self):
        self.siap("A")
        self.diskusi(("user", "buat program halo"))
        stream = StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], jelaskan=["x"])
        masuk, boleh = threading.Event(), threading.Event()

        def sebelum(peran):
            if peran == "PELAKSANA":
                masuk.set()
                boleh.wait(20)
        stream.sebelum = sebelum
        self.addCleanup(boleh.set)
        sesi = self.jalankan_penuh(stream)
        self.assertTrue(masuk.wait(10))
        self.assertEqual(self.req("POST", "/api/model/pilih", {"model": "A"})[0], 409)
        kode, isi = self.req("POST", "/api/kirim", {"id": self.cid, "teks": "halo"})
        self.assertEqual(kode, 409)
        boleh.set()
        self.baca_event(sesi)


class TestLampiranObrolan(DasarSerah):
    def test_lampiran_bertambah_antar_pesan_dan_ikut_terhapus(self):
        self.siap("A")
        with mock.patch.object(agen, "giliran", lambda *a, **k: iter([{"t": "token", "d": "ok"}])):
            for nama in ("a.py", "b.py"):
                paket = self.unggah(nama, b"x = 1\n")[1]["paket"]
                self.req("POST", "/api/kirim", {"id": self.cid, "teks": "lihat " + nama, "unggahan": paket})
        self.assertEqual([x["nama"] for x in server_handoff.lampiran_chat(self.cid)], ["a.py", "b.py"])
        d = server_handoff.lampiran_dir(self.cid)
        self.assertTrue(d.is_dir())
        self.assertEqual(self.req("DELETE", "/api/chat/" + self.cid)[0], 200)
        self.assertFalse(d.exists())

    def test_hapus_semua_obrolan_menghapus_lampiran(self):
        self.siap("A")
        paket = self.unggah("a.py", b"x = 1\n")[1]["paket"]
        server_handoff.simpan_lampiran(self.cid, paket)
        d = server_handoff.lampiran_dir(self.cid)
        self.assertTrue(d.is_dir())
        server_chat.hapus_semua_chat()
        self.assertFalse(d.exists())

    def test_batas_jumlah_lampiran_obrolan(self):
        self.siap("A")
        with mock.patch.object(asisten, "MAKS_BERKAS_PAKET", 2):
            paket = self.unggah("a.py", b"1\n")[1]["paket"]
            self.unggah("b.py", b"2\n", paket)
            server_handoff.simpan_lampiran(self.cid, paket)
            paket2 = self.unggah("c.py", b"3\n")[1]["paket"]
            server_handoff.simpan_lampiran(self.cid, paket2)
            self.assertEqual([x["nama"] for x in server_handoff.lampiran_chat(self.cid)], ["a.py", "b.py"])

    def test_kunci_tampilan_tidak_dikirim_ke_model(self):
        riwayat = [{"role": "assistant", "content": "🏭 Diserahkan", "agent": {"status": "berjalan"}},
                   {"role": "assistant", "content": "✔ selesai", "hasil": {"run": "r", "berkas": []}},
                   {"role": "user", "content": "lanjut"}]
        for m in agen.siapkan(riwayat, 100000):
            self.assertEqual(set(m), {"role", "content"})


class TestUnduhan(DasarServer):
    def buat_run(self):
        from test_tim import DasarAgent  # noqa: F401
        sesi = None
        self.pasang(LlamaPalsu("A", "B"), StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK],
                                                       jelaskan=["x"]))
        kode, isi = self.req("POST", "/api/agent/jalankan", {"teks": "buat halo", "mode": 2, "model_p": "A",
                                                             "model_e": "B", "maks": 2, "uji": False})
        sesi = json.loads(isi)["sesi"]
        for _ in range(100):
            d = json.loads(self.req("GET", "/api/agent/event?sesi=%s&dari=0&tunggu=5" % sesi)[1])
            if d["habis"]:
                break
        return [e for e in d["events"] if e["t"] == "mulai"][0]["id"]

    def setUp(self):
        super().setUp()
        with asisten.AGENT_COND:
            asisten.AGENT.update(sesi=None, id=None, tugas="", events=[], awal=0, aktif=False, mulai=0.0,
                                 status=None, chat_id=None)

    def test_unduh_satu_berkas_dan_zip(self):
        run = self.buat_run()
        kode, isi = self.req("GET", "/api/agent/run/%s/unduh?berkas=main.py" % run)
        self.assertEqual(kode, 200)
        self.assertEqual(isi.decode(), (Path(self._tmp.name) / run / "hasil" / "main.py").read_text())
        kode, isi = self.req("GET", "/api/agent/run/%s/unduh" % run)
        self.assertEqual(kode, 200)
        with zipfile.ZipFile(io.BytesIO(isi)) as z:
            self.assertEqual(z.namelist(), ["main.py"])
            self.assertEqual(z.read("main.py").decode(), (Path(self._tmp.name) / run / "hasil" / "main.py").read_text())

    def test_penolakan_unduhan(self):
        run = self.buat_run()
        base = "/api/agent/run/%s/unduh" % run
        self.assertEqual(self.req("GET", base, token=False)[0], 401)
        for nama in ("../run.json", "..%2Frun.json", "tidak-ada.py", "a.exe"):
            self.assertIn(self.req("GET", base + "?berkas=" + nama)[0], (400, 404), nama)
        self.assertEqual(self.req("GET", "/api/agent/run/20260101-000000-abcd/unduh")[0], 404)
        self.assertEqual(self.req("GET", "/api/agent/run/..%2F..%2Fetc/unduh")[0], 404)

    def test_header_unduhan(self):
        import urllib.request
        run = self.buat_run()
        r = urllib.request.Request("http://127.0.0.1:%d/api/agent/run/%s/unduh" % (self.port, run))
        r.add_header("Authorization", "Bearer " + self.TOKEN)
        with urllib.request.urlopen(r, timeout=10) as resp:
            self.assertEqual(resp.headers["Content-Type"], "application/zip")
            self.assertRegex(resp.headers["Content-Disposition"], r'^attachment; filename="[A-Za-z0-9_-]+\.zip"$')


class TestLanjutHasilSebelumnya(DasarSerah):
    def serah_pertama(self):
        self.siap("A")
        paket = self.unggah("main.py", MAIN_BUG.encode())[1]["paket"]
        server_handoff.simpan_lampiran(self.cid, paket)
        self.diskusi(("user", "buat program halo"))
        stream = StreamCatat(rencana=[RENCANA], tulis=[KODE_BAIK], periksa=[NILAI_OK], jelaskan=["x"])
        self.pasang(LlamaPalsu("A", "B"), stream)
        sesi = json.loads(self.kirim_agent()[1])["sesi"]
        ev = self.baca_event(sesi)
        self.assertTrue(self.tunggu(lambda: self.dimuat == ["A"]))
        with asisten.S_LOCK:                                     # model chat sudah dimuat ulang
            asisten.S.update(model="A", status="siap")
        return [e for e in ev if e["t"] == "mulai"][0]["id"]

    def test_ringkas_menyarankan_hasil_terakhir_untuk_dilanjutkan(self):
        run = self.serah_pertama()
        self.diskusi(("user", "tambahkan fungsi kali"))
        with mock.patch.object(agen, "llama", llama_palsu()):
            d = json.loads(self.req("POST", "/api/handoff/ringkas", {"id": self.cid})[1])
        self.assertEqual(d["lanjut"]["run"], run)
        self.assertEqual(d["lanjut"]["status"], "lolos")
        self.assertTrue(d["lanjut"]["judul"])

    def test_lanjut_tidak_ditimpa_lampiran_asli(self):
        """Perbaikan Agent sebelumnya tidak boleh tertimpa berkas asli dari lampiran obrolan."""
        run = self.serah_pertama()
        hasil_awal = (Path(self._tmp.name) / run / "hasil" / "main.py").read_text()
        self.assertNotEqual(hasil_awal, MAIN_BUG)                              # Pelaksana menulis ulang main.py
        stream = StreamCatat(rencana=[RENCANA], tulis=["=== FILE: util.py ===\nx = 1\n=== END ==="],
                             periksa=[NILAI_OK], jelaskan=["x"])
        self.pasang(LlamaPalsu("A", "B"), stream)
        kode, isi = self.kirim_agent(lanjut=run)
        self.assertEqual(kode, 200, isi)
        ev = self.baca_event(json.loads(isi)["sesi"])
        self.assertNotIn("bahan", jenis_ev(ev))                                 # lampiran tidak ditimpakan lagi
        baru = Path(self._tmp.name) / [e for e in ev if e["t"] == "mulai"][0]["id"]
        self.assertEqual((baru / "hasil" / "main.py").read_text(), hasil_awal)
        self.assertTrue((baru / "hasil" / "util.py").is_file())
        self.assertEqual(json.loads((baru / "run.json").read_text())["lanjut"], run)

    def test_lanjut_tidak_valid_ditolak_tanpa_membongkar_model(self):
        self.siap("A")
        self.diskusi(("user", "buat sesuatu"))
        for lanjut in ("../x", "20260101-000000-abcd", 5):
            self.assertEqual(self.kirim_agent(lanjut=lanjut)[0], 400, lanjut)
        self.assertEqual(asisten.S["status"], "siap")

    def test_hasil_analisis_juga_bisa_dilanjutkan_tetapi_butuh_info_tidak(self):
        self.siap("A")
        chat = {"pesan": [{"role": "assistant", "content": "x", "hasil": {"run": "20260101-000000-abcd", "status": "butuh_info"}}]}
        self.assertIsNone(server_handoff.hasil_terakhir(chat))
        self.assertIsNone(server_handoff.hasil_terakhir({"pesan": []}))
        self.assertIsNone(server_handoff.hasil_terakhir(
            {"pesan": [{"role": "assistant", "hasil": {"run": "20260101-000000-abcd", "status": "lolos"}}]}))   # folder tidak ada


def jenis_ev(ev):
    return [e["t"] for e in ev]


class TestHalamanSerahTerima(unittest.TestCase):
    WEB = Path(__file__).resolve().parent.parent / "web"

    def test_serahkan_js_dengan_dom_tiruan(self):
        import shutil
        import subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node tidak terpasang")
        r = subprocess.run([node, str(Path(__file__).resolve().parent / "serahkan_smoke.js")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "OK")

    def test_halaman_chat_memuat_dan_memakai_modul(self):
        html = (self.WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="serahkan.css"', html)
        self.assertLess(html.index('src="serahkan.js"'), html.index('src="index.js"'))
        js = (self.WEB / "index.js").read_text(encoding="utf-8")
        for pasti in ("Serahkan.pasang", "serah.kartuHasil(m.hasil)", "serah.pulihkan(ag)", "setAgentAktif", "serah.tampilkan"):
            self.assertIn(pasti, js)

    def test_halaman_agent_membuka_proses_dari_tautan(self):
        js = (self.WEB / "agent.js").read_text(encoding="utf-8")
        self.assertIn("qs.get('run')", js)
        self.assertIn("bukaRun(bukaDariTautan)", js)

    def test_berkas_statis_dilayani_server(self):
        from server import server_http
        for p in ("/serahkan.js", "/serahkan.css"):
            nama, _ = server_http.STATIS[p]
            self.assertTrue((self.WEB / nama).is_file(), p)


if __name__ == "__main__":
    unittest.main()
