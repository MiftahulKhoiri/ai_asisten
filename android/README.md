# AI Asisten untuk Android

Aplikasi Android yang membuka halaman web `asisten.py` di WebView. Isinya **persis sama** dengan web
(dasbor, Sesi AI Asisten, Sesi Agent, prompt, unggah, serahkan) karena halamannya diambil langsung
dari server. Kalau berkas `web/` diubah, aplikasi ikut berubah tanpa perlu build ulang.

Saat dibuka, aplikasi menampilkan **Beranda**. Tampilannya sama dengan dasbor web karena memakai
`index.css`, `dasbor.css`, `robot.css`, dan `robot.js` yang sama persis (disalin dari `web/` saat build,
bersama `beranda/`). Kalau berkas-berkas itu diubah, GitHub Actions membangun APK baru.

- **Server**: isi alamat, tekan **Tes koneksi**. Statusnya bisa aktif (beserta waktu respons), tidak aktif,
  beda jaringan, atau "bukan server AI Asisten" (port dipakai aplikasi lain). Tombol **Masuk** baru muncul
  kalau server AI Asisten aktif, lalu halaman utama web terbuka seperti biasa. Alamat yang berhasil
  disimpan di **Alamat terakhir** (maksimal 5, ketuk untuk mengetes, ✕ untuk menghapus).
- **Aplikasi**: versi dan nomor build terpasang. Pembaruan diperiksa otomatis ke GitHub Releases
  (tag `android-v*`), sama seperti Game_server. Kalau ada versi baru, tekan **Unduh dan pasang**: APK
  diunduh, ukuran dan sha256-nya diperiksa, lalu Android meminta konfirmasi "Perbarui". Saat pertama kali,
  Android meminta izin "Izinkan dari sumber ini".

Di halaman web:

- unggah berkas dan zip proyek lewat pemilih berkas Android (bisa beberapa berkas)
- unduhan dari halaman (ekspor prompt `.json`, hasil Agent `.zip`) disimpan ke **Download/AI Asisten**
- dialog konfirmasi asli Android, tautan luar dibuka di browser
- tombol **Kembali** hanya mundur ke halaman server yang sah; di halaman pertama muncul pilihan Beranda / Keluar.
  Kalau koneksi putus, aplikasi kembali ke Beranda. Di Beranda ada tombol **Keluar aplikasi**
- tema terang/gelap mengikuti sistem (Android 10+), sama seperti web

Butuh Android 7.0 atau yang lebih baru, dengan HP berada di jaringan yang sama dengan Pi (Wi-Fi yang sama atau Tailscale).

## Mengambil APK

APK dibangun otomatis oleh GitHub Actions (`.github/workflows/android.yml`), sama seperti Game_server:

- **Setiap push ke `main` yang mengubah `android/`**: buka tab **Actions → Aplikasi Android → run terbaru →
  Artifacts**, lalu unduh `AI-Asisten-v…-build….zip` (isinya APK).
- **Rilis**: samakan `android/VERSI` (misalnya `1.0.0`), lalu
  `git tag android-v1.0.0 && git push origin android-v1.0.0`. APK otomatis dilampirkan ke **Releases**,
  jadi bisa diunduh langsung dari HP tanpa login.
- Mengubah `web/` **tidak** perlu APK baru, karena aplikasi memuat halaman langsung dari server.

## Memasang

1. Pasang APK di HP (izinkan "pasang dari sumber tidak dikenal").
2. Jalankan server di Pi: `./start.sh` atau `python3 asisten.py`.
3. Buka aplikasi **AI Asisten**, isi alamat yang tampil di terminal (misalnya `http://192.168.1.10:8090/?token=...`),
   tekan **Tes koneksi**, lalu **Masuk**.

## Membangun di Pi (tanpa Android Studio dan tanpa sudo)

```bash
cd android
./siapkan-alat.sh     # cukup sekali: alat build diunduh ke ~/android-tools
./build.sh            # hasil: build/ai_asisten.apk
```

- `versionCode` = jumlah commit git (selalu naik, sama dengan build di GitHub). `versionName` diambil dari `VERSI`.
- Kunci tanda tangan ada di `kunci/` dan ikut di-commit, supaya APK dari Pi dan dari GitHub bisa saling menimpa.
  **Jangan diganti**: kalau diganti, aplikasi yang sudah terpasang harus di-uninstall dulu.
- `python3 ikon.py` membuat ulang ikon dari bentuk robot di `web/robot.svg` (hanya perlu dijalankan kalau bentuknya diubah).

## Isi folder

| Berkas | Fungsi |
|---|---|
| `AndroidManifest.xml` | identitas aplikasi `id.aiasisten.app`, izin internet, HTTP lokal diizinkan |
| `beranda/` | halaman Beranda (HTML/JS/CSS tambahan), dikemas sebagai aset APK |
| `src/id/aiasisten/app/MainActivity.java` | WebView Beranda + halaman server, jembatan JS (tes koneksi, pembaruan, unggah, unduh) |
| `src/id/aiasisten/app/Pembaruan.java` | cek rilis GitHub, unduh + sha256, pasang lewat PackageInstaller |
| `src/id/aiasisten/app/Versi.java` | fungsi murni (alamat, nomor build), diuji `uji/UjiVersi.java` saat build |
| `res/` | nama aplikasi, warna, tema, ikon |
| `ikon.py` | pembuat ikon peluncur |
| `siapkan-alat.sh` | mengunduh aapt2, zipalign, android.jar, d8, apksigner |
| `build.sh` | aapt2 → javac → d8 → zipalign → apksigner (dipakai di Pi dan di GitHub Actions) |
| `VERSI` | versi tampilan aplikasi, harus sama dengan tag `android-v…` |
| `kunci/` | kunci tanda tangan APK (jangan diganti) |
