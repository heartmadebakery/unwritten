#!/usr/bin/env bash
set -euo pipefail
# Runs from its own checkout, wherever the repo is cloned (cron:
# `cd /home/<you>/unwritten && bash run_cloud.sh`, see docs/SETUP.md).
cd "$(dirname "$0")"
set -a; source .env 2>/dev/null || true; set +a
export PATH="$HOME/.local/bin:$PATH"
LOG="$PWD/work/cloud/cron.log"
mkdir -p "$(dirname "$LOG")"
(
  flock -n 9 || { echo "[cloud] $(date '+%F %T'): previous run still holds the lock — skipping" >>"$LOG"; exit 0; }
  FAIL=0
  # Queued URL jobs first (YouTube/watch links from the apps), when the
  # queue is configured; --fetch exits 0 with no jobs pending.
  if [ -n "${FETCH_QUEUE_URL:-${CLOUD_PROXY_URL:-}}" ]; then
    .venv/bin/python pipeline/run_pipeline.py --fetch work/cloud >>"$LOG" 2>&1 || { echo "[cloud] FAIL: fetch step failed (see above)" >>"$LOG"; FAIL=1; }
  fi
  .venv/bin/python pipeline/run_pipeline.py --cloud work/cloud >>"$LOG" 2>&1 || { echo "[cloud] FAIL: pipeline step failed (see above)" >>"$LOG"; FAIL=1; }
  # Rebuild site so new sessions appear immediately
  # Publish finished work dirs to the hub (needs the signer token).
  # --if-changed posts a session only when its artifacts changed:
  # re-posting each cycle resurrected hub deletes made in the apps.
  HUB_SIGNER_URL="${HUB_SIGNER_URL:-https://unwritten-cloud-signer.heartmade.workers.dev}"
  HUB_SIGNER_TOKEN="${HUB_SIGNER_TOKEN:-$(head -1 app/cloud-signer/tokens.txt 2>/dev/null || echo "")}"
  if [ -n "$HUB_SIGNER_TOKEN" ]; then
    shopt -s nullglob
    for work in work/cloud/*__*; do
      [ -f "$work/writeup.md" ] && [ -f "$work/corrections.json" ] || continue
      # Fetch-queue sessions finish here with a writeup but map to no
      # cloud video, and publish.py only publishes Stream-backed
      # lessons — resolve the guid first and skip those dirs, or every
      # cron run would end FAIL on them.
      GUID="$(.venv/bin/python -c 'import json,os,sys; st=json.load(open("work/cloud/cloud_state.json")); w=os.path.abspath(sys.argv[1]); print(next((g for g,e in st.items() if isinstance(e,dict) and os.path.abspath(e.get("workDir",""))==w),""))' "$work" 2>/dev/null || true)"
      [ -n "$GUID" ] || continue
      .venv/bin/python pipeline/publish.py --work "$work" --guid "$GUID" --state work/cloud/cloud_state.json --signer "$HUB_SIGNER_URL" --token "$HUB_SIGNER_TOKEN" --if-changed >>"$LOG" 2>&1 || { echo "[cloud] FAIL: publish $work failed (see above)" >>"$LOG"; FAIL=1; }
    done
    # Sync operator set-asides so the apps badge them on Record (the
    # hub sessions list excludes them server-side).
    .venv/bin/python pipeline/publish.py --sync-ignored --state work/cloud/cloud_state.json --signer "$HUB_SIGNER_URL" --token "$HUB_SIGNER_TOKEN" >>"$LOG" 2>&1 || { echo "[cloud] FAIL: ignored sync failed (see above)" >>"$LOG"; FAIL=1; }
  fi
  .venv/bin/python pipeline/make_site.py work/cloud work/site >>"$LOG" 2>&1 || { echo "[cloud] FAIL: site rebuild failed (see above)" >>"$LOG"; FAIL=1; }
  if [ "$(wc -l < "$LOG" 2>/dev/null || echo 0)" -gt 2000 ]; then
    tail -n 1000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  fi
  # Non-zero on any failure so cron can alert (MAILTO); every failure
  # is also greppable as "[cloud] FAIL" in the log.
  if [ "$FAIL" -ne 0 ]; then
    echo "[cloud] FAIL: cloud run finished with failures" >>"$LOG"
    exit 1
  fi
) 9>/tmp/unwritten-cloud.lock
