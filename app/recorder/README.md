# The Apprentice recorder (app/recorder/index.html)

A single-file web app that turns whatever device is at hand into the
"robot apprentice" for a teacher session. Plain HTML/CSS/JS — no build
step, no dependencies, no network calls. Everything is recorded and
stored **on the device only** (IndexedDB, plus a download copy of each
clip).

## Three roles (v6) — see `docs/DEVICES.md` for the full guide

At startup the app probes the device (in-page recording? clip vault?
robot voice? screen size?), shows what it found, and suggests a role.
The holder can override the suggestion, and the choice persists.

- **Interviewer** — runs the whole guided session: spoken prompts,
  filming, an editable apprentice line for step 3, and a session manifest
  export. On big screens it uses the wide layout plus keyboard control
  (←/→ steps, R records). A modern laptop is the reference device.
- **Recorder** — the same four steps, minimal. Where in-page recording
  does not exist (old Safari on an old iPhone, `file://`, locked-down
  browsers), per-step buttons open the native camera / voice-memo apps,
  and the takes land in the library named by step.
- **Companion** — a second perspective. It takes a session code plus a
  one-tap sync (3-2-1 countdown; a beep and a screen flash at zero are the
  alignment marker), then records one long take: either a second camera
  angle (`unwritten_broll_<CODE>_…`) or an audio-only dialogue track
  (`unwritten_dialogue_<CODE>_…`).

## The four captures (interviewer / recorder)

1. **Show me** — film the teacher doing the move once, unexplained.
2. **Teach me** — film the explanation. The screen supplies the worn-tool
   opening question and the "index card" framing, warns the holder not to
   help fill the gaps, and holds all other questions for later (wisdom
   timing — Claude review fix, Oct 26).
3. **I try** — the screen shows the blind apprentice's commitment for the
   holder to read aloud; film the teacher's reaction and correction. The
   line is an editable field on the home screen: paste the real apprentice
   output for the session's craft — the bread line is only the prefilled
   example.
4. **Your try** — the wisdom questions open this step (asked only now,
   after her reaction). Then the student attempts the move from the card
   only. Finally, photograph both results side by side.

Clips are named `unwritten_<step>_<SESSIONCODE>_<YYYYMMDD-HHMMSS-mmm>.webm/mp4`,
photos `.jpg`, and native-app takes `unwritten_<step>_camera-app_<CODE>_…` /
`_voice-app_…`. Every name carries the session code and a full timestamp,
so takes never collide in the vault. Clips are listed in an on-page library,
with a ✅ once persisted to IndexedDB. **↻ New session** on the home screen
rotates the code and starts fresh (old clips stay in the vault under their
own code).

## Design decisions (from a Muse Wonder review, Oct 26)

- **IndexedDB persistence** — a clip is not "saved" just because a download
  fired. It is written to IndexedDB when recording stops, and restored on
  reload. Downloads are only a convenience copy. (On old Safari the vault
  may be unavailable; the app detects that and says so.)
- **No silent clip loss** — while recording, the first tap on Next/Back
  only stops and keeps the clip; navigation never eats a take. The stop
  handler captures the step, chunks, and mime type at record-start, so a
  late `onstop` can never mislabel a clip with the next step's name.
- **Interruption-safe** — `MediaRecorder.onerror` surfaces a visible
  warning; leaving the page mid-recording stops and flushes; the wake
  lock is re-acquired on return.
- **Old-hardware codec order** — VP8 before VP9 (old Android hardware encodes
  VP8 far more kindly), `video/mp4` included for Safari, a 2.5 Mbps cap,
  and a no-timeslice retry if `start(250)` throws (old Safari).
- **Mic failure ≠ video failure** — if the combined audio+video request
  is denied, the app retries video-only. A video-only stream raises a red
  "No microphone" banner rather than passing silently (steps 2–3 are her
  words).
- **Fallback is a feature** — where in-page recording is unavailable,
  the native-app capture path is the designed route for that device,
  presented as such, with real file extensions preserved.

## Getting it onto a device

The page needs an HTTPS (or localhost) origin for in-page camera
access. Without one, the native-app capture path still works:

1. **Durable:** GitHub Pages from this repo once it is public
   (Settings → Pages → deploy from `main`, folder `/app/recorder` —
   or serve the repo root and navigate to the path).
2. **Quick test:** download `index.html` and open it. Chrome treats
   `file://` as trustworthy; iOS Safari generally does not for camera
   access — which is exactly what the Recorder role's native-app
   buttons are for.
3. Allow camera + microphone, then **Add to Home screen** for a
   full-screen icon. Turn the robot voice off if the room is loud —
   the same instructions are on screen.
