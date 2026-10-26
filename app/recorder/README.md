# The Apprentice recorder (app/recorder/index.html)

A single-file web app that turns whatever device is at hand into the
"robot apprentice" for a teacher session. Plain HTML/CSS/JS — no build
step, no dependencies, no network calls. Everything is recorded and
stored **on the device only** (IndexedDB + a download copy of each
clip).

## Three roles (v6) — see `docs/DEVICES.md` for the full guide

At startup the app probes the device (in-page recording? clip vault?
robot voice? screen size?), displays what it found, and suggests a
role; the holder can override, and the choice persists.

- **Interviewer** — runs the whole guided session: spoken prompts,
  filming, an editable apprentice line for step 3, a session manifest
  export. On big screens: wide layout + keyboard (←/→, R). The
  Legion-class laptop is the reference device.
- **Recorder** — the same four steps, minimal. Where in-page recording
  doesn't exist (old Safari on an iPhone 7, `file://`, locked-down
  browsers), per-step buttons open the native camera / voice-memo
  apps and the takes land in the library named by step.
- **Companion** — a second perspective: session code + one-tap sync
  (3-2-1, beep + screen flash at zero = the alignment marker), then
  one long take as a second camera (`unwritten_broll_<CODE>_…`) or an
  audio-only dialogue track (`unwritten_dialogue_<CODE>_…`).

## The four captures (interviewer / recorder)

1. **Show me** — film the teacher doing the move once, unexplained.
2. **Teach me** — film the explanation; the screen supplies the
   worn-tool opening question and the "index card" framing, warns the
   holder not to help fill the gaps, and holds all other questions for
   later (wisdom timing — Claude review fix, Oct 26).
3. **I try** — the screen shows the blind apprentice's commitment for
   the holder to read aloud; film the teacher's reaction/correction.
   The line is an editable field on the home screen: paste the real
   apprentice output for the session's craft — the bread line is only
   the prefilled example.
4. **Your try** — the wisdom questions open this step (asked only now,
   after her reaction), then the student attempts the move from the
   card only; photograph both results side by side.

Clips are named `unwritten_<step>_<time>.webm/mp4`, photos `.jpg`,
listed in an on-page library with a ✅ once persisted to IndexedDB.

## Design decisions (from a Muse Wonder review, Oct 26)

- **IndexedDB persistence** — a clip is not "saved" because a download
  fired; it is written to IndexedDB on stop and restored on reload.
  Downloads are just a convenience copy. (On old Safari the vault may
  be unavailable; the app detects that and says so.)
- **No silent clip loss** — while recording, the first tap on Next/Back
  only stops and keeps the clip; navigation never eats a take. The stop
  handler captures the step/chunks/mime at record-start, so a late
  `onstop` can never mislabel a clip with the next step's name.
- **Interruption-safe** — `MediaRecorder.onerror` surfaces a visible
  warning; leaving the page mid-recording stops and flushes; the wake
  lock is re-acquired on return.
- **Old-hardware codec order** — VP8 before VP9 (the Pixel 2 encodes
  VP8 far more kindly), `video/mp4` included for Safari, 2.5 Mbps cap,
  and a no-timeslice retry if `start(250)` throws (old Safari).
- **Mic failure ≠ video failure** — if the combined audio+video request
  is denied, it retries video-only; a video-only stream raises a red
  "No microphone" banner rather than passing silently (steps 2–3 are
  her words).
- **Fallback is a feature** — where in-page recording is unavailable,
  the native-app capture path is the designed route for that device,
  presented as such, with real file extensions preserved.

## Getting it onto a device

The page needs an HTTPS (or localhost) origin for in-page camera
access; without one, the native-app capture path still works:

1. **Durable:** GitHub Pages from this repo once it is public
   (Settings → Pages → deploy from `main`, folder `/app/recorder` —
   or serve the repo root and navigate to the path).
2. **Quick test:** download `index.html` and open it — Chrome treats
   `file://` as trustworthy; iOS Safari generally doesn't for camera
   access, which is exactly what the Recorder role's native-app
   buttons are for.
3. Allow camera + microphone, then **Add to Home screen** for a
   full-screen icon. Turn the robot voice off if the room is loud —
   the same instructions are on screen.
