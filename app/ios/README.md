# Unwritten Recorder — native iOS app

The native port of the [web recorder](../recorder/) and the [native
Android app](../android/). Same single job — record one lesson, stop,
keep the file — and the same filename contract
(`unwritten_lesson_<timestamp>.mp4`), so lessons from this app drop
straight into the existing pipeline (`pipeline/ingest.py`) unchanged.
Base device: **iPhone** (2019-class, the iOS counterpart to the
Pixel 4). **iOS 17+**, iPhone only. No storyboards, no third-party
libraries — SwiftUI + AVFoundation and one C++ core only.

**Continuing this work?** Read
[`docs/ios-app-worklog.md`](../../docs/ios-app-worklog.md)
first — full history, build verification, simulator evidence, and the
open items (on-device shakeout, app icon, release signing).

## Why native, and what's in C++

The web recorder is the baseline fallback (it works anywhere a browser
does). Native iOS wins where the web cannot:

- **Hardware encoding** — video goes through AVCaptureSession +
  movie-file output (H.264/AAC at 720p: plenty for hands-and-work
  footage, and kind to storage and batteries), remuxed to `.mp4` with
  a passthrough export — no re-encode. If the remux ever fails, the
  original `.mov` is kept under the same stamp rather than lost; the
  pipeline takes the largest media file whatever its extension.
- **Native core (C++, retained)** — the portable half of Android's
  `libuwcore` (`ComputeLumaStats` mean + 8×8 grid, `FlashDetector`)
  is ported verbatim and linked through an Objective-C++ bridge:
  CameraEngine's per-frame luma analysis runs natively when a
  listener is attached (≤10 fps, like Android). The AAudio WAV half
  stays Android-only — it drives an API with no iOS equivalent.

Swift handles what it is good at: the capture-session wrapper and the
single-screen UI (built programmatically — no storyboards): preview,
zoom, one Record/Stop button, the Cloud toggle, export, the lessons
list, and in-viewfinder playback.

## Layout

```
UnwrittenRecorder.xcodeproj/         (project + shared scheme)
build.sh                             (stamp + simulator build — see below)
UnwrittenRecorder/
    Info.plist             camera/mic usage, Files sharing, portrait
    UnwrittenRecorderApp.swift   app entry
    ContentView.swift      single screen: preview, zoom, record, Cloud, sessions
    CameraEngine.swift     AVCaptureSession + movie output + zoom + luma hook
    SessionStore.swift     clips dir, rows, durations, export/share/delete, uploads
    CloudStore.swift       Cloud settings + per-lesson link state (UserDefaults)
    CloudUploader.swift    presigned TUS upload + status polling + delete
    Names.swift            the filename contract (single source of truth)
    CloudConfig.swift      build-stamped signer token (template in repo)
    uwcore_luma.{h,cpp}    portable C++ core (luma + flash detector)
    UWCoreBridge.{h,mm}    Objective-C++ bridge to Swift
```

## Building

```sh
./build.sh   # needs Xcode; stamps a token, builds, verifies the bundle
```

`build.sh` stamps one random token from the signer pool into the app
(`token #N of 10` in the build log), builds Release for the simulator
with `xcodebuild`, then verifies the `.app` bundle, the linked uwcore
symbol, and that the source template carries no token afterwards.

**Xcode route (normal dev machine / real iPhone):** open
`UnwrittenRecorder.xcodeproj` in Xcode, pick a development team, run on
a connected iPhone. A device run uses the template (empty token)
unless the build stamps one — paste a token in ⚙️ Cloud settings, or
run `build.sh` first and build from the same checkout.

## Cloud upload (on by default)

Lessons are always saved on-device first — with Cloud on, a copy then
uploads (resumable TUS, retries on flaky links, resumes after the app
restarts) and the lesson gains a ☁ marker; tapping ↗ copies the
streamed-playback (HLS) link and offers it through the share sheet.
Cloud has **no live ingest** — this is store-then-stream, not live
broadcast. **☁ Cloud** toggles saving off (lessons stay on-device
only). Long-press a lesson to delete it from the phone *and* its cloud
copy (cloud first — if that fails, the local lesson is kept).
**Export sessions to Downloads** is shown only when Cloud is off
(offline fallback); it shares every lesson through the share sheet
(Save to Files, AirDrop, …).

No typing needed: `build.sh` stamps one random token from the signer
pool into the app, so uploads work out of the box.
`CloudUploader.swift` implements create-video, TUS upload, status
polling, and delete over `URLSession` — framework APIs only, no
third-party libraries.

## Device notes

- Permissions: camera + microphone, plus network — used *only* for
  the Cloud upload. With Cloud toggled off the app makes no network
  calls. Recording stays portrait; the screen stays awake while
  recording, and leaving the app mid-recording stops and keeps the
  take.
- Lessons live in the app's clips folder (`Documents/clips`) —
  visible in the Files app, no permission needed.
- Verified so far: clean build with zero warnings, simulator launch
  with the full UI, the permission prompt with its usage strings, the
  no-camera guard (a simulator crash in `startRunning` was found and
  fixed with a regression test), the filename/signer/link-state logic
  harness, and the repo suite. On-device shakeout (real iPhone) is
  the next step — capture sessions and mic-denied behavior vary by
  device and are the things to watch.
