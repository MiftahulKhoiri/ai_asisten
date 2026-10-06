# ai_asisten

Asisten AI lokal dengan tampilan chat web yang bisa dibuka dari HP. Otaknya model
di `llama-server` (Raspberry Pi 5), dan ia bisa menjalankan perintah, membaca/menulis
file, dan melihat folder lewat *function calling*. Hanya memakai library standar Python.

Terminal hanya untuk menyalakan aplikasi dan menampilkan log.

## Menjalankan

```bash
cd ~/ai_asisten
python3 asisten.py
```

Terminal menampilkan alamat seperti `http://192.168.x.x:8090/?token=...`.
Buka alamat itu dari HP (harus satu Wi-Fi dengan Pi). Token tersimpan di browser,
jadi berikutnya cukup buka `http://IP:8090`.

Opsi: `--port 8090`, `--idle 20` (menit; 0 = mati), `--auto`, `--token-baru`, `--tanpa-warna`.

## Alur sesi

1. Buka halaman web, **pilih model**. Model baru dimuat setelah dipilih.
2. Chat. Jawaban muncul bertahap (streaming), tiap tool tampil sebagai kartu.
3. Model **otomatis dibongkar dari memori** saat:
   - menekan tombol **Selesai** di web,
   - tidak ada aktivitas selama `--idle` menit (default 20),
   - menekan **Ctrl+C** di terminal (atau proses dihentikan).

Model yang sudah termuat oleh pihak lain (misalnya klien Termux) dipakai apa adanya
dan **tidak** dibongkar.

## Fitur web

- Riwayat obrolan tersimpan di `riwayat/` dan bisa dibuka lagi (tombol menu). Tiap obrolan
  menampilkan jumlah pesan dan cuplikan jawaban terakhir; ada kolom **cari** dan tombol
  **Hapus semua obrolan** (obrolan yang sedang dibuka tetap disimpan).
- Kartu tool punya ikon dan lencana status (berjalan, selesai, gagal, ditolak).
- Tombol **Salin** di setiap blok kode dan hasil tool.
- Tombol **Stop** menghentikan jawaban yang sedang berjalan.
- Kartu izin (Ya/Tolak) sebelum perintah shell atau penulisan file.
- Mode **AUTO** (di menu): tanpa konfirmasi, kecuali `sudo` dan instal paket.

## Tools

| Tool | Fungsi | Izin |
|---|---|---|
| `jalankan_perintah` | satu perintah bash | tanya (kecuali AUTO) |
| `baca_file` | baca file; `dari_baris`/`sampai_baris` untuk bagian tertentu | - |
| `baca_ekor` | N baris terakhir (log) | - |
| `daftar_folder`, `pohon_folder` | isi folder / struktur bertingkat | - |
| `info_file` | ukuran, waktu ubah, izin, pemilik, jumlah baris | - |
| `cari_file`, `cari_teks` | cari nama file / cari teks di dalam file | - |
| `info_sistem` | ringkas (suhu, CPU, RAM, disk), proses, port, jaringan, disk, layanan, log_layanan | - |
| `git_baca` | status, log, diff, branch, remote | - |
| `hitung` | kalkulator aman | - |
| `waktu_sekarang` | tanggal, jam, zona waktu Pi | - |
| `bandingkan_file` | selisih (diff) dua file teks | - |
| `ukuran_folder` | total ukuran folder dan 10 isi terbesar | - |
| `cek_sintaks` | periksa sintaks `.py`, `.json`, `.sh` tanpa menjalankannya | - |
| `tulis_file` | tulis/timpa (cadangan .bak) atau tambah di akhir | tanya (kecuali AUTO) |
| `edit_file` | ganti satu potongan teks yang unik | tanya (kecuali AUTO) |
| `buat_folder`, `salin_pindah`, `arsip` | folder, salin/pindah, zip (daftar/buat/ekstrak) | tanya (kecuali AUTO) |
| `git_tulis` | add, commit, pull, push, dll. (opsi force/hard dilarang) | tanya; push selalu |
| `ambil_url` | baca halaman web atau unduh file | tanya (kecuali AUTO) |
| `hapus` | pindah ke `~/.sampah_asisten` (bisa dipulihkan) | selalu tanya |
| `matikan_proses` | kirim sinyal ke PID | selalu tanya |

Menambah tool: tulis satu fungsi dengan dekorator `@tool(...)` di `src/tolls.py`;
skema untuk model dibuat otomatis. Banyak tool memakan konteks model (8192 token);
jalankan dengan `ASISTEN_TOOLS=dasar python3 asisten.py` untuk hanya 4 tool inti.

## Keamanan

- Semua `/api` wajib **token** (`.token`, izin 600). Jangan bagikan alamat berisi token.
- Server memakai HTTP biasa di jaringan lokal. Jangan buka port 8090 ke internet.
  Untuk akses dari luar rumah, pakai VPN seperti Tailscale.
- Perintah dengan `sudo` dan instal/hapus paket (`apt`, `pip`, `npm`) **selalu** minta izin.
- `hapus`, `git push`, dan `matikan_proses` **selalu** minta izin, juga di mode AUTO.
- Tool pengubah file hanya boleh bekerja di home dan `/tmp` (tambah lewat `ASISTEN_AKAR_TULIS=/a:/b`), tidak di `~/.ssh`.
- `.token` dan kunci pribadi SSH tidak bisa dibaca lewat tool file.
- Perintah berbahaya (`rm -rf /`, `mkfs`, `dd of=/dev/...`, `reboot`, dll.) **selalu diblokir**.
- Semua aksi tool dicatat di `aksi.log`.
- Daftar blokir hanya pengaman dasar. Baca perintah sebelum menekan Ya.

## Berkas

| Berkas | Fungsi |
|---|---|
| `asisten.py` | server web, siklus model, log terminal |
| `agen.py` | klien llama-server, riwayat, loop agen |
| `src/tolls.py` | semua tool + pengaman (tambah tool baru di sini) |
| `web/index.html`, `index.css`, `index.js` | tampilan chat |
| `tests/` | pengujian otomatis (`unittest`) |
| `cli_lama.py` | versi CLI lama (tanpa web), masih bisa dipakai |
| `riwayat/`, `.token`, `aksi.log` | data (dibuat otomatis) |

## Pengujian

```bash
cd ~/ai_asisten
python3 -m unittest discover -s tests -v
```

Mencakup tool dan pengaman (`tests/test_tolls.py`), server web dan riwayat
(`tests/test_asisten.py`, memakai folder sementara, tidak menyentuh `riwayat/` asli),
serta pemeriksaan tampilan web (`tests/test_web.py`; sintaks JS dicek bila `node` terpasang).
Tidak butuh model termuat.

## Batasan

Model kecil cukup untuk tugas sederhana (lihat folder, baca file, cek status) tetapi
sering salah di tugas berlangkah banyak. Konteks server 8192 token, jadi riwayat lama
dipangkas saat dikirim ke model (riwayat di disk tetap utuh). Hanya satu proses
generasi berjalan pada satu waktu.
