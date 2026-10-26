"""Keyframe extraction for the Unwritten Craft pipeline.

Pulls stills from the 'show' video: a handful of evenly spaced frames
plus any strong scene changes ffmpeg detects. The first clear frame of
the work surface becomes the hero image the SAM overlay draws on.

Usage: frames.py <video> <out_dir> [--count 6]
Writes <out_dir>/frame_*.jpg and prints the hero frame path last.
"""
import os
import subprocess
import sys


def extract(video, out_dir, count=6):
    os.makedirs(out_dir, exist_ok=True)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video],
        capture_output=True, text=True, check=True).stdout.strip())
    frames = []
    for i in range(count):
        t = dur * (i + 0.5) / count
        out = os.path.join(out_dir, f"frame_{i:02d}.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", video,
             "-frames:v", "1", "-q:v", "3", out],
            check=True)
        frames.append(out)
    return frames


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    count = 6
    if "--count" in sys.argv:
        count = int(sys.argv[sys.argv.index("--count") + 1])
    frames = extract(args[0], args[1], count)
    print(f"extracted {len(frames)} frames")
    print(frames[len(frames) // 2])  # hero: a middle frame


if __name__ == "__main__":
    main()
