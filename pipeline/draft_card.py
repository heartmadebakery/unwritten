"""Draft the write-up from a lesson transcript with Muse Spark.

One of the three core things (Oct 27, 2026): the write-up — her steps in
her words, usable without rewatching the lesson. Spark runs under
prompts/card_drafter.md, the stenographer rule: transcribe, compress,
order — never add. (Filename kept from the earlier card design; what it
drafts is the write-up.)

Usage: draft_card.py <transcript_file> <writeup_out.md>
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


def draft(transcript):
    with open(os.path.join(ROOT, "prompts", "card_drafter.md")) as fh:
        rules = fh.read()
    prompt = (rules + "\n\n=== LESSON TRANSCRIPT ===\n" + transcript.strip())
    prompt += "\n\nDraft the write-up now, following the rules above exactly."
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
        # Never write a non-write-up as writeup.md (Wonder review).
        sys.exit("Spark drafting produced no numbered steps — refusing "
                 "to write it as a write-up.")
    return card


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    args = ap.parse_args()
    with open(args.transcript) as fh:
        card = draft(fh.read())
    with open(args.out, "w") as fh:
        fh.write(card + "\n")
    print(f"write-up drafted -> {args.out}")


if __name__ == "__main__":
    main()
