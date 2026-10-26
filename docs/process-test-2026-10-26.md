# Process test — 2026-10-26 (Day 1)

First end-to-end exercise of the core mechanic, text-only, against the
FICTIONAL sample card in `samples/sample_card.md`. No real teacher data.

## Setup

- Apprentice: `meta-llama/llama-3.3-70b-instruct` via OpenRouter, standing
  in for the Meta open-weight apprentice the shipped app will call. Each
  run was a fresh call whose entire context was the contract in
  `prompts/apprentice.md` plus the card text. Nothing else.
- Harness: `harness/run_test.py`, 7 unit tests passing
  (`python3 -m unittest discover -s tests`).

## Result

- The sample card specifies almost no physical parameters, and the
  apprentice came back at the geometric-neutral default on essentially
  every parameter of every step — silence score 14/14 on steps 1–3,
  12 on step 4 (it echoed the card's own "till it's done" as the stopping
  condition). The gap report lights up exactly where the card is silent,
  which is the mechanic working as designed.
- The apprentice's `in_my_words` sentences also show mild training leakage
  in the *prose* ("probably to control how it expands during baking") even
  while its *parameters* stayed honest — worth watching, but the parameter
  commitments are the contract that matters.

## Robustness note

1 of 3 apprentice calls returned truncated JSON (the provider cut the
completion short at ~100 tokens despite a 2500-token budget; a retry of
the same call completed). The harness skips unparseable responses with a
warning instead of failing the run. The shipped app needs the same
contract: retry a truncated apprentice call, never proceed on partial
commitments.

## Cost

Five apprentice calls total (3 + 2 retries): ≈ $0.002.

## Not yet proven (by design)

The real Day-2 gate needs a real teacher: an actual card drafted from a
real explanation, fresh apprentice runs against it, and the teacher
producing a filmable correction that traces to a card silence. That test
waits on the teacher session.
