# Unwritten Craft

**Teach what must not disappear.** Unwritten Craft preserves a skill by making
it usable by another person. A teacher explains a move once; the app writes it
down the way the teacher actually said it; then a *blind apprentice* — a model
that receives **only** the written card, never the interview — tries to follow
it and commits to exactly what it would do. Where the apprentice fails is where
the teacher's tacit knowledge lives. The teacher corrects it once, and those
corrections — the **Tricks** — become the artifact: a shareable page a real
person can learn from.

Built for the Meta Global AI Developer Hackathon 2026 (Indie, solo).
Build window: Oct 26 – Nov 4, 2026. Submission is public by the organizer's
terms — this repo contains no private code from any other project.

## The four steps

1. **Show & teach.** The teacher photographs the work and talks briefly
   (~45 seconds of "index card" capture, plus one opening question about any
   visible wear in the photo — a burn mark, a scar in the tool). Muse Spark
   drafts the **card**: a short instruction sheet.
2. **The apprentice tries.** A blind learner model receives *only* the card
   and must commit to concrete mechanical parameters (angle, force, duration,
   contact area, stopping condition). Anything the card does not specify falls
   back to a geometric-neutral default — so the apprentice fails exactly where
   the teacher left physics unspoken, honestly, with no "play dumb" prompt.
   The misreading is shown on the teacher's real photo: SAM 3.1 highlights the
   region and the apprentice's own sentence is pinned to it. (Muse Image may
   render the *consequence* beside it — what the mistake produces.)
3. **Correct once.** The teacher reacts. Each correction becomes a **Trick**
   on the card. For each Trick, one question is asked — *"Is that for the
   bread, or because of who taught you?"* — and the Trick is tagged
   **Craft** (it works) or **Lineage** (it's inherited).
4. **Hand it on.** One shareable page: the card, the Tricks, the teacher's
   voice clips, and the recipient's real attempt placed beside the teacher's
   original.

## Design rules (do not break these)

- **The information boundary is real.** The apprentice call is a fresh model
  call whose entire context is the card text. No interview transcript, no
  photo, no system-prompt hints about the right technique. The demo shows the
  input on camera.
- **Spark is a stenographer, not an expert.** When drafting the card, Spark
  may transcribe, compress, and order — it must not add steps, quantities,
  timings, or techniques the teacher did not say, and it preserves the
  teacher's distinctive phrasing verbatim. Spark's own domain knowledge
  leaking into the card would silently close the very gaps the apprentice is
  meant to fall into. ("Spark was not allowed to improve her words.")
- **Step 1 stays short.** A long, curious interview extracts the tacit
  knowledge up front and the mechanic dies. One soulful opening question,
  then "give me the quick steps like you're jotting them on an index card."
- **The overlay is the primary visual.** SAM-highlight + the apprentice's
  sentence on the real photo — designed, not a fallback. Inpainted hands are
  enhancement only.

## Repo layout

- `prompts/` — the exact prompts that carry the design rules:
  `card_drafter.md` (constrained Spark) and `apprentice.md` (the
  forced-commitment contract).
- `harness/` — the process-test harness for the core mechanic. Text-only on
  purpose: it proves (or kills) the mechanic before any UI exists.
  `run_test.py` takes a card and a set of apprentice responses and produces a
  gap report: where runs defaulted or diverged is where the card is silent.
- `samples/` — fictional sample cards for process testing. **Not** real
  teacher data.

## Running the mechanic test

```bash
# 1. Put teacher words in a card file (see samples/sample_card.md).
# 2. Collect N fresh apprentice responses (each call sees ONLY the card):
#    any model backend works — the harness consumes raw response text.
# 3. Analyze:
python3 harness/run_test.py --card samples/sample_card.md \
    --responses responses.json --out report.md
```

`responses.json` is a JSON list of raw model output strings. Each response
must contain the JSON commitment object specified in `prompts/apprentice.md`
(the parser tolerates surrounding prose and code fences).
