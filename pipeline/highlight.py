"""Correction-clip highlights: a tracking spotlight on the subject.

SAM tracks the correction's subject through the clip as boxes; this
module renders one RGBA overlay PNG per frame — everything outside the
boxes dimmed, an amber edge on each box — and muxes the overlay stream
over the clip with ffmpeg. Masks ride along in the tracks JSON for a
future pixel-precise pass; the spotlight itself needs boxes only, so a
clip highlights even when mask decoding is unavailable.

stdlib + ffmpeg only. numpy deliberately not required: overlays are
built with whole-row slice ops, never per-pixel Python loops.
"""
import json
import os
import struct
import subprocess
import zlib

DIM_ALPHA = 115          # dimmed background: ~45% black
EDGE_RGB = (232, 161, 58)  # amber, the recorder accent
EDGE_WIDTH = 3


def clamp_box(box, width, height):
    """Clamp (x1,y1,x2,y2) into the frame; None when nothing remains."""
    x1, y1, x2, y2 = (int(v) for v in box)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(width, x2), min(height, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def write_png_rgba(path, width, height, pixels):
    """Write raw RGBA bytes (row-major, width*height*4) as a PNG."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6,
                                       0, 0, 0))
           + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def spotlight_frame(width, height, boxes):
    """One overlay frame: dimmed everywhere except the (clamped) boxes,
    with an amber edge around each. boxes are (x1,y1,x2,y2)."""
    dim = bytes((0, 0, 0, DIM_ALPHA))
    clear = bytes((0, 0, 0, 0))
    edge = bytes((EDGE_RGB[0], EDGE_RGB[1], EDGE_RGB[2], 255))
    pixels = bytearray(dim * (width * height))
    kept = []
    for box in boxes:
        clamped = clamp_box(box, width, height)
        if clamped:
            kept.append(clamped)
    for x1, y1, x2, y2 in kept:
        row_clear = clear * (x2 - x1)
        for y in range(y1, y2):
            off = y * width * 4
            pixels[off + x1 * 4:off + x2 * 4] = row_clear
    for x1, y1, x2, y2 in kept:
        for y in range(y1, min(y2, y1 + EDGE_WIDTH)):
            off = y * width * 4
            pixels[off + x1 * 4:off + x2 * 4] = edge * (x2 - x1)
        for y in range(max(y1, y2 - EDGE_WIDTH), y2):
            off = y * width * 4
            pixels[off + x1 * 4:off + x2 * 4] = edge * (x2 - x1)
        for y in range(y1, y2):
            off = y * width * 4
            pixels[off + x1 * 4:off + min(x2, x1 + EDGE_WIDTH) * 4] = \
                edge * (min(x2, x1 + EDGE_WIDTH) - x1)
            pixels[off + max(x1, x2 - EDGE_WIDTH) * 4:off + x2 * 4] = \
                edge * (x2 - max(x1, x2 - EDGE_WIDTH))
    return bytes(pixels)


def boxes_for_frame(parsed_frames, index):
    """Boxes visible on one frame; holds the nearest earlier frame's
    boxes across gaps (SAM emits no line where nothing is visible)."""
    best = None
    for entry in parsed_frames:
        if entry["frame"] <= index:
            best = entry
        else:
            break
    if best is None:
        return []
    return [(r["box"]["x1"], r["box"]["y1"], r["box"]["x2"], r["box"]["y2"])
            for r in best["records"]]


def probe_clip(path):
    """(width, height, fps, frame_count) via ffprobe; None on failure."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,avg_frame_rate,duration",
             "-of", "default=noprint_wrappers=1", path],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    info = {}
    for line in (proc.stdout or "").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            info[key.strip()] = value.strip()
    try:
        width, height = int(info["width"]), int(info["height"])
        num, _, den = info.get("avg_frame_rate", "30/1").partition("/")
        fps = float(num) / float(den or 1)
        count = int(float(info.get("duration", "0")) * fps)
    except (KeyError, ValueError, ZeroDivisionError):
        return None
    if width <= 0 or height <= 0 or fps <= 0 or count <= 0:
        return None
    return (width, height, fps, count)


def render_overlays(parsed_frames, width, height, count, outdir):
    """Write overlay_%05d.png for every clip frame. Returns the count."""
    os.makedirs(outdir, exist_ok=True)
    for index in range(count):
        pixels = spotlight_frame(
            width, height, boxes_for_frame(parsed_frames, index))
        write_png_rgba(os.path.join(outdir, "overlay_%05d.png" % index),
                       width, height, pixels)
    return count


def mux_highlight(clip_path, overlay_pattern, fps, out_path):
    """Overlay the PNG stream over the clip; True on success."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", clip_path,
             "-framerate", "%.3f" % fps, "-i", overlay_pattern,
             "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1",
             "-c:a", "copy", "-shortest", out_path],
            capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 and os.path.exists(out_path)


def save_tracks(path, concept, parsed_frames):
    with open(path, "w") as fh:
        json.dump({"concept": concept, "frames": parsed_frames}, fh)


def highlight_clip(clip_path, parsed_frames, out_path, workdir):
    """Full pass: probe, render overlays, mux. True on success."""
    probed = probe_clip(clip_path)
    if probed is None or not parsed_frames:
        return False
    width, height, fps, count = probed
    ovdir = os.path.join(workdir, "ov")
    render_overlays(parsed_frames, width, height, count, ovdir)
    return mux_highlight(clip_path, os.path.join(ovdir, "overlay_%05d.png"),
                         fps, out_path)
