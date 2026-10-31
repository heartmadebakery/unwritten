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
EDGE_RGB = (232, 161, 58)  # amber, the app accent
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
    """Boxes visible on one frame; holds the nearest tracked frame's
    boxes across gaps (SAM emits no line where nothing is visible) —
    the nearest earlier frame first, the nearest later frame before
    the first track. A share-safe redaction must never render a bare
    face for want of an earlier box."""
    best, best_key = None, None
    for entry in parsed_frames:
        frame = entry["frame"]
        key = (0, index - frame) if frame <= index else (1, frame - index)
        if best_key is None or key < best_key:
            best_key, best = key, entry
    if best is None:
        return []
    return [(r["box"]["x1"], r["box"]["y1"], r["box"]["x2"], r["box"]["y2"])
            for r in best["records"]]


FACE_RGB = (20, 20, 20)
FACE_PAD = 0.15  # heads move; cover a margin around each tracked box


def _pad(box, width, height):
    x1, y1, x2, y2 = box
    px, py = (x2 - x1) * FACE_PAD, (y2 - y1) * FACE_PAD
    return (max(0, int(x1 - px)), max(0, int(y1 - py)),
            min(width, int(x2 + px)), min(height, int(y2 + py)))


def solid_frame(width, height, boxes):
    """One redaction overlay: fully opaque dark boxes over each (padded,
    clamped) face, transparent elsewhere. Plain flat cover — chosen so a
    face never peeks through a soft mask edge."""
    cover = bytes((FACE_RGB[0], FACE_RGB[1], FACE_RGB[2], 255))
    pixels = bytearray(bytes(4) * (width * height))
    for box in boxes:
        clamped = clamp_box(_pad(box, width, height), width, height)
        if not clamped:
            continue
        x1, y1, x2, y2 = clamped
        run = cover * (x2 - x1)
        for y in range(y1, y2):
            off = y * width * 4
            pixels[off + x1 * 4:off + x2 * 4] = run
    return bytes(pixels)


def _fps(rate):
    """'30000/1001' -> float, or None when unusable (0/0, missing)."""
    try:
        num, _, den = (rate or "").partition("/")
        fps = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return None
    return fps if fps > 0 else None


def _decode_count(path):
    """Frame count via a decode-counted ffprobe pass (slow but exact);
    None when that fails too."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-count_frames", "-show_entries", "stream=nb_read_frames",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        return int((proc.stdout or "").strip())
    except ValueError:
        return None


def probe_clip(path):
    """(width, height, fps, frame_count) via ffprobe; None on failure.

    Phone captures often lack a usable duration or report 0/0 fps
    (notably WebM/VFR) — the probe then falls back to the container's
    frame count, and finally to a decode-counted pass, instead of
    silently killing highlights and redaction."""
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height,avg_frame_rate,r_frame_rate,"
             "duration,nb_frames",
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
    except (KeyError, ValueError):
        return None
    fps = _fps(info.get("avg_frame_rate", "")) \
        or _fps(info.get("r_frame_rate", "")) or 30.0
    count = None
    try:
        dur = float(info.get("duration", ""))
        if dur > 0:
            count = int(dur * fps)
    except (TypeError, ValueError):
        pass
    if not count or count <= 0:
        try:
            count = int(info.get("nb_frames", ""))
        except (TypeError, ValueError):
            count = None
    if not count or count <= 0:
        count = _decode_count(path)
    if width <= 0 or height <= 0 or fps <= 0 or not count or count <= 0:
        return None
    return (width, height, fps, count)


def render_overlays(parsed_frames, width, height, count, outdir,
                    painter=None):
    """Write overlay_%05d.png for every clip frame. painter(width,
    height, boxes) defaults to the spotlight. Returns the count."""
    paint = painter or spotlight_frame
    os.makedirs(outdir, exist_ok=True)
    for index in range(count):
        pixels = paint(width, height, boxes_for_frame(parsed_frames, index))
        write_png_rgba(os.path.join(outdir, "overlay_%05d.png" % index),
                       width, height, pixels)
    return count


def mux_highlight(clip_path, overlay_pattern, fps, out_path):
    """Overlay the PNG stream over the clip; True on success. The
    output is yuv420p (the overlay filter can otherwise emit
    unplayable pixel formats), and a failed mux leaves no partial
    file behind to be mistaken for a highlight."""
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", clip_path,
             "-framerate", "%.3f" % fps, "-i", overlay_pattern,
             "-filter_complex", "[0:v][1:v]overlay=0:0:shortest=1",
             "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
             out_path],
            capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        _drop(out_path)
        return False
    if proc.returncode != 0 or not os.path.exists(out_path):
        _drop(out_path)
        return False
    return True


def _drop(path):
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def save_tracks(path, concept, parsed_frames):
    with open(path, "w") as fh:
        json.dump({"concept": concept, "frames": parsed_frames}, fh)


def highlight_clip(clip_path, parsed_frames, out_path, workdir,
                   painter=None):
    """Full pass: probe, render overlays, mux. True on success."""
    probed = probe_clip(clip_path)
    if probed is None or not parsed_frames:
        return False
    width, height, fps, count = probed
    ovdir = os.path.join(workdir, "ov")
    render_overlays(parsed_frames, width, height, count, ovdir,
                    painter=painter)
    return mux_highlight(clip_path, os.path.join(ovdir, "overlay_%05d.png"),
                         fps, out_path)


def redact_clip(clip_path, parsed_faces, out_path, workdir):
    """Share-safe pass: opaque covers over every tracked face."""
    return highlight_clip(clip_path, parsed_faces, out_path, workdir,
                          painter=solid_frame)
