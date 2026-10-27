# Unwritten Recorder — native Android app

The native port of the [web recorder](../recorder/). Same guided
session, same roles, same filename contract — so clips from this app
drop straight into the existing pipeline (`pipeline/ingest.py`)
unchanged. Built for old hardware: **minSdk 26** (Android 8.0 — an
old-Android-era OS from 2017). No AndroidX, no Kotlin, no third-party
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

- **AAudio WAV capture (C++)** — the companion's dialogue track is
  recorded by a native AAudio engine: device-rate capture, stereo→mono
  mixdown, integer decimation to 16 kHz PCM, written straight to a WAV
  file from a writer thread. No GC pauses, no browser resampling
  surprises, and the WAV is exactly what the local Whisper stage wants.
- **Luma / sync-flash detection (C++)** — camera YUV frames are
  analyzed natively (mean luma plus an 8×8 grid, plus an EMA flash
  detector). Per-frame pixel work is the classic place managed code
  drops frames on 2017 hardware; in C++ it takes a few milliseconds at
  640×480. Detections land in `sync_marks_<CODE>.json` next to the clips.
- **Hardware encoding** — video goes through Camera2 + MediaRecorder
  (H.264/AAC, capped at 720p / 4 Mbps: plenty for hands-and-work
  footage, and kind to old storage and batteries).

Managed Java handles what it is good at: the Camera2 state machine,
the three-role UI (built programmatically — no layout XML), the
four-step flow, TTS prompts for the interviewer role, and export to
Downloads.

## Layout

```
settings.gradle, build.gradle, gradle.properties   (Gradle route)
build.sh                                           (offline route — see below)
app/build.gradle
app/src/main/AndroidManifest.xml
app/src/main/cpp/        CMakeLists.txt, uwcore.{h,cpp}, jni_bridge.cpp
app/src/main/java/org/tinio/unwritten/
    MainActivity.java    roles, 4-step session, companion sync, export
    CameraEngine.java    Camera2 + MediaRecorder + YUV/still readers
    NativeCore.java      JNI bridge to libuwcore
    Names.java           the filename contract (single source of truth)
    Prefs.java           role / session code / apprentice line / step
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

## Device notes

- Permissions: CAMERA + RECORD_AUDIO (plus WRITE_EXTERNAL_STORAGE only on
  API ≤ 28, and only when exporting). No INTERNET permission — the app
  never makes a network call.
- Clips live in the app's external files dir (`Android/data/
  org.tinio.unwritten/files/clips`) — visible over USB, no permission
  needed. **Export** copies the current session's clips to
  `Downloads/Unwritten`.
- Companion sync: recording starts *before* the 3-2-1 countdown, so
  the beep + full-screen flash at zero are inside the take — the same
  pre-roll design as the web recorder.
- Verified so far: clean build, signature, badging (sdkVersion 26),
  JNI symbol table. On-device shakeout (old Android phone) is the next step —
  Camera2 session combinations and AAudio behavior vary by device and
  are the two things to watch.
