#!/usr/bin/env bash
# Build the Unwritten Recorder APK without Gradle — plain SDK tools.
#
# Why: the app has zero dependencies, so the whole build is javac +
# aapt2 + d8 + CMake/NDK + apksigner. This script works fully offline
# (CI sandboxes where Gradle's daemon/proxy stack can't run) and on any
# machine with a JDK 17, an Android SDK (platform 34, build-tools 34)
# and NDK r26. On a normal dev machine, Android Studio / the Gradle
# files in this directory also work.
#
# Env overrides: JAVA_HOME, ANDROID_HOME (or ANDROID_SDK_ROOT),
# ANDROID_NDK_HOME, BUILD_TYPE=release (default debug-signed).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/app"
SDK="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}"
NDK="${ANDROID_NDK_HOME:-$SDK/ndk/26.1.10909125}"
BT="$SDK/build-tools/34.0.0"
AJAR="$SDK/platforms/android-34/android.jar"
OUT="$HERE/build-manual"
MIN_API=29

command -v javac >/dev/null || { echo "javac not found — set JAVA_HOME (JDK 17)"; exit 1; }
[ -f "$AJAR" ] || { echo "android.jar missing at $AJAR"; exit 1; }
[ -d "$NDK" ] || { echo "NDK missing at $NDK"; exit 1; }
CMAKE="$(command -v cmake || echo "$SDK/cmake/3.22.1/bin/cmake")"
NINJA="$(command -v ninja || true)"
if [ -z "$NINJA" ]; then
  for host in linux-x86_64 darwin-x86_64; do
    if [ -x "$NDK/prebuilt/$host/bin/ninja" ]; then NINJA="$NDK/prebuilt/$host/bin/ninja"; break; fi
  done
fi
[ -n "$NINJA" ] || NINJA="$SDK/cmake/3.22.1/bin/ninja"
[ -x "$CMAKE" ] || { echo "cmake not found"; exit 1; }

rm -rf "$OUT"; mkdir -p "$OUT/gen" "$OUT/classes" "$OUT/dex" "$OUT/lib"

echo "== native (CMake/NDK) =="
for ABI in arm64-v8a; do
  "$CMAKE" -S "$APP/src/main/cpp" -B "$OUT/cpp-$ABI" -G Ninja \
    -DCMAKE_MAKE_PROGRAM="$NINJA" \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$ABI" -DANDROID_PLATFORM="android-$MIN_API" \
    -DCMAKE_BUILD_TYPE=Release > /dev/null
  "$CMAKE" --build "$OUT/cpp-$ABI" > /dev/null
  mkdir -p "$OUT/lib/$ABI"
  cp "$OUT/cpp-$ABI/libuwcore.so" "$OUT/lib/$ABI/"
  echo "  $ABI libuwcore.so"
done

echo "== resources (aapt2) =="
"$BT/aapt2" link -o "$OUT/base.apk" -I "$AJAR" \
  --manifest "$APP/src/main/AndroidManifest.xml" \
  --java "$OUT/gen" --min-sdk-version "$MIN_API" --target-sdk-version 34

echo "== stamp (signer token) =="
POOL="$HERE/../cloud-signer/tokens.txt"
[ -f "$POOL" ] || { echo "Missing $POOL — run: bash ../cloud-signer/mint-tokens.sh" >&2; exit 1; }
CFG="$APP/src/main/java/org/tinio/unwritten/CloudConfig.java"
CFG_BAK="$OUT/CloudConfig.java.template"
cp "$CFG" "$CFG_BAK"
restore_cfg() { cp "$CFG_BAK" "$CFG"; }
trap restore_cfg EXIT
python3 - "$POOL" "$CFG" <<'EOF'
import random, sys
pool, target = sys.argv[1], sys.argv[2]
tokens = [t.strip() for t in open(pool) if t.strip()]
assert len(tokens) >= 1, "token pool is empty"
i = random.randrange(len(tokens))
src = open(target).read()
old = 'public static final String CLOUD_SIGNER_TOKEN_DEFAULT = "";'
assert old in src, "CloudConfig.java is NOT the template (a previous build may have died mid-stamp and left a real token in it — inspect before proceeding)"
open(target, "w").write(src.replace(old, 'public static final String CLOUD_SIGNER_TOKEN_DEFAULT = "%s";' % tokens[i], 1))
print("stamped token #%d of %d into CloudConfig.java (restored after build)" % (i + 1, len(tokens)))
EOF

echo "== java (javac) =="
find "$APP/src/main/java" "$OUT/gen" -name '*.java' > "$OUT/sources.txt"
JAVAC_LOG="$OUT/javac.log"
if ! javac -source 8 -target 8 -encoding UTF-8 -cp "$AJAR" \
  -d "$OUT/classes" @"$OUT/sources.txt" > "$JAVAC_LOG" 2>&1; then
  grep -v "bootstrap class path" "$JAVAC_LOG" || true
  echo "javac failed — see $JAVAC_LOG"; exit 1
fi

echo "== dex (d8) =="
(cd "$OUT/classes" && find . -name '*.class' > "$OUT/classlist.txt")
"$BT/d8" --lib "$AJAR" --min-api "$MIN_API" --output "$OUT/dex" \
  $(cd "$OUT/classes" && find . -name '*.class' | sed 's|^|'"$OUT/classes"'/|')

echo "== package + sign =="
cp "$OUT/base.apk" "$OUT/unwritten-recorder.apk"
(cd "$OUT" && zip -q -j unwritten-recorder.apk dex/classes.dex)
(cd "$OUT" && zip -q -r unwritten-recorder.apk lib)
"$BT/zipalign" -f -p 4 "$OUT/unwritten-recorder.apk" "$OUT/unwritten-recorder-aligned.apk"
KS="$HERE/debug.keystore"
if [ ! -f "$KS" ]; then
  keytool -genkeypair -keystore "$KS" -storepass android -keypass android \
    -alias androiddebugkey -keyalg RSA -keysize 2048 -validity 10950 \
    -dname "CN=Android Debug,O=Android,C=US" > /dev/null 2>&1
fi
"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android \
  --min-sdk-version "$MIN_API" \
  --out "$OUT/unwritten-recorder-signed.apk" "$OUT/unwritten-recorder-aligned.apk"
"$BT/apksigner" verify "$OUT/unwritten-recorder-signed.apk"
cp "$OUT/unwritten-recorder-signed.apk" "$HERE/unwritten-recorder.apk"
echo "APK: $HERE/unwritten-recorder.apk"
"$BT/aapt2" dump badging "$HERE/unwritten-recorder.apk" | head -4
