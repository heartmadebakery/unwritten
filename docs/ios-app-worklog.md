# iOS app — work log & handoff (2026-10-29)

**Audience: whoever continues this work.** This file records what was
done for the native iOS recorder, why, and what is verified — so none
of it has to be rediscovered. The app overview lives in
[`app/ios/README.md`](../app/ios/README.md); this file is the history,
the evidence, and the open items.

## The order

Build an iOS version of the recorder with the same features, in parity
with the Android app and the web app: one screen, one job (record one
lesson, stop, keep the file), same dark palette and column order
(viewfinder, zoom, record, Cloud toggle, export, sessions), same
session rows (newest first, date + length, tap to play in the
viewfinder, ↓/↗ actions, long-press to delete from device and cloud),
same filename contract, same presigned-TUS Cloud upload with the same
link states, same build-time signer-token stamping, and the retained
C++ core.

## What was built

Package `org.tinio.unwritten` (same identifier as Android), **iOS
17+**, iPhone only, base device iPhone (2019-class — the iOS
counterpart to the Pixel 4). SwiftUI with no storyboards, no
third-party libraries, one C++17 core. Full inventory is in the app
README; the notable porting decisions:

- **Capture:** `AVCaptureSession` preset `.hd1280x720` +
  `AVCaptureMovieFileOutput` (hardware H.264/AAC), then a
  passthrough `AVAssetExportSession` remux to the final
  `unwritten_lesson_<stamp>.mp4` — no re-encode. Bitrate is left to
  the hardware encoder (Android caps MediaRecorder at 4 Mbps; iOS
  exposes no bitrate knob on the movie output, and the manual
  AVAssetWriter pipeline that would allow one trades away
  reliability). If the remux ever fails, the `.mov` is kept under the
  same stamp — the pipeline takes the largest media file whatever its
  extension, so the lesson is never lost to a container step.
- **Preview/playback:** `AVCaptureVideoPreviewLayer` under an
  `AVPlayerLayer` overlay with ▶/⏸/✕, like Android's viewfinder
  player. Recording stops playback; playback ends by closing,
  completion, or starting a recording.
- **Zoom:** the device's `maxAvailableVideoZoomFactor` drives a
  −/slider/+/label row; ±0.2 nudges like Android; the row hides when
  the camera reports no zoom range (web behavior — never dead UI).
- **Mic denied:** the session configures video-only and raises the
  red **No microphone** banner — a denied mic never costs the video,
  and a silent take is never silent about being silent.
- **Cloud:** `URLSession` TUS (create, HEAD resume, 5 MB PATCH
  chunks, 8 retries with backoff, 120×5 s encoding poll), signer mode
  by default with direct library-key mode, per-lesson link state in
  `UserDefaults` with one-generation legacy migration, clipboard copy
  + share sheet on ↗, cloud-first delete. Uploads run while the app
  is foregrounded and resume after restarts.
- **Export:** the share sheet (Save to Files, AirDrop, …) for one
  lesson (↓) or all lessons; lessons also sit in `Documents/clips`,
  visible in the Files app with no action at all.
- **Native core:** `uwcore::ComputeLumaStats` + `FlashDetector`
  ported verbatim from Android's `uwcore.cpp` (the AAudio WAV
  recorder stays Android-only), exposed to Swift through
  `UWCoreBridge` with zero-copy Y-plane calls. `setLumaListener`
  attaches a 420YpCbCr data output at ≤10 fps; the UI leaves it
  detached, exactly like Android.

## Verification evidence

- `bash app/ios/build.sh` — **BUILD SUCCEEDED**, zero warnings:
  token stamped (`token #N of 10`) and the template restored and
  re-checked afterwards, `.app` bundle produced (universal
  arm64+x86_64 simulator slices), `UWComputeLumaMean` present in the
  linked binary.
- `python3 -m unittest discover -s tests` — full suite green,
  including 30 new tests in `tests/test_ios_recorder.py` (parity,
  Cloud, baseline, streamlined-design contract) and the terminology
  scanner widened to `.swift/.cpp/.h/.mm/.plist/.pbxproj/.xcscheme`
  so the new sources obey the Cloud/mentor wording rules.
- Swift logic harness (throwaway, `/tmp/uw_harness.swift`): the
  app's own `Names`/`CloudStore`/`CloudUploader` sources compiled
  for macOS — 20/20 checks pass, and the SHA-256 probe matches
  Python `hashlib` exactly.
- Simulator (iPhone 17 + iPhone 17e, iOS 27): the app installs,
  launches, renders the full UI, and shows the camera prompt with
  the correct usage strings (screenshots reviewed). Crash log count
  stayed flat after the fix below.
- **Crash found and fixed in the simulator:** the first granted-path
  launch died in `-[AVCaptureSession startRunning]` — an uncatchable
  ObjC exception when the session has no inputs (simulator,
  camera-less device). Fixed with an `inputs.isEmpty` guard plus a
  `@try/@catch` bridge (`UWStartCaptureSession`), locked by a
  regression test. Note the simulator runtime always re-prompts for
  camera (grants via `simctl privacy` and TCC writes are ignored),
  so the granted/denied branches past the prompt are verified by
  code path + regression test, not by tapping — see open items.

## Open items

1. **On-device shakeout (real iPhone)** — the next step: granted
   recording end to end, mic-denied video-only + banner, front/back
   switch, zoom range, backgrounding mid-take, a real TUS upload to
   the signer (stamped token) through encoding to ↗ share, and
   cloud-first delete. Capture sessions vary by device; this is the
   one thing the simulator cannot prove.
2. **App icon** — no asset catalog yet (same open item as Android).
3. **Release signing** — the project uses automatic signing; device
   and store builds need a development team.
