#!/usr/bin/env bash
# Memasang AI Asisten sebagai layanan systemd tingkat-pengguna (tanpa sudo), supaya
# llama-server dan asisten menyala otomatis saat Raspberry Pi hidup.
#
#   ./deploy/pasang-layanan.sh           pasang, nyalakan, aktifkan saat boot
#   ./deploy/pasang-layanan.sh --hapus   hentikan dan hapus layanan
#
# Pengaturan (opsional): LLAMA_BIN, ASISTEN_MODELS_DIR, LLAMA_PORT, ASISTEN_CTX
# (sama seperti start.sh). Jalur tidak boleh mengandung spasi.

set -eu

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYSTEMCTL="${SYSTEMCTL:-systemctl}"
LOGINCTL="${LOGINCTL:-loginctl}"
UNIT_DIR="${SYSTEMD_USER_DIR:-$HOME/.config/systemd/user}"
LLAMA_BIN="${LLAMA_BIN:-$HOME/llama.cpp/build/bin/llama-server}"
MODELS_DIR="${ASISTEN_MODELS_DIR:-$HOME/models}"
PORT="${LLAMA_PORT:-8080}"
CTX="${ASISTEN_CTX:-8192}"
PYTHON="$(command -v python3 || true)"
UNIT_LLAMA="llama-server.service"
UNIT_ASISTEN="ai-asisten.service"

galat() { printf 'ERR   %s\n' "$*" >&2; exit 1; }

if [ "${1:-}" = "--hapus" ]; then
    "$SYSTEMCTL" --user disable --now "$UNIT_ASISTEN" "$UNIT_LLAMA" 2>/dev/null || true
    rm -f "$UNIT_DIR/$UNIT_ASISTEN" "$UNIT_DIR/$UNIT_LLAMA"
    "$SYSTEMCTL" --user daemon-reload
    echo "OK    layanan dihapus"
    exit 0
fi
[ $# -eq 0 ] || galat "opsi tidak dikenal: $1 (yang ada: --hapus)"

for nilai in "$DIR" "$LLAMA_BIN" "$MODELS_DIR" "$PYTHON"; do
    case "$nilai" in
        *[[:space:]\|\&\\\"\']*) galat "jalur tidak boleh mengandung spasi atau tanda kutip: $nilai" ;;
    esac
done
[ -n "$PYTHON" ] || galat "python3 tidak ditemukan"
[ -x "$LLAMA_BIN" ] || galat "llama-server tidak ditemukan di $LLAMA_BIN (isi LLAMA_BIN=/jalur/ke/llama-server)"
case "$PORT$CTX" in *[!0-9]*) galat "LLAMA_PORT dan ASISTEN_CTX harus berupa angka" ;; esac

mkdir -p "$UNIT_DIR"
for unit in "$UNIT_LLAMA" "$UNIT_ASISTEN"; do
    sed -e "s|@DIR@|$DIR|g" -e "s|@PYTHON@|$PYTHON|g" -e "s|@LLAMA_BIN@|$LLAMA_BIN|g" \
        -e "s|@MODELS_DIR@|$MODELS_DIR|g" -e "s|@PORT@|$PORT|g" -e "s|@CTX@|$CTX|g" \
        "$DIR/deploy/$unit.in" > "$UNIT_DIR/$unit"
done

"$SYSTEMCTL" --user daemon-reload
"$SYSTEMCTL" --user enable --now "$UNIT_LLAMA" "$UNIT_ASISTEN"
"$LOGINCTL" enable-linger "$(id -un)" 2>/dev/null \
    || echo "WARN  gagal mengaktifkan linger; layanan baru menyala setelah kamu login. Coba: sudo loginctl enable-linger $(id -un)"

echo "OK    layanan terpasang di $UNIT_DIR"
echo "INFO  status : systemctl --user status ai-asisten llama-server"
echo "INFO  log    : journalctl --user -u ai-asisten -f"
echo "INFO  token  : cat $DIR/.token"
