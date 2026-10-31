"""
RETIRED (Oct 27, 2026): part of the cut apprentice design. Not called
by pipeline/run_pipeline.py or anything in the core flow; kept in the
tree as a retired experiment.

SAM overlay — the Apprentice's misreading, drawn on the mentor's photo.

This is Step 2's primary visual (see README's design rules): SAM segments
the region of the mentor's real photo where the action happens, the
region is highlighted, and the Apprentice's own sentence is pinned to it.

How SAM is used here:
- Local engine for development: Meta's segment-anything, ViT-B checkpoint
  (pipeline/models/sam_vit_b_01ec64.pth — download per docs/PIPELINE.md;
  too large for git). A point prompt says "the action is here": the
  mentor (or the pipeline's hero-frame heuristic) supplies it as
  normalized --point X,Y. SAM returns the mask for the object under the
  point; we take its best-scoring mask.
- Production swap: SAM 3.1 via the Meta Model API accepts richer prompts
  (including text), but the contract of this module stays identical —
  image + point/phrase in, highlighted overlay + mask stats out. See
  docs/PIPELINE.md.

Usage:
  sam_overlay.py --image PHOTO --point 0.52,0.44 \
      --label "I'd cut straight down, at 90 degrees." --out overlay.png
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

MODELS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
CHECKPOINT = os.path.join(MODELS_DIR, "sam_vit_b_01ec64.pth")
HIGHLIGHT = (232, 161, 58)  # apprentice amber, matches the app palette


def load_predictor():
    if not os.path.exists(CHECKPOINT):
        sys.exit("SAM checkpoint missing: " + CHECKPOINT +
                 "\nDownload it per docs/PIPELINE.md (375 MB, not in git).")
    try:
        import torch  # noqa: F401  (backend for segment-anything)
        from segment_anything import SamPredictor, sam_model_registry
    except ImportError:
        sys.exit("sam_overlay needs the retired requirements "
                 "(torch + segment-anything, ~2 GB):\n"
                 "  uv pip install -r requirements-retired.txt")
    sam = sam_model_registry["vit_b"](checkpoint=CHECKPOINT)
    sam.to(device="cpu")
    return SamPredictor(sam)


def segment(predictor, image_rgb, point_xy):
    predictor.set_image(image_rgb)
    masks, scores, _ = predictor.predict(
        point_coords=np.array([point_xy]), point_labels=np.array([1]),
        multimask_output=True)
    best = int(np.argmax(scores))
    return masks[best], float(scores[best])


def render_overlay(image, mask, label, out_path):
    base = image.convert("RGB")
    tint = Image.new("RGB", base.size, HIGHLIGHT)
    alpha = Image.fromarray((mask * 110).astype(np.uint8))
    base = Image.composite(tint, base, alpha)
    draw = ImageDraw.Draw(base)
    ys, xs = np.nonzero(mask)
    if len(xs):
        cx, cy = float(xs.mean()), float(ys.mean())
        top = int(ys.min())
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                max(16, base.width // 42))
        except OSError:
            font = ImageFont.load_default()
        # Wrap the label to at most ~34 characters per line.
        words, lines, cur = label.split(), [], ""
        for w in words:
            if len(cur) + len(w) + 1 > 34:
                lines.append(cur); cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            lines.append(cur)
        text = "APPRENTICE: " + "\n".join(lines)
        pad = 12
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        lx = min(max(pad, cx - tw / 2), base.width - tw - 2 * pad)
        ly = max(pad, top - th - 3 * pad)
        draw.line([(cx, cy), (cx, ly + th + pad)], fill=HIGHLIGHT, width=4)
        draw.rounded_rectangle([lx - pad, ly - pad, lx + tw + pad, ly + th + pad],
                               radius=10, fill=(23, 19, 14))
        draw.multiline_text((lx, ly), text, font=font, fill=(245, 234, 214))
    base.save(out_path)
    return base.size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--point", default="0.5,0.45",
                    help="normalized X,Y of the action (default 0.5,0.45)")
    ap.add_argument("--label", required=True,
                    help="the Apprentice's own sentence to pin to the region")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    parts = args.point.split(",")
    if len(parts) != 2:
        sys.exit("--point must be X,Y (normalized, 0..1)")
    try:
        px, py = (float(v) for v in parts)
    except ValueError:
        sys.exit("--point must be numeric X,Y")
    if not (0.0 <= px <= 1.0 and 0.0 <= py <= 1.0):
        sys.exit("--point coordinates must be within 0..1")

    # EXIF orientation first: portrait phone photos store rotated
    # pixels, and the point must map onto the image as displayed.
    image = ImageOps.exif_transpose(Image.open(args.image)).convert("RGB")
    rgb = np.array(image)
    point = (px * rgb.shape[1], py * rgb.shape[0])
    mask, score = segment(load_predictor(), rgb, point)
    if mask.mean() == 0 or score < 0.5:
        # A fake overlay (untinted photo presented as the Apprentice's
        # try) is worse than no overlay (Wonder review).
        sys.exit(f"SAM found no confident region at that point "
                 f"(score={score:.2f}, mask={float(mask.mean()):.4f}) — "
                 "no overlay written; try a point on the object itself.")
    size = render_overlay(image, mask, args.label, args.out)
    stats = {"image": args.image, "point_normalized": [px, py],
             "mask_score": round(score, 3),
             "mask_fraction": round(float(mask.mean()), 4),
             "overlay": args.out, "size": size}
    with open(os.path.splitext(args.out)[0] + ".json", "w") as fh:
        json.dump(stats, fh, indent=1)
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
