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
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import meta_api
import schemas

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MUSE_BIN = (os.environ.get("MUSE_BIN") or shutil.which("muse")
            or os.path.expanduser("~/.local/bin/muse"))
SCHEMA_PATH = os.path.join(ROOT, "prompts", "writeup_schema.json")


def muse_bin():
    """The muse runner, verified present: the keyless drafting path
    shells out to it, and a missing binary must fail with a pointer,
    not a raw traceback."""
    if MUSE_BIN and (os.path.isfile(MUSE_BIN)
                     or shutil.which(MUSE_BIN)):
        return MUSE_BIN
    sys.exit("muse CLI not found (looked for %r and on PATH) — the "
             "keyless write-up path needs it; see docs/PIPELINE.md."
             % (MUSE_BIN,))

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


def parse_draft(raw):
    """Parse the model's JSON draft and validate it against the schema.
    Raises ValueError naming the problem."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        try:
            start = text.index("{")
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
        except (ValueError, json.JSONDecodeError):
            raise ValueError("draft was not JSON")
    with open(SCHEMA_PATH) as fh:
        try:
            schemas.validate(obj, json.load(fh))
        except schemas.SchemaError as exc:
            raise ValueError(f"draft failed validation: {exc}")
    return obj


def render_writeup(obj):
    """Deterministic markdown from a validated draft object. Same shape
    the page parser has always read."""
    lines = ["# %s" % obj["title"].strip(), ""]
    if obj.get("intro", "").strip():
        lines += [obj["intro"].strip(), ""]
    if obj.get("needs"):
        lines.append("## What you need")
        lines.append("")
        lines += ["- %s" % item.strip() for item in obj["needs"]]
        lines.append("")
    lines.append("## Steps")
    lines.append("")
    lines += ["%d. %s" % (i, step.strip())
              for i, step in enumerate(obj["steps"], 1)]
    lines.append("")
    if obj.get("knows"):
        lines.append("## What the mentor knows")
        lines.append("")
        lines += ["- %s" % item.strip() for item in obj["knows"]]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


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
    anything else is remuxed losslessly — or, when the codecs cannot
    ride in MP4 (the web recorder's VP8/Opus WebM: "Could not find tag
    for codec vp8"), transcoded to H.264/AAC. "" when neither works."""
    if not media or not os.path.isfile(media):
        return ""
    if os.path.splitext(media)[1].lower() in MP4_EXTS:
        return media
    out = os.path.join(tmpdir, "lesson.mp4")
    for codecs, timeout in ((["-c", "copy"], 600),
                            (["-c:v", "libx264", "-preset", "veryfast",
                              "-crf", "28", "-pix_fmt", "yuv420p",
                              "-c:a", "aac"], 3600)):
        try:
            proc = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", media] + codecs
                + [out], capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError):
            return ""
        if proc.returncode == 0 and os.path.exists(out) \
                and os.path.getsize(out) > 0:
            return out
    return ""


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
        cmd = [muse_bin(), "exec", "--contributor-mode", "on", "--model",
               "muse-spark-1.3", "--output-schema", SCHEMA_PATH,
               "--prompt-file", prompt_path]
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
                print("  [write-up] lesson is not MP4 and would not convert — "
                      "falling back to frames")
        if writeup is None:
            writeup = draft_frames(transcript, media, rules, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        writeup = render_writeup(parse_draft(writeup))
    except ValueError as exc:
        # Never write a non-write-up as writeup.md (Wonder review).
        sys.exit(f"Spark drafting {exc} — refusing to write it "
                 "as a write-up.")
    problem = validate_writeup(writeup)
    if problem:
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
