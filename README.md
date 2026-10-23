# ai_asisten

[![tests](https://github.com/MiftahulKhoiri/ai_asisten/actions/workflows/tests.yml/badge.svg)](https://github.com/MiftahulKhoiri/ai_asisten/actions/workflows/tests.yml)

Asisten AI lokal dengan tampilan chat web yang bisa dibuka dari HP. Otaknya model
`.gguf` yang dijalankan oleh `llama-server` (llama.cpp) di Raspberry Pi 5. Ia bisa
menjalankan perintah, membaca/menulis file, melihat folder, dan mencari informasi di
internet lewat *function calling*. Aplikasinya hanya memakai library standar Python
(tanpa `pip install`).

Terminal hanya untuk menyalakan aplikasi dan menampilkan log.

## Daftar isi

1. [Cara kerja](#cara-kerja)
2. [Yang dibutuhkan](#yang-dibutuhkan)
3. [Instalasi dari nol](#instalasi-dari-nol)
4. [Menjalankan sehari-hari](#menjalankan-sehari-hari)
5. [Alur sesi](#alur-sesi)
6. [Skill (bisa digabung)](#skill-bisa-digabung)
7. [Fitur web](#fitur-web)
8. [Unggah berkas](#unggah-berkas)
9. [Agent (tim beberapa model)](#agent-tim-beberapa-model)
10. [Tools](#tools)
11. [Pengaturan (variabel lingkungan)](#pengaturan-variabel-lingkungan)
12. [Keamanan](#keamanan)
13. [Berkas](#berkas)
14. [Pengujian](#pengujian)
15. [Pemecahan masalah](#pemecahan-masalah)
16. [Batasan](#batasan)

## Cara kerja

```
 HP / browser  ──►  asisten.py (port 8090)  ──►  llama-server (port 8080)  ──►  model .gguf
 (tampilan chat)    server web + tool            mesin AI (llama.cpp)            file di ~/models
```

Ada **dua program yang harus hidup bersamaan**:

| Program | Tugas | Port |
|---|---|---|
| `llama-server` | menjalankan model AI (otak) | 8080 |
| `asisten.py` | tampilan web, tool, riwayat chat | 8090 |

Penting: `asisten.py` **tidak membawa model sendiri**. Ia hanya meminta `llama-server`
memuat dan membongkar model. Jadi sebelum `asisten.py` dijalankan, `llama-server` sudah
harus menyala dan di folder model sudah ada minimal satu file `.gguf`.

## Yang dibutuhkan

### Perangkat

| Kebutuhan | Keterangan |
|---|---|
| Komputer Linux | Dikembangkan di Raspberry Pi 5 (Raspberry Pi OS / Debian). Linux lain (Debian, Ubuntu) umumnya bisa |
| RAM | Minimal sebesar file model ditambah ruang cadangan. Contoh: model 1 GB butuh sekitar 2 GB RAM kosong. Pi 5 RAM 8/16 GB nyaman |
| Ruang disk | Beberapa GB untuk llama.cpp dan model |
| Internet | Hanya untuk instalasi, mengunduh model, dan skill Web |
| HP / laptop | Untuk membuka tampilan chat, satu Wi-Fi dengan Pi |

### Perangkat lunak

| Perangkat lunak | Wajib? | Untuk apa |
|---|---|---|
| Python 3.9+ (diuji di 3.12) | Wajib | menjalankan `asisten.py`. Tidak ada paket pip yang perlu dipasang |
| `llama-server` (dari llama.cpp) | Wajib | menjalankan model |
| **File model `.gguf`** | Wajib | otak asisten, lihat [langkah 3](#3-unduh-model-gguf) |
| `git` | Wajib untuk cara clone, juga dipakai tool `git_baca` / `git_tulis` | |
| `build-essential`, `cmake`, `libcurl4-openssl-dev` | Hanya saat membangun llama.cpp | |
| `iproute2` (`ip`, `ss`), `procps` (`ps`), `diffutils` (`diff`), `systemd` (`systemctl`, `journalctl`) | Bawaan Raspberry Pi OS | dipakai tool `info_sistem` dan `bandingkan_file` |
| `vcgencmd` | Opsional, hanya ada di Raspberry Pi | membaca status *throttling* (pembatasan kecepatan karena panas/daya) di `info_sistem` |
| `node` (Node.js) | Opsional | hanya untuk pemeriksaan sintaks JS saat pengujian |

## Instalasi dari nol

Semua perintah dijalankan di terminal Raspberry Pi (lewat SSH juga boleh).

### 1. Siapkan sistem

```bash
sudo apt update
sudo apt install -y git python3 build-essential cmake libcurl4-openssl-dev wget
python3 --version        # pastikan 3.9 atau lebih baru
```

### 2. Pasang llama.cpp (llama-server)

```bash
cd ~
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build
cmake --build build --config Release -j4
```

Proses ini bisa belasan menit di Raspberry Pi. Setelah selesai, programnya ada di
`~/llama.cpp/build/bin/llama-server`. Cek:

```bash
~/llama.cpp/build/bin/llama-server --version
```

Kalau memakai llama.cpp hasil unduhan jadi (bukan hasil build), pakai jalur `llama-server`
milikmu sendiri di langkah berikutnya.

### 3. Unduh model `.gguf`

Model adalah file besar berekstensi `.gguf`. Letakkan di folder `~/models`
(folder yang dibaca aplikasi secara bawaan).

```bash
mkdir -p ~/models
cd ~/models
wget -c https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_K_M.gguf
```

Kalau tautan itu sudah berubah, cari sendiri di [huggingface.co](https://huggingface.co):
ketik `Qwen3 1.7B GGUF`, buka tab **Files**, lalu unduh file berakhiran `Q4_K_M.gguf`.

Hal yang perlu dipahami pemula:

- **Nama file = nama model di aplikasi.** `Qwen_Qwen3-1.7B-Q4_K_M.gguf` akan muncul sebagai
  `Qwen_Qwen3-1.7B-Q4_K_M`. Jangan ganti nama sembarangan setelah dipakai.
- **Q4_K_M** adalah tingkat kompresi yang seimbang antara ukuran dan mutu. Angka parameter
  (1.7B, 3B, 9B) menentukan ukuran file dan kebutuhan RAM: makin besar, makin pintar tetapi
  makin lambat dan makin berat di Pi.
- Pilih model **Instruct/Chat** yang mendukung *tool calling*. Model tanpa dukungan itu hanya
  cocok untuk skill **Tanpa skill**.
- Boleh punya banyak model sekaligus di `~/models`. Pilihannya muncul di halaman web.
- Kalau modelmu disimpan di folder lain, atur `ASISTEN_MODELS_DIR` (lihat
  [Pengaturan](#pengaturan-variabel-lingkungan)).

Catatan hasil uji penulis di Raspberry Pi 5: `Qwen_Qwen3-1.7B-Q4_K_M` memberi jawaban paling
baik untuk tugas asisten. Beberapa model lain (misalnya Llama-3.2-3B-Instruct dan model 9B)
terlalu sering langsung memanggil tool padahal tidak perlu. Hasil ini bisa berbeda di
perangkat dan versi lain, jadi coba dulu model kecil.

### 4. Jalankan llama-server

`ai_asisten` memakai llama-server dalam **mode router**: server membaca semua `.gguf` di sebuah
folder, lalu model dimuat dan dibongkar sesuai permintaan aplikasi.

```bash
~/llama.cpp/build/bin/llama-server \
  --models-dir ~/models \
  --host 127.0.0.1 --port 8080 \
  -c 8192 --jinja
```

Arti opsinya:

| Opsi | Arti |
|---|---|
| `--models-dir ~/models` | folder berisi file `.gguf` (mode router) |
| `--host 127.0.0.1 --port 8080` | hanya bisa diakses dari Pi sendiri, port 8080 |
| `-c 8192` | ukuran konteks 8192 token (harus sama dengan `ASISTEN_CTX`, bawaan 8192) |
| `--jinja` | mengaktifkan templat chat yang dibutuhkan untuk tool calling |

Nama opsi bisa sedikit berbeda antar versi llama.cpp. Kalau ada pesan galat, jalankan
`llama-server --help` dan sesuaikan.

Biarkan terminal ini tetap terbuka (atau jalankan di `tmux`, lihat di bawah). Di terminal
kedua, cek bahwa server hidup dan melihat modelmu:

```bash
curl http://127.0.0.1:8080/v1/models
```

Hasilnya harus berupa JSON yang memuat nama modelmu. Kalau kosong atau error, jangan lanjut
dulu, lihat [Pemecahan masalah](#pemecahan-masalah).

### 5. Ambil ai_asisten

Pilih salah satu:

```bash
# Cara A: git clone
cd ~
git clone https://github.com/MiftahulKhoiri/ai_asisten.git
```

```bash
# Cara B: dari file ZIP (hasil unduhan dari GitHub)
cd ~
unzip ai_asisten-main.zip
mv ai_asisten-main ai_asisten
```

Folder hasilnya harus bernama `~/ai_asisten`.

### 6. Jalankan asisten

```bash
cd ~/ai_asisten
python3 asisten.py
```

Terminal menampilkan alamat seperti ini:

```
OK    Server jalan di http://192.168.x.x:8090
OK    Buka dari HP: http://192.168.x.x:8090/?token=...
INFO  Model belum dimuat. Pilih model dari tampilan web.
```

### 7. Buka dari HP

1. Pastikan HP satu Wi-Fi dengan Pi.
2. Buka alamat `http://192.168.x.x:8090/?token=...` di browser HP.
3. Token tersimpan di browser, jadi berikutnya cukup buka `http://IP-PI:8090`.
4. Di halaman web: **pilih skill**, lalu **pilih model**. Tunggu sampai model termuat
   (di Pi bisa puluhan detik), lalu mulai chat.

Lupa IP Pi-nya? Jalankan `hostname -I` di Pi.

## Menjalankan sehari-hari

Ada tiga cara menjalankannya. Pilih salah satu.

### Cara 1: `start.sh` (paling mudah)

```bash
cd ~/ai_asisten
./start.sh
```

Skrip ini menyalakan `llama-server` bila belum hidup, menunggu sampai siap, lalu menjalankan
`asisten.py`. Tekan Ctrl+C untuk berhenti: asisten menutup diri dulu (model dibongkar), baru
llama-server ikut dihentikan, dan hanya bila skrip ini yang menyalakannya. Opsi `asisten.py`
bisa ditambahkan di belakangnya, misalnya `./start.sh --port 8091 --idle 10`. Log llama-server
ada di `llama-server.log`.

Pengaturan lewat variabel lingkungan, contoh:
`LLAMA_BIN=/opt/llama/llama-server ASISTEN_MODELS_DIR=/mnt/models ./start.sh`
(daftar lengkap di [Pengaturan](#pengaturan-variabel-lingkungan)).
Kalau muncul `Permission denied`, jalankan `chmod +x start.sh` sekali, atau pakai `bash start.sh`.

### Cara 2: otomatis saat Pi menyala (systemd)

```bash
cd ~/ai_asisten
./deploy/pasang-layanan.sh
```

Skrip memasang dua layanan systemd tingkat-pengguna (tanpa sudo): `llama-server` dan
`ai-asisten`. Keduanya langsung menyala dan aktif setiap Pi boot, bahkan sebelum kamu login
(lewat `loginctl enable-linger`; bila gagal, skrip menampilkan perintah `sudo` yang perlu dijalankan).

| Perintah | Fungsi |
|---|---|
| `systemctl --user status ai-asisten llama-server` | lihat status |
| `journalctl --user -u ai-asisten -f` | lihat log asisten |
| `cat ~/ai_asisten/.token` | lihat token untuk alamat `http://IP-PI:8090/?token=...` |
| `systemctl --user restart ai-asisten` | mulai ulang asisten |
| `systemctl --user stop ai-asisten llama-server` | hentikan (model dibongkar dulu) |
| `./deploy/pasang-layanan.sh --hapus` | hentikan dan hapus layanan |

Pengaturan tambahan (misalnya `ASISTEN_LOG_MAKS_KB` atau `ASISTEN_TOOLS`) ditaruh di
`~/.config/ai_asisten.env`, satu baris `NAMA=nilai`, lalu `systemctl --user restart ai-asisten`.

Catatan: jalur proyek, llama-server, dan folder model tidak boleh mengandung spasi; pasang ulang
bila jalurnya berubah. Jangan menjalankan `start.sh` bersamaan dengan layanan (port bentrok):
hentikan layanan dulu.

### Cara 3: manual (dua terminal)

Jalankan dua hal ini (di dua terminal, atau pakai `tmux`):

```bash
# terminal 1
~/llama.cpp/build/bin/llama-server --models-dir ~/models --host 127.0.0.1 --port 8080 -c 8192 --jinja

# terminal 2
cd ~/ai_asisten && python3 asisten.py
```

Supaya tetap hidup walau SSH terputus, pakai `tmux`:

```bash
sudo apt install -y tmux
tmux new -s ai        # lalu jalankan kedua perintah di jendela terpisah (Ctrl+b lalu %)
# lepas dengan Ctrl+b lalu d, kembali dengan: tmux attach -t ai
```

### Opsi `asisten.py`

| Opsi | Fungsi |
|---|---|
| `--port 8090` | port web (bawaan 8090) |
| `--host 0.0.0.0` | alamat bind (bawaan 0.0.0.0 supaya bisa dibuka dari HP) |
| `--idle 20` | menit tanpa aktivitas sebelum model dibongkar (0 = tidak pernah) |
| `--auto` | mode AUTO, tanpa konfirmasi (hati-hati, lihat [Keamanan](#keamanan)) |
| `--token-baru` | buat token baru (token lama tidak berlaku) |
| `--tanpa-warna` | log terminal tanpa warna |

## Alur sesi

1. Buka halaman web, **pilih skill** (boleh lebih dari satu) lalu **pilih model**.
   Model baru dimuat setelah dipilih.
2. Chat. Jawaban muncul bertahap (streaming), tiap tool tampil sebagai kartu.
3. Model **otomatis dibongkar dari memori** saat:
   - menekan tombol **Selesai** di web,
   - tidak ada aktivitas selama `--idle` menit (default 20),
   - menekan **Ctrl+C** di terminal (atau proses dihentikan).

Model yang sudah termuat oleh pihak lain (misalnya klien Termux) dipakai apa adanya
dan **tidak** dibongkar.

## Skill (bisa digabung)

Ada 5 skill; pilih satu atau beberapa sekaligus sebelum memuat model. Tool yang aktif
adalah **gabungan** tool dari semua skill terpilih.

| Skill | Fungsi |
|---|---|
| **Tanpa skill** | tanya jawab saja, tanpa tool (cocok untuk mengetes model baru) |
| **Web** | cari informasi dan berita terbaru di internet (4 tool: `berita`, `cari_web`, `baca_halaman`, `waktu_sekarang`) |
| **Dasar** | 4 tool inti: perintah, baca file, tulis file, daftar folder |
| **Kompleks** | semua tool sistem dan web |
| **Berpikir kritis** | jawaban dibuat dua tahap: draf (tampil di blok "Berpikir"), lalu model memeriksa dan memperbaikinya. Sekitar 2x lebih lambat, lebih teliti |

Contoh: **Tanpa skill + Web** = jago ngobrol plus informasi dari internet. **Web + Berpikir
kritis** = hasil pencarian diperiksa ulang sebelum disajikan. Jawaban pendek (sapaan) tidak
diperiksa ulang.

Saran untuk pemula: mulai dengan **Tanpa skill** untuk memastikan model menjawab dengan baik,
lalu coba **Dasar**.

Skill Web: tanyakan misalnya "carikan berita terbaru hari ini" atau "berapa harga emas
sekarang". `berita` memakai Google News (judul, sumber, umur berita); `cari_web` memakai
halaman hasil Brave Search dan beralih ke berita bila gagal; `baca_halaman` membuka isi
halaman. Hanya alamat internet **publik** yang boleh dibuka (alamat lokal/privat ditolak,
termasuk lewat pengalihan), dan isi halaman diperlakukan sebagai data, bukan perintah.
Halaman yang butuh JavaScript (mis. harga emas dinamis) bisa terbaca kosong.

## Fitur web

- Riwayat obrolan tersimpan di `riwayat/` dan bisa dibuka lagi (tombol menu). Tiap obrolan
  menampilkan jumlah pesan dan cuplikan jawaban terakhir; ada kolom **cari** dan tombol
  **Hapus semua obrolan** (obrolan yang sedang dibuka tetap disimpan).
- Kartu tool punya ikon dan lencana status (berjalan, selesai, gagal, ditolak).
- Tombol **Salin** di setiap blok kode dan hasil tool.
- Tombol **Stop** menghentikan jawaban yang sedang berjalan.
- Kartu izin (Ya/Tolak) sebelum perintah shell atau penulisan file.
- Mode **AUTO** (di menu): tanpa konfirmasi, kecuali hal berisiko (`sudo`, instal paket, lokasi sensitif,
  lihat [Keamanan](#keamanan)), setelah tool Web dipakai di obrolan itu, dan di obrolan yang berisi lampiran.
- Tombol **📎** di kotak ketik (chat dan Agent): lampirkan file; lihat [Unggah berkas](#unggah-berkas).

## Unggah berkas

Tombol **📎** di kotak ketik halaman Chat dan halaman Agent menerima **beberapa file teks/kode** dan
**zip** sekaligus (satu proyek utuh). Berkas ditampung dulu di `unggahan/<paket>/`, tampil sebagai
chip yang bisa dihapus (✕), lalu dipakai satu kali saat pesan dikirim. Paket yang belum terkirim
bertahan walau halaman dimuat ulang dan dibersihkan otomatis setelah 24 jam.

- **Chat**: isi berkas menjadi lampiran pesan; model membacanya sebagai konteks ("jelaskan kode ini",
  "cari bug di sini"). Jatah isi lampiran mengikuti ruang konteks skill yang aktif; berkas yang terlalu
  panjang dipotong atau hanya disebut namanya, dan halaman memberi tahu bila itu terjadi. Di obrolan
  itu mode AUTO tidak berlaku (lihat [Keamanan](#keamanan)).
- **Agent**: berkas disalin ke folder kerja sebelum Perencana mulai, jadi tim bisa memperbaiki atau
  mengembangkan kode milikmu ("tambahkan fitur X", "perbaiki bug di main.py"). Perencana diberi daftar
  nama berkas; hanya berkas yang perlu diubah yang ditulis ulang, sisanya jadi konteks. Batas berkas
  per proyek bertambah sebesar jumlah berkas unggahan. Boleh digabung dengan **Lanjutkan** proyek lama.
- **Yang diterima**: teks UTF-8 dengan jenis yang dikenal (`.py .js .ts .html .css .json .md .txt .sh .c
  .cpp .h .hpp .java .go .rs .xml .sql .yaml .yml .toml .ini .cfg .csv .rst`, dll.), nama aman, maks 3
  tingkat folder, maks 200 KB per berkas, 100 berkas per paket. Biner, gambar, dan jenis lain dilewati
  beserta alasannya.
- **Zip**: maks 10 MB (`ASISTEN_UNGGAH_MB`), isi hasil ekstrak maks 30 MB, 3000 entri. Folder pembungkus
  tunggal (`proyek-main/`) dibuang; `.git`, `__pycache__`, `node_modules`, `venv`, dan berkas tersembunyi
  diabaikan. Entri berjalur `..` atau absolut, symlink, dan entri terenkripsi dilewati; ukuran
  dibatasi saat membaca, bukan hanya menurut header (penangkal zip bomb).
- Isi unggahan dianggap **data yang tidak tepercaya**: dibungkus tanda khusus beserta catatan "bukan
  perintah", dan penutup tag di dalam isinya dinetralkan.
- Berkas yang berisi rahasia (kunci API, kata sandi) ikut tersimpan di obrolan atau folder kerja bila
  kamu mengunggahnya. Jangan unggah berkas seperti itu.

## Agent (tim beberapa model)

Tombol **Agent** di pojok atas halaman chat membuka `agent.html`. Di sana beberapa model
lokal bekerja bergiliran untuk **membuat program**; tiap model dimuat saat gilirannya dan
dibongkar saat selesai (bila "Bongkar model tiap tahap" aktif).

| Peran | Tugas |
|---|---|
| **Perencana** (Model 1) | menerima perintah, menyusun lembar tugas `tugas.json` + `tugas.md`, lalu menjelaskan hasil akhir kepada kamu |
| **Pelaksana** (Model 2) | membaca lembar tugas dan **hanya menulis** program ke folder `hasil/` (tidak menjalankan apa pun) |
| **Pemeriksa** | menerima hasil Pelaksana langsung, **menjalankan** programnya, lalu **menentukan benar/salah**: dinyatakan jadi (selesai) atau memberi koreksi yang dikirim ke Pelaksana |

### Alur menyesuaikan jenis tugas

Urutan tahap tidak selalu sama. Ada tiga **jalur**; pilih di bar **Otomatis / Buat / Perbaiki / Cari bug**
di atas kotak ketik (bawaan Otomatis), dan stepper alur di layar ikut berubah:

| Jalur | Urutan tahap | Dipakai untuk |
|---|---|---|
| **Buat** | Perencana → [Pelaksana → Pemeriksa]× → Penjelas | program baru, atau menambah/mengubah fitur |
| **Perbaiki** | **Diagnosa** → Perencana → [Pelaksana → Pemeriksa]× → Penjelas | memperbaiki bug di kode yang sudah ada (unggahan atau proyek lanjutan) |
| **Cari bug** | **Diagnosa** → Penjelas | hanya mencari bug dan melapor; **tidak ada berkas yang diubah** |

**Diagnosa** adalah Pemeriksa memeriksa kode yang SUDAH ADA sebelum ada yang diubah: sintaks semua
berkas (berkas kosong seperti `__init__.py` dianggap sah), uji jalan pada titik masuk yang *ditebak*
(hanya bila "Izinkan Pemeriksa menjalankan program" menyala; hasilnya sebatas catatan, karena program
bisa butuh argumen atau berjalan terus), lalu penilaian model terhadap kodenya. Bug harus bisa
ditunjuk barisnya. Sintaks salah yang dicatat sistem tidak boleh dinyatakan "tidak ada bug".

Alur bisa **berubah di tengah jalan** menurut hasil Diagnosa:
- **Tidak ada bug nyata** (jalur Perbaiki): berhenti dengan status **analisis**, Perencana dan Pelaksana
  tidak dijalankan, tidak ada berkas yang diubah. Tahap yang dilewati tampil bertanda "–".
- **Ada bug**: Perencana menyusun lembar tugas *perbaikan* dari temuan itu (hanya berkas yang perlu
  diubah, tanpa fitur baru), dan temuan menjadi **koreksi pertama** untuk Pelaksana; sesudahnya putaran
  Pelaksana → Pemeriksa berjalan seperti biasa.
- **Cari bug → Perbaiki**: sesudah analisis dengan temuan muncul tombol **🔧 Perbaiki temuan**. Prosesnya
  melanjutkan proyek yang sama dan **memakai ulang diagnosa** (tanpa memeriksa lagi) selama isi proyek
  tidak berubah.
- **Tanpa berkas**: jalur Perbaiki/Cari bug (dipilih sendiri) meminta kamu mengunggah berkas atau
  melanjutkan proyek lebih dulu, tanpa memuat model.

Pada **Otomatis**, jalur dipilih dari isi tugas dengan aturan kata kunci (tanpa memuat model; alasannya
ditampilkan): ada berkas + "perbaiki/betulkan/fix" → Perbaiki; "cari bug / review / apa yang salah /
kenapa error" → Cari bug; "tambahkan/buat/ubah" → Buat; menyebut gejala (error, crash, gagal) → Perbaiki;
tanpa berkas → Buat. Kamu selalu bisa memilih sendiri jalurnya. Pemeriksa membaca isi sebagian berkas
bila proyek besar (yang disebut di tugas, yang bermasalah, dan titik masuk didahulukan); cakupannya
ditulis di laporan.

Pilihan di halaman Agent:

- **2 model**: Model 1 = Perencana + Pemeriksa + Penjelas, Model 2 = Pelaksana.
- **3 model**: tiap peran punya model sendiri (model yang sama boleh dipakai untuk dua peran).
  Minimal harus ada 2 model yang berbeda.
- **Maksimal putaran koreksi** (1-10): berapa kali Pelaksana boleh mengulang.
- **Bongkar model tiap tahap**: hemat RAM; model yang dipakai tahap berikutnya tidak dibongkar.
- **Izinkan Pemeriksa menjalankan program hasil**: izin ada di pengaturan ini (mati secara bawaan).
  Bila menyala, program dijalankan tanpa bertanya lagi, jadi proses yang lama tidak berhenti
  menunggu jawabanmu. Bila mati, Pemeriksa hanya mengecek berkas dan sintaks.

Alur satu proses: Perencana -> Pelaksana (menulis) -> Pemeriksa (menjalankan + menentukan) ->
(koreksi kembali ke Pelaksana bila belum jadi) -> Perencana menjelaskan. Pesan lanjutan di halaman yang sama **melanjutkan proyek
yang sama** (berkas lama ikut dibawa); tombol **Proyek baru** memulai dari nol. Bila
Perencana butuh info, ia bertanya dulu; jawabanmu digabung dengan permintaan awal.

**Berjalan di latar belakang.** Proses Agent berjalan di server, bukan di halaman. Menutup
halaman, putus sinyal, atau HP tidur **tidak menghentikannya**; yang menghentikan hanya tombol
**Stop** atau mematikan aplikasi. Buka halaman Agent lagi kapan saja: bila proses masih
berjalan, halaman otomatis tersambung dan memutar ulang semua yang sudah terjadi (tahap,
berkas, hasil pemeriksaan, log berwaktu), lalu memantau terus. Proses yang sudah selesai tetap
bisa diputar ulang sampai proses berikutnya dimulai atau aplikasi dimatikan; setelah itu ada
ringkasan di Riwayat. Proses tampil di Riwayat sejak mulai dengan status **berjalan**; bila
aplikasi dimatikan di tengah proses, statusnya jadi **terhenti**. Satu proses Agent pada satu
waktu. Catatan: aplikasi harus tetap hidup (terminal/Termux/layanan systemd jangan ditutup).

**Log langsung.** Selama proses berjalan, lencana kecil muncul di pojok kanan atas chat Agent
dengan aktivitas saat ini: memuat model, berpikir, menulis kode, membongkar model, atau Pemeriksa
memeriksa dan menjalankan program (disertai nama model dan detik berjalan).
Ketuk lencana untuk membuka panel: aktivitas sekarang, status tiap model (belum dimuat / sedang
dimuat / termuat / sedang dibongkar / sudah dibongkar), keluaran model yang sedang ditulis, dan
riwayat proses bertanda waktu. Tombol **Salin log** menyalin seluruhnya. Setelah selesai, lencana
tetap ada agar log bisa ditinjau. Log disimpan di server selama aplikasi hidup, jadi bisa dibuka lagi dari halaman atau HP lain.

Pembagian tugas dibuat tegas, karena model 1-4B sering salah menilai dan sering salah format:

- **Pelaksana hanya menulis.** Ia tidak menjalankan dan tidak menilai programnya.
- **Pemeriksa menjalankan dan menentukan.** Hasil Pelaksana langsung ke Pemeriksa, setiap putaran
  (juga bila sintaksnya rusak). Di tahap Pemeriksa, programnya dijalankan (berkas ada, sintaks
  Python/JSON/JavaScript/Bash benar, uji jalan bila diizinkan di pengaturan). Hasilnya jadi **fakta** di prompt Pemeriksa, lalu **Pemeriksa yang memutuskan**:
  `ok=true` = dinyatakan jadi (selesai), `ok=false` = koreksinya (masalah + perbaikan) dikirim ke
  Pelaksana untuk putaran berikutnya.
- **Tidak ada jalan pintas dari kode.** Kode tidak lagi meloloskan hasil di belakang Pemeriksa
  (mis. karena `harapan` terpenuhi) dan tidak membalik penolakan Pemeriksa. `harapan` dari
  Perencana (teks yang pasti muncul di keluaran, mis. `88`) hanya menjadi fakta tambahan, dan
  bisa keliru.
- **Penolakan harus punya koreksi.** `ok=false` wajib menyebut masalah konkret; bila kosong,
  Pemeriksa ditanya sekali lagi. Bila tetap kosong: program yang lolos dijalankan diterima (dicatat di
  ringkasan); program yang gagal tetap ditolak dengan masalah dari hasil menjalankan.
- **Pengecualian yang tercatat**: (1) tidak ada berkas sama sekali, Pemeriksa menolak tanpa
  memanggil model; (2) jawaban Pemeriksa dua kali bukan JSON, keputusan mengikuti hasil
  menjalankan program.
- **Laporan jujur.** Bila Pemeriksa menyatakan jadi padahal hasil menjalankan mencatat `GAGAL`,
  laporan akhir menambahkan peringatan. Kamu tetap yang terakhir menilai.
- **Hasil terbaik dipulihkan**: bila akhirnya belum sempurna, berkas dikembalikan ke putaran
  terbaik, supaya koreksi yang keliru tidak merusak hasil yang sudah baik.
- **Laporan akhir**: Penjelas hanya menulis prosa tentang programnya. Status, berkas, keluaran uji
  jalan, dan hasil pemeriksaan ditambahkan oleh sistem dari data nyata, jadi tidak bisa dikarang.
- Lembar tugas untuk Pelaksana/Pemeriksa tidak memuat `langkah` buatan Perencana (sering keliru
  dan menyesatkan); langkah hanya disimpan di `tugas.md` untuk dibaca manusia.

Berkas hasil ada di `~/agent_kerja/<id>/` (`hasil/`, `tugas.json`, `koreksi_N.md`, `laporan.md`,
`run.json`, `log.jsonl` = catatan event proses, `jejak/` = prompt dan keluaran mentah tiap model
untuk diagnosis). Riwayat proses tampil di halaman Agent dan bisa dilanjutkan.

**Menghapus riwayat:** tombol **✕** di tiap item menghapus satu proses, dan **Hapus semua** di
atas daftar menghapus semuanya. Keduanya menghapus seluruh folder prosesnya, termasuk berkas
hasil program (tidak masuk tempat sampah, tidak bisa dikembalikan), dan selalu minta konfirmasi.
Proses yang sedang berjalan tidak bisa dihapus (dilewati oleh Hapus semua). Hanya folder proses
(`AAAAMMDD-JJMMDD-xxxx`) yang disentuh; folder atau berkas lain di `~/agent_kerja` tetap aman.

Keamanan: program buatan model dijalankan **hanya bila kamu menyalakan izinnya di pengaturan**
(mati secara bawaan; menyalakannya berarti kamu mempercayai model dan tugasnya), tanpa shell, di folder `hasil/`, dengan batas waktu
(`ASISTEN_AGENT_UJI_DTK`). Perintah uji dibatasi pada `python3`/`node` + berkas dari lembar tugas.
Nama berkas dari model divalidasi (tanpa `..`, tanpa titik di depan, ekstensi yang dikenal).
Tetap periksa kodenya bila ragu.

Catatan model kecil: konteks terbatas, jadi proyek yang terlalu besar akan terpotong. Pecah
permintaan menjadi bagian kecil (1-3 berkas). Bila berkas sering terpotong, naikkan
`ASISTEN_AGENT_TOKENS` (dan `ASISTEN_CTX` bila RAM cukup). Agent butuh llama-server mode router
(sama seperti halaman chat) dan menolak berjalan selama sesi chat masih memuat model: tekan
**Selesai** di chat dulu.

### Mengubah perilaku Agent

Kode Agent ada di folder `tim/`, satu berkas satu tanggung jawab, jadi perbaikan cukup menyentuh
berkas yang relevan:

| Ingin mengubah | Berkas |
|---|---|
| teks prompt Perencana/Pelaksana/Pemeriksa/Penjelas, susunan isi prompt | `tim/tim_prompt.py` |
| batas token, batas waktu uji, folder kerja, batas berkas, validasi pengaturan dari web | `tim/tim_config.py` |
| alur putaran (Pelaksana menulis -> Pemeriksa menjalankan + menentukan), pemulihan hasil terbaik, pemakaian ulang diagnosa | `tim/tim_alur.py` |
| pilihan jalur (buat / perbaiki / cari bug) dan aturan kata kuncinya | `tim/tim_jalur.py` |
| tiap tahap model (Diagnosa, Perencana, Pelaksana menulis, Pemeriksa menjalankan + menentukan, Penjelas) dan jejak diagnosis | `tim/tim_tahap.py` |
| alat Pemeriksa: cek berkas/sintaks, uji jalan, perapian penilaian | `tim/tim_cek.py` |
| cara membaca keluaran Pelaksana (`=== FILE: ===`), nama berkas aman | `tim/tim_berkas.py` |
| lembar tugas: perintah uji yang diizinkan, harapan keluaran | `tim/tim_spec.py` |
| muat/bongkar model di llama-server | `tim/tim_model.py` |
| aliran jawaban model, pengambilan JSON | `tim/tim_llm.py` |
| bagian fakta pada laporan akhir | `tim/tim_laporan.py` |
| riwayat proses (daftar, baca, hapus) | `tim/tim_riwayat.py` |

Dari luar cukup `import tim` (`tim.jalankan`, `tim.daftar_run`, ...). Konstanta pengaturan
(`tim.KERJA`, `tim.TOKEN_TAHAP`, ...) dibaca langsung dari `tim_config`.

### Mengubah perilaku chat (paket `agen/`)

| Ingin mengubah | Berkas |
|---|---|
| alamat llama-server, `CTX_MAKS`, `MAX_TOKENS`, gerbang tool, batas putaran, lokasi `aksi.log` | `agen/agen_config.py` |
| teks prompt sistem (`SYSTEM_PROMPT`, skill web, berpikir kritis), kata pemicu tool, jatah riwayat | `agen/agen_prompt.py` |
| cara bicara dengan llama-server, membaca stream jawaban | `agen/agen_llama.py` |
| pemangkasan dan peringkasan riwayat percakapan | `agen/agen_memori.py` |
| tahap pemeriksaan jawaban (skill berpikir kritis) | `agen/agen_kritik.py` |
| loop agen: urutan putaran, eksekusi tool, anti-loop, perlindungan setelah tool web | `agen/agen_giliran.py` |

Dari luar cukup `import agen` (`agen.giliran`, `agen.llama`, `agen.CTX_MAKS`, ...). Nilai yang
diubah lewat paket (`agen.GERBANG = False`, `mock.patch.object(agen, "stream_chat", ...)`)
diteruskan ke modul pemiliknya. Antar modul, nilai konfigurasi dibaca lewat `cfg.NAMA` saat
dipakai, bukan disalin saat impor, supaya perubahan itu langsung berlaku.

### Mengubah perilaku server (paket `server/`)

| Ingin mengubah | Berkas |
|---|---|
| lokasi folder, `MODELS_DIR`, batas buffer proses Agent | `server/server_config.py` |
| rute `/api/...`, izin token, file statis web, alur `kirim` dan `agent_jalankan` | `server/server_http.py` |
| cara memuat/membongkar model, idle, tombol Selesai | `server/server_model.py` |
| menyimpan dan membaca riwayat obrolan | `server/server_chat.py` |
| izin lewat web (mode AUTO, konfirmasi) | `server/server_ctx.py` |
| buffer dan long-poll proses Agent di latar belakang | `server/server_agent.py` |
| argumen baris perintah (`--port`, `--idle`, ...), penutupan rapi | `server/server_main.py` |

Dari luar tetap `import asisten` (`asisten.GEN_LOCK`, `asisten.H`, `asisten.daftar_model`, ...). Antar
modul, nilai bersama dibaca lewat modul pemilik saat dipakai (`conf.TOKEN`, `state.S`), dan
penetapan nilai lewat `asisten` atau `mock.patch.object(asisten, ...)` diteruskan ke pemiliknya
(`server/server_shim.py`).

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
| `berita` | berita terbaru (judul, sumber, umur) dari Google News; skill Web | - |
| `cari_web` | cari informasi di internet; skill Web | - |
| `baca_halaman` | baca isi halaman web publik (hanya baca); skill Web | - |
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

Menambah tool: tulis satu fungsi dengan dekorator `@tool(...)` di salah satu `src/tool_*.py`
(paling mudah di `src/tool_lain.py`), dengan `from .registri import tool`. Skema untuk model
dibuat otomatis (`dasar=True` / `web=True` memasukkannya ke skill itu). Kalau membuat modul
baru, tambahkan namanya di baris `from . import ...` pada `src/tolls.py`. Tool baru otomatis
ditaruh di urutan paling belakang.
Banyak tool memakan konteks model (8192 token), jadi skill Dasar/Web lebih hemat daripada
Kompleks. Skill bawaan bisa diubah: `ASISTEN_TOOLS=dasar python3 asisten.py`.

## Pengaturan (variabel lingkungan)

Semua opsional. Contoh pemakaian: `LLAMA_BASE_URL=http://192.168.1.5:8080 python3 asisten.py`.
Agar permanen, tambahkan baris `export NAMA=nilai` di `~/.bashrc`.

| Variabel | Bawaan | Fungsi |
|---|---|---|
| `LLAMA_BASE_URL` | `http://127.0.0.1:8080` | alamat llama-server (boleh berakhiran `/v1`) |
| `ASISTEN_MODELS_DIR` | `~/models` | folder file `.gguf`, dipakai untuk menampilkan ukuran model. Harus sama dengan `--models-dir` llama-server |
| `ASISTEN_CTX` | `8192` | ukuran konteks; samakan dengan `-c` di llama-server. Juga menentukan seberapa banyak riwayat yang dikirim ke model |
| `ASISTEN_MAX_TOKENS` | `700` | batas token satu jawaban. Naikkan bila jawaban atau isi file sering terpotong (makin besar, makin sedikit riwayat yang muat) |
| `ASISTEN_TOOLS` | `kompleks` | skill bawaan bila web belum memilih (`dasar` = 4 tool inti) |
| `ASISTEN_AKAR_TULIS` | home dan `/tmp` | folder yang boleh diubah tool, pisahkan dengan `:` (`/a:/b`) |
| `ASISTEN_LOG_MAKS_KB` | `1024` | batas ukuran `aksi.log` sebelum diputar menjadi `aksi.log.1` .. `.3` (0 = tanpa rotasi) |
| `ASISTEN_GERBANG` | `1` | `0` mematikan gerbang yang membatasi tool pada permintaan yang tampak butuh akses sistem |
| `ASISTEN_MODEL` | `Qwen_Qwen3-1.7B-Q4_K_M` | model bawaan untuk `cli_lama.py` |
| `ASISTEN_AGENT_DIR` | `~/agent_kerja` | folder kerja halaman Agent (satu subfolder per proses) |
| `ASISTEN_AGENT_TOKENS` | `3000` | batas token tahap Pelaksana (menulis kode) |
| `ASISTEN_AGENT_UJI_DTK` | `20` | batas waktu uji jalan program hasil Agent, dalam detik |
| `ASISTEN_UNGGAH_MB` | `10` | ukuran maksimum satu unggahan (zip), dalam MB |

Khusus `start.sh` (dan sebagian `deploy/pasang-layanan.sh`):

| Variabel | Bawaan | Fungsi |
|---|---|---|
| `LLAMA_BIN` | `~/llama.cpp/build/bin/llama-server` | lokasi llama-server (juga dipakai `pasang-layanan.sh`) |
| `LLAMA_PORT` | `8080` | port llama-server yang dinyalakan (juga dipakai `pasang-layanan.sh`) |
| `LLAMA_ARGS` | kosong | opsi tambahan untuk llama-server, mis. `"-t 4"` (hanya `start.sh`) |
| `LLAMA_TUNGGU` | `120` | detik menunggu llama-server siap (hanya `start.sh`) |
| `LLAMA_LOG` | `llama-server.log` di folder proyek | berkas log llama-server (hanya `start.sh`) |

`ASISTEN_MODELS_DIR` dan `ASISTEN_CTX` juga dipakai skrip ini untuk `--models-dir` dan `-c`, jadi
nilainya otomatis sama dengan asisten. Bila `LLAMA_BASE_URL` diisi, `start.sh` memakai llama-server
di alamat itu dan tidak menyalakan yang lokal.

## Keamanan

- Semua `/api` wajib **token** (`.token`, izin 600). Jangan bagikan alamat berisi token.
- Berkas unggahan tidak tepercaya: nama dan jalur divalidasi, hanya teks UTF-8, zip dibatasi (tanpa `..`,
  symlink, terenkripsi, zip bomb), dan obrolan berlampiran memakai aturan yang sama seperti setelah tool Web.
- Server memakai HTTP biasa di jaringan lokal. Jangan buka port 8090 ke internet.
  Untuk akses dari luar rumah, pakai VPN seperti Tailscale.
- Perintah berikut **selalu** minta izin, juga di mode AUTO, baik lewat tool khusus maupun lewat `jalankan_perintah`:
  `sudo`; instal/hapus paket (`apt`, `pip`, `npm`, dll.); `rm`; `find ... -delete`; `kill`/`pkill`/`killall`; `git push`;
  `chmod`/`chown -R`; dan perintah yang mengeksekusi teks lain (`| sh`, `bash -c`, `eval`, `base64 -d`, `$(curl ...)`).
- Selalu minta izin juga (walau AUTO): kode inline lewat interpreter (`python3 -c`, `perl -e`, `node -e`, heredoc, `| python3`);
  membaca file rahasia lewat shell (`cat ~/.ssh/id_*`, `.env`, `.git-credentials`); menulis ke skrip login (`~/.bashrc`, `.profile`);
  `crontab`, `systemctl enable/start/stop`, `.git/hooks`, dan soket balik (`nc -e`, `/dev/tcp`).
- `hapus` dan `matikan_proses` juga selalu minta izin.
- **Lokasi sensitif** juga selalu minta izin untuk tulis/edit/salin/pindah/arsip/unduh, di mode AUTO sekalipun:
  skrip login (`~/.bashrc`, `.profile`, `.zshrc`), `~/.config/systemd`, `~/.config/autostart`, `~/.local/bin`, `.git/hooks`,
  kode asisten sendiri (kecuali `riwayat/`), dan file kredensial. Kartu izin diberi tanda `[LOKASI SENSITIF]`.
  Konsekuensinya, mengedit kode di `~/ai_asisten` lewat asisten selalu bertanya dulu.
- Tool pengubah file hanya boleh bekerja di home dan `/tmp` (tambah lewat `ASISTEN_AKAR_TULIS=/a:/b`), tidak di `~/.ssh`.
- File rahasia tidak bisa dibaca atau dicari lewat tool file: `.token`, kunci pribadi SSH, `.env` (`.env.example` boleh),
  `.git-credentials`, `.netrc`, `~/.aws`, `~/.config/gh`, `~/.gnupg`, `.bash_history`, dan sejenisnya.
- Tool Web (termasuk `ambil_url`) hanya ke alamat publik; alamat lokal/privat dan pengalihan ke sana ditolak.
  Hasil web bisa berisi instruksi jahat (*prompt injection*), jadi **setelah tool Web dipakai dalam sebuah obrolan, mode AUTO
  tidak berlaku lagi di obrolan itu**: setiap aksi pengubah dan perintah shell minta izin (kartu diberi tanda
  `[setelah tool web ...]`). Obrolan baru mulai bersih. File yang diunduh dari web lalu dibaca belum dilindungi seperti ini.
- Perintah berbahaya **selalu diblokir**, termasuk yang dibungkus (`bash -c 'rm -rf /'`) atau diberi tanda kutip/backslash: menghapus `/`, home, atau folder sistem (`rm`, `mv`, `find -delete`), `chmod/chown -R` di sana, `mkfs`, `dd of=/dev/...`, `reboot`/`shutdown`, `kill -9 -1`, *fork bomb*, serta `git push --force`, `git reset --hard`, dan `git clean -f` lewat shell.
- Semua aksi tool dicatat di `aksi.log`. Berkas ini diputar otomatis pada 1 MB (maksimal 3 salinan lama), jadi tidak membesar tanpa batas.
- Daftar blokir hanya pengaman dasar berbasis pola. Perintah yang disamarkan lewat variabel atau *brace expansion* (`{rm,-rf,/}`) masih bisa lolos dari pola-polanya. Baca perintah sebelum menekan Ya.
- Model kecil bisa salah mengerti perintah. Untuk pemula, biarkan mode AUTO **mati**.

## Berkas

| Berkas | Fungsi |
|---|---|
| `asisten.py` | pintu masuk (`python3 asisten.py`); isinya dipecah ke paket `server/` |
| `server/server_config.py` | folder (`web/`, `riwayat/`, `.token`), `MODELS_DIR`, token, batas buffer Agent |
| `server/server_state.py` | keadaan bersama: model aktif, `GEN_LOCK`, izin menunggu, buffer proses Agent |
| `server/server_log.py`, `server_akses.py` | log berwarna di terminal; token akses dan alamat IP |
| `server/server_model.py` | daftar model, muat/bongkar di llama-server, idle, tombol Selesai |
| `server/server_chat.py` | penyimpanan riwayat obrolan |
| `server/server_ctx.py` | konteks satu proses generasi: mode AUTO, batal, izin lewat web |
| `server/server_agent.py`, `server_status.py` | buffer event Agent di latar belakang; isi `/api/status` |
| `server/server_unggah.py` | unggahan berkas: penampung paket, ekstrak zip aman, lampiran chat |
| `web/unggah.js`, `web/unggah.css` | tombol 📎 dan daftar lampiran (dipakai halaman Chat dan Agent) |
| `server/server_http.py` | penangan HTTP: rute `/api`, file statis, proses generasi di thread |
| `server/server_main.py` | argumen baris perintah, siklus hidup server, penutupan rapi |
| `agen/` | paket inti agen (dulu satu berkas `agen.py`); `import agen` tetap dipakai seperti biasa |
| `agen/agen_config.py` | konfigurasi: `LLAMA_URL`, `CTX_MAKS`, `MAX_TOKENS`, `GERBANG`, `LOG_AKSI`, batas peringkasan |
| `agen/agen_prompt.py` | prompt sistem, skill web dan berpikir kritis, gerbang tool, jatah riwayat |
| `agen/agen_llama.py` | klien llama-server: permintaan biasa, stream SSE, pembaca jawaban satu putaran |
| `agen/agen_memori.py` | pemangkasan riwayat agar muat di konteks dan peringkasan pesan lama |
| `agen/agen_kritik.py` | skill berpikir kritis tahap 2 (model memeriksa drafnya sendiri) |
| `agen/agen_giliran.py` | loop agen: `giliran()` dan eksekusi tool calls |
| `src/tolls.py` | pintu masuk: menggabungkan semua modul tool dan menjaga urutan tool |
| `src/registri.py` | dekorator `@tool`, skill, skema untuk model, eksekusi tool |
| `src/util.py` | konstanta dan fungsi bantu bersama (path, izin, menjalankan proses) |
| `src/pengaman.py` | daftar perintah shell yang diblokir / wajib izin |
| `src/tool_file.py` | baca, tulis, ubah, pindah, hapus file, arsip ZIP |
| `src/tool_telusur.py` | tool hanya-baca: daftar, cari, dan info folder/file |
| `src/tool_sistem.py` | perintah shell, info sistem, proses, git |
| `src/tool_web.py` | `ambil_url`, `baca_halaman`, `berita`, `cari_web` |
| `src/aksilog.py` | penulisan `aksi.log` dengan rotasi |
| `src/tool_lain.py` | kalkulator dan waktu (tempat termudah untuk tool baru) |
| `tim/` | paket Agent, dipecah per tanggung jawab (lihat tabel "Mengubah perilaku Agent"); dipakai lewat `import tim` |
| `web/index.html`, `index.css`, `index.js` | tampilan chat |
| `web/agent.html`, `agent.css`, `agent.js` | tampilan Agent (tombol **Agent** di chat) |
| `start.sh` | menyalakan llama-server (bila belum hidup) lalu asisten, dengan satu perintah |
| `deploy/` | `pasang-layanan.sh` dan templat unit systemd (`*.service.in`) |
| `.github/workflows/tests.yml` | CI GitHub: menjalankan pengujian di Python 3.9, 3.11, 3.13 |
| `tests/` | pengujian otomatis (`unittest`) |
| `cli_lama.py` | versi CLI lama (tanpa web), masih bisa dipakai, dan memakai pengaman perintah yang sama. Contoh: `python3 cli_lama.py "cek suhu CPU"` |
| `riwayat/`, `.token`, `aksi.log*`, `llama-server.log` | data (dibuat otomatis, tidak ikut git) |

## Pengujian

```bash
cd ~/ai_asisten
python3 -m unittest discover -s tests -v
```

Mencakup tool, pengaman shell, dan susunan modul `src/` (`tests/test_tolls.py`), server web dan riwayat
(`tests/test_asisten.py`, memakai folder sementara, tidak menyentuh `riwayat/` asli),
agen dan skill (`tests/test_agen.py`, memakai model palsu), susunan paket `agen/` (`tests/test_agen_paket.py`) dan `server/` (`tests/test_server_paket.py`), unggah berkas (`tests/test_unggah.py`, `tests/unggah_smoke.js`), alur adaptif Agent (`tests/test_jalur.py`),
keamanan jalur, rahasia, dan pengaman shell (`tests/test_keamanan.py`),
kunci generasi, batas token, dan perlindungan setelah tool web (`tests/test_batas_dan_taint.py`),
pemeriksaan tampilan web chat dan Agent (`tests/test_web.py`; sintaks JS dicek bila `node` terpasang),
Agent: urutan muat/bongkar model, putaran koreksi, Pemeriksa yang menjalankan dan menentukan, keamanan nama berkas, dan
endpoint `/api/agent`, dan log langsung di halaman Agent (`tests/test_tim.py` + `tests/agent_smoke.js`,
memakai llama-server dan model palsu; tes `agent_smoke.js` butuh `node`).
rotasi `aksi.log` (`tests/test_aksilog.py`), serta `start.sh` dan `deploy/pasang-layanan.sh`
(`tests/test_skrip.py`, memakai llama-server dan systemctl palsu; butuh `bash`).
Tidak butuh model termuat dan tidak butuh llama-server menyala.

Setiap push ke GitHub menjalankan pengujian yang sama lewat GitHub Actions
(`.github/workflows/tests.yml`, Python 3.9, 3.11, dan 3.13).

## Pemecahan masalah

| Gejala | Penyebab umum dan solusi |
|---|---|
| `Tidak bisa terhubung ke llama-server di http://127.0.0.1:8080` lalu program berhenti | llama-server belum menyala atau beda port. Jalankan dulu ([langkah 4](#4-jalankan-llama-server)), cek dengan `curl http://127.0.0.1:8080/v1/models`. Kalau server di perangkat lain, atur `LLAMA_BASE_URL` |
| `Tidak bisa membuka port 8090` | Port dipakai program lain (mungkin `asisten.py` yang sudah jalan). Tutup yang lama, atau pakai `--port 8091` |
| Daftar model kosong di web | Tidak ada `.gguf` di folder model, atau llama-server dijalankan tanpa `--models-dir`. Cek `ls ~/models` dan perintah llama-server |
| Ukuran model tidak tampil | `ASISTEN_MODELS_DIR` tidak sama dengan folder `--models-dir` |
| `Model tidak ditemukan di llama-server` | Nama model tidak ada di `/v1/models`. Muat ulang halaman web, periksa nama file `.gguf` |
| `llama-server gagal memuat model` | RAM tidak cukup, file model rusak/terpotong, atau model tidak didukung versi llama.cpp. Lihat log di terminal llama-server, coba model lebih kecil, unduh ulang dengan `wget -c` |
| `Model belum siap setelah 5 menit` | Model terlalu besar untuk perangkat, atau kartu SD/disk lambat. Coba model lebih kecil |
| Halaman web menolak / "Akses ditolak (token salah)" | Buka lagi alamat lengkap yang berisi `?token=...` dari terminal. Token hilang? Jalankan `python3 asisten.py --token-baru` |
| HP tidak bisa membuka alamatnya | HP dan Pi harus satu Wi-Fi, IP bisa berubah (cek `hostname -I`), dan `asisten.py` jangan dijalankan dengan `--host 127.0.0.1` |
| Model langsung memanggil tool untuk sapaan, atau jawabannya ngawur | Model terlalu kecil/tidak cocok untuk tool calling. Coba skill **Tanpa skill**, atau ganti model. Pastikan llama-server memakai `--jinja` |
| Jawaban berakhir dengan `[Jawaban terpotong ...]`, atau `tulis_file` gagal dengan pesan terpotong | Batas token satu jawaban (`ASISTEN_MAX_TOKENS`, bawaan 700) tercapai. Ketik `lanjut`, naikkan nilainya, atau minta file ditulis bertahap (`tambah=true`) |
| Riwayat terasa dilupakan | Konteks terbatas (`ASISTEN_CTX`), riwayat lama dipangkas saat dikirim ke model. Pastikan nilainya sama dengan `-c` di llama-server |
| `./start.sh`: `Permission denied` | `chmod +x start.sh deploy/pasang-layanan.sh`, atau jalankan dengan `bash start.sh` |
| `./start.sh`: `llama-server tidak ditemukan` | Belum dibangun, atau jalurnya lain. Bangun ([langkah 2](#2-pasang-llamacpp-llama-server)) atau isi `LLAMA_BIN=/jalur/ke/llama-server ./start.sh` |
| `./start.sh`: `llama-server berhenti saat dinyalakan` | Baca 20 baris log yang ditampilkan (lengkapnya di `llama-server.log`). Umumnya ada opsi yang tidak dikenal versi llama.cpp-mu, atau port 8080 dipakai program lain (coba `LLAMA_PORT=8081 ./start.sh`) |
| Layanan systemd tidak menyala setelah Pi reboot | Jalankan `sudo loginctl enable-linger $USER`, lalu reboot. Periksa `systemctl --user status ai-asisten llama-server` |
| `ai-asisten` sempat gagal lalu menyala sendiri saat boot | Normal: ia menunggu llama-server siap dan mencoba lagi tiap 5 detik. Lihat `journalctl --user -u ai-asisten` |
| `aksi.log` terlalu besar | Diputar otomatis pada 1 MB. Ubah batasnya dengan `ASISTEN_LOG_MAKS_KB` (0 = tanpa rotasi) |
| Suhu CPU atau status throttling tidak tampil | Suhu dibaca dari `/sys/class/thermal/thermal_zone0/temp` (tidak ada di semua perangkat). Status throttling butuh `vcgencmd`, yang hanya ada di Raspberry Pi |

## Batasan

Model kecil cukup untuk tugas sederhana (lihat folder, baca file, cek status) tetapi
sering salah di tugas berlangkah banyak. Konteks server 8192 token, jadi riwayat lama
dipangkas saat dikirim ke model (riwayat di disk tetap utuh). Hanya satu proses
generasi berjalan pada satu waktu.
