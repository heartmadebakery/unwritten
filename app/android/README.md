# Unwritten Recorder — native Android app

The native port of the [web recorder](../recorder/). Same single job —
record one lesson, stop, keep the file — and the same filename contract
(`unwritten_lesson_<timestamp>.mp4`), so lessons from this app drop
straight into the existing pipeline (`pipeline/ingest.py`) unchanged.
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
The prebuilt APK is `unwritten-recorder.apk` in this directory.

## Why native, and what's in C++

The web recorder is the baseline fallback (it works anywhere a browser
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
the single-screen UI (built programmatically — no layout XML): preview,
one Record/Stop button, the lessons list, and export to Downloads.

## Layout

```
settings.gradle, build.gradle, gradle.properties   (Gradle route)
build.sh                                           (offline route — see below)
app/build.gradle
app/src/main/AndroidManifest.xml
app/src/main/cpp/        CMakeLists.txt, uwcore.{h,cpp}, jni_bridge.cpp
app/src/main/java/org/tinio/unwritten/
    MainActivity.java    single screen: preview, record, lessons, export
    CameraEngine.java    Camera2 + MediaRecorder + YUV/still readers
    NativeCore.java      JNI bridge to libuwcore
    Names.java           the filename contract (single source of truth)
unwritten-recorder.apk   prebuilt debug-signed APK (sideload-ready)
```

## Building

**Offline / sandbox route (what produced the bundled APK):**

```sh
./build.sh   # needs JDK 17, SDK platform 34 + build-tools 34, NDK r26, cmake, ninja
```

`build.sh` runs CMake per ABI, then aapt2, javac, d8, zipalign, and
apksigner — no Gradle, no network. It generates a local `debug.keystore` on
first run (git-ignored) and writes `unwritten-recorder.apk`.

**Gradle route (normal dev machine):** open this directory in Android
Studio, or run `gradle assembleDebug` with the same SDK/NDK installed.
Note: the manifest carries `package=` + version attributes for the
manual route; AGP's `namespace` says the same thing.

## Optional: Bunny Stream upload

Off by default; toggle under **Bunny streaming (optional)** on the one
screen. Lessons are always saved on-device first — with Bunny on, a
copy then uploads (resumable TUS, retries on flaky links, resumes
after the app restarts) and the lesson gains a ☁▶ marker; tapping it
opens the streamed-playback (HLS) link, which is also copied to the
clipboard and offered via **Share Bunny link**. Bunny has **no live
ingest** — this is store-then-stream, not live broadcast.

Authorisation mirrors the web recorder: either a **signer URL**
(recommended — the tiny Cloudflare Worker in
[`app/bunny-signer/`](../../bunny-signer/) holds the library API key)
or the **library API key on-device** (stored in app-private
SharedPreferences, sent only to Bunny). `BunnyUploader.java` implements
create-video, TUS upload, and status polling over a raw `SSLSocket` —
framework APIs only, no third-party libraries, and no
`HttpURLConnection` PATCH trap on older Android.

## Device notes

- Permissions: CAMERA + RECORD_AUDIO, plus INTERNET — used *only* for
  the optional Bunny upload. With Bunny off (the default) the app
  makes no network calls. Export uses MediaStore Downloads (API 29+),
  which needs no storage permission.
- Lessons live in the app's external files dir (`Android/data/
  org.tinio.unwritten/files/clips`) — visible over USB, no permission
  needed. **Export** copies all lessons to `Downloads/Unwritten`.
- Verified so far: clean build, signature, badging (sdkVersion 29),
  JNI symbol table. On-device shakeout (Pixel 4) is the next step —
  Camera2 session combinations and AAudio behavior vary by device and
  are the two things to watch.
