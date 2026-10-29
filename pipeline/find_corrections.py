"""Find the correction moments in a lesson transcript (Muse Spark).

The simplified core's second half: after the write-up, surface every moment
where the mentor corrected the beginner — each anchored to its timestamp
and the mentor's exact words — under prompts/correction_finder.md.

Usage: find_corrections.py <transcript_file> <out.json>
The transcript is timestamped segments, one per line: "[mm:ss] text".
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import schemas

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSE_BIN = (os.environ.get("MUSE_BIN") or shutil.which("muse")
            or os.path.expanduser("~/.local/bin/muse"))
SCHEMA_PATH = os.path.join(ROOT, "prompts", "correction_schema.json")


def find(transcript):
    with open(os.path.join(ROOT, "prompts", "correction_finder.md")) as fh:
        rules = fh.read()
    prompt = rules + "\n\n=== LESSON TRANSCRIPT ===\n" + transcript.strip()
    fd, prompt_path = tempfile.mkstemp(prefix="unwritten_finder_",
                                       suffix=".txt")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(prompt)
        proc = subprocess.run(
            [MUSE_BIN, "exec", "--contributor-mode", "on", "--model",
             "muse-spark-1.3", "--output-schema", SCHEMA_PATH,
             "--prompt-file", prompt_path],
            capture_output=True, text=True, timeout=600)
    finally:
        try:
            os.unlink(prompt_path)
        except OSError:
            pass
    if proc.returncode != 0:
        sys.exit(f"correction finder failed: {proc.stderr[-300:]}")
    return parse_hits(proc.stdout)


def parse_hits(raw):
    """Parse the finder's JSON array. The model sometimes emits the
    array twice (observed: `[][]` for "no corrections") or with stray
    prose, so take the first complete JSON value instead of requiring
    the whole output to be exactly one document."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        hits = json.loads(text)
    except json.JSONDecodeError:
        try:
            start = text.index("[")
            hits, _ = json.JSONDecoder().raw_decode(text[start:])
        except (ValueError, json.JSONDecodeError):
            sys.exit(f"finder output was not JSON: {raw[:300]}")
    if not isinstance(hits, list):
        sys.exit("finder output was not a JSON array")
    try:
        with open(SCHEMA_PATH) as fh:
            schemas.validate(hits, json.load(fh))
    except schemas.SchemaError as exc:
        sys.exit(f"finder output failed validation: {exc}")
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    args = ap.parse_args()
    with open(args.transcript) as fh:
        transcript = fh.read()
    hits = find(transcript)
    with open(args.out, "w") as fh:
        json.dump(hits, fh, indent=1)
    print(f"{len(hits)} correction(s) -> {args.out}")


if __name__ == "__main__":
    main()
