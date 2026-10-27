# Unwritten Craft

**Teach what must not disappear.** Unwritten Craft preserves a skill by making
it usable by another person. A teacher explains a move once; the app writes it
down the way the teacher actually said it; then a *blind apprentice* — a model
that receives **only** the written card, never the interview — tries to follow
it and commits to exactly what it would do. Where the apprentice fails is where
the teacher's tacit knowledge lives. The teacher corrects it once, and those
corrections — the **Knack** — become the artifact: a shareable page a real
person can learn from.

Built for the Meta Global AI Developer Hackathon 2026 (Indie, solo).
Build window: Oct 26 – Nov 4, 2026. Submission is public by the organizer's
terms — this repo contains no private code from any other project.

## Explainer (10 seconds, ELI5)

[Watch the vision video](https://muse.ai/files/471196432735854/1109151131711720/btttvfzuf1f61fpwgnezpprs/media-generation-unwritten-craft-eli5-explainer-0-61a07ebe-6401-4dbe-8c4b-5b8cc420d6e0.mp4)
— a cartoon grandma, a robot apprentice, one wrong cut, one correction.
Hosted outside this repo (temporary link, expires Oct 28, 2026; a durable
host is needed before submission).

The robot is a metaphor, and the video is the storyboard: every scene maps
to a real screen in the build. There is no physical robot. In the app, the
"robot" is the blind apprentice **model**: it reads only the card, commits
to exactly what it would do, and its mistake is drawn onto the teacher's
real photo (SAM 3.1 highlight + its own sentence pinned to the region),
with Muse Image rendering the consequence beside it. Notably, the video's
wrong move — the knife held perfectly upright, cutting straight down — is
literally what the apprentice committed to in testing (90°, moderate
force, center): the cartoon depicts the verified mechanic.

## The four steps

1. **Show & teach.** The teacher photographs the work and talks briefly
   (~45 seconds of "index card" capture, plus one opening question about any
   visible wear in the photo — a burn mark, a scar in the tool). Muse Spark
   drafts the **card** from her steps. Her **wisdom** — the judgment layer —
   is captured later, after she has reacted to the apprentice (see step 4),
   and filed on the card under *What the teacher knows*, in her own words.
2. **The apprentice tries.** A blind learner model receives *only* the card
   and must commit to concrete parameters — motion (angle, force, duration),
   material (tool, size, amount), and heat (temperature), plus a stopping
   condition. Anything the card does not specify falls
   back to a geometric-neutral default — so the apprentice fails exactly where
   the teacher left physics unspoken, honestly, with no "play dumb" prompt.
   The misreading is shown on the teacher's real photo: SAM 3.1 highlights the
   region and the apprentice's own sentence is pinned to it. (Muse Image may
   render the *consequence* beside it — what the mistake produces.)
3. **Correct once.** The teacher reacts. Each correction becomes a **knack**
   on the card. For each one, one question is asked — *"Is that for the
   bread, or because of who taught you?"* — and the knack is tagged
   **Craft** (it works) or **Lineage** (it's inherited).
4. **Hand it on.** One shareable page: the card, the knacks, the teacher's
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
- **Ask for wisdom — after the reaction, never before.** Steps capture
  the move; they rarely capture the judgment. But ask for judgment too
  early and it pre-arms the apprentice with exactly what it was built
  to miss (a "how do you know?" answer *is* a stopping condition; a
  "what goes wrong?" answer pre-explains its failure — Claude review,
  Oct 26). So the four wisdom questions — *How do you know when it's
  right? What goes wrong the other way? What do you do differently now
  than when you started? Who taught you this?* — are asked only after
  the teacher has reacted to the apprentice's attempt, and the
  apprentice's first run always sees the steps-only card (the harness
  strips the wisdom section; `--keep-wisdom` exists for the deliberate
  transfer check: same card, wisdom unsealed, compare the gaps). For
  elder teachers especially, this section is the difference between
  recording a recipe and rescuing a lifetime's judgment before it
  disappears.
- **Any craft, not just bread.** Nothing in the prompts, the parameter
  set, or the pipeline is specific to one task: the card format and the
  apprentice contract (motion + material + heat) serve baking, cooking,
  sewing, gardening, home repair — any work a teacher can show with
  their hands. `samples/` carries three fictional sessions proving it:
  scoring a boule, a pecan tart, and rolling lumpia. The demo's hero is
  one family's bread; the system is built for the home, and the same
  shape extends to trades and manufacturing later.
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
# 1. Draft the card from the teacher's words with Muse Spark constrained
#    by prompts/card_drafter.md (see samples/sample_card_spark.md).
# 2. Collect fresh apprentice responses from Muse Wonder — each `muse
#    exec` call is a fresh context that sees ONLY the card:
python3 harness/apprentice_muse.py --card samples/sample_card_spark.md \
    --runs 3 --model muse-wonder-1.0 --out responses.json
# 3. Analyze:
python3 harness/run_test.py --card samples/sample_card_spark.md \
    --responses responses.json --out report.md
```

Stack roles are fixed: **Spark** interviews and drafts (it has seen the
teacher, so it is never the apprentice); **Wonder** is the blind apprentice
(it has seen only the card). The harness itself is model-agnostic — it
consumes raw response text — but runs on non-Muse backends are process
checks only and count for nothing toward the hackathon stack.

`responses.json` is a JSON list of raw model output strings. Each response
must contain the JSON commitment object specified in `prompts/apprentice.md`
(the parser tolerates surrounding prose and code fences).
