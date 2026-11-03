# Unwritten Craft web app (app/recorder/)

One page per screen sharing a common core: home (`index.html`) holds
Record and Upload actions with the published hub last, `record.html`
is the viewfinder screen with cloud, device sessions, and a debug
Advanced settings link below, `upload.html` takes a video file or points to `link.html`, the
Fetch from link page.
`common.js` holds the vault, cloud, hub (rows open a session's detail
— write-up, corrections, chapters — with Play, Share, and Delete, as
on Android and iOS), and session rows;
`home.js` / `record.js` / `upload.js` / `link.js` wire each page; `app.css` holds
the Hearth design language ([docs/DESIGN.md](../../docs/DESIGN.md)). Plain HTML/CSS/JS — no dependencies, no modules
(`file://` keeps working); one tiny build step stamps a signer token
into a servable copy. Every take is saved to the on-device vault
(IndexedDB) with no download prompt, and with Cloud on (a default) a
copy is also uploaded for streamed playback. An upload rides the exact
session path of a take, so the pipeline picks it up the same way a
recording is picked up. Pasting a link instead of a file works too:
direct video files download in the page, while YouTube and
watch-page links queue to the pipeline (`POST /fetch/jobs`), which
fetches them with yt-dlp, processes them like a recording, and
publishes them to the hub.

The layout mirrors the [native Android app](../android/) and the iOS
app: the same Hearth tokens, the same session rows — newest first, a
frame of the video with its length, the date, the status in a chip,
tap to play inside the viewfinder, ↓ to save one file, long-press to
delete it from the device and the cloud.

It is drawn as a friendly phone app, not a web page: warm paper (and
a matching dark set that follows `prefers-color-scheme`), a greeting
and large title on home over two action tiles (Record in ember,
Upload video), lesson cards with warm cover tiles for the hub, a
translucent top bar with a back chevron on Record and Upload (camera
switch on the right), the shutter in a dock with the status line
under it, a real **Cloud** switch, and words in chips for every
upload state. `common.js` tags the page `ios` or `android` so the CSS
can nudge type, radii and the header per platform; touch targets are
48px, keyboard focus is visible, and reduced motion turns off the
press squish.

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
  zoom range), and one round shutter-style Record / Stop button (the running
  timer rides the REC badge); saved takes list on the home screen. If the stream
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
local take. the **Cloud** switch turns saving off (lessons stay on-device
only); **Advanced settings** holds overrides; **Export sessions to
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

As a fallback, a library ID + API key pasted in Advanced settings
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
`manifest.webmanifest` (standalone display, the warm canvas as its
theme colour, with light/dark `theme-color` metas on every page), home-screen
icons in `icons/`, and `sw.js`, a service worker that caches the app
shell for offline use — pages are network-first, so updates still
arrive when online. On iPhone: open the page in Safari → Share →
**Add to Home Screen**; it launches full-screen with no Safari chrome,
using the safe areas around the notch and home indicator. Lessons are
unaffected: they still live in IndexedDB and downloads, never in the
service-worker cache.
