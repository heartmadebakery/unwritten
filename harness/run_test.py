#!/usr/bin/env python3
"""Run the Unwritten Craft mechanic test (text-only).

Usage:
  python3 harness/run_test.py --card CARD.md --responses RESPONSES.json [--out REPORT.md]

RESPONSES.json is a JSON list of raw apprentice response strings, each from
a FRESH model call whose only context was the card (see
prompts/apprentice.md). The report ranks the card's steps by silence:
parameters stuck at the geometric-neutral default, or diverging across
runs, are where the teacher's unwritten knowledge lives.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from apprentice import parse_commitments, analyze, render_report


def card_title(card_text):
    for line in card_text.splitlines():
        if line.startswith("#"):
            return line.lstrip("# ").strip()
    return "untitled card"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--responses", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    with open(args.card) as fh:
        card = fh.read()
    with open(args.responses) as fh:
        data = json.load(fh)
    # Provenance (Wonder review): collectors now write
    # {card_sha256, keep_wisdom, model, runs:[...]}; accept the legacy
    # bare list too, but say which one this is in the report.
    provenance = ""
    if isinstance(data, dict):
        raw_responses = data.get("runs", [])
        import hashlib
        digest = hashlib.sha256(card.encode()).hexdigest()
        if data.get("card_sha256") and data["card_sha256"] != digest:
            provenance = ("⚠️ Provenance: these runs were collected against a "
                          "DIFFERENT card (hash mismatch) — scores may not "
                          "describe this card.")
        elif data.get("keep_wisdom"):
            provenance = ("Provenance: runs collected WITH the wisdom section "
                          "unsealed (--keep-wisdom).")
        else:
            provenance = "Provenance: steps-only runs; card hash verified."
    else:
        raw_responses = data
        provenance = ("Provenance: legacy response file (no card hash, no "
                      "wisdom flag) — treat scores with care.")

    runs, failures = [], 0
    for raw in raw_responses:
        if not isinstance(raw, str):
            failures += 1
            continue
        try:
            runs.append(parse_commitments(raw))
        except (ValueError, json.JSONDecodeError) as e:
            failures += 1
            print(f"warning: unparseable response skipped ({e})", file=sys.stderr)
    if not runs:
        print("error: no parseable apprentice responses", file=sys.stderr)
        sys.exit(1)
    notes = provenance
    if failures:
        notes += (f"\n⚠️ {failures} of {len(raw_responses)} responses were "
                  "unparseable and dropped — divergence evidence is weakened.")
    if len(runs) < 2:
        notes += ("\n⚠️ Only one parseable run: divergence across runs is "
                  "impossible, so silence here is defaults-only evidence.")

    report = render_report(card_title(card), runs, analyze(runs), notes=notes)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(report)
        print(f"wrote {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
