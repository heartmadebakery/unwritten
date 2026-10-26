# Process test — 2026-10-26 (Day 1), Muse stack run

The full Step 1 → Step 2 pipeline exercised end to end with the hackathon's
own models, replacing the earlier Llama stand-in run (kept in
`docs/process-test-2026-10-26.md` for history; a non-Muse backend proves
the harness but counts for nothing toward the required stack).

## Setup

- **Card drafting — Muse Spark** (`muse-spark-1.3` via Muse,
  contributor mode), constrained by `prompts/card_drafter.md`, working from
  the fictional transcript in `samples/sample_transcript.md`.
- **Apprentice — Muse Wonder** (`muse-wonder-1.0`), three fresh
  `muse exec` calls via `harness/apprentice_muse.py`. Each call's entire
  input was `prompts/apprentice_instruction.txt` + the drafted card.
  Wonder never saw the transcript.
- Analysis: `harness/run_test.py`. All 3 responses parsed (no truncations).

## What Spark did with the transcript

The drafted card (`samples/sample_card_spark.md`) obeyed the stenographer
rules: Rosa's phrasing survives verbatim — *"don't saw at it, it drags"*,
*"you want it to tear a little, that's how you know"*, *"don't let it sit
there thinking about itself"* — and Spark added **nothing**: no angle, no
depth, no timing, no flour quantity, despite all of those being standard
baking knowledge it certainly has. The worn-lame answer is recorded as the
opening quote, unelaborated. This is the Round-3 "Spark leaks" fix working
as intended.

## What the apprentice did with the card

Silence scores (max 14): steps 1, 2, 3, 5 scored **14** — every physical
parameter at the geometric-neutral default in all three runs. The card
says *what*, never *how*, and Wonder — following the contract literally —
did not smuggle in technique: it would score at 90°, moderate force,
center application, because the card never said otherwise.

The one exception is instructive. Step 4 — *"you want it to tear a little,
that's how you know"* — is the only step where Rosa gave a sensory
stopping condition, and it is the only step where the apprentice's
`stopping_condition` left the default in every run ("when it tears a
little"). Its `size` diverged across runs ("a little" vs the default):
"A little" is doing real work in her sentence, and no two readers —
human or model — cash it out the same way. That divergence is a Trick
waiting for a number.

## Verdict

The mechanic holds on the real stack: a constrained Spark keeps the gaps
open, a blind Wonder falls into exactly those gaps, and the gap report
points at them step by step. Still unproven, by design: a real teacher,
a real card, a real correction. That is the Day-2 test.
