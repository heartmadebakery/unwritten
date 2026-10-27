#!/usr/bin/env python3
"""Run the whole Unwritten Craft session pipeline.

  python3 pipeline/run_pipeline.py <session_dir> <work_dir> \
      [--title "Mom's Bread"] [--point 0.5,0.45] [--apprentice-runs 3]

Stages (each skips gracefully if its input is missing, and says so):
  1. ingest      — classify the recorder's files -> manifest.json
  2. transcribe  — teach + react (+ attempt, companion dialogue) audio
                   -> transcripts (local whisper; optional takes are
                   allowed to fail, the teach take is not)
  3. frames      — keyframes from the show video; middle frame is hero
                   (a session photo of the work beats frames; failure
                   here never blocks the card)
  4. card        — Muse Spark drafts the card from the teach transcript
  5. apprentice  — Muse Wonder, fresh calls, card only -> gap report
  6. overlay     — SAM segments the action region on the hero/photo;
                   the Apprentice's sentence for the biggest-gap step is
                   pinned to it -> overlay.png
  7. page        — hand-it-on page.html (tricks mined from the react
                   transcript as a DRAFT — the teacher confirms them)

Honesty rules (Wonder review, Oct 26): stale artifacts from a previous
run in the work dir are deleted up front; the run exits non-zero unless
a card AND a page were produced THIS run; every "first file" choice a
stage makes is logged. Python deps live in .venv (torch,
segment-anything, faster-whisper); stages re-invoke under .venv when
present, else the current interpreter.
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
STALE = ("card.md", "overlay.png", "page.html", "gap_report.md",
         "responses.json", "tricks_draft.md", "transcripts.json",
         "manifest.json", "hero.jpg", "hero.png", "hero.jpeg",
         "attempt_photo.jpg", "attempt_photo.png", "attempt_photo.jpeg")


def py():
    return VENV_PY if os.path.exists(VENV_PY) else sys.executable


def run(cmd, stage, fatal=True):
    print(f"[{stage}] {' '.join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd))}")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          env={**os.environ, "PATH": os.environ.get("PATH", "")})
    out = (proc.stdout or "").strip()
    if out:
        print("  " + out.replace("\n", "\n  "))
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        msg = f"[{stage}] FAILED: {tail[-1] if tail else proc.returncode}"
        if fatal:
            sys.exit(msg + " — pipeline stops here (earlier stages' outputs are kept).")
        print(msg + " — continuing without it.")
        return None
    return out


def pick_take(files, step):
    """Latest take wins (recorder names sort chronologically)."""
    if not files:
        return None
    if len(files) > 1:
        print(f"  [{step}] {len(files)} takes found — using the latest: "
              f"{os.path.basename(files[-1])}")
    return files[-1]


def photo_with_step(photos, *steps):
    for step in steps:
        for p in photos:
            if f"_{step}_" in os.path.basename(p) or f"_{step}-" in os.path.basename(p):
                return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir")
    ap.add_argument("work_dir")
    ap.add_argument("--title", default="Unwritten Craft")
    ap.add_argument("--point", default="0.5,0.45",
                    help="normalized SAM point prompt on the hero image")
    ap.add_argument("--apprentice-runs", type=int, default=3)
    args = ap.parse_args()

    parts = args.point.split(",")
    if len(parts) != 2 or not all(0.0 <= float(v) <= 1.0 for v in parts):
        sys.exit("--point must be X,Y with both values in 0..1")
    if args.apprentice_runs < 1:
        sys.exit("--apprentice-runs must be >= 1")

    os.makedirs(args.work_dir, exist_ok=True)
    for stale in STALE:
        p = os.path.join(args.work_dir, stale)
        if os.path.exists(p):
            os.unlink(p)
    work = lambda *p: os.path.join(args.work_dir, *p)
    produced = set()

    # 1. ingest
    sys.path.insert(0, HERE)
    from ingest import ingest
    media = ingest(args.session_dir)
    # A recorder session manifest, when present, defines THIS session's
    # files — a downloads folder must not merge past sessions into it.
    for sm in glob.glob(os.path.join(args.session_dir, "unwritten_session_*.json")):
        try:
            names = {c["name"] for c in json.load(open(sm)).get("clips", [])}
            if names:
                for key in media:
                    media[key] = [p for p in media[key]
                                  if os.path.basename(p) in names]
                print(f"  [ingest] session manifest {os.path.basename(sm)} "
                      f"restricts the run to its {len(names)} clips")
        except (ValueError, OSError, TypeError):
            pass
    with open(work("manifest.json"), "w") as fh:
        json.dump({k: [os.path.basename(p) for p in v] for k, v in media.items()},
                  fh, indent=1)
    counts = {k: len(v) for k, v in media.items() if v}
    print(f"[ingest] {counts}")

    teach = pick_take(media["teach"], "teach")
    show = pick_take(media["show"], "show") or pick_take(media["broll"], "broll")
    react = pick_take(media["react"], "react")
    attempt = pick_take(media["attempt"], "attempt")
    dialogue = pick_take(media["dialogue"], "dialogue")

    # 2. transcribe (local whisper; teacher audio never leaves the machine)
    transcripts = {}
    wanted = [(k, p) for k, p in (("teach", teach), ("react", react),
                                  ("attempt", attempt), ("dialogue", dialogue)) if p]
    for kind, path in wanted:
        if run([py(), os.path.join(HERE, "transcribe.py"), path, work(f"transcript_{kind}")],
               f"transcribe:{kind}", fatal=False) is not None:
            tpath = work(f"transcript_{kind}", "transcript.txt")
            if os.path.exists(tpath):
                transcripts[kind] = tpath
    if not transcripts.get("teach") and transcripts.get("dialogue"):
        # The companion's clean dialogue track carries the whole session:
        # an honest fallback, labeled as such.
        print("  [transcribe] no usable teach take — using the companion "
              "dialogue track as the teaching transcript (fallback)")
        transcripts["teach"] = transcripts["dialogue"]
    if teach and not transcripts.get("teach"):
        sys.exit(f"[transcribe:teach] produced no transcript from "
                 f"{os.path.basename(teach)} and no dialogue fallback "
                 "exists — cannot draft a card.")
    if transcripts:
        with open(work("transcripts.json"), "w") as fh:
            json.dump({k: os.path.basename(v) for k, v in transcripts.items()}, fh, indent=1)

    # 3. frames / hero image (never fatal — the card matters more)
    hero = photo_with_step(media["photos"], "show", "teach") or \
        (media["photos"][0] if media["photos"] else "")
    if not hero and show:
        out = run([py(), os.path.join(HERE, "frames.py"), show, work("frames")],
                  "frames", fatal=False)
        if out:
            hero = out.splitlines()[-1].strip()
    if hero:
        ext = os.path.splitext(hero)[1].lower() or ".jpg"
        shutil.copy(hero, work("hero" + ext))
        print(f"[frames] hero = {os.path.basename(hero)}")
    attempt_photo = photo_with_step(media["photos"], "attempt")
    if attempt_photo:
        ext = os.path.splitext(attempt_photo)[1].lower() or ".jpg"
        shutil.copy(attempt_photo, work("attempt_photo" + ext))

    # 4. card — Spark drafts from the teach transcript (+ the wisdom Q&A
    #    recorded after her reaction: the attempt clip opens with it; a
    #    companion dialogue take is the fallback source)
    card_path = work("card.md")
    if transcripts.get("teach"):
        cmd = [sys.executable, os.path.join(HERE, "draft_card.py"),
               transcripts["teach"], card_path]
        wisdom_src = transcripts.get("attempt") or transcripts.get("dialogue")
        if wisdom_src:
            cmd += ["--wisdom", wisdom_src]
        if run(cmd, "card") is not None and os.path.exists(card_path):
            produced.add("card.md")
    else:
        print("[card] skipped — no teach transcript")

    # 5. apprentice — Wonder, fresh calls, steps only (wisdom sealed)
    gap_sentence, gap_step = "", None
    responses = work("responses.json")
    if os.path.exists(card_path) and "card.md" in produced:
        if run([sys.executable, os.path.join(ROOT, "harness", "apprentice_muse.py"),
                "--card", card_path, "--runs", str(args.apprentice_runs),
                "--out", responses], "apprentice") is not None:
            run([sys.executable, os.path.join(ROOT, "harness", "run_test.py"),
                 "--card", card_path, "--responses", responses,
                 "--out", work("gap_report.md")], "gap-report")
            sys.path.insert(0, os.path.join(ROOT, "harness"))
            from apprentice import parse_commitments, analyze, gap_score
            data = json.load(open(responses))
            raw_runs = data.get("runs", []) if isinstance(data, dict) else data
            runs = []
            for raw in raw_runs:
                try:
                    runs.append(parse_commitments(raw))
                except ValueError as e:
                    print(f"  [apprentice] re-parse skipped a run ({e})")
            if runs:
                top = max(analyze(runs), key=gap_score)
                gap_step = top["step"]
                gap_sentence = next((s for s in top["sentences"] if s), "")
                print(f"  [apprentice] biggest silence: step {gap_step} "
                      f"(score {gap_score(top)})")

    # 6. overlay — SAM on the hero, the Apprentice's sentence pinned
    if hero and gap_sentence:
        label = "APPRENTICE: " + gap_sentence
        if run([py(), os.path.join(HERE, "sam_overlay.py"), "--image", hero,
                "--point", args.point, "--label", label,
                "--out", work("overlay.png")], "overlay", fatal=False) is not None:
            produced.add("overlay.png")
    else:
        print("[overlay] skipped — needs a hero image and an apprentice sentence")

    # 7. tricks draft from the react transcript, then the page
    tricks = work("tricks_draft.md")
    if transcripts.get("react"):
        text = open(transcripts["react"]).read()
        mined = []
        for sent in re.split(r"(?<=[.!?])\s+", text.replace("\n", " ")):
            s = sent.strip()
            if re.search(r"\b(no|don'?t|never|wait)\b", s, re.IGNORECASE) or "!" in s:
                mined.append(s)
        with open(tricks, "w") as fh:
            fh.write("# Tricks — DRAFT mined from her reaction (she confirms "
                     "and tags each Craft or Lineage)\n\n")
            for s in mined:
                fh.write(f"- {s}\n")
        print(f"[tricks] {len(mined)} candidate corrections mined (draft)")
    if os.path.exists(card_path) and "card.md" in produced:
        run([sys.executable, os.path.join(HERE, "handiton.py"),
             "--work", args.work_dir, "--title", args.title,
             "--tricks", tricks], "page")
        if os.path.exists(work("page.html")):
            produced.add("page.html")

    if "card.md" not in produced or "page.html" not in produced:
        sys.exit(f"Pipeline incomplete: produced {sorted(produced) or 'nothing'} "
                 f"this run. Check the stage messages above — an empty or "
                 f"unrecognized session folder is the usual cause.")
    print(f"\nPipeline done. Work dir: {args.work_dir} "
          f"(card, gap report, overlay, page.html)")


if __name__ == "__main__":
    main()
