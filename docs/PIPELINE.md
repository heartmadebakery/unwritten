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
   ├─► draft_writeup.py ─► writeup.md        (Muse Spark: transcript
   │                                        + lesson frames) — THE WRITE-UP (#3)
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

## Cloud lessons

When the recorders upload with Cloud on, finished lessons can be
processed without copying files off the phone first:

```
export CLOUD_LIBRARY_ID=... CLOUD_LIBRARY_KEY=... CLOUD_CDN_HOSTNAME=...
pipeline/run_pipeline.py --cloud work/cloud [--max N] [--retry-failed]
```

`--cloud` lists the Cloud library, downloads each new finished video
(status 4) into `cloud_downloads/`, and runs the full pipeline on
each into its own `work/cloud/<title>__<videoid>/` dir. Seen videos
are remembered in `cloud_state.json`, so reruns only pick up new
lessons; failed ones stay failed unless `--retry-failed` is given.
`CLOUD_LIBRARY_KEY` is the library AccessKey and `CLOUD_CDN_HOSTNAME`
the pull-zone hostname — both on the Stream dashboard's library API
page — and both stay on this machine only (same trust as the
recorders' direct mode). Without `--cloud` the pipeline never touches
the network: same single-lesson flow as before.

Python deps live in `.venv` (faster-whisper); the runner re-invokes
the transcription stage under it when present. Everything else is
stdlib + ffmpeg + Muse calls.

## Stage notes

- **Transcription is local on purpose.** faster-whisper (base model,
  int8, CPU) — a mentor's raw voice never leaves the machine for a
  third-party transcription service. `UNWRITTEN_WHISPER_MODEL=small`
  trades speed for accuracy. Negations matter: a dropped "don't"
  inverts a step, so the write-up's imperatives get checked back
  against this transcript.
- **The Model API is opt-in per run.** Video understanding and SAM
  segmentation need `MODEL_API_KEY`; without it the pipeline takes
  the keyless path (still frames, plain clips) and nothing changes.
  With it, the lesson video — picture and voice, by the owner's
  explicit choice — is uploaded for the write-up, and each
  correction clip for its highlight; uploads are deleted
  afterwards. Transcription itself always stays local.
- **The write-up** is `draft_writeup.py`: a polished, sectioned
  document in the mentor's voice; the transcript is the spine, and
  what it leaves unsaid is filled in from the lesson video — never
  from outside knowledge. With `MODEL_API_KEY` set, Spark watches
  the whole video (Meta video understanding, visuals and speech);
  otherwise evenly spaced still frames go along (`--image`
  attachments), and without lesson media it degrades to
  transcript-only.
- **Correction highlights** ride on the clips: when the finder names
  a visible subject (`"segment"`) and `MODEL_API_KEY` is set, SAM
  3.1 tracks it through the cut clip (Meta media segmentation) and
  the runner renders `highlight-NN.mp4` — subject spotlighted, rest
  dimmed — plus `segments-NN.json` with the tracks. Any failure
  keeps the plain clip and the anchor; highlights never block a run.
- **The corrections** are `find_corrections.py`: the timestamped
  transcript + `prompts/correction_finder.md` into Muse Spark. Each
  hit is a technique: timestamp, the mentor's exact words, what they were
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
