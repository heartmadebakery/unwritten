#!/usr/bin/env bash
# Mint a pool of 10 random signer tokens (one per line) into tokens.txt.
# tokens.txt is gitignored: it never gets committed. Back it up — it is
# the only record of which token (#1..#10) each build carries, and you
# need it to revoke a single build's token later.
# Token values are NEVER printed; only the joined secret is piped.
set -euo pipefail
cd "$(dirname "$0")"
if [ -f tokens.txt ]; then
  echo "tokens.txt already exists — refusing to overwrite." >&2
  echo "Delete it first if you really want a fresh pool (this orphans" >&2
  echo "every build stamped from the old pool)." >&2
  exit 1
fi
python3 -c "import secrets; print('\n'.join(secrets.token_urlsafe(24) for _ in range(10)))" > tokens.txt
chmod 600 tokens.txt
echo "Minted 10 tokens into tokens.txt (lines = token #1..#10)."
echo "Next: set them on the worker WITHOUT printing them:"
echo "  paste -sd, tokens.txt | npx wrangler secret put SIGNER_TOKENS"
