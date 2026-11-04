# Android app — work log & handoff (2026-10-26)

**Audience: whoever continues this work** (e.g. Muse on the
owner's modern PC). This file records everything that was done for the
native Android recorder, why, and what is verified — so none of it has
to be rediscovered. The app overview lives in
[`app/android/README.md`](../app/android/README.md); this file is the
history, the evidence, and the open items.

State at this log: app committed in `0c0ed9d` (19 files). Prior repo
HEAD was `b4f70b7`.

## Update — 2026-11-02: bug sweep (device install pending)

`MainActivity`: camera errors (raised on the camera thread) reset
the Record button on the UI thread — before, the view write threw
inside the engine's catch and a failed start stranded "■ Stop"; the
take MediaRecorder is writing (`liveTake`) is no longer a session row
(it cached a blank duration for good, could be tapped or deleted
mid-take, and a backlog sweep could upload it half written); picked
uploads copy under a `.part` name and rename in when complete;
`.mkv` uploads list (they were copied and uploaded but invisible);
Export and the per-row ↓ copy on the background pool (an hour-long
lesson on the UI thread is an ANR). `CameraEngine`: a take that fails
to start (setup, `start()`, or an unconfigurable session) deletes the
empty file `prepare()` created (`discardFailedTake`), and the stop
callback reports an empty take like iOS and the web. 7 new
`AndroidBugSweepTests`.
`build.sh` exit 0, token-stamped, template restored. **Not yet
installed:** the Pixel 4's wireless-debugging port had rotated
(connection refused). Next: `adb connect` the new port, `adb install
-r`, launch, record a take while another uploads (row appears only
after Stop, with its duration), Export with Cloud off.

## Update — 2026-11-01: parity sync + Android-at-home redesign

Owner's order: bring Android to feature parity with the web and iOS
apps, in Android idioms. Parity: hub playback moved out of the
record viewfinder into its own dialog player (MP4 then HLS, Cloud
embed last — watching a lesson never opens the camera, like iOS);
REC + elapsed badge over the viewfinder; zoom row hides with no
zoom range; ✕ joins the player controls; ⟳ refreshes the hub (no
SwipeRefreshLayout without AndroidX); "Nothing yet." device empty
state; permission denial points to Settings. Idioms: `Theme.Material`
ActionBar with per-screen titles + Up off record (the custom
"‹ Home" button is deleted); Record is one filled red action;
session/hub rows ripple; hub detail is an elevated rounded card;
48dp row targets; adaptive amber-dot launcher icon (`res/`,
`build.sh` gained the `aapt2 compile` res step — closes the icon
open item below). Covered by 12 new `AndroidSyncTests` (325/325
green, 41/41 hub checks); `build.sh` exit 0, token-stamped,
icon confirmed in badging. On-device shakeout DONE same day (Pixel 4
`flame` over tailnet wireless adb — 39871 is the connect port, the
pairing port was separate; the previous install's foreign debug key
forced an uninstall, so the 4 on-phone takes were pulled to /tmp
first and pushed back after — prefs wiped, so they show 📱
device-only until re-uploaded). Verified: launch, live hub rows,
permissions deferred past entry, 12 s take
(`unwritten_lesson_20261101-035127-906.mp4`), REC badge + red Stop,
signer creds + TUS 201 + bytes in logcat, export to
Downloads/Unwritten with Cloud off, long-press delete removed the
Stream copy first then the file, restored takes list with real
durations (8:26 on the 261 MB lesson). One fix from the shakeout:
zoom row now hides with no camera yet (pre-permission dead UI).

## Update — 2026-11-01: bug-hunt fixes (take with the next commit)

Deep review found six, all fixed test-first (`CameraEngineTests`
is new): cloud link writes synchronize on `cloudLinkLock` (upload
callbacks persist off the UI thread); `configured()` needs a token
in signer mode (URL-alone no longer counts, same contract as
`canUpload`); a sub-700ms stop-throw deletes its partial take
instead of listing/uploading a corrupt lesson; a camera
error/disconnect/configure-failure fails a queued start loudly
instead of wedging later takes on "already queued"; surface
resizes and luma attach no longer rebuild the session mid-take.
Rebuilt and re-verified on the Pixel 4 (record, upload,
cloud-first delete).

Merged the same day with the source-only native-feel pass below:
its Material foundation (cards, RippleDrawables, Switch, action-bar
camera menu, primary buttons) stands; this sync's verified behaviors
(REC badge, zoom-hide, player ✕, hub refresh + HLS dialog player,
Settings denial, launcher icon) were kept on top, plus Referer on hub
streams and scroll-to-viewfinder on device playback from the iOS
playback fix. Rebuilt, re-tested, and re-verified on the Pixel 4 in
the merge.

## Update — 2026-11-01: native-feel UI pass (source-only)

- Goal "apps feel native": `Theme.Material` + ActionBar (title, up
  arrow, camera-switch menu action), themed system bars, rounded
  ripple buttons, a Record primary button, a `Switch` for Cloud, card
  lists with ripple rows, 48dp targets, empty states. The `‹ Home`
  button and `📷/🤳` toggle are gone (up arrow / menu item replace them).
- **Not compiled, not built, not run:** no Android SDK on the machine
  that did this (this Mac has no JDK either, so not even a `javac`
  syntax pass — only the contract tests in `AndroidNativeFeelTests`
  and a manual read-through). `unwritten-craft.apk` is
  therefore STALE relative to the source. First job for the next
  machine with the SDK: `bash app/android/build.sh`, install on the
  Pixel 4, look at every screen, fix what the compiler/device finds.
  (Done in the merge above: built, installed, and shaken out on the
  Pixel 4 the same day.)

## Update — 2026-10-29: quiet-minute check, camera toggle, mic banner

- Parity with the web recorder: a `MediaRecorder.getMaxAmplitude()`
  poll raises the same "Quiet for a while" banner after a full
  quiet minute; a front/back toggle switches lenses between takes;
  a denied/broken mic raises the red video-only banner (previously
  invisible — errors went to a hidden status line).
- Not rebuilt here (no Android SDK on this machine); covered by
  `test_recorder_streamlined.py` contract tests only.

## Update — 2026-10-29: in-app hub

- A Hub section lists published sessions from the signer store
  (`HubClient`: list/get/delete), with inline detail (write-up,
  corrections, chapters), mp4 playback in the viewfinder (browser
  fallback for embed-only sessions), share, and cloud-first delete
  (video first, then the hub record).
- Switch-on checklist lives in the iOS worklog ("Still to do (hub
  switch-on)"); same backend serves both apps.
- First real build 2026-10-30 (borrowed Mac, JDK 17 + SDK 34 + NDK
  26.1.10909125 via `build.sh`): caught two compile breaks the hub
  commit shipped with — `INK` in `MainActivity` (iOS name; Android's
  identical constant is `TEXT`) and a duplicate `get(String)` in
  `HubClient` (private worker renamed `getRaw`). Prebuilt APK
  refreshed. macOS note: NDK r26 ships no ninja — `build.sh`
  falls back to a Linux path, so put the SDK cmake's `ninja`
  on PATH. Not installed on a device yet.

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

Result: package `com.heartmadebakery.unwritten`, **minSdk 26** (Android 8.0, an
old-Android-era launch OS), target/compileSdk 34, Java 8, **no AndroidX,
no Kotlin, no third-party libraries**, programmatic UI (no layout
XML), one C++17 library (`libuwcore`). APK ≈ 0.5 MB.

### File inventory (as committed)

| File | Lines | Role |
|---|---|---|
| `app/android/app/src/main/java/com/heartmadebakery/unwritten/MainActivity.java` | 905 | Home/session/companion screens, pre-roll sync countdown (ToneGenerator beeps + white flash overlay), native-WAV dialogue mode with RMS meter, session manifest JSON export, TTS interviewer prompts, export to Downloads |
| `…/CameraEngine.java` | 1062 | Camera2 state machine: preview, photo (JPEG still), video via MediaRecorder (≤720p, 4 Mbps H.264), YUV_420_888 reader feeding luma analysis at ≤10 fps; video-only fallback when the mic is denied |
| `…/NativeCore.java` | 27 | JNI declarations for `libuwcore` |
| `…/Names.java` | 61 | The filename contract — single source of truth, identical to the web recorder's (below) |
| `…/Prefs.java` | 96 | Persisted role, session code, apprentice line, current step |
| `app/android/app/src/main/cpp/uwcore.h` / `uwcore.cpp` | 114 / 555 | C++ core: AAudio WAV recorder + luma/flash analysis |
| `…/cpp/jni_bridge.cpp` | 202 | JNI bindings (8 exported `Java_com_heartmadebakery_unwritten_NativeCore_*` symbols) |
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
(`Android/data/com.heartmadebakery.unwritten/files/clips`), export copies a
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
- `aapt2 dump badging` — package `com.heartmadebakery.unwritten`, versionCode 1,
  **sdkVersion 26**, targetSdkVersion 34, permissions exactly
  CAMERA / RECORD_AUDIO / WAKE_LOCK / WRITE_EXTERNAL_STORAGE
  (maxSdk 28), launchable activity `.MainActivity`.
- APK contents: `classes.dex` (71 KB) + `lib/arm64-v8a/libuwcore.so`
  (856 KB) + `lib/armeabi-v7a/libuwcore.so` (705 KB) + signed manifest.
- Dex contains all five app classes (+ inner classes); `llvm-nm -D`
  on the .so shows all 8 `Java_com_heartmadebakery_unwritten_NativeCore_*`
  exports.

## Update — 2026-11-03: session parts (javac only)

A lesson in several videos reads as one hub session. `HubClient`:
`tie(List)`, `untie(id)`, `queueFetchJob(url, joinTo)`.
`MainActivity`: `joinToVideoId`/`joinToTitle` (set by the hub
detail's **Add a part**, cleared on Home or *Make it its own
session*), a `joinBannerView()` atop Record/Upload/Fetch from link,
`markJoin` on each saved take/upload, `tieCloudPart` from the
uploader's `onSession` (three tries, retried by `cloudResumePending`),
hub rows with "N parts • M processing", and a detail with a Parts
list (play one / Untie), Add a part, a tie picker, Play running part
to part (`setOnCompletionListener`), "Part N ·" chips, share of every
part link, and a delete that names every part. Verified: `javac
-source 8 -target 8` against platform-34 `android.jar` compiles the
sources clean. **Not built into an APK or run on a device** — no
build-tools/NDK/token pool on that host; the committed APK predates
this. Build with `app/android/build.sh` and walk a two-part session
on the Pixel 4 before shipping.

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
