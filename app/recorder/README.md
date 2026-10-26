# The Apprentice recorder (app/recorder/index.html)

A single-file web app that turns a spare phone into the "robot apprentice"
for a teacher session. Built for a Pixel 2 (Chrome, Android 11) but it is
plain HTML/CSS/JS — no build step, no dependencies, no network calls.
Everything is recorded and stored **on the device only** (IndexedDB +
a download copy of each clip).

## What it does

Prop the phone where it can see the teacher's hands, tap **Start a
session**, and it walks the holder through the four captures that mirror
the product, with on-screen instructions and a spoken robot voice
(text-to-speech, toggleable):

1. **Show me** — film the teacher doing the move once, unexplained.
2. **Teach me** — film the explanation; the screen supplies the worn-tool
   opening question and the "index card" framing, and warns the holder
   not to help fill the gaps.
3. **I try** — the screen shows the *real* blind-apprentice commitment
   from the Day-1 harness test (90°, moderate, center — what Wonder,
   given only the card, said it would do) for the holder to read aloud;
   film the teacher's reaction/correction.
4. **Your try** — film the student attempting the move from the card
   only, then photograph both results side by side.

Clips are named `unwritten_<step>_<time>.webm/mp4`, photos `.jpg`, listed
in an on-page library with a ✅ once persisted to IndexedDB.

## Design decisions (from a Muse Wonder review, Oct 26)

- **IndexedDB persistence** — a clip is not "saved" because a download
  fired; it is written to IndexedDB on stop and restored on reload.
  Downloads are just a convenience copy.
- **No silent clip loss** — while recording, the first tap on Next/Back
  only stops and keeps the clip; navigation never eats a take. The stop
  handler captures the step/chunks/mime at record-start, so a late
  `onstop` can never mislabel a clip with the next step's name.
- **Interruption-safe** — `MediaRecorder.onerror` surfaces a visible
  warning; leaving the page mid-recording stops and flushes; the wake
  lock is re-acquired on return.
- **Old-hardware codec order** — VP8 before VP9 (the Pixel 2 encodes VP8
  far more kindly), 2.5 Mbps cap.
- **Mic failure ≠ video failure** — if the combined audio+video request
  is denied, it retries video-only before showing the fallback.
- **Fallback** — if in-page recording is unavailable, a capture input
  hands off to the native camera app and the file still lands in the
  library with its real extension.

## Getting it onto the phone

The page needs an HTTPS (or localhost) origin for camera access:

1. **Durable:** GitHub Pages from this repo once it is public
   (Settings → Pages → deploy from `main`, folder `/app/recorder` —
   or serve the repo root and navigate to the path).
2. **Quick test:** download `index.html` to the phone and open it in
   Chrome — `file://` is a trustworthy origin in Chrome, so the camera
   may work directly; if not, the in-app camera-app fallback still
   captures everything.
3. On the phone: allow camera + microphone, then **Add to Home screen**
   for a full-screen icon. Turn the robot voice off if the kitchen is
   loud — the same instructions are on screen.
