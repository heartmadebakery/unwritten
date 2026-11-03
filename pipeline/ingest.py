"""Session ingest for the Unwritten Craft pipeline.

Simplified core (Oct 27, 2026): a session is one ordinary lesson filmed
on a phone. There is no recorder protocol and no step naming — ingest
scans a folder and classifies files by extension only:

  {"media": [...], "photos": [...], "unknown": [...]}

"media" is every video/audio file; the pipeline takes the largest one
as the lesson (a full lesson dwarfs any stray clip) and says so when
there is more than one. Nothing is moved or renamed.
"""
import json
import os
import sys

MEDIA_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi",
              ".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}


def classify(path):
    ext = os.path.splitext(os.path.basename(path))[1].lower()
    if ext in MEDIA_EXTS:
        return "media"
    if ext in PHOTO_EXTS:
        return "photos"
    return "unknown"


def ingest(session_dir):
    manifest = {"media": [], "photos": [], "unknown": []}
    for root, _dirs, files in os.walk(session_dir):
        for entry in files:
            full = os.path.join(root, entry)
            manifest[classify(full)].append(full)
    for key in manifest:
        manifest[key].sort()
    return manifest


def pick_lesson(media):
    """The lesson is the largest media file. Returns (path, note)."""
    if not media:
        return None, ""
    if len(media) == 1:
        return media[0], ""
    def _size(p):
        try:
            return os.path.getsize(p)
        except OSError:
            return -1
    biggest = max(media, key=_size)
    return biggest, (f"{len(media)} media files found — using the largest "
                     f"as the lesson: {os.path.basename(biggest)}")


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
