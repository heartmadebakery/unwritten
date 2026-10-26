# Flexibility test — 2026-10-26 (tart + lumpia)

Ordered by the user: the system must not be bread-shaped. It has to
serve a pecan tart lesson and a lumpia lesson as readily as scoring a
boule, extract **wisdom** — not just steps — from elder teachers in a
short session, and stay scoped to the home (trades/manufacturing are a
closing line, not a second product).

## What changed to make it true

1. **The apprentice contract went craft-agnostic.** Seven motion
   parameters became ten across three families — motion (`angle_deg`,
   `force`, `force_location`, `duration_s`, `repetitions`), material
   (`tool`, `size`, `amount`), heat (`temperature`). A tart lives and
   dies by temperature and timing; lumpia by amount and tightness; the
   old set could not even *ask* about the first two.
2. **The card gained a wisdom layer.** `prompts/card_drafter.md` now
   files the teacher's judgment — how she knows, what goes wrong, what
   the years changed, who taught her — under `## What <Teacher> knows`,
   under the identical stenographer rule: her words only, or the
   section doesn't exist.
3. **The recorder asks for it.** The Teach step now ends with four
   fixed wisdom questions (How do you know when it's right? / What
   goes wrong the other way? / What do you do differently now? / Who
   taught you this?). Fixed and few on purpose: maximal extraction from
   a short session without interviewing the tacit knowledge away before
   the apprentice can miss it.

## The test

Two new fictional sessions (`samples/sample_transcript_tart.md`,
`samples/sample_transcript_lumpia.md`), Spark-drafted cards
(`samples/sample_card_tart.md`, `samples/sample_card_lumpia.md`),
three fresh Wonder apprentice runs each (tart: 2 of 3 parseable — one
response carried extra data past the JSON and was skipped per the
standing retry rule; lumpia: 3 of 3).

**The wisdom capture worked verbatim.** Nadia's card carries "If it
doesn't move at all, you went too far — it turns to candy and it'll
break your teeth," "Forty years to learn to toast the nuts," and Aunt
Rose's church bazaar under `Learned from:`. Lola Cely's carries "the
oil is shy," "they visit each other and stick together," her
daughter's internet freeze-first trick ("You can learn from the young
ones too"), and her mother in Batangas feeding her the torn wrappers —
lineage in both directions.

**Written wisdom transfers; unwritten mechanics don't.** In both gap
reports the apprentice's *reasons* came straight from the wisdom
section ("so the eggs do not scramble in the hot syrup"; "because too
loose makes them burst in the oil"), and wherever her words gave a
sensory stopping condition, the default vanished: "until it threads
off the spoon," the wobble "like jelly that's almost set," oil that
"sizzles right away, no waiting," done "when the singing goes quiet."
Meanwhile the mechanical layer stayed silent everywhere (silence
17–20 of 20 per step): **temperature defaulted on every tart step —
no oven temperature exists anywhere in Nadia's world** — as did bean
weight, bake durations, roll force, and seal pressure. Those silences
are precisely what the correction round exists to harvest.

## Verdict

Same prompts, same harness, same pipeline — three crafts, two
cuisines, zero bread-specific code paths. The card now carries two
layers (the move, and the judgment), and the apprentice proves which
layer each piece of knowledge lives in. For elder teachers, that is
the whole point: the steps are the easy part to lose; the judgment —
and who it came from — is what disappears first.

## Addendum — Claude review, same day (the wisdom moves)

Claude's first-pass review landed a hit this doc's own data supports:
asked *before* the apprentice runs, three of the four wisdom questions
hand it exactly what it was built to miss — a "how do you know" answer
is a stopping condition, a "what goes wrong" answer pre-explains its
failure, and Nadia's "toast the pecans" was a Trick delivered early.
The saturation above (silence 17–20 everywhere) is partly that effect,
not only tacit knowledge.

**Adopted (user's call):** the wisdom questions now come *after* the
teacher's reaction (they open the recorder's "Your try" step), and the
harness strips the wisdom section before the apprentice's first
attempt — `--keep-wisdom` runs the deliberate transfer check this doc
accidentally performed. Wisdom is still captured in full, in her
words, on the final card; it simply can't rescue the gaps the session
exists to find. Codex's second pass was blocked by its usage limit
(resets Nov 1) and remains owed.

