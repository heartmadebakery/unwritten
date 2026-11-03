# Unwritten Craft — native Android app

Unwritten Craft for Android: home lands on the hub sessions with
Record and Upload above them, and recording is one screen of the app.
Same filename contract (`unwritten_lesson_<timestamp>.mp4`), so
lessons from this app drop straight into the existing pipeline
(`pipeline/ingest.py`) unchanged.
Base device: **Google Pixel 4**. **minSdk 29** (Android 10 — the
OS the Pixel 4 shipped with in 2019); the app is arm64-v8a only,
matching the Pixel 4. No AndroidX, no Kotlin, no third-party
libraries — framework APIs and one C++ library only. The APK is
~0.5 MB.

Coded by Muse Wonder (three drafting passes), integrated and
build-verified by the project maintainer agent.

**Continuing this work?** Read
[`docs/android-app-worklog.md`](../../docs/android-app-worklog.md)
first — full history, build-route diagnosis, verification evidence,
and the open items (on-device shakeout, app icon, release signing).
The prebuilt APK is `unwritten-craft.apk` in this directory.

## Why native, and what's in C++

The web app is the baseline fallback (it works anywhere a browser
does, including iPhones). Native Android wins where the web cannot:

- **Hardware encoding** — video goes through Camera2 + MediaRecorder
  (H.264/AAC, capped at 720p / 4 Mbps: plenty for hands-and-work
  footage, and kind to storage and batteries).
- **Native core (C++, retained)** — `libuwcore` still builds and links:
  CameraEngine's per-frame luma analysis (mean luma plus an 8×8 grid)
  runs natively when a listener is attached. The AAudio dialogue-track
  and sync-flash paths that used it belonged to the retired companion
  mode and are no longer driven by the UI.

Managed Java handles what it is good at: the Camera2 state machine and
the four-screen UI (built programmatically — no layout XML): home
(greeting, Record and Upload video action tiles, the hub last), upload
(Choose a video or Fetch from link), link (the paste-a-link field) and record (preview with REC badge, an auto-hiding zoom
pill, the shutter in a dock, in-viewfinder playback with ▶/⏸/✕, a
`Switch` for Cloud, device sessions, advanced link). It draws the
Hearth design language ([docs/DESIGN.md](../../docs/DESIGN.md)) in
Material idioms without AndroidX: `Theme.DeviceDefault.DayNight` with
a palette chosen at start from the system night mode (light status
and navigation bars on the warm canvas), the ActionBar stepping aside
on home for an in-content large title and returning with the up arrow
on Record (camera switch as a menu action), elevated cards, ripple
rows and tiles that dip when pressed, line icons drawn in code
(`Glyphs.java` — no icon assets), video-frame thumbnails probed off the
UI thread, status chips, 48dp targets, haptics on Record/Stop, and
friendly empty states. The hub detail is an elevated listing-style
card (cover banner, ember Play pill, quote cards for corrections), and
hub playback runs in its own dialog player (MP4 then HLS with the
embed URL as `Referer`, Cloud embed last) so watching a published
lesson never opens the camera. The launcher icon is an adaptive cream
record glyph on ember (`res/`, minSdk 29 needs no legacy PNGs).

## Layout

```
settings.gradle, build.gradle, gradle.properties   (Gradle route)
build.sh                                           (offline route — see below)
app/build.gradle
app/src/main/AndroidManifest.xml
app/src/main/cpp/        CMakeLists.txt, uwcore.{h,cpp}, jni_bridge.cpp
app/src/main/res/         drawable/uw_icon_fg.xml, mipmap-anydpi-v26/ icons, values/colors.xml
app/src/main/java/org/tinio/unwritten/
    MainActivity.java    home + record screens, upload picker + link queue, cloud, hub
    Glyphs.java          the line icons, drawn in code (Hearth)
    TinyFileProvider.java read-only content:// clips for external players
    CameraEngine.java    Camera2 + MediaRecorder + YUV/still readers
    NativeCore.java      JNI bridge to libuwcore
    Names.java           the filename contract (single source of truth)
unwritten-craft.apk      prebuilt debug-signed APK (sideload-ready)
```

## Building

**Offline / sandbox route (what produced the bundled APK):**

```sh
./build.sh   # needs JDK 17, SDK platform 34 + build-tools 34, NDK r26, cmake, ninja
```

`build.sh` runs CMake per ABI, then aapt2, javac, d8, zipalign, and
apksigner — no Gradle, no network. It generates a local `debug.keystore` on
first run (git-ignored) and writes `unwritten-craft.apk`.

**Gradle route (normal dev machine):** open this directory in Android
Studio, or run `gradle assembleDebug` with the same SDK/NDK installed.
Note: the manifest carries `package=` + version attributes for the
manual route; AGP's `namespace` says the same thing.

## Cloud upload (on by default)

Lessons are always saved on-device first — with Cloud on, a copy then
uploads (resumable TUS, retries on flaky links, resumes after the app
restarts) and the lesson gains a ☁▶ marker; tapping it opens the
streamed-playback (HLS) link, which is also copied to the clipboard
and offered via **Share Cloud link**. Cloud has **no live ingest** —
this is store-then-stream, not live broadcast. **☁ Cloud** toggles
saving off (lessons stay on-device only). Long-press a lesson to
delete it from the phone *and* its cloud copy (cloud first — if that
fails, the local lesson is kept). **Export lessons to Downloads** is
shown only when Cloud is off (offline fallback); **Share Cloud link**
only when Cloud is on. Pasting a link instead queues it to the
pipeline fetcher (`POST /fetch/jobs`), which downloads YouTube and
watch pages with yt-dlp, processes them like a take, and publishes
them to the hub.

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

No typing needed: `build.sh` stamps one random token from the signer
pool into the APK (`token #N of 10` in the build log), so uploads work
out of the box.
`CloudUploader.java` implements create-video, TUS upload, status
polling, and delete over a raw `SSLSocket` — framework APIs only, no
third-party libraries, and no `HttpURLConnection` PATCH trap on older
Android.

## Device notes

- Permissions: CAMERA + RECORD_AUDIO, plus INTERNET — used *only* for
  the Cloud upload. With Cloud toggled off the app makes no network
  calls. Export uses MediaStore Downloads (API 29+),
  which needs no storage permission.
- Lessons live in the app's external files dir (`Android/data/
  org.tinio.unwritten/files/clips`) — visible over USB, no permission
  needed. **Export** copies all lessons to `Downloads/Unwritten`.
- Verified so far: clean build, signature, badging (sdkVersion 29),
  JNI symbol table, and the Nov 1 on-device shakeout (Pixel 4, wireless
  adb): install, launch, live hub rows, 12 s take saved under the
  contract name, REC badge, cloud upload (signer creds + TUS 201),
  cloud-off export to Downloads, cloud-first delete of both copies,
  and four restored takes listed with real durations. Camera2/AAudio
  stayed healthy throughout; first-take start lags ~2–3 s on a cold
  camera thread.
