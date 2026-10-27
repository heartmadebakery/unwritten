# Unwritten Craft

**Film a lesson. Keep the corrections.**

When someone who knows a craft teaches it, the knowledge that matters most
surfaces in the corrections — *"no, like this,"* a hand reaching in to redo
yours. Those moments are where thirty years of judgment live, and they are
exactly what a written recipe leaves out. They also vanish: nobody writes
them down, and an ordinary video buries them in an hour of footage.

Unwritten Craft keeps them. Record an ordinary lesson — a teacher, a
beginner, one phone. Afterwards, the session is transcribed, the steps are
drafted into a short **card** in the teacher's own words, and the moments
where she corrected the beginner are pulled out as **techniques**: each one
her exact words, anchored to its clip. Together the techniques are the
**Knack**. The result is one page: the card, the Knack, her voice, and the
beginner's attempt beside her original.

No protocol during the lesson. No steps to perform for the machine. Teach
the way you'd teach anyway; the system notices afterwards.

## How it works

1. **Record.** One ordinary teaching session, filmed on a phone. The
   beginner genuinely learns — and genuinely gets things wrong.
2. **Draft and notice.** The pipeline transcribes the session, drafts the
   card strictly in the teacher's words, and surfaces the correction
   moments as candidate techniques with their clips.
3. **Hand it on.** One shareable page: card, techniques, voice clips, the
   beginner's attempt beside the teacher's work.

## Design rules (do not break these)

- **Her words only.** The card is drafted under a stenographer rule:
  transcribe, compress, order — never add a step, quantity, or technique
  the teacher didn't say, and preserve her phrasing. Drafts are checked
  back against the audio; a dropped "don't" inverts a step, so every
  imperative and negation on the card gets verified against the recording.
- **Corrections are the artifact.** A technique exists because she
  corrected a real attempt, on camera — not because a form asked. If she
  didn't correct it, it isn't a technique.
- **She approves the page.** The teacher sees and approves the finished
  page, and only clips she has heard and approved are ever published. No
  raw session is published.
- **A byline, not a character.** The models work backstage — transcription,
  drafting, finding the moments. They do not appear in the lesson, and the
  page does not pretend they were there.

## Status

Built first for personal use: capturing one baker's knack — the builder's
mother, thirty years at it — before it goes unwritten for good. Whether it
is also submitted to the Meta Global AI Developer Hackathon 2026 (Indie,
solo; submissions close Nov 4, 2026) is **undecided** and will be decided
in the coming days, based on what the real session produces.

An earlier, more elaborate design — a blind AI "apprentice" that read only
the card and committed to mechanical parameters, with its misreading drawn
onto the teacher's photo — was cut on Oct 27 after a hands-on test found
the capture flow cumbersome and outside reviewers showed the apprentice's
failures were scripted defaults rather than discoveries. See
[the design note](docs/design-simplification-2026-10-27.md). The apprentice
harness and overlay code remain in the tree as retired experiments.

This repo contains no private code from any other project, and no real
teacher data — samples are fictional.

## Repo layout

- `pipeline/` — the working pipeline: session clips in, hand-it-on page
  out. `ingest.py` → `transcribe.py` (local faster-whisper) → `frames.py`
  → `draft_card.py` (Muse Spark, stenographer prompt) → `handiton.py`
  renders the page. See [the pipeline guide](docs/PIPELINE.md).
  `sam_overlay.py` belongs to the retired apprentice design.
- `prompts/` — `card_drafter.md` carries the stenographer rule.
  `apprentice.md` / `apprentice_instruction.txt` are retired with the
  apprentice design.
- `harness/` — the retired apprentice process-test harness, kept for the
  record. Its tests still run (`python3 -m unittest discover -s tests`).
- `app/` — capture experiments: `app/recorder/` (single-file web app) and
  `app/android/` (native Android port). Capture turned out to be a
  commodity — an ordinary phone camera is the recommended recorder; see
  [the Android work log](docs/android-app-worklog.md).
- `samples/` — fictional sample cards and transcripts for testing.
  **Not** real teacher data.
- `docs/` — design notes, test logs, and the (undecided) submission draft.
