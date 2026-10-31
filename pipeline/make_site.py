"""Build the Unwritten website: one hub, two sections.

- App: the Unwritten Craft web app, copied in so it opens from the hub.
- Sessions: every pipeline work dir under a root becomes an entry —
  its write-up rendered to a page (via make_page), with poster,
  chapters, corrections, and clips carried along.

Fully automatic: any directory containing writeup.md is a session,
newest first. Nothing here is part of the core pipeline; it only
presents finished runs.

Usage: make_site.py <work_root> <site_dir> [--recorder DIR]
Default recorder source is app/recorder/dist when built, else
app/recorder/ (unstamped: Cloud upload then needs a pasted token).
"""
import argparse
import datetime
import html
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import make_page

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def esc(text):
    return html.escape(text, quote=True)


def find_sessions(work_root):
    """Work dirs (containing writeup.md) directly under root, newest
    first by directory mtime. Returns [(dirname, path)]."""
    found = []
    for name in sorted(os.listdir(work_root)):
        path = os.path.join(work_root, name)
        if os.path.isdir(path) and os.path.isfile(
                os.path.join(path, "writeup.md")):
            found.append((name, path))
    found.sort(key=lambda item: os.path.getmtime(item[1]), reverse=True)
    return found


def session_meta(path):
    """(title, date, blurb) from a work dir. Title is the write-up's
    first heading, date the lesson stamp (else the dir mtime), blurb
    the first paragraph after the title."""
    title, blurb = "", ""
    with open(os.path.join(path, "writeup.md")) as fh:
        lines = [line.rstrip("\n") for line in fh]
    for i, line in enumerate(lines):
        if line.startswith("# "):
            title = line[2:].strip()
            for rest in lines[i + 1:]:
                if rest.strip() and not rest.startswith("#"):
                    blurb = rest.strip()
                    break
            break
    stamp = ""
    for probe in (os.path.join(path, "manifest.json"),
                  os.path.join(path, "transcript.txt")):
        try:
            with open(probe) as fh:
                text = fh.read(500)
        except OSError:
            continue
        m = re.search(r"unwritten_lesson_(\d{4})(\d{2})(\d{2})-(\d{6})",
                      text)
        if m:
            stamp = "%s %d, %s" % (MONTHS[int(m.group(2)) - 1],
                                   int(m.group(3)), m.group(1))
            break
    if not stamp:
        stamp = datetime.datetime.fromtimestamp(
            os.path.getmtime(path)).strftime("%b %d, %Y")
    return (title or os.path.basename(path), stamp, blurb)


def render_hub(sessions):
    """sessions: [(dirname, title, date, blurb, has_poster)]."""
    cards = []
    for dirname, title, date, blurb, has_poster in sessions:
        img = (f'<img src="sessions/{esc(dirname)}/poster.jpg" alt="">'
               if has_poster else "")
        cards.append(
            f'<a class="card" href="sessions/{esc(dirname)}/page.html">'
            f"{img}<div><h3>{esc(title)}</h3>"
            f'<p class="date">{esc(date)}</p>'
            f"<p>{esc(blurb)}</p></div></a>")
    grid = ("\n".join(cards) if cards else
            '<p class="empty">No sessions yet — run the pipeline and '
            "rebuild this site.</p>")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Unwritten Craft</title>
<style>
  *{{box-sizing:border-box}}
  html,body{{margin:0;padding:0;background:#17130E;color:#F5EAD6;
    font-family:system-ui,-apple-system,"Segoe UI",sans-serif}}
  #app{{max-width:720px;margin:0 auto;padding:28px 16px 48px}}
  header{{text-align:center;margin-bottom:8px}}
  h1{{font-size:28px;font-weight:normal;margin:0 0 4px}}
  .sub{{color:#B8A888;font-size:16px;margin:0 0 20px}}
  h2{{font-weight:normal;color:#B8A888;font-size:17px;margin:22px 0 10px}}
  .card{{display:flex;gap:14px;background:#241C12;border-radius:8px;
    padding:14px;margin:10px 0;color:#F5EAD6;text-decoration:none}}
  .card img{{width:120px;height:68px;object-fit:cover;border-radius:4px;
    flex:none}}
  .card h3{{font-weight:normal;font-size:17px;margin:0 0 4px}}
  .card .date,.empty{{color:#B8A888;font-size:14px;margin:0 0 6px}}
  .card p{{font-size:14px;line-height:1.5;margin:0;color:#F5EAD6}}
  .card p.date{{color:#B8A888}}
</style>
</head>
<body>
<div id="app">
  <header>
    <h1>Unwritten Craft</h1>
    <p class="sub">Film a lesson. Keep the corrections.</p>
  </header>
  <h2>App</h2>
  <a class="card" href="recorder/"><div><h3>Open Unwritten Craft</h3>
  <p>Record or upload a lesson on this device. Sessions save locally
  first, then upload to Cloud when it is on.</p></div></a>
  <h2>Sessions</h2>
  {grid}
</div>
</body>
</html>
"""


def build_session(src, dest, title):
    """Copy a work dir and render its page. Returns True on success."""
    try:
        if os.path.isdir(dest):
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        argv = sys.argv
        sys.argv = ["make_page", "--work", dest, "--title", title]
        try:
            make_page.main()
        finally:
            sys.argv = argv
        return os.path.exists(os.path.join(dest, "page.html"))
    except Exception as exc:
        print(f"  [site] session {os.path.basename(src)}: {exc} — skipped")
        return False


def default_recorder():
    dist = os.path.join(ROOT, "app", "recorder", "dist")
    if os.path.isdir(dist):
        return dist
    return os.path.join(ROOT, "app", "recorder")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_root")
    ap.add_argument("site_dir")
    ap.add_argument("--recorder", default=None)
    args = ap.parse_args()
    rec_src = args.recorder or default_recorder()
    if not os.path.isdir(rec_src):
        print(f"recorder source not found: {rec_src}")
        sys.exit(2)
    os.makedirs(args.site_dir, exist_ok=True)
    rec_dest = os.path.join(args.site_dir, "recorder")
    if os.path.isdir(rec_dest):
        shutil.rmtree(rec_dest)
    shutil.copytree(rec_src, rec_dest)
    print(f"[site] recorder <- {rec_src}")
    if os.path.basename(rec_src) != "dist":
        print("  [site] unstamped copy: Cloud upload needs a pasted token")
    entries = []
    for dirname, path in find_sessions(args.work_root):
        title, date, blurb = session_meta(path)
        dest = os.path.join(args.site_dir, "sessions", dirname)
        if build_session(path, dest, title):
            entries.append(
                (dirname, title, date, blurb,
                 os.path.exists(os.path.join(dest, "poster.jpg"))))
    with open(os.path.join(args.site_dir, "index.html"), "w") as fh:
        fh.write(render_hub(entries))
    print(f"[site] {len(entries)} session(s) -> {args.site_dir}/index.html")


if __name__ == "__main__":
    main()
