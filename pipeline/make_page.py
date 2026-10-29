"""OPTIONAL page generator — not part of the core pipeline.

The core is three things: the lesson video, the correction clips, the
write-up (pipeline/run_pipeline.py). This module assembles those into a
single shareable page — a guide or manual for someone who wasn't in the
room — for when there is a recipient for it. Nothing in the core
depends on it, and the core pipeline never calls it.

It consumes only core outputs: writeup.md (the mentor's steps + the
mentor's judgment) and corrections.json (the techniques, each with
the mentor's exact words and,
where run_pipeline cut them, a clip file under clips/).

Usage: make_page.py --work DIR --title "Mom's Bread"
Reads <work>/writeup.md and <work>/corrections.json; writes
<work>/page.html.
"""
import argparse
import html
import json
import os
import re


def parse_writeup(md_text):
    """Split a write-up into (steps, wisdom bullets). Steps are numbered
    lines before the first '## ' heading — the wisdom section's bullets
    are NOT steps."""
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--title", default="Unwritten Craft")
    args = ap.parse_args()
    work = args.work

    with open(os.path.join(work, "writeup.md")) as fh:
        steps, wisdom = parse_writeup(fh.read())
    hits = []
    corrections_path = os.path.join(work, "corrections.json")
    if os.path.exists(corrections_path):
        with open(corrections_path) as fh:
            hits = json.load(fh)

    def esc(s):
        return html.escape(str(s), quote=True)

    steps_html = "".join(f"<li>{esc(s)}</li>" for s in steps)
    wisdom_html = "".join(f"<li>{esc(w)}</li>" for w in wisdom)
    wisdom_block = (f"<h2>What the mentor knows</h2><ul>{wisdom_html}</ul>"
                    if wisdom else "")
    poster_block = ('<p><img src="poster.jpg" alt="Lesson poster"></p>'
                    if os.path.exists(os.path.join(work, "poster.jpg"))
                    else "")
    chapters_path = os.path.join(work, "chapters.json")
    chapters_block = ""
    if os.path.exists(chapters_path):
        try:
            chapters = json.load(open(chapters_path))
            rows = "".join(
                f"<li><b>{esc(c.get('start', ''))}</b> "
                f"{esc(c.get('label', ''))}</li>" for c in chapters)
            chapters_block = (f"<h2>Chapters</h2><ul>{rows}</ul>"
                              if rows else "")
        except (OSError, ValueError):
            pass

    technique_blocks = []
    for i, hit in enumerate(hits, 1):
        clip_name = f"correction-{i:02d}.mp4"
        clip = (f'<p><video controls src="clips/{clip_name}"></video></p>'
                if os.path.exists(os.path.join(work, "clips", clip_name))
                else "")
        technique_blocks.append(
            f"<h3>{esc(hit.get('start', ''))} — {esc(hit.get('correcting', ''))}</h3>"
            f"<blockquote>{esc(hit.get('quote', ''))}</blockquote>{clip}")
    knacks_html = "".join(technique_blocks) or \
        "<p><em>No corrections captured in this lesson.</em></p>"

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(args.title)} — Unwritten Craft</title>
<style>body{{background:#17130e;color:#f5ead6;font-family:Georgia,serif;
max-width:760px;margin:0 auto;padding:28px 18px;line-height:1.6}}
h1{{font-weight:normal}} h2{{color:#e8a13a;font-weight:normal;margin-top:34px}}
video{{max-width:100%;border-radius:10px}} li{{margin:7px 0}}
img{{max-width:100%;border-radius:10px}}
blockquote{{border-left:3px solid #e8a13a;margin-left:0;padding-left:14px;
font-style:italic}}
footer{{color:#b8a888;margin-top:40px;font-style:italic}}</style></head>
<body>
<h1>{esc(args.title)}</h1>
<p><em>Film a lesson. Keep the corrections.</em></p>
{poster_block}
{chapters_block}
<h2>The write-up</h2><ol>{steps_html}</ol>
{wisdom_block}
<h2>The Knack — the corrections</h2>{knacks_html}
<footer>Unwritten Craft — the mentor approved every clip on this page
before it was shared.</footer>
</body></html>"""
    out = os.path.join(work, "page.html")
    with open(out, "w") as fh:
        fh.write(page)
    print(f"page -> {out}")


if __name__ == "__main__":
    main()
