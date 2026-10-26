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


def draft(transcript, wisdom=""):
    with open(os.path.join(ROOT, "prompts", "card_drafter.md")) as fh:
        rules = fh.read()
    prompt = (rules + "\n\n=== TEACHER TRANSCRIPT (her steps) ===\n" + transcript.strip())
    if wisdom.strip():
        prompt += ("\n\n=== WISDOM Q&A (asked AFTER her reaction — her "
                   "judgment, for the wisdom section) ===\n" + wisdom.strip())
    prompt += "\n\nDraft the card now, following the rules above exactly."
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
