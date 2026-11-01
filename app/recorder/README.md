# Unwritten Craft web app (app/recorder/)

One page per screen sharing a common core: home (`index.html`) lands
on the hub sessions with Record and Upload above them, `record.html`
is the viewfinder screen, and `upload.html` takes a video file.
`common.js` holds the vault, cloud, hub (rows open a session's detail
— write-up, corrections, chapters — with Play, Share, and Delete, as
on Android and iOS), and session rows;
`home.js` / `record.js` / `upload.js` wire each page; `app.css` holds
the dark palette. Plain HTML/CSS/JS — no dependencies, no modules
(`file://` keeps working); one tiny build step stamps a signer token
into a servable copy. Every take is saved to the on-device vault
(IndexedDB) with no download prompt, and with Cloud on (a default) a
copy is also uploaded for streamed playback. An upload rides the exact
session path of a take, so the pipeline picks it up the same way a
recording is picked up.

The layout mirrors the [native Android app](../android/): the same dark
palette, the same session rows — newest first, date + length, tap to
play inside the viewfinder, ↓ to download one file, long-press to
delete it from the device and the cloud.

There are no roles, steps, prompts, or session codes. The mentor
teaches the way they would anyway; afterwards the pipeline transcribes
the take, drafts the write-up in the mentor's words, and surfaces the
corrections. It picks the lesson as the largest media file in the
folder, so the single take is all it needs. Takes are named
`unwritten_lesson_<YYYYMMDD-HHMMSS-mmm>.<ext>`.

## How it adapts (no choices to make)

At startup the app probes the device (in-page recording? clip vault?)
and adapts on its own:

- **In-page recording available:** the record screen shows a camera
  preview, a zoom row below it (hidden when the camera reports no
  zoom range), and one **● Record** / **■ Stop** button carrying the
  running timer; saved takes list on the home screen. If the stream
  ends up video-only, a red **No
  microphone** banner says so — the mentor's words are the whole point.
  While recording, a local mic-level monitor warns after a quiet
  minute, so a dead mic is caught during the lesson, not after.
- **In-page recording unavailable** (old Safari, `file://`,
  locked-down browsers): **Record video** / **Record audio** buttons
  open the device's own camera / voice-memo apps, and the takes land
  in the same library, named the same way.

## Cloud upload (on by default)

Each video lesson is uploaded to [Bunny Stream](https://bunny.net/docs/stream)
after the local save, and the session's **↗** action shares its
streaming (adaptive HLS player) link once Cloud finishes encoding —
the link is also copied to the clipboard. Uploads are
resumable (TUS), resume after reloads, and never delay or endanger the
local take. **☁️ Cloud** toggles saving off (lessons stay on-device
only); **⚙️ Cloud settings** holds overrides; **Export sessions to
Downloads** appears only with Cloud off, as the offline fallback.
Long-pressing a session removes it from the device vault *and* the
cloud copy (cloud first — if that fails, the local lesson is kept).

No typing needed: `bash build.sh` copies the app to `dist/` (gitignored,
this is what you serve) and stamps one random token from the signer
pool into it:

```sh
cd app/recorder && bash build.sh        # stamps token #N of 10 into dist/
cd ../.. && .venv/bin/python -m http.server 8765 --directory app/recorder/dist
```

As a fallback, a library ID + API key pasted in ⚙️ settings
talks to the library directly instead of the signer. The key can manage
that one library only; it is stored in `localStorage` and sent only to
`video.bunnycdn.com`. Fine for the mentor's own device.

Notes: Cloud has **no live ingest** — this is store-then-stream, not
live broadcast. Audio-only lessons (voice-app takes) are not uploaded;
Cloud is a video platform. If the library has embed token
authentication turned on, the plain ▶ links will 403 — leave it off
(links are unguessable GUIDs) or front playback with your own page.
MP4 fallback (library → Encoding) is worth enabling if the pipeline
should later pull MP4s straight from Cloud.

## Design decisions (kept from the Oct 26 reviews)

- **IndexedDB persistence** — a lesson is not "saved" just because a
  download fired. It is written to IndexedDB when recording stops, and
  restored on reload. Downloads are only a convenience copy. (On old
  Safari the vault may be unavailable; the app detects that and says
  so.)
- **No silent lesson loss** — leaving the page mid-recording stops and
  keeps the take; an empty or failed take is reported on screen, never
  swallowed.
- **Codec order** — VP8 before VP9 (the Pixel 4 base device encodes
  VP8 in hardware, and it is the most compatible WebM codec),
  `video/mp4` included for Safari, a 2.5 Mbps cap, and a no-timeslice
  retry if `start(250)` throws (old Safari).
- **Mic failure ≠ video failure** — if the combined audio+video
  request is denied, the app retries video-only, and raises the red
  banner rather than passing silently.

## Getting it onto a device

The page needs an HTTPS (or localhost) origin for in-page camera
access. Without one, the native-app capture path still works:

1. **Durable:** GitHub Pages from this repo once it is public
   (Settings → Pages → deploy from `main`, folder `/app/recorder` —
   or serve the repo root and navigate to the path).
2. **Quick test:** download the folder (the pages plus their `.js`
   and `.css` travel together) and open `index.html`. Chrome treats
   `file://` as trustworthy; iOS Safari generally does not for camera
   access — which is exactly what the native-app buttons are for.
3. Allow camera + microphone, then **Add to Home screen** for a
   full-screen icon.

## Install as an app (PWA)

Served over HTTPS, the recorder is an installable PWA:
`manifest.webmanifest` (standalone display, dark theme matching the
Android app), home-screen
icons in `icons/`, and `sw.js`, a service worker that caches the app
shell for offline use — pages are network-first, so updates still
arrive when online. On iPhone: open the page in Safari → Share →
**Add to Home Screen**; it launches full-screen with no Safari chrome,
using the safe areas around the notch and home indicator. Lessons are
unaffected: they still live in IndexedDB and downloads, never in the
service-worker cache.
