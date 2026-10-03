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

- Riwayat obrolan tersimpan di `riwayat/` dan bisa dibuka lagi (tombol menu).
- Tombol **Stop** menghentikan jawaban yang sedang berjalan.
- Kartu izin (Ya/Tolak) sebelum perintah shell atau penulisan file.
- Mode **AUTO** (di menu): tanpa konfirmasi, kecuali `sudo` dan instal paket.

## Keamanan

- Semua `/api` wajib **token** (`.token`, izin 600). Jangan bagikan alamat berisi token.
- Server memakai HTTP biasa di jaringan lokal. Jangan buka port 8090 ke internet.
  Untuk akses dari luar rumah, pakai VPN seperti Tailscale.
- Perintah dengan `sudo` dan instal/hapus paket (`apt`, `pip`, `npm`) **selalu** minta izin.
- Perintah berbahaya (`rm -rf /`, `mkfs`, `dd of=/dev/...`, `reboot`, dll.) **selalu diblokir**.
- Semua aksi tool dicatat di `aksi.log`.
- Daftar blokir hanya pengaman dasar. Baca perintah sebelum menekan Ya.

## Berkas

| Berkas | Fungsi |
|---|---|
| `asisten.py` | server web, siklus model, log terminal |
| `agen.py` | tools, pengaman, klien llama-server, loop agen |
| `web/index.html` | tampilan chat |
| `cli_lama.py` | versi CLI lama (tanpa web), masih bisa dipakai |
| `riwayat/`, `.token`, `aksi.log` | data (dibuat otomatis) |

## Batasan

Model kecil cukup untuk tugas sederhana (lihat folder, baca file, cek status) tetapi
sering salah di tugas berlangkah banyak. Konteks server 8192 token, jadi riwayat lama
dipangkas saat dikirim ke model (riwayat di disk tetap utuh). Hanya satu proses
generasi berjalan pada satu waktu.
