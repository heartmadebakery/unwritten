#!/usr/bin/env python3
"""Claim queued URL fetch jobs and turn them into sessions.

The apps queue video URLs the browser cannot download itself
(YouTube/watch pages) at the signer Worker (POST /fetch/jobs); this
module claims them one at a time, downloads each video, and lays it
out as a session dir the pipeline runs like any other:

  FETCH_QUEUE_URL   signer Worker URL (falls back to CLOUD_PROXY_URL)
  FETCH_QUEUE_TOKEN signer token (falls back to CLOUD_PROXY_TOKEN,
                    then line 1 of app/cloud-signer/tokens.txt)

Direct media URLs download with plain HTTPS; anything else goes
through yt-dlp (pip install yt-dlp), which also needs ffmpeg for its
mp4 merge. Terminal states mirror the cloud fetcher: a failed job
stays failed until --retry-failed reclaims it, and a claim older
than two hours counts as an abandoned worker and comes back.
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

import cloud_fetch

MEDIA_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".m4v",
              ".mp3", ".m4a", ".wav", ".ogg")
YTDLP_TIMEOUT = 1800
WORKER_NAME = "pipeline"


class QueueError(Exception):
    pass


def load_config(env=None):
    """Read the queue URL + token. Exits loudly without a URL so a
    --fetch run never silently processes nothing."""
    env = os.environ if env is None else env
    queue = (env.get("FETCH_QUEUE_URL")
             or env.get("CLOUD_PROXY_URL") or "").strip().rstrip("/")
    if not queue:
        raise SystemExit("Missing FETCH_QUEUE_URL — export the signer "
                         "Worker URL (or CLOUD_PROXY_URL) to fetch "
                         "queued URLs.")
    token = (env.get("FETCH_QUEUE_TOKEN")
             or env.get("CLOUD_PROXY_TOKEN") or "").strip()
    if not token:
        try:
            here = os.path.dirname(os.path.abspath(__file__))
            pool_path = os.path.join(os.path.dirname(here), "app",
                                     "cloud-signer", "tokens.txt")
            with open(pool_path) as fh:
                token = fh.readline().strip()
        except OSError:
            pass
    return {"queue": queue, "token": token}


def classify_url(url):
    """'direct' when the URL names a media file, else 'page' (yt-dlp)."""
    try:
        path = urllib.parse.urlparse(url).path.lower()
    except Exception:
        return "page"
    return "direct" if path.endswith(MEDIA_EXTS) else "page"


def direct_ext(url):
    """A download extension for a direct URL (mp4 fallback)."""
    name = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1].lower()
    ext = os.path.splitext(name)[1].lstrip(".")
    return ext if ext in ("mp4", "webm", "mov", "mkv", "m4v",
                          "mp3", "m4a", "wav", "ogg") else "mp4"


def stamp():
    """Full date + time + milliseconds, like the web recorder's takes."""
    ms = int(time.time() * 1000) % 1000
    return time.strftime("%Y%m%d-%H%M%S", time.localtime()) + "-%03d" % ms


def media_name(ext):
    return "unwritten_lesson_%s.%s" % (stamp(), ext)


def _short_id(job_id):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", job_id or "")[-8:] or "job"


def session_dir_name(job_id):
    return "fetch_" + _short_id(job_id)


def job_slug(title, job_id):
    return "%s__%s" % (cloud_fetch.sanitize(title), _short_id(job_id))


def is_media_file(name):
    """True for finished media names only — never a ".part" sidecar
    or a yt-dlp ".ytdl"/".temp" leftover from a killed run."""
    return name.lower().endswith(MEDIA_EXTS)


def existing_media(session_dir):
    """A previously downloaded lesson in the session dir, else '' —
    lets --retry-failed resume without re-downloading. An interrupted
    download's sidecar never counts: a killed run skips the cleanup,
    and resuming from it would process a truncated lesson as real."""
    if not os.path.isdir(session_dir):
        return ""
    for entry in sorted(os.listdir(session_dir)):
        if not entry.startswith("unwritten_lesson_") \
                or not is_media_file(entry):
            continue
        full = os.path.join(session_dir, entry)
        if os.path.isfile(full) and os.path.getsize(full) > 0:
            return full
    return ""


def write_source(session_dir, job, title, lesson):
    with open(os.path.join(session_dir, "source.json"), "w") as fh:
        json.dump({"url": job.get("url", ""), "title": title,
                   "job_id": job.get("id", ""),
                   "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "lesson": os.path.basename(lesson)}, fh, indent=1)


def read_source_title(session_dir):
    try:
        with open(os.path.join(session_dir, "source.json")) as fh:
            return json.load(fh).get("title", "") or ""
    except (OSError, ValueError):
        return ""


def read_upload_guid(session_dir):
    """The Stream video id minted for this session ("" when none) —
    written once, right after create, so a retry reuses it instead of
    minting a duplicate video."""
    try:
        with open(os.path.join(session_dir, "upload.json")) as fh:
            return json.load(fh).get("videoId", "") or ""
    except (OSError, ValueError):
        return ""


def write_upload_guid(session_dir, guid):
    with open(os.path.join(session_dir, "upload.json"), "w") as fh:
        json.dump({"videoId": guid}, fh, indent=1)


def _request(cfg, method, path, body=None):
    url = cfg["queue"] + path
    headers = {"User-Agent": "UnwrittenCraft/1.0", "Accept": "application/json"}
    if cfg.get("token"):
        headers["X-Signer-Token"] = cfg["token"]
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {}
            try:
                return json.loads(raw)
            except ValueError:
                raise QueueError("fetch queue answered %s with not JSON "
                                 "(edge error page?): %.80s"
                                 % (path, raw.strip()))
    except urllib.error.HTTPError as exc:
        eb = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 401:
            raise QueueError("fetch queue refused the token (401) — "
                             "check FETCH_QUEUE_TOKEN / tokens.txt.")
        raise QueueError("fetch queue %s for %s: %s" % (exc.code, path, eb))
    except urllib.error.URLError as exc:
        raise QueueError("fetch queue unreachable at %s: %s "
                         "(is FETCH_QUEUE_URL right?)"
                         % (cfg["queue"], exc.reason))
    except (OSError, http.client.HTTPException) as exc:
        raise QueueError("fetch queue request failed: %s" % exc)


def claim_job(cfg, by=WORKER_NAME, include_failed=False):
    """Oldest pending job (or None). include_failed also reclaims
    failed ones — the --retry-failed path."""
    path = "/fetch/jobs?claim=1&by=" + urllib.parse.quote(by)
    if include_failed:
        path += "&includeFailed=1"
    return _request(cfg, "GET", path).get("job")


def finish_job(cfg, job_id, ok, session="", error=""):
    verb = "done" if ok else "failed"
    body = {"session": session} if ok else {"error": error}
    _request(cfg, "POST",
             "/fetch/jobs/%s/%s" % (urllib.parse.quote(job_id), verb),
             body)


def rehanded(cfg, job, attempted, tag="[fetch]"):
    """True when the queue hands back a job this run already tried.
    --retry-failed reclaims failed jobs, so one that just failed
    comes straight back: claiming it again would loop forever. The
    claim is put back as failed with its error (a dangling claim
    would return after two hours even without --retry-failed) and
    the caller stops claiming."""
    job_id = job.get("id", "")
    if job_id not in attempted:
        return False
    print("%s %r already failed this run — leaving it failed."
          % (tag, job.get("url")))
    try:
        finish_job(cfg, job_id, False,
                   error=attempted[job_id] or "failed again this run")
    except Exception as exc:
        print("%s could not mark failed: %s" % (tag, exc))
    return True


def download_direct(url, dest):
    """Plain-HTTPS download into a .part sidecar, renamed only on
    success — the cloud path's discipline: an interrupted download
    must never leave a truncated lesson that a retry would process
    as real."""
    part = dest + ".part"
    try:
        cloud_fetch.http_download(url, part)
    except Exception:
        try:
            if os.path.exists(part):
                os.unlink(part)
        except OSError:
            pass
        raise
    os.replace(part, dest)
    return dest


def _ytdlp_cmd():
    """yt-dlp invocation: the binary when on PATH, else the running
    interpreter's module (cron has no venv bin on PATH)."""
    exe = shutil.which("yt-dlp")
    if exe:
        return [exe]
    try:
        import importlib.util
        if importlib.util.find_spec("yt_dlp") is not None:
            return [sys.executable, "-m", "yt_dlp"]
    except Exception:
        pass
    return None


def ytdlp_title(url):
    """Best-effort video title ('' when anything fails)."""
    base = _ytdlp_cmd()
    if not base:
        return ""
    try:
        proc = subprocess.run(
            base + ["--no-playlist", "--no-warnings",
                    "--print", "%(title)s", "--skip-download", url],
            capture_output=True, text=True, timeout=120)
    except subprocess.SubprocessError:
        return ""
    if proc.returncode != 0:
        return ""
    lines = (proc.stdout or "").strip().splitlines()
    return lines[0].strip() if lines else ""


def ytdlp_download(url, session_dir):
    """yt-dlp the URL into the session dir as the lesson file."""
    base = _ytdlp_cmd()
    if not base:
        raise QueueError("yt-dlp is not installed — install it "
                         "(pip install yt-dlp) to fetch %s" % url)
    tmpl = os.path.join(session_dir, "video.%(ext)s")
    cmd = base + ["--no-playlist", "--no-warnings", "-f", "bv*+ba/b",
                  "--merge-output-format", "mp4", "-o", tmpl, url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=YTDLP_TIMEOUT)
    except subprocess.SubprocessError as exc:
        raise QueueError("yt-dlp timed out for %s: %s" % (url, exc))
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        raise QueueError("yt-dlp failed for %s: %s"
                         % (url, tail[-1] if tail else proc.returncode))
    produced = [os.path.join(session_dir, entry)
                for entry in os.listdir(session_dir)
                if entry.startswith("video.") and is_media_file(entry)]
    produced = [p for p in produced
                if os.path.isfile(p) and os.path.getsize(p) > 0]
    if not produced:
        raise QueueError("yt-dlp produced no file for %s" % url)
    src = max(produced, key=os.path.getsize)
    ext = os.path.splitext(src)[1].lstrip(".").lower() or "mp4"
    dest = os.path.join(session_dir, media_name(ext))
    os.replace(src, dest)
    return dest


def download_job(job, session_dir):
    """Fetch one claimed job's video into its session dir. Returns
    (lesson_path, title)."""
    url = job.get("url", "")
    if classify_url(url) == "direct":
        dest = os.path.join(session_dir, media_name(direct_ext(url)))
        return download_direct(url, dest), ""
    title = ytdlp_title(url)
    return ytdlp_download(url, session_dir), title


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: fetch_jobs.py <dest_root> [--max N] [--retry-failed]")
        print("  Claims queued URLs and downloads each into "
              "fetch_<job>/ as a pipeline-ready session (no pipeline "
              "run — hand the session dir to run_pipeline.py, or use "
              "--fetch for download+pipeline in one step).")
        return 0 if len(sys.argv) > 1 else 2
    root = sys.argv[1]
    max_n = 0
    retry_failed = False
    args = sys.argv[2:]
    while args:
        flag = args.pop(0)
        if flag == "--max" and args:
            try:
                max_n = int(args.pop(0))
            except ValueError:
                print("invalid --max value (want an integer)")
                return 2
        elif flag == "--retry-failed":
            retry_failed = True
        else:
            print("unknown flag: %s" % flag)
            return 2
    cfg = load_config()
    os.makedirs(root, exist_ok=True)
    done = failures = 0
    attempted = {}  # job id -> its error this run ("" when it finished)
    while True:
        if max_n > 0 and done + failures >= max_n:
            break
        try:
            job = claim_job(cfg, include_failed=retry_failed)
        except QueueError as exc:
            print("[fetch] claim failed: %s" % exc)
            return 1
        if not job or rehanded(cfg, job, attempted):
            break
        attempted[job.get("id", "")] = ""
        session = os.path.join(root, session_dir_name(job.get("id", "")))
        os.makedirs(session, exist_ok=True)
        try:
            lesson = existing_media(session) or None
            title = read_source_title(session)
            if not lesson:
                lesson, title = download_job(job, session)
                write_source(session, job, title, lesson)
            finish_job(cfg, job["id"], True, session=lesson)
        except Exception as exc:
            failures += 1
            attempted[job.get("id", "")] = str(exc)
            print("[fetch] failed for %r: %s" % (job.get("url"), exc))
            try:
                finish_job(cfg, job["id"], False, error=str(exc))
            except QueueError as exc2:
                print("[fetch] could not mark failed: %s" % exc2)
            continue
        done += 1
        print("[fetch] fetched %r -> %s" % (job.get("url"), lesson))
    if not done and not failures:
        print("[fetch] no pending URL jobs.")
        return 0
    print("[fetch] %d job(s) fetched, %d failed." % (done, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
