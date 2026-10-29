# Changelog

All notable changes to Unwritten Craft, newest first. Dates are
Pacific Time. **Rule: every commit to `main` adds its entry here, in
the same commit.** Entries cite the commit they describe; this file
was compiled retroactively on Oct 27, 2026 from the full commit
history (30 commits) and is maintained in the open from then on.

## 2026-10-29

### Added
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
