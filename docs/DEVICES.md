# Devices — one recorder, one job

The recorder ([`app/recorder/index.html`](../app/recorder/index.html) — still
a single file, no build step, no network; the Android app in
[`app/android/`](../app/android/) is the same recorder natively) has
exactly one job: **record one lesson, stop, keep the file.** No roles,
no steps, no session code, nothing performed for the machine — the
teacher teaches the way she would anyway, and the pipeline works
afterwards on the single take (it picks the largest media file in the
lesson folder as the lesson; see [`docs/PIPELINE.md`](PIPELINE.md)).

At startup the page probes what the device can actually do — in-page
recording, a clip vault (IndexedDB) — and adapts on its own. There is
nothing to choose.

## What any device does

- **In-page recording works** (modern phone, laptop): point the camera
  at her hands, press **Record the lesson**, press **Stop** at the end.
  A red "No microphone" banner appears if the take would be silent —
  her words are the whole point, so silence is never passed over
  quietly.
- **In-page recording does not exist** (old Safari on an old iPhone,
  `file://` pages, locked-down browsers): it does not fail. The buttons
  open the device's own camera / voice-memo apps instead, and the take
  lands in the same library. An old phone is a perfectly good recorder;
  it just needed the app to stop demanding APIs it does not have.

Every take is named `unwritten_lesson_<timestamp>.<ext>` and saved on
the device only (IndexedDB vault plus a download copy on the web;
the app clips folder plus Export to `Downloads/Unwritten` on Android).

## Which device

The base device is a **Google Pixel 4** propped at her hands — that
is the reference setup, and the Android app's floor (Android 10 /
API 29, arm64). A laptop webcam works for the web recorder; an old
phone works through its own camera app. A second device is no longer part of the design — one
lesson file is what the pipeline consumes, and an ordinary phone camera
with no recorder app at all produces exactly that file too.

## Honest limits

- In-page recording needs a secure context (HTTPS, or a local file the
  browser trusts). Where that fails, the native-app path is the
  designed route, not an error.
- The clip vault (IndexedDB) is best-effort on old Safari. Downloads
  still happen, and the library marks what is saved where.
