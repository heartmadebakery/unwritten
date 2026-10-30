#!/usr/bin/env bash
set -euo pipefail
cd /home/aurelio/unwritten
set -a; source .env 2>/dev/null || true; set +a
export PATH="$HOME/.local/bin:$PATH"
LOG="$HOME/unwritten/work/cloud/cron.log"
mkdir -p "$(dirname "$LOG")"
(
  flock -n 9 || exit 0
  .venv/bin/python pipeline/run_pipeline.py --cloud work/cloud >>"$LOG" 2>&1 || true
  # Rebuild site so new sessions appear immediately
  # Publish finished work dirs to the hub (idempotent upsert; needs signer token)
  HUB_SIGNER_URL="${HUB_SIGNER_URL:-https://unwritten-cloud-signer.heartmade.workers.dev}"
  HUB_SIGNER_TOKEN="${HUB_SIGNER_TOKEN:-$(head -1 app/cloud-signer/tokens.txt 2>/dev/null || echo "")}"
  if [ -n "$HUB_SIGNER_TOKEN" ]; then
    for work in work/cloud/*__*; do
      [ -f "$work/writeup.md" ] || continue
      .venv/bin/python pipeline/publish.py --work "$work" --state work/cloud/cloud_state.json --signer "$HUB_SIGNER_URL" --token "$HUB_SIGNER_TOKEN" >>"$LOG" 2>&1 || true
    done
  fi
  .venv/bin/python pipeline/make_site.py work/cloud work/site >>"$LOG" 2>&1 || true
  if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 2000 ]; then
    tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
) 9>/tmp/unwritten-cloud.lock
