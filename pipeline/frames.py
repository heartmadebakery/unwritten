"""
RETIRED (Oct 27, 2026): extracted keyframes for the SAM overlay's
hero image. Not called by pipeline/run_pipeline.py or anything in
the core flow; kept in the tree as a retired experiment.

Keyframe extraction for the Unwritten Craft pipeline.

Pulls evenly spaced stills from the 'show' video (absolute-time
sampling when the container carries no duration, as MediaRecorder
WebMs often don't). The middle frame becomes the hero image the SAM
overlay draws on.

Usage: frames.py <video> <out_dir> [--count 6]
Writes <out_dir>/frame_*.jpg and prints the hero frame path last.
"""
import os
import subprocess
import sys


def extract(video, out_dir, count=6):
    os.makedirs(out_dir, exist_ok=True)
    dur = probe_duration(video)
    frames = []
    if dur:
        times = [dur * (i + 0.5) / count for i in range(count)]
    else:
        # No container duration (common for MediaRecorder WebM): sample
        # absolute times; per-frame failures are tolerated below.
        times = [1 + 2 * i for i in range(count)]
    for i, t in enumerate(times):
        out = os.path.join(out_dir, f"frame_{i:02d}.jpg")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
             "-frames:v", "1", "-q:v", "3", out],
            capture_output=True)
        if proc.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
            frames.append(out)
    if not frames:
        raise RuntimeError(f"no frames could be extracted from {video}")
    return frames


def probe_duration(video):
    """Container duration in seconds, or None if the file doesn't say
    (ffprobe prints 'N/A' for many WebMs — float() on that used to kill
    the whole pipeline before the card existed)."""
    for entries in ("format=duration", "stream=duration"):
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", entries,
                 "-of", "csv=p=0", video],
                capture_output=True, text=True, check=True).stdout.strip()
            return float(out)
        except (subprocess.CalledProcessError, ValueError):
            continue
    return None


def main():
    argv = sys.argv[1:]
    count = 6
    if "--count" in argv:
        i = argv.index("--count")
        count = max(1, int(argv[i + 1]))
        del argv[i:i + 2]
    if len(argv) != 2:
        print("usage: frames.py <video> <out_dir> [--count 6]")
        sys.exit(2)
    frames = extract(argv[0], argv[1], count)
    print(f"extracted {len(frames)} frames")
    print(frames[len(frames) // 2])  # hero: a middle frame


if __name__ == "__main__":
    main()
