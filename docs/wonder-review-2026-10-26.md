# Muse Wonder full-code review — Oct 26, 2026

At the user's direction, Muse Wonder reviewed ALL code written so far in
this repo, in three passes (recorder app / pipeline / harness+tests),
with the code inlined (Wonder has no file access). Every finding was
then verified against the code before being fixed. Raw outputs:
`~/workspace/advisors/wonder_rev{1,2,3}_out.txt` (local, not committed).

Top line per pass, in Wonder's words:
1. Recorder: "the new companion and native-capture paths can overwrite
   or orphan clips, and lead-device clip filenames carry no date/session
   code, so clips can collide in IndexedDB and be silently lost or
   misattributed."
2. Pipeline: "the recorder's native camera/voice-app fallback — the path
   old iPhones use — produces files that ingest classifies as `unknown`,
   so a first real session on such a phone yields no card at all while
   the pipeline still prints 'Pipeline done.'"
3. Harness: "the wisdom-strip is fail-open and a step attempted by only
   one run scores as 'fully specified' — both invert the harness's core
   claim silently."

## What was fixed

### Recorder (23 findings → v6.1)
- Filenames: every clip/photo now carries step + session code + full
  `YYYYMMDD-HHMMSS-mmm` stamp; native-app takes too. IndexedDB records
  carry the code; restore returns only the current session's clips,
  sorted by capture time.
- Session code persisted at creation (a reload can't change a code a
  companion already typed); **↻ New session** rotates it.
- Guards: double-tap on Start/Sync can't orphan a recorder; companion
  mode buttons lock during countdown+recording; the recording mode is
  captured at tap time, not re-read after the countdown.
- Companion: starts recording BEFORE the countdown zero so the beep +
  flash land inside the take; one shared AudioContext created in the
  tap gesture; wake lock requested; `onerror` + video-only retry added;
  leaving mid-countdown cancels it (no hidden recordings).
- Companion on old iOS (no MediaRecorder): native camera/voice-app
  buttons instead of a dead end.
- Photo step captured at shot time (not in the async callback);
  `canvas.toBlob` fallback added.
- Finish/manifest race closed: the manifest button appears only when
  the last take's save has landed; empty takes are rejected with a
  message in both recorders.
- Recorder role can see/edit the apprentice line again (only companion
  hides it); empty line renders guidance instead of an empty quote.
- Keyboard: modifier keys and key-repeat ignored; keys dead on the Done
  screen; ⌂ role button added; step position persists across reloads.
- Capture controls are reversible; file extensions derive from the
  file's MIME type; probe's "secure page" fact is surfaced; the
  big-screen threshold matches the layout breakpoint (900 px);
  IndexedDB open can't hang on a blocked upgrade.

### Pipeline (5 P0 + 9 P1 + P2s)
- Ingest: step token is letters-only, so `unwritten_teach_camera-app_…`
  classifies as `teach` (was: `unknown` — every native-app clip lost);
  recursive walk; `.heic` counts as a photo.
- Honesty: stale work-dir artifacts are deleted up front; the run
  exits non-zero unless a card AND a page were produced this run.
- Frames: WebM files with no container duration no longer crash the
  run (stream-duration fallback, then absolute-time sampling with
  per-frame tolerance); a frames failure never blocks the card.
- Takes: the LATEST take per step wins, logged; a recorder session
  manifest, when present, restricts the run to that session's clips.
- Transcription: optional takes (react/attempt/dialogue) may fail
  without killing the run; the companion dialogue track is an honest,
  labeled fallback for a missing teach take; broll is the hero-source
  fallback; empty/silent audio raises instead of becoming a card
  Spark would invent; VAD filter on; detected language logged.
- Photos: hero prefers a show/teach-step photo; the attempt photo is
  chosen by step and BOTH are copied into the work dir — the hand-it-on
  page now shows teacher-original beside student-attempt (was: the
  overlay twice, with a 404).
- Card drafting: output validated (must contain numbered steps);
  wisdom-source header no longer claims the whole attempt clip is
  Q&A — Spark is instructed to use only the wisdom answers.
- Model binary: `$MUSE_BIN` → PATH → `~/.local/bin/muse` in both
  draft_card and the apprentice collector; prompt files are unique
  per-run temp files, deleted afterwards.
- Page: card bullets from the wisdom section no longer render as
  steps; wisdom renders in its own section; Tricks heading is marked
  DRAFT until the teacher confirms; image `src`s are escaped.
- Tricks miner: word-boundary matching ("Now…" no longer counts as
  "No…"), real sentence boundaries.
- SAM: EXIF orientation applied before the point maps; an empty or
  low-confidence mask aborts instead of writing a fake overlay;
  `--point` validated in both the overlay and the runner (before the
  expensive apprentice stage).

### Harness (3 P0-class + P1s)
- `strip_wisdom` matches headings case/level-insensitively and cuts
  only its own section; the collector now FAILS CLOSED — a
  wisdom-like heading it cannot strip aborts the run instead of
  leaking.
- Values are canonicalised once (90 == 90.0 == "90", "Moderate" ==
  "moderate") and used for both the default test and divergence, so a
  parameter can never be scored as both.
- Steps align by their `step` number, not position. A step attempted
  by a minority of runs counts every unattempted parameter as missing
  — it can never render "fully specified." None/empty commitments are
  missing, not specified. Non-dict steps raise instead of crashing
  analysis. Fenced-block extraction tries each block in turn.
- Collector: runs execute from an empty temp working directory;
  responses carry provenance (`card_sha256`, `keep_wisdom`, model);
  `run_test.py` reads both formats, verifies the hash, and prints
  dropped-run counts and quorum warnings IN the report.
- Tests: 9 → 16, including a contract test that parses
  `prompts/apprentice_instruction.txt` and asserts its 10 parameters
  and defaults match `DEFAULTS` exactly.

## Disagreements / judgment calls
- Pass 1 suggested splitting clip identity into IDB key + display name
  with `crypto.randomUUID()`; not adopted — full timestamps make
  collisions practically impossible on one device and keep filenames
  human-meaningful in a downloads folder, which matters when a family
  member is hunting for a clip.
- Pass 3 suggested scoring normalisation by `n_present`; adopted in
  spirit (counts are printed per step) but the score formula itself is
  unchanged, so historical gap reports stay comparable.
- The broll-hero fallback uses the show-step photo preference first;
  broll FRAMES are used only when there is no show take at all.
