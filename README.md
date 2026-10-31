# Unwritten Craft

**Film a lesson. Keep the corrections.**

When someone who knows a craft teaches it, the knowledge that matters most
surfaces in the corrections — *"no, like this,"* a hand reaching in to redo
yours. Those moments are where thirty years of judgment live, and they are
exactly what a written recipe leaves out. They also vanish: nobody writes
them down, and an ordinary video buries them in an hour of footage.

Unwritten Craft keeps them. Record an ordinary lesson — a mentor, a
beginner, one phone. Afterwards, the session is transcribed, the steps are
drafted into a short **write-up** in the mentor's own words, and the
moments where the mentor corrected the beginner are pulled out as
**techniques**: each one the mentor's exact words, anchored to its
clip. Together
the techniques are the **Knack**.

No protocol during the lesson. No steps to perform for the machine. Teach
the way you'd teach anyway; the system notices afterwards.

## The three core things

1. **The lesson video.** The primary source — the session itself, kept
   whole.
2. **The correction clips.** Every moment the mentor corrected the
   beginner, cut and anchored to the mentor's exact words. This is the
   extracted gold.
3. **The write-up.** A polished, sectioned document in the mentor's
   voice — transcript plus lesson-video frames, grounded in the
   lesson only, per the rule below — the lesson made usable without
   rewatching an hour of footage.

Everything else is optional. In particular, a rendered **page** — a guide
or manual assembled from these three things for someone who wasn't in the
room — may be generated later, when there is a recipient for it. It is not
part of the core, and nothing in the core depends on it.

## How it works

1. **Record.** One ordinary teaching session, filmed on a phone. The
   beginner genuinely learns — and genuinely gets things wrong.
2. **Transcribe and draft.** The pipeline transcribes the session and
   drafts the write-up strictly in the mentor's words.
3. **Keep the corrections.** The correction moments are surfaced as
   techniques, each with its clip and the mentor's exact words.

## Design rules (do not break these)

- **Grounded in the lesson only.** The write-up is drafted from the
  transcript plus frames of the lesson video itself: the transcript is
  the spine, and anything it leaves unsaid (a tool, a quantity, a
  doneness cue) is filled in from what the video plainly shows —
  never from outside knowledge. The mentor's distinctive phrasing is
  preserved verbatim. Drafts are checked
  back against the recording; a dropped "don't" inverts a step, so every
  imperative and negation in the write-up gets verified against it.
- **Corrections are the artifact.** A technique exists because the
  mentor corrected a real attempt, on camera — not because a form
  asked. If the mentor didn't correct it, it isn't a technique.
- **The mentor approves what's published.** The mentor hears and approves every
  clip before it is shared in any form. No raw session is published.
- **A byline, not a character.** The models work backstage — transcription,
  drafting, finding the moments. They do not appear in the lesson, and
  nothing pretends they were there.

## Status

Built first for personal use: capturing one baker's knack — the builder's
mother, thirty years at it — before it goes unwritten for good. Whether it
is also submitted to the Meta Global AI Developer Hackathon 2026 (Indie,
solo; submissions close Nov 4, 2026) is **undecided** and will be decided
in the coming days, based on what the real session produces.

An earlier, more elaborate design — a blind AI "apprentice" that read only
the card and committed to mechanical parameters, with its misreading drawn
onto the mentor's photo — was cut on Oct 27 after a hands-on test found
the capture flow cumbersome and outside reviewers showed the apprentice's
failures were scripted defaults rather than discoveries. See
[the design note](docs/design-simplification-2026-10-27.md). The apprentice
harness and overlay code remain in the tree as retired experiments.

This repo contains no private code from any other project, and no real
mentor data — samples are fictional.

## Repo layout

- `pipeline/` — the working pipeline, and all it does is the three
  core things: `run_pipeline.py` takes one ordinary lesson file in and
  produces the write-up and the correction clips out. `ingest.py`
  finds the lesson (largest media file in the folder) →
  `transcribe.py` (Meta speech-to-text, or local faster-whisper) →
  `draft_writeup.py` (Muse
  Spark: whole-video understanding with `MODEL_API_KEY`, else
  transcript + still frames) drafts the write-up →
  `find_corrections.py` (Spark, `prompts/correction_finder.md`)
  surfaces the correction moments, which the runner cuts from the
  lesson into `clips/` (plus SAM-tracked `highlight-NN.mp4` with the
  key). `meta_api.py` is the stdlib Files + Responses client;
  `highlight.py` renders the spotlight overlays. `make_page.py` renders the optional page/guide
  from those outputs — later, not core, and the core never calls it.
  `sam_overlay.py` and `frames.py` belong to the retired apprentice
  design. `cloud_fetch.py` pulls finished Cloud lessons so
  `run_pipeline.py --cloud` processes each into its own dir.
  See [the pipeline guide](docs/PIPELINE.md).
- `prompts/` — `writeup_drafter.md` carries the write-up rules
  (transcript spine, video fills the gaps, nothing imported);
  `correction_finder.md` defines a correction. `apprentice.md` /
  `apprentice_instruction.txt` are retired with the apprentice design.
- `harness/` — the retired apprentice process-test harness, kept for the
  record. Its tests still run (`python3 -m unittest discover -s tests`).
- `app/` — Unwritten Craft, in three forms: `app/recorder/`
  (single-file web app), `app/android/` (native port, base device:
  Pixel 4, minSdk 29), and `app/ios/` (native port, base device:
  iPhone, iOS 17+). All three open on the hub sessions with Record
  and Upload above them; recording is one screen of the app, and an
  upload rides the take path into the pipeline. An ordinary phone
  camera with no app produces exactly the same lesson file and works
  just as well. See [the Android work log](docs/android-app-worklog.md)
  and [the iOS work log](docs/ios-app-worklog.md).
- `samples/` — fictional sample write-ups and transcripts for testing.
  **Not** real mentor data.
- `docs/` — design notes, test logs, and the (undecided) submission draft.
- `CHANGELOG.md` — the running changelog, at the repo root. Every
  commit to `main` updates it in the same commit.
