# Submission answers — DRAFT (prepared Oct 26, 2026)

For the Cerebral Valley "Submit Project" form. **Re-verify every field
against the finished build before submitting** (deadline Wed Nov 4,
6:00 PM PT). Two fields describe the completed product; anything not yet
true at submission time must be cut, not hoped for.

## Project name
**Unwritten Craft**

## X post link (Most Viral Track) — OPTIONAL
Leave blank unless entering the viral track (would need a public X post
about the project from @tinio).

## Project Description *
> Unwritten Craft teaches what must not disappear. Every craft runs on
> knacks that were never written down — the angle of a blade, the moment
> dough "stops fighting you" — and they die with the people who hold them,
> because experts explaining their work skip exactly the parts that matter
> most. Unwritten Craft catches those knacks. A teacher (in our demo, a
> baker of 30 years) shows a move and explains it briefly; the app writes
> the **card** in the teacher's own words and is forbidden from adding
> anything she didn't say. Then a second model — the Apprentice, which
> receives *only* the steps on the card, never the interview — commits
> to exactly what it would do. Its mistakes are the map of her
> unwritten knowledge: they are drawn onto her real photo, she corrects
> them once ("No! Tilt it — quick — it should tear a little"), and each
> correction becomes a **knack** on the card, tagged **Craft** (it
> works) or **Lineage** (who taught her). Only after she has reacted
> does the app ask the four wisdom questions — how she knows when it's
> right, what goes wrong, what forty years changed, who taught her —
> recorded in her words as **What the teacher knows**, deliberately
> kept from the Apprentice's first attempt so it cannot rescue the
> very gaps the session exists to find. For elder teachers, that
> judgment matters as much as the steps. The result is one shareable page a real person can
> actually learn from — the card, the knacks, her voice, and the
> student's own attempt beside hers. Nothing in the system is specific
> to bread: the same card and the same apprentice contract (motion,
> material, heat) are process-tested on a pecan tart and on rolling
> lumpia, and built for home crafts generally — cooking, sewing,
> gardening, repair — anywhere a lifetime of judgment lives in
> someone's hands.

## Public GitHub Repository *
`https://github.com/tinio/unwritten`
⚠️ **Action needed before submitting: flip the repo from private to
public** (the form requires a public repository). Nothing sensitive is
in it — samples are fictional, real teacher media is never committed.

## 3-Minute Demo Video *
⚠️ **Action needed: upload the final demo to YouTube** (the field wants
a youtube.com link; unlisted is fine unless rules say otherwise).
Structure (a 60-second animated storyboard of this exists — beats below;
the real video replaces cartoon frames with the working app and the real
session):

- **0:00–0:30** — Her hands, scoring a boule. "30 years of baking.
  Never written down." The problem in one shot.
- **0:30–1:00** — She explains; the card types itself, her words only.
  On-screen: Spark's constraint — "the drafter may not add anything."
- **1:00–1:30** — The boundary, shown honestly: the card pasted into a
  fresh model call, input on camera. The Apprentice commits: 90°,
  moderate, center.
- **1:30–2:00** — The misreading on her real photo: SAM highlight +
  the Apprentice's sentence pinned to the seam. Muse Image renders
  the consequence beside it.
- **2:00–2:30** — Her correction, on camera. The knack joins the card;
  one question tags it Craft or Lineage.
- **2:30–3:00** — The hand-it-on page: two loaves side by side.
  "Mom's Bread: 4 knacks that were never written down." Closing line:
  "Every trade runs on knacks like these."

## Describe your use of Meta products *
> **Muse Spark** is the interviewer and card drafter. It conducts the
> short teacher capture and drafts the instruction card under an unusual
> negative constraint: transcribe, compress, and order — but never add a
> step, quantity, or technique the teacher didn't say, and preserve her
> phrasing verbatim. The product depends on Spark *not* using knowledge
> it plainly has. **Muse Wonder** is the blind Apprentice: a fresh
> context that receives only the finished card and must commit to
> concrete mechanical parameters (angle, force, duration, stopping
> condition), defaulting to geometric-neutral values wherever the card
> is silent — so its failures locate the teacher's tacit knowledge
> mechanically, with no "play dumb" prompting. On the hand-it-on page,
> Wonder also compares the teacher's and the student's finished results
> and narrates the visible difference for confirmation. **SAM 3.1**
> segments the teacher's real photo so the Apprentice's misreading is
> grounded on the actual work — the highlighted region plus the
> Apprentice's own sentence pinned to it. **Muse Image** renders the
> downstream consequence of the mistake beside the overlay (what the
> error bakes into), and the **Meta Model API** ties the roles together
> with strict context isolation between them: the boundary between what
> Spark saw and what Wonder gets is enforced by architecture, not by
> asking nicely.

## Why are Meta's models important to your solution? *
> The core mechanic is an *information boundary between models*, and it
> only works if each model plays its role with discipline. Spark must
> follow an instruction that runs against its training — be a
> stenographer, not an expert — and in our first end-to-end test, on a
> scripted transcript, the drafted card added zero technique. Wonder must be
> a genuine second mind: a separate model whose entire input is the
> card — by construction it never contains the interview, and the demo
> shows that input on camera — so its wrong answer is evidence, not theater.
> SAM grounds the whole exchange in the teacher's real photograph
> instead of a generated stand-in, which is what makes a correction
> feel like it belongs to *her* loaf. Remove any one of these and the
> product collapses into either a recipe generator (no boundary) or an
> SOP tool (no meaning). The stack isn't interchangeable plumbing here;
> the models' separateness *is* the instrument.

## Feedback — Meta products (optional)
> Short draft — finalize with real build experience: Muse's headless
> mode made fresh-context apprentice calls trivial to enforce and
> audit, and Wonder followed a strict structured-output contract
> reliably (3/3 parseable long-form commitments in our first test).
> Spark holding a "do not add knowledge" constraint across a full
> drafting task was the pleasant surprise of the build.

## Feedback — partner technologies (optional)
Leave blank unless Baseten / Modal / Fireworks are actually used in
the final build.

## Permission checkbox
The form's checkbox grants Meta and Cerebral Valley permission to use,
publish, share, and promote the submitted materials. Accepting it is
the submitter's own action at submission time — consistent with the
standing understanding that submissions are effectively public.
**Nothing private belongs in the submission: no Blaze code, no raw
interview recording — only clips the teacher has heard and approved.**
