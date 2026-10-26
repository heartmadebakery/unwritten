#!/usr/bin/env python3
"""Collect fresh blind-apprentice responses using Muse models via Muse.

Each run is a separate `muse exec` invocation — a genuinely fresh model
context whose entire task input is the apprentice instruction plus the
card text. The transcript, this script's arguments, and any prior runs are
never passed. That is the information boundary, enforced mechanically.

Usage:
  python3 harness/apprentice_muse.py --card CARD.md --runs 3 \
      [--model muse-wonder-1.0] [--out responses.json]

Requires the `muse` CLI on PATH (Muse). The apprentice model
for the shipped app is a Muse model (Wonder); Muse Spark plays the
interviewer/drafter role instead and is never used as the apprentice —
it has seen the interview.
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSE_BIN = os.path.expanduser("~/.local/bin/muse")


def build_prompt(card_text):
    with open(os.path.join(ROOT, "prompts", "apprentice_instruction.txt")) as fh:
        template = fh.read()
    return template.replace("{CARD}", card_text.strip())


def one_run(prompt, model):
    with open("/tmp/.unwritten_apprentice_prompt.txt", "w") as fh:
        fh.write(prompt)
    proc = subprocess.run(
        [MUSE_BIN, "exec", "--contributor-mode", "on", "--model", model,
         "--prompt-file", "/tmp/.unwritten_apprentice_prompt.txt"],
        capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"muse exec failed ({proc.returncode}): {proc.stderr[-400:]}")
    return proc.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="muse-wonder-1.0")
    ap.add_argument("--out", default="responses.json")
    ap.add_argument("--keep-wisdom", action="store_true",
                    help="send the card WITH its wisdom section (the "
                         "wisdom-transfer check). Default: steps only — "
                         "the first attempt must not be pre-armed with "
                         "the teacher's judgment.")
    args = ap.parse_args()

    with open(args.card) as fh:
        card_text = fh.read()
    if not args.keep_wisdom:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from apprentice import strip_wisdom
        stripped = strip_wisdom(card_text)
        if stripped != card_text:
            print("wisdom section withheld from the apprentice "
                  "(steps-only card)", file=sys.stderr)
        card_text = stripped
    prompt = build_prompt(card_text)

    responses = []
    for i in range(1, args.runs + 1):
        print(f"apprentice run {i}/{args.runs} ({args.model})...", file=sys.stderr)
        responses.append(one_run(prompt, args.model))
    with open(args.out, "w") as fh:
        json.dump(responses, fh, indent=1)
    print(f"wrote {args.out} ({len(responses)} responses)")


if __name__ == "__main__":
    main()
