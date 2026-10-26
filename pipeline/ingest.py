"""Session ingest for the Unwritten Craft pipeline.

The recorder app (app/recorder) names everything it saves
`unwritten_<step>_<time>.<ext>` with step in {show, teach, react,
attempt, camera-app}. Ingest scans a folder of such files (however they
arrived off the phone), classifies them, and writes manifest.json:

  {"show": [...], "teach": [...], "react": [...], "attempt": [...],
   "photos": [...], "unknown": [...]}

Classification is by filename first, extension second (jpg/png -> photo).
Nothing is moved or renamed — the manifest holds paths.
"""
import json
import os
import re
import sys

STEPS = ("show", "teach", "react", "attempt")
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def classify(path):
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]
    m = re.search(r"unwritten_([a-z-]+)", name)
    step = m.group(1) if m else None
    if step in STEPS:
        return "photos" if ext in PHOTO_EXTS else step
    if step == "camera-app":
        return "unknown"
    if ext in PHOTO_EXTS:
        return "photos"
    return "unknown"


def ingest(session_dir):
    manifest = {k: [] for k in STEPS + ("photos", "unknown")}
    for entry in sorted(os.listdir(session_dir)):
        full = os.path.join(session_dir, entry)
        if os.path.isfile(full):
            manifest[classify(full)].append(full)
    for key in manifest:
        manifest[key].sort()
    return manifest


def main():
    if len(sys.argv) != 3:
        print("usage: ingest.py <session_dir> <manifest_out.json>")
        sys.exit(2)
    manifest = ingest(sys.argv[1])
    with open(sys.argv[2], "w") as fh:
        json.dump(manifest, fh, indent=1)
    counts = {k: len(v) for k, v in manifest.items() if v}
    print("ingested:", counts or "nothing recognized")


if __name__ == "__main__":
    main()
