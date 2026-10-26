#!/usr/bin/env bash
# start.sh - menyalakan llama-server (bila belum hidup) lalu AI Asisten.
# Ctrl+C menghentikan asisten, dan llama-server ikut dihentikan bila dinyalakan oleh skrip ini.
#
# Pemakaian:   ./start.sh [opsi asisten.py]      contoh: ./start.sh --port 8091 --idle 10
#
# Pengaturan lewat variabel lingkungan (semuanya opsional):
#   LLAMA_BIN           lokasi llama-server    (bawaan: ~/llama.cpp/build/bin/llama-server)
#   ASISTEN_MODELS_DIR  folder file .gguf      (bawaan: ~/models)
#   LLAMA_PORT          port llama-server      (bawaan: 8080)
#   ASISTEN_CTX         ukuran konteks         (bawaan: 8192)
#   LLAMA_ARGS          opsi tambahan llama-server, mis. "-t 4"
#   LLAMA_TUNGGU        detik menunggu llama-server siap (bawaan: 120)
#   LLAMA_LOG           berkas log llama-server (bawaan: llama-server.log di folder proyek)
#   LLAMA_BASE_URL      bila diisi, memakai llama-server di alamat itu dan TIDAK
#                       menyalakan yang lokal

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LLAMA_BIN="${LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
MODELS_DIR="${ASISTEN_MODELS_DIR:-$HOME/models}"
LLAMA_PORT="${LLAMA_PORT:-8080}"
CTX="${ASISTEN_CTX:-8192}"
TUNGGU="${LLAMA_TUNGGU:-120}"
LOG_LLAMA="${LLAMA_LOG:-$DIR/llama-server.log}"
PID_LLAMA=""

info() { printf 'INFO  %s\n' "$*"; }
warn() { printf 'WARN  %s\n' "$*" >&2; }
galat() { printf 'ERR   %s\n' "$*" >&2; }

llama_hidup() {   # $1 = alamat dasar, mis. http://127.0.0.1:8080
    python3 - "$1" <<'PY'
import sys
import urllib.request
alamat = sys.argv[1].rstrip("/")
if alamat.endswith("/v1"):
    alamat = alamat[:-3]
try:
    urllib.request.urlopen(alamat + "/v1/models", timeout=2).read()
except Exception:
    sys.exit(1)
PY
}

bersih() {
    if [ -n "$PID_LLAMA" ] && kill -0 "$PID_LLAMA" 2>/dev/null; then
        kill "$PID_LLAMA" 2>/dev/null
        wait "$PID_LLAMA" 2>/dev/null
        info "llama-server dihentikan"
    fi
}
trap bersih EXIT

if ! command -v python3 >/dev/null 2>&1; then
    galat "python3 tidak ditemukan. Pasang dulu: sudo apt install python3"
    exit 1
fi

if [ -n "${LLAMA_BASE_URL:-}" ]; then
    info "memakai llama-server di $LLAMA_BASE_URL (tidak menyalakan yang lokal)"
else
    export LLAMA_BASE_URL="http://127.0.0.1:$LLAMA_PORT"
    if llama_hidup "$LLAMA_BASE_URL"; then
        info "llama-server sudah hidup di $LLAMA_BASE_URL, dipakai apa adanya"
    else
        if [ ! -x "$LLAMA_BIN" ]; then
            if command -v llama-server >/dev/null 2>&1; then
                LLAMA_BIN="$(command -v llama-server)"
            else
                galat "llama-server tidak ditemukan di $LLAMA_BIN"
                galat "Bangun dulu (lihat README, langkah 2) atau isi LLAMA_BIN=/jalur/ke/llama-server"
                exit 1
            fi
        fi
        if ! compgen -G "$MODELS_DIR/*.gguf" >/dev/null; then
            warn "tidak ada file .gguf di $MODELS_DIR (lihat README, langkah 3)"
        fi
        # shellcheck disable=SC2206
        EXTRA=(${LLAMA_ARGS:-})
        info "menyalakan llama-server di port $LLAMA_PORT (log: $LOG_LLAMA)"
        "$LLAMA_BIN" --models-dir "$MODELS_DIR" --host 127.0.0.1 --port "$LLAMA_PORT" \
            -c "$CTX" --jinja "${EXTRA[@]+"${EXTRA[@]}"}" >"$LOG_LLAMA" 2>&1 &
        PID_LLAMA=$!
        siap=0
        for _ in $(seq 1 "$TUNGGU"); do
            if llama_hidup "$LLAMA_BASE_URL"; then
                siap=1
                break
            fi
            if ! kill -0 "$PID_LLAMA" 2>/dev/null; then
                galat "llama-server berhenti saat dinyalakan. 20 baris terakhir log:"
                tail -n 20 "$LOG_LLAMA" >&2
                PID_LLAMA=""
                exit 1
            fi
            sleep 1
        done
        if [ "$siap" -ne 1 ]; then
            galat "llama-server belum siap setelah $TUNGGU detik. Lihat $LOG_LLAMA"
            exit 1
        fi
        info "llama-server siap"
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
