# AGENTS.md — working in Unwritten Craft

Unwritten Craft keeps a craft's corrections: film one ordinary lesson,
then the pipeline transcribes it, drafts a write-up in the mentor's
words, and cuts the correction moments into clips. One app on three
platforms (web, Android, iOS) opens on the hub sessions with Record
and Upload above them; uploads ride the take path into the pipeline.

New machine? Read `docs/SETUP.md` first — secrets map, builds,
service, cron. Then come back here.

## Layout

| Path | What it is |
|---|---|
| `app/recorder/` | Single-file web app (`index.html`); `build.sh` stamps a token into `dist/` (git-ignored, never edit — rebuild) |
| `app/android/` | Native app, no Gradle daemon needed (`build.sh`: javac + d8 + CMake/NDK); base device Pixel 4, minSdk 29 |
| `app/ios/` | SwiftUI app; `build.sh` needs Xcode (Mac only). Without it: contract tests only, say so |
| `app/cloud-signer/` | Cloudflare Worker: Stream signing proxy + hub API (D1). `hub-check.mjs` is its test suite |
| `pipeline/` | Transcribe → write-up → corrections → clips; `--cloud` pulls finished Stream lessons |
| `prompts/` | Write-up rules + correction definition (live); apprentice files are retired |
| `harness/`, `samples/` | Retired experiments / fictional fixtures (no real mentor data anywhere) |
| `tests/` | unittest suite, mostly source-contract tests (assert on code, not just behavior) |
| `run_cloud.sh`, `setup.sh` | Cron runner (pipeline + publish + site) / machine bootstrap |
| `CHANGELOG.md` | Every commit to `main` adds its entry, same commit |

## First commands

```sh
bash setup.sh                                        # bootstrap + full suite
.venv/bin/python -m unittest discover -s tests       # the gate: must stay green
node app/cloud-signer/hub-check.mjs                  # service gate
bash app/recorder/build.sh && bash app/android/build.sh   # rebuild after app edits
```

## Conventions (repo law)

- **Test-first, durable tests.** Bug fix or behavior change = failing
  test in `tests/` first, minimal fix, focused pass, then the broad
  run. Match the file's existing style (many tests assert regions of
  the source under test).
- **Never weaken a red test to go green.** A failing test is the
  contract; only a user-ordered behavior change rewrites it, and then
  it says so in a comment.
- **CHANGELOG.md grows with every commit**, same commit, newest first.
- **Tokens are never printed or committed.** `tokens.txt`,
  `.env`, `debug.keystore`, `.certs/`, `dist/`, `build-manual/`,
  `work/` are all git-ignored — keep it that way. Builds log only
  `token #N of 10`; templates must carry `""` afterwards.
- **Fail fast, never silently stuck.** Retries with backoff, timeouts
  that surface a retry action, errors that name the fix (which
  setting, which file). A degraded state must show as degraded.
- **Leave the repo in sync.** Any change updates everything related:
  sibling platforms (web, Android, and iOS move together), generated
  outputs (rebuild `dist/` and the APK — never hand-edit them), the
  docs and comments that describe the old behavior, and the contract
  tests. A finished change leaves no stale reference behind; grep is
  part of done.
- **Shell is dash by default**: no `source`, no `<(...)` — use
  `. ./.env` and explicit `shell: /bin/bash` when needed.
- **Verify what you claim, where you claim it.** `javac` for Android
  edits (see `build.sh` for flags), `node --check` for page JS,
  real `adb install` + launch for APKs, on-device build for Swift.
  "No Xcode on this host" is an honest result, not a gap to fill
  with guessing.

## Gotchas

- Wireless-`adb` addresses rotate (`No route to host` = re-check the
  phone, don't retry blindly). The reference device is a Pixel 4.
- `work/`, `dist/`, `build-manual/` are generated: rebuild, don't
  hand-edit. `cloud_state.json` results: `done` never reprocesses,
  `failed` retries only with `--retry-failed`, `ignored` never comes
  back (operator set-aside for non-lessons).
- The pipeline refuses to draft from near-empty transcripts — that is
  the validator working, not a bug to fix.
- Dated docs (`docs/*-2026-10-2*`, worklogs) are history: read, don't
  rewrite. Live docs are `README.md`, `docs/SETUP.md`,
  `docs/PIPELINE.md`, `docs/DEVICES.md`, and the app READMEs.
- Continuing native work? Read `docs/android-app-worklog.md` /
  `docs/ios-app-worklog.md` first — build routes, device evidence,
  open items (icon, release signing, on-device shakeout).
