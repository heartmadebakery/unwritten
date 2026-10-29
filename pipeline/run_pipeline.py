#!/usr/bin/env python3
"""Run the Unwritten Craft pipeline — the three core things.

  python3 pipeline/run_pipeline.py <session_dir> <work_dir>
      [--lesson FILE] [--transcript FILE]

A session is one ordinary lesson filmed on a phone — no recorder
protocol, no step names, nothing performed for the machine. Stages:

  1. lesson      — find the lesson media in the folder (the largest
                   video/audio file; --lesson names it explicitly).
                   Core thing #1: the lesson video, kept whole.
  2. transcribe  — local faster-whisper -> plain + timestamped
                   transcript (skipped with --transcript FILE, which
                   must be timestamped "[mm:ss] text" lines).
  3. write-up    — Muse Spark drafts the write-up under the
                   stenographer rule (prompts/writeup_drafter.md)
                   -> writeup.md. Core thing #3.
  4. corrections — Muse Spark finds the correction moments
                   (prompts/correction_finder.md) -> corrections.json
                   + corrections.md, and each moment is cut from the
                   lesson video into clips/ when the lesson is a local
                   media file. Core thing #2: the correction clips,
                   each anchored to the mentor's exact words.

The run exits non-zero unless a write-up AND a corrections list were
produced THIS run. Stale outputs from a previous run are deleted up
front. The optional page/guide (pipeline/make_page.py) is NOT part of
this pipeline — it can be generated later, from these outputs, when
there is a recipient for it. The retired apprentice/SAM code is not
invoked here at all.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
STALE_FILES = ("manifest.json", "transcript.txt",
               "transcript_timestamped.txt", "segments.json",
               "writeup.md", "corrections.json", "corrections.md")
STALE_DIRS = ("clips", "transcript")


def py():
    return VENV_PY if os.path.exists(VENV_PY) else sys.executable


def run(cmd, stage, fatal=True):
    print(f"[{stage}] {' '.join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd))}")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          env={**os.environ, "PATH": os.environ.get("PATH", "")})
    out = (proc.stdout or "").strip()
    if out:
        print("  " + out.replace("\n", "\n  "))
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        msg = f"[{stage}] FAILED: {tail[-1] if tail else proc.returncode}"
        if fatal:
            sys.exit(msg + " — pipeline stops here (earlier stages' outputs are kept).")
        print(msg + " — continuing without it.")
        return None
    return out


def parse_ts(ts):
    """'02:08' (or '1:02:08') -> seconds. Raises ValueError."""
    parts = str(ts).strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    raise ValueError(f"bad timestamp: {ts!r}")


def fmt_ts(seconds):
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def segment_ends(timestamped_text):
    """Map each segment start (seconds) -> end (seconds), from a
    timestamped transcript: a segment ends where the next begins; the
    last segment gets a nominal 20 s."""
    starts = []
    for line in timestamped_text.splitlines():
        m = re.match(r"\[(\d+:\d{2}(?::\d{2})?)\]", line.strip())
        if m:
            try:
                starts.append(parse_ts(m.group(1)))
            except ValueError:
                pass
    ends = {}
    for i, s in enumerate(starts):
        ends[s] = starts[i + 1] if i + 1 < len(starts) else s + 20
    return ends


def clip_window(start_s, end_s):
    """Pad the correction beat a little on both sides."""
    return max(0, start_s - 2), (end_s + 2 if end_s else start_s + 20)


def render_corrections_md(hits, clips):
    """clips: {index: filename or ''}. The techniques list — together,
    the Knack."""
    lines = ["# Corrections — the techniques", "",
             "Every moment the mentor corrected the beginner, anchored "
             "to the mentor's exact words. Together these are the Knack.",
             ""]
    if not hits:
        lines.append("No corrections found in this lesson.")
    for i, hit in enumerate(hits, 1):
        lines.append(f"## {i}. {hit.get('start', '??:??')} — "
                     f"{hit.get('correcting', '')}".rstrip(" —"))
        lines.append("")
        lines.append(f"> \"{hit.get('quote', '')}\"")
        lines.append("")
        clip = clips.get(i, "")
        if clip:
            lines.append(f"Clip: `clips/{clip}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def cut_clip(lesson, start_s, end_s, out_path):
    dur = max(1, int(round(end_s - start_s)))
    is_video = os.path.splitext(lesson)[1].lower() in VIDEO_EXTS
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", str(int(start_s)),
           "-i", lesson, "-t", str(dur)]
    if is_video:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
    else:
        cmd += ["-vn", "-c:a", "aac"]
    cmd.append(out_path)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode == 0 and os.path.exists(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir",
                    help="folder with the lesson media (or the media file itself)")
    ap.add_argument("work_dir")
    ap.add_argument("--lesson", default="",
                    help="the lesson media file, if not the largest in the folder")
    ap.add_argument("--transcript", default="",
                    help="timestamped transcript file; skips transcription")
    args = ap.parse_args()

    os.makedirs(args.work_dir, exist_ok=True)
    for stale in STALE_FILES:
        p = os.path.join(args.work_dir, stale)
        if os.path.exists(p):
            os.unlink(p)
    for stale in STALE_DIRS:
        p = os.path.join(args.work_dir, stale)
        if os.path.isdir(p):
            shutil.rmtree(p)
    work = lambda *p: os.path.join(args.work_dir, *p)
    produced = set()

    # 1. lesson — core thing #1, the lesson video, kept whole
    sys.path.insert(0, HERE)
    from ingest import ingest, pick_lesson
    lesson = None
    if args.lesson:
        lesson = args.lesson
    elif os.path.isfile(args.session_dir):
        lesson = args.session_dir
    else:
        media = ingest(args.session_dir)
        lesson, note = pick_lesson(media["media"])
        if note:
            print(f"  [lesson] {note}")
        with open(work("manifest.json"), "w") as fh:
            json.dump({k: [os.path.basename(p) for p in v]
                       for k, v in media.items()}, fh, indent=1)
    if lesson:
        print(f"[lesson] {os.path.basename(lesson)}")
    elif not args.transcript:
        sys.exit("[lesson] no media file found and no --transcript given "
                 "— nothing to process.")

    # 2. transcribe (local whisper; the mentor's voice never leaves
    #    the machine for a third-party transcription service)
    timestamped_path = work("transcript_timestamped.txt")
    if args.transcript:
        shutil.copy(args.transcript, timestamped_path)
        print(f"[transcribe] skipped — using {os.path.basename(args.transcript)}")
    elif lesson:
        if run([py(), os.path.join(HERE, "transcribe.py"), lesson,
                work("transcript")], "transcribe") is not None:
            for name in ("transcript.txt", "transcript_timestamped.txt",
                         "segments.json"):
                src = work("transcript", name)
                if os.path.exists(src):
                    shutil.move(src, work(name))
            shutil.rmtree(work("transcript"), ignore_errors=True)
    if not os.path.exists(timestamped_path):
        sys.exit("[transcribe] no timestamped transcript — cannot draft "
                 "the write-up or find corrections.")
    with open(timestamped_path) as fh:
        timestamped_text = fh.read()

    # 3. write-up — core thing #3
    if run([sys.executable, os.path.join(HERE, "draft_writeup.py"),
            timestamped_path, work("writeup.md")], "write-up") is not None \
            and os.path.exists(work("writeup.md")):
        produced.add("writeup.md")

    # 4. corrections — core thing #2
    hits = []
    if run([sys.executable, os.path.join(HERE, "find_corrections.py"),
            timestamped_path, work("corrections.json")],
           "corrections") is not None \
            and os.path.exists(work("corrections.json")):
        produced.add("corrections.json")
        with open(work("corrections.json")) as fh:
            hits = json.load(fh)
    clips = {}
    if hits and lesson and os.path.exists(lesson):
        ends = segment_ends(timestamped_text)
        os.makedirs(work("clips"), exist_ok=True)
        is_video = os.path.splitext(lesson)[1].lower() in VIDEO_EXTS
        ext = ".mp4" if is_video else ".m4a"
        for i, hit in enumerate(hits, 1):
            try:
                start_s = parse_ts(hit.get("start", ""))
            except ValueError:
                print(f"  [clips] correction {i}: bad timestamp "
                      f"{hit.get('start')!r} — anchor kept, no clip cut")
                continue
            lo, hi = clip_window(start_s, ends.get(start_s))
            name = f"correction-{i:02d}{ext}"
            if cut_clip(lesson, lo, hi, work("clips", name)):
                clips[i] = name
            else:
                print(f"  [clips] correction {i}: ffmpeg cut failed — "
                      "anchor kept, no clip cut")
        if clips:
            print(f"[clips] {len(clips)} correction clip(s) cut")
    elif hits:
        print("[clips] no local lesson media — corrections are anchored "
              "by timestamp only, no clips cut")
    if "corrections.json" in produced:
        with open(work("corrections.md"), "w") as fh:
            fh.write(render_corrections_md(hits, clips))

    if "writeup.md" not in produced or "corrections.json" not in produced:
        sys.exit(f"Pipeline incomplete: produced {sorted(produced) or 'nothing'} "
                 "this run. Check the stage messages above.")
    print(f"\nPipeline done. Work dir: {args.work_dir} "
          f"(lesson, writeup.md, corrections.md, "
          f"{len(clips)} clip(s))")


if __name__ == "__main__":
    main()
