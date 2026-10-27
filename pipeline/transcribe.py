"""Transcription for the Unwritten Craft pipeline.

Extracts audio with ffmpeg and transcribes locally with faster-whisper
(no audio leaves the machine — a teacher's voice is not ours to upload).
Model size via UNWRITTEN_WHISPER_MODEL (default "base"; "tiny" is faster
and worse, "small" is slower and better). First run downloads the model.

Usage: transcribe.py <media_file> <out_dir>
Writes <out_dir>/transcript.txt and <out_dir>/segments.json.
"""
import json
import os
import subprocess
import sys
import tempfile


def extract_audio(media, wav):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", media, "-vn",
         "-ac", "1", "-ar", "16000", wav],
        check=True)


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


def transcribe(media):
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
        # An empty transcript must never become an "empty teacher" the
        # card drafter then invents steps for (Wonder review).
        raise RuntimeError(
            f"no speech recognized in {os.path.basename(media)} "
            f"(language={info.language}, p={info.language_probability:.2f}) — "
            "silent or wrong file; refusing to transcribe emptiness")
    print(f"  language={info.language} (p={info.language_probability:.2f})",
          file=sys.stderr)
    return segs


def main():
    if len(sys.argv) != 3:
        print("usage: transcribe.py <media_file> <out_dir>")
        sys.exit(2)
    media, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    segs = transcribe(media)
    with open(os.path.join(out_dir, "transcript.txt"), "w") as fh:
        fh.write(" ".join(s["text"] for s in segs).strip() + "\n")
    with open(os.path.join(out_dir, "segments.json"), "w") as fh:
        json.dump(segs, fh, indent=1)
    print(f"transcribed {len(segs)} segments from {os.path.basename(media)}")


if __name__ == "__main__":
    main()
