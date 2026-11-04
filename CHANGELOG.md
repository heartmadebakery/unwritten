# Changelog

All notable changes to Unwritten Craft, newest first. Dates are
Pacific Time. **Rule: every commit to `main` adds its entry here, in
the same commit.** Entries cite the commit they describe; this file
was compiled retroactively on Oct 27, 2026 from the full commit
history (30 commits) and is maintained in the open from then on.

## 2026-11-04

### Added
- **iOS TestFlight build (the iOS twin of the APK link).** An iPhone
  cannot install a downloaded app, so `TESTFLIGHT=1
  DEVELOPMENT_TEAM=<id> app/ios/build.sh` archives a token-stamped
  Release build with a fresh UTC build number and uploads it to App
  Store Connect, signed in by an App Store Connect API key
  (`ASC_KEY_ID`/`ASC_ISSUER_ID`/`ASC_KEY_PATH`, `.p8` in the git-ignored
  `.certs/`) or the Mac's Xcode account; failures name the fix.
  Info.plist takes its versions from the build settings and declares
  `ITSAppUsesNonExemptEncryption` false (HTTPS only). Tests in
  `test_ios_testflight.py`. Archive verified; the upload waits on the
  one-time App Store Connect app record, and the web footer link on
  the TestFlight public URL.

### Changed
- **App identifier is `com.heartmadebakery.unwritten` everywhere.**
  (User-ordered: match the web app's home, unwritten.heartmadebakery.com,
  with no trace of the old prefix.) iOS bundle ID (Info.plist now reads
  `$(PRODUCT_BUNDLE_IDENTIFIER)`), Android applicationId, manifest
  package, Gradle namespace, Java package (sources moved to
  `java/com/heartmadebakery/unwritten/`), the 8 JNI symbols in
  `jni_bridge.cpp`, the file-provider authority, queue labels, tests,
  READMEs and worklogs. New guard
  `test_no_reference_to_the_old_identifier_anywhere` scans the repo for
  the old prefix in any spelling. Installs under the new ID are a new
  app on each device. Android not compiled on this host (no SDK): the
  committed APK still carries the old ID until it is rebuilt.

### Fixed
- **iOS build broken on `main` again.** The write-up screengrab strip
  put a regex in a plain Swift literal (`"!\[Step\s+\d+\]…"`), whose
  `\[`, `\s`, `\d` are invalid escapes; now a raw `#"…"#` string in
  `ContentView.swift`. New guard
  `test_plain_string_literals_use_only_swift_escapes` fails on any
  non-Swift escape in a plain literal. Signed device and Mac (Designed
  for iPad) builds succeed; 530 tests OK.

### Added
- **Hub write-ups render full markdown with step screengrabs.**
  (User-ordered: a proper write-up renderer that looks complete, with
  step screenshots that resolve in the hub.) *Web:* `renderMd` renders
  headings, paragraphs, lists, inline code, and images — everything
  escaped first, and only embedded `data:image` stills become `<img>`;
  anything else in an image slot is dropped. *Pipeline:* `publish.py`
  inlines each `stills/step-NN.jpg` into `writeupMd` as a data: URL at
  publish time (missing/oversized stills drop their line, never the
  step), so the hub stays one text field with no still host. A real
  640px still is ~28KB (~37KB base64), so even long write-ups add only
  hundreds of KB. Native apps keep their inline reading (still
  image-stripping) until the parity pass. Verified: renderer smoke
  (headings/lists/images/XSS/inline), publish embed tests, full suite.
- **Step screenshots display at half width.** (User-ordered: smaller
  images by default.) *Web / page:* step `<img>`s carry a `still`
  class capped at 50% width, each linking through to the full image.
  Verified: sizing-hook contract tests plus the full suite.
- **Home page footer links the Android dev build.** (User-ordered: share
  the APK in the web app at the bottom of the page so others can use
  the install for dev without adb or a checkout.) *Web:* a quiet footer
  link (`Android dev build (.apk)`) in the established bottom-link
  style; `build.sh` ships the prebuilt debug-signed APK into `dist/`
  beside the pages; the service worker leaves `.apk` downloads
  uncached so they never go stale. Verified: 3 new contract tests plus
  the full suite.
- **Each write-up step carries its screengrab.** (User-ordered: when
  creating the write-up include a corresponding appropriate screengrab
  from the video for the step being described.) *Pipeline:*
  `draft_writeup.py` cuts one JPEG per step (`stills/step-NN.jpg`,
  spread across the lesson in step order) and embeds
  `![Step N](stills/step-NN.jpg)` in `writeup.md`; transcript-only runs
  keep text only, failed cuts keep the step without its still — stills
  never block a run. Stale `stills/` clears with the run. *Page/site:*
  `make_page.py` renders each still under its step when the file
  exists. *Apps (web, Android, iOS):* the hub write-up strips step
  images (no still URLs in the hub) instead of showing raw markdown.
  Verified: focused still/page/strip tests plus the full suite.

### Changed
- **Cloud settings are read-only build values.** (User-ordered: a
  stale saved signer URL once broke every cloud request, so
  connection values load fresh from the stamped build on every load
  and nothing persists or overrides them.) *Web / Android / iOS:*
  signer URL and token come from the build constants; the direct
  library-key mode is gone (uploads always sign through the signer);
  the library id rides each lesson's own link row. Advanced settings
  (web) / Cloud settings (native) show the effective URL and token
  status for debugging, and every failure message names the rebuild
  instead of settings that no longer exist.
- **The upload screen lists previous upload/fetch attempts.**
  (User-ordered: the list is the indicator that an upload or fetch
  occurred, like the record page's session list.) *Web / Android /
  iOS:* the upload page/screen ends with previous uploads (session
  rows) and previous fetches (link attempts logged locally with URL,
  date and outcome, newest first, capped at 20).
- **Fetch from link moves into the upload page; the link page is
  gone.** (User-ordered: no separate fetch/link page — the fetch
  section sits after the upload section, history at the end.) *Web:*
  `link.html`/`link.js` are deleted and the shell and build ship only
  the upload page, which holds the picker, the link-fetch field and
  the attempts history. *Android / iOS:* the link screen and its
  routes are removed; the upload screen holds the fetch field after
  the upload section with previous attempts at the end.
- **Web app hosted on Cloudflare Pages.** (User-ordered: serve it
  from `unwritten.heartmadebakery.com`.) The static `dist/`
  deploys as the Pages project `unwritten` from this machine, so
  the token pool never leaves the host; the signer pins its CORS
  allowlist to the custom domain plus `localhost:8765` and
  reflects only listed origins. The custom-domain attach is one
  dashboard click (DNS + cert automatic); hub-check covers the
  allowlist.

## 2026-11-03

### Changed
- **Repo moved to `heartmadebakery/unwritten`.** `origin` and the
  clone line in `docs/SETUP.md` now point at the new organization;
  dated docs and worklogs keep the old name as history.
- **Nested-clone guard.** `.gitignore` no longer ignores a stray
  `unwritten/` folder, so an accidental clone inside the working tree
  shows up in `git status` instead of hiding.
- **Repo hygiene.** `.gitignore` now ignores `.venv-python/`, the
  Python 3.12 that `uv` downloads for `.venv` on hosts without one
  (`rm -rf .venv .venv-python` undoes the whole local setup).

### Added
- **Session parts: one session in several videos.** (User-ordered:
  record, upload, or fetch a video as the next part of a previous
  session, or tie several together so they read as one overall
  session.) *Signer:* `migrations/0005_parts.sql` (`session_parts`,
  `fetch_jobs.join_to`); `POST /hub/parts {videoIds}` ties videos onto
  the first one's session (merging whole sessions, order kept),
  `DELETE /hub/parts/<id>` unties (a lone part dissolves its session;
  hub delete unties too); `GET /hub/sessions` lists a tied session
  once with `partCount`, `pendingParts`, `groupId` and the summed
  length; `GET /hub/sessions/<any part>` answers the whole session
  (one write-up under "Part N" headings, corrections/chapters tagged
  with `part`, `parts` in order); `POST /fetch/jobs {url, joinTo}` and
  `done {videoId}` tie a fetched link on. *Pipeline:* `--fetch` closes
  jobs with the new Stream id; `source.json` records `join_to`.
  Each part is still processed on its own. *Apps (web, Android, iOS):*
  **Add a part** (Record / Upload / Link) on a hub session, an "Adds
  a part to …" note on the capture screens (*Make it its own
  session* backs out), takes tied as soon as their upload has an id
  (three tries, retried on resume, never silent), "Part of …" chips
  on device takes, **Tie a session to this one**, a Parts list (play
  one / Untie), Play running part to part, "Part N ·" chips, share of
  every part link, and a delete that names every part. Tests first:
  32 new hub checks (101 total), `tests/test_session_parts.py` (18),
  2 fetch-job tests; `test_one_job_runs_the_pipeline_and_finishes`
  now expects the `video_id` (commented as user-ordered). Verified:
  `node hub-check.mjs` 101/101; unittest 515/515 (with yt-dlp
  installed, as `setup.sh` does); web driven in
  Chromium (Playwright) against a mocked signer — hub detail, tie,
  link queue with `joinTo`, upload tie with a retried failure; Android
  `javac` clean against platform-34. **Not done here:** `dist/` and
  the APK not rebuilt (no token pool / SDK on this host), no iOS
  compile (no Xcode), no device runs, and `0005_parts.sql` is not yet
  applied to the live D1 — apply it before deploying this worker.
  Merged with `main`'s Swift-escape fix: the new `hubSubtitle` joins
  with `"\u{2022}"`, and `test_unicode_escapes_are_swift_style`
  passes over every new Swift line (516 tests).

### Fixed
- **iOS build broken on `main` (Xcode Cloud archive failed).** The hub
  subtitle's bullet was written Java-style (`"•"`), a Swift
  compile error the source-contract tests could not see; now
  `"\u{2022}"` in `SessionStore.swift`. New guard
  `test_unicode_escapes_are_swift_style` scans every Swift file.
  Verified with a Release `xcodebuild archive` for generic iOS from a
  clean clone (no token stamped, as Xcode Cloud builds it): archive
  succeeded, no compile warnings.

### Fixed
- **New-machine YouTube stall.** `fetch_jobs.load_config()` and `run_cloud.sh` now default the fetch queue to the baked signer `https://unwritten-cloud-signer.heartmade.workers.dev` so a fresh clone with no `.env` still processes queued YouTube links instead of silently skipping `--fetch`; `setup.sh` now scaffolds `.env` with `CLOUD_PROXY_URL`/`FETCH_QUEUE_URL` defaults and appends them non-destructively on re-run; `docs/SETUP.md` and `docs/PIPELINE.md` updated; contract tests added (`test_default_queue_is_baked_signer`, `test_fetch_runs_without_env_override`, `test_scaffolds_env_with_fetch_defaults`), kept green (495 tests, 69 hub checks).

### Fixed
- **Bug sweep: pipeline, hub, web, and docs.** Kept green (493 tests,
  69 hub checks): `draft_writeup.py`/`find_corrections.py` no longer
  crash with `UnboundLocalError` on muse timeout; `make_page.py` leak
  closed, `make_site.py` handles `SystemExit` per session, `ingest.py`
  tolerates unreadable files, `schemas.py` enforces
  `additionalProperties: false`; `cloud_fetch.py` remux no longer
  mislabels every ffmpeg failure as token-auth (now only on 403);
  `publish.py` reuses loaded state for duration; `worker.js`
  `MIGRATIONS` now covers `0004_duration.sql` and `failed()` handles
  `no such column` → 503, URL validation allows localhost/IP;
  `app/recorder/common.js` escapes `c.name` (XSS), `e.message` at 596,
  null-guards `hubplayer`/`hubclose`/`status`; `sw.js` wraps cache
  put in `waitUntil`; `run_cloud.sh` nullglob, `run_pipeline.py` no
  longer clobbers `PATH`; `docs/SETUP.md` lists all four migrations.
  `dist/` rebuilt (token #9/10). HLS remux test skips when local ffmpeg
  cannot handle HLS (static 7.0.2 segfault on this host).

### Fixed
- **Merge: Nov 2 bug sweep with the Hearth / link-screen / duration
  work.** Conflict fallout, kept green (493 unittest, 69 hub
  checks): the service worker is the same-origin network-first shell
  plus the link page at v12; the upload and link pages both say
  "saved" only once the vault write lands; `publish.py` uniquifies
  the title, then fingerprints, `--if-changed` skips, 404s skip, and
  the probed duration rides along; `wrangler.toml` lists 0001–0004
  all with `--remote`. `dist/` and the APK rebuilt from the merged
  sources on JDK 17 (device install still pending).

### Added
- **Hub: duration on home + unique titles via chapters.** Hub rows now show video duration to the right of date (`lessonDate • m:ss`, `h:mm:ss` when needed) on web (`app/recorder/common.js:hubRowHTML`), Android (`MainActivity.refreshHubRows`) and iOS (`SessionStore.hubSubtitle`/`ContentView`). `duration_seconds` column added via `app/cloud-signer/migrations/0004_duration.sql` (applied to live D1, `hub-check` updated); `worker.js` computes `durationSeconds` from `ffprobe` on publish and returns it in `GET /hub/sessions` list/detail; `pipeline/publish.py` probes the lesson file and sends `durationSeconds`; `pipeline/title_utils.py` ensures new hub titles stay unique via chapter summarization (distinctive chapter words, fallback date/increment) at first creation and the worker enforces it server-side for all new publishers. Prompt extended (`prompts/writeup_drafter.md`). Verified: republished 13 work dirs + fixed remaining "Yes" to "Yes — Core Concepts" (14/14 unique, durations 4s–506s live at `GET /hub/sessions`), `node app/cloud-signer/hub-check.mjs` PASS (60), `python -m unittest` 452 pass (1 pre-existing), `app/recorder/build.sh` token #10/10, `app/android/build.sh` APK ok, `npx wrangler deploy` live.

### Added
- **iOS: a real iPad app, portrait and landscape.** The target is now
  iPhone + iPad (`TARGETED_DEVICE_FAMILY = "1,2"`) with all four
  orientations on the iPad (`UISupportedInterfaceOrientations~ipad`);
  the iPhone stays portrait. On the iPad the viewfinder and the take
  follow the screen rotation (`PreviewUIView` -> `setInterfaceRotation`
  -> `captureAngle`, default 90 so the iPhone is unchanged). On wide
  screens every screen is a centered 760 pt column, the home title
  moves into it, and the viewfinder is taller. Contract tests first
  (`tests/test_ios_ipad.py`). Verified: Release simulator build and
  both orientations of home on the iPad Pro 13-inch simulator; the
  camera rotation itself is untested (the simulator has no camera) —
  film a landscape take on the iPad before relying on it.

### Changed
- **Upload video is a screen with two options; Fetch from link is its
  own screen; status lines stay on their screen.** Home is now just
  Record and Upload video above the hub — no paste-a-link card, no
  status footer. Upload video opens *Choose a video* (iOS: Photos or
  Files; Android: system picker; web: the file drop zone) and *Fetch
  from link*, which opens its own screen (web: new `link.html` /
  `link.js`, precached and shipped by `build.sh`, cache bumped to v12).
  The camera help ("Point the camera at the mentor's hands…") no longer
  boots into the iOS store's shared status: it is the Record screen's
  own line, and iOS clears the status on every navigation so one
  screen's message never follows you to another. Contract tests added
  first (`tests/test_upload_link_screens.py`); the old web link tests
  now read the link page. Verified: iOS Release simulator build and a
  walk through home → Upload → Fetch from link → Record on the iPhone
  17 Pro Max simulator; web JS `node --check`, `dist/` rebuilt. Android
  not compiled — no JDK 17 / Android SDK on this host (braces balance
  only); build it on a machine with the SDK before shipping.

### Changed
- **Repo hygiene: `.gitignore` covers Finder metadata and Xcode
  per-user state** (`.DS_Store`, `xcuserdata/`, `*.xcuserstate`,
  `DerivedData/`), and the stray nested clone beside the tree is
  ignored, so `git status` shows only real changes.
- **iOS: Xcode Cloud setup + Xcode's recommended project updates.**
  Adds `xcshareddata/xcodecloud/manifest.json` (Xcode Cloud product
  link), accepts Xcode 27.2's recommended build-setting updates
  (compiler warning flags, dead-code stripping, user-script
  sandboxing, whole-module Release) and bumps the scheme's
  `LastUpgradeVersion`. The personal `xcuserstate` stays untracked.
- **iOS: signing team set in the Xcode project.** Both build
  configurations now carry `DEVELOPMENT_TEAM`, so Xcode and
  `build.sh` produce a signed device build without passing the team
  by hand. First device build installed and launched on a paired
  iPhone (iPhone15,2) with `devicectl`. Xcode's own project rewrite
  (objectVersion downgrade) was discarded; only the two team lines
  are committed.

### Fixed
- **Android build: new value resources link, wrong JDK fails fast.**
  The first official-SDK build of the Hearth redesign failed twice:
  `aapt2 link` takes the app's resources as an overlay (`-R`), which
  may not add a resource the base lacks, so the new
  `values/colors.xml` was refused — the link step now passes
  `--auto-add-overlay`. And JDK 21's javac output crashes
  build-tools 34's `d8` (an NPE inside R8 on an anonymous class), so
  `build.sh` now honours `JAVA_HOME` and stops early on javac 18+,
  naming the JDK 17 fix. Two contract tests added first. With both
  fixes the full official route (CMake/NDK, aapt2, javac 17, d8,
  apksigner) builds and verifies here; the committed APK is not
  replaced, since no token pool is on this host to stamp it.

## 2026-11-02

### Fixed
- **Bug sweep, part 2: web, Android, and iOS**
  (user-ordered "fix all bugs"; every fix test-first; sibling
  platforms move together).
  - *Web:* the service worker served every GET cache-first —
    including the signer's API on other origins, so the hub list
    froze and upload status polls ended "taking too long"; and
    scripts lagged pages by a cache bump. Now same-origin only,
    network-first, offline deep links keep their page; cache v12 with the link page (v10/v11 dropped on activate). `dist/` rebuilt.
  - *Web, second pass:* `serve_https.py` serves the stamped `dist/`
    (phones got the tokenless source); the upload and link pages say "saved"
    only once the IndexedDB write lands (leaving earlier aborted
    it); the record page starts sessions that never got an upload
    link; and the ignored-badge fetch honors Cloud off — no
    network, as on Android (iOS too).
  - *Android:* camera-thread errors now reset the Record button on
    the UI thread (it stuck on "■ Stop"); the take being written is
    no longer a session row (blank duration for good, deletable or
    sweep-uploaded mid-take); picked uploads land atomically; `.mkv`
    uploads list; Export and the per-row copy move off the UI thread
    (ANR). A take that fails to start deletes the empty file
    MediaRecorder made, and an empty take is reported like on iOS
    and the web. APK rebuilt; device install pending (the Pixel 4's
    wireless-debugging port had rotated).
  - *iOS (contract-only, no Xcode here):* the remux exports to the
    temp dir and moves in when complete (a refresh mid-export listed
    half a lesson and cached its blank duration for good); the hub
    and ignored badges empty with Cloud off, like Android and the
    web. A granted-but-unattachable mic raises the video-only
    banner, and the level tap reads only the contiguous sample
    bytes. 5 new `IOSBugSweepTests`; 7 new `AndroidBugSweepTests`
    on the Android side.
- **Bug sweep, part 1: pipeline, hub publish, and worker**
  (user-ordered "fix all bugs"; every fix test-first).
  - *HLS fallback always failed.* Since downloads land in a
    `.mp4.part` sidecar, ffmpeg could not infer the muxer ("Unable
    to choose an output format") and blamed token auth; the remux
    now names `-f mp4` (verified against real ffmpeg).
  - *Truncated downloads passed as complete.* urllib returns a
    short read at EOF instead of failing: `http_download` now checks
    `Content-Length` and wraps mid-body resets, so a cut-off lesson
    never survives the `.part` rename (local-socket tests).
  - *`--retry-failed` looped forever* on a job that failed again
    (the queue hands it straight back). Each job now runs once per
    run, a re-handed one goes back to failed, and the worker orders
    retries after pending work, least recently tried first, so one
    bad job cannot starve the rest. Same guard in `fetch_jobs.py`.
  - *A killed direct download resumed from its `.part`* as if it
    were the lesson; resume and yt-dlp pickup accept finished media
    names only. A video listed on two pages runs once.
  - *Hub deletes made in the apps came back within 5 minutes*:
    `run_cloud.sh` re-posted every work dir each cycle (also
    churning `publishedAt`, the hub's newest-first order).
    `publish.py --if-changed` posts once per artifact version
    (`work/cloud/hub_published.json`), and a video Stream answers
    404 for is never published. `run_cloud.sh` also runs from its
    own checkout instead of a hard-coded `/home/aurelio`.
  - *Worker:* deploy docs never applied `0003_ignored.sql` (the hub
    list reads it) and every `wrangler d1 execute` lacked
    `--remote`, which Wrangler 4 needs to touch production; a
    missing table now answers 503 naming the file, every route
    answers JSON on a thrown error, the listing proxy checks its key
    first, a numeric `videoId` publishes, and vendor status/delete
    paths carry the videoId encoded. 9 new hub checks (69).
    Not yet deployed: production still runs the Nov 1 worker until
    `npx wrangler deploy` (its D1 already has all three tables).
  - *Second pass, pipeline side.* Lesson dates came from the work
    dir's mtime (the processing day) although cloud work dirs carry
    the take's stamp in their name; the publish fingerprint now
    includes the date, so corrected dates reach the hub, and
    mtime-fallback dates match the stamp format ("Nov 1", not
    "Nov 01"). A poster time past the video's end falls back to the
    midpoint instead of no poster. Raw web takes (VP8/Opus WebM,
    which the MP4 muxer refuses) transcode for video understanding
    instead of always falling back to stills. `setup.sh` picks the
    ffmpeg build for the machine (arm64 Linux got an amd64 binary;
    macOS is told to `brew install ffmpeg`) and lands the SAM
    checkpoint atomically.
  - *Tests:* the two "single positional" CLI tests locked the live
    `work/cloud` and flaked whenever cron held it; they use a temp
    root now.
### Changed
- **"Hearth": a friendlier design language across all three apps
  (user-ordered).** Inspired by Airbnb's warm whites and photo-first
  cards and the old Path app's warm red and round buttons, specified
  once in the new `docs/DESIGN.md` and drawn in each platform's own
  idiom; features unchanged and in parity. Warm paper by default with
  a matching dark set that follows the system (CSS
  `prefers-color-scheme`; Android `Theme.DeviceDefault.DayNight` plus
  a runtime palette and light system bars; iOS dynamic colours, no
  more forced dark), one ember accent (`#D2452A`, AA with white),
  a time-of-day greeting over Record / Upload video action tiles,
  hub lessons on warm cover tiles (same colour per title everywhere),
  device sessions shown by a frame of the video with its length, and
  statuses in word chips ("Uploading 42%", "In the cloud", "Upload
  failed · Retry") with an upload progress ring. Record gets a
  shutter dock (status under the shutter), a sage Cloud badge, a
  pill zoom track; lessons open listing-style (cover banner, ember
  Play pill, corrections as quote cards, chapters as time chips,
  inline Markdown in the write-up). Platform touches: SF Pro Rounded
  titles and press squish on iOS; on Android an in-content large
  title (the ActionBar steps aside on home), line icons drawn in code
  (`Glyphs.java`), video frames probed off the UI thread, haptics on
  Record/Stop; on the web a translucent top bar, a drop-zone upload
  card and a hub refresh button. New ember app icons (PWA, iOS,
  Android adaptive). Design-pinned contract tests rewritten with the
  order noted; 15 new cross-platform tests in
  `tests/test_design_language.py`. Web verified by Playwright
  screenshots (light/dark, every page); Android javac-checked against
  the API 34 framework (no Android SDK on this host, so the APK and
  web `dist/` are not rebuilt — no token pool here either); iOS
  syntax-checked only (no Xcode).

## 2026-11-01

### Fixed
- **Ignored sync verifies worker responses.** A stale worker answers
  the marker POST with 200 and a mint payload (unknown paths fall
  into the video trio) — now a 200 without `{"ignored": <that
  guid>}` fails naming a redeploy, like a refusal, and a non-list
  GET is loud too. Found live: production predates the route
  hardening, so the sync stays red until it is deployed.

### Added
- **Ignored takes: hub-backed set-asides with Record-screen badges.**
  Operator `ignored` entries sync to a new `ignored_videos` table
  (`POST`/`GET /hub/ignored`, `DELETE /hub/ignored/<id>`,
  migration `0003_ignored.sql`); the hub sessions list and detail
  exclude them server-side, and all three recorders badge matching
  takes on Record (cloud-link videoId, else filename vs marker
  title) with the reason attached. `publish.py --sync-ignored`
  converges markers every `run_cloud.sh` cycle; 13 new hub checks
  (60 total) plus pipeline and per-app contract tests. Web `dist/`
  and the APK rebuilt; iOS contract-test-only (no Xcode here).

### Fixed
- **Correction beats capped at 60 s (user-ordered).** Sparse API
  transcripts yielded 4-minute "moments" (three identical 65 MB cuts
  on one lesson) that also blew the highlight size limit; beats now
  end at most 60 s past the start. The span contract test rewritten
  with the order noted, plus a sparse-segment regression test.

### Added
- **Fetch-to-Stream upload: fetched lessons reach the in-app hub.**
  `--fetch` uploads each finished lesson after the pipeline (create
  the video, PUT the bytes streamed from disk, wait for finished)
  and records it in `cloud_state.json`, so `--cloud` skips it and
  the publish loop picks it up — no manual backfill. The video id
  is stored in `upload.json` before the bytes go up, so a retry
  reuses it instead of minting a duplicate; without the library key
  the run fails fast before claiming. Docs and all three app READMEs
  updated; verified end to end over a live
  queue→pipeline→upload→publish loop (test traces deleted after).
- **Scheduled service with boot persistence.** `*/5 * * * *` runs
  `run_cloud.sh` (fetch → cloud → publish → site) via BusyBox
  `crond`, kept up by an inittab respawn line — back within 5
  minutes of a reboot. SETUP notes the host rules: the crontab file
  must be root-owned (this `crond` silently ignores user-owned
  ones), jobs run as the file's name, and there is no `@reboot` /
  `MAILTO` here — failures surface in `work/cloud/cron.log`.

### Fixed
- **Pipeline races closed; reruns are safe.** `--cloud`/`--fetch`
  take an exclusive lock on the work root (`.lock`): a second run
  on the same root skips with a message instead of processing videos
  twice (verified live against a held lock). The publish loop now
  requires both `writeup.md` and `corrections.json`, so a mid-run or
  crashed dir can never push partial artifacts through the hub
  upsert; it also resolves each work dir's guid up front and skips
  finished fetch sessions that map to no cloud video instead of
  failing every cron run. New "Races and reruns" section in
  PIPELINE.md; `--cloud` stays a one-machine job.
- **Android rebuild, backlog drained, hub filled.** Fresh APK from
  `build.sh` (token-stamped, template restored), installed and
  launch-verified on the Pixel 4 with no crash; processed the full
  backlog (1 fetch job, 11 cloud lessons → 8 done, 3 validator
  refusals on non-lesson test takes) and published 9 sessions to the
  hub (10 with the manual omelette backfill that motivated the
  upload feature above).

### Fixed
- **Android: link lock, configured(), engine robustness.** Cloud
  link writes synchronize (callbacks persist off the UI thread);
  `configured()` needs a token in signer mode; a sub-700ms
  stop-throw deletes its partial take instead of listing/uploading
  a corrupt lesson; camera error/disconnect/configure-failure
  fails a queued start loudly instead of wedging later takes;
  surface resizes and luma attach no longer rebuild mid-take.
  Rebuilt and re-verified on the Pixel 4.
- **iOS: audio session, locks, and small leaks fixed.** Playback
  restores a record-capable session when either player stops or a
  take starts (both players set `.playback`, nothing restored it);
  the links blob's read-modify-write holds an `NSLock` (progress
  callbacks persist off-main); session observers are stored and
  removed; the hub shows a loading state instead of flashing the
  empty text; `configured()` needs a token in signer mode.
  Contract-test-only — needs a Mac compile.
- **Fetcher robustness: atomic downloads, honest errors.** Direct
  URL downloads land via `.part` + rename, so an interrupted
  download can no longer leave a truncated lesson that a retry
  would process as real; non-JSON 200s surface as wrapped errors
  instead of raw tracebacks; non-object state files fail loudly
  instead of silently reprocessing everything; the token-auth hint
  moved onto remux failures only (it misdirected ffmpeg-missing
  cases); both `--max` flags answer clean 2s.
- **Signer routing hardened, auth fails closed.** Only `/` mints
  videos and proxies status/delete now — any other path 404s instead
  of falling into the trio (a typo'd client could mint or delete a
  video); malformed job/video ids answer 400 instead of an uncaught
  500; and an empty token pool fails loud (500) instead of silently
  serving the library. 6 new hub checks (47 green).
- **iOS playback was broken for hub sessions and device recordings.**
  *Hub:* the Cloud CDN's hotlink protection 403s any request without
  the player page as `Referer` (the pipeline fetcher already sends it),
  and AVPlayer sent none, so every hub stream failed to a crossed-out
  play glyph. Hub playback now sends the session's embed URL as
  `Referer`, prefers the progressive MP4 (then HLS), plays through the
  speaker (`.playback` audio category), and a stream that still fails
  opens the Cloud player instead of dying silently — like Android and
  the web. *Device:* tapping a session row played the video in the
  viewfinder at the top of the Record list, off-screen whenever the
  row was scrolled into view (and `scrollTo` inside the List did not
  bring it back). A tapped session now plays in a full-screen native
  `VideoPlayer` (scrub, AirPlay, close), and the camera rests while it
  plays. Verified on an iPhone 14 Pro: hub frames advance; the player
  covers the screen with the list scrolled to the bottom.

### Added
- **iOS app icon, the same artwork as the web PWA icon.** New
  `Assets.xcassets/AppIcon` (single 1024 opaque PNG, upscaled from
  `app/recorder/icons/icon-512.png`) wired into the Xcode project;
  contract test added.

### Changed
- **Android parity sync + at-home redesign (user-ordered).** Hub
  playback moves to its own dialog player (MP4 then HLS with the
  embed URL as `Referer` for the CDN's hotlink protection, Cloud
  embed last — watching never opens the camera); REC badge,
  auto-hiding zoom, player ✕, hub ⟳ refresh, device empty state,
  denial→Settings; device playback scrolls the viewfinder into view.
  Merged with the native-feel pass below: its Material foundation
  stands (cards, `RippleDrawable`s, `Switch`, action-bar camera menu,
  primary buttons), these behaviors kept on top. ActionBar titles +
  Up replace ‹ Home; adaptive launcher icon (`res/` + `aapt2 compile`
  step). `AndroidSyncTests` reconciled with `AndroidNativeFeelTests`;
  rebuilt, re-tested, re-verified on the Pixel 4 in the merge.

### Fixed
- **URL fetcher finds yt-dlp without a PATH binary.** `fetch_jobs.py`
  fell back to `sys.executable -m yt_dlp`, so `--fetch` works under
  cron/bare environments where only the module is installed; the
  failure message still names the `uv pip install yt-dlp` fix.
  Regression test included; end-to-end `--fetch` run green
  (3 jobs, 0 failed).

### Changed
- **Native-feel UI pass on all three apps (user-ordered goal: they
  should feel native to their platforms and be intuitive).**
  - *Web:* drawn as a phone app — large title on home, top bar with a
    back chevron and the camera switch on Record/Upload, grouped inset
    lists, a real `role="switch"` Cloud row, a round shutter-style
    Record button, 48px targets, visible keyboard focus, per-platform
    nudges (`html.ios` / `html.android`). Same element IDs; service
    worker cache `v9`.
  - *iOS:* Record is an inset-grouped List (viewfinder card with zoom,
    a ring-and-disc shutter, the system Cloud toggle, and session rows
    whose swipe now really deletes — it was a no-op in the old
    ScrollView); empty state is a `ContentUnavailableView`; Fetch from
    link waits for a link and submits from the keyboard's Go. The Cloud
    toggle's binding now acts only on a real change.
  - *Android (source-only — no SDK on the machine that wrote it, so
    **not compiled and the APK is NOT rebuilt**):* `Theme.Material`
    with an ActionBar (up arrow replaces the `‹ Home` button, camera
    switch is a menu action), themed system bars, rounded ripple
    buttons, a primary Record button, a `Switch` for Cloud, card lists
    with ripple rows and empty states, 48dp targets. Rebuild and
    shake out on the Pixel 4 before trusting it.
  - Contract tests added per platform; the Android `‹ Home` assertion
    was rewritten (up arrow) — user-ordered, noted in the test.
- **Home is actions with the hub last; cloud + device moved to the
  record screen (user-ordered, all three apps).** Cloud settings hide
  behind a small Advanced settings link (debug overrides only). Web:
  `index.html` keeps actions + hub, `record.html` gains the toggle,
  sessions, and link; rows play in place. Android and iOS mirror it
  (dialog/sheet unchanged, new trigger). Service-worker cache `v8`.

### Added
- **URL fetch queue (user-ordered).** Paste a link on any app's
  upload screen: direct video files download in the page (web) while
  YouTube/watch links queue at the signer (`POST /fetch/jobs`, D1
  table `fetch_jobs`) for the pipeline, which claims them
  oldest-first, downloads with yt-dlp or plain HTTPS, and runs each
  like a session (`run_pipeline.py --fetch`, also in `run_cloud.sh`
  when configured). Failed jobs stay failed until `--retry-failed`;
  claims older than two hours come back. Natives queue every link
  server-side. Needs `migrations/0002_fetch_jobs.sql` applied + a
  worker redeploy (service gate: 41 hub checks).

### Changed
- **iOS feels at home on iOS (user-ordered), same design as web and
  Android.** `ContentView.swift` now uses a `NavigationStack`: home is
  a grouped list (Record and Upload, then Hub, the Cloud toggle, and
  This device) with pull to refresh and a ⚙ toolbar button that opens
  Cloud settings as a sheet `Form`. Record is pushed, and the system
  back button and edge swipe replace ‹ Home. The path drives
  `showScreen`, so leaving Record still stops and keeps a live take
  and parks the camera, and foregrounding resumes the camera only when
  Record is on top. Session rows use SF Symbols, a context menu (Play,
  Share Cloud link, Retry upload, Save a copy, Delete), and
  swipe-to-delete. Upload offers the Photos picker as well as Files.
  Hub sessions open their own screen with an inline `VideoPlayer`, the
  write-up rendered as Markdown, corrections and chapters, and
  Share/Delete in the toolbar.
  Contract tests in `tests/test_ios_recorder.py` were rewritten where
  they pinned the old widgets (each one is commented as user-ordered),
  and new ones were added for the navigation, sheet, Photos, refresh,
  and hub playback.

### Fixed
- **iOS hub playback no longer opens the camera.** It used to route
  through the record screen, so watching a published lesson could
  trigger the camera permission prompt.
- **Web hub rows were dateless and could not play.** `hubRowHTML`
  read snake_case fields (`lesson_date`, `mp4_url`), but the signer
  answers in camelCase and its list route carries no playback URLs.
  Rows now open the session's detail (`GET /hub/sessions/<id>`) with
  the write-up, corrections, chapters, ▶ Play (home's own player),
  ↗ Share, and 🗑 Delete. Delete removes the hub record before the
  video and reports a partial outcome honestly. This brings the web to
  parity with Android and iOS. The hub also explains when Cloud is off
  and reloads after toggling Cloud or closing settings. Service-worker
  cache bumped to `v7`.
- **Hub Play is never a dead button.** If a session has no stream URL,
  iOS opens the Cloud embed page. On the web, a player error (HLS
  outside Safari) opens the embed page and says so. Outcomes now show
  on the iOS hub screen itself.

### Open
- **Android hub playback still opens the camera.** It still routes
  through `showScreen("record")`, and its hub header still says "Hub
  sessions" where web and iOS say "Hub". It is unchanged because this
  Mac has no Android SDK, so editing the source would leave the
  prebuilt APK stale. Fix it on a machine that can rebuild and install
  the APK.

## 2026-10-31

### Changed
- **Web app split into one page per screen (user-ordered).** The
  single `index.html` with `showScreen` toggles is now `index.html`
  (home) + `record.html` + `upload.html` sharing `common.js` and
  `app.css`, with per-page scripts. Same screens, same behavior —
  home rows reach the viewfinder via `record.html?play=<name>` — and
  the build stamps its token into `dist/common.js`, the single stamp
  point. Contract tests in `tests/test_recorder_streamlined.py` read
  the file that owns each assertion; the service worker precaches
  every page and script (cache `v6`).
- **Prebuilt APK re-stamped from the restored original token pool**
  (no source change — the shipped build matches the worker again).

### Fixed
- **Android `build.sh` exits 0 on success.** The final
  `aapt2 dump badging | head -4` line died with SIGPIPE under
  `set -o pipefail` (badging prints 21 lines; head closes early), so
  every successful build exited 141 and broke `build.sh && ...`
  chains. The tail is now SIGPIPE-safe; covered by
  `AndroidBuildExitTests` in `tests/test_recorder_streamlined.py`.

## 2026-10-30

### Docs
- **Fresh-machine setup + agent entry.** New `docs/SETUP.md` (clone to
  running: secrets map, token pool, worker reuse/deploy, builds, cron)
  and root `AGENTS.md` (layout, gates, conventions — incl. leaving the
  repo in sync on every change); `setup.sh` now serves the stamped
  `dist/` and points at SETUP.
- **Stale sweep.** `docs/DEVICES.md` rewritten for the single app;
  PIPELINE/signer/native READMEs, worker header, code comments, and
  test docstrings updated from recorder-as-product to app framings;
  pipeline docs now cover the `ignored` video state.

### Changed
- **One app: Unwritten Craft.** Recording is a screen, not a separate
  app, on all three platforms. Web (`app/recorder/index.html`), Android
  (`MainActivity.java`), and iOS (`ContentView.swift`) now land on home:
  Record and Upload actions above the hub sessions, cloud toggle and
  settings, then the on-device sessions — with ‹ Home navigation back
  from the record screen. An upload rides the exact session path of a
  take (clips folder under an `unwritten_lesson_upload_` name, then
  Cloud), so the pipeline picks it up like a recording. The camera only
  opens on the record screen; leaving it stops a live take (kept) and
  releases the camera. Product naming follows: Android label and APK
  (`unwritten-craft.apk`), iOS display name, web manifest/title/service
  worker, and the site hub/session templates all say Unwritten Craft;
  `recorder/` URL paths and internal identifiers are unchanged. New
  contract tests: `AndroidScreensTests`, `IOSScreensTests`, web screen
  tests, and a terminology ban on the retired product name (271 tests,
  23 hub checks green).
- **Pipeline: ignored videos stay set aside.** `select_ready` now skips
  state entries with result `ignored` — an operator decision that a
  video is not a lesson — even under `--retry-failed`, so test clips
  (two single-word "Yeah" takes failed write-up validation twice) stop
  showing as failed without being re-downloaded. The two entries keep
  their title/lesson/workDir with a reason; Cloud videos untouched.

### Added
- **Cloud proxy for local pipeline.** `app/cloud-signer/worker.js` exposes `GET /pipeline/videos` proxied with `CLOUD_API_KEY` so the local `pipeline/cloud_fetch.py --cloud` can list via `CLOUD_PROXY_URL` without holding the library key; `CLOUD_LIBRARY_KEY` becomes optional when the proxy is set. `http_get_json` now sends `User-Agent: UnwrittenCraft/1.0`.
- **Local cloud runner (auto-publish).** `run_cloud.sh` (now tracked) runs `run_pipeline.py --cloud work/cloud` *and* publishes each finished `work/cloud/*__*/writeup.md` via `pipeline/publish.py` to `HUB_SIGNER_URL` (`app/cloud-signer/tokens.txt`) then `make_site.py work/cloud work/site` every minute via `flock` to `work/cloud/cron.log`; `work/site` on `0.0.0.0:8787`.
- **Hub WAF fix.** `pipeline/publish.py:91` sends `User-Agent: UnwrittenCraft/1.0` (like `cloud_fetch.py`) to bypass Cloudflare WAF `1010` that blocked `Python-urllib`; plus `Android: surface hub error cause + log` at `MainActivity.java:874-884` surfaces `(Unable to resolve host…)` instead of generic.

### Fixed
- **Bug-fix campaign, service first.** `GET /pipeline/videos` required
  no token — anyone could list the library through the proxy; it now
  sits behind the token check like every other route (6 new
  `hub-check.mjs` checks). Hub routes tolerate trailing/doubled
  slashes (pasted signer URLs), corrupt JSON columns serve as empty
  instead of 500ing, and the header documents the token trust
  boundary. `hub-check.mjs` grows 13 → 23 checks.
- **Pipeline: tighter clips, safer fetching.** Correction windows
  bisect to the next segment instead of a blind 20 s default;
  `parse_ts` tolerates `[02:08]`/fractions and rejects out-of-range
  stamps; the finder prompt demands bare `mm:ss`. Downloads land via
  `.part` + rename (truncated files can never pass as lessons),
  `cloud_fetch` main records per-video failures and continues, and
  `--transcript` is refused when blank or unstamped. New: `muse`
  preflight, ffmpeg timeouts with stderr tails, a guarded
  `corrections.json` load, shared 429/500 retry plus TLS/HTTP error
  wrapping in `meta_api`, streaming (constant-RAM) file uploads,
  fail-closed redaction hold, `yuv420p` muxes with partial cleanup,
  and an ffprobe fallback ladder for phone WebM/VFR. Pages render
  intro, "What you need", and audio (`.m4a`) clips, and survive
  corrupt JSON.
- **Recorders: no more silent/stuck states.** Web, Android, and iOS
  all fail fast without cloud credentials (was: doomed 401s on web),
  end 10-minute processing polls and dead status checks in the
  failed state with retry, cancel in-flight work on delete (no
  zombie rows), sweep the offline backlog when Cloud is re-enabled,
  and offer device-only delete when the cloud delete fails. Linked
  rows keep their ↓ download on all three; share fallbacks can no
  longer serve another lesson's link or an `embed//videoId` URL; hub
  deletes remove the record before the video and report partial
  outcomes honestly.
- **iOS specifics.** Fixed a remux-failure path that deleted the
  take and registered a phantom row; guarded 9 force-unwrapped URLs
  (mistyped signer URLs now error, never crash); `PlayerView` swaps
  players; settings fields bind stored values with build defaults as
  placeholders (no override shadowing); foreground refreshes
  permissions and resumes the session; background pauses it;
  camera-switch re-checks recording on-queue.
- **Android specifics.** New ⚙ Cloud settings screen (token/keys
  were previously unstamped-build dead ends); camera/permission/
  record errors Toast instead of dying in a hidden view; stop
  uploads wait for take finalization (was: partial uploads); failed
  uploads retry from the ! badge; clips dir survives missing
  external storage; external playback goes through a read-only
  `TinyFileProvider` (the `file://` + StrictMode bypass never worked
  on Android 7+); export cleans `IS_PENDING` rows per file and
  continues past failures; background releases the camera and
  foreground reopens it. Full `build.sh` APK verified.
- **Repo hygiene.** `requirements.txt` is live-only (torch moves to
  `requirements-retired.txt` with its CPU index; `setup.sh` installs
  both); `sw.js` caches good pages only and answers offline plainly;
  `run_cloud.sh` logs FAIL markers plus lock contention and exits
  non-zero; `baseten.py` names its optional `openai` dependency;
  fixture plumbing over `samples/lesson_transcript_fixture.md` is
  covered by tests. Investigated and cleared: sample write-ups all
  validate; untimestamped sample transcripts are drafter fixtures by
  design. Full suite (Python + hub-check + javac + APK) green.

## 2026-10-29

### Added
- **Session-cleanup skill.** `.agents/skills/cleanup/` reclaims disk
  by removing regenerable session artifacts (`~/uw-cloud`,
  `/tmp/uw-*`, orphaned `$TMPDIR` debris, the Whisper model cache)
  while keeping credentials, `.venv`, and anything of unknown
  authorship. Validated with `muse skills validate`.
- **Unwritten website generator.** `pipeline/make_site.py <work_root>
  <site_dir>` builds a static site with two sections: the web
  recorder app (copied in from the built `dist/`) and Sessions —
  every finished pipeline work dir rendered to a page via
  `make_page`, with poster, chapters, corrections, and clips
  carried along. Discovery is fully automatic (any dir with a
  `writeup.md`, newest first). Its tests live in `tests/test_site.py`.
- **Native iOS recorder.** `app/ios/` is a third recorder in full
  parity with the Android and web apps: one screen (viewfinder, zoom,
  record, Cloud toggle, export, sessions), same session rows (newest
  first, date + length, tap to play in the viewfinder, long-press to
  delete from device and cloud), same `unwritten_lesson_<stamp>.mp4`
  contract, same presigned-TUS Cloud upload with signer-token
  stamping at build time, and the portable uwcore C++ core linked
  through an Objective-C++ bridge. SwiftUI + AVFoundation, iOS 17+,
  no storyboards, no third-party libraries. 30 tests in
  `tests/test_ios_recorder.py`; build, simulator, and logic-harness
  evidence in `docs/ios-app-worklog.md`.
- **Cloud fetch for the pipeline.** `pipeline/cloud_fetch.py` lists the
  Cloud library, downloads each new finished lesson (highest MP4
  rendition, HLS remux fallback), and `run_pipeline.py --cloud
  <work_root>` runs one full pipeline per new video into its own dir,
  tracking seen videos in `cloud_state.json`. Credentials come from
  `CLOUD_LIBRARY_ID` / `CLOUD_LIBRARY_KEY` / `CLOUD_CDN_HOSTNAME` on
  the pipeline machine only. 13 tests in `tests/test_cloud_fetch.py`.
- **Baseten Muse Spark example request.** `baseten.py` sends a greeting
  through the OpenAI-compatible client using `BASETEN_API_KEY` from the
  environment; it requires the `openai` Python package.

### Changed
- **Cloud fetch defeats CDN hotlink protection and fixes `--cloud`
  args.** `download_video` now sends the video's player page as the
  `Referer` on MP4 downloads and HLS remuxes (bare fetches 403),
  and `run_pipeline.py --cloud` reads the work root from the
  correct positional. Proven live: all 11 library videos
  downloaded, 8 processed end to end. 5 new tests in
  `tests/test_cloud_fetch.py`.
- **Hub navigation and mic parity across all three recorders.**
  Session pages link back to the hub list and over to the recorder,
  and the web recorder shows a Hub link when served inside the site.
  The quiet-minute mic check now exists everywhere (web analyser,
  Android `getMaxAmplitude()`, iOS capture RMS with the same banner),
  and Android gained the front/back camera toggle plus the red
  video-only banner the web and iOS recorders already had. Tests in
  `test_recorder_streamlined.py`, `test_ios_recorder.py`,
  `test_site.py`; iOS device-build verified.
- **The hub lives inside both apps now.** `pipeline/publish.py`
  pushes finished runs (write-up, corrections, chapters, playback
  URLs) to a D1-backed store on the cloud signer (`POST|GET|DELETE
  /hub/sessions`, `node hub-check.mjs` exercises them against real
  SQLite); the iOS and Android recorders gained a Hub section with
  session detail, streamed playback, share, and cloud-first delete.
  Signer-only — direct library-key mode has no hub. 13 worker
  checks, 5 publish tests.
- **iOS recorder commits its config before starting the camera.**
  `configureSession` called `startRunning` inside the
  `beginConfiguration`/`commitConfiguration` block, which throws
  `NSGenericException` on a real camera — black viewfinder, "Camera
  not ready yet". It now commits first, then starts; kept the
  `[UWCam]` console diagnostics that found it. 1 test; session
  start proven on an iPhone 14 Pro.
- **Pipeline docs for the new stages.** `docs/PIPELINE.md` covers
  schema-first outputs, batch caching, and chapters; the deferred
  list is now Teach-back QA alone.
- **Live mic check in the web recorder.** A local mic-energy monitor
  warns after a quiet minute of recording, so a dead mic is caught
  during the lesson; no audio leaves the device. 1 test; service
  worker bumped to v4.
- **Chaptered sessions.** `try_chapters` builds `chapters.json` via
  video understanding (key + MP4 only, validated against
  `prompts/chapters_schema.json`, never blocks a run) and the
  optional page shows the timeline. 2 tests.
- **Prompt cache keys on direct API calls.** `responses_create`
  sends a stable `prompt_cache_key` per use case
  (`unwritten-video`, `unwritten-segmentation`, ...) and logs the
  cached-token hit rate, so sequential `--cloud` backlog runs reuse
  prefixes. 2 tests.
- **Schema-first finder and write-up.** Both return validated JSON
  (`prompts/correction_schema.json`, `prompts/writeup_schema.json`,
  enforced via `--output-schema`, checked locally by new
  `pipeline/schemas.py`) and the write-up renders markdown
  deterministically; `segment` is now required-but-`""`, malformed
  output fails loudly. 4 tests; both paths proven live.
- **Transcription is Meta speech-to-text by default.** With
  `MODEL_API_KEY`, `transcribe.py` sends mono 24 kHz WAV to Muse
  Voice Transcribe (DIARIZATION turns + speaker labels into
  `segments.json`), splitting audio over 10 minutes into capped
  chunks with re-offset turns; `UNWRITTEN_TRANSCRIBE=local`
  (or no key) keeps local faster-whisper, `=api` forces the API.
  Recognition bias via `UNWRITTEN_ASR_KEYWORDS` /
  `UNWRITTEN_ASR_LANGUAGES`. Refuse-emptiness guard kept on both
  paths. 11 tests; local path proven live on the 8.4-minute lesson.
- **Share-safe clips and auto-posters.** With the key, each video
  correction clip also runs SAM as "face" and gains `redacted-NN.mp4`
  (opaque covers) plus `faces-NN.json` when faces track; every run
  picks `poster.jpg` (Spark-chosen moment, else midpoint), shown by
  the optional page. Deferred TODOs (teach-back QA, live mic check,
  chapters, schema-first outputs, batch caching) recorded in
  `docs/PIPELINE.md`. 9 tests; poster proven live keyless.
- **Meta video understanding + SAM highlights in the pipeline.** New
  stdlib-only `pipeline/meta_api.py` (Files + Responses): with
  `MODEL_API_KEY`, the write-up watches the whole lesson video
  (visuals and speech, owner's choice; MP4 remux when needed) with
  automatic fallback to still frames, and each correction clip gains
  a SAM-3.1-tracked `highlight-NN.mp4` spotlight plus
  `segments-NN.json` (subject from the finder's new `"segment"`
  phrase; new `pipeline/highlight.py` renders the overlays). Uploads
  are deleted after use; without the key the pipeline is unchanged.
  25 tests in `tests/test_meta_api.py`; render path proven on a real
  clip, live API calls await a keyed run.
- **Write-ups are polished and video-grounded.** `draft_writeup.py`
  now attaches up to 16 evenly spaced lesson frames to the Spark
  call; the rewritten `prompts/writeup_drafter.md` produces an intro,
  `## What you need`, numbered `## Steps`, and `## What <Mentor>
  knows` — the transcript is the spine, the video fills what it
  leaves unsaid, nothing is imported from outside knowledge, and the
  mentor's phrasing survives verbatim. Degrades to transcript-only
  without media. 4 tests in `tests/test_core.py`; proven on an
  8.4-minute lesson (16 steps, 6 wisdom bullets, page parser clean).
- **Corrections finder tolerates doubled output.** `parse_hits()` in
  `pipeline/find_corrections.py` takes the first complete JSON array
  instead of requiring the whole model output to be exactly one
  document (live failure: `[][]` for "no corrections" crashed the
  run). Non-array JSON and garbage are still refused. 5 tests in
  `tests/test_core.py`; proven on an 8.4-minute lesson run end to end.
- **Web recorder matches the Android app.** `app/recorder/` now uses
  the same dark palette and single-column order (viewfinder, zoom,
  record, Cloud toggle, export, sessions) and the same session rows:
  newest first, date + length, tap to play in the viewfinder, ↓ to
  download, ↗ to share the Cloud link, long-press to delete. The
  **■ Stop** button carries the timer, zoom follows the camera's
  reported range, and **Export sessions to Downloads** appears only
  with Cloud off. Filename contract, vault, and TUS upload unchanged;
  10 parity tests in `tests/test_recorder_streamlined.py`.
- **Recorder builds refreshed.** Rebuild the committed Android APK
  with default Cloud uploads, signer-token stamping, and lesson
  deletion; regenerate the ignored web `dist/` output as well. Verify
  the APK signature and restored source-token templates. All 47 tests,
  signer request smoke checks, and script syntax checks pass.
- **Mentor wording throughout live material.** Use generic mentor
  language in the pipeline, prompts, fictional samples, harness, and
  current documentation. Add terminology checks for mentor and Cloud
  naming while preserving dated history and necessary vendor endpoints.
- **Cloud uploads enabled by default in both recorders.** Rename the
  signer and uploader to Cloud, retain existing settings and lesson
  links through migration, and add cloud-first lesson deletion that
  keeps the local lesson if the cloud request fails. Both builds stamp
  a random signer-pool token while keeping source templates empty;
  tokens, web build output, and Wrangler caches stay out of git. The
  web vault no longer prompts for an automatic download; lesson names
  still offer manual downloads. Update recorder docs and contract tests.

## 2026-10-28

### Added
- **Optional Bunny Stream upload in both recorders.** On the
  owner's order, web (`app/recorder/`) and Android (`app/android/`)
  can now, when turned on, upload a copy of each video lesson to
  Bunny Stream (resumable TUS, auto-resume) and surface a ▶
  streamed-playback (HLS) link per lesson. Local-first is untouched:
  the on-device save always happens first, Bunny only ever receives
  a copy, and failures leave the take safe with a retry path. Keys
  are handled two ways, per Bunny's security guidance: a new tiny
  Cloudflare Worker (`app/bunny-signer/`) can hold the library API
  key and issue presigned credentials (recommended), or the key can
  live on the teacher's device only (web `localStorage`, Android
  app-private `SharedPreferences`). Android gains the INTERNET
  permission for this alone and a framework-only `BunnyUploader`;
  its README's "no network calls" note is now scoped to Bunny-off.
  Bunny has no live ingest, so this is store-then-stream, not live
  broadcast — the same workflow Alfred/Ring gate behind manual
  export, here one tap. New `BunnyWebTests` / `BunnyAndroidTests` /
  `BunnySignerTests` contract tests; full suite 45 tests green,
  TUS signature verified against Bunny's documented recipe, APK
  rebuilt with the INTERNET permission, installed on the Pixel 4,
  and the Bunny section verified in the on-device UI.

### Changed
- **Base device: Pixel 4.** On the owner's order, the Android
  recorder now targets the Google Pixel 4 as its base device and
  the previous Pixel 2 / minSdk 26 target is retired. **minSdk 29**
  (Android 10, the Pixel 4's launch OS) in `app/build.gradle` and
  `build.sh`; **arm64-v8a only** (the Pixel 4 is 64-bit only), so
  the APK carries one native library and drops to ~269 KB.
  Everything that existed only for the old target is removed, not
  left dormant: the `WRITE_EXTERNAL_STORAGE` (maxSdk 28) permission,
  the API ≤28 export-permission gate, and the legacy
  external-storage export path — export is MediaStore Downloads
  only, as it already was on API 29+. The AAudio
  voice-recognition input preset (API 28+, previously unavailable
  at minSdk 26) is now actually set for the dialogue WAV. Web
  recorder codec rationale, `docs/DEVICES.md` (Pixel 4 = reference
  setup), the Android README, and the work log updated to match;
  the work log's stale shakeout checklist (roles / steps /
  companion) rewritten to the streamlined one-job flow, and its
  Oct 26 minSdk 26 narrative kept as superseded history. New
  `Pixel4BaselineTests` in `tests/test_recorder_streamlined.py`
  pin the baseline (minSdk 29, arm64 only, no pre-29 storage
  fallback). Verified: `build.sh` clean, APK badging
  **sdkVersion 29**, permissions CAMERA / RECORD_AUDIO / WAKE_LOCK
  only, signature OK, all 36 tests pass. The recorder's job is
  unchanged and in sync with the docs goal: record one lesson,
  stop, keep the file.

## 2026-10-27

### Changed
- **The recorders, streamlined to match the simplified design.** Both
  recorders (`app/recorder/`, `app/android/`) now have one job: record
  one lesson, stop, keep the file. The three roles (Interviewer /
  Recorder / Companion), the four-step session protocol, the apprentice
  line, session codes, companion sync, TTS prompts, photos, and session
  manifests are removed; every take is `unwritten_lesson_<timestamp>`.
  The no-loss engineering stays: IndexedDB vault + download copy and
  the native-app fallback on the web, Camera2/MediaRecorder capture
  and Downloads export on Android. `Prefs.java` deleted; covered by
  `tests/test_recorder_streamlined.py`.

### Added
- **This changelog**, compiled retroactively from the commit history.
- **Correction finder** — `pipeline/find_corrections.py` +
  `prompts/correction_finder.md` (Muse Spark): surfaces every moment
  the teacher corrected the beginner, anchored to its timestamp and
  her exact words. (`b506a24`)
- **Core test** — a fictional lesson fixture with planted ground truth
  (6 corrections, 4 distractors, fidelity traps) and its scored
  results in `docs/core-test-2026-10-27.md`: finder caught 6/6
  corrections with 0 false alarms (keyword-regex baseline: precision
  0.26, missed the buried correction); write-up audit clean — no
  invented oven temperature or bake time, "two pinches" kept, all
  technique negations preserved. (`b506a24`)
- **Machine setup** — pinned Python requirements and an idempotent
  `setup.sh`; a local HTTPS server for the recorder. (`c341af1`,
  `eca35ef`)

### Changed
- **The code now follows the three core things.** `run_pipeline.py`
  rewritten: one ordinary lesson file in → transcribe → write-up →
  corrections, with each correction cut from the lesson into `clips/`.
  It calls `find_corrections.py` (the old runner never did), and
  success requires a write-up + corrections list — not a page.
  `ingest.py` classifies by extension only (the lesson is the largest
  media file); `transcribe.py` also writes the timestamped transcript;
  the write-up drafter's recorder-era `--wisdom` input and
  session-protocol prompt rules are removed; `docs/PIPELINE.md`
  rewritten to match. (`03172d7`)
- **Naming made consistent** — what the docs call the write-up is what
  the code calls it: `draft_card.py` → `draft_writeup.py`,
  `card_drafter.md` → `writeup_drafter.md`, `handiton.py` →
  `make_page.py`, `sample_card*.md` → `sample_writeup*.md`, with every
  living reference updated and the old files deleted. (`b00ddf1`)
- **Framing** — "learn what is of value" supersedes "teach what must
  not disappear" in the README and the submission draft. (`25e04d3`)
- **Recorder redesign** (before the design was cut later the same
  day): a young-apprentice flow and a warmer page; the web recorder
  became an installable PWA; the Android APK was rebuilt on the new
  toolchain. (`f76f922`, `0482fc5`, `1b6d9de`)

### Removed
- **The elaborate design, cut from the product.** Blind AI apprentice,
  SAM overlay as hero visual, recorder protocol and step names,
  correct-once ceremony — cut after a hands-on test found the capture
  flow cumbersome and Claude/Wonder critiques showed the apprentice's
  failures were scripted defaults. README and submission draft
  rewritten to match what is actually built; **submission undecided**,
  personal use first. The cut code remains in the tree as retired
  experiments (`harness/`, `pipeline/sam_overlay.py`,
  `pipeline/frames.py`). (`7ad887b`)
- **The page, as a core output.** Demoted to optional: `make_page.py`
  assembles a guide/manual from the three core outputs later, when
  there is a recipient. Nothing in the core depends on it.
  (`b506a24`, `03172d7`)

## 2026-10-26

### Added
- **Project scaffold** — design README, boundary prompts, and the
  mechanic-test harness with a fictional sample. (`212b54e`; a
  duplicate scaffold commit `9057ff9` is the empty-repo bootstrap
  artifact.)
- **Process test on the Muse stack** — Spark drafts, Wonder
  apprentices; the earlier stack's test superseded. (`9ece9ca`)
- **ELI5 explainer video** linked from the README (hosted outside the
  repo). (`15c1408`)
- **Web recorder app** — the Pixel 2 "fake robot" apprentice recorder,
  plus the first hackathon submission draft. (`c6d9446`)
- **Session pipeline v1** — media in, card + SAM overlay + hand-it-on
  page out; synthetic end-to-end test passes the same evening.
  (`6c5eb02`, `0e3c7bb`)
- **Wisdom extraction** — the drafter captures the teacher's judgment
  in a separate section; the design made craft-agnostic by
  construction. (`dea0449`)
- **Recorder v6** — one file, three roles, every device in the room
  useful. (`4c89d86`)
- **Native Android recorder** — minSdk 26 (Pixel 2), C++ core
  (AAudio + luma/flash detection), Camera2 recording, no INTERNET
  permission; Wonder-coded in three passes, integrated and
  build-verified; APK committed, with a work log and Legion handoff
  doc. (`0c0ed9d`, `dd71dc1`)

### Changed
- **Terminology** — the artifact's units renamed on the owner's call:
  "tricks" → each correction is a **technique**; together they are
  **the Knack**. Demo title set in the owner's exact wording: "Mom's
  Bread: 4 techniques, a knack never written down." (`480b2d9`,
  `8a93a84`, `46e8751`)
- **Wisdom timing** — the wisdom Q&A moved to after the teacher's
  reaction, on Claude's approved fix. (`5494b7c`)
- Docs wording and code comments polished; a stray build file
  removed. (`7deb025`, `e2415a7`)

### Fixed
- **Silent-mic guard** — a recorder can no longer pass a session with
  a silently dead microphone unnoticed (Claude review). (`0bc8577`)
- **Correctness fixes** from Claude's first review pass — no design
  change. (`569a2d6`)
- **Wonder full-code review fixes** — recorder v6.1, pipeline honesty
  rules (stale artifacts deleted up front; a run fails unless its
  outputs were produced this run), harness hardening. Tests 9 → 16.
  (`b4f70b7`)
