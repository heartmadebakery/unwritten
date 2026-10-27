# Unwritten Craft

**Teach what must not disappear.** Unwritten Craft preserves a skill by making
it usable by another person.

It works like this. A teacher explains a move once, and the app writes down a
short instruction **card** in the teacher's own words. A second model — the
*blind apprentice* — then tries to follow the card. It receives **only** the
card, never the interview, and it must state exactly what it would do. Where
it fails is where the teacher's unwritten knowledge lives. The teacher
corrects it once. Each correction is a **technique**; together, the techniques
are the **Knack**. The Knack is the artifact: one shareable page a real person
can learn from.

Built for the Meta Global AI Developer Hackathon 2026 (Indie, solo).
Build window: Oct 26 – Nov 4, 2026. Submission is public by the organizer's
terms — this repo contains no private code from any other project.

## The idea in 10 seconds

[Watch the vision video](https://muse.ai/files/471196432735854/1109151131711720/btttvfzuf1f61fpwgnezpprs/media-generation-unwritten-craft-eli5-explainer-0-61a07ebe-6401-4dbe-8c4b-5b8cc420d6e0.mp4)
— a cartoon grandma, a robot apprentice, one wrong cut, one correction.
The video is hosted outside this repo (temporary link, expires Oct 28, 2026;
a durable host is needed before submission).

The robot is a metaphor. There is no physical robot. In the app, the "robot"
is the blind apprentice **model**: it reads only the card, states exactly what
it would do, and its mistake is drawn onto the teacher's real photo (a SAM 3.1
highlight, with the apprentice's own sentence pinned to the region). Muse
Image may render the consequence of the mistake beside it. Every scene in the
video maps to a real screen in the build. Notably, the video's wrong move —
the knife held perfectly upright, cutting straight down — is literally what
the apprentice committed to in testing (90°, moderate force, center). The
cartoon depicts the verified mechanic.

## The four steps

1. **Show & teach.** The teacher photographs the work and talks briefly
   (about 45 seconds, like jotting steps on an index card). The session opens
   with one question about any visible wear in the photo — a burn mark, a
   scar in the tool. Muse Spark drafts the **card** from her steps. Her
   **wisdom** — the judgment layer — is captured later, after she has reacted
   to the apprentice (see step 4), and filed on the card under *What the
   teacher knows*, in her own words.
2. **The apprentice tries.** A blind learner model receives *only* the card.
   It must commit to concrete parameters: motion (angle, force, duration),
   material (tool, size, amount), and heat (temperature), plus a stopping
   condition. Anything the card does not specify falls back to a
   geometric-neutral default. So the apprentice fails exactly where the
   teacher left the physics unspoken — honestly, with no "play dumb" prompt.
   The misreading is shown on the teacher's real photo: SAM 3.1 highlights
   the region and the apprentice's own sentence is pinned to it. Muse Image
   may render the *consequence* beside it — what the mistake produces.
3. **Correct once.** The teacher reacts. Each correction becomes a
   **technique** on the card. For each one, the app asks one question —
   *"Is that for the bread, or because of who taught you?"* — and tags the
   technique **Craft** (it works) or **Lineage** (it's inherited).
4. **Hand it on.** One shareable page: the card, the Knack, the teacher's
   voice clips, and the recipient's real attempt placed beside the teacher's
   original.

## Design rules (do not break these)

- **The information boundary is real.** The apprentice call is a fresh model
  call whose entire context is the card text. No interview transcript, no
  photo, no system-prompt hints about the right technique. The demo shows the
  input on camera.
- **Spark is a stenographer, not an expert.** When drafting the card, Spark
  may transcribe, compress, and order. It must not add steps, quantities,
  timings, or techniques the teacher did not say, and it preserves the
  teacher's distinctive phrasing verbatim. If Spark's own domain knowledge
  leaked into the card, it would silently close the very gaps the apprentice
  is meant to fall into. ("Spark was not allowed to improve her words.")
- **Step 1 stays short.** A long, curious interview extracts the tacit
  knowledge up front, and the mechanic dies. So: one soulful opening
  question, then "give me the quick steps like you're jotting them on an
  index card."
- **Ask for wisdom — after the reaction, never before.** Steps capture the
  move; they rarely capture the judgment. But ask for judgment too early and
  it pre-arms the apprentice with exactly what it was built to miss. (A "how
  do you know?" answer *is* a stopping condition; a "what goes wrong?" answer
  pre-explains its failure — Claude review, Oct 26.) So the four wisdom
  questions — *How do you know when it's right? What goes wrong the other
  way? What do you do differently now than when you started? Who taught you
  this?* — are asked only after the teacher has reacted to the apprentice's
  attempt. The apprentice's first run always sees the steps-only card: the
  harness strips the wisdom section. (`--keep-wisdom` exists for the
  deliberate transfer check: same card, wisdom unsealed, compare the gaps.)
  For elder teachers especially, this section is the difference between
  recording a recipe and rescuing a lifetime's judgment before it disappears.
- **Any craft, not just bread.** Nothing in the prompts, the parameter set,
  or the pipeline is specific to one task. The card format and the apprentice
  contract (motion + material + heat) serve baking, cooking, sewing,
  gardening, home repair — any work a teacher can show with their hands.
  `samples/` carries three fictional sessions proving it: scoring a boule, a
  pecan tart, and rolling lumpia. The demo's hero is one family's bread; the
  system is built for the home, and the same shape extends to trades and
  manufacturing later.
- **The overlay is the primary visual.** The SAM highlight plus the
  apprentice's sentence on the real photo is the designed visual, not a
  fallback. Inpainted hands are enhancement only.

## Repo layout

- `prompts/` — the exact prompts that carry the design rules:
  `card_drafter.md` (constrained Spark) and `apprentice.md` (the
  forced-commitment contract).
- `harness/` — the process-test harness for the core mechanic. Text-only on
  purpose: it proves (or kills) the mechanic before any UI exists.
  `apprentice_muse.py` collects fresh apprentice responses; `run_test.py`
  turns a card plus a set of responses into a gap report. Where runs
  defaulted or diverged is where the card is silent.
- `pipeline/` — the session pipeline: recorder clips in, hand-it-on page out.
  See [the pipeline guide](docs/PIPELINE.md).
- `app/` — the recorders: `app/recorder/` (single-file web app) and
  `app/android/` (native Android port). See [the device guide](docs/DEVICES.md).
- `samples/` — fictional sample cards and transcripts for process testing.
  **Not** real teacher data.
- `tests/` — unit tests for the harness (`python3 -m unittest discover -s tests`).
- `docs/` — design notes, test logs, and the submission draft.

## Running the mechanic test

```bash
# 1. Draft the card from the teacher's words with Muse Spark, constrained
#    by prompts/card_drafter.md (see samples/sample_card_spark.md).
# 2. Collect fresh apprentice responses from Muse Wonder. Each `muse exec`
#    call is a fresh context that sees ONLY the card:
python3 harness/apprentice_muse.py --card samples/sample_card_spark.md \
    --runs 3 --model muse-wonder-1.0 --out responses.json
# 3. Analyze:
python3 harness/run_test.py --card samples/sample_card_spark.md \
    --responses responses.json --out report.md
```

Stack roles are fixed. **Spark** interviews and drafts; it has seen the
teacher, so it is never the apprentice. **Wonder** is the blind apprentice;
it has seen only the card. The harness itself is model-agnostic — it consumes
raw response text — but runs on non-Muse backends are process checks only
and count for nothing toward the hackathon stack.

`responses.json` is written by the collector as an object with provenance:
`{card_sha256, keep_wisdom, model, runs}`, where `runs` is a list of raw
model output strings. (`run_test.py` also accepts the legacy bare list.) Each
response must contain the JSON commitment object specified in
`prompts/apprentice.md`; the parser tolerates surrounding prose and code
fences.
