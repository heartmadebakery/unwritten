"""Draft the card from a transcript with Muse Spark (Step 1).

Spark runs under prompts/card_drafter.md — the stenographer constraint.
The teacher's words in, the card out; Spark's own knowledge stays out.

Usage: draft_card.py <transcript_file> <card_out.md> [--teacher-name NAME]
The transcript file may be plain text or the recorder's transcript.txt.
"""
import argparse
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSE_BIN = os.path.expanduser("~/.local/bin/muse")


def draft(transcript, teacher_hint=""):
    with open(os.path.join(ROOT, "prompts", "card_drafter.md")) as fh:
        rules = fh.read()
    prompt = (rules + "\n\n=== TEACHER TRANSCRIPT ===\n" + transcript.strip() +
              "\n\nDraft the card now, following the rules above exactly.")
    with open("/tmp/.unwritten_drafter_prompt.txt", "w") as fh:
        fh.write(prompt)
    proc = subprocess.run(
        [MUSE_BIN, "exec", "--contributor-mode", "on", "--model",
         "muse-spark-1.3", "--prompt-file", "/tmp/.unwritten_drafter_prompt.txt"],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        sys.exit(f"Spark drafting failed: {proc.stderr[-300:]}")
    return proc.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    args = ap.parse_args()
    with open(args.transcript) as fh:
        card = draft(fh.read())
    with open(args.out, "w") as fh:
        fh.write(card + "\n")
    print(f"card drafted -> {args.out}")


if __name__ == "__main__":
    main()
