"""Draft the card from a transcript with Muse Spark (Step 1).

Spark runs under prompts/card_drafter.md — the stenographer constraint.
The teacher's words in, the card out; Spark's own knowledge stays out.

Usage: draft_card.py <transcript_file> <card_out.md> [--wisdom FILE]
The wisdom file is the transcript of the post-reaction wisdom Q&A
(the recorder's attempt clip opens with it; a companion dialogue take
may serve instead). Only the teacher's answers to the four wisdom
questions may be used from it.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSE_BIN = (os.environ.get("MUSE_BIN") or shutil.which("muse")
            or os.path.expanduser("~/.local/bin/muse"))


def draft(transcript, wisdom=""):
    """Ask Spark for the card. Exits (rather than writing) if the reply
    is not a card — a non-card must never land in card.md (Wonder review).
    """
    with open(os.path.join(ROOT, "prompts", "card_drafter.md")) as fh:
        rules = fh.read()
    prompt = (rules + "\n\n=== TEACHER TRANSCRIPT (her steps) ===\n" + transcript.strip())
    if wisdom.strip():
        prompt += ("\n\n=== WISDOM Q&A — recorded AFTER her reaction; this "
                   "audio may also contain the student's attempt and room "
                   "chatter. Use ONLY her answers to the wisdom questions "
                   "(how she knows when it's right, what goes wrong, what "
                   "she changed over the years, who taught her) ===\n"
                   + wisdom.strip())
    prompt += "\n\nDraft the card now, following the rules above exactly."
    fd, prompt_path = tempfile.mkstemp(prefix="unwritten_drafter_", suffix=".txt")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(prompt)
        proc = subprocess.run(
            [MUSE_BIN, "exec", "--contributor-mode", "on", "--model",
             "muse-spark-1.3", "--prompt-file", prompt_path],
            capture_output=True, text=True, timeout=600)
    finally:
        try:
            os.unlink(prompt_path)
        except OSError:
            pass
    if proc.returncode != 0:
        sys.exit(f"Spark drafting failed: {proc.stderr[-300:]}")
    card = proc.stdout.strip()
    if not re.search(r"^\s*\d+[.)]\s+\S", card, re.MULTILINE):
        sys.exit("Spark drafting produced no numbered steps — refusing "
                 "to write it as a card. Raw output kept in stderr log.")
    return card


def main():
    ap = argparse.ArgumentParser(
        description="Draft the card from a teach transcript (Muse Spark).")
    ap.add_argument("transcript", help="the teach transcript text file")
    ap.add_argument("out", help="where to write the drafted card")
    ap.add_argument("--wisdom", default="",
                    help="transcript of the post-reaction wisdom Q&A")
    args = ap.parse_args()
    wisdom = ""
    if args.wisdom:
        with open(args.wisdom) as fh:
            wisdom = fh.read()
    with open(args.transcript) as fh:
        card = draft(fh.read(), wisdom)
    with open(args.out, "w") as fh:
        fh.write(card + "\n")
    print(f"card drafted -> {args.out}")


if __name__ == "__main__":
    main()
