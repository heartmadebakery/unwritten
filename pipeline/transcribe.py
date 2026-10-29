"""Transcription for the Unwritten Craft pipeline.

Default: Meta speech-to-text (Muse Voice Transcribe, DIARIZATION) over
the Model API — needs MODEL_API_KEY. Turn-level timestamps plus
speaker labels come back per speech turn. Audio over 10 minutes is
split into <=10-minute chunks (the API cap) and the turns are
re-offset; a cut may garble a word at a boundary.

Optional: local faster-whisper (nothing leaves the machine) when the
key is missing or UNWRITTEN_TRANSCRIBE=local. UNWRITTEN_TRANSCRIBE=api
forces the API and fails loudly without a key; any other value is a
usage error. The local model size is UNWRITTEN_WHISPER_MODEL (default
"base"). First local run downloads the model.

API recognition bias (set from past write-ups' vocabulary):
UNWRITTEN_ASR_KEYWORDS="sinigang,patis" and
UNWRITTEN_ASR_LANGUAGES="English,Tagalog" — hints, never forced.

Usage: transcribe.py <media_file> <out_dir>
Writes <out_dir>/transcript.txt (plain), <out_dir>/transcript_timestamped.txt
(one "[mm:ss] text" line per segment — the correction finder consumes
this), and <out_dir>/segments.json (segments gain a "speaker" label on
the API path; the line format is unchanged).
"""
import json
import math
import os
import subprocess
import sys
import tempfile

import meta_api

CHUNK_SECONDS = 600  # the API refuses audio over 10 minutes
API_RATE = 24000     # the model's native sample rate
LOCAL_RATE = 16000   # what faster-whisper consumes


def chunk_plan(duration_s):
    """Split a duration into [(offset_s, length_s)] chunks of at most
    CHUNK_SECONDS. One chunk passes through untouched."""
    total = max(0, int(math.ceil(duration_s)))
    if total <= CHUNK_SECONDS:
        return [(0, total)]
    plan, start = [], 0
    while start < total:
        length = min(CHUNK_SECONDS, total - start)
        plan.append((start, length))
        start += length
    return plan


def extract_audio(media, wav, rate=LOCAL_RATE, start=0, length=0):
    cmd = ["ffmpeg", "-y", "-v", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", media]
    if length:
        cmd += ["-t", str(length)]
    cmd += ["-vn", "-ac", "1", "-ar", str(rate), "-c:a", "pcm_s16le",
            "-map_metadata", "-1", wav]
    subprocess.run(cmd, check=True)


def wav_duration(wav):
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", wav],
            capture_output=True, text=True, timeout=60)
        return float((proc.stdout or "").strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def load_wav_numpy(wav):
    """Decode a 16kHz mono WAV with the stdlib (avoids a PyAV/faster-whisper
    version clash in decode_audio) and return float32 samples in [-1, 1]."""
    import wave
    import numpy as np
    with wave.open(wav, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        width = wf.getsampwidth()
    if width == 2:
        return (np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0)
    if width == 4:
        return np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    raise ValueError(f"unsupported WAV sample width: {width}")


def transcribe_local(media):
    from faster_whisper import WhisperModel
    model_name = os.environ.get("UNWRITTEN_WHISPER_MODEL", "base")
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "audio.wav")
        extract_audio(media, wav)
        audio = load_wav_numpy(wav)
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        segments, info = model.transcribe(audio, beam_size=1, vad_filter=True)
        segs = [{"start": round(s.start, 2), "end": round(s.end, 2),
                 "text": s.text.strip()} for s in segments]
    text = " ".join(s["text"] for s in segs).strip()
    if not text:
        # An empty transcript must never become an "empty mentor" the
        # write-up drafter then invents steps for (Wonder review).
        raise RuntimeError(
            f"no speech recognized in {os.path.basename(media)} "
            f"(language={info.language}, p={info.language_probability:.2f}) — "
            "silent or wrong file; refusing to transcribe emptiness")
    print(f"  engine=local-whisper ({model_name}) "
          f"language={info.language} (p={info.language_probability:.2f})",
          file=sys.stderr)
    return segs


def _csv_env(name):
    return [item.strip() for item in os.environ.get(name, "").split(",")
            if item.strip()]


def transcribe_api(media, key):
    keywords = _csv_env("UNWRITTEN_ASR_KEYWORDS")
    languages = _csv_env("UNWRITTEN_ASR_LANGUAGES")
    print("  engine=meta-asr (muse-voice-transcribe-1.0, DIARIZATION)"
          + (f" keywords={keywords} languages={languages}"
             if keywords or languages else ""),
          file=sys.stderr)
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "audio.wav")
        extract_audio(media, wav, rate=API_RATE)
        dur = wav_duration(wav)
        plan = chunk_plan(dur) if dur else [(0, 0)]
        multi = len(plan) > 1
        segs = []
        for index, (start, length) in enumerate(plan):
            chunk = wav
            if multi:
                chunk = os.path.join(td, "chunk-%02d.wav" % index)
                extract_audio(media, chunk, rate=API_RATE,
                              start=start, length=length)
            for seg in meta_api.asr_transcribe(
                    chunk, key, empty_ok=multi, keywords=keywords,
                    languages=languages):
                seg["start"] = round(seg["start"] + start, 2)
                seg["end"] = round(seg["end"] + start, 2)
                segs.append(seg)
    if not segs:
        raise meta_api.MetaApiError(
            "no speech recognized in %s — silent or wrong file; "
            "refusing to transcribe emptiness" % os.path.basename(media))
    return segs


def transcribe(media):
    choice = os.environ.get("UNWRITTEN_TRANSCRIBE", "").strip().lower()
    key = meta_api.api_key()
    if choice in ("", "auto"):
        if key:
            return transcribe_api(media, key)
        return transcribe_local(media)
    if choice == "local":
        return transcribe_local(media)
    if choice == "api":
        if not key:
            raise meta_api.MetaApiError(
                "UNWRITTEN_TRANSCRIBE=api but MODEL_API_KEY is not set")
        return transcribe_api(media, key)
    raise ValueError("UNWRITTEN_TRANSCRIBE must be auto, api, or local "
                     "(got %r)" % choice)


def fmt_ts(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def main():
    if len(sys.argv) != 3:
        print("usage: transcribe.py <media_file> <out_dir>")
        sys.exit(2)
    media, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    segs = transcribe(media)
    with open(os.path.join(out_dir, "transcript.txt"), "w") as fh:
        fh.write(" ".join(s["text"] for s in segs).strip() + "\n")
    with open(os.path.join(out_dir, "transcript_timestamped.txt"), "w") as fh:
        for s in segs:
            fh.write(f"[{fmt_ts(s['start'])}] {s['text']}\n")
    with open(os.path.join(out_dir, "segments.json"), "w") as fh:
        json.dump(segs, fh, indent=1)
    print(f"transcribed {len(segs)} segments from {os.path.basename(media)}")


if __name__ == "__main__":
    main()
