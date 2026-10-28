# The pipeline — three core things

What happens after the lesson. Capture is a commodity: one ordinary
lesson filmed on a phone, no recorder protocol, no step names, nothing
performed for the machine. This pipeline processes that one file.

```
lesson folder (off the phone)
   │  ingest.py — classify by extension; the largest media file
   │              is the lesson (or name it with --lesson)
   ▼
THE LESSON VIDEO — kept whole (core thing #1)
   │  transcribe.py — local faster-whisper
   ▼
transcript.txt + transcript_timestamped.txt ("[mm:ss] text" per segment)
   ├─► draft_writeup.py ─► writeup.md        (Muse Spark, stenographer
   │                                        rule) — THE WRITE-UP (#3)
   └─► find_corrections.py ─► corrections.json + corrections.md
                                            (Muse Spark), and each
                                            correction cut from the
                                            lesson into clips/ — THE
                                            CORRECTION CLIPS (#2)
```

Run it:

```
pipeline/run_pipeline.py <session_dir> <work_dir> [--lesson FILE] [--transcript FILE]
```

`--transcript FILE` skips transcription and uses an existing
timestamped transcript — how the core test in
`docs/core-test-2026-10-27.md` was run. The runner exits non-zero
unless a write-up **and** a corrections list were produced this run;
stale outputs from a previous run are deleted up front.

Python deps live in `.venv` (faster-whisper); the runner re-invokes
the transcription stage under it when present. Everything else is
stdlib + ffmpeg + Muse calls.

## Stage notes

- **Transcription is local on purpose.** faster-whisper (base model,
  int8, CPU) — a teacher's raw voice never leaves the machine for a
  third-party transcription service. `UNWRITTEN_WHISPER_MODEL=small`
  trades speed for accuracy. Negations matter: a dropped "don't"
  inverts a step, so the write-up's imperatives get checked back
  against this transcript.
- **The write-up** is `draft_writeup.py`: transcript + the stenographer
  prompt (`prompts/writeup_drafter.md`) into Muse Spark via Muse.
  Her steps in her words; nothing added.
- **The corrections** are `find_corrections.py`: the timestamped
  transcript + `prompts/correction_finder.md` into Muse Spark. Each
  hit is a technique: timestamp, her exact words, what she was
  correcting. `run_pipeline.py` renders `corrections.md` and cuts each
  moment from the lesson video with ffmpeg (segment window padded
  2 s on both sides; a failed cut keeps the timestamp anchor and says
  so — it never blocks the run).
- **Clips need the lesson file.** A transcript-only run produces
  anchored corrections without clips; the anchors carry the timestamps
  either way.

## Not in this pipeline

- **The page/guide** (`pipeline/make_page.py`) — optional, later, for a
  recipient who wasn't in the room. It assembles `writeup.md` +
  `corrections.json` + `clips/` into one HTML page. The core never
  calls it and nothing in the core depends on it.
- **The retired apprentice design** — `harness/`,
  `pipeline/sam_overlay.py`, `pipeline/frames.py`,
  `prompts/apprentice*`. Cut Oct 27, 2026; kept in the tree as retired
  experiments, invoked by nothing here.
- **The recorder apps** (`app/`) — a single-mode recorder (record one
  lesson, stop, keep the file). An ordinary phone camera produces the
  same lesson file and works just as well.
