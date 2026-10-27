#!/usr/bin/env python3
"""Collect fresh blind-apprentice responses using Muse models via Muse.

Each run is a separate `muse exec` invocation — a genuinely fresh model
context whose entire task input is the apprentice instruction plus the
card text. The transcript, this script's arguments, and any prior runs
are never passed. Runs execute from an empty temporary working
directory so the CLI cannot pick up project files from the repo, and
the prompt travels in a unique per-run temp file that is deleted
afterwards (Wonder review, Oct 26). Responses are written with
provenance: {card_sha256, keep_wisdom, model, runs}.

Usage:
  python3 harness/apprentice_muse.py --card CARD.md --runs 3 \
      [--model muse-wonder-1.0] [--out responses.json] [--keep-wisdom]

The apprentice model for the shipped app is a Muse model (Wonder);
Muse Spark plays the interviewer/drafter role instead and is never
used as the apprentice — it has seen the interview. Muse binary
resolution: $MUSE_BIN, then PATH, then ~/.local/bin/muse.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSE_BIN = (os.environ.get("MUSE_BIN") or shutil.which("muse")
            or os.path.expanduser("~/.local/bin/muse"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apprentice import strip_wisdom, has_wisdom_section


def build_prompt(card_text):
    """The apprentice instruction with the card slotted into {CARD}."""
    with open(os.path.join(ROOT, "prompts", "apprentice_instruction.txt")) as fh:
        template = fh.read()
    return template.replace("{CARD}", card_text.strip())


def one_run(prompt, model):
    """One fresh `muse exec` call. Returns the model's raw reply text."""
    fd, prompt_path = tempfile.mkstemp(prefix="unwritten_apprentice_", suffix=".txt")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(prompt)
        with tempfile.TemporaryDirectory(prefix="unwritten_apprentice_cwd_") as cwd:
            proc = subprocess.run(
                [MUSE_BIN, "exec", "--contributor-mode", "on", "--model", model,
                 "--prompt-file", prompt_path],
                capture_output=True, text=True, timeout=600, cwd=cwd)
        if proc.returncode != 0:
            raise RuntimeError(f"muse exec failed ({proc.returncode}): {proc.stderr[-400:]}")
        return proc.stdout.strip()
    finally:
        try:
            os.unlink(prompt_path)
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(
        description="Collect fresh blind-apprentice responses (card only).")
    ap.add_argument("--card", required=True, help="the card markdown file")
    ap.add_argument("--runs", type=int, default=3,
                    help="how many fresh apprentice calls to make (default 3)")
    ap.add_argument("--model", default="muse-wonder-1.0",
                    help="apprentice model (default muse-wonder-1.0)")
    ap.add_argument("--out", default="responses.json",
                    help="where to write the responses JSON")
    ap.add_argument("--keep-wisdom", action="store_true",
                    help="send the card WITH its wisdom section (the "
                         "wisdom-transfer check). Default: steps only — "
                         "the first attempt must not be pre-armed with "
                         "the teacher's judgment.")
    args = ap.parse_args()
    if args.runs < 1:
        sys.exit("error: --runs must be >= 1")

    with open(args.card) as fh:
        card_text = fh.read()
    card_sha = hashlib.sha256(card_text.encode()).hexdigest()
    if not args.keep_wisdom:
        if has_wisdom_section(card_text):
            stripped = strip_wisdom(card_text)
            if stripped == card_text:
                # Fail CLOSED: a wisdom-looking heading we could not
                # strip must never reach the apprentice silently.
                sys.exit("error: card has a wisdom-like heading but the "
                         "strip removed nothing — refusing to leak it. "
                         "Fix the heading or pass --keep-wisdom.")
            print(f"wisdom section withheld from the apprentice "
                  f"({len(card_text) - len(stripped)} chars removed)",
                  file=sys.stderr)
            card_text = stripped
    prompt = build_prompt(card_text)

    responses = []
    for i in range(1, args.runs + 1):
        print(f"apprentice run {i}/{args.runs} ({args.model})...", file=sys.stderr)
        responses.append(one_run(prompt, args.model))
    payload = {"card_sha256": card_sha, "keep_wisdom": bool(args.keep_wisdom),
               "model": args.model, "runs": responses}
    with open(args.out, "w") as fh:
        json.dump(payload, fh, indent=1)
    print(f"wrote {args.out} ({len(responses)} responses)")


if __name__ == "__main__":
    main()
