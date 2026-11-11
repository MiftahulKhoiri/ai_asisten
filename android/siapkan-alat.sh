#!/usr/bin/env bash
# siapkan-alat.sh - unduh alat build APK ke ~/android-tools TANPA sudo dan tanpa Android Studio.
#   aapt2 + zipalign : paket Debian arm64 (diekstrak lokal, bukan dipasang)
#   android.jar      : platform Android 34 dari Google (aapt2 Debian belum bisa membaca versi 35)
#   d8 + apksigner   : build-tools 35.0.1 dari Google (berkas .jar, jalan di Java mana pun)
# Cukup sekali. Butuh: java/javac (JDK 17+), curl, unzip, apt-get (Debian / Raspberry Pi OS arm64).
set -euo pipefail

ALAT="${ANDROID_TOOLS:-$HOME/android-tools}"
mkdir -p "$ALAT/deb" "$ALAT/sdk"
cd "$ALAT"

echo "== 1/3 aapt2 + zipalign (paket Debian, diekstrak ke $ALAT/root)"
cd deb
paket=$(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks \
        --no-replaces --no-enhances aapt zipalign | grep -E '^[a-z0-9]' | sort -u)
perlu=""
for p in $paket; do dpkg -s "$p" >/dev/null 2>&1 || perlu="$perlu $p"; done
[ -n "$perlu" ] && apt-get download $perlu
for d in *.deb; do dpkg-deb -x "$d" ../root; done
cd ..

echo "== 2/3 android.jar (platform 34)"
[ -f platform-34-ext7_r03.zip ] || curl -fL --retry 3 -o platform-34-ext7_r03.zip \
    https://dl.google.com/android/repository/platform-34-ext7_r03.zip
echo "== 3/3 d8 + apksigner (build-tools 35.0.1)"
[ -f build-tools_r35.0.1_linux.zip ] || curl -fL --retry 3 -o build-tools_r35.0.1_linux.zip \
    https://dl.google.com/android/repository/build-tools_r35.0.1_linux.zip
unzip -q -o platform-34-ext7_r03.zip -d sdk34
unzip -q -o build-tools_r35.0.1_linux.zip -d sdk

echo
echo "Selesai. Isi penting:"
find "$ALAT/root" "$ALAT/sdk" "$ALAT/sdk34" \( -name aapt2 -o -name zipalign -o -name android.jar \
     -o -name d8.jar -o -name apksigner.jar \) -type f -not -path '*/share/*'
