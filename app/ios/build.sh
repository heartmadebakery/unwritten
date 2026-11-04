#!/usr/bin/env bash
# Build the Unwritten Craft iOS app and verify the bundle.
#
# Like the Android and web builds, this stamps one random token from the
# signer pool into the app (CloudConfig.swift) before compiling, then
# restores the template — so the committed file NEVER carries a real
# token. Default is a simulator build (no paid developer account, no
# device needed); pass DEVELOPMENT_TEAM=<id> for a signed real-iPhone
# build instead; add TESTFLIGHT=1 to archive a Release build and upload
# it to App Store Connect for TestFlight (the iOS install link). Every
# path stamps, so installs never need hand-pasted credentials.
#
# On a dev machine with a team, open UnwrittenRecorder.xcodeproj in
# Xcode to run on a real iPhone.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/build"

command -v xcodebuild >/dev/null || { echo "xcodebuild not found — install Xcode"; exit 1; }

echo "== stamp (signer token) =="
POOL="$HERE/../cloud-signer/tokens.txt"
[ -f "$POOL" ] || { echo "Missing $POOL — run: bash ../cloud-signer/mint-tokens.sh" >&2; exit 1; }
CFG="$HERE/UnwrittenRecorder/CloudConfig.swift"
CFG_BAK="$HERE/CloudConfig.swift.template"
cp "$CFG" "$CFG_BAK"
restore_cfg() { cp "$CFG_BAK" "$CFG"; rm -f "$CFG_BAK"; }
trap restore_cfg EXIT
python3 - "$POOL" "$CFG" <<'EOF'
import random, sys
pool, target = sys.argv[1], sys.argv[2]
tokens = [t.strip() for t in open(pool) if t.strip()]
assert len(tokens) >= 1, "token pool is empty"
i = random.randrange(len(tokens))
src = open(target).read()
old = 'static let CLOUD_SIGNER_TOKEN_DEFAULT = ""'
assert old in src, "CloudConfig.swift is NOT the template (a previous build may have died mid-stamp and left a real token in it — inspect before proceeding)"
open(target, "w").write(src.replace(old, 'static let CLOUD_SIGNER_TOKEN_DEFAULT = "%s"' % tokens[i], 1))
print("stamped token #%d of %d into CloudConfig.swift (restored after build)" % (i + 1, len(tokens)))
EOF

if [ -n "${TESTFLIGHT:-}" ]; then
# TestFlight: the iOS twin of the Android APK link. Archive a stamped
# Release build and upload it to App Store Connect with the Mac's
# Xcode account; testers install from the TestFlight public link.
[ -n "${DEVELOPMENT_TEAM:-}" ] || { echo "TESTFLIGHT=1 needs DEVELOPMENT_TEAM=<team id> (Xcode → Settings → Accounts)" >&2; exit 1; }
BUILD_NUMBER="$(date -u +%Y%m%d%H%M)"
echo "== archive (Release, team $DEVELOPMENT_TEAM, build $BUILD_NUMBER) =="
rm -rf "$OUT/testflight" && mkdir -p "$OUT/testflight"
xcodebuild archive \
  -project "$HERE/UnwrittenRecorder.xcodeproj" \
  -scheme UnwrittenRecorder \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -archivePath "$OUT/testflight/UnwrittenRecorder.xcarchive" \
  -derivedDataPath "$OUT/testflight/DerivedData" \
  DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM" \
  CURRENT_PROJECT_VERSION="$BUILD_NUMBER" \
  -allowProvisioningUpdates
cat > "$OUT/testflight/ExportOptions.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>teamID</key><string>$DEVELOPMENT_TEAM</string>
  <key>signingStyle</key><string>automatic</string>
  <key>manageAppVersionAndBuildNumber</key><false/>
</dict></plist>
PLIST
echo "== upload to App Store Connect (TestFlight) =="
# Upload auth: an App Store Connect API key when ASC_KEY_ID,
# ASC_ISSUER_ID and ASC_KEY_PATH are set (keep the .p8 in the
# git-ignored .certs/), else the Mac's Xcode account.
AUTH=""
if [ -n "${ASC_KEY_ID:-}" ]; then
  [ -n "${ASC_ISSUER_ID:-}" ] && [ -f "${ASC_KEY_PATH:-}" ] || { echo "ASC_KEY_ID set: also set ASC_ISSUER_ID and ASC_KEY_PATH (the AuthKey .p8 file)" >&2; exit 1; }
  AUTH="-authenticationKeyPath $ASC_KEY_PATH -authenticationKeyID $ASC_KEY_ID -authenticationKeyIssuerID $ASC_ISSUER_ID"
fi
# shellcheck disable=SC2086
xcodebuild -exportArchive \
  -archivePath "$OUT/testflight/UnwrittenRecorder.xcarchive" \
  -exportOptionsPlist "$OUT/testflight/ExportOptions.plist" \
  -exportPath "$OUT/testflight/export" \
  -allowProvisioningUpdates $AUTH \
  || { echo "Upload failed (error above). 'Failed to Use Accounts' = no App Store Connect access: re-add the account in Xcode → Settings → Accounts, or set ASC_KEY_ID/ASC_ISSUER_ID/ASC_KEY_PATH (App Store Connect → Users and Access → Integrations → Keys). 'App record ... not found' = create it once: App Store Connect → Apps → + → New App, bundle ID com.heartmadebakery.unwritten." >&2; exit 1; }
echo "Uploaded build $BUILD_NUMBER — it shows in App Store Connect → TestFlight once processed."
exit 0
elif [ -n "${DEVELOPMENT_TEAM:-}" ]; then
echo "== build (xcodebuild, device, team $DEVELOPMENT_TEAM) =="
rm -rf "$OUT"
xcodebuild \
  -project "$HERE/UnwrittenRecorder.xcodeproj" \
  -scheme UnwrittenRecorder \
  -configuration Debug \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$OUT/DerivedData" \
  DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM" \
  -allowProvisioningUpdates \
  build
else
echo "== build (xcodebuild, simulator) =="
rm -rf "$OUT"
xcodebuild \
  -project "$HERE/UnwrittenRecorder.xcodeproj" \
  -scheme UnwrittenRecorder \
  -configuration Release \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$OUT/DerivedData" \
  CODE_SIGNING_ALLOWED=NO \
  build
fi

APP="$(find "$OUT/DerivedData" -name 'UnwrittenRecorder.app' -maxdepth 5 | head -1)"
[ -n "$APP" ] || { echo "Build produced no .app bundle"; exit 1; }
echo "APP: $APP"
ls -la "$APP/UnwrittenRecorder"
file "$APP/UnwrittenRecorder" | head -1
# uwcore must be linked in. (nm's symtab count is unreliable — Debug
# strips it — so check the link list instead.)
LINKLIST="$(find "$OUT/DerivedData" -name '*.LinkFileList' | head -1)"
[ -n "$LINKLIST" ] || { echo "no LinkFileList found"; exit 1; }
grep -q "uwcore_luma" "$LINKLIST" || { echo "uwcore_luma not linked into binary"; exit 1; }
echo "uwcore_luma linked (via $LINKLIST)"

echo "== template check =="
grep -q 'CLOUD_SIGNER_TOKEN_DEFAULT = ""' "$CFG_BAK" && echo "CloudConfig.swift template intact (no token committed)"
