# Devices — one recorder, three roles

The recorder ([`app/recorder/index.html`](../app/recorder/index.html) — still
a single file, no build step, no network) adapts to whatever device it is
opened on. At startup it probes what the device can actually do: in-page
recording, camera/mic access, a clip vault (IndexedDB), a robot voice (speech
synthesis), and screen size. It shows the result on the home screen and
suggests a role. The person can override the suggestion; the choice persists.

## The roles

- **Interviewer** — *this device runs the session.* The full guided flow: it
  speaks the prompts, films each step, carries the editable apprentice line
  for the React step, and exports a session manifest. On a big screen it
  switches to the wide layout with keyboard control (←/→ steps, R records).
  The best device in the room gets this job. A modern laptop is
  ideal: a real webcam, real speakers for the robot voice — and later, the
  same machine can run the processing pipeline
  ([`docs/PIPELINE.md`](PIPELINE.md)) as the studio.
- **Recorder** — *just capture.* The same four steps with the fuss removed
  (no robot voice). On devices where in-page recording does not exist — old
  Safari on an old iPhone, `file://` pages, locked-down
  browsers — it does not fail. Instead, each step gets **Record video** /
  **Record audio** buttons that open the device's own camera and voice-memo
  apps, and the takes land in the library named by step, exactly as if they
  had been recorded in-page. An old phone is a perfectly good recorder; it
  just needed the app to stop demanding APIs it does not have.
- **Companion** — *a second perspective.* Prop a spare device elsewhere:
  across the room as a **second camera** (the wide angle — her posture, the
  whole workspace, the student attempting), or near the teacher as the
  **dialogue mic** (audio only — the cleanest track for transcription, away
  from oven fans and running water). The companion takes the session code
  shown on the lead device, then one tap runs a 3-2-1 sync: a beep and a
  full-screen flash at zero, then recording starts. The beep-plus-flash pair
  is the alignment marker — every device's take carries the same zero point.
  Files are named `unwritten_<dialogue|broll>_<CODE>_<time>`, so the pipeline
  knows what they are.

## Suggested fleet

| Device | Role | Why |
|---|---|---|
| Modern PC | Interviewer + studio | Big screen, webcam, speakers; later runs the pipeline |
| Modern phone | Interviewer or lead Recorder | Capable in-page recording + clip vault |
| Old Android phone | Recorder | VP8-friendly in-page recording; propped at her hands |
| Old iPhone | Recorder (native apps) or Companion | No reliable in-page recording; excellent camera/mic via its own apps |
| Any old tablet/phone | Companion | A second angle or the dialogue mic is pure gain |

## Work areas travel too

Nothing in the session is kitchen-shaped. "The move" can be scoring a boule,
wrapping lumpia, or scrubbing a bathroom grout line the way someone who has
done it for thirty years does it. The worn-object opening works on a scorched
pan or a beloved brush alike. And the apprentice line is a fill-in field
precisely so a bathroom-cleaning session reads the apprentice's *actual*
commitment for that craft — never the bread line by accident.

## Honest limits

- In-page recording needs a secure context (HTTPS, or a local file the
  browser trusts). Where that fails, the native-app path is the designed
  route, not an error.
- The clip vault (IndexedDB) is best-effort on old Safari. Downloads still
  happen, and the library marks what is saved where.
- Companion takes are single long recordings by design. Alignment is by the
  sync marker, and the pipeline transcribes the dialogue take as the
  session's clean-audio source.
