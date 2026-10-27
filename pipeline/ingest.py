"""Session ingest for the Unwritten Craft pipeline.

The recorder app (app/recorder) names everything it saves
`unwritten_<step>_<time>.<ext>` with step in {show, teach, react,
attempt, camera-app}. Companion devices add two one-take kinds:
`unwritten_dialogue_<CODE>_<time>` (audio-only, near the teacher) and
`unwritten_broll_<CODE>_<time>` (second camera angle). Ingest scans a
folder of such files (however they arrived off the devices),
classifies them, and writes manifest.json:

  {"show": [...], "teach": [...], "react": [...], "attempt": [...],
   "dialogue": [...], "broll": [...], "photos": [...], "unknown": [...]}

Classification is by filename first, extension second (jpg/png -> photo).
Nothing is moved or renamed — the manifest holds paths.
"""
import json
import os
import re
import sys

STEPS = ("show", "teach", "react", "attempt")
# Companion-device takes (see app/recorder): one long second-angle video
# and/or one clean dialogue track, named with the session code.
EXTRA = ("dialogue", "broll")
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def classify(path):
    """Bucket one file: a step name, 'dialogue'/'broll', 'photos', 'unknown'."""
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]
    # The step token is LETTERS ONLY: recorder names glue suffixes onto
    # it (unwritten_teach_camera-app_CODE_..., unwritten_teach_CODE_...),
    # and a hyphen-greedy token swallows "teach-camera-app" whole,
    # misclassifying every native-app clip as unknown (Wonder review).
    m = re.match(r"unwritten_([a-z]+)", name)
    step = m.group(1) if m else None
    if step in STEPS:
        return "photos" if ext in PHOTO_EXTS else step
    if step in EXTRA:
        return step
    if ext in PHOTO_EXTS:
        return "photos"
    return "unknown"


def ingest(session_dir):
    """Walk a session folder and return {bucket: [paths, sorted]}."""
    manifest = {k: [] for k in STEPS + EXTRA + ("photos", "unknown")}
    for root, _dirs, files in os.walk(session_dir):
        for entry in files:
            full = os.path.join(root, entry)
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
