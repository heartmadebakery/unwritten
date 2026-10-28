# Android app — work log & handoff (2026-10-26)

**Audience: whoever continues this work** (e.g. Muse on the
owner's modern PC). This file records everything that was done for the
native Android recorder, why, and what is verified — so none of it has
to be rediscovered. The app overview lives in
[`app/android/README.md`](../app/android/README.md); this file is the
history, the evidence, and the open items.

State at this log: app committed in `0c0ed9d` (19 files). Prior repo
HEAD was `b4f70b7`.

## Update — 2026-10-28: base device is now the Pixel 4

Owner's order, Oct 28: **the base device is the Google Pixel 4; the
previous old-Android (minSdk 26 / Android 8) target is retired and
no longer a design constraint.** Everything below that describes the
Oct 26 build (minSdk 26, armeabi-v7a, the API ≤28 export path, the
multi-role flow) is history — accurate for that build, superseded
now. Current state: **minSdk 29** (Android 10, the Pixel 4's launch
OS), **arm64-v8a only**, no `WRITE_EXTERNAL_STORAGE` permission
(export is MediaStore-only), the AAudio voice-recognition input
preset (API 28+) is now called, and the pre-29 export fallback is
deleted. The app's one job is unchanged and matches the docs goal
(README / `docs/DEVICES.md`): record one lesson, stop, keep the file.

## The APK

- **In this repo:** `app/android/unwritten-recorder.apk` (508,525
  bytes, debug-signed, versionCode 1 / versionName 1.0). This is the
  durable link — clone the repo and it's there.
- **Direct download (temporary):**
  https://muse.ai/files/471196432735854/3297278657123126/nek5tru1jl7ontar9akqpok0/unwritten-recorder.apk
  — expires **Oct 29, 2026, 02:47 UTC**. Muse file links expire; the
  repo copy does not.
- Install on the Pixel 4: `adb install -r app/android/unwritten-recorder.apk`
  (USB debugging on; use the PC's plain USB-C port for the phone —
  a USB4/Thunderbolt port gains
  nothing, the phone is USB 5 Gbps).

## What was built (owner's order, Oct 26)

The web recorder (`app/recorder/`) stays as the baseline fallback for
anything with a browser. The owner ordered a **native Android app** so
older devices can use their hardware efficiently: **C/C++ for the
critical paths**, **compatible back to old Android**, and **the code
written by the Muse Wonder model**.

Result: package `org.tinio.unwritten`, **minSdk 26** (Android 8.0, an
old-Android-era launch OS), target/compileSdk 34, Java 8, **no AndroidX,
no Kotlin, no third-party libraries**, programmatic UI (no layout
XML), one C++17 library (`libuwcore`). APK ≈ 0.5 MB.

### File inventory (as committed)

| File | Lines | Role |
|---|---|---|
| `app/android/app/src/main/java/org/tinio/unwritten/MainActivity.java` | 905 | Home/session/companion screens, pre-roll sync countdown (ToneGenerator beeps + white flash overlay), native-WAV dialogue mode with RMS meter, session manifest JSON export, TTS interviewer prompts, export to Downloads |
| `…/CameraEngine.java` | 1062 | Camera2 state machine: preview, photo (JPEG still), video via MediaRecorder (≤720p, 4 Mbps H.264), YUV_420_888 reader feeding luma analysis at ≤10 fps; video-only fallback when the mic is denied |
| `…/NativeCore.java` | 27 | JNI declarations for `libuwcore` |
| `…/Names.java` | 61 | The filename contract — single source of truth, identical to the web recorder's (below) |
| `…/Prefs.java` | 96 | Persisted role, session code, apprentice line, current step |
| `app/android/app/src/main/cpp/uwcore.h` / `uwcore.cpp` | 114 / 555 | C++ core: AAudio WAV recorder + luma/flash analysis |
| `…/cpp/jni_bridge.cpp` | 202 | JNI bindings (8 exported `Java_org_tinio_unwritten_NativeCore_*` symbols) |
| `…/cpp/CMakeLists.txt` | — | Builds `libuwcore` against `log` + `aaudio` |
| `app/android/app/src/main/AndroidManifest.xml` | — | CAMERA, RECORD_AUDIO, WAKE_LOCK, WRITE_EXTERNAL_STORAGE (maxSdk 28); no INTERNET |
| `app/android/build.sh` | 82 | Offline build (below) |
| `app/android/{settings.gradle, build.gradle, gradle.properties, app/build.gradle}` | — | Gradle route: AGP 8.5.2, Gradle 8.9 |

### The C++ core does two jobs

1. **AAudio WAV recorder** — native-rate capture, stereo→mono mixdown,
   integer decimation to 16 kHz, lock-free ring buffer + writer
   thread, RMS polling for the level meter. Output is exactly the
   16 kHz mono WAV the pipeline's local Whisper stage consumes.
2. **Luma analysis + flash detector** — mean luma and an 8×8 grid over
   the Y plane, plus an EMA-baseline spike detector (fires once at
   mean > baseline×1.8 + 12, 1 s refractory). Used by the Companion
   role to timestamp the lead device's sync flash into
   `sync_marks_<CODE>.json`.

### Filename contract (must not drift from the web recorder)

```
unwritten_<step>_<CODE>_<YYYYMMDD-HHMMSS-mmm>.<ext>     step clips/photos
unwritten_broll_<CODE>_<stamp>.mp4
unwritten_dialogue_<CODE>_<stamp>.wav                  native AAudio track
unwritten_<step>_<CODE>_<stamp>.jpg                    photos
session codes from Names.CODE_WORDS: PLUM BREAD OVEN RIVER MANGO
LODGE CORAL BASIL HARBOR MEADOW
```

Clips land in the app's external-files `clips/` dir
(`Android/data/org.tinio.unwritten/files/clips`), export copies a
session to `Downloads/Unwritten` (MediaStore on API 29+, legacy path
on 26–28). Because the contract matches, `pipeline/ingest.py` ingests
Android sessions unchanged — that was the point of the design.

## How the code was produced

- Three drafting passes by **Muse Wonder** (`muse exec --model
  muse-wonder-1.0`): (1) project scaffold + native core, (2) the C++
  engine + JNI bridge, (3) the Java layer (CameraEngine, then
  MainActivity + helpers). Prompts/outputs were kept in the build
  sandbox, not in this repo.
- Integration, fixes, and verification by the maintainer agent
  (Muse Spark session, Oct 26). Two compile fixes were needed:
  1. `uwcore.cpp`: `AAudioStreamBuilder_setInputPreset` is unavailable
     below API 28 (marked so in the NDK headers). Removed — it's a
     hint only and GENERIC is the default. This is exactly the class
     of bug the old-Android target exists to catch.
  2. `MainActivity.java`: the `column(View)` helper was called with
     the Activity at 4 sites; signature widened to `Context`.
  One build-system fix: Wonder's `app/build.gradle` used the plugins
  DSL while the root used buildscript style — switched to
  `apply plugin: 'com.android.application'`.
  One integration fix: the manifest gained `package=` + versionCode/
  versionName attributes (AGP injects these from `namespace` on the
  Gradle route; the manual route needs them in the manifest itself).

## Build routes — read this before rebuilding

### Gradle does NOT run in the Muse sandbox (diagnosed, don't re-litigate)

Every `gradle assembleDebug`/`help` failed in ~4 s with "Could not
receive a message from the daemon": daemons started, greeted, and
listened on 127.0.0.1, the client connected and dispatched, then the
receive failed ~24 ms later and the daemon never logged a build.
Ruled out with tests: loopback TCP itself (a plain-Java socket server
accepted cross-process connections fine), process supervision, OOM.
With `org.gradle.daemon=false` the build ran in-process and then
failed at dependency download: Gradle's HTTP client got
`ProtocolException: The server failed to respond with a valid HTTP
response` from the sandbox egress proxy — while `curl` to the same
URLs returned 200. `sdkmanager` fails the same way (its HTTPS
tunneling throws `NoSuchElementException`). Conclusion: this
sandbox's proxy speaks something curl tolerates and Java HTTP clients
don't. **On a normal machine (a modern PC) none of this applies** —
the Gradle files are standard AGP 8.5.2 and are expected to just work.

### The route that produced the committed APK: `app/android/build.sh`

Fully offline, no Gradle: CMake+ninja per ABI (arm64-v8a,
armeabi-v7a) → aapt2 link → javac (source/target 8) → d8 → zip
(dex + `lib/<abi>/libuwcore.so`) → zipalign → apksigner with a
locally generated **debug** keystore (`app/android/debug.keystore`,
git-ignored, generated on first run). Sandbox toolchain used
(all under a tools dir, downloaded as zips because sdkmanager
can't): Temurin JDK 17, SDK platform android-34, build-tools
34.0.0, NDK 26.1.10909125, AGP — n/a, Gradle 8.9 (for reference),
system CMake 3.28.3, ninja 1.12.1. Gotcha found en route: the NDK
r26 prebuilt dir ships GNU make but **no ninja binary**; build.sh
takes ninja from PATH. Another: `/tmp` on the sandbox is a 512 MB
tmpfs — the 1.2 GB NDK zip must be downloaded to a real disk.

### Continuing on a modern PC (recommended)

1. Clone this repo (it's private: `tinio/unwritten`).
2. Easiest: Android Studio → open `app/android/` → let it install
   SDK 34 / build-tools 34 / NDK r26 → Build APK. Or from Muse
   in `app/android/`: `gradle assembleDebug` (Gradle 8.9, JDK 17).
3. Or reuse `./build.sh` — set `JAVA_HOME`, `ANDROID_HOME`,
   `ANDROID_NDK_HOME` to your installs; needs cmake + ninja
   on PATH.
4. `local.properties` in the repo points at the sandbox's SDK path —
   it's git-ignored going forward; Android Studio/Gradle will
   regenerate it. Delete it if the path confuses a local build.

## Verification performed (Oct 26, sandbox)

- Clean end-to-end `build.sh` run: both ABIs compiled, javac clean,
  dex built, APK signed.
- `apksigner verify` — OK.
- `aapt2 dump badging` — package `org.tinio.unwritten`, versionCode 1,
  **sdkVersion 26**, targetSdkVersion 34, permissions exactly
  CAMERA / RECORD_AUDIO / WAKE_LOCK / WRITE_EXTERNAL_STORAGE
  (maxSdk 28), launchable activity `.MainActivity`.
- APK contents: `classes.dex` (71 KB) + `lib/arm64-v8a/libuwcore.so`
  (856 KB) + `lib/armeabi-v7a/libuwcore.so` (705 KB) + signed manifest.
- Dex contains all five app classes (+ inner classes); `llvm-nm -D`
  on the .so shows all 8 `Java_org_tinio_unwritten_NativeCore_*`
  exports.

## NOT done yet — the honest gaps

- **No on-device run.** There is no emulator in the sandbox (no KVM),
  so nothing has executed on a real Pixel 4 yet. First shakeout
  checklist (streamlined flow — one job, no roles or steps): install;
  grant/deny each permission and confirm recording still behaves;
  record one lesson and confirm it is saved as
  `unwritten_lesson_<timestamp>.mp4`; Export and confirm the file
  appears in `Downloads/Unwritten`; run the pipeline on it and
  confirm it transcribes.
- **Gradle route untested** (see above — sandbox-only blocker).
  The first build on a modern PC may surface small AGP complaints; the manifest
  `package=` attribute coexists with `namespace` by design.
- **No app icon** — the launcher entry uses the default. Add one
  before any public submission.
- **Debug-signed only.** No release keystore / Play signing exists;
  create one (and keep it OUT of this repo) before distribution
  beyond sideloading.
- Camera2 session combinations and AAudio behavior vary per device —
  if the Pixel 4 misbehaves, those two subsystems are where to look
  first (CameraEngine's session setup; uwcore's stream config).
