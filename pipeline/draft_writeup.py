"""Draft the write-up from a lesson transcript + video with Muse Spark.

One of the three core things (Oct 27, 2026): the write-up — a polished,
sectioned document that reads well and stands without the lesson. Spark
runs under prompts/writeup_drafter.md: the transcript is the spine, and
anything the transcript leaves unsaid is filled in from the lesson
video itself — never from outside knowledge. With MODEL_API_KEY set,
Spark watches the whole video (Meta video understanding); otherwise
evenly spaced still frames go along instead, and without lesson media
at all the draft is written from the transcript alone.

Usage: draft_writeup.py <transcript_file> <writeup_out.md> [lesson_media]
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

import meta_api

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSE_BIN = (os.environ.get("MUSE_BIN") or shutil.which("muse")
            or os.path.expanduser("~/.local/bin/muse"))

MAX_FRAMES = 16
FRAME_EVERY = 30  # aim for about one frame per 30 seconds of lesson
FRAME_WIDTH = 640


def media_duration(path):
    """Lesson length in seconds, or None when it cannot be read."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return float((proc.stdout or "").strip())
    except ValueError:
        return None


def extract_frames(media, outdir):
    """Evenly spaced JPEG frames as [(mm:ss, path)]. Partial results
    are kept; [] when the media is missing, unreadable, or has no
    video — the draft then falls back to the transcript alone."""
    if not media or not os.path.isfile(media):
        return []
    dur = media_duration(media)
    if not dur or dur <= 0:
        return []
    n = min(MAX_FRAMES, max(4, int(dur // FRAME_EVERY)))
    frames = []
    for i in range(n):
        t = dur * (i + 1) / (n + 1)
        out = os.path.join(outdir, "frame-%02d.jpg" % (i + 1))
        try:
            proc = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", "%.1f" % t,
                 "-i", media, "-frames:v", "1", "-vf",
                 "scale=%d:-1" % FRAME_WIDTH, out],
                capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0 or not os.path.exists(out):
            continue
        frames.append(("%02d:%02d" % (int(t // 60), int(t % 60)), out))
    return frames


def validate_writeup(text):
    """The shape the pipeline and the page parser depend on: a title,
    numbered steps, and at least one ## section. Returns "" when the
    draft is acceptable, else the reason it is not a write-up."""
    if not re.search(r"^#\s+\S", text, re.MULTILINE):
        return "produced no title"
    if not re.search(r"^\s*\d+[.)]\s+\S", text, re.MULTILINE):
        return "produced no numbered steps"
    if not re.search(r"^##\s+\S", text, re.MULTILINE):
        return "produced no sections"
    return ""


MP4_EXTS = {".mp4", ".mov", ".m4v"}


def ensure_mp4(media, tmpdir):
    """The video API takes MP4-family containers: mp4 passes through,
    anything else is remuxed losslessly, "" when neither works."""
    if not media or not os.path.isfile(media):
        return ""
    if os.path.splitext(media)[1].lower() in MP4_EXTS:
        return media
    out = os.path.join(tmpdir, "lesson.mp4")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", media, "-c", "copy", out],
            capture_output=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0 or not os.path.exists(out):
        return ""
    return out


def draft_video(transcript, mp4):
    """Full-video understanding: Spark watches the lesson (visuals and
    speech) alongside the transcript. Raises MetaApiError."""
    with open(os.path.join(ROOT, "prompts", "writeup_drafter.md")) as fh:
        rules = fh.read()
    prompt = (rules + "\n\n=== LESSON VIDEO ===\nWatch the attached "
              "lesson video — its visuals and its speech — alongside the "
              "transcript below. The transcript is the spine; the video "
              "fills what it leaves unsaid." +
              "\n\n=== LESSON TRANSCRIPT ===\n" + transcript.strip() +
              "\n\nDraft the write-up now, following the rules above exactly.")
    file_id = meta_api.upload_file(mp4)
    try:
        return meta_api.ask_video({"file_id": file_id}, prompt,
                                  meta_api.api_key())
    finally:
        meta_api.delete_file(file_id)


def draft_frames(transcript, media, rules, tmpdir):
    """Still-frames path via the local muse runner (no API key)."""
    frames = extract_frames(media, tmpdir) if media else []
    if frames:
        guide = "\n".join(
            "- attached image %d of %d: video frame at %s" % (i, len(frames), ts)
            for i, (ts, _) in enumerate(frames, 1))
        prompt = (rules + "\n\n=== VIDEO FRAMES ===\n" + guide +
                  "\n\n=== LESSON TRANSCRIPT ===\n" + transcript.strip())
        images = [path for _, path in frames]
    else:
        prompt = (rules + "\n\nNo video frames were available for this "
                  "lesson — write from the transcript alone, and omit "
                  "anything you cannot ground in it." +
                  "\n\n=== LESSON TRANSCRIPT ===\n" + transcript.strip())
        images = []
    fd, prompt_path = tempfile.mkstemp(prefix="unwritten_drafter_",
                                       suffix=".txt")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(prompt)
        cmd = [MUSE_BIN, "exec", "--contributor-mode", "on", "--model",
               "muse-spark-1.3", "--prompt-file", prompt_path]
        for path in images:
            cmd += ["--image", path]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=900)
    finally:
        try:
            os.unlink(prompt_path)
        except OSError:
            pass
    if proc.returncode != 0:
        sys.exit(f"Spark drafting failed: {proc.stderr[-300:]}")
    return proc.stdout.strip()


def draft(transcript, media=""):
    with open(os.path.join(ROOT, "prompts", "writeup_drafter.md")) as fh:
        rules = fh.read()
    tmpdir = tempfile.mkdtemp(prefix="unwritten_frames_")
    try:
        writeup = None
        if media and meta_api.api_key():
            mp4 = ensure_mp4(media, tmpdir)
            if mp4:
                try:
                    writeup = draft_video(transcript, mp4)
                except meta_api.MetaApiError as exc:
                    print("  [write-up] video understanding unavailable "
                          "(%s) — falling back to frames" % exc)
            else:
                print("  [write-up] lesson is not MP4 and would not remux — "
                      "falling back to frames")
        if writeup is None:
            writeup = draft_frames(transcript, media, rules, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    problem = validate_writeup(writeup)
    if problem:
        # Never write a non-write-up as writeup.md (Wonder review).
        sys.exit(f"Spark drafting {problem} — refusing to write it "
                 "as a write-up.")
    return writeup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("media", nargs="?",
                    help="lesson video: watched whole with MODEL_API_KEY, "
                         "else still frames fill what the transcript leaves "
                         "unsaid (omit for transcript-only)")
    args = ap.parse_args()
    with open(args.transcript) as fh:
        writeup = draft(fh.read(), args.media or "")
    with open(args.out, "w") as fh:
        fh.write(writeup + "\n")
    print(f"write-up drafted -> {args.out}")


if __name__ == "__main__":
    main()
