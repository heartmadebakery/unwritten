# Devices — capture on any device

Unwritten Craft is one app in three forms: the web app
([`app/recorder/index.html`](../app/recorder/index.html) — still a
single file, plus a small build step that stamps in its Cloud
credentials), the native Android app ([`app/android/`](../app/android/)),
and the native iOS app ([`app/ios/`](../app/ios/)). All three open on
the hub sessions with Record and Upload above them; recording is one
screen of the app, not a separate app. No roles, no steps, no session
code, nothing performed for the machine — the mentor teaches the way
they would anyway, and the pipeline works afterwards on the session
(it picks the largest media file in the lesson folder as the lesson;
see [`docs/PIPELINE.md`](PIPELINE.md)). An upload rides the exact
session path of a take, so the pipeline treats both alike.

At startup the web app probes what the device can actually do —
in-page recording, a clip vault (IndexedDB) — and adapts on its own.
There is nothing to choose.

## What any device does

- **In-page recording works** (modern phone, laptop): on the home
  screen press **● Record**, point the camera at the mentor's hands,
  press **■ Stop** at the end. A red "No microphone" banner appears
  if the take would be silent — the mentor's words are the whole
  point, so silence is never passed over quietly.
- **In-page recording does not exist** (old Safari on an old iPhone,
  `file://` pages, locked-down browsers): it does not fail. The
  buttons open the device's own camera / voice-memo apps instead, and
  the take lands in the same on-device list. An old phone is a
  perfectly good recorder; it just needed the app to stop demanding
  APIs it does not have.

Every take is named `unwritten_lesson_<timestamp>.<ext>` and saved on
the device first (IndexedDB vault on the web, the app clips folder on
native); with Cloud on, a copy is also uploaded for streamed
playback, and Export moves sessions out (`Downloads/Unwritten` on
Android, the share sheet on iOS, per-file download on the web app).

## Which device

The base device is a **Google Pixel 4** propped at the mentor's hands —
that is the reference setup, and the Android app's floor (Android 10 /
API 29, arm64). A laptop webcam works for the web app; an iPhone runs
the native iOS app (iOS 17+); an old phone works through its own
camera app. A second device is no longer part of the design — one
lesson file is what the pipeline consumes, and an ordinary phone
camera with no app at all produces exactly that file too.

## Honest limits

- In-page recording needs a secure context (HTTPS, or a local file the
  browser trusts). Where that fails, the native-app path is the
  designed route, not an error.
- The clip vault (IndexedDB) is best-effort on old Safari. Downloads
  still happen, and a ⚠ on the row marks what never reached the
  vault, so nothing is silently memory-only.
