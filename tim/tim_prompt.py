"""Prompt tiap peran (Perencana, Pelaksana, Pemeriksa, Penjelas) dan penyusun isi prompt.
"""
import json

import agen

from . import tim_config as conf
from .tim_spec import spec_model


SYSTEM_PERENCANA = (
    "Kamu PERENCANA dalam tim pembuat program. Tugasmu mengubah permintaan pengguna menjadi "
    "lembar tugas untuk PELAKSANA (model lain yang menulis kode). Kamu TIDAK menulis kode.\n"
    "Balas HANYA dengan satu objek JSON, tanpa teks lain, dengan kunci:\n"
    '- "judul": judul singkat (maksimal 6 kata)\n'
    '- "ringkasan": 1-2 kalimat tentang apa yang harus dibuat\n'
    '- "bahasa": python, javascript, html, bash, atau lainnya\n'
    '- "berkas": daftar {"nama": "main.py", "fungsi": "tugas berkas ini"}; maksimal 5 berkas, '
    "nama sederhana tanpa spasi\n"
    '- "langkah": maksimal 3 langkah garis besar, tanpa nama library dan tanpa potongan kode\n'
    '- "kriteria": daftar syarat selesai yang bisa diperiksa (maksimal 5); tidak boleh saling '
    "bertentangan\n"
    '- "jalankan": perintah uji berupa daftar, mis. ["python3", "main.py"]. Kosongkan [] bila '
    "programnya interaktif, butuh internet, atau berupa tampilan/GUI/web. Program yang diuji "
    "harus selesai sendiri dalam beberapa detik tanpa input keyboard (pakai data contoh bawaan).\n"
    '- "harapan": daftar teks pendek yang PASTI muncul di keluaran program bila benar, mis. ["88"] '
    "untuk jumlah 10 bilangan Fibonacci pertama (0+1+1+2+3+5+8+13+21+34). Isi HANYA bila kamu "
    '100% yakin dengan hasil hitungannya dan "jalankan" tidak kosong; selain itu [].\n'
    '- "catatan": asumsi yang kamu ambil\n'
    '- "tanya": isi HANYA bila permintaan benar-benar tidak bisa dikerjakan tanpa info tambahan '
    '(satu pertanyaan singkat) dan biarkan "berkas" kosong. Selain itu isi "" dan buat asumsi '
    "sendiri.\n"
    "Pilih rancangan paling sederhana yang memenuhi permintaan. Utamakan library standar.")


SYSTEM_PELAKSANA = (
    "Kamu PELAKSANA dalam tim pembuat program. Tulis kode sesuai lembar tugas dari PERENCANA.\n"
    "Kamu hanya MENULIS kode: kamu tidak menjalankan dan tidak menilai programmu. PEMERIKSA yang "
    "Kmau hanya MENULIS kode: tidak perlu menjelaskan bagaimana memakai atu cara menjalankan nya."
    "Format keluaran WAJIB, untuk setiap berkas:\n"
    "=== FILE: nama_berkas ===\n"
    "(isi LENGKAP berkas)\n"
    "=== END ===\n"
    "Aturan:\n"
    "1. Tulis isi berkas LENGKAP dan siap jalan, bukan potongan, juga saat hanya memperbaiki "
    "satu bagian.\n"
    "2. Jangan memakai pagar ``` dan jangan menulis penjelasan di luar blok berkas.\n"
    "3. Tulis berkas yang tercantum di lembar tugas; berkas lain hanya bila benar-benar perlu.\n"
    "4. Bila lembar tugas punya perintah \"jalankan\", program harus selesai sendiri tanpa "
    "meminta input keyboard dan mencetak hasilnya.\n"
    "5. Bila ada KOREKSI, perbaiki masalah yang disebut di dalamnya. Ubah HANYA bagian yang "
    "bermasalah; jangan merusak bagian yang sudah benar.\n"
    "6. Saran koreksi bisa keliru. Abaikan saran yang bertentangan dengan lembar tugas atau "
    "dengan keluaran program yang sudah benar.\n"
    "7. Utamakan library standar; jangan menginstal paket.")


SYSTEM_PEMERIKSA = (
    "Kamu PEMERIKSA dalam tim pembuat program. Kamulah yang MENJALANKAN program buatan "
    "PELAKSANA dan yang MENENTUKAN benar atau salah. HASIL KAMU MENJALANKAN PROGRAM (sintaks dan "
    "keluaran program yang benar-benar dijalankan) adalah fakta.\n"
    "Balas HANYA dengan satu objek JSON:\n"
    '{"ok": true atau false, "ringkas": "satu kalimat penilaian", '
    '"masalah": ["berkas:baris - uraian bug nyata"], '
    '"dilihat": "kutipan PERSIS dari keluaran program atau baris kode yang salah", '
    '"perbaikan": "instruksi konkret untuk pelaksana"}\n'
    "Aturan:\n"
    "1. ok=true berarti hasil SUDAH JADI dan tim selesai. Pakai ok=true bila semua kriteria "
    "utama terpenuhi dan tidak ada bug nyata.\n"
    "2. ok=false berarti koreksimu dikirim ke PELAKSANA. Wajib isi \"masalah\" (kesalahan nyata), "
    "\"dilihat\" (kutipan persis dari keluaran atau kode yang salah), dan \"perbaikan\" "
    "(instruksi konkret). ok=false tanpa masalah konkret tidak bisa dikirim sebagai koreksi.\n"
    "3. Bila hasil menjalankan memuat GAGAL (sintaks salah, berkas belum dibuat, program error), "
    "itu kesalahan nyata: jangan jawab ok=true.\n"
    "4. Harapan Perencana hanya petunjuk dan bisa keliru; kamu yang memutuskan.\n"
    "5. Jangan menuntut gaya penulisan, fitur tambahan, atau hal di luar kriteria. Jangan "
    "mengarang masalah atau angka yang tidak ada di keluaran. Jangan menyarankan mengubah "
    "algoritma yang keluarannya sudah benar.\n"
    "6. Maksimal 5 masalah.")


SYSTEM_PENJELAS = (
    "Kamu PENJELAS: wajah tim bagi pengguna. Jelaskan dalam bahasa Indonesia yang ramah, "
    "3-5 kalimat, APA yang dibuat program dan cara kerjanya secara garis besar, berdasarkan "
    "lembar tugas dan kode. JANGAN menulis status lolos/gagal, hasil uji, angka keluaran, atau "
    "saran perbaikan: bagian itu ditulis oleh sistem. Jangan mengarang fitur yang tidak ada di kode.")


def blok_berkas(berkas, anggaran, nomor=False):
    """Teks berkas untuk prompt, dipotong rata bila melebihi anggaran karakter."""
    if not berkas:
        return "(belum ada berkas)"
    per = max(500, anggaran // len(berkas))
    bagian = []
    for nama, isi in berkas:
        teks = isi
        if nomor:
            teks = "\n".join("%d: %s" % (i, b) for i, b in enumerate(isi.splitlines(), 1))
        if len(teks) > per:
            teks = teks[:per] + "\n...[dipotong]"
        bagian.append("--- %s ---\n%s" % (nama, teks))
    return "\n".join(bagian)


def anggaran_prompt(token_keluar):
    """Karakter yang aman untuk isi prompt, menurut konteks model (ASISTEN_CTX)."""
    return max(3000, (agen.CTX_MAKS - token_keluar - 900) * 3)


# ---------------------------------------------------------------------------
# Penyusun isi prompt (pesan "user") dan susunan pesan chat
# ---------------------------------------------------------------------------
PESAN_ULANG_JSON = ("Balasanmu bukan JSON valid. Balas ulang HANYA dengan objek JSON sesuai "
                    "format.")


PESAN_MINTA_MASALAH = ("Kamu menjawab ok=false tanpa masalah yang konkret, sehingga tidak ada koreksi "
                       "untuk Pelaksana. Balas ulang HANYA dengan objek JSON: bila ada kesalahan "
                       "nyata, isi \"masalah\" (berkas:baris - uraian), \"dilihat\", dan "
                       "\"perbaikan\"; bila tidak ada bug nyata, jawab ok=true.")


def pesan_chat(system, user):
    """Pesan awal: prompt peran (system) + isi tugas (user)."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def pesan_ulang_json(jawaban_sebelumnya):
    """Tambahan pesan untuk meminta model mengulang jawaban yang bukan JSON valid."""
    return [{"role": "assistant", "content": jawaban_sebelumnya[:1500]},
            {"role": "user", "content": PESAN_ULANG_JSON}]


def pesan_minta_masalah(jawaban_sebelumnya):
    """Tambahan pesan: Pemeriksa menolak tapi tidak menyebut masalah konkret, minta ulang."""
    return [{"role": "assistant", "content": jawaban_sebelumnya[:1500]},
            {"role": "user", "content": PESAN_MINTA_MASALAH}]


def prompt_rencana(tugas, spec_lama=None, berkas_ada=()):
    """Isi prompt Perencana. `spec_lama` + `berkas_ada` hanya ada saat melanjutkan proyek."""
    user = "PERMINTAAN PENGGUNA:\n" + tugas
    if spec_lama:
        user += ("\n\nPROYEK SEBELUMNYA (lembar tugas lama):\n"
                 + json.dumps(spec_lama, ensure_ascii=False)[:2500]
                 + "\nBerkas yang sudah ada: " + (", ".join(berkas_ada) or "-")
                 + "\nBuat lembar tugas BARU yang mencakup perubahan yang diminta; daftar "
                   "\"berkas\" berisi semua berkas yang perlu ditulis ulang.")
    return user


def prompt_tulis(spec, koreksi, berkas_ada):
    """Isi prompt Pelaksana: lembar tugas, berkas saat ini, dan koreksi (bila ada)."""
    anggaran = anggaran_prompt(conf.TOKEN_TAHAP)
    user = "LEMBAR TUGAS:\n" + json.dumps(spec_model(spec), ensure_ascii=False, indent=1)
    if berkas_ada:
        user += "\n\nBERKAS SAAT INI:\n" + blok_berkas(
            berkas_ada, max(1500, anggaran - len(user) - 3000))
    if koreksi:
        user += "\n\nKOREKSI YANG HARUS DIPERBAIKI:\n" + koreksi[:2500]
    user += ("\n\nTulis semua berkas yang tercantum di lembar tugas (isi LENGKAP) dengan "
             "format === FILE: nama === ... === END ===.")
    return user


def prompt_periksa(spec, cek_baris, berkas):
    """Isi prompt Pemeriksa: lembar tugas, kode bernomor baris, dan hasil ia menjalankan program."""
    anggaran = anggaran_prompt(conf.TOKEN_PERIKSA)
    return ("LEMBAR TUGAS:\n" + json.dumps(spec_model(spec), ensure_ascii=False, indent=1)
            + "\n\nBERKAS (dengan nomor baris):\n"
            + blok_berkas(berkas, max(1500, anggaran - 2500), nomor=True)
            + "\n\nHASIL KAMU MENJALANKAN PROGRAM (fakta, bukan pendapat):\n"
            + "\n".join(cek_baris)[:1800])


def prompt_jelas(spec, berkas):
    """Bahan untuk Penjelas: apa program ini (tanpa status uji, itu urusan sistem)."""
    bagian = ["RINGKASAN: " + spec["ringkasan"],
              "BERKAS: " + ", ".join("%s (%s)" % (b["nama"], b["fungsi"]) for b in spec["berkas"])]
    if berkas:
        bagian.append("KODE:\n" + blok_berkas(berkas, 3000))
    return "\n\n".join(bagian)
