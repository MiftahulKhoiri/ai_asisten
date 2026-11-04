"""Tes pengaman shell terhadap nama perintah yang disamarkan (variabel, substitusi, brace, glob)."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import pengaman, tolls, tool_sistem  # noqa: E402


class Ctx:
    def __init__(self, auto=True, izin=True, skill="semua"):
        self.auto, self.izin, self.skill = auto, izin, skill
        self.ditanya = []

    def konfirmasi(self, jenis, ringkas, detail=""):
        self.ditanya.append(jenis)
        return self.izin


# Variabel diberi nilai di dalam perintah itu sendiri: setelah diisi, jadi perintah yang sudah dikenal.
SAMAR_BLOKIR = [
    "X=rm; $X -rf ~", "X=rm; ${X} -rf /", "a=r; b=m; $a$b -rf /", "D=~; rm -rf $D", "D=/; rm -rf ${D}",
    "cmd=rm\n$cmd -rf /", "export X=rm; $X -rf $HOME", "X=/etc; rm -rf $X", "X=sudo; Y=rm; $X $Y -rf /",
    "A=shutdown; $A now", "G=git; $G push --force origin main",
]

# Nama perintah baru ditentukan saat shell berjalan: tidak terbaca, jadi SELALU tanya (juga di mode AUTO).
SAMAR_TANYA = [
    "$X -rf ~", "$(echo rm) -rf ~", "`echo rm` -rf ~", "{rm,-rf,/}", "r{m,m} x", "/bin/r? -rf x",
    "/???/r[m] x", "$'\\x72\\x6d' x", "FOO=1 $CMD arg", "ls; $EDITOR f", "sudo $X", "echo a | $X",
    "env $X y", "*.sh", "./run*", "x=1 && $RUN",
]

# Pemakaian sehari-hari yang mirip tetapi tidak menyamarkan nama perintah: tidak boleh tanya.
SAMAR_AMAN = [
    "echo $HOME", "echo $(date)", "ls $HOME/proj", "[ -f x ] && echo y", "[[ -f x ]] && echo y",
    "x=$(date); echo $x", "cd ~ && ls", "ls *.py", "echo {a,b}.txt", "mkdir -p d/{a,b}",
    "FOO=1 python3 x.py", "N=3; echo $N", "for f in a b; do echo $f; done", 'echo "$PATH"',
    "cat a.txt | grep $X", "if [ -d x ]; then ls; fi", "test -f x && echo ok", "A=1 B=2 ls",
    "grep -r 'a*b' .", "echo '$X'", "du -sh *",
]


class TestKlasifikasiSamar(unittest.TestCase):
    def cek(self, daftar, harap):
        for perintah in daftar:
            with self.subTest(perintah=perintah):
                self.assertEqual(pengaman.cek_perintah(perintah), harap)

    def test_variabel_diisi_lalu_diblokir(self):
        self.cek(SAMAR_BLOKIR, "blokir")

    def test_nama_perintah_samar_selalu_tanya(self):
        self.cek(SAMAR_TANYA, "izin")

    def test_pemakaian_biasa_tidak_terganggu(self):
        self.cek(SAMAR_AMAN, None)


class TestIsiVariabel(unittest.TestCase):
    def test_mengisi_nilai_dari_dalam_perintah(self):
        self.assertEqual(pengaman._isi_variabel("X=rm; $X -rf /"), "X=rm; rm -rf /")
        self.assertEqual(pengaman._isi_variabel("A=r; B=${A}m; $B x"), "A=r; B=rm; rm x")

    def test_variabel_dari_lingkungan_dibiarkan(self):
        self.assertIsNone(pengaman._isi_variabel("rm -rf $DIR"))
        self.assertIsNone(pengaman._isi_variabel("echo hai"))

    def test_nilai_kosong_dan_batas_jumlah(self):
        self.assertEqual(pengaman._isi_variabel("X=; rm -rf /$X"), "X=; rm -rf /")
        banyak = "; ".join("V%d=a" % i for i in range(200)) + "; echo $V199"
        self.assertIsNone(pengaman._isi_variabel(banyak))      # hanya 32 variabel pertama yang dicatat

    def test_acuan_melingkar_berhenti(self):
        hasil = pengaman._isi_variabel("A=$B; B=$A; echo $A")      # tidak boleh menggantung / berulang tak hingga
        self.assertTrue(hasil is None or isinstance(hasil, str))
        self.assertIsNone(pengaman.cek_perintah("A=$B; B=$A; echo $A"))


class TestSamarLewatTool(unittest.TestCase):
    """Jalur sebenarnya: tolls.eksekusi. `_run` dipalsukan, jadi tidak ada perintah yang sungguh jalan."""

    def test_diblokir_tanpa_bertanya_dan_tidak_dijalankan(self):
        for perintah in SAMAR_BLOKIR:
            with self.subTest(perintah=perintah):
                with mock.patch.object(tool_sistem, "_run", return_value=(0, "")) as run:
                    ctx = Ctx(auto=True, izin=True)
                    r = tolls.eksekusi("jalankan_perintah", {"perintah": perintah}, ctx)
                self.assertTrue(r.startswith("DITOLAK"), r)
                run.assert_not_called()
                self.assertEqual(ctx.ditanya, [])

    def test_tanya_walau_auto_dan_batal_bila_ditolak(self):
        for perintah in SAMAR_TANYA:
            with self.subTest(perintah=perintah):
                with mock.patch.object(tool_sistem, "_run", return_value=(0, "")) as run:
                    ctx = Ctx(auto=True, izin=False)
                    r = tolls.eksekusi("jalankan_perintah", {"perintah": perintah}, ctx)
                self.assertTrue(r.startswith("DIBATALKAN"), r)
                self.assertEqual(ctx.ditanya, ["shell"])
                run.assert_not_called()

    def test_perintah_aman_di_auto_langsung_jalan(self):
        with mock.patch.object(tool_sistem, "_run", return_value=(0, "ok")) as run:
            ctx = Ctx(auto=True, izin=False)
            tolls.eksekusi("jalankan_perintah", {"perintah": "N=3; echo $N"}, ctx)
        self.assertEqual(ctx.ditanya, [])
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
