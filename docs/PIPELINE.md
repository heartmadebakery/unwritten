# The session pipeline

What happens to the recordings after a teacher session. The recorder app
([`app/recorder`](../app/recorder)) captures; this pipeline processes.
Everything runs locally except the two Muse model roles — and those roles
are the product's architecture, not an implementation detail.

```
session folder (off the phone)
   │  ingest.py — classify unwritten_<step>_*.{webm,mp4,mp3,jpg}
   ▼
manifest.json
   ├─ teach/react media ─► transcribe.py ─► transcript.txt   (local Whisper)
   ├─ show video ────────► frames.py ─────► keyframes (hero = middle frame)
   ├─ teach transcript ──► draft_card.py ─► card.md          (Muse Spark;
   │                             the wisdom section comes from the attempt
   │                             clip, which opens with the post-reaction
   │                             wisdom Q&A)
   ├─ card ──────────────► harness/apprentice_muse.py ─► gap_report.md
   │                                                  (Muse Wonder, card only)
   ├─ hero/photo + top-gap sentence ─► sam_overlay.py ─► overlay.png (SAM)
   └─ react transcript ──► techniques draft + handiton.py ─► page.html
```

Run it:

```bash
pipeline/run_pipeline.py <session_dir> <work_dir> [--title ...] \
    [--point X,Y] [--apprentice-runs 3]
```

Every stage skips gracefully, with a message, if its input is missing — so a
partial session still yields a partial work dir. Python dependencies live in
`.venv` (created with `python3 -m venv .venv`, plus torch CPU, torchvision,
segment-anything, and faster-whisper). The runner re-invokes the heavy stages
under `.venv` when it exists.

## Stage notes

- **Transcription is local on purpose.** It uses faster-whisper (base model,
  int8, CPU), so a teacher's raw voice never leaves the machine for a
  third-party transcription service. Set `UNWRITTEN_WHISPER_MODEL=small` to
  trade speed for accuracy. The transcript feeds two places: Spark's card
  draft, and the technique miner, which drafts correction candidates from the
  reaction clip (lines starting "No / Don't / Never / Wait"). That draft is
  for the teacher to confirm — never gospel.
- **Card drafting** is `draft_card.py`: the transcript plus the stenographer
  prompt (`prompts/card_drafter.md`), sent to Muse Spark via Muse.
- **The Apprentice** stage reuses the harness: Wonder, in fresh `muse exec`
  contexts, seeing the card only. The gap report's highest-silence step
  supplies the sentence the overlay pins.
- **Frames**: evenly spaced stills from the show clip. If the session
  includes a real teacher *photo* of the work, it overrides the hero frame.

## How SAM is used

SAM produces the overlay — Step 2's primary visual. The contract
(`sam_overlay.py`) is: **image + point in, highlighted overlay + mask stats
out.** The point (normalized coordinates, `--point X,Y`) marks where the
action happens on the teacher's photo — for the demo, the center of the loaf
where the cut lands. SAM returns candidate masks for the object under the
point; the best-scoring mask is tinted in the app's amber, and the
Apprentice's own sentence for the biggest-gap step is pinned to the mask with
a leader line, labeled `APPRENTICE:`.

The development engine is Meta's original **segment-anything (ViT-B)**,
running on CPU (a few seconds per image at these sizes). The checkpoint
(375 MB) is **not in git** — fetch it once:

```bash
mkdir -p pipeline/models
curl -L -o pipeline/models/sam_vit_b_01ec64.pth \
  https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth
```

**Production swap — SAM 3.1 via the Meta Model API.** SAM 3 / 3.1 adds
concept (text) prompts, so the point can be replaced or backed by a phrase
("the seam of the dough") once the build wires the Meta Model API key in.
Nothing downstream changes: the overlay module's contract is the seam. Until
then, the local engine proves the visual end to end and costs nothing per
run — which matters during the 10-day build.

One honest limitation of a *point* prompt: it finds the object, not the
gesture. So the overlay pairs the mask with the Apprentice's sentence. The
sentence carries the wrongness (angle, force); the mask carries the *where*.
That pairing is the design, not a workaround — it is exactly the
SAM-highlight-plus-pinned-sentence visual the advisor panel chose as primary.
