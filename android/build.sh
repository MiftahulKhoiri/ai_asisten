#!/usr/bin/env bash
# build.sh - membangun APK AI Asisten tanpa Gradle/Android Studio.
# Jalan di Raspberry Pi arm64 (alat dari ~/android-tools, lihat siapkan-alat.sh) maupun di GitHub
# Actions (alat dari Android SDK runner, diberikan lewat variabel lingkungan).
#
#   ./build.sh  ->  build/ai_asisten.apk  (sudah ditandatangani, siap dipasang di HP)
#
# Variabel opsional (kalau kosong dicari di ~/android-tools):
#   AAPT2 ZIPALIGN ANDROID_JAR D8_JAR APKSIGNER_JAR   lokasi alat
#   VERSI_KODE   versionCode (bawaan: jumlah commit git, jadi selalu naik)
#   NAMA_APK     nama berkas hasil di build/ (bawaan ai_asisten.apk)
# Versi tampilan (versionName) dibaca dari berkas VERSI.
# Kunci tanda tangan ada di kunci/ dan ikut di-commit (seperti Game_server): APK dari Pi maupun dari
# GitHub ditandatangani kunci yang sama, jadi versi baru selalu bisa dipasang menimpa yang lama.
set -euo pipefail

MIN_SDK=24        # Android 7.0
TARGET_SDK=34     # Android 14

DIR="$(cd "$(dirname "$0")" && pwd)"
ALAT="${ANDROID_TOOLS:-$HOME/android-tools}"
VERSI_NAMA="$(tr -d ' \r\n' < "$DIR/VERSI")"
VERSI_KODE="${VERSI_KODE:-$(git -C "$DIR" rev-list --count HEAD 2>/dev/null || echo 1)}"
NAMA_APK="${NAMA_APK:-ai_asisten.apk}"
KUNCI="$DIR/kunci/ai_asisten.jks"
SANDI="$DIR/kunci/sandi"

cari() { find "$ALAT/$1" -name "$2" -type f -not -path "*/share/*" 2>/dev/null | head -1; }
AAPT2="${AAPT2:-$(cari root aapt2)}"
ZIPALIGN="${ZIPALIGN:-$(cari root zipalign)}"
ANDROID_JAR="${ANDROID_JAR:-$(cari sdk34 android.jar)}"   # platform 34: aapt2 Debian belum bisa membaca android.jar 35
D8_JAR="${D8_JAR:-$(cari sdk d8.jar)}"
APKSIGNER_JAR="${APKSIGNER_JAR:-$(cari sdk apksigner.jar)}"
for v in AAPT2 ZIPALIGN ANDROID_JAR D8_JAR APKSIGNER_JAR; do
    if [ -z "${!v}" ] || [ ! -f "${!v}" ]; then
        echo "Alat $v tidak ditemukan. Di Pi: jalankan ./siapkan-alat.sh dulu." >&2
        exit 1
    fi
done
# aapt2/zipalign hasil ekstrak paket Debian butuh pustaka dari folder yang sama.
if [ -d "$ALAT/root/usr/lib" ]; then
    export LD_LIBRARY_PATH="$ALAT/root/usr/lib/aarch64-linux-gnu/android:$ALAT/root/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

B="$DIR/build"
rm -rf "$B"
mkdir -p "$B/gen" "$B/kelas" "$B/dex"
echo "AI Asisten versi $VERSI_NAMA (versionCode $VERSI_KODE)"

echo "== 1/6 sumber daya (aapt2 compile)"
"$AAPT2" compile --dir "$DIR/res" -o "$B/res.zip"

echo "== 2/6 manifest + sumber daya (aapt2 link)"
"$AAPT2" link -o "$B/tanpa-dex.apk" -I "$ANDROID_JAR" \
    --manifest "$DIR/AndroidManifest.xml" --java "$B/gen" \
    --min-sdk-version "$MIN_SDK" --target-sdk-version "$TARGET_SDK" \
    --version-code "$VERSI_KODE" --version-name "$VERSI_NAMA" \
    "$B/res.zip"

echo "== 3/6 kompilasi Java"
find "$DIR/src" "$B/gen" -name '*.java' > "$B/sumber.txt"
javac --release 8 -nowarn -Xlint:-options -encoding UTF-8 \
    -classpath "$ANDROID_JAR" -d "$B/kelas" @"$B/sumber.txt"

echo "== 4/6 dex (d8)"
find "$B/kelas" -name '*.class' > "$B/kelas.txt"
java -cp "$D8_JAR" com.android.tools.r8.D8 --release --min-api "$MIN_SDK" \
    --lib "$ANDROID_JAR" --output "$B/dex" @"$B/kelas.txt"

echo "== 5/6 gabung + zipalign"
python3 - "$B/tanpa-dex.apk" "$B/dex/classes.dex" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "a", zipfile.ZIP_DEFLATED) as z:
    z.write(sys.argv[2], "classes.dex")
PY
"$ZIPALIGN" -f -p 4 "$B/tanpa-dex.apk" "$B/rata.apk"

echo "== 6/6 tanda tangan (apksigner)"
if [ ! -f "$KUNCI" ] || [ ! -f "$SANDI" ]; then
    echo "Kunci tanda tangan tidak ada di $DIR/kunci/." >&2
    echo "Jangan buat kunci baru kalau aplikasi sudah terpasang di HP (APK baru tidak bisa menimpa)." >&2
    echo "Kalau memang belum pernah ada:  ./build.sh --kunci-baru" >&2
    [ "${1:-}" = "--kunci-baru" ] || exit 1
    mkdir -p "$DIR/kunci"
    head -c 24 /dev/urandom | base64 | tr -d '/+=' > "$SANDI"
    keytool -genkeypair -keystore "$KUNCI" -storetype PKCS12 -alias ai_asisten \
        -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=AI Asisten" \
        -storepass "$(cat "$SANDI")" >/dev/null 2>&1
    echo "   kunci baru dibuat: $KUNCI"
fi
java -jar "$APKSIGNER_JAR" sign --ks "$KUNCI" --ks-key-alias ai_asisten \
    --ks-pass "file:$SANDI" --out "$B/$NAMA_APK" "$B/rata.apk"
java -jar "$APKSIGNER_JAR" verify "$B/$NAMA_APK"
rm -f "$B/tanpa-dex.apk" "$B/rata.apk" "$B/res.zip"

echo
echo "APK siap: $B/$NAMA_APK ($(du -h "$B/$NAMA_APK" | cut -f1), versi $VERSI_NAMA, versionCode $VERSI_KODE)"
