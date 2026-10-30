---
name: cleanup
description: Reclaim disk by removing session-built pipeline outputs, proof dirs, and model caches while keeping credentials and the dev environment.
---

# Session Cleanup

Use when the user asks to clean up, reclaim disk space, or remove
session-built artifacts from this machine.

## Remove (all regenerable)

- `~/uw-cloud` — downloaded lessons plus processed work dirs. A future
  `pipeline/run_pipeline.py --cloud` run re-downloads and rebuilds them
  (its `cloud_state.json` goes with it, so a rerun reprocesses all).
- `/tmp/uw-*` — test runs, proof dirs (`uw-cloud-test`, `uw-site`,
  `uw-highlight-proof`, `uw-local-proof`, `uw-measure`, `uw-pip-cache`,
  `uw-poster-proof`, `uw-schema-proof`). List first; remove each.
- `/tmp/rec*.js` — throwaway `node --check` snippets.
- Orphaned large `$TMPDIR/tmp*` entries: inspect before touching —
  show mtime and top contents with `du`, confirm no process holds
  the files (`lsof`), and only remove ones dated from this session's
  work (Python `TemporaryDirectory` debris such as an abandoned
  `v.mp4`). Never remove temp dirs that predate the session.
- `~/.cache/huggingface` — Whisper models for the local-transcription
  fallback. The Meta API path is the default now; the local path
  re-downloads models on demand if ever used.

## Always keep

- Credentials and environment: `.env`, `app/cloud-signer/tokens.txt`,
  the repo itself, and `.venv` (reinstalling is slow).
- Build outputs still served: `app/recorder/dist/`.
- Other tools' caches (`~/.cache/claude`, `~/.cache/codex-runtimes`,
  `~/.cache/gh`) and other projects' DerivedData.
- Untracked files of unknown authorship (e.g. a stray `lesson1/`):
  report them with a removal command for the user; never delete what
  this session did not create.

## Procedure

1. Inventory first: `du -sh` every candidate and report sizes, so the
   user sees what goes and what stays.
2. `rm -rf` only the exact verified paths — no broad wildcards near
   user data.
3. Verify: candidates gone, `~/.cache` re-measured, `git status`
   unchanged apart from already-known untracked files.
4. Report freed space, what was kept and why, and anything left for
   the user to decide.
