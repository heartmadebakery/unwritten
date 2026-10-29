#!/usr/bin/env python3
"""Run the Unwritten Craft pipeline — the three core things.

  python3 pipeline/run_pipeline.py <session_dir> <work_dir>
      [--lesson FILE] [--transcript FILE]
  python3 pipeline/run_pipeline.py --cloud <work_root> [--max N]
      [--retry-failed] [--cloud-state FILE]

A session is one ordinary lesson filmed on a phone — no recorder
protocol, no step names, nothing performed for the machine. Stages:

  1. lesson      — find the lesson media in the folder (the largest
                   video/audio file; --lesson names it explicitly).
                   Core thing #1: the lesson video, kept whole.
  2. transcribe  — Meta speech-to-text (or local faster-whisper
                   without MODEL_API_KEY) -> plain + timestamped
                   transcript (skipped with --transcript FILE, which
                   must be timestamped "[mm:ss] text" lines).
  3. write-up    — Muse Spark drafts the polished, sectioned
                   write-up (prompts/writeup_drafter.md) from the
                   transcript plus frames of the lesson video, which
                   fill what the transcript leaves unsaid
                   -> writeup.md. Core thing #3.
  4. corrections — Muse Spark finds the correction moments
                   (prompts/correction_finder.md) -> corrections.json
                   + corrections.md, and each moment is cut from the
                   lesson video into clips/ when the lesson is a local
                   media file. Core thing #2: the correction clips,
                   each anchored to the mentor's exact words. With
                   MODEL_API_KEY, each video clip also gains a
                   SAM-tracked spotlight highlight (subject named by
                   the finder's "segment" phrase).

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
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import highlight as highlight_mod
import meta_api
VENV_PY = os.path.join(ROOT, ".venv", "bin", "python")
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
STALE_FILES = ("manifest.json", "transcript.txt",
               "transcript_timestamped.txt", "segments.json",
               "writeup.md", "corrections.json", "corrections.md",
               "poster.jpg", "chapters.json")
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


def render_corrections_md(hits, clips, highlights=None, redacted=None):
    """clips/highlights/redacted: {index: filename or ''}. The
    techniques list — together, the Knack."""
    highlights = highlights or {}
    redacted = redacted or {}
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
        highlight = highlights.get(i, "")
        if highlight:
            lines.append(f"Highlight: `clips/{highlight}` "
                         "(subject tracked, rest dimmed)")
        share = redacted.get(i, "")
        if share:
            lines.append(f"Share-safe: `clips/{share}` "
                         "(faces covered)")
        if clip or highlight or share:
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


def _validate_masks_advisory(parsed_frames):
    """Decode a few masks so API drift fails loudly in the log while the
    boxes-only spotlight still renders. Returns True when checked."""
    try:
        from meta_sam_parser import (SegmentationMask,
                                     decode_mask_to_raster)
    except ImportError:
        return False
    checked = 0
    for entry in parsed_frames:
        for rec in entry["records"]:
            mask = rec["mask"]
            raster = decode_mask_to_raster(SegmentationMask(
                encoding="one_bit" if mask["enc"] == "!" else "lossless",
                payload=mask["enc"] + mask["payload"],
                width=mask["w"], height=mask["h"]))
            if len(raster) != mask["w"] * mask["h"]:
                raise ValueError("mask raster size mismatch")
            checked += 1
            if checked >= 3:
                return True
    return checked > 0


def _segment_clip(clip_path, concept):
    """Upload a clip, track one concept through it, return the parsed
    frames ([] when nothing matched). Raises MetaApiError."""
    file_id = meta_api.upload_file(clip_path)
    try:
        wire = meta_api.segment_video_lines(
            file_id, concept, meta_api.api_key())
    finally:
        meta_api.delete_file(file_id)
    return meta_api.parse_segmentation(wire)


def try_highlight(work, clip_name, concept, index):
    """SAM-tracked spotlight version of a correction clip. Returns the
    highlight filename or "": needs MODEL_API_KEY, never raises, never
    blocks the run — the plain clip and the timestamp anchor stand."""
    if not concept or not meta_api.api_key():
        return ""
    clip_path = work("clips", clip_name)
    try:
        parsed = _segment_clip(clip_path, concept)
        if not parsed:
            print(f"  [highlights] correction {index}: {concept!r} not "
                  f"visible — plain clip kept")
            return ""
        try:
            _validate_masks_advisory(parsed)
        except Exception as exc:
            print(f"  [highlights] correction {index}: mask check ({exc}) "
                  f"— boxes still render")
        highlight_mod.save_tracks(
            work("clips", "segments-%02d.json" % index), concept, parsed)
        tmpdir = tempfile.mkdtemp(prefix="unwritten_highlight_")
        try:
            ok = highlight_mod.highlight_clip(
                clip_path, parsed,
                work("clips", "highlight-%02d.mp4" % index), tmpdir)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        if not ok:
            print(f"  [highlights] correction {index}: render failed — "
                  f"plain clip kept")
            return ""
        return "highlight-%02d.mp4" % index
    except meta_api.MetaApiError as exc:
        print(f"  [highlights] correction {index}: {exc} — plain clip kept")
        return ""
    except Exception as exc:
        print(f"  [highlights] correction {index}: unexpected ({exc}) — "
              f"plain clip kept")
        return ""


def try_redact(work, clip_name, index):
    """Share-safe version of a correction clip: opaque covers over
    every tracked face (clips/redacted-NN.mp4). Returns "" when there
    is no key or no face — never raises, never blocks the run."""
    if not meta_api.api_key():
        return ""
    clip_path = work("clips", clip_name)
    try:
        parsed = _segment_clip(clip_path, "face")
        if not parsed:
            return ""
        highlight_mod.save_tracks(
            work("clips", "faces-%02d.json" % index), "face", parsed)
        tmpdir = tempfile.mkdtemp(prefix="unwritten_redact_")
        try:
            ok = highlight_mod.redact_clip(
                clip_path, parsed,
                work("clips", "redacted-%02d.mp4" % index), tmpdir)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        return "redacted-%02d.mp4" % index if ok else ""
    except Exception as exc:
        print(f"  [redacted] correction {index}: {exc} — original kept")
        return ""


POSTER_PROMPT = ("At what timestamp does the finished work look its "
                 "best — the single frame that would best represent "
                 "this lesson? Answer with only mm:ss.")

CHAPTERS_PROMPT = ("List the main chapters of this lesson video as a "
                   "JSON array of {\"start\": \"mm:ss\", \"label\": "
                   "\"...\"} objects: 3 to 8 chapters covering the "
                   "whole lesson in time order, labels of 2 to 5 "
                   "words. Output ONLY the JSON array.")


def pick_poster_ts(text):
    """Seconds from a '... mm:ss ...' answer, or None."""
    m = re.search(r"(\d+:\d{2}(?::\d{2})?)", text or "")
    if not m:
        return None
    try:
        return parse_ts(m.group(1))
    except ValueError:
        return None


def parse_chapters(text):
    """Chapters JSON into [{start, label}] with validated mm:ss starts.
    Raises ValueError on anything else."""
    import schemas
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        raise ValueError("chapters were not JSON")
    with open(os.path.join(HERE, "..", "prompts",
                           "chapters_schema.json")) as fh:
        try:
            schemas.validate(obj, json.load(fh))
        except schemas.SchemaError as exc:
            raise ValueError(f"chapters failed validation: {exc}")
    chapters = []
    for entry in obj:
        chapters.append({"start": entry["start"].strip(),
                         "label": entry["label"].strip()})
        parse_ts(chapters[-1]["start"])  # raises on bad stamps
    return chapters


def try_chapters(work, lesson):
    """Chapter timeline (chapters.json) via video understanding. Needs
    a key and MP4-family media; never raises, never blocks the run."""
    if not lesson or not os.path.exists(lesson) or not meta_api.api_key():
        return ""
    if os.path.splitext(lesson)[1].lower() not in (".mp4", ".mov", ".m4v"):
        return ""
    try:
        file_id = meta_api.upload_file(lesson)
        try:
            answer = meta_api.ask_video(
                {"file_id": file_id}, CHAPTERS_PROMPT, meta_api.api_key(),
                cache_key="unwritten-chapters")
        finally:
            meta_api.delete_file(file_id)
        chapters = parse_chapters(answer)
        if not chapters:
            return ""
        with open(work("chapters.json"), "w") as fh:
            json.dump(chapters, fh, indent=1)
        return "chapters.json"
    except Exception as exc:
        print(f"  [chapters] {exc} — skipped")
        return ""


def try_poster(work, lesson):
    """Pick a representative frame as poster.jpg. With a key and an
    MP4-family lesson, Spark watches the video and names the moment;
    otherwise the midpoint. Never raises, never blocks the run.
    Returns "poster.jpg" or ""."""
    if not lesson or not os.path.exists(lesson):
        return ""
    out = work("poster.jpg")
    try:
        stamp = None
        from draft_writeup import MP4_EXTS
        if meta_api.api_key() and \
                os.path.splitext(lesson)[1].lower() in MP4_EXTS:
            file_id = meta_api.upload_file(lesson)
            try:
                answer = meta_api.ask_video({"file_id": file_id},
                                            POSTER_PROMPT,
                                            meta_api.api_key())
            finally:
                meta_api.delete_file(file_id)
            stamp = pick_poster_ts(answer)
        if stamp is None:
            probed = highlight_mod.probe_clip(lesson)
            if probed is None:
                return ""
            _, _, fps, count = probed
            stamp = (count / fps) / 2 if fps else 0
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(int(stamp)),
             "-i", lesson, "-frames:v", "1", "-vf", "scale=1280:-1",
             out], capture_output=True, timeout=120)
        if proc.returncode != 0 or not os.path.exists(out):
            return ""
        return "poster.jpg"
    except Exception:
        return ""


def _run_one(lesson, work):
    """Run one single-lesson pipeline. Split out so tests can stub it."""
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), lesson, work])
    return proc.returncode


def run_cloud_mode(root, max_n=0, retry_failed=False, state_path=""):
    """Fetch every new finished Cloud lesson and run the full pipeline
    on each into its own subdir of root. Returns an exit code."""
    import cloud_fetch  # lazy so local-only runs never touch the cloud path

    cfg = cloud_fetch.load_config()
    os.makedirs(root, exist_ok=True)
    state_path = state_path or os.path.join(root, "cloud_state.json")
    state = cloud_fetch.load_state(state_path)
    videos = cloud_fetch.list_videos(cfg)
    ready = cloud_fetch.select_ready(videos, state,
                                     retry_failed=retry_failed)
    if max_n and max_n > 0:
        ready = ready[:max_n]
    if not ready:
        print("[cloud] no new finished videos.")
        return 0
    dl_dir = os.path.join(root, "cloud_downloads")
    os.makedirs(dl_dir, exist_ok=True)
    failures = 0
    for vid in ready:
        guid = vid.get("guid", "")
        title = vid.get("title") or "lesson"
        slug = "%s__%s" % (cloud_fetch.sanitize(title), guid[:8])
        entry = state.get(guid, {})
        lesson = entry.get("lesson", "")
        if not (lesson and os.path.exists(lesson)):
            try:
                lesson = cloud_fetch.download_video(cfg, vid, dl_dir)
            except Exception as exc:
                failures += 1
                print("[cloud] download failed for %r: %s" % (title, exc))
                state[guid] = {"title": title, "result": "failed",
                               "error": str(exc)}
                cloud_fetch.save_state(state_path, state)
                continue
            state[guid] = {"title": title, "lesson": lesson,
                           "result": "downloaded"}
            cloud_fetch.save_state(state_path, state)
        work = os.path.join(root, slug)
        code = _run_one(lesson, work)
        state[guid] = {"title": title, "lesson": lesson, "workDir": work,
                       "result": "done" if code == 0 else "failed"}
        cloud_fetch.save_state(state_path, state)
        if code != 0:
            failures += 1
            print("[cloud] pipeline failed for %r — recorded as failed; "
                  "use --retry-failed to retry it." % title)
        else:
            print("[cloud] done %r -> %s" % (title, work))
    print("[cloud] %d video(s) processed, %d failed."
          % (len(ready), failures))
    return 1 if failures else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session_dir", nargs="?",
                    help="folder with the lesson media (or the media file itself)")
    ap.add_argument("work_dir", nargs="?",
                    help="output dir for the run (or the cloud work root with --cloud)")
    ap.add_argument("--lesson", default="",
                    help="the lesson media file, if not the largest in the folder")
    ap.add_argument("--transcript", default="",
                    help="timestamped transcript file; skips transcription")
    ap.add_argument("--cloud", action="store_true",
                    help="fetch new finished Cloud lessons and run one "
                         "pipeline per video into subdirs of the work root")
    ap.add_argument("--max", type=int, default=0,
                    help="max cloud videos per --cloud run (0 = no cap)")
    ap.add_argument("--retry-failed", action="store_true",
                    help="retry cloud videos recorded as failed")
    ap.add_argument("--cloud-state", default="",
                    help="state file for --cloud "
                         "(default <work_root>/cloud_state.json)")
    args = ap.parse_args()

    if args.cloud:
        if args.session_dir is not None or not args.work_dir:
            ap.error("--cloud takes exactly one positional: the work root "
                     "(e.g. run_pipeline.py --cloud work/cloud)")
        sys.exit(run_cloud_mode(args.work_dir, max_n=args.max,
                                retry_failed=args.retry_failed,
                                state_path=args.cloud_state))
    if not args.session_dir or not args.work_dir:
        ap.error("the following arguments are required: "
                 "session_dir, work_dir")

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

    # 2. transcribe (Meta speech-to-text with MODEL_API_KEY, else
    #    local whisper; see pipeline/transcribe.py for the routing)
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

    # 3. write-up — core thing #3 (transcript + lesson frames;
    #    transcript-only when there is no local lesson media)
    cmd = [sys.executable, os.path.join(HERE, "draft_writeup.py"),
           timestamped_path, work("writeup.md")]
    if lesson and os.path.exists(lesson):
        cmd.append(lesson)
    if run(cmd, "write-up") is not None \
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
    # 3.5 poster + chapters — representative frame and timeline,
    #    never block the run
    poster = try_poster(work, lesson) if lesson else ""
    if poster:
        print(f"[poster] {poster}")
    chapters = try_chapters(work, lesson) if lesson else ""
    if chapters:
        print(f"[chapters] {chapters}")

    clips = {}
    highlights = {}
    redacted = {}
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
                if is_video:
                    hl = try_highlight(work, name, hit.get("segment", ""), i)
                    if hl:
                        highlights[i] = hl
                    share = try_redact(work, name, i)
                    if share:
                        redacted[i] = share
            else:
                print(f"  [clips] correction {i}: ffmpeg cut failed — "
                      "anchor kept, no clip cut")
        if clips:
            print(f"[clips] {len(clips)} correction clip(s) cut")
        if highlights:
            print(f"[highlights] {len(highlights)} spotlight clip(s) cut")
        if redacted:
            print(f"[redacted] {len(redacted)} share-safe clip(s) cut")
    elif hits:
        print("[clips] no local lesson media — corrections are anchored "
              "by timestamp only, no clips cut")
    if "corrections.json" in produced:
        with open(work("corrections.md"), "w") as fh:
            fh.write(render_corrections_md(hits, clips, highlights, redacted))

    if "writeup.md" not in produced or "corrections.json" not in produced:
        sys.exit(f"Pipeline incomplete: produced {sorted(produced) or 'nothing'} "
                 "this run. Check the stage messages above.")
    print(f"\nPipeline done. Work dir: {args.work_dir} "
          f"(lesson, writeup.md, corrections.md, "
          f"{len(clips)} clip(s))")


if __name__ == "__main__":
    main()
