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
9. [Serah terima chat ke Agent](#serah-terima-chat-ke-agent)
10. [Agent (tim beberapa model)](#agent-tim-beberapa-model)
11. [Tools](#tools)
12. [Pengaturan (variabel lingkungan)](#pengaturan-variabel-lingkungan)
13. [Keamanan](#keamanan)
14. [Berkas](#berkas)
15. [Pengujian](#pengujian)
16. [Pemecahan masalah](#pemecahan-masalah)
17. [Batasan](#batasan)

## Cara kerja

```
 HP / browser  ──►  asisten.py (port 8090)  ──►  llama-server (port 8080)  ──►  model .gguf
 (tampilan chat)    server web + tool            mesin AI (llama.cpp)            file di ~/models
```

Ada **dua program terpisah**, masing-masing dijalankan sendiri (biasanya di dua terminal):

| Program | Dijalankan dengan | Tugas | Port |
|---|---|---|---|
| `llama-server` | `./llama_server.sh` | menjalankan model AI (otak); log lengkapnya tampil di terminalnya | 8080 |
| `asisten.py` | `python3 asisten.py` | **hanya** server web: tampilan, tool, riwayat chat | 8090 |

`asisten.py` **tidak membawa model sendiri dan tidak menyalakan llama-server**. Ia hanya terhubung ke
satu atau beberapa alamat server model. Alamat itu (dan API key bila ada) diisi dari web lewat tombol
**Atur koneksi**, jadi server model bisa berada di Pi yang sama, perangkat lain di jaringan, dan/atau
penyedia online yang kompatibel OpenAI, sekaligus. `asisten.py` tetap menyala walau server model belum hidup;
isi alamatnya, atau nyalakan `./llama_server.sh`, lalu muat ulang daftar model.
`./start.sh` adalah jalan pintas yang menjalankan keduanya sekaligus.

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
folder, lalu model dimuat dan dibongkar sesuai permintaan aplikasi. Cara termudah adalah skrip
`llama_server.sh`, dijalankan di **terminal tersendiri**:

```bash
cd ~/ai_asisten
./llama_server.sh                      # port 8080, hanya dari Pi ini
./llama_server.sh --port 8081 --host 0.0.0.0 --ctx 16384 --api-key RAHASIA   # contoh opsi
```

Terminal itu menampilkan ringkasan (program, folder model dan jumlah `.gguf`, konteks, host:port,
apakah API key dipakai), lalu `OK  ISI ALAMAT INI di web (Pengaturan koneksi): http://IP:PORT`, dan
sesudahnya **seluruh log llama-server** mengalir di sana. Ctrl+C menghentikannya.

| Opsi | Arti |
|---|---|
| `--port N` | port yang didengarkan (bawaan 8080) |
| `--host ALAMAT` | `127.0.0.1` (bawaan, hanya Pi ini) atau `0.0.0.0` (bisa diakses perangkat lain; disarankan bersama `--api-key`, lihat [Cara 4](#cara-4-llama-server-di-pc-terpisah---host-0000)) |
| `--models-dir DIR` | folder `.gguf` (bawaan `~/models`) |
| `--ctx N` | ukuran konteks (bawaan 8192) |
| `--api-key KUNCI` | llama-server hanya melayani permintaan yang membawa kunci ini. Kunci diteruskan lewat variabel `LLAMA_API_KEY`, bukan argumen, jadi tidak tampil di daftar proses |
| `--log BERKAS` | tulis log llama-server ke berkas, bukan ke terminal |
| `--bin JALUR`, `--tunggu DETIK` | lokasi llama-server; batas menunggu siap |
| `-- opsi...` | semua sesudah `--` diteruskan ke llama-server, mis. `./llama_server.sh -- -t 4` |

Opsi ini juga bisa lewat variabel lingkungan (`LLAMA_PORT`, `LLAMA_HOST`, `ASISTEN_MODELS_DIR`,
`ASISTEN_CTX`, `LLAMA_API_KEY`, `LLAMA_BIN`, `LLAMA_ARGS`); opsi baris perintah menang. Skrip menolak
berjalan bila port sudah dipakai, dan memberi tahu bila program llama-server tidak ditemukan.

Bila ingin menjalankan llama-server tanpa skrip, perintah setaranya:

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

Di terminal lain (llama-server tetap hidup di terminal pertamanya):

```bash
cd ~/ai_asisten
python3 asisten.py
```

Alamat llama-server bawaannya `http://127.0.0.1:8080`. Bila servernya di port/perangkat lain,
isi dari web ([Koneksi model](#koneksi-model-lokal-dan-online-sekaligus)); tidak perlu menjalankan ulang asisten.

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
4. Di halaman web: **pilih skill**, **pilih model**, lalu tekan **Mulai sesi**. Tunggu sampai model termuat
   (di Pi bisa puluhan detik), lalu mulai chat.

Lupa IP Pi-nya? Jalankan `hostname -I` di Pi.

## Menjalankan sehari-hari

Ada tiga cara menjalankannya. Pilih salah satu.

### Cara 1: `start.sh` (jalan pintas, satu perintah)

```bash
cd ~/ai_asisten
./start.sh
```

Skrip ini hanyalah jalan pintas: ia menjalankan `llama_server.sh` (log-nya ke `llama-server.log`,
bukan ke terminal) bila llama-server belum hidup, menunggu sampai siap, lalu menjalankan
`asisten.py`. Untuk hanya menyalakan asisten (server model sudah ada di tempat lain, atau memakai
penyedia online), pakai `./start.sh --tanpa-llama`. Tekan Ctrl+C untuk berhenti: asisten menutup diri dulu (model dibongkar), baru
llama-server ikut dihentikan, dan hanya bila skrip ini yang menyalakannya. Opsi `asisten.py`
bisa ditambahkan di belakangnya, misalnya `./start.sh --port 8091 --idle 10`. Log llama-server
ada di `llama-server.log`.

Pengaturan lewat variabel lingkungan, contoh:
`LLAMA_BIN=/opt/llama/llama-server ASISTEN_MODELS_DIR=/mnt/models ./start.sh`
(daftar lengkap di [Pengaturan](#pengaturan-variabel-lingkungan)).
Kalau muncul `Permission denied`, jalankan `chmod +x start.sh llama_server.sh` sekali, atau pakai `bash start.sh`.

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

Layanan `llama-server` bawaan hanya mendengarkan `127.0.0.1`. Bila model dijalankan di PC lain, lihat [Cara 4](#cara-4-llama-server-di-pc-terpisah---host-0000).

Catatan: jalur proyek, llama-server, dan folder model tidak boleh mengandung spasi; pasang ulang
bila jalurnya berubah. Jangan menjalankan `start.sh` bersamaan dengan layanan (port bentrok):
hentikan layanan dulu.

### Cara 3: dua terminal (disarankan bila ingin melihat log llama-server)

Jalankan dua hal ini (di dua terminal, atau pakai `tmux`):

```bash
# terminal 1: log lengkap llama-server tampil di sini
cd ~/ai_asisten && ./llama_server.sh

# terminal 2: server web
cd ~/ai_asisten && python3 asisten.py
```

Supaya tetap hidup walau SSH terputus, pakai `tmux`:

```bash
sudo apt install -y tmux
tmux new -s ai        # lalu jalankan kedua perintah di jendela terpisah (Ctrl+b lalu %)
# lepas dengan Ctrl+b lalu d, kembali dengan: tmux attach -t ai
```

### Cara 4: llama-server di PC terpisah (`--host 0.0.0.0`)

Cocok bila server web berjalan di perangkat kecil (misalnya Pi atau VPS dengan RAM 1 GB) dan model
dijalankan di PC lain yang RAM-nya lebih besar (misalnya 8 GB). Pembagian tugasnya:

| Perangkat | Menjalankan | Kebutuhan |
|---|---|---|
| **Server web** (RAM 1 GB cukup) | `python3 asisten.py` saja, tanpa llama.cpp dan tanpa model | sekitar 30 MB RAM saat diam; Python 3 |
| **PC model** (RAM 8 GB) | `./llama_server.sh --host 0.0.0.0 ...` | llama.cpp, folder `.gguf`, RAM sebesar model terbesar yang dipakai |

Karena model dimuat satu per satu, biarkan **Bongkar model tiap tahap** menyala di halaman Agent
supaya RAM 8 GB di PC model tidak penuh. Server web tidak ikut menanggung beban model.

**A. Di PC model**

1. Pasang llama.cpp dan taruh `.gguf` di satu folder (langkah [2](#2-pasang-llamacpp-llama-server) dan
   [3](#3-unduh-model-gguf)). Skrip `llama_server.sh` ada di folder proyek; salin folder proyek ke PC ini
   (atau cukup berkas `llama_server.sh`).
2. Nyalakan dengan `--host 0.0.0.0` supaya bisa dijangkau perangkat lain. Tanpa opsi ini llama-server
   hanya mendengarkan `127.0.0.1` (PC itu sendiri) dan perangkat lain **pasti ditolak**.
   Pasang juga API key, karena siapa pun di jaringan yang sama bisa memakai server tanpa kunci:

   ```bash
   cd ~/ai_asisten
   ./llama_server.sh --host 0.0.0.0 --api-key GANTI-DENGAN-KUNCI-PANJANG
   ```

   Bentuk lain yang setara:

   ```bash
   # lewat variabel lingkungan
   LLAMA_HOST=0.0.0.0 LLAMA_API_KEY=GANTI-DENGAN-KUNCI-PANJANG ./llama_server.sh

   # tanpa skrip
   LLAMA_API_KEY=GANTI-DENGAN-KUNCI-PANJANG ~/llama.cpp/build/bin/llama-server \
     --models-dir ~/models --host 0.0.0.0 --port 8080 -c 8192 --jinja
   ```

   Skrip menolak jalan bila port sudah dipakai, dan memperingatkan bila `0.0.0.0` dipakai tanpa
   `--api-key`. Setelah siap, ia mencetak
   `OK  ISI ALAMAT INI di web (Pengaturan koneksi): http://192.168.x.x:8080`. **Catat alamat itu.**
   Bila alamatnya tidak tampil atau salah, lihat IP PC dengan `hostname -I` (Linux) atau `ipconfig` (Windows).
3. Buka port di firewall PC model, hanya untuk jaringan rumah/kantor:

   ```bash
   sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp    # sesuaikan subnet-mu
   ```

   Di Windows: Windows Defender Firewall → Inbound Rules → New Rule → Port → TCP 8080 → Allow
   (cukup profil *Private*), atau dari PowerShell administrator:
   `netsh advfirewall firewall add rule name="llama-server" dir=in action=allow protocol=TCP localport=8080`.
   Di Windows, jalankan llama-server langsung: `llama-server.exe --models-dir C:\models --host 0.0.0.0 --port 8080 -c 8192 --jinja`.
4. Biarkan tetap hidup walau terminal ditutup: jalankan di `tmux` (lihat [Cara 3](#cara-3-dua-terminal-disarankan-bila-ingin-melihat-log-llama-server)),
   atau pasang sebagai layanan di PC Linux itu. Unit bawaan `deploy/llama-server.service.in` memakai
   `--host 127.0.0.1`, jadi **jangan** dipakai apa adanya untuk skenario ini. Buat unit sendiri,
   misalnya `~/.config/systemd/user/llama-server.service`:

   ```ini
   [Unit]
   Description=llama-server (PC model)
   After=network-online.target

   [Service]
   Type=simple
   EnvironmentFile=%h/.config/llama-server.env
   ExecStart=/home/NAMAMU/llama.cpp/build/bin/llama-server --models-dir /home/NAMAMU/models --host 0.0.0.0 --port 8080 -c 8192 --jinja
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```

   Isi `~/.config/llama-server.env` dengan satu baris `LLAMA_API_KEY=kuncimu` (batasi aksesnya:
   `chmod 600 ~/.config/llama-server.env`), lalu:
   `systemctl --user daemon-reload && systemctl --user enable --now llama-server && sudo loginctl enable-linger $USER`.

**B. Di server web (RAM 1 GB)**

1. Cek dulu bahwa PC model bisa dijangkau dari server web (ganti IP dan kunci):

   ```bash
   curl -H "Authorization: Bearer KUNCI" http://192.168.1.50:8080/v1/models
   ```

   Hasil yang benar adalah JSON berisi daftar model. Bila gagal, lihat
   [Koneksi ke llama-server di PC lain gagal](#koneksi-ke-llama-server-di-pc-lain-gagal) di bagian
   Pemecahan masalah.
2. Nyalakan **hanya** server web, tanpa llama-server lokal:

   ```bash
   cd ~/ai_asisten
   python3 asisten.py                 # atau: ./start.sh --tanpa-llama
   ```

   Jangan memakai `./deploy/pasang-layanan.sh` di perangkat ini: skrip itu memasang dan menyalakan
   llama-server lokal juga, yang di sini tidak ada atau tidak dibutuhkan.
3. Buka web → **Atur koneksi** → ubah koneksi utama: isi **Alamat** `http://192.168.1.50:8080`, pilih jenis
   **llama-server**, dan isi **API key** sama dengan kunci di PC model → **Uji koneksi** → **Simpan**. Alamat dan kunci tersimpan di
   server web, jadi cukup diisi sekali.
4. Samakan konteksnya: bila PC model dijalankan dengan `--ctx 16384`, jalankan server web dengan
   `ASISTEN_CTX=16384 python3 asisten.py` (bawaan keduanya 8192).

Catatan untuk skenario dua perangkat:

- Ukuran model (MB) di daftar model **tidak tampil**, karena server web tidak bisa melihat folder
  `.gguf` di PC lain. Ini normal dan tidak memengaruhi fungsi apa pun.
- Alamat PC model dapat berubah bila router membagi IP secara dinamis (DHCP). Beri PC itu IP tetap
  (di router: *DHCP reservation*), atau pakai nama host (misalnya `http://pc-model.local:8080`).
- Lalu lintas ke llama-server memakai `http` biasa, jadi hanya aman di jaringan yang kamu percaya.
  Jangan membuka port 8080 ke internet. Bila server web dan PC model berada di jaringan berbeda,
  hubungkan lewat VPN (misalnya Tailscale atau WireGuard) dan pakai alamat VPN-nya.

### Koneksi model (lokal dan online sekaligus)

Boleh ada **beberapa sumber model sekaligus**: satu koneksi **utama** (biasanya llama-server di Pi atau jaringan
sendiri) ditambah sampai 8 koneksi tambahan (OpenAI, OpenRouter, Groq, DeepSeek, dll). Di web, tombol
**Atur koneksi** (di layar Mulai sesi dan di halaman Agent) membuka daftar koneksi:

- Tiap koneksi tampil sebagai kartu: nama, lencana **Lokal** / **Online**, alamat, tanda API key, dan status
  (`✔ 12 model` atau `⚠ alasan gagal`). **Ubah** membuka formulirnya; koneksi tambahan juga punya **Hapus**.
- **+ Tambah koneksi** membuka formulir kosong. Koneksi utama tidak bisa dihapus, hanya diubah atau dikembalikan
  ke bawaan (**Pakai bawaan**; tidak menyentuh koneksi tambahan).

| Kolom formulir | Isi |
|---|---|
| Nama | opsional; bila kosong dibuat dari alamatnya (mis. `openai.com`) |
| Alamat server | alamat llama-server (mis. `http://192.168.1.5:8080`) atau penyedia online (mis. `https://api.openai.com/v1`). Awalan `http://` dilengkapi otomatis, akhiran `/v1` boleh ada atau tidak |
| Jenis server | **llama-server** (lokal/jaringan sendiri) atau **Penyedia online**. Penyedia online tidak dikirimi parameter khusus llama.cpp yang ditolak sebagian penyedia |
| API key | opsional untuk llama-server; wajib untuk penyedia online |

**Uji koneksi** menghubungi server dengan isi formulir (tanpa menerapkannya) dan melaporkan jumlah model
serta apakah server memakai mode router. **Simpan** menerapkan dan menyimpannya di `pengaturan.json`
(izin 600, tidak ikut git), jadi tetap berlaku setelah asisten dimulai ulang; koneksi utama yang disimpan dari web
menang atas `LLAMA_BASE_URL`/`LLAMA_API_KEY`. Mengubah atau menghapus koneksi ditolak selama ada chat
atau proses Agent berjalan; model yang dimuat aplikasi ini di server lama dibongkar dulu.

**Daftar model digabung dan dikelompokkan.** Di tombol **Pilih model** (dan pilihan model di halaman Agent),
model dikelompokkan menurut sumbernya, supaya jelas mana yang lokal dan mana yang online:

```
LOKAL · llama-server
   Qwen3-4B                 Lokal   2.4 GB · sedang
   gemma-3-1b               Lokal   0.8 GB · ringan, cepat
ONLINE · OpenRouter
   gpt-4o                   Online  tanpa muat/bongkar
```

Judul kelompok hanya muncul bila ada lebih dari satu sumber. Tombol pilihan menampilkan nama model dengan
lencana Lokal/Online, dan di halaman Agent model online ditandai ☁. Kolom **Cari model** menyaring semua kelompok.
Sumber yang gagal dihubungi tidak menghilangkan model sumber lain; alasannya tertulis di bawah daftar model.

**Tiap model memakai koneksinya sendiri.** Chat dan Agent mengarahkan setiap permintaan ke server pemilik
modelnya, lengkap dengan API key koneksi itu saja: Perencana bisa memakai model online sementara Pelaksana
memakai model lokal, misalnya. Kunci satu koneksi tidak pernah dikirim ke koneksi lain. Di balik layar, nama
model di koneksi tambahan disimpan sebagai `<id koneksi>::<nama>` (mis. `k1a2b3c::gpt-4o`) agar tidak bentrok
dengan model lokal bernama sama; nama itu tidak tampil di layar dan server memakai nama aslinya.

**Apakah semua model akan tampil?** Ya: daftar model tiap koneksi adalah isi `/v1/models` server itu, apa adanya.

| Server | Yang tampil dan cara kerjanya |
|---|---|
| llama-server mode router (`--models-dir`) | semua model di folder itu. Dimuat saat **Mulai** dan dibongkar saat selesai (seperti biasa). Ukuran (GB) hanya tampil untuk koneksi utama bila folder modelnya terbaca dari mesin yang menjalankan asisten |
| llama-server satu model (`-m`) | model itu saja, dipakai langsung (tidak ada muat/bongkar) |
| Penyedia online | semua yang dilaporkan penyedia, **termasuk model non-chat** (embedding, gambar, dll). Daftar yang panjang mendapat kolom **Cari model**. Model dipakai langsung, tanpa muat/bongkar. Penyedia yang tidak punya `/v1/models` menghasilkan daftar kosong |

Langkah lengkap mendaftarkan model online, beserta alamat tiap penyedia (termasuk Claude), ada di
[Mendaftarkan model online](#mendaftarkan-model-online-langkah-demi-langkah).

Catatan untuk penyedia online: pemakaian token dikenai biaya di akun penyedia; kualitas pemanggilan tool
tergantung modelnya; `ASISTEN_CTX` (bawaan 8192) menentukan seberapa banyak riwayat dikirim, naikkan
bila model yang dipakai berkonteks panjang. Penyedia yang menolak `max_tokens` (sebagian model baru
mewajibkan `max_completion_tokens`) belum didukung. Alamat dengan awalan lain seperti `/v1beta/openai` dikenali.

### Mendaftarkan model online (langkah demi langkah)

Model online (Claude, GPT, Gemini, dll) dipakai lewat **penyedia** yang punya API. Untuk mendaftarkannya asisten butuh
**dua hal sekaligus**: **alamat server** penyedia dan **API key** dari akun penyedia itu. Key saja tidak cukup,
karena tanpa alamat asisten tidak tahu ke mana key harus dikirim. Alamat dan key harus dari penyedia yang sama:
key OpenRouter ditolak bila dikirim ke alamat OpenAI.

**A. Ambil API key dan siapkan saldo**

1. Daftar di situs penyedia dan buat API key di halaman pengelolaan key (lihat kolom "Ambil key" di tabel bawah).
2. Salin key saat dibuat. Kebanyakan penyedia hanya menampilkannya sekali.
3. Pastikan akunmu punya saldo atau kuota. Key tanpa saldo tetap bisa terhubung (daftar model tampil), tetapi
   chat ditolak dengan galat pembayaran atau kuota. Langganan chat (mis. Claude Pro, ChatGPT Plus) **bukan** saldo
   API; API ditagih terpisah.

**B. Daftarkan di asisten**

1. Buka web asisten, lalu ketuk **Atur koneksi** (di layar Mulai sesi atau di halaman Agent).
2. Ketuk **+ Tambah koneksi**.
3. Isi formulir:

   | Kolom | Isi |
   |---|---|
   | Nama | bebas, mis. `Claude` atau `OpenRouter`. Nama ini tampil di judul kelompok daftar model |
   | Alamat server | salin dari tabel di bawah, **persis** seperti tertulis. Jangan tambahkan `/chat/completions` atau `/models` |
   | Jenis server | **Penyedia online** |
   | API key | tempel key dari penyedia yang sama |

4. Ketuk **Uji koneksi**. Hasil `✔ Terhubung · N model` berarti alamat dan key benar. Kalau gagal, lihat
   [bila uji koneksi gagal](#bila-uji-koneksi-gagal).
5. Ketuk **Simpan**. Koneksi tampil sebagai kartu bertanda **Online**, dan modelnya muncul di tombol **Pilih model**
   dalam kelompok `ONLINE · nama`. Memilih model online dan menekan **Mulai sesi** langsung memakainya (tanpa muat/bongkar).
6. Koneksi tersimpan di `pengaturan.json`, jadi tidak perlu diisi lagi setelah asisten dimulai ulang. Boleh mendaftarkan
   beberapa penyedia sekaligus (sampai 8) di samping llama-server lokal.

**Alamat server penyedia populer**

| Penyedia | Alamat server | Ambil key |
|---|---|---|
| Anthropic (Claude) | `https://api.anthropic.com/v1` | platform.claude.com (Console, menu API keys) |
| OpenAI | `https://api.openai.com/v1` | platform.openai.com/api-keys |
| OpenRouter (banyak model dari berbagai penyedia, termasuk Claude) | `https://openrouter.ai/api/v1` | openrouter.ai/keys |
| Groq | `https://api.groq.com/openai/v1` | console.groq.com/keys |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | aistudio.google.com/apikey |
| DeepSeek | `https://api.deepseek.com` | platform.deepseek.com |
| Mistral | `https://api.mistral.ai/v1` | console.mistral.ai |
| Together AI | `https://api.together.xyz/v1` | api.together.ai |
| xAI (Grok) | `https://api.x.ai/v1` | console.x.ai |
| Cerebras | `https://api.cerebras.ai/v1` | cloud.cerebras.ai |
| Fireworks AI | `https://api.fireworks.ai/inference/v1` | fireworks.ai |

Alamat di atas adalah yang diketahui saat README ini ditulis; penyedia kadang mengubahnya. Bila uji koneksi gagal
dengan 404, cari "OpenAI compatible" atau "Base URL" di dokumentasi penyedia dan pakai alamat yang tertulis di sana.
Penyedia yang tidak kompatibel OpenAI (tidak punya `/v1/chat/completions`) tidak bisa dipakai langsung.
Awalan `http://` atau `https://` boleh dilewati (dilengkapi otomatis, tetapi sebaiknya tulis `https://`), dan garis miring di
ujung alamat diabaikan.

**Contoh: Claude langsung dari Anthropic**

1. Buat key di Claude Console, dan isi saldo di menu Billing. Langganan Claude Pro **tidak** termasuk akses API;
   hanya paket Max, Ultra, dan Team yang mendapat kredit API bulanan, dan itu pun harus diklaim di pengaturan billing.
2. Atur koneksi → **+ Tambah koneksi** → Nama `Claude`, Alamat `https://api.anthropic.com/v1`, Jenis **Penyedia online**,
   tempel key → **Uji koneksi** → **Simpan**.
3. Pilih model `claude-...` dari kelompok `ONLINE · Claude` (model kecil seperti Haiku jauh lebih murah untuk mencoba).

Untuk alamat Anthropic asisten menyesuaikan permintaannya: tidak mengirim `temperature`, `top_p`, dan JSON mode (ditolak
model Claude terbaru lewat jalur kompatibel OpenAI), dan daftar modelnya diambil lewat jalur asli Anthropic
(header `x-api-key` dan `anthropic-version`, sampai 1000 model). Header `x-api-key` hanya dikirim ke `api.anthropic.com`,
tidak ke koneksi lain. Anthropic menyebut jalur kompatibel OpenAI ini untuk uji coba, bukan pemakaian jangka panjang:
pikiran model (thinking) tidak ikut, dan `tool_choice` `required` tidak didukung. API key yang tidak terikat workspace
perlu header `anthropic-workspace-id` yang belum didukung di sini.

#### Bila uji koneksi gagal

| Pesan | Artinya dan cara memperbaiki |
|---|---|
| `Ditolak server (401)` | API key salah, terpotong saat disalin, atau bukan milik penyedia ini. Buat key baru, tempel ulang tanpa spasi |
| `Ditolak server (403)` | Key tidak punya izin, wilayah/akun dibatasi, atau penyedia memblokir klien. Cek status akun di situs penyedia |
| `Server menjawab galat 404` | Alamat salah. Bandingkan dengan tabel di atas; jangan tambahkan `/chat/completions` |
| `Server mengalihkan ke alamat lain` | Pakai alamat tujuan pengalihan (biasanya `https://` bukan `http://`) |
| `Tidak bisa terhubung` | Tidak ada internet dari Pi/HP, alamat salah ketik, atau server penyedia sedang bermasalah. Coba `curl -i -H "Authorization: Bearer KEY" ALAMAT/models` dari Pi (ganti `KEY` dan `ALAMAT`) |
| `Jawaban server bukan JSON` | Alamat menunjuk ke halaman web, bukan ke API. Pakai alamat API dari tabel |
| Terhubung, tetapi chat gagal dengan galat 402/429 atau pesan saldo/kuota | Saldo atau kuota habis, atau terlalu sering mengirim. Isi saldo, atau tunggu sebentar |
| Terhubung, tetapi model yang dipilih ditolak (400/404) | Model itu bukan model chat (embedding, gambar) atau tidak tersedia di akunmu. Pilih model lain di daftar |

### Opsi `asisten.py`

| Opsi | Fungsi |
|---|---|
| `--port 8090` | port web (bawaan 8090) |
| `--host 0.0.0.0` | alamat bind (bawaan 0.0.0.0 supaya bisa dibuka dari HP; bawaannya juga bisa diubah lewat `ASISTEN_HOST`) |
| `--lokal` | hanya bisa dibuka dari perangkat ini (sama dengan `--host 127.0.0.1`), mis. bila diakses lewat terowongan atau proksi di Pi yang sama |
| `--idle 20` | menit tanpa aktivitas sebelum model dibongkar (0 = tidak pernah) |
| `--auto` | mode AUTO, tanpa konfirmasi (hati-hati, lihat [Keamanan](#keamanan)) |
| `--token-baru` | buat token baru (token lama tidak berlaku) |
| `--tanpa-warna` | log terminal tanpa warna |

## Alur sesi

1. Buka halaman web, lalu tiga langkah: **pilih skill** (boleh lebih dari satu), **pilih model**
   (daftarnya tersembunyi di balik tombol **Pilih model**; ketuk untuk membuka, lalu ketuk satu model
   untuk menandainya dan daftar menutup lagi), dan tekan **Mulai sesi**. Model baru dimuat setelah Mulai ditekan, jadi
   salah ketuk tidak langsung memuat model besar. Pilihan model diingat; bila hanya ada satu
   model, langsung ditandai.
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

### Prompt pilihan (untuk semua skill)

Di layar **Mulai sesi** ada panel **List prompt** untuk menentukan prompt apa yang dipakai model. Panel
tersedia untuk **semua skill**, tetapi cara kerjanya menurut skill:

| Skill yang aktif | Prompt yang dicentang | Tidak mencentang apa pun |
|---|---|---|
| tanpa akses sistem: **Tanpa**, **Web**, **Berpikir kritis** (dan gabungannya) | **menggantikan** prompt bawaan | model berjalan **murni**, tanpa prompt sistem |
| dengan akses sistem: **Dasar**, **Kompleks** (juga bila digabung dengan Tanpa) | **ditambahkan di bawah** prompt sistem skill | skill memakai prompt sistemnya sendiri |

Pada skill Dasar/Kompleks prompt sistem memuat aturan tool dan keamanan, jadi prompt pilihanmu **tidak
pernah menggantikannya**, hanya melengkapi (diberi judul "Instruksi tambahan dari pengguna"). Barisnya
"Bawaan" di mode ini tampil sebagai "selalu aktif" dan tidak bisa dilepas.

Kapan panel terbuka: pada alur **Tanpa skill** (Tanpa tanpa Dasar/Kompleks) panel otomatis terbuka sebagai
langkah sendiri: pilih skill, atur prompt lalu tekan **Selesai**, pilih model, tekan **Mulai sesi**. Pada
skill lain panel berupa ringkasan satu baris ("Prompt: ..." atau "Prompt tambahan: ...") dengan tombol
**Ubah**, supaya tidak menghalangi. Skill bisa digabung: bila **Kompleks** (bawaan) masih menyala saat
kamu menekan **Tanpa**, mode-nya "tambah", bukan "ganti"; matikan Kompleks bila ingin mengganti prompt bawaan.

- **+ prompt** membuka kolom nama dan isi; tombol **Simpan** ada di pojok bawah kolom. Prompt baru
  langsung tercentang.
- Daftar berbentuk `□ nama prompt (✎) (−)`: centang untuk memakai, `(✎)` untuk **mengubah** nama dan isinya,
  `(−)` untuk menghapus (ada konfirmasi). Mengubah tidak melepas centang dan berlaku mulai pesan berikutnya,
  termasuk di sesi yang sedang berjalan. Tombol **Batal** menutup form tanpa menyimpan.
  Boleh mencentang **beberapa** prompt; isinya digabung berurutan sesuai daftar.
- **Bawaan** adalah prompt asisten yang dipakai selama ini; tercentang secara bawaan, tidak bisa dihapus dan
  tidak bisa diubah. Tombol `(✎)`-nya membuat **salinan** (nama baru, isi terisi dari bawaan) yang bisa kamu ubah lalu simpan.
- **Tidak mencentang satu pun** = model berjalan **tanpa prompt sistem sama sekali** (murni), tanpa
  ringkasan otomatis yang disisipkan. Cocok untuk melihat perilaku asli model.
- Isi prompt boleh memuat `{waktu}`, yang diganti tanggal dan jam saat dipakai. Maks 40 karakter untuk
  nama, 4000 untuk isi, 50 prompt.
- Pilihan centang dan status Selesai diingat per browser; ketuk **Ubah** untuk membuka panelnya lagi.
- Nama prompt yang dipakai tampil di header (`model · skill · prompt: ...`, atau `+prompt: ...` untuk prompt
  tambahan; prompt bawaan polos pada skill Web/Kritis tidak ditulis).
- **Catatan** (opsional, maks 200 karakter): tulis prompt ini cocok untuk apa atau diuji di model apa. Tampil di
  bawah nama prompt dan ikut terbawa saat dibagikan.

#### Penyimpanan dan berbagi prompt

**Satu prompt = satu berkas JSON** di folder `prompt/` (di folder proyek; pindahkan dengan
`ASISTEN_PROMPT_DIR`), sama di semua perangkat yang memakai server itu:

```json
{
 "format": "ai-asisten-prompt",
 "versi": 1,
 "nama": "Penerjemah",
 "isi": "Kamu penerjemah. Terjemahkan pesan pengguna ke bahasa Inggris. {waktu}",
 "catatan": "cocok untuk model kecil"
}
```

- Nama berkas (tanpa `.json`) menjadi id prompt dan tidak berubah walau namanya diganti. Huruf kecil,
  angka, `-` dan `_`, maks 40 karakter.
- **Bagikan prompt yang berhasil:** ketuk **(⬇)** di barisnya untuk mengunduh berkas `.json`, lalu kirim ke
  siapa pun (WhatsApp, e-mail, dsb.). Penerima menekan **⬆ Impor** dan memilih berkasnya (boleh beberapa
  sekaligus; boleh juga berisi daftar `{"prompt": [...]}`). Isi yang sama persis dengan yang sudah ada
  dilewati; nama yang sudah dipakai diberi akhiran `(2)`. Hasil impor tidak otomatis dicentang.
- Tanpa web pun bisa: **salin berkas `.json` ke folder `prompt/`**, dan prompt langsung muncul di
  daftar (tanpa restart). Kunci `format`, `versi`, dan `catatan` boleh dihilangkan; `nama` dan `isi` wajib.
- Berkas yang tidak valid (bukan JSON, tanpa nama/isi, terlalu besar, nama berkas salah, symlink) dilewati
  dan dilaporkan di bawah daftar; tidak ada yang rusak atau hilang karenanya.
- Batas: 40 karakter nama, 4000 isi, 200 catatan, 50 prompt, berkas maks 64 KB, impor maks 256 KB.
- Versi awal fitur ini menyimpan semuanya di satu `prompt.json`. Berkas itu otomatis dipecah ke folder
  `prompt/` saat pertama kali dibaca dan disimpan sebagai `prompt.json.migrasi` (cadangan). Id lama
  berubah jadi nama berkas, jadi centang prompt buatan sendiri perlu dipasang lagi satu kali.
- Prompt hanya berlaku untuk skill tanpa akses sistem (Tanpa, Web, Berpikir kritis). Skill **Dasar** dan
  **Kompleks** memakai prompt bertool sendiri, jadi panel tidak tampil dan pilihan diabaikan.

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

## Serah terima chat ke Agent

Chat dan Agent punya tugas berbeda. **Chat** adalah tempat berdiskusi dan mencoba model: bertanya,
menggali ide, membaca berkas. **Agent** adalah dapur produksi: tim model dengan peran masing-masing
yang mengerjakan sesuatu sampai jadi. Serah terima menyambungkan keduanya, tanpa mengubah
pembagian itu (Agent tidak dipakai untuk ngobrol):

1. **Diskusi di chat** sampai idenya matang (boleh melampirkan berkas dengan 📎).
2. Ketuk **🏭** di header. Model chat menyusun **brief** dari diskusi: tujuan, yang diminta, batasan,
   berkas yang ada, kriteria selesai. Brief tampil sebagai kartu yang bisa kamu **ubah**; pilih jalur
   (Otomatis / Buat / Perbaiki / Cari bug) dan lihat model Agent yang akan dipakai.
3. **Setujui & kirim ke Agent.** Tidak ada yang dikirim sebelum kamu menyetujui. Server melepas model
   chat dari memori, lalu Agent mengerjakan brief itu di latar belakang (lihat
   [alur adaptif](#alur-menyesuaikan-jenis-tugas)), dengan berkas lampiran obrolan sebagai bahan kerja.
   Di chat tampil kartu progres (jalur, tahap yang sedang berjalan, putaran) dengan tombol Stop.
4. **Hasil kembali ke obrolan.** Begitu Agent selesai, server menulis hasilnya ke obrolan yang sama:
   laporan Penjelas dan **kartu hasil** berisi berkas yang bisa diunduh satu per satu atau sebagai zip,
   plus tautan "Lihat proses" ke halaman Agent. Karena ditulis oleh server, hasilnya tetap masuk
   walau halaman ditutup; buka lagi kapan saja.
5. Model chat **dimuat ulang** otomatis (bisa dimatikan di kartu brief) supaya diskusi berlanjut:
   minta perubahan, lalu ketuk 🏭 lagi. Brief berikutnya menawarkan **melanjutkan dari hasil Agent
   sebelumnya**, sehingga perbaikan lama tidak hilang dan berkas lampiran asli tidak menimpanya.

Hal yang perlu diketahui:
- Model Agent dibaca dari pengaturan di halaman Agent (satu kali diatur di sana). Bila belum diatur,
  tombol kirim dinonaktifkan dan kartu menunjukkan alasannya.
- Selama Agent bekerja, kotak ketik chat dinonaktifkan dan model tidak bisa dimuat dari halaman lain.
- Bila Agent butuh informasi tambahan, hasilnya berupa pertanyaan di obrolan; jawab di chat lalu serahkan lagi.
- Bila Agent tidak bisa mulai (mis. masih ada proses lain), pesan serah terima ditarik dan model chat
  dimuat ulang. Brief otomatis gagal? Kartu memakai pesanmu sebagai brief dan kamu tinggal merapikannya.
- Berkas yang dilampirkan di chat disimpan di `riwayat/<id>.lampiran/` (maks 100 berkas) dan ikut
  terhapus saat obrolan dihapus.

## Agent (tim beberapa model)

Tombol **Agent** di pojok atas halaman chat membuka `agent.html`. Di sana beberapa model
lokal bekerja bergiliran untuk **membuat program**; tiap model dimuat saat gilirannya dan
dibongkar saat selesai (bila "Bongkar model tiap tahap" aktif).

| Peran | Tugas |
|---|---|
| **Perencana** (Model 1) | menerima perintah, menyusun lembar tugas `tugas.json` + `tugas.md`, lalu menjelaskan hasil akhir kepada kamu |
| **Pelaksana** (Model 2) | membaca lembar tugas dan **hanya menulis** program ke folder `hasil/` (tidak menjalankan apa pun) |
| **Pemeriksa** | menerima hasil Pelaksana langsung, **menjalankan** programnya, lalu **menentukan benar/salah**: dinyatakan jadi (selesai) atau memberi koreksi yang dikirim ke Pelaksana |

### Prompt tiap peran (tombol "+ prompt")

Di layar pengaturan Agent, tiap peran (**Perencana, Pelaksana, Pemeriksa, Penjelas**) punya baris
`Prompt: bawaan` dengan tombol **+ prompt**. Panelnya sama seperti [prompt di chat](#prompt-pilihan-untuk-semua-skill):
daftar dengan kotak centang, **+ prompt** (nama, isi, catatan), **(✎)** ubah, **(⬇)** unduh `.json` untuk
dibagikan, **⬆ Impor**, **(−)** hapus, dan **Selesai**. Penjelas memakai model Perencana, dan di mode 2 model
Pemeriksa = Perencana, jadi keduanya tetap punya panel sendiri walau tidak punya pilihan model sendiri.

Dua cara pakai, dipilih **per peran**:

| Cara | Akibatnya |
|---|---|
| **Tambah ke bawaan** (awal) | prompt bawaan peran tetap dipakai utuh; prompt yang dicentang ditambahkan di bawahnya |
| **Ganti bawaan** | prompt yang dicentang menggantikan *perilaku* bawaan peran (siapa dia dan cara kerjanya) |

**Format keluaran selalu ikut.** Program membaca keluaran model dengan format tetap (JSON Perencana,
Pemeriksa, dan Diagnosa; blok `=== FILE: nama ===` Pelaksana), jadi pada cara *Ganti* bagian format itu tetap
ditambahkan otomatis di bawah prompt kamu. Tanpa itu, satu prompt yang terlalu bebas bisa membuat seluruh
proses gagal karena keluarannya tidak terbaca. Tombol **(✎)** pada baris Bawaan membuat salinan yang berisi
perilaku bawaan peran itu (tanpa bagian format), sehingga bisa diubah sebagai titik awal prompt *Ganti*.
Tidak ada yang dicentang = perilaku Agent persis seperti sebelum fitur ini ada.

Penyimpanan: satu prompt satu berkas (format `ai-asisten-prompt`, sama dengan prompt chat), tetapi dipisah per
peran supaya daftar tiap peran hanya berisi prompt yang memang untuknya:

```
prompt/agent/perencana/*.json     prompt/agent/pelaksana/*.json
prompt/agent/pemeriksa/*.json     prompt/agent/penjelas/*.json
```

(folder induknya mengikuti `ASISTEN_PROMPT_DIR`; folder `prompt/` untuk chat tidak terpengaruh). Berkas dari
teman cukup disalin ke folder peran yang cocok, atau diimpor lewat tombol **⬆ Impor** di panel peran itu. Berkas
yang sudah ada di folder chat (mis. `prompt/system-pemeriksa.json`) bisa diimpor ke peran mana pun. Perhatikan
bahwa prompt yang sudah memuat teks format keluaran sebaiknya dipakai dengan cara *Tambah*.

Aturan lain:
- Gabungan isi prompt yang dicentang untuk satu peran maksimal **6000 karakter** (di atas 3000 sudah
  memakan konteks model kecil); lebih dari itu ditolak dengan pesan yang jelas sebelum proses dimulai.
- `{waktu}` di isi prompt diganti tanggal dan jam saat dipakai.
- Pilihan (id prompt + cara pakai) tersimpan di peramban bersama pengaturan model, dan dipakai juga oleh
  **serah terima dari chat**. Yang dikirim ke server hanya id: isi prompt selalu dibaca server dari berkasnya.
- Prompt yang dipakai dicatat di log proses, di kartu "Tim siap", dan di `run.json` (`prompt`: peran, cara, nama;
  isinya tidak ikut dicatat).
- Rute: `GET /api/agent/prompt?peran=...`, `GET /api/agent/prompt/ekspor?peran=...&id=...`,
  `POST /api/agent/prompt` (tambah), `/ubah`, `/impor`, `/hapus` (semuanya dengan `peran` di badan permintaan).

### Pemeriksa kedua dan pembuktian temuan

Satu Pemeriksa bermodel kecil bisa salah ke dua arah: **menyetujui** kode yang sebenarnya bermasalah, atau
**menolak** dengan "masalah" karangan sehingga Pelaksana menulis ulang kode yang sudah benar. Ada empat
pengaman, semuanya bekerja di tahap **Periksa** (dan pembuktian juga di tahap **Diagnosa**):

1. **Pembuktian temuan (otomatis, tanpa model tambahan).** Kutipan `dilihat` dan nama berkas pada setiap
   penolakan dicocokkan dengan isi kode dan keluaran program (huruf besar/kecil, spasi, dan nomor baris
   diabaikan). Kutipan yang tidak ditemukan, atau semua masalah yang menyebut berkas yang tidak ada,
   ditanyakan ulang **sekali**. Bila tetap tidak terbukti, penolakan tetap dikirim (Pemeriksa tetap penentu),
   tetapi koreksinya diberi **CATATAN SISTEM** supaya Pelaksana memeriksa sendiri dan tidak mengubah kode yang
   sudah benar, dan laporan akhir memberi peringatan.
2. **Pemeriksa kedua (opsional).** Pilih model di bawah Pemeriksa (kosong = perilaku lama persis). Jawaban
   untuk "apakah dua model saling berdiskusi itu relevan": relevan, **asal dibatasi dan berpijak pada bukti**,
   karena dua model kecil yang berdiskusi bebas gampang saling mengiyakan. Jadi:
   - Pemeriksa kedua menilai hasil yang sama **secara mandiri**, tanpa melihat penilaian pertama.
   - Sepakat menerima → jadi. Sepakat menolak → masalah digabung tanpa pengulangan, dikirim ke Pelaksana.
   - Berbeda pendapat → **satu ronde sanggahan**: yang menerima diminta memeriksa temuan yang menolak
     langsung pada kode (disertai status pembuktian kutipannya) dan dilarang ikut setuju hanya karena
     diminta. Bila ia berbalik, ditolak. Bila ia bertahan: program **gagal** dijalankan/diperiksa → ditolak
     (fakta mengalahkan opini); selain itu → diterima dengan tanda **keputusan lemah**, dan temuan yang
     disanggah dicantumkan di laporan agar kamu menilainya sendiri.
   - Biayanya: 1 panggilan model tambahan bila sepakat, 2 bila berbeda pendapat; model bergantian dimuat
     (nyalakan "Bongkar model tiap tahap" hanya bila RAM terbatas). Model kedua boleh model Pelaksana, tetapi
     model ketiga yang berbeda lebih independen.
3. **Deteksi macet.** Pelaksana menulis kode yang sama persis dengan putaran lalu (Pemeriksa tidak dipanggil
   lagi karena penilaiannya pasti sama), atau Pemeriksa mengulang masalah yang sama. Kali pertama koreksi
   diberi peringatan "ganti pendekatan"; kali kedua berturut-turut proses **berhenti lebih awal** dan
   alasannya ditulis di laporan. Hasil putaran terbaik tetap dipulihkan.
4. **Tanda keputusan lemah.** Laporan akhir memberi peringatan bila "jadi" hanya berdasarkan keputusan
   cadangan (jawaban Pemeriksa tidak terbaca, atau menolak tanpa masalah konkret), bila Pemeriksa berbeda
   pendapat, atau bila program **belum pernah dijalankan** (uji jalan dimatikan atau tidak ada perintah uji).

Jejak tiap penilaian ada di `jejak/` (`periksa-N`, `periksa2-N`, `sanggah-N`, serta `-kutipan` untuk tanya
ulang kutipan). Aturan keputusan dua Pemeriksa ada di `tim_tahap._putuskan_dua` (fungsi murni, mudah diuji).

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
- **Pemeriksa kedua (opsional)**: lihat [Pemeriksa kedua dan pembuktian temuan](#pemeriksa-kedua-dan-pembuktian-temuan).
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
Program uji juga **dikurung** (`tim/tim_kotak.py`): environment bersih (kunci API dan variabel server tidak terbawa;
`HOME` mengarah ke folder sementara yang dihapus), batas memori (`ASISTEN_UJI_RAM_MB`), waktu CPU, ukuran berkas yang
ditulis, jumlah berkas terbuka dan proses/thread baru (maksimal 128 di atas yang sudah dipakai penggunamu), **jaringan diputus** bila sistem mendukung `unshare -rn`, dan keluaran
hanya dibaca bagian akhirnya (RAM server aman walau program mencetak tanpa henti). Ini pengurungan dasar, bukan sandbox
penuh: program masih bisa membaca berkas milikmu lewat jalur absolut (mis. `~/.token`), jadi tetap nyalakan izin uji jalan
hanya untuk tugas yang kamu percaya. Catatan isolasi ikut dikirim ke Pemeriksa, supaya kegagalan akibat jaringan terputus
tidak dianggap bug program.
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
| teks prompt Perencana/Pelaksana/Pemeriksa/Penjelas, susunan isi prompt, pembagian perilaku/format keluaran, perakitan prompt pilihan pengguna (`rakit_sistem`, `sistem_peran`) | `tim/tim_prompt.py` |
| batas token, batas waktu uji, folder kerja, batas berkas, validasi pengaturan dari web | `tim/tim_config.py` |
| alur putaran (Pelaksana menulis -> Pemeriksa menjalankan + menentukan), deteksi macet, pemulihan hasil terbaik, pemakaian ulang diagnosa | `tim/tim_alur.py` |
| pilihan jalur (buat / perbaiki / cari bug) dan aturan kata kuncinya | `tim/tim_jalur.py` |
| tiap tahap model (Diagnosa, Perencana, Pelaksana menulis, Pemeriksa menjalankan + menentukan, Pemeriksa kedua + sanggahan, Penjelas) dan jejak diagnosis | `tim/tim_tahap.py` |
| alat Pemeriksa: cek berkas/sintaks, uji jalan, perapian penilaian, pembuktian lokasi/kutipan terhadap kode, kemiripan masalah | `tim/tim_cek.py` |
| cara membaca keluaran Pelaksana (`=== FILE: ===`), nama berkas aman | `tim/tim_berkas.py` |
| lembar tugas: perintah uji yang diizinkan, harapan keluaran | `tim/tim_spec.py` |
| muat/bongkar model di llama-server | `tim/tim_model.py` |
| aliran jawaban model, pengambilan JSON | `tim/tim_llm.py` |
| bagian fakta pada laporan akhir | `tim/tim_laporan.py` |
| kotak uji jalan: environment bersih, batas RAM/CPU/proses/berkas, jaringan diputus, keluaran dibatasi | `tim/tim_kotak.py` |
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
| koneksi model (utama + tambahan): alamat, API key, jenis, uji, hapus, `pengaturan.json` | `server/server_koneksi.py` |
| menyimpan dan membaca riwayat obrolan | `server/server_chat.py` |
| izin lewat web (mode AUTO, konfirmasi) | `server/server_ctx.py` |
| buffer dan long-poll proses Agent di latar belakang; memulai proses (`mulai_proses`) | `server/server_agent.py` |
| brief dari diskusi, penyerahan ke Agent, hasil kembali ke obrolan, unduhan | `server/server_handoff.py`, rute `/api/handoff/*` dan `/api/agent/run/<id>/unduh` di `server/server_http.py` |
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
| `LLAMA_BASE_URL` | `http://127.0.0.1:8080` | alamat awal server model (boleh berakhiran `/v1`). Pengaturan dari web (`pengaturan.json`) menang atas ini |
| `LLAMA_API_KEY` | kosong | API key awal untuk server model. Dipakai juga oleh `llama_server.sh` sebagai kunci yang diwajibkan |
| `ASISTEN_PENGATURAN` | `pengaturan.json` di folder proyek | lokasi berkas pengaturan koneksi dari web |
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
| `ASISTEN_UJI_RAM_MB` | `512` | batas memori program uji jalan, dalam MB (0 = tanpa batas; tidak berlaku untuk `node`) |
| `ASISTEN_UJI_JARINGAN` | `putus` | `boleh` bila program uji memang perlu internet; bawaan: jaringan diputus (butuh `unshare -rn`) |
| `ASISTEN_UJI_KELUARAN_KB` | `200` | keluaran program uji yang dibaca kembali (bagian akhirnya), dalam KB |
| `ASISTEN_AGENT_EVENT` | `20000` | jumlah event Agent yang disimpan di RAM server; kecilkan (mis. `3000`) di perangkat RAM 1 GB |
| `ASISTEN_MAKS_KONEKSI` | `32` | koneksi HTTP serentak ke server web; di atas itu dijawab 503 |
| `ASISTEN_HOST` | `0.0.0.0` | alamat bind server web bila `--host` tidak diberikan (`127.0.0.1` = hanya perangkat ini) |
| `ASISTEN_IZIN_IP` | kosong | alamat/CIDR di luar jaringan lokal yang boleh terhubung, dipisah koma, mis. `203.0.113.7,198.51.100.0/24` |
| `ASISTEN_IZIN_PUBLIK` | `0` | `1` menerima koneksi dari alamat internet mana pun (tidak disarankan; HTTP polos) |
| `ASISTEN_GAGAL_MAKS` | `10` | token salah dalam semenit dari satu alamat sebelum alamat itu dikunci (minimal 3) |
| `ASISTEN_GAGAL_KUNCI` | `30` | lama kunci pertama dalam detik; berlipat dua tiap terkunci lagi, maksimal 600 |
| `ASISTEN_UNGGAH_MB` | `10` | ukuran maksimum satu unggahan (zip), dalam MB |
| `ASISTEN_PROMPT_DIR` | `prompt/` di folder proyek | folder berkas prompt untuk skill Tanpa (satu prompt satu berkas `.json`) |

Khusus `llama_server.sh` dan `start.sh` (dan sebagian `deploy/pasang-layanan.sh`):

| Variabel | Bawaan | Fungsi |
|---|---|---|
| `LLAMA_BIN` | `~/llama.cpp/build/bin/llama-server` | lokasi llama-server (juga dipakai `pasang-layanan.sh`) |
| `LLAMA_PORT` | `8080` | port llama-server yang dinyalakan (juga dipakai `pasang-layanan.sh`) |
| `LLAMA_HOST` | `127.0.0.1` | alamat bind llama-server (`0.0.0.0` = terbuka untuk jaringan) (hanya `llama_server.sh`) |
| `LLAMA_ARGS` | kosong | opsi tambahan untuk llama-server, mis. `"-t 4"` |
| `LLAMA_TUNGGU` | `120` | detik menunggu llama-server siap |
| `LLAMA_LOG` | kosong (`llama_server.sh`), `llama-server.log` di folder proyek (`start.sh`) | berkas log llama-server; kosong = log tampil di terminal |

`ASISTEN_MODELS_DIR` dan `ASISTEN_CTX` juga dipakai skrip ini untuk `--models-dir` dan `-c`, jadi
nilainya otomatis sama dengan asisten. Bila `LLAMA_BASE_URL` diisi, `start.sh` memakai llama-server
di alamat itu dan tidak menyalakan yang lokal.

## Keamanan

- Semua `/api` wajib **token** (`.token`, izin 600). Jangan bagikan alamat berisi token.
- Berkas unggahan tidak tepercaya: nama dan jalur divalidasi, hanya teks UTF-8, zip dibatasi (tanpa `..`,
  symlink, terenkripsi, zip bomb), dan obrolan berlampiran memakai aturan yang sama seperti setelah tool Web.
- **API key** model online disimpan di `pengaturan.json` (izin 600, tidak ikut git). Kunci tidak pernah dikirim balik
  ke browser (web hanya tahu ada/tidaknya), tidak ditulis ke log, dan tidak disimpan di browser. Kunci dikirim hanya
  sebagai header `Authorization` ke alamat yang kamu isi, dan **pengalihan (redirect) ditolak** saat memakai kunci agar
  tidak bocor ke server lain; bila penyedia mengalihkan, pakai alamat tujuannya (mis. `https://`). Alamat `http://` ke
  server di internet diberi peringatan karena kunci terkirim tanpa enkripsi. Siapa pun yang memegang token web bisa
  mengubah alamat/kunci ini, jadi jaga token seperti sebelumnya.
- Server memakai HTTP biasa (token tidak terenkripsi di jaringan), jadi pakai di jaringan tepercaya. Jangan buka port
  8090 ke internet; untuk akses dari luar rumah pakai VPN seperti Tailscale. Server tetap bind `0.0.0.0` supaya HP bisa
  menjangkau Pi, tetapi sebagai lapis kedua:
  - **Alamat dari internet ditolak (403).** Yang diterima hanya perangkat ini, jaringan rumah/kantor (`10.x`,
    `172.16-31.x`, `192.168.x`, IPv6 lokal), dan rentang VPN Tailscale (`100.64.0.0/10`). Port yang tanpa sengaja
    diteruskan (*port-forward*) di router tidak langsung membuka server. Tambah alamat tertentu dengan
    `ASISTEN_IZIN_IP=203.0.113.7,198.51.100.0/24`, atau buka semuanya dengan `ASISTEN_IZIN_PUBLIK=1` (tidak disarankan).
  - **Token salah berulang dikunci sementara.** Setelah `ASISTEN_GAGAL_MAKS` (10) token salah dalam semenit dari satu
    alamat, alamat itu dikunci `ASISTEN_GAGAL_KUNCI` (30) detik dengan jawaban 429. Kunci berikutnya berlipat dua
    (maksimal 10 menit). Selama terkunci, token benar pun ditolak, supaya tebakan tidak bisa diteruskan. Perangkat
    ini sendiri (`127.0.0.1`) tidak pernah dikunci. Bila halaman web memakai token lama berulang-ulang, tunggu kunci
    habis lalu buka alamat dengan token baru.
  - Semua jawaban membawa `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, dan `Referrer-Policy: no-referrer`
    (token ada di alamat `?token=`, jadi tidak boleh bocor lewat Referer).
  - Server tidak mempercayai `X-Forwarded-For`. Di belakang proksi di Pi yang sama, semua klien terlihat sebagai
    `127.0.0.1`, sehingga penyaring alamat dan pengunci token tidak berlaku. Pasang pembatasan di proksinya.
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
- Nama perintah yang disamarkan ikut dijaga. Variabel yang diberi nilai di dalam perintah itu sendiri diisi dulu sebelum
  dicocokkan, jadi `X=rm; $X -rf ~` **diblokir** seperti `rm -rf ~`. Bila nama perintah baru ditentukan saat shell berjalan
  (`$X -rf ~`, `$(echo rm) ...`, `` `echo rm` ... ``, `{rm,-rf,/}`, `/bin/r? ...`, `/???/r[m] ...`), perintah **selalu minta
  izin**, juga di mode AUTO. Pemakaian biasa (`echo $HOME`, `ls *.py`, `[ -f x ]`, `mkdir -p d/{a,b}`) tidak terganggu.
- Daftar blokir tetap pengaman dasar berbasis pola, bukan sandbox. Variabel yang nilainya datang dari luar perintah
  (lingkungan, berkas, keluaran perintah lain) tidak bisa dibaca polanya, dan `python3 -c` hanya ditahan oleh aturan izin.
  Baca perintah sebelum menekan Ya.
- Model kecil bisa salah mengerti perintah. Untuk pemula, biarkan mode AUTO **mati**.

## Berkas

| Berkas | Fungsi |
|---|---|
| `asisten.py` | pintu masuk (`python3 asisten.py`); isinya dipecah ke paket `server/` |
| `server/server_config.py` | folder (`web/`, `riwayat/`, `.token`), `MODELS_DIR`, token, batas buffer Agent |
| `server/server_state.py` | keadaan bersama: model aktif, `GEN_LOCK`, izin menunggu, buffer proses Agent |
| `server/server_log.py`, `server_akses.py` | log berwarna di terminal; token akses, alamat IP, penyaring alamat klien, dan pembatas token salah |
| `server/server_model.py` | daftar model, muat/bongkar di llama-server (dilewati bila tanpa mode router), idle, tombol Selesai |
| `server/server_koneksi.py` | daftar koneksi model (utama + tambahan): alamat, API key, jenis, nama (`pengaturan.json`), uji, hapus, penerapan ke paket `agen` |
| `server/server_chat.py` | penyimpanan riwayat obrolan |
| `server/server_ctx.py` | konteks satu proses generasi: mode AUTO, batal, izin lewat web |
| `server/server_agent.py`, `server_status.py` | buffer event Agent di latar belakang; isi `/api/status` |
| `server/server_unggah.py` | unggahan berkas: penampung paket, ekstrak zip aman, lampiran chat |
| `server/server_prompt.py` | prompt pilihan untuk skill Tanpa: satu prompt satu berkas di `prompt/`, tambah/ubah/hapus, ekspor/impor, migrasi, rakit (operasinya umum per `Ruang`, dipakai juga oleh `server_peran`) |
| `server/server_peran.py` | prompt pilihan per peran Agent: berkas di `prompt/agent/<peran>/`, ubah pilihan dari web (id) menjadi isi prompt untuk `cfg` |
| `web/prompt.js` | panel List prompt di layar Mulai sesi (centang, + prompt, hapus, Selesai) |
| `web/prompt_peran.js` | tombol "+ prompt" di tiap peran halaman Agent (daftar centang, tambah/ubah/hapus, impor/ekspor, tambah/ganti bawaan) |
| `server/server_handoff.py` | serah terima chat -> Agent -> chat: brief dari diskusi, lampiran obrolan, hasil kembali ke obrolan |
| `web/serahkan.js`, `web/serahkan.css` | tombol 🏭, kartu brief, progres Agent, dan kartu hasil + unduhan di halaman chat |
| `web/unggah.js`, `web/unggah.css` | tombol 📎 dan daftar lampiran (dipakai halaman Chat dan Agent) |
| `server/server_http.py` | penangan HTTP: rute `/api`, file statis, proses generasi di thread |
| `server/server_main.py` | argumen baris perintah, siklus hidup server, penutupan rapi |
| `agen/` | paket inti agen (dulu satu berkas `agen.py`); `import agen` tetap dipakai seperti biasa |
| `agen/agen_config.py` | konfigurasi: `LLAMA_URL`, `LLAMA_KEY`, `LLAMA_JENIS`, `CTX_MAKS`, `MAX_TOKENS`, `GERBANG`, `LOG_AKSI`, batas peringkasan |
| `agen/agen_prompt.py` | prompt sistem, skill web dan berpikir kritis, gerbang tool, jatah riwayat |
| `agen/agen_llama.py` | klien server model: permintaan biasa, stream SSE, header `Authorization`, penolakan redirect, pembaca jawaban satu putaran |
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
| `llama_server.sh` | menyalakan llama-server di terminal sendiri: banner alamat/port, log lengkap, opsi `--port --host --models-dir --ctx --api-key` |
| `start.sh` | jalan pintas: menjalankan `llama_server.sh` (bila perlu) lalu asisten, dengan satu perintah |
| `web/koneksi.js`, `koneksi.css` | dialog **Atur koneksi**: daftar koneksi (lokal/online), tambah, ubah, hapus, uji |
| `deploy/` | `pasang-layanan.sh` dan templat unit systemd (`*.service.in`) |
| `.github/workflows/tests.yml` | CI GitHub: menjalankan pengujian di Python 3.9, 3.11, 3.13 |
| `tests/` | pengujian otomatis (`unittest`) |
| `cli_lama.py` | versi CLI lama (tanpa web), masih bisa dipakai, dan memakai pengaman perintah yang sama. Contoh: `python3 cli_lama.py "cek suhu CPU"` |
| `riwayat/`, `.token`, `pengaturan.json`, `aksi.log*`, `llama-server.log` | data (dibuat otomatis, tidak ikut git) |

## Pengujian

```bash
cd ~/ai_asisten
python3 -m unittest discover -s tests -v
```

Mencakup tool, pengaman shell, dan susunan modul `src/` (`tests/test_tolls.py`), server web dan riwayat
(`tests/test_asisten.py`, memakai folder sementara, tidak menyentuh `riwayat/` asli),
agen dan skill (`tests/test_agen.py`, memakai model palsu), susunan paket `agen/` (`tests/test_agen_paket.py`) dan `server/` (`tests/test_server_paket.py`), unggah berkas (`tests/test_unggah.py`, `tests/unggah_smoke.js`), layar Mulai sesi (`tests/test_web.py`, `tests/index_smoke.js`), prompt untuk skill Tanpa (`tests/test_prompt.py`, `tests/prompt_smoke.js`), alur adaptif Agent (`tests/test_jalur.py`), prompt tiap peran Agent (`tests/test_peran.py`, `tests/prompt_peran_smoke.js`), serah terima chat-Agent (`tests/test_serahterima.py`, `tests/serahkan_smoke.js`),
keamanan jalur, rahasia, dan pengaman shell (`tests/test_keamanan.py`),
kunci generasi, batas token, dan perlindungan setelah tool web (`tests/test_batas_dan_taint.py`),
pemeriksaan tampilan web chat dan Agent (`tests/test_web.py`; sintaks JS dicek bila `node` terpasang),
Agent: urutan muat/bongkar model, putaran koreksi, Pemeriksa yang menjalankan dan menentukan, keamanan nama berkas, dan
endpoint `/api/agent`, dan log langsung di halaman Agent (`tests/test_tim.py` + `tests/agent_smoke.js`,
memakai llama-server dan model palsu; tes `agent_smoke.js` butuh `node`),
penguatan Pemeriksa: pembuktian kutipan, Pemeriksa kedua + sanggahan, deteksi macet, tanda keputusan lemah (`tests/test_pemeriksa.py`),
kotak uji jalan: environment bersih, batas memori/berkas/waktu, jaringan diputus (`tests/test_kotak.py`; tes jaringan dilewati bila `unshare -rn` tidak tersedia),
akses jaringan server: penyaring alamat, kunci token salah, header aman (`tests/test_jaringan.py`), dan perintah shell yang disamarkan (`tests/test_samar.py`),
rotasi `aksi.log` (`tests/test_aksilog.py`), pengaturan koneksi dan API key (`tests/test_koneksi.py` dengan server model palsu, termasuk lokal + online sekaligus,
yang meminta kunci, mengalihkan, dan berpura-pura router atau bukan; `tests/koneksi_smoke.js` butuh `node`), serta `start.sh`,
`llama_server.sh`, dan `deploy/pasang-layanan.sh` (`tests/test_skrip.py`, memakai llama-server dan systemctl palsu; butuh `bash`).
Tidak butuh model termuat dan tidak butuh llama-server menyala.

Setiap push ke GitHub menjalankan pengujian yang sama lewat GitHub Actions
(`.github/workflows/tests.yml`, Python 3.9, 3.11, dan 3.13).

## Pemecahan masalah

| Gejala | Penyebab umum dan solusi |
|---|---|
| Terminal: `Belum bisa menghubungi llama-server di ...` (aplikasi tetap menyala) | llama-server belum menyala atau alamatnya beda. Nyalakan `./llama_server.sh` ([langkah 4](#4-jalankan-llama-server)), cek dengan `curl http://127.0.0.1:8080/v1/models`, atau isi alamat yang benar lewat **Atur koneksi** di web |
| Web: `Tidak bisa menghubungi llama-server` | Sama seperti di atas. Dialog **Atur koneksi** → **Uji koneksi** menunjukkan penyebabnya (ditolak 401 = API key salah/kurang, 404 = alamat salah, tidak bisa terhubung = server mati/port salah) |
| Uji koneksi: `Server mengalihkan ke alamat lain` | Penyedia mengalihkan (sering `http://` → `https://`). Pakai alamat tujuannya; kunci sengaja tidak diteruskan ke pengalihan |
| Model online tidak muncul padahal API key sudah diisi | Biasanya alamat server belum diisi atau salah (key saja tidak cukup), atau lupa menekan **Simpan** setelah **Uji koneksi**. Lihat kartu koneksi di **Atur koneksi** (`✔ N model` atau `⚠ alasan`) dan [Mendaftarkan model online](#mendaftarkan-model-online-langkah-demi-langkah). Setelah mengganti berkas, jalankan ulang `asisten.py` dan muat ulang halaman |
| Model online terhubung tetapi chat gagal soal saldo/kuota | API ditagih terpisah dari langganan chat. Isi saldo di akun API penyedia |
| Daftar model online sangat panjang / ada model aneh | Itu isi `/v1/models` penyedia (termasuk embedding dll). Pakai kolom **Cari model** |
| Server model ada di PC/perangkat lain dan koneksinya gagal (timeout, ditolak, 401, 404, daftar model kosong) | Ikuti langkah di [Koneksi ke llama-server di PC lain gagal](#koneksi-ke-llama-server-di-pc-lain-gagal), setelah menjalankan llama-server dengan `--host 0.0.0.0` ([Cara 4](#cara-4-llama-server-di-pc-terpisah---host-0000)) |
| `Tidak bisa membuka port 8090` | Port dipakai program lain (mungkin `asisten.py` yang sudah jalan). Tutup yang lama, atau pakai `--port 8091` |
| Daftar model kosong di web | Tidak ada `.gguf` di folder model, atau llama-server dijalankan tanpa `--models-dir`. Cek `ls ~/models` dan perintah llama-server |
| Ukuran model tidak tampil | `ASISTEN_MODELS_DIR` tidak sama dengan folder `--models-dir`. Bila llama-server ada di PC lain, ini normal: server web tidak bisa melihat foldernya |
| `Model tidak ditemukan di llama-server` | Nama model tidak ada di `/v1/models`. Muat ulang halaman web, periksa nama file `.gguf` |
| `llama-server gagal memuat model` | RAM tidak cukup, file model rusak/terpotong, atau model tidak didukung versi llama.cpp. Lihat log di terminal llama-server, coba model lebih kecil, unduh ulang dengan `wget -c` |
| `Model belum siap setelah 5 menit` | Model terlalu besar untuk perangkat, atau kartu SD/disk lambat. Coba model lebih kecil |
| Halaman web menolak / "Akses ditolak (token salah)" | Buka lagi alamat lengkap yang berisi `?token=...` dari terminal. Token hilang? Jalankan `python3 asisten.py --token-baru` |
| HP tidak bisa membuka alamatnya | HP dan Pi harus satu Wi-Fi, IP bisa berubah (cek `hostname -I`), dan `asisten.py` jangan dijalankan dengan `--lokal` atau `--host 127.0.0.1`. Bila HP memakai data seluler atau alamat publik, server menjawab 403 `Ditolak: alamat di luar jaringan lokal`; sambungkan lewat Wi-Fi/VPN, atau izinkan alamatnya dengan `ASISTEN_IZIN_IP` |
| Jawaban 429 `Terlalu banyak token salah` | Alamat itu dikunci sementara karena token salah berulang. Tunggu sesuai detik di pesan (header `Retry-After`), lalu buka alamat dengan token yang benar |
| Model langsung memanggil tool untuk sapaan, atau jawabannya ngawur | Model terlalu kecil/tidak cocok untuk tool calling. Coba skill **Tanpa skill**, atau ganti model. Pastikan llama-server memakai `--jinja` |
| Jawaban berakhir dengan `[Jawaban terpotong ...]`, atau `tulis_file` gagal dengan pesan terpotong | Batas token satu jawaban (`ASISTEN_MAX_TOKENS`, bawaan 700) tercapai. Ketik `lanjut`, naikkan nilainya, atau minta file ditulis bertahap (`tambah=true`) |
| Riwayat terasa dilupakan | Konteks terbatas (`ASISTEN_CTX`), riwayat lama dipangkas saat dikirim ke model. Pastikan nilainya sama dengan `-c` di llama-server |
| `./start.sh`: `Permission denied` | `chmod +x start.sh deploy/pasang-layanan.sh`, atau jalankan dengan `bash start.sh` |
| `./start.sh`: `llama-server tidak ditemukan` | Belum dibangun, atau jalurnya lain. Bangun ([langkah 2](#2-pasang-llamacpp-llama-server)) atau isi `LLAMA_BIN=/jalur/ke/llama-server ./start.sh` |
| `./start.sh` atau `./llama_server.sh`: `llama-server berhenti saat dinyalakan` | Baca 20 baris log yang ditampilkan (lengkapnya di `llama-server.log`). Umumnya ada opsi yang tidak dikenal versi llama.cpp-mu, atau port dipakai program lain (coba `./llama_server.sh --port 8081`, lalu isi alamatnya di web) |
| `./llama_server.sh`: `port 8080 sudah dipakai` | Sudah ada llama-server (atau program lain) di port itu. Hentikan yang lama, atau pakai `--port` lain |
| Layanan systemd tidak menyala setelah Pi reboot | Jalankan `sudo loginctl enable-linger $USER`, lalu reboot. Periksa `systemctl --user status ai-asisten llama-server` |
| `ai-asisten` menyala tetapi daftar model kosong saat baru boot | Normal bila llama-server belum siap: asisten tidak lagi berhenti, cukup tekan **Muat ulang daftar model** beberapa detik kemudian |
| `aksi.log` terlalu besar | Diputar otomatis pada 1 MB. Ubah batasnya dengan `ASISTEN_LOG_MAKS_KB` (0 = tanpa rotasi) |
| Suhu CPU atau status throttling tidak tampil | Suhu dibaca dari `/sys/class/thermal/thermal_zone0/temp` (tidak ada di semua perangkat). Status throttling butuh `vcgencmd`, yang hanya ada di Raspberry Pi |

### Koneksi ke llama-server di PC lain gagal

Untuk skenario [Cara 4](#cara-4-llama-server-di-pc-terpisah---host-0000) (server web dan PC model terpisah).
Periksa berurutan; berhenti di langkah pertama yang gagal.

**Langkah diagnosa**

1. **Di PC model**, apakah llama-server hidup dan mendengarkan semua alamat?

   ```bash
   curl -H "Authorization: Bearer KUNCI" http://127.0.0.1:8080/v1/models    # tanpa -H bila tanpa API key
   ss -ltn | grep 8080          # Linux; Windows: netstat -an | findstr 8080
   ```

   Kolom alamat harus `0.0.0.0:8080` (atau `*:8080`). Kalau `127.0.0.1:8080`, server belum dinyalakan
   dengan `--host 0.0.0.0`.
2. **Dari server web**, apakah PC model terjangkau?

   ```bash
   ping -c 3 192.168.1.50
   curl -v --max-time 5 -H "Authorization: Bearer KUNCI" http://192.168.1.50:8080/v1/models
   ```
3. **Di web**: **Atur koneksi** → **Uji koneksi**. Pesannya sama dengan hasil `curl` di langkah 2.

**Gejala dan solusi**

| Gejala | Penyebab umum dan solusi |
|---|---|
| `curl`: `Connection refused`, atau **Uji koneksi** "tidak bisa terhubung" | Alamat terjangkau tetapi tidak ada yang mendengarkan di port itu. Server belum jalan, port salah, atau llama-server masih di `127.0.0.1`. Nyalakan ulang dengan `./llama_server.sh --host 0.0.0.0`, lalu cek `ss -ltn \| grep 8080` di PC model |
| `curl`: lama lalu `Connection timed out`, `ping` juga gagal atau `No route to host` | Paket tidak sampai. Penyebab terbanyak: **firewall** PC model memblokir port (buka sesuai langkah A.3 di Cara 4), IP salah (cek ulang dengan `hostname -I` / `ipconfig` di PC model), atau kedua perangkat beda jaringan/subnet. Router dengan "AP isolation" / "guest network" juga memblokir antar-perangkat |
| `ping` berhasil tetapi `curl` timeout | Ping lolos, port 8080 yang diblokir firewall. Buka port TCP 8080 (`sudo ufw allow from 192.168.1.0/24 to any port 8080 proto tcp`, atau aturan Inbound di Windows). Di Windows pastikan jaringannya berprofil *Private*, bukan *Public* |
| **401** / "ditolak" | API key di web berbeda dengan `--api-key` / `LLAMA_API_KEY` di PC model, atau kolom API key kosong. Isi ulang di **Atur koneksi** (tanpa spasi atau baris baru di ujung kunci), **Uji koneksi**, **Simpan** |
| **404** / "alamat salah" | Alamat tidak menunjuk ke llama-server. Isi `http://IP:PORT` saja (tanpa `/v1/models` atau garis miring tambahan), pastikan `http` (bukan `https`) dan portnya sama dengan yang dicetak `llama_server.sh` |
| Awalnya berhasil, lalu mendadak gagal | Alamat PC model berubah (DHCP), PC tidur/mati, atau llama-server berhenti saat terminalnya ditutup. Cek IP baru, nyalakan ulang di `tmux` atau layanan systemd (Cara 4, langkah A.4), dan beri PC itu IP tetap |
| Web terhubung, daftar model **kosong** | Folder yang dipakai `--models-dir` di **PC model** tidak berisi `.gguf` (folder di server web tidak dipakai sama sekali). Cek `ls ~/models` di PC model dan `./llama_server.sh` yang mencetak jumlah `.gguf` saat start |
| Model gagal dimuat, atau llama-server mati mendadak saat pindah model | RAM 8 GB di PC model tidak cukup. Nyalakan **Bongkar model tiap tahap selesai** di halaman Agent, pakai model berkuantisasi lebih kecil (mis. Q4_K_M), turunkan `--ctx`, atau tutup program lain di PC itu. Lihat log di terminal llama-server (kata kunci `out of memory` / `failed to allocate`) |
| `llama-server berhenti saat dinyalakan`, galat `unknown argument` / `invalid argument` | Versi llama.cpp di PC model tidak mengenal salah satu opsi (mis. `--jinja` atau `--models-dir` pada versi lama). Perbarui llama.cpp (`git pull` lalu bangun ulang), atau cek `llama-server --help` |
| `address already in use` / `port 8080 sudah dipakai` | Ada llama-server lama atau program lain di port itu. Hentikan yang lama (`pkill llama-server`), atau pakai `--port 8081` dan ubah alamatnya di web |
| Peringatan `0.0.0.0 tanpa --api-key` | Server terbuka untuk semua perangkat di jaringan. Tambahkan `--api-key`, lalu isi kunci yang sama di web |
| Respons sangat lambat, atau galat waktu habis saat model besar dimuat | Pemuatan pertama dari disk lambat (HDD, SD, atau RAM nyaris penuh). Tunggu hingga model siap (batasnya 5 menit), atau pakai model yang lebih kecil |
| Model tampil, tetapi isi jawaban terpotong / riwayat terasa dilupakan | `ASISTEN_CTX` di server web tidak sama dengan `--ctx` di PC model. Samakan keduanya |

Bila semuanya tampak benar tetapi tetap gagal, jalankan `./llama_server.sh --log llama.log` di PC model
(atau baca terminalnya), ulangi **Uji koneksi** dari web, lalu lihat apakah permintaan muncul di log.
Bila tidak ada permintaan yang masuk sama sekali, masalahnya ada di jaringan atau firewall, bukan di llama-server.

## Batasan

Model kecil cukup untuk tugas sederhana (lihat folder, baca file, cek status) tetapi
sering salah di tugas berlangkah banyak. Konteks server 8192 token, jadi riwayat lama
dipangkas saat dikirim ke model (riwayat di disk tetap utuh). Hanya satu proses
generasi berjalan pada satu waktu.
