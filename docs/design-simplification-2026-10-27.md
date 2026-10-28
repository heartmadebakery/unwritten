# Design note — the simplification (Oct 27, 2026)

## What changed

The design is now: **film a lesson, keep the corrections, one page.** The
teacher teaches a real beginner (the builder) the way she would anyway. The
pipeline works afterwards: transcribe, draft the card in her words, surface
the correction moments as techniques, render the page.

## Why

- The owner's hands-on test of the recorder/interviewer flow (Oct 27):
  "too cumbersome — too many steps and protocols," and the open question of
  whether the AI was offering something real or was bolted on at the expense
  of the experience.
- Two outside critiques commissioned the same day (Claude, primary review;
  Muse Wonder, second) converged: the blind apprentice's failures came from
  hardcoded defaults in its prompt, so it reported what the card omitted
  rather than discovering anything; a plain checklist captures much of the
  same delta; and every claim rested on fictional sessions the team had
  invented, while the one real session hadn't happened.

## What was cut

- The blind apprentice as a staged step (its prompts and harness remain in
  the tree as retired experiments).
- The SAM overlay as the hero visual; Muse Image consequence renders
  (never built).
- The recorder protocol and index-card capture ceremony. The web and
  Android recorders are frozen; an ordinary phone camera is the recorder.
- "Correct once" as a ceremony, the 10-parameter commitment contract, and
  the Craft/Lineage tagging question during capture.

## What survives

- Corrections as the artifact; each correction is a **technique**; together
  they are the **Knack**.
- The stenographer drafting rule (her words only), now with the card's
  imperatives and negations verified against the audio.
- The hand-it-on page: card, techniques with clips, her voice, the
  beginner's attempt beside her original.
- Consent: she approves the finished page; only clips she has heard and
  approved are published; no raw session is ever published.
- The demo title form, with the count set by the real session:
  "Mom's Bread: N techniques, a knack never written down."

## Addendum (Oct 27, later) — three core things; the page is optional

The owner narrowed the focus further the same day. The core is exactly
three things: **the lesson video, the correction clips, the write-up.**
The page is demoted: it may be generated later as a guide or manual for
other people's consumption, when there is a recipient — it is optional,
and the core does not depend on it.

First measurement of the core: `docs/core-test-2026-10-27.md` — a
fictional but realistic lesson transcript with planted corrections and
distractors, scored write-up drafting and correction capture against
ground truth, including a keyword-regex baseline.

## Addendum (Oct 27, evening) — the code now follows it

The simplification first landed in the docs; the owner asked whether
all the code followed, and it didn't — `run_pipeline.py` still ran the
old seven stages. Aligned the same evening:

- `pipeline/run_pipeline.py` rewritten: lesson in → transcribe →
  write-up → corrections (+ clips cut from the lesson). It no longer
  invokes the apprentice, SAM, or the page, and no longer requires a
  page to succeed. It now calls `find_corrections.py`, which the old
  runner never did.
- `pipeline/ingest.py` rewritten: classification by extension only;
  the lesson is the largest media file in the folder. Recorder step
  names (`teach`/`react`/`attempt`/…) are gone.
- `pipeline/draft_writeup.py`: the recorder-era `--wisdom` Q&A input is
  removed; it drafts the write-up from the lesson transcript alone.
  `prompts/writeup_drafter.md` simplified to match (session-protocol
  rules — post-reaction Q&A, worn-tool opening question — removed).
- `pipeline/transcribe.py` now also writes the timestamped transcript
  the correction finder consumes.
- `pipeline/make_page.py` rewritten as the optional page generator over
  core outputs only (write-up + corrections + clips); its apprentice
  overlay section is gone.
- `harness/`, `pipeline/sam_overlay.py`, `pipeline/frames.py` carry
  RETIRED headers and are invoked by nothing in the core flow.

## Addendum (Oct 27, night) — naming made consistent

At the owner's order, every living name now matches what the thing is:
`pipeline/draft_card.py` → `pipeline/draft_writeup.py`,
`prompts/card_drafter.md` → `prompts/writeup_drafter.md`,
`pipeline/handiton.py` → `pipeline/make_page.py`, and
`samples/sample_card*.md` → `samples/sample_writeup*.md`, with all
references in living code, docs, and samples updated (including the
submission draft, which now says "write-up" throughout). The retired
apprentice-era code and the dated Oct 26 test logs keep the word
"card" — in that design the artifact genuinely was a card, and those
files are the historical record of it.

## Undecided

Whether this is submitted to the hackathon at all. The project is being
built for personal use first; the submission decision follows the real
session, in the coming days. `docs/submission-answers.md` is kept truthful
to the simplified build in case the decision is yes.
