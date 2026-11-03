"""Publish a finished pipeline run to the hub store.

Reads a work dir (writeup.md, corrections.json, chapters.json) plus the
cloud video id, and POSTs it to the signer's /hub/publish route, where
the apps' in-app hub reads it back. Video bytes stay in Stream —
only playback URLs and the text artifacts travel here.

Usage:
  CLOUD_LIBRARY_ID=.. CLOUD_LIBRARY_KEY=.. CLOUD_CDN_HOSTNAME=.. \\
  HUB_SIGNER_URL=https://signer.example.com HUB_SIGNER_TOKEN=.. \\
  python3 pipeline/publish.py --work <work_dir> [--state cloud_state.json]
                              [--guid GUID] [--signer URL] [--token T]
  python3 pipeline/publish.py --sync-ignored [--state cloud_state.json]
                              [--signer URL] [--token T]

--guid overrides the state lookup (the state maps each cloud video id
to the work dir the pipeline ran in). Playback URLs come from the
vendor video object when the Cloud credentials are present, else the
HLS pattern is used blind and mp4 is left empty. --sync-ignored
converges the hub's ignored markers on the state instead of
publishing: every ignored video upserted, stale markers removed.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cloud_fetch  # noqa: E402
from make_site import session_meta  # noqa: E402


def load_state(path):
    try:
        with open(path) as fh:
            obj = json.load(fh)
    except (OSError, ValueError) as exc:
        raise SystemExit("cannot read state %s: %s" % (path, exc))
    return obj if isinstance(obj, dict) else {}


def resolve_guid(state, work, override):
    if override:
        return override
    want = os.path.abspath(work)
    for guid, entry in state.items():
        if not isinstance(entry, dict):
            continue
        if os.path.abspath(entry.get("workDir", "")) == want:
            return guid
    raise SystemExit("no cloud video maps to %s in %s "
                     "(pass --guid)" % (work, "state"))


def read_json(path, default):
    try:
        with open(path) as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        return default
    return obj


def media_duration(path):
    if not path or not os.path.isfile(path):
        return 0
    try:
        import subprocess
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return int(round(float((proc.stdout or "").strip())))
    except Exception:
        return 0


def unique_title_sync(proposed, chapters, lesson_date, signer, token, video_id):
    """Ensure new title at first creation stays unique via chapter summary."""
    try:
        from title_utils import unique_title
    except ImportError:
        return proposed
    # fetch existing titles unless this is an update of same videoId
    try:
        status, body = get_json(signer.rstrip("/") + "/hub/sessions", token)
        if status >= 200 and status < 300:
            import json as _json
            rows = _json.loads(body)
            existing = [r.get("title","") for r in rows if isinstance(r, dict) and r.get("videoId") != video_id]
            return unique_title(proposed, chapters, lesson_date, existing)
    except Exception:
        pass
    return proposed


def playback_urls(guid):
    """(hls, mp4) for the video, vendor-confirmed when possible."""
    try:
        cfg = cloud_fetch.load_config()
    except SystemExit:
        return "", ""
    hls = cloud_fetch.playlist_url(cfg["cdn"], guid)
    try:
        req = urllib.request.Request(
            "https://video.bunnycdn.com/library/%s/videos/%s"
            % (cfg["library_id"], guid),
            headers={"AccessKey": cfg["api_key"],
                     "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            vid = json.load(resp)
        cands = cloud_fetch.mp4_candidates(
            cfg["cdn"], guid, vid.get("availableResolutions"))
        return hls, (cands[0] if cands else "")
    except Exception:
        return hls, ""


def post_json(url, payload, token):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json",
                 "X-Signer-Token": token,
                 "User-Agent": "UnwrittenCraft/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise SystemExit("hub publish failed: %s" % exc)


def get_json(url, token):
    req = urllib.request.Request(
        url, headers={"X-Signer-Token": token,
                      "Accept": "application/json",
                      "User-Agent": "UnwrittenCraft/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise SystemExit("hub request failed: %s" % exc)


def delete_url(url, token):
    req = urllib.request.Request(
        url, headers={"X-Signer-Token": token,
                      "User-Agent": "UnwrittenCraft/1.0"},
        method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        raise SystemExit("hub request failed: %s" % exc)


def sync_ignored(state_path, signer, token):
    """Converge the hub's ignored markers on the cloud state: every
    locally-ignored video upserted, every marker for a video no
    longer ignored removed. Missing state is a quiet no-op (fresh
    machine); corrupt state fails loudly."""
    if not os.path.exists(state_path):
        print("[hub] no cloud state yet — nothing to sync")
        return 0
    state = load_state(state_path)
    base = signer.rstrip("/") + "/hub/ignored"
    ignored = sorted(guid for guid, entry in state.items()
                     if isinstance(entry, dict)
                     and entry.get("result") == "ignored")
    for guid in ignored:
        entry = state[guid]
        status, body = post_json(
            base, {"videoId": guid, "title": entry.get("title", ""),
                   "reason": entry.get("reason", "")}, token)
        if status < 200 or status >= 300:
            raise SystemExit("hub ignore refused for %s (%s): %s"
                             % (guid, status, body))
        try:
            ack = json.loads(body)
        except ValueError:
            ack = None
        # A stale worker answers 200 with a mint payload (unknown
        # paths fall into the video trio) — a 200 with the wrong
        # shape is a refusal, never a stored marker.
        if not isinstance(ack, dict) or ack.get("ignored") != guid:
            raise SystemExit("hub ignore for %s answered 200 without "
                             "a marker (stale worker? redeploy): %.80s"
                             % (guid, body.strip()))
    status, body = get_json(base, token)
    if status < 200 or status >= 300:
        raise SystemExit("hub ignored list refused (%s): %s"
                         % (status, body))
    try:
        remote = json.loads(body)
    except ValueError:
        raise SystemExit("hub ignored list answered not JSON: %.80s"
                         % body.strip())
    if not isinstance(remote, list):
        raise SystemExit("hub ignored list answered not a list: %.80s"
                         % body.strip())
    remote_ids = set(entry.get("videoId", "")
                     for entry in remote
                     if isinstance(entry, dict))
    removed = 0
    for guid in sorted(remote_ids - set(ignored)):
        status, body = delete_url("%s/%s" % (base, guid), token)
        if status < 200 or status >= 300:
            raise SystemExit("hub un-ignore refused for %s (%s): %s"
                             % (guid, status, body))
        removed += 1
    print("[hub] %d ignored video(s) synced, %d marker(s) removed."
          % (len(ignored), removed))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="",
                    help="finished work dir to publish "
                         "(not needed with --sync-ignored)")
    ap.add_argument("--state", default="cloud_state.json")
    ap.add_argument("--guid", default="")
    ap.add_argument("--signer", default=os.environ.get("HUB_SIGNER_URL", ""))
    ap.add_argument("--token", default=os.environ.get("HUB_SIGNER_TOKEN", ""))
    ap.add_argument("--sync-ignored", action="store_true",
                    help="sync the cloud state's ignored videos to the "
                         "hub instead of publishing one work dir")
    args = ap.parse_args(argv)

    if not args.signer or not args.token:
        raise SystemExit("hub signer URL and token required "
                         "(--signer/--token or HUB_SIGNER_URL/HUB_SIGNER_TOKEN)")
    if args.sync_ignored:
        return sync_ignored(args.state, args.signer, args.token)
    if not args.work:
        ap.error("--work is required without --sync-ignored")

    work = os.path.abspath(args.work)
    md_path = os.path.join(work, "writeup.md")
    if not os.path.isfile(md_path):
        raise SystemExit("no writeup.md in %s — nothing to publish" % work)
    state = load_state(args.state)
    guid = resolve_guid(state, work, args.guid.strip())
    with open(md_path) as fh:
        writeup = fh.read()
    title, date, _ = session_meta(work)
    corrections = read_json(os.path.join(work, "corrections.json"), [])
    chapters = read_json(os.path.join(work, "chapters.json"), [])
    hls, mp4 = playback_urls(guid)
    # unique at first creation via chapter summarization
    title = unique_title_sync(title, chapters if isinstance(chapters, list) else [], date, args.signer, args.token, guid)
    # duration from lesson media (cloud_state lesson path or local probe)
    dur = 0
    try:
        st = load_state(args.state) if os.path.exists(args.state) else {}
        ent = st.get(guid, {}) if isinstance(st, dict) else {}
        lesson_path = ent.get("lesson", "") if isinstance(ent, dict) else ""
        dur = media_duration(lesson_path)
        if not dur:
            # fallback: probe any download in sibling cloud_downloads
            dl = os.path.join(os.path.dirname(os.path.abspath(args.state)), "cloud_downloads")
            cand = os.path.join(dl, os.path.basename(lesson_path)) if lesson_path else ""
            if cand and os.path.isfile(cand):
                dur = media_duration(cand)
    except Exception:
        pass
    payload = {
        "videoId": guid,
        "title": title,
        "lessonDate": date,
        "durationSeconds": dur,
        "hlsUrl": hls,
        "mp4Url": mp4,
        "writeupMd": writeup,
        "corrections": corrections if isinstance(corrections, list) else [],
        "chapters": chapters if isinstance(chapters, list) else [],
        "glossary": {},
    }
    status, body = post_json(args.signer.rstrip("/") + "/hub/publish",
                             payload, args.token)
    if status < 200 or status >= 300:
        raise SystemExit("hub publish refused (%s): %s" % (status, body))
    print("[hub] published %s (%s)" % (guid, title))
    return 0


if __name__ == "__main__":
    main()
