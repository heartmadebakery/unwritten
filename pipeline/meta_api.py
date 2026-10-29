"""Meta Model API client, stdlib only: Files + Responses.

Two capabilities feed the pipeline's end result:

* video understanding (muse-spark-1.3) — the whole lesson video, visuals
  plus embedded audio, grounds the write-up in what actually happened;
* media segmentation (sam-3.1) — a short noun phrase tracks a subject
  through a correction clip as boxes + masks, which become highlights.

Both need MODEL_API_KEY. Every caller must degrade gracefully without
it — the pipeline never requires the key. Uploaded files are deleted
after use; team Files storage only grows until removed.
"""
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request

BASE_URL = "https://api.meta.ai/v1"
SPARK_MODEL = "muse-spark-1.3"
SAM_MODEL = "sam-3.1"
ASR_MODEL = "muse-voice-transcribe-1.0"


class MetaApiError(Exception):
    """Anything the Model API refused or failed to return."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def api_key():
    return os.environ.get("MODEL_API_KEY", "")


def _post_multipart(url, fields, files, key, timeout):
    """POST multipart/form-data. fields: {name: value} where a value may
    be (value, content_type) for typed parts; files: [(field, filename,
    mime, bytes)]. Returns parsed JSON."""
    boundary = "----unwritten-%d" % os.getpid()
    body = bytearray()
    for name, value in fields.items():
        ctype = None
        if isinstance(value, tuple):
            value, ctype = value
        part = ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n"
                % (boundary, name))
        if ctype:
            part += "Content-Type: %s\r\n" % ctype
        body += (part + "\r\n%s\r\n" % value).encode()
    for field, filename, mime, data in files:
        body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; "
                 "filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                 % (boundary, field, filename, mime)).encode()
        body += data + b"\r\n"
    body += ("--%s--\r\n" % boundary).encode()
    req = urllib.request.Request(
        url, data=bytes(body),
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "multipart/form-data; boundary=" + boundary},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise MetaApiError("POST %s -> HTTP %s: %s" % (url, exc.code, detail),
                           status=exc.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MetaApiError("POST %s failed: %s" % (url, exc))


def _post_json(url, payload, key, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key,
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise MetaApiError("POST %s -> HTTP %s: %s" % (url, exc.code, detail),
                           status=exc.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MetaApiError("POST %s failed: %s" % (url, exc))


def upload_file(path, purpose="user_data", timeout=600):
    """Upload once to the Files API; returns the file- ID. The caller
    owns cleanup via delete_file."""
    key = api_key()
    if not key:
        raise MetaApiError("MODEL_API_KEY is not set")
    with open(path, "rb") as fh:
        data = fh.read()
    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    resp = _post_multipart(BASE_URL + "/files", {"purpose": purpose},
                           [("file", os.path.basename(path), mime, data)],
                           key, timeout)
    file_id = resp.get("id", "")
    if not isinstance(file_id, str) or not file_id.startswith("file-"):
        raise MetaApiError("Files API returned no file ID")
    return file_id


def delete_file(file_id, timeout=60):
    """Best-effort cleanup; returns False instead of raising."""
    key = api_key()
    if not key or not file_id:
        return False
    req = urllib.request.Request(
        BASE_URL + "/files/" + file_id,
        headers={"Authorization": "Bearer " + key}, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def responses_create(model, content, key, timeout=900, extra=None):
    """One non-streaming Responses call. content is the user message's
    content-block list. Returns the parsed response object."""
    payload = {"model": model,
               "input": [{"type": "message", "role": "user",
                          "content": content}]}
    if extra:
        payload.update(extra)
    return _post_json(BASE_URL + "/responses", payload, key, timeout)


def output_text(resp):
    """Concatenate every output_text chunk of a Responses object.
    Defensive: unknown shapes yield "" rather than raising."""
    texts = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") in ("output_text", "output_text.delta") \
                    and isinstance(node.get("text", node.get("delta")), str):
                texts.append(node.get("text", node.get("delta")))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    try:
        walk(resp.get("output", resp))
    except Exception:
        return ""
    return "".join(texts)


def ask_video(video_ref, prompt, key, model=SPARK_MODEL, timeout=1200):
    """Ask about a video: video_ref is {"file_id": ...} for an upload
    or {"video_url": ...} for a hosted file. Returns the text answer."""
    if not key:
        raise MetaApiError("MODEL_API_KEY is not set")
    block = {"type": "input_video"}
    block.update(video_ref)
    resp = responses_create(
        model, [{"type": "input_text", "text": prompt}, block],
        key, timeout=timeout)
    text = output_text(resp).strip()
    if not text:
        raise MetaApiError("video understanding returned no text")
    return text


def asr_transcribe(wav_path, key, mode="DIARIZATION", timeout=900,
                 empty_ok=False, keywords=None, languages=None):
    """Transcribe one supported WAV (mono 16-bit PCM, 16/24 kHz) via
    Muse Voice Transcribe. Returns [{start, end, text, speaker?}] with
    seconds. keywords/languages bias recognition toward the mentor's
    own vocabulary and languages (a hint, never a force). Empty
    results raise unless empty_ok (multi-chunk callers tolerate
    silent chunks but refuse a silent whole). Retries follow the
    docs: backoff on 429, once on 500."""
    if not key:
        raise MetaApiError("MODEL_API_KEY is not set")
    with open(wav_path, "rb") as fh:
        data = fh.read()
    config = {"mode": mode, "model": ASR_MODEL, "audioEncoding": "WAV"}
    if keywords:
        config["keywords"] = list(keywords)
    if languages:
        config["languageBias"] = list(languages)
    settings = json.dumps(config)
    resp = None
    for attempt in range(4):
        try:
            resp = _post_multipart(
                BASE_URL + "/asr/transcribe",
                {"request": (settings, "application/json")},
                [("audio", os.path.basename(wav_path), "audio/wav", data)],
                key, timeout)
            break
        except MetaApiError as exc:
            if exc.status == 429 and attempt < 3:
                time.sleep(min(2 ** attempt, 30))
                continue
            if exc.status == 500 and attempt == 0:
                time.sleep(2)
                continue
            raise
    segs = []
    for turn in resp.get("turns", []) or []:
        text = (turn.get("transcript") or "").strip()
        if not text:
            continue
        seg = {"start": round(turn.get("startMs", 0) / 1000, 2),
               "end": round(turn.get("endMs", 0) / 1000, 2),
               "text": text}
        if turn.get("speaker"):
            seg["speaker"] = turn["speaker"]
        segs.append(seg)
    if not segs and not empty_ok:
        raise MetaApiError(
            "no speech recognized in %s — silent or wrong file; "
            "refusing to transcribe emptiness"
            % os.path.basename(wav_path))
    return segs


def segment_video_lines(file_id, concept, key, timeout=1200):
    """Track one noun-phrase concept through an uploaded clip. Returns
    the raw wire text (one <Nf> line per frame) — "" when nothing
    matched, which is a valid outcome, not an error."""
    if not key:
        raise MetaApiError("MODEL_API_KEY is not set")
    phrase = (concept or "").strip()
    if not phrase:
        raise MetaApiError("segmentation needs a short noun phrase")
    resp = responses_create(
        SAM_MODEL,
        [{"type": "input_text", "text": phrase},
         {"type": "input_video", "file_id": file_id}],
        key, timeout=timeout)
    return output_text(resp).strip()


_LINE_RE = re.compile(r"^<(\d+)f>(.*)$")
_RECORD_SPLIT = re.compile(r",(?=\d+<\|box)")
_BOX_RE = re.compile(
    r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)"
    r"(?:;c=([\d.]+))?\|>")
_MASK_RE = re.compile(
    r"<\|mask;x=0;y=0(?:;c=([\d.]+))?;data=(\d+),(\d+),([~!])([^|]*)\|>")


def _num(value, kind):
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


def parse_segmentation(text):
    """Parse SAM wire text into per-frame records.

    Returns [{"frame": N, "records": [{"id": int,
    "box": {"x1","y1","x2","y2","w","h","c" or None},
    "mask": {"h","w","enc","payload","c" or None}}]}].
    Malformed lines are skipped; "" parses to []. Masks are box-local
    rasters (height rows x width columns).
    """
    frames = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        records = []
        for chunk in _RECORD_SPLIT.split(m.group(2)):
            id_m = re.match(r"(\d+)<\|", chunk)
            box_m = _BOX_RE.search(chunk)
            mask_m = _MASK_RE.search(chunk)
            if not id_m or not box_m or not mask_m:
                continue
            records.append({
                "id": int(id_m.group(1)),
                "box": {"x1": int(box_m.group(1)), "y1": int(box_m.group(2)),
                        "x2": int(box_m.group(3)), "y2": int(box_m.group(4)),
                        "w": int(box_m.group(5)), "h": int(box_m.group(6)),
                        "c": _num(box_m.group(7), float)},
                "mask": {"h": int(mask_m.group(2)), "w": int(mask_m.group(3)),
                         "enc": mask_m.group(4), "payload": mask_m.group(5),
                         "c": _num(mask_m.group(1), float)},
            })
        if records:
            frames.append({"frame": int(m.group(1)), "records": records})
    return frames


def tracks(frames):
    """Per-object spans across parsed frames: {id: {"frames": [N...],
    "boxes": [(x1,y1,x2,y2)...]}}. Ids are sparse by design."""
    out = {}
    for entry in frames:
        for rec in entry["records"]:
            track = out.setdefault(rec["id"], {"frames": [], "boxes": []})
            track["frames"].append(entry["frame"])
            box = rec["box"]
            track["boxes"].append((box["x1"], box["y1"], box["x2"], box["y2"]))
    return out
