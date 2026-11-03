#!/usr/bin/env bash
# start.sh - jalan pintas: menyalakan llama-server (lewat llama_server.sh) lalu AI Asisten.
# Ctrl+C menghentikan asisten, dan llama-server ikut dihentikan bila dinyalakan oleh skrip ini.
#
# Untuk memakai TERMINAL TERPISAH (log llama-server tampil lengkap), jalankan sendiri-sendiri:
#     terminal 1:  ./llama_server.sh [--port 8080 ...]
#     terminal 2:  python3 asisten.py        (alamat llama-server diisi di web: Pengaturan koneksi)
#
# Pemakaian:   ./start.sh [--tanpa-llama] [opsi asisten.py]    contoh: ./start.sh --port 8091 --idle 10
#   --tanpa-llama       hanya menyalakan asisten (llama-server sudah ada / dipakai dari perangkat lain / online)
#
# Pengaturan lewat variabel lingkungan (semuanya opsional; yang berkaitan dengan llama-server
# dipakai oleh llama_server.sh, lihat ./llama_server.sh --help):
#   LLAMA_BIN  ASISTEN_MODELS_DIR  LLAMA_PORT  ASISTEN_CTX  LLAMA_ARGS  LLAMA_TUNGGU  LLAMA_API_KEY
#   LLAMA_LOG           berkas log llama-server (bawaan: llama-server.log di folder proyek)
#   LLAMA_BASE_URL      bila diisi, memakai llama-server di alamat itu dan TIDAK
#                       menyalakan yang lokal

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_PORT="${LLAMA_PORT:-8080}"
TUNGGU="${LLAMA_TUNGGU:-120}"
LOG_LLAMA="${LLAMA_LOG:-$DIR/llama-server.log}"
PID_LLAMA=""
TANPA_LLAMA=0

info() { printf 'INFO  %s\n' "$*"; }
galat() { printf 'ERR   %s\n' "$*" >&2; }

if [ "${1:-}" = "--tanpa-llama" ]; then
    TANPA_LLAMA=1
    shift
fi

llama_hidup() {   # $1 = alamat dasar, mis. http://127.0.0.1:8080 ; jawaban 401/403 juga berarti hidup
    python3 - "$1" <<'PY'
import sys
import urllib.error
import urllib.request
alamat = sys.argv[1].rstrip("/")
if alamat.endswith("/v1"):
    alamat = alamat[:-3]
try:
    urllib.request.urlopen(alamat + "/v1/models", timeout=2).read()
except urllib.error.HTTPError as e:
    sys.exit(0 if e.code < 500 else 1)
except Exception:
    sys.exit(1)
PY
}

bersih() {
    if [ -n "$PID_LLAMA" ] && kill -0 "$PID_LLAMA" 2>/dev/null; then
        kill "$PID_LLAMA" 2>/dev/null
        wait "$PID_LLAMA" 2>/dev/null
    fi
}
trap bersih EXIT

if ! command -v python3 >/dev/null 2>&1; then
    galat "python3 tidak ditemukan. Pasang dulu: sudo apt install python3"
    exit 1
fi

if [ "$TANPA_LLAMA" -eq 1 ]; then
    info "tanpa llama-server (alamatnya diatur di web: Pengaturan koneksi)"
elif [ -n "${LLAMA_BASE_URL:-}" ]; then
    info "memakai llama-server di $LLAMA_BASE_URL (tidak menyalakan yang lokal)"
else
    export LLAMA_BASE_URL="http://127.0.0.1:$LLAMA_PORT"
    if llama_hidup "$LLAMA_BASE_URL"; then
        info "llama-server sudah hidup di $LLAMA_BASE_URL, dipakai apa adanya"
    else
        info "menyalakan llama-server lewat llama_server.sh (log: $LOG_LLAMA)"
        # llama_server.sh sendiri menunggu sampai siap, lalu menahan proses ini sampai dihentikan.
        bash "$DIR/llama_server.sh" --log "$LOG_LLAMA" --port "$LLAMA_PORT" &
        PID_LLAMA=$!
        siap=0
        while kill -0 "$PID_LLAMA" 2>/dev/null; do
            if llama_hidup "$LLAMA_BASE_URL"; then
                siap=1
                break
            fi
            sleep 1
        done
        if [ "$siap" -ne 1 ]; then
            wait "$PID_LLAMA" 2>/dev/null
            PID_LLAMA=""
            exit 1
        fi
    fi
fi

# asisten.py dijalankan di latar belakang agar sinyal (kill/TERM) ke skrip ini bisa
# diteruskan. Ctrl+C dari terminal sampai ke asisten.py langsung, jadi skrip hanya menunggu.
# llama-server baru dihentikan SETELAH asisten selesai, supaya model sempat dibongkar.
python3 "$DIR/asisten.py" "$@" &
PID_ASISTEN=$!
trap 'kill -TERM "$PID_ASISTEN" 2>/dev/null' TERM HUP
trap ':' INT
wait "$PID_ASISTEN"
kode=$?
while kill -0 "$PID_ASISTEN" 2>/dev/null; do   # wait terpotong sinyal; tunggu sampai benar-benar selesai
    wait "$PID_ASISTEN"
    kode=$?
done
exit "$kode"
