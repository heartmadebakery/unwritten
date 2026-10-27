"""Hand-it-on page generator (Step 4).

Renders the shareable page as one HTML file beside its images in the
work dir: the card's steps, the card's wisdom section, the Knack (the
teacher's corrections — headed as a DRAFT until she confirms them),
the overlay of the Apprentice's misreading, and the student's attempt
beside the teacher's original (hero). run_pipeline copies the images
into the work dir under canonical names (hero.*, attempt_photo.*,
overlay.png); this module only references files that exist.

Usage: handiton.py --work DIR --title "Mom's Bread" [--techniques TECHNIQUES.md]
Writes <work>/page.html.
"""
import argparse
import html
import os
import re


def card_sections(md_text):
    """Split a card into (steps, wisdom bullets).

    Steps are the numbered lines before the first '## ' heading. The
    wisdom section's bullets are NOT steps (Wonder review).
    """
    steps, wisdom, in_wisdom = [], [], False
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            in_wisdom = "know" in s.lower()
            continue
        if in_wisdom:
            if s.startswith("- "):
                wisdom.append(s[2:].strip())
        elif re.match(r"^\d+[.)]\s+", s):
            steps.append(re.sub(r"^\d+[.)]\s+", "", s))
    return steps, wisdom


def bullet_list(md_text):
    """The text of every '- ' bullet line in a markdown file."""
    return [ln.strip()[2:].strip() for ln in md_text.splitlines()
            if ln.strip().startswith("- ")]


def find_local(work, stem):
    """Image filename in `work` with this stem (hero.*, ...), or ''."""
    for entry in sorted(os.listdir(work)):
        if os.path.splitext(entry)[0] == stem and \
                os.path.splitext(entry)[1].lower() in (".jpg", ".jpeg", ".png", ".webp"):
            return entry
    return ""


def main():
    ap = argparse.ArgumentParser(
        description="Render the hand-it-on page from a pipeline work dir.")
    ap.add_argument("--work", required=True, help="the pipeline work dir")
    ap.add_argument("--title", default="Unwritten Craft",
                    help="page title (default 'Unwritten Craft')")
    ap.add_argument("--techniques", default="",
                    help="techniques draft markdown (the Knack, unconfirmed)")
    args = ap.parse_args()
    work = args.work

    with open(os.path.join(work, "card.md")) as fh:
        steps, wisdom = card_sections(fh.read())
    techniques, knacks_draft = [], False
    if args.techniques and os.path.exists(args.techniques):
        with open(args.techniques) as fh:
            techniques_text = fh.read()
        techniques = bullet_list(techniques_text)
        knacks_draft = "DRAFT" in techniques_text[:200]

    overlay = "overlay.png" if os.path.exists(os.path.join(work, "overlay.png")) else ""
    hero = find_local(work, "hero")
    attempt = find_local(work, "attempt_photo")

    def img(name, alt):
        return (f'<img src="{html.escape(name, quote=True)}" '
                f'alt="{html.escape(alt, quote=True)}">') if name else ""

    steps_html = "".join(f"<li>{html.escape(s)}</li>" for s in steps)
    wisdom_html = "".join(f"<li>{html.escape(w)}</li>" for w in wisdom)
    knacks_html = "".join(f"<li>{html.escape(t)}</li>" for t in techniques) or \
        "<li><em>Corrections land here after the teacher reacts.</em></li>"
    knacks_title = "The Knack — what was never written down" + \
        (" (draft — the teacher confirms these)" if knacks_draft else "")
    overlay_html = img(overlay, "The Apprentice's misreading")
    wisdom_block = f"<h2>What the teacher knows</h2><ul>{wisdom_html}</ul>" if wisdom else ""

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(args.title)} — Unwritten Craft</title>
<style>body{{background:#17130e;color:#f5ead6;font-family:Georgia,serif;
max-width:760px;margin:0 auto;padding:28px 18px;line-height:1.6}}
h1{{font-weight:normal}} h2{{color:#e8a13a;font-weight:normal;margin-top:34px}}
img{{max-width:100%;border-radius:10px}} .duo{{display:grid;
grid-template-columns:1fr 1fr;gap:12px}} li{{margin:7px 0}}
footer{{color:#b8a888;margin-top:40px;font-style:italic}}</style></head>
<body>
<h1>{html.escape(args.title)}</h1>
<p><em>Taught once, written as it was said, corrected once — handed on.</em></p>
<h2>The card</h2><ol>{steps_html}</ol>
{wisdom_block}
<h2>The Apprentice's try</h2>{overlay_html}
<h2>{html.escape(knacks_title)}</h2><ul>{knacks_html}</ul>
<h2>Handed on</h2><div class="duo">{img(hero, "The teacher's original")}{img(attempt, "The student's attempt")}</div>
<footer>Unwritten Craft — teach what must not disappear.</footer>
</body></html>"""
    out = os.path.join(work, "page.html")
    with open(out, "w") as fh:
        fh.write(page)
    print(f"page -> {out}")


if __name__ == "__main__":
    main()
