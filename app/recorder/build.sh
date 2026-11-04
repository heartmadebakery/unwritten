#!/usr/bin/env bash
# Build the servable web app into dist/ (gitignored): copies the pages,
# style, and scripts, and stamps ONE random token from the signer pool
# (app/cloud-signer/tokens.txt) into CLOUD_SIGNER_TOKEN_DEFAULT in
# common.js, so the served pages upload without anyone typing a URL
# or token. Prints only the pool slot ("token #N of 10"), never the
# token value.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
POOL="$HERE/../cloud-signer/tokens.txt"
[ -f "$POOL" ] || { echo "Missing $POOL — run: bash ../cloud-signer/mint-tokens.sh" >&2; exit 1; }
rm -rf "$HERE/dist" && mkdir -p "$HERE/dist"
cp "$HERE/index.html" "$HERE/record.html" "$HERE/upload.html" "$HERE/app.css" \
  "$HERE/common.js" "$HERE/home.js" "$HERE/record.js" "$HERE/upload.js" \
  "$HERE/manifest.webmanifest" "$HERE/sw.js" "$HERE/dist/"
# The home page footer links the Android dev build: ship the prebuilt
# debug-signed APK beside the pages so the link resolves on the served
# site (missing APK fails here, naming it, instead of shipping a 404).
cp "$HERE/../android/unwritten-craft.apk" "$HERE/dist/"
[ -d "$HERE/icons" ] && cp -r "$HERE/icons" "$HERE/dist/"
python3 - "$POOL" "$HERE/dist/common.js" <<'EOF'
import random, sys
pool, target = sys.argv[1], sys.argv[2]
tokens = [t.strip() for t in open(pool) if t.strip()]
assert len(tokens) >= 1, "token pool is empty"
i = random.randrange(len(tokens))
src = open(target).read()
old = 'var CLOUD_SIGNER_TOKEN_DEFAULT = "";'
assert old in src, "token placeholder missing from common.js"
open(target, "w").write(src.replace(old, 'var CLOUD_SIGNER_TOKEN_DEFAULT = "%s";' % tokens[i], 1))
print("stamped token #%d of %d into dist/common.js" % (i + 1, len(tokens)))
EOF
echo "Serve with:  .venv/bin/python -m http.server 8765 --directory app/recorder/dist"
