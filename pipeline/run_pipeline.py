#!/usr/bin/env python3
"""Run the whole Unwritten Craft session pipeline.

  python3 pipeline/run_pipeline.py <session_dir> <work_dir> \
      [--title "Mom's Bread"] [--point 0.5,0.45] [--apprentice-runs 3]

Stages (each skips gracefully if its input is missing, and says so):
  1. ingest      — classify the recorder's files -> manifest.json
  2. transcribe  — teach + react audio -> transcripts (local whisper)
  3. frames      — keyframes from the show video; middle frame is hero
  4. card        — Muse Spark drafts the card from the teach transcript
  5. apprentice  — Muse Wonder, fresh calls, card only -> gap report
  6. overlay     — SAM segments the action region on the hero/photo;
                   the Apprentice's sentence for the biggest-gap step is
                   pinned to it -> overlay.png
  7. page        — hand-it-on page.html (tricks mined from the react
                   transcript as a DRAFT — the teacher confirms them)

Python deps live in .venv (torch, segment-anything, faster-whisper);
system python3 is fine for stages that don't import them. This runner
re-invokes itself under .venv when present.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")


def run(mod_args, use_venv=False, **kw):
    py = VENV_PY if (use_venv and os.path.exists(VENV_PY)) else sys.executable
    print(f"\n=== {' '.join(mod_args)} ===", flush=True)
    subprocess.run([py] + mod_args, check=True, **kw)


def stage_transcripts(work, manifest):
    out = {}
    for step in ("teach", "react", "attempt"):
        media = manifest.get(step) or []
        if media:
            tdir = os.path.join(work, f"transcript_{step}")
            run([os.path.join(HERE, "transcribe.py"), media[0], tdir], use_venv=True)
            out[step] = os.path.join(tdir, "transcript.txt")
    # A companion's dialogue take covers the whole session in one clean
    # track: transcribe it too. It is the fallback wisdom source (and a
    # cross-check on the step clips' audio) — see the card stage.
    dialogue = manifest.get("dialogue") or []
    if dialogue:
        tdir = os.path.join(work, "transcript_dialogue")
        run([os.path.join(HERE, "transcribe.py"), dialogue[0], tdir], use_venv=True)
        out["dialogue"] = os.path.join(tdir, "transcript.txt")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir")
    ap.add_argument("work_dir")
    ap.add_argument("--title", default="Unwritten Craft")
    ap.add_argument("--point", default="0.5,0.45")
    ap.add_argument("--apprentice-runs", type=int, default=3)
    args = ap.parse_args()
    work = args.work_dir
    os.makedirs(work, exist_ok=True)

    # 1. ingest
    manifest_path = os.path.join(work, "manifest.json")
    run([os.path.join(HERE, "ingest.py"), args.session_dir, manifest_path])
    with open(manifest_path) as fh:
        manifest = json.load(fh)

    # 2. transcripts
    transcripts = stage_transcripts(work, manifest)

    # 3. frames + hero image (teacher photo wins over video frame)
    hero = ""
    if manifest.get("show"):
        frames_dir = os.path.join(work, "frames")
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "frames.py"),
             manifest["show"][0], frames_dir],
            capture_output=True, text=True, check=True)
        hero = proc.stdout.strip().splitlines()[-1]
    if manifest.get("photos"):
        hero = manifest["photos"][0]

    # 4. card (Spark) — steps from the teach transcript; the wisdom
    # section from the post-reaction wisdom Q&A, which opens the
    # attempt clip under the current recorder flow.
    card_path = os.path.join(work, "card.md")
    if "teach" in transcripts:
        cmd = [os.path.join(HERE, "draft_card.py"), transcripts["teach"], card_path]
        wisdom_src = transcripts.get("attempt") or transcripts.get("dialogue")
        if wisdom_src:
            cmd += ["--wisdom", wisdom_src]
        run(cmd)
    else:
        print("\n=== card skipped: no teach recording ===")

    # 5. apprentice (Wonder) + gap report — needs the card
    gap_step, gap_sentence = None, ""
    if os.path.exists(card_path):
        responses = os.path.join(work, "responses.json")
        env = dict(os.environ, PATH=os.path.expanduser("~/.local/bin") + ":" + os.environ["PATH"])
        run([os.path.join(ROOT, "harness", "apprentice_muse.py"),
             "--card", card_path, "--runs", str(args.apprentice_runs),
             "--out", responses], env=env)
        report = os.path.join(work, "gap_report.md")
        run([os.path.join(ROOT, "harness", "run_test.py"),
             "--card", card_path, "--responses", responses, "--out", report])
        # Biggest-gap step's first apprentice sentence becomes the overlay label.
        sys.path.insert(0, os.path.join(ROOT, "harness"))
        from apprentice import parse_commitments, analyze, gap_score
        with open(responses) as fh:
            runs = [parse_commitments(r) for r in json.load(fh)]
        analysis = analyze(runs)
        if analysis:
            top = max(analysis, key=gap_score)
            gap_step = top["step"]
            gap_sentence = top["sentences"][0] if top["sentences"] else ""

    # 6. SAM overlay — needs a hero image and a sentence to pin
    if hero and gap_sentence:
        # Copy the hero beside the overlay so the page can reference it.
        import shutil
        hero_local = os.path.join(work, "hero" + os.path.splitext(hero)[1])
        if os.path.abspath(hero) != os.path.abspath(hero_local):
            shutil.copy(hero, hero_local)
        run([os.path.join(HERE, "sam_overlay.py"), "--image", hero_local,
             "--point", args.point, "--label", gap_sentence,
             "--out", os.path.join(work, "overlay.png")], use_venv=True)
    else:
        print("\n=== overlay skipped: needs hero image + apprentice run ===")

    # 7. tricks draft from the react transcript + hand-it-on page
    tricks_path = os.path.join(work, "tricks_draft.md")
    if "react" in transcripts:
        with open(transcripts["react"]) as fh:
            text = fh.read()
        lines = [s.strip() for s in text.replace("!", "!.").split(".")
                 if s.strip() and (s.strip().lower().startswith(("no", "don't", "never", "wait"))
                                   or "!" in s)]
        with open(tricks_path, "w") as fh:
            fh.write("# Tricks — DRAFT mined from her reaction (teacher confirms)\n\n")
            for line in lines:
                fh.write(f"- {line}\n")
    if os.path.exists(card_path):
        run([os.path.join(HERE, "handiton.py"), "--work", work,
             "--title", args.title, "--tricks", tricks_path])
    print(f"\nPipeline done. Work dir: {work}")


if __name__ == "__main__":
    main()
