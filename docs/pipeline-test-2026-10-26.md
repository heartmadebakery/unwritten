# Pipeline test — 2026-10-26 (synthetic session, end to end)

First full run of `pipeline/run_pipeline.py`. The session is synthetic
in every part, assembled from project assets:

- `show` — storyboard beat 1 (cartoon clip)
- `teach` — TTS voice reading Rosa's explanation (the fictional
  transcript from `samples/`, spoken verbatim)
- `react` — TTS voice reading a scripted correction
- photo — a generated top-down dough photo (which also served as the
  "attempt" photo and the overlay's canvas)

Wall time ≈ 2 min 52 s on this VM, including three fresh Wonder calls
and CPU SAM inference.

## What came out

- **Transcription (local Whisper, base/int8)** — near-verbatim on clean
  TTS audio, including "It cuts how I expect, you know?" and the worn-
  tool answer. Two errors, both instructive:
  1. **It dropped a "don't"**: "don't let it sit there thinking about
     itself" came back as "Let it sit there thinking about itself" — a
     meaning inversion, and Spark's stenographer discipline faithfully
     carried it into the card as step 8. *Negation is Whisper's most
     dangerous failure mode for this product.* Mitigation is already in
     the design — the teacher sees and confirms the card — but this run
     is why that confirmation is a required step, not a courtesy.
  2. In the react clip, "Don't saw at it" became "Don't sod it either"
     in the mined tricks draft. Charming, wrong, and exactly why mined
     tricks are labeled DRAFT for teacher confirmation.
- **Card (Spark, from the audio transcript)** — faithful, zero added
  technique, worn-tip quote preserved. Two cosmetic notes: the
  teacher's name is absent (the audio never contained it — the card
  title came out as "# — the card"), and Spark split compound lines
  into 8 steps where the hand-fed version had 5.
- **Apprentice (Wonder ×3)** — all runs parsed; every step at or near
  maximum silence again, consistent with the Day-1 harness result.
- **SAM overlay** — mask score 0.981, covering 23.1% of the frame; the
  mask edge tracks the boule exactly (see
  `docs/previews/pipeline-synthetic-overlay.png`). The pinned label is
  step 1's sentence because all steps tied at silence 14 and the
  tie-break takes the first — for the real demo, the pinned sentence
  should be the step the teacher actually corrected, not the first
  tied step. Noted as the pipeline's next refinement.
- **Hand-it-on page** — rendered with card, overlay, tricks draft, and
  the attempt photo placeholder grid.

## Verdict

The chain the user asked for exists and runs: recordings → transcript →
card → blind apprentice → gap report → SAM overlay → page, with the two
Muse roles wired in and nothing about the teacher's audio leaving the
machine except the transcript text Spark drafts from. The remaining
unknowns are the ones only the real session answers: Whisper on a real
voice in a real kitchen, and a real correction to pin.
