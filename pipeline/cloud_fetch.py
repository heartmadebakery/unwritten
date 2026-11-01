#!/usr/bin/env python3
"""Fetch finished Cloud lessons so the pipeline can process them.

The apps upload a copy of every lesson to Cloud (see
app/cloud-signer/); this module pulls the finished ones back down with
the library credentials, which stay on the pipeline machine only:

  CLOUD_LIBRARY_ID   Stream library ID (same value as wrangler.toml)
  CLOUD_LIBRARY_KEY  library AccessKey (Stream dashboard -> library -> API)
  CLOUD_CDN_HOSTNAME pull-zone hostname, e.g. vz-1234abcd.b-cdn.net
                     (Stream dashboard -> library -> API page)

Only videos with status 4 (finished/playable) are candidates,
and a JSON state file remembers every video already handled so reruns
only pick up new lessons. Downloads prefer the highest MP4 rendition
and fall back to remuxing the HLS playlist with ffmpeg (already a
pipeline dependency). Stdlib only, except ffmpeg for the fallback.
"""
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://video.bunnycdn.com"
PER_PAGE = 100
FINISHED = 4  # finished/playable in the library API
PUT_TIMEOUT = 3600
POLL_INTERVAL = 30
POLL_TIMEOUT = 3600


class DownloadError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def load_config(env=None):
    """Read Cloud library credentials from the environment. Exits loudly
    if any are missing so a --cloud run never silently processes nothing.

    When CLOUD_PROXY_URL is set (e.g. the signer Worker URL), listing
    goes through the proxy and CLOUD_LIBRARY_KEY is not required — the
    Worker holds the key."""
    env = os.environ if env is None else env
    library_id = (env.get("CLOUD_LIBRARY_ID") or "").strip()
    api_key = (env.get("CLOUD_LIBRARY_KEY") or "").strip()
    cdn = (env.get("CLOUD_CDN_HOSTNAME") or "").strip().rstrip("/")
    proxy = (env.get("CLOUD_PROXY_URL") or "").strip().rstrip("/")
    missing = [name for name, val in
               (("CLOUD_LIBRARY_ID", library_id),
                ("CLOUD_CDN_HOSTNAME", cdn)) if not val]
    if not proxy:
        if not api_key:
            missing.append("CLOUD_LIBRARY_KEY")
        if missing:
            raise SystemExit("Missing %s — export them to fetch cloud videos."
                             % ", ".join(missing))
    elif missing:
        raise SystemExit("Missing %s — export them to fetch cloud videos."
                         % ", ".join(missing))
    return {"library_id": library_id, "api_key": api_key, "cdn": cdn,
            "proxy": proxy}


def http_get_json(url, headers):
    hdrs = {"User-Agent": "UnwrittenCraft/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("Cloud library API %s for %s: %s"
                           % (exc.code, url, body))
    except urllib.error.URLError as exc:
        raise RuntimeError("Cloud library request failed for %s: %s"
                           % (url, exc.reason))
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError("Cloud library request failed for %s: %s"
                           % (url, exc))
    try:
        return json.loads(raw)
    except ValueError:
        raise RuntimeError("Cloud library API answered %s with not JSON "
                           "(edge error page?): %.80s" % (url, raw.strip()))


def http_download(url, dest, referer=""):
    """Stream a URL to dest. 404s raise DownloadError(404); anything
    else missing raises DownloadError with its status. The CDN's
    hotlink protection 403s bare fetches, so callers pass the
    video's player page as referer."""
    headers = {"User-Agent": "UnwrittenCraft/1.0"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, \
                open(dest, "wb") as fh:
            shutil.copyfileobj(resp, fh, length=1024 * 256)
    except urllib.error.HTTPError as exc:
        raise DownloadError(exc.code, "HTTP %s for %s" % (exc.code, url))
    except urllib.error.URLError as exc:
        raise DownloadError(-1, "request failed for %s: %s"
                            % (url, exc.reason))
    if not os.path.exists(dest) or os.path.getsize(dest) == 0:
        raise DownloadError(-1, "empty download for %s" % url)
    return dest


def list_videos(cfg):
    """Every video in the library, oldest first. Raises RuntimeError
    with the library status when the API refuses. When cfg has a
    proxy, listing goes through the signer Worker instead of the
    vendor API directly (so the API key never leaves the Worker)."""
    if cfg.get("proxy"):
        headers = {"Accept": "application/json"}
        # Signer tokens live in app/cloud-signer/tokens.txt; the proxy
        # checks X-Signer-Token when a token pool is configured.
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            pool_path = os.path.join(os.path.dirname(here), "app",
                                     "cloud-signer", "tokens.txt")
            with open(pool_path) as fh:
                tok = fh.readline().strip()
                if tok:
                    headers["X-Signer-Token"] = tok
        except OSError:
            pass
        # Also honor CLOUD_PROXY_TOKEN if set explicitly.
        tok2 = os.environ.get("CLOUD_PROXY_TOKEN", "").strip()
        if tok2:
            headers["X-Signer-Token"] = tok2
        videos = []
        page = 1
        while True:
            url = ("%s/pipeline/videos?page=%d" % (cfg["proxy"], page))
            data = http_get_json(url, headers)
            batch = data.get("items", [])
            videos.extend(batch)
            if len(batch) < PER_PAGE:
                break
            page += 1
        return videos
    videos = []
    page = 1
    while True:
        url = ("%s/library/%s/videos?page=%d&itemsPerPage=%d&orderBy=date"
               % (API, cfg["library_id"], page, PER_PAGE))
        data = http_get_json(url, {"AccessKey": cfg["api_key"],
                                   "Accept": "application/json"})
        batch = data.get("items", [])
        videos.extend(batch)
        if len(batch) < PER_PAGE:
            break
        page += 1
    return videos


def select_ready(videos, state, retry_failed=False):
    """Finished videos this machine has not handled yet. Entries marked
    failed are skipped unless retry_failed is set; done entries never
    come back, and neither do ignored ones — 'ignored' is an operator
    decision that the video is not a lesson, so even --retry-failed
    leaves it set aside. 'downloaded' means fetched but
    pipeline-never-finished, so it reprocesses: run_cloud_mode skips
    the re-download (the lesson is on disk) and runs the pipeline."""
    ready = []
    for vid in videos:
        guid = vid.get("guid", "")
        if not guid or vid.get("status") != FINISHED:
            continue
        entry = state.get(guid, {})
        if entry.get("result") in ("done", "ignored"):
            continue
        if entry.get("result") == "failed" and not retry_failed:
            continue
        ready.append(vid)
    return ready


def sanitize(title):
    """A filename-safe slug of a Cloud video title."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "").strip())
    slug = re.sub(r"_+", "_", slug).strip("._-")[:80]
    return slug or "lesson"


def mp4_candidates(cdn, guid, resolutions):
    """Direct MP4 rendition URLs, highest resolution first."""
    found = []
    for part in str(resolutions or "").split(","):
        num = re.sub(r"\D", "", part)
        if num:
            found.append(int(num))
    return ["https://%s/%s/play_%dp.mp4" % (cdn, guid, res)
            for res in sorted(set(found), reverse=True)]


def playlist_url(cdn, guid):
    return "https://%s/%s/playlist.m3u8" % (cdn, guid)


def remux_hls(url, dest, referer=""):
    """Remux a finished video's HLS playlist to mp4 (used when no MP4
    rendition is downloadable). referer defeats hotlink protection."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH — needed to fetch %s"
                           % url)
    cmd = [ffmpeg, "-y", "-v", "error"]
    if referer:
        cmd += ["-headers", "Referer: %s" % referer]
    cmd += ["-i", url, "-c", "copy", dest]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=900)
    except subprocess.SubprocessError as exc:
        raise RuntimeError("ffmpeg remux timed out for %s: %s" % (url, exc))
    if proc.returncode != 0 or not os.path.exists(dest):
        tail = (proc.stderr or "").strip().splitlines()
        raise RuntimeError("ffmpeg remux failed for %s: %s "
                           "(token-authenticated libraries block direct "
                           "downloads — check Stream -> Security in the "
                           "library dashboard)"
                           % (url, tail[-1] if tail else proc.returncode))
    return dest


def _drop(path):
    """Best-effort removal of a partial download sidecar."""
    try:
        if os.path.exists(path):
            os.unlink(path)
    except OSError:
        pass


def download_video(cfg, vid, dest_dir):
    """Download one finished video; returns the local path. Reuses an
    existing non-empty file so interrupted runs resume cheaply. Bytes
    land in a .part sidecar first — only a complete download is ever
    renamed into place, so a truncated file can never pass as a lesson
    and satisfy the resume check on the next run."""
    guid = vid.get("guid", "")
    dest = os.path.join(dest_dir,
                        "%s__%s.mp4" % (sanitize(vid.get("title")), guid[:8]))
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    part = dest + ".part"
    referer = ("https://player.mediadelivery.net/embed/%s/%s"
               % (cfg["library_id"], guid))
    for url in mp4_candidates(cfg["cdn"], guid, vid.get("availableResolutions")):
        try:
            http_download(url, part, referer)
        except DownloadError as exc:
            _drop(part)
            if exc.status == 404:
                continue  # rendition listed but not served; try the next
            raise
        os.replace(part, dest)
        return dest
    # No MP4 rendition served (or none listed): remux the HLS playlist.
    # (A failed remux names the token-auth hint itself; anything else —
    # a missing ffmpeg, a timeout — passes through naming its own fix.)
    try:
        remux_hls(playlist_url(cfg["cdn"], guid), part, referer)
    except RuntimeError:
        _drop(part)
        raise
    os.replace(part, dest)
    return dest


def require_upload_config(env=None):
    """Library credentials for UPLOADING lesson bytes. Listing can go
    through the proxy without the key; bytes upload direct, so the key
    is mandatory — exits naming the fix."""
    cfg = load_config(env)
    if not cfg["api_key"]:
        raise SystemExit("Missing CLOUD_LIBRARY_KEY — paste the library "
                         "AccessKey in .env (Stream dashboard -> library "
                         "-> API) to upload fetched lessons.")
    return cfg


def create_video(cfg, title):
    """Create the library video object; returns its guid."""
    payload = json.dumps(
        {"title": title or "Unwritten lesson"}).encode("utf-8")
    req = urllib.request.Request(
        "%s/library/%s/videos" % (API, cfg["library_id"]),
        data=payload,
        headers={"AccessKey": cfg["api_key"],
                 "Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": "UnwrittenCraft/1.0"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            obj = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("Stream video create refused (%s): %s "
                           "(check CLOUD_LIBRARY_ID and "
                           "CLOUD_LIBRARY_KEY)" % (exc.code, body))
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise RuntimeError("Stream video create failed: %s" % exc)
    guid = obj.get("guid") or obj.get("videoId") or ""
    if not guid:
        raise RuntimeError("Stream video create returned no video id: %.80s"
                           % json.dumps(obj))
    return guid


def upload_bytes(cfg, guid, path, timeout=PUT_TIMEOUT):
    """PUT one file's bytes to its video object. Streams from disk in
    chunks — an hour-long lesson never sits whole in RAM. The
    octet-stream content type is mandatory: without it the vendor
    answers 400."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise RuntimeError("cannot read %s: %s" % (path, exc))
    parts = urllib.parse.urlsplit(API)
    conn_cls = http.client.HTTPSConnection \
        if parts.scheme == "https" else http.client.HTTPConnection
    try:
        conn = conn_cls(parts.hostname, parts.port or None,
                        timeout=timeout)
        conn.putrequest("PUT", "/library/%s/videos/%s"
                        % (cfg["library_id"], guid))
        conn.putheader("AccessKey", cfg["api_key"])
        conn.putheader("Content-Type", "application/octet-stream")
        conn.putheader("Content-Length", str(size))
        conn.endheaders()
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(1024 * 256)
                if not chunk:
                    break
                conn.send(chunk)
        resp = conn.getresponse()
        status, body = resp.status, resp.read().decode("utf-8", "replace")
        conn.close()
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError("Stream upload failed for %s: %s" % (guid, exc))
    if status is None or status < 200 or status >= 300:
        raise RuntimeError("Stream upload refused for %s (%s): %s"
                           % (guid, status, body[:300]))
    return guid


def video_status(cfg, guid):
    """The vendor's integer status for one video (4 = finished)."""
    data = http_get_json("%s/library/%s/videos/%s"
                         % (API, cfg["library_id"], guid),
                         {"AccessKey": cfg["api_key"],
                          "Accept": "application/json"})
    try:
        return int(data.get("status", -1))
    except (TypeError, ValueError):
        raise RuntimeError("Stream answered for %s with no status: %.80s"
                           % (guid, json.dumps(data)))


def await_finished(cfg, guid, timeout=POLL_TIMEOUT, interval=POLL_INTERVAL):
    """Poll until the video is finished/playable. A transcode error or
    an expired wait raises naming the video — the caller records it
    failed and a retry reuses the same video id."""
    deadline = time.time() + timeout
    while True:
        status = video_status(cfg, guid)
        if status == FINISHED:
            return
        if status in (5, 6):
            raise RuntimeError("Stream video %s failed transcoding "
                               "(status %d) — check the source file, "
                               "then retry." % (guid, status))
        if time.time() >= deadline:
            raise RuntimeError("Stream video %s still not finished "
                               "after %ds (status %d) — retry later; "
                               "the same video id is reused."
                               % (guid, int(timeout), status))
        time.sleep(interval)


def load_state(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            data = json.load(fh)
    except (ValueError, OSError) as exc:
        raise SystemExit("Unreadable cloud state %s: %s "
                         "(fix or move it aside — deleting it would "
                         "reprocess every cloud video)." % (path, exc))
    if not isinstance(data, dict):
        raise SystemExit("Unreadable cloud state %s: valid JSON but not "
                         "an object (fix or move it aside — treating it "
                         "as empty would reprocess every cloud video)."
                         % path)
    return data


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(state, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def main():
    ap_dest = sys.argv[1] if len(sys.argv) > 1 else ""
    if not ap_dest or ap_dest in ("-h", "--help"):
        print("usage: cloud_fetch.py <dest_dir> [--state PATH] [--max N]")
        return 0 if ap_dest else 2
    state_path = ""
    max_n = 0
    args = sys.argv[2:]
    while args:
        flag = args.pop(0)
        if flag == "--state" and args:
            state_path = args.pop(0)
        elif flag == "--max" and args:
            try:
                max_n = int(args.pop(0))
            except ValueError:
                print("invalid --max value (want an integer)")
                return 2
        else:
            print("unknown flag: %s" % flag)
            return 2
    cfg = load_config()
    os.makedirs(ap_dest, exist_ok=True)
    state_path = state_path or os.path.join(ap_dest, "cloud_state.json")
    state = load_state(state_path)
    videos = list_videos(cfg)
    ready = select_ready(videos, state)
    if max_n > 0:
        ready = ready[:max_n]
    if not ready:
        print("[cloud] no new finished videos.")
        return 0
    failures = 0
    for vid in ready:
        try:
            dest = download_video(cfg, vid, ap_dest)
        except Exception as exc:
            failures += 1
            print("[cloud] fetch failed for %r: %s"
                  % (vid.get("title"), exc))
            state[vid["guid"]] = {"title": vid.get("title", ""),
                                  "result": "failed",
                                  "error": str(exc)}
            save_state(state_path, state)
            continue
        state[vid["guid"]] = {"title": vid.get("title", ""),
                              "lesson": dest, "result": "downloaded"}
        save_state(state_path, state)
        print("[cloud] fetched %s -> %s" % (vid.get("title"), dest))
    print("[cloud] %d video(s) fetched, %d failed."
          % (len(ready) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
