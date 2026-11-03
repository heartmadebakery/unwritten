# Setup — new machine, from zero to running

Gets a brand-new computer (Ubuntu/WSL2 or macOS) from clone to a
verified repo, working builds, and a running pipeline + service. For
agents: read `AGENTS.md` at the repo root first, then come back here.

## 0. Clone and bootstrap

```sh
git clone git@github.com:tinio/unwritten.git && cd unwritten
bash setup.sh
```

`setup.sh` is idempotent and needs no sudo. It installs: `uv` (if
missing) → `.venv` (Python 3.12) → `requirements.txt` (+ the retired
torch file, harmless) → static `ffmpeg`/`ffprobe` into `~/.local/bin`
when missing (amd64 or arm64 Linux; on macOS it stops and asks for
`brew install ffmpeg`) → the SAM checkpoint into `pipeline/models/`
(git-ignored, 375 MB; an interrupted download is retried, never kept).
It ends by running the full test suite — no secrets needed for that;
green here means the tree is good before you touch any credential.

You also need, not installed by the script:

- **Node 20+** (`node -v`) — for `wrangler` (service deploys) and
  `hub-check.mjs` (service tests). Any install works; `npx` must run.
- **A C++ toolchain + CMake + Ninja** — only for the Android native
  lib (see step 5). Skip until then.
- **Xcode** — only on the Mac that builds iOS (see step 5).

## 1. Secrets: what goes where

Nothing secret is ever committed. Every secret lives in exactly one
of these places:

| Secret | Lives in | Get / set it with |
|---|---|---|
| `MODEL_API_KEY` (Meta Model API) | `.env` at repo root (git-ignored, `export KEY=value` lines) | Paste your key. Without it the pipeline falls back to local faster-whisper transcription and the keyless `muse`-runner drafting path — slower, fully offline-capable. |
| `CLOUD_LIBRARY_ID`, `CLOUD_LIBRARY_KEY`, `CLOUD_CDN_HOSTNAME` | `.env` | Stream dashboard → your library → API page. `KEY` may be omitted when `CLOUD_PROXY_URL` is set (listing goes through the signer instead) — except `--fetch`, which needs the key to upload finished lessons. |
| `CLOUD_PROXY_URL` (optional) | `.env` | The signer worker URL (below). Lets the pipeline list the library without holding the library key. |
| `FETCH_QUEUE_URL`, `FETCH_QUEUE_TOKEN` (optional) | `.env` | Fetch-queue worker URL (falls back to `CLOUD_PROXY_URL`); token falls back to `CLOUD_PROXY_TOKEN`, then line 1 of `tokens.txt`. |
| `HUB_SIGNER_URL`, `HUB_SIGNER_TOKEN` (optional) | `.env`, or `run_cloud.sh` defaults | Publish target; the token defaults to line 1 of `tokens.txt`. |
| `UNWRITTEN_TRANSCRIBE`, `UNWRITTEN_WHISPER_MODEL`, `UNWRITTEN_ASR_KEYWORDS`, `UNWRITTEN_ASR_LANGUAGES`, `MUSE_BIN` (all optional) | `.env` / environment | Transcription backend + hints; `muse` CLI override (default: `muse` on `PATH`, else `~/.local/bin/muse`). |
| Signer token pool, 10 lines | `app/cloud-signer/tokens.txt` (git-ignored, `chmod 600`) | **Either** copy the existing file over securely (preferred — keeps every shipped build valid), **or** mint a fresh pool: `bash app/cloud-signer/mint-tokens.sh`, then set it on the worker (step 3). Never print a token; builds log only `token #N of 10`. |
| `CLOUD_API_KEY`, `SIGNER_TOKENS` | Cloudflare Worker secrets (never a file) | `npx wrangler secret put CLOUD_API_KEY`, and `paste -sd, tokens.txt \| npx wrangler secret put SIGNER_TOKENS` (comma-joins without printing). |
| Worker D1 binding | `wrangler.toml` (`database_id`, committed) | Reuse the existing worker: keep as is, but apply `migrations/0002_fetch_jobs.sql` (URL queue), `0003_ignored.sql` (ignored takes), and `0004_duration.sql` (session durations) + redeploy — the hub list reads `ignored_videos` and `duration_seconds`, so a worker deployed without 0003/0004 answers 503 naming the file. Fresh worker: `npx wrangler d1 create unwritten-hub`, paste the printed id, apply `0001_sessions.sql`, `0002_fetch_jobs.sql`, `0003_ignored.sql`, and `0004_duration.sql`. Always `npx wrangler d1 execute unwritten-hub --remote --file migrations/<file>`: without `--remote`, Wrangler migrates a local dev copy and production never sees it. |
| Android signing | `app/android/debug.keystore` (auto-generated, git-ignored) | `build.sh` creates it on first run. Release signing is an open item. |
| LAN HTTPS certs | `.certs/` (git-ignored, `mkcert`) | Only for serving the web app to a phone camera (step 6). |

Copy order on a new machine: `.env` first (repo root), then
`tokens.txt`. Everything else generates or deploys.

## 2. Verify the tree (no secrets needed)

```sh
.venv/bin/python -m unittest discover -s tests   # ~490 tests, contract-only
node app/cloud-signer/hub-check.mjs              # 69 checks against a local D1
```

Both must be green before you build anything.

## 3. Service: reuse or deploy the signer

The apps and the pipeline proxy talk to one Cloudflare Worker
(default baked into all three apps):
`https://unwritten-cloud-signer.heartmade.workers.dev`.

- **Reuse it** (normal case): nothing to do. Confirm it's alive:
  `curl -s -o /dev/null -w "%{http_code}\n" <url>/hub/sessions`
  must print `401` (protected route refusing anonymously = healthy).
- **Deploy your own**: `cd app/cloud-signer`, `npx wrangler login`,
  create + migrate D1 (see `wrangler.toml` comments), set the two
  secrets from step 1, `npx wrangler deploy`. Then either update the
  `CLOUD_SIGNER_DEFAULT` baked into the three apps or override the
  signer URL in each app's Cloud settings.

## 4. Token pool

If you copied `tokens.txt` over, skip this. Otherwise:

```sh
bash app/cloud-signer/mint-tokens.sh
paste -sd, app/cloud-signer/tokens.txt | npx wrangler secret put SIGNER_TOKENS
```

Every build (web, Android, iOS) stamps one random pool slot into the
app and refuses to build without the pool. A fresh pool orphans builds
stamped from an old one — that is the point of the backup warning in
the mint script.

## 5. Builds (each stamps a token, each restores its template)

```sh
bash app/recorder/build.sh    # → app/recorder/dist/ (git-ignored), serve it
bash app/android/build.sh     # needs JDK 17, SDK platform + build-tools 34,
                              # NDK r26, cmake/ninja → unwritten-craft.apk
bash app/ios/build.sh         # needs Xcode (Mac only); simulator by default,
                              # DEVELOPMENT_TEAM=<id> for a real iPhone
```

Overrides: `JAVA_HOME`, `ANDROID_HOME` (or `ANDROID_SDK_ROOT`),
`ANDROID_NDK_HOME`, `BUILD_TYPE=release`. The Android script works
fully offline once the SDK exists (no Gradle daemon). After each
build, confirm its `CloudConfig` template still carries `""` — the
scripts check this themselves and fail loudly otherwise.

No Xcode on the machine (Linux CI, this dev box): iOS is
contract-test-only until a Mac builds it. Say so instead of claiming
it verified.

## 6. Run

```sh
# Web app (this host only):
.venv/bin/python -m http.server 8765 --directory app/recorder/dist
# Web app to a phone camera (camera APIs need https on LAN):
.venv/bin/python app/recorder/serve_https.py   # serves dist/ like the line above;
                                               # first: make .certs/ per its header,
                                               # install .certs/rootCA.pem on the phone

# Pipeline, one lesson:
.venv/bin/python pipeline/run_pipeline.py <session_dir> <work_dir>
# Pipeline, every new finished Cloud lesson + publish + site rebuild:
bash run_cloud.sh   # cron-friendly (flock), logs to work/cloud/cron.log

# Phone install (address rotates — re-check wireless debugging each time):
adb connect <phone-ip>:<port> && adb install -r app/android/unwritten-craft.apk
```

Suggested cron (every 5 minutes; failures land in
`work/cloud/cron.log` as `[cloud] FAIL`, and the exit code is
non-zero so `MAILTO` gets them where mail exists):

```cron
*/5 * * * * cd /home/<you>/unwritten && bash run_cloud.sh
```

On this host (BusyBox init + `crond`, no systemd) the schedule
lives in `/etc/crontabs/<you>` — note the file must be
**root-owned** (this `crond` silently ignores user-owned crontabs)
while jobs run as the file's name — and `crond` itself is kept up
by an inittab respawn line (`::respawn:/usr/sbin/crond -f -L
/var/log/crond.log`), so the service is back within 5 minutes of a
reboot with no `@reboot` support needed. Verify with
`pgrep -a crond` and a fresh timestamp on `work/cloud/cron.log`.

## 7. What "working" looks like

- Tests + hub-check green (step 2).
- All three builds succeed (step 5).
- `run_cloud.sh` processes any new Cloud videos; `work/site`
  rebuilds; the hub in each app lists published sessions.
- The Pixel 4 (reference device) installs and launches the APK with
  no crash; home shows the hub, Record opens the viewfinder.

If any of these fail on a fresh machine, the failure is the setup —
not the code — until proven otherwise: re-check this file top to
bottom before editing sources.
