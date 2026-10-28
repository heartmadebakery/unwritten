# The recorder (app/recorder/index.html)

A single-file web app with one job: **record one lesson, stop, keep the
file.** Plain HTML/CSS/JS — no build step, no dependencies, no network
calls. Everything is recorded and stored **on the device only**
(IndexedDB, plus a download copy of each take).

There are no roles, steps, prompts, or session codes. The teacher
teaches the way she would anyway; afterwards the pipeline transcribes
the take, drafts the write-up in her words, and surfaces the
corrections. It picks the lesson as the largest media file in the
folder, so the single take is all it needs. Takes are named
`unwritten_lesson_<YYYYMMDD-HHMMSS-mmm>.<ext>`.

## How it adapts (no choices to make)

At startup the app probes the device (in-page recording? clip vault?)
and adapts on its own:

- **In-page recording available:** a camera preview, one **Record the
  lesson** / **Stop** button with a running timer, and a lessons
  library below. If the stream ends up video-only, a red **No
  microphone** banner says so — her words are the whole point.
- **In-page recording unavailable** (old Safari, `file://`,
  locked-down browsers): **Record video** / **Record audio** buttons
  open the device's own camera / voice-memo apps, and the takes land
  in the same library, named the same way.

## Optional: Bunny Stream upload (added Oct 28)

Off by default. Tap **☁️ Bunny** under the camera toggle, fill in a
signer URL (recommended — see below) *or* the library ID + API key, and
tap again to turn it on. From then on, each video lesson is also
uploaded to [Bunny Stream](https://bunny.net/docs/stream) after the
local save, and a **▶ Watch** link (adaptive HLS player) appears under
the lesson when Bunny finishes encoding. Uploads are resumable (TUS),
resume after reloads, and never delay or endanger the local take.

Two ways to authorise uploads, per Bunny's own security guidance:

- **Signer (recommended):** deploy the tiny Cloudflare Worker in
  [`app/bunny-signer/`](../bunny-signer/) once — it holds the library
  API key, so no key ever lives in this page. Paste its URL (plus the
  optional signer token) into the Bunny panel.
- **Key on device (simpler):** paste the library ID + API key. The key
  can manage that one library only; it is stored in `localStorage` and
  sent only to `video.bunnycdn.com`. Fine for the teacher's own device.

Notes: Bunny has **no live ingest** — this is store-then-stream, not
live broadcast. Audio-only lessons (voice-app takes) are not uploaded;
Bunny is a video platform. If the library has embed token
authentication turned on, the plain ▶ links will 403 — leave it off
(links are unguessable GUIDs) or front playback with your own page.
MP4 fallback (library → Encoding) is worth enabling if the pipeline
should later pull MP4s straight from Bunny.

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
2. **Quick test:** download `index.html` and open it. Chrome treats
   `file://` as trustworthy; iOS Safari generally does not for camera
   access — which is exactly what the native-app buttons are for.
3. Allow camera + microphone, then **Add to Home screen** for a
   full-screen icon.

## Install as an app (PWA)

Served over HTTPS, the recorder is an installable PWA:
`manifest.webmanifest` (standalone display, warm theme), home-screen
icons in `icons/`, and `sw.js`, a service worker that caches the app
shell for offline use — pages are network-first, so updates still
arrive when online. On iPhone: open the page in Safari → Share →
**Add to Home Screen**; it launches full-screen with no Safari chrome,
using the safe areas around the notch and home indicator. Lessons are
unaffected: they still live in IndexedDB and downloads, never in the
service-worker cache.
