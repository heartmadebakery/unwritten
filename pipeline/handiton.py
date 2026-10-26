"""Hand-it-on page generator (Step 4).

Renders the shareable page as one self-contained HTML file: the card,
the Tricks (the teacher's corrections), the overlay of the Apprentice's
misreading, and the student's attempt beside the teacher's original.
Images are referenced by relative path (they sit beside the page in the
work dir); nothing is uploaded anywhere by this module.

Usage: handiton.py --work DIR --title "Mom's Bread" [--tricks TRICKS.md]
Reads from the work dir: card.md, overlay.png (optional), frames/
(teacher original = hero frame), attempt photos from the manifest.
Writes <work>/page.html.
"""
import argparse
import html
import json
import os


def md_list(md_text):
    items = []
    for line in md_text.splitlines():
        line = line.strip()
        if line and (line[0].isdigit() or line.startswith("- ")):
            items.append(line.split(".", 1)[-1].strip() if line[0].isdigit()
                         else line[2:].strip())
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--title", default="Unwritten Craft")
    ap.add_argument("--tricks", default="")
    args = ap.parse_args()
    work = args.work

    with open(os.path.join(work, "card.md")) as fh:
        card_md = fh.read()
    steps = md_list(card_md)
    tricks = []
    if args.tricks and os.path.exists(args.tricks):
        with open(args.tricks) as fh:
            tricks = md_list(fh.read())

    overlay = "overlay.png" if os.path.exists(os.path.join(work, "overlay.png")) else ""
    manifest_path = os.path.join(work, "manifest.json")
    attempt = ""
    if os.path.exists(manifest_path):
        with open(manifest_path) as fh:
            manifest = json.load(fh)
        if manifest.get("photos"):
            attempt = os.path.basename(manifest["photos"][-1])

    steps_html = "".join(f"<li>{html.escape(s)}</li>" for s in steps)
    tricks_html = "".join(f"<li>{html.escape(t)}</li>" for t in tricks) or \
        "<li><em>Corrections land here after the teacher reacts.</em></li>"
    overlay_html = f'<img src="{overlay}" alt="The Apprentice\'s misreading">' if overlay else ""
    attempt_html = f'<img src="{attempt}" alt="The student\'s attempt">' if attempt else ""

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
<h2>The Apprentice's try</h2>{overlay_html}
<h2>The Tricks — what was never written down</h2><ul>{tricks_html}</ul>
<h2>Handed on</h2><div class="duo">{overlay_html}{attempt_html}</div>
<footer>Unwritten Craft — teach what must not disappear.</footer>
</body></html>"""
    out = os.path.join(work, "page.html")
    with open(out, "w") as fh:
        fh.write(page)
    print(f"page -> {out}")


if __name__ == "__main__":
    main()
