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
   │  transcribe.py — Meta speech-to-text (or local Whisper)
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

When the apps upload with Cloud on, finished lessons can be
processed without copying files off the phone first:

```
export CLOUD_LIBRARY_ID=... CLOUD_LIBRARY_KEY=... CLOUD_CDN_HOSTNAME=...
pipeline/run_pipeline.py --cloud work/cloud [--max N] [--retry-failed]
```

`--cloud` lists the Cloud library, downloads each new finished video
(status 4) into `cloud_downloads/` (the highest MP4 rendition, else
an ffmpeg remux of the HLS playlist; a body cut off before its
`Content-Length` is refused, never kept), and runs the full pipeline on
each into its own `work/cloud/<title>__<videoid>/` dir. Seen videos
are remembered in `cloud_state.json`, so reruns only pick up new
lessons; failed ones stay failed unless `--retry-failed` is given,
and ones marked `ignored` (an operator decision that the video is not
a lesson) are set aside for good — never re-downloaded, not even on
retry. `CLOUD_LIBRARY_KEY` is the library AccessKey and
`CLOUD_CDN_HOSTNAME` the pull-zone hostname — both on the Stream
dashboard's library API page — and both stay on this machine only
(same trust as the apps' direct mode). Without `--cloud` the pipeline
never touches the network: same single-lesson flow as before.

## Fetched URL jobs

Pasting a link (YouTube, watch pages, direct media files) in any
app's upload screen queues it at the signer (`POST /fetch/jobs`, D1
table `fetch_jobs`); the pipeline claims jobs oldest-first,
downloads each (yt-dlp for watch pages, plain HTTPS for direct
files), and runs it like a session:

```
export FETCH_QUEUE_URL=https://unwritten-cloud-signer.heartmade.workers.dev
pipeline/run_pipeline.py --fetch work/cloud [--max N] [--retry-failed]
```

Each job lands in `work/cloud/fetch_<jobid>/` as
`unwritten_lesson_<stamp>.mp4` plus `source.json` (URL, title, job
id, and `join_to` — the hub session the link continues, if any),
then runs into its own `work/cloud/<title>__<jobid>/` dir.
When the pipeline succeeds, the lesson is uploaded to the Stream
library (create the video, PUT the bytes, wait for finished) and
recorded in `cloud_state.json` — so `--cloud` skips it and the
publish loop picks it up for the in-app hub like any cloud lesson.
The video id is stored in the session dir (`upload.json`) before
the bytes go up, so a retry reuses it instead of minting a
duplicate. The job is closed with that id (`done {session,
videoId}`): a link queued to continue a session (an app's *Add a
part → Link*, `joinTo`) is tied on by the signer as that session's
next part. Uploads need the direct library key
(`CLOUD_LIBRARY_ID` + `CLOUD_LIBRARY_KEY` in `.env` — the proxy
cannot stand in); without it `--fetch` fails fast before claiming.
Failed jobs stay failed until `--retry-failed` reclaims them — after
any pending work, least recently tried first, each job once per run
(one that fails again is put back as failed and the run ends, never
loops) — and a claim older than two hours counts as a crashed worker
and comes back. A resumed session never reuses a `.part` sidecar
left by a killed download: it downloads again. `FETCH_QUEUE_TOKEN` overrides the signer token (else
`CLOUD_PROXY_TOKEN`, else line 1 of the pool file);
`CLOUD_PROXY_URL` (or the baked signer `https://unwritten-cloud-signer.heartmade.workers.dev` by default) stands in for the queue URL. `run_cloud.sh` runs
`--fetch` ahead of `--cloud` on every run (queue defaults to the baked signer so a fresh clone never stalls).

## Session parts

A lesson filmed in several takes, uploaded in pieces, or fetched from
more than one link can read as one overall session in the hub. The
pipeline does not change for it: **each part is processed and
published on its own** (its own transcript, write-up, corrections and
clips), and the signer ties them together (`session_parts`, see
`app/cloud-signer/README.md`). The hub detail then reads as one —
the parts' write-ups in order under "Part N" headings, corrections
and chapters tagged with their part, playback running part to part.
A part not yet published shows as still processing. There is no
combined transcript or cross-part write-up yet; each part's
corrections are anchored to its own video.

## Races and reruns

`--cloud` and `--fetch` take an exclusive lock on the work root
(`.lock`): a second run on the same root — cron or manual — skips
with a message instead of processing videos twice. (`run_cloud.sh`
adds its own `flock` so cron never overlaps itself.) Every step is
idempotent: reruns skip `done`/`ignored` state, resume downloads
from the `.part` sidecar discipline, reuse stored upload ids, and
republish through the hub upsert, so a crash loses at most the
in-flight video. The cron loop publishes with `--if-changed`: a
session posts once per version of its artifacts (fingerprints in
`work/cloud/hub_published.json`), so a session deleted from the hub
in an app stays deleted, and one whose Stream video is gone (404) is
never published. One rule: run `--cloud` on exactly one machine —
the state file is local, so two machines would each process every
new video.

Python deps live in `.venv` (faster-whisper); the runner re-invokes
the transcription stage under it when present. Everything else is
stdlib + ffmpeg + Muse calls.

## Stage notes

- **Transcription is Meta speech-to-text by default.** With
  `MODEL_API_KEY`, `transcribe.py` sends mono 24 kHz WAV to Muse
  Voice Transcribe (DIARIZATION: turn timestamps plus speaker
  labels, which land in `segments.json`). Audio over 10 minutes is
  split into <=10-minute chunks first (the API cap); a cut may
  garble a word at a boundary. Without the key — or with
  `UNWRITTEN_TRANSCRIBE=local` — local faster-whisper (base model,
  int8, CPU) runs instead and nothing leaves the machine;
  `UNWRITTEN_TRANSCRIBE=api` forces the API and fails loudly
  without a key. `UNWRITTEN_WHISPER_MODEL=small` trades speed for
  accuracy on the local path. Negations matter: a dropped "don't"
  inverts a step, so the write-up's imperatives get checked back
  against this transcript.
- **The Model API is opt-in per run.** Transcription, video
  understanding, and SAM segmentation use `MODEL_API_KEY` when it
  is set; without it the pipeline takes the keyless path (local
  Whisper, still frames, plain clips) and nothing leaves the
  machine. With it, the lesson audio goes up for transcription and
  the lesson video — picture and voice, by the owner's explicit
  choice — for the write-up, plus each correction clip for its
  highlight; Files uploads are deleted afterwards.
- **The write-up** is `draft_writeup.py`: a polished, sectioned
  document in the mentor's voice; the transcript is the spine, and
  what it leaves unsaid is filled in from the lesson video — never
  from outside knowledge. With `MODEL_API_KEY` set, Spark watches
  the whole video (Meta video understanding, visuals and speech; a
  non-MP4 lesson is remuxed, or transcoded to H.264/AAC when its
  codecs cannot ride in MP4, like the web's VP8 WebM takes);
  otherwise evenly spaced still frames go along (`--image`
  attachments), and without lesson media it degrades to
  transcript-only.
- **Correction highlights** ride on the clips: when the finder names
  a visible subject (`"segment"`) and `MODEL_API_KEY` is set, SAM
  3.1 tracks it through the cut clip (Meta media segmentation) and
  the runner renders `highlight-NN.mp4` — subject spotlighted, rest
  dimmed — plus `segments-NN.json` with the tracks. Any failure
  keeps the plain clip and the anchor; highlights never block a run.
- **Share-safe clips** ride alongside: with the key, each video clip
  also goes through SAM as "face"; when faces are tracked the runner
  renders `redacted-NN.mp4` with opaque covers (plain clips show
  mostly hands; no face, no file). Recognition on the API
  transcription path is biased by `UNWRITTEN_ASR_KEYWORDS` /
  `UNWRITTEN_ASR_LANGUAGES` when set — feed them the vocabulary of
  past write-ups.
- **The poster** is one representative frame (`poster.jpg`, shown by
  the optional page): with the key, Spark names the best moment;
  otherwise the midpoint frame. Never blocks a run.
- **Chapters** are a video-understanding timeline (`chapters.json`,
  shown by the optional page): key + MP4 only, never blocks a run.
- **Outputs are schema-first.** The finder and the write-up return
  validated JSON (`prompts/*_schema.json`, enforced via
  `--output-schema` on the `muse` path) and render markdown
  deterministically; malformed output fails loudly instead of
  shipping a guess.
- **Prompt caching for `--cloud` batches.** Direct API calls carry a
  stable `prompt_cache_key` per use case and log the cached-token
  hit rate; sequential backlog runs reuse the same prefixes.
- **The corrections** are `find_corrections.py`: the timestamped
  transcript + `prompts/correction_finder.md` into Muse Spark. Each
  hit is a technique: timestamp, the mentor's exact words, what they were
  correcting. `run_pipeline.py` renders `corrections.md` and cuts each
  moment from the lesson video with ffmpeg (segment window capped
  at a 60 s beat, padded 2 s on both sides; a failed cut keeps the
  timestamp anchor and says so — it never blocks the run).
- **Clips need the lesson file.** A transcript-only run produces
  anchored corrections without clips; the anchors carry the timestamps
  either way.

## Deferred on purpose (TODO)

- **Teach-back QA.** Restart from only `writeup.md` in a fresh call,
  have the model "cook" it back step by step, and diff against the
  video: every hesitation or invention is a write-up gap. The retired
  apprentice idea, repurposed as a write-up linter. Held off until
  the current flow is proven polished — do not build yet.

## Not in this pipeline

- **The page/guide** (`pipeline/make_page.py`) — optional, later, for a
  recipient who wasn't in the room. It assembles `writeup.md` +
  `corrections.json` + `clips/` into one HTML page. The core never
  calls it and nothing in the core depends on it.
- **The retired apprentice design** — `harness/`,
  `pipeline/sam_overlay.py`, `pipeline/frames.py`,
  `prompts/apprentice*`. Cut Oct 27, 2026; kept in the tree as retired
  experiments, invoked by nothing here.
- **The apps** (`app/`) — Unwritten Craft on web, Android, and iOS:
  home opens on the hub sessions with Record and Upload above them.
  An ordinary phone camera produces the same lesson file and works
  just as well.
