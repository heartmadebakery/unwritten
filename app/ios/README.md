# Unwritten Craft — native iOS app

Unwritten Craft for iOS: home lands on the hub sessions with Record
and Upload above them, and recording is one screen of the app. Same
filename contract (`unwritten_lesson_<timestamp>.mp4`), so lessons
from this app drop straight into the existing pipeline
(`pipeline/ingest.py`) unchanged.
Base device: **iPhone** (2019-class, the iOS counterpart to the
Pixel 4). **iOS 17+**, iPhone only. No storyboards, no third-party
libraries — SwiftUI + AVFoundation and one C++ core only.

**Continuing this work?** Read
[`docs/ios-app-worklog.md`](../../docs/ios-app-worklog.md)
first — full history, build verification, simulator evidence, and the
open items (on-device shakeout, release signing). On-device
note (Oct 29): the first real-iPhone run hit a `startRunning`-inside-
`beginConfiguration` throw — fixed by committing the config before
starting the session, proven by a test take on an iPhone 14 Pro.

## Why native, and what's in C++

The web app is the baseline fallback (it works anywhere a browser
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
UI (built programmatically — no storyboards). It draws the same
Hearth design language as the web and Android apps
([docs/DESIGN.md](../../docs/DESIGN.md)) from iOS parts: dynamic
light/dark colours that follow the system, SF Pro Rounded titles, a
`NavigationStack` home (a greeting, Record and Upload video action
tiles, and the hub's
lessons on warm cover tiles, pull to refresh) that pushes Upload (Choose a video from Photos or Files, then a
Fetch from link field, then previous attempts) and Record (an
inset-grouped list: the rounded viewfinder with zoom, the shutter in a
dock with haptics, the Cloud toggle on a sage badge, and the device
sessions — a frame of the video, the date, a status chip; a swipe
deletes — plus a
full-screen native player for a tapped session, camera switch in the toolbar, and an Advanced settings link
opening the Cloud settings sheet) and hub sessions (their own player, never the camera,
plus the write-up, corrections and chapters, with Share/Delete in the
toolbar). The system back button and edge swipe leave Record exactly
like the old ‹ Home did: a live take stops and is kept, and the camera
parks. Upload offers the Photos picker and Files.

## Layout

```
UnwrittenRecorder.xcodeproj/         (project + shared scheme)
build.sh                             (stamp + simulator build — see below)
UnwrittenRecorder/
    Info.plist             camera/mic usage, Files sharing, orientations (iPhone portrait; iPad all four)
    Assets.xcassets        AppIcon (same ember record glyph as the web PWA icon)
    UnwrittenRecorderApp.swift   app entry
    ContentView.swift      home + record screens, upload picker + link queue, playback
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
unless the build stamps one — run `build.sh` first and build from the
same checkout (⚙️ Cloud settings only shows the build values).

**TestFlight (the iOS install link):** an iPhone cannot install a
downloaded app the way Android installs the APK, so the iOS twin of the
web footer's APK link is a TestFlight public link.

```sh
TESTFLIGHT=1 DEVELOPMENT_TEAM=<team id> ./build.sh
```

This archives a token-stamped Release build with a fresh build number
(UTC `yyyymmddHHMM`) and uploads it to App Store Connect. It signs in
with the Mac's Xcode account, or with an App Store Connect API key when
`ASC_KEY_ID`, `ASC_ISSUER_ID` and `ASC_KEY_PATH` are set (keep the
`.p8` in the git-ignored `.certs/`). One-time setup in App Store
Connect: an app record for `com.heartmadebakery.unwritten`, then TestFlight →
an external testing group → Enable Public Link. The first external
build goes through Beta App Review.

## Cloud upload (on by default)

Lessons are always saved on-device first — with Cloud on, a copy then
uploads (resumable TUS, retries on flaky links, resumes after the app
restarts) and the lesson gains a ☁ marker; its share button copies the
streamed-playback (HLS) link and offers it through the share sheet.
Cloud has **no live ingest** — this is store-then-stream, not live
broadcast. The **Cloud** toggle turns saving off (lessons stay on-device
only). Touch and hold a lesson for its context menu (Play, Share Cloud
link, Retry upload, Save a copy, Delete), or swipe it to delete it from
the phone *and* its cloud copy (cloud first — if that fails, the local
lesson is kept). Pasting a link instead queues it to the pipeline
fetcher (`POST /fetch/jobs`), which downloads YouTube and watch pages
with yt-dlp, processes them like a take, and publishes them to the hub.

**Parts — one session in several videos.** Open a hub session and
use **Add a part** (Record / Upload / Link): the capture screen says
"Adds a part to …" (with *Make it its own session* to back out), and
every take, upload or link saved there becomes that session's next
part — tied the moment its upload has a video id (retried until it
lands), or, for a link, when the pipeline finishes it. **Tie a
session to this one** joins another hub session (with its own parts)
onto the end. A tied session lists once in the hub (total length,
"N parts", parts still processing), plays its parts in order, shows
each part's write-up under a "Part N" heading with corrections and
chapters tagged by part, and each part can be played on its own or
untied. Deleting a tied session names every part and deletes them
all. The signer owns the model (`/hub/parts`, see
[the signer README](../cloud-signer/README.md)).
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
  calls. The iPhone records portrait; the iPad rotates all four ways and films what you see upright, in a centered readable column; the screen stays awake while
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
