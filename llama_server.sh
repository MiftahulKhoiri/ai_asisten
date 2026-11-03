#!/usr/bin/env bash
# llama_server.sh - menyalakan llama-server (mode router: banyak model dalam satu folder).
# Dijalankan di terminal tersendiri; log llama-server tampil lengkap di sini. Ctrl+C untuk berhenti.
# AI Asisten (asisten.py) TIDAK menyalakan llama-server: alamatnya diisi di web (Pengaturan koneksi).
#
# Pemakaian:   ./llama_server.sh [opsi] [-- opsi tambahan llama-server]
#   --port N          port yang didengarkan            (bawaan: 8080)
#   --host ALAMAT     alamat bind                       (bawaan: 127.0.0.1; 0.0.0.0 = bisa diakses
#                                                        perangkat lain di jaringan)
#   --models-dir DIR  folder file .gguf                 (bawaan: ~/models)
#   --ctx N           ukuran konteks                    (bawaan: 8192)
#   --bin JALUR       lokasi llama-server               (bawaan: ~/llama.cpp/build/bin/llama-server)
#   --api-key KUNCI   llama-server hanya melayani permintaan yang membawa kunci ini
#   --log BERKAS      tulis log llama-server ke berkas, bukan ke terminal
#   --tunggu DETIK    batas menunggu llama-server siap  (bawaan: 120)
#   -h, --help        bantuan
#
# Contoh:   ./llama_server.sh --port 8081 --host 0.0.0.0 --ctx 16384
#           ./llama_server.sh -- -t 4          (semua sesudah -- diteruskan ke llama-server)
#
# Variabel lingkungan (setara opsi di atas; opsi baris perintah menang):
#   LLAMA_BIN  LLAMA_HOST  LLAMA_PORT  ASISTEN_MODELS_DIR  ASISTEN_CTX  LLAMA_API_KEY
#   LLAMA_TUNGGU  LLAMA_LOG  LLAMA_ARGS (opsi tambahan llama-server, mis. "-t 4")

set -u

LLAMA_BIN="${LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
HOST="${LLAMA_HOST:-127.0.0.1}"
PORT="${LLAMA_PORT:-8080}"
MODELS_DIR="${ASISTEN_MODELS_DIR:-$HOME/models}"
CTX="${ASISTEN_CTX:-8192}"
TUNGGU="${LLAMA_TUNGGU:-120}"
LOG="${LLAMA_LOG:-}"
KUNCI="${LLAMA_API_KEY:-}"
# shellcheck disable=SC2206
EXTRA=(${LLAMA_ARGS:-})

info() { printf 'INFO  %s\n' "$*"; }
ok() { printf 'OK    %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*" >&2; }
galat() { printf 'ERR   %s\n' "$*" >&2; }

bantuan() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

perlu_nilai() { [ $# -ge 2 ] || { galat "opsi $1 butuh nilai"; exit 2; }; }

while [ $# -gt 0 ]; do
    case "$1" in
        --port) perlu_nilai "$@"; PORT="$2"; shift 2 ;;
        --host) perlu_nilai "$@"; HOST="$2"; shift 2 ;;
        --models-dir) perlu_nilai "$@"; MODELS_DIR="$2"; shift 2 ;;
        --ctx) perlu_nilai "$@"; CTX="$2"; shift 2 ;;
        --bin) perlu_nilai "$@"; LLAMA_BIN="$2"; shift 2 ;;
        --api-key) perlu_nilai "$@"; KUNCI="$2"; shift 2 ;;
        --log) perlu_nilai "$@"; LOG="$2"; shift 2 ;;
        --tunggu) perlu_nilai "$@"; TUNGGU="$2"; shift 2 ;;
        -h|--help) bantuan; exit 0 ;;
        --) shift; EXTRA+=("$@"); break ;;
        *) galat "opsi tidak dikenal: $1 (lihat ./llama_server.sh --help; opsi llama-server taruh sesudah --)"; exit 2 ;;
    esac
done

case "$PORT$CTX$TUNGGU" in
    ''|*[!0-9]*) galat "--port, --ctx, dan --tunggu harus berupa angka"; exit 2 ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
    galat "python3 tidak ditemukan. Pasang dulu: sudo apt install python3"
    exit 1
fi

# Alamat yang dipakai untuk memeriksa (bind 0.0.0.0 diperiksa lewat 127.0.0.1).
case "$HOST" in 0.0.0.0|""|::) CEK="127.0.0.1" ;; *) CEK="$HOST" ;; esac

# Keluaran 0 bila ada yang menjawab di alamat itu. Jawaban 401/403 (butuh kunci) juga berarti hidup.
llama_hidup() {
    python3 - "$CEK" "$PORT" <<'PY'
import sys
import urllib.error
import urllib.request
try:
    urllib.request.urlopen("http://%s:%s/v1/models" % (sys.argv[1], sys.argv[2]), timeout=2).read()
except urllib.error.HTTPError as e:
    sys.exit(0 if e.code < 500 else 1)
except Exception:
    sys.exit(1)
PY
}

# Alamat yang bisa dipakai perangkat lain di jaringan (tanpa mengirim paket apa pun).
ip_lan() {
    python3 - <<'PY'
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("10.255.255.255", 1))
    print(s.getsockname()[0])
except Exception:
    print("127.0.0.1")
PY
}

if [ ! -x "$LLAMA_BIN" ]; then
    if command -v llama-server >/dev/null 2>&1; then
        LLAMA_BIN="$(command -v llama-server)"
    else
        galat "llama-server tidak ditemukan di $LLAMA_BIN"
        galat "Bangun dulu (lihat README, langkah 2) atau isi --bin /jalur/ke/llama-server"
        exit 1
    fi
fi

if llama_hidup; then
    galat "port $PORT sudah dipakai: sudah ada yang menjawab di http://$CEK:$PORT"
    galat "Hentikan yang lama, atau pilih port lain: ./llama_server.sh --port 8081"
    exit 1
fi

if [ ! -d "$MODELS_DIR" ]; then
    warn "folder model tidak ada: $MODELS_DIR (lihat README, langkah 3)"
    JUMLAH=0
else
    JUMLAH=$(find "$MODELS_DIR" -maxdepth 1 -name '*.gguf' 2>/dev/null | wc -l | tr -d ' ')
    [ "$JUMLAH" -gt 0 ] || warn "tidak ada file .gguf di $MODELS_DIR (lihat README, langkah 3)"
fi

if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
    ALAMAT="http://$(ip_lan):$PORT"
    [ -n "$KUNCI" ] || warn "terbuka untuk seluruh jaringan TANPA kunci. Disarankan: --api-key KUNCI"
else
    ALAMAT="http://$CEK:$PORT"
fi

[ -z "$KUNCI" ] || export LLAMA_API_KEY="$KUNCI"   # dibaca llama-server; tidak tampil di daftar proses

PID=""
bersih() {
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        kill "$PID" 2>/dev/null
        wait "$PID" 2>/dev/null
        info "llama-server dihentikan"
    fi
    PID=""
}
trap bersih EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

info "program      : $LLAMA_BIN"
info "folder model : $MODELS_DIR ($JUMLAH berkas .gguf)"
info "konteks      : $CTX"
info "mendengarkan : $HOST:$PORT"
if [ -n "$KUNCI" ]; then info "API key      : dipakai (klien wajib membawa kunci)"; else info "API key      : tidak dipakai"; fi
[ -z "$LOG" ] || info "log          : $LOG"
info "menyalakan llama-server ..."

if [ -n "$LOG" ]; then
    "$LLAMA_BIN" --models-dir "$MODELS_DIR" --host "$HOST" --port "$PORT" \
        -c "$CTX" --jinja "${EXTRA[@]+"${EXTRA[@]}"}" >"$LOG" 2>&1 &
else
    "$LLAMA_BIN" --models-dir "$MODELS_DIR" --host "$HOST" --port "$PORT" \
        -c "$CTX" --jinja "${EXTRA[@]+"${EXTRA[@]}"}" &
fi
PID=$!

siap=0
for _ in $(seq 1 "$TUNGGU"); do
    if llama_hidup; then
        siap=1
        break
    fi
    if ! kill -0 "$PID" 2>/dev/null; then
        wait "$PID"
        kode=$?
        PID=""
        galat "llama-server berhenti saat dinyalakan (kode $kode)"
        if [ -n "$LOG" ]; then
            galat "20 baris terakhir log:"
            tail -n 20 "$LOG" >&2
        fi
        exit 1
    fi
    sleep 1
done
if [ "$siap" -ne 1 ]; then
    galat "llama-server belum siap setelah $TUNGGU detik${LOG:+. Lihat $LOG}"
    exit 1
fi

echo
ok "llama-server siap"
ok "ISI ALAMAT INI di web (Pengaturan koneksi): $ALAMAT"
[ -z "$KUNCI" ] || info "isi juga API key yang sama di Pengaturan koneksi"
info "tekan Ctrl+C untuk berhenti"
echo

# Menunggu llama-server selesai. wait terpotong sinyal, jadi diulang sampai benar-benar selesai.
kode=0
while kill -0 "$PID" 2>/dev/null; do
    wait "$PID"
    kode=$?
done
if [ "$kode" -ne 0 ] && [ "$kode" -lt 128 ]; then
    galat "llama-server berhenti sendiri (kode $kode)${LOG:+. Lihat $LOG}"
fi
PID=""
exit "$kode"
