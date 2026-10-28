# Changelog

All notable changes to Unwritten Craft, newest first. Dates are
Pacific Time. **Rule: every commit to `main` adds its entry here, in
the same commit.** Entries cite the commit they describe; this file
was compiled retroactively on Oct 27, 2026 from the full commit
history (30 commits) and is maintained in the open from then on.

## 2026-10-27

### Added
- **This changelog**, compiled retroactively from the commit history.
- **Correction finder** — `pipeline/find_corrections.py` +
  `prompts/correction_finder.md` (Muse Spark): surfaces every moment
  the teacher corrected the beginner, anchored to its timestamp and
  her exact words. (`b506a24`)
- **Core test** — a fictional lesson fixture with planted ground truth
  (6 corrections, 4 distractors, fidelity traps) and its scored
  results in `docs/core-test-2026-10-27.md`: finder caught 6/6
  corrections with 0 false alarms (keyword-regex baseline: precision
  0.26, missed the buried correction); write-up audit clean — no
  invented oven temperature or bake time, "two pinches" kept, all
  technique negations preserved. (`b506a24`)
- **Machine setup** — pinned Python requirements and an idempotent
  `setup.sh`; a local HTTPS server for the recorder. (`c341af1`,
  `eca35ef`)

### Changed
- **The code now follows the three core things.** `run_pipeline.py`
  rewritten: one ordinary lesson file in → transcribe → write-up →
  corrections, with each correction cut from the lesson into `clips/`.
  It calls `find_corrections.py` (the old runner never did), and
  success requires a write-up + corrections list — not a page.
  `ingest.py` classifies by extension only (the lesson is the largest
  media file); `transcribe.py` also writes the timestamped transcript;
  the write-up drafter's recorder-era `--wisdom` input and
  session-protocol prompt rules are removed; `docs/PIPELINE.md`
  rewritten to match. (`03172d7`)
- **Naming made consistent** — what the docs call the write-up is what
  the code calls it: `draft_card.py` → `draft_writeup.py`,
  `card_drafter.md` → `writeup_drafter.md`, `handiton.py` →
  `make_page.py`, `sample_card*.md` → `sample_writeup*.md`, with every
  living reference updated and the old files deleted. (`b00ddf1`)
- **Framing** — "learn what is of value" supersedes "teach what must
  not disappear" in the README and the submission draft. (`25e04d3`)
- **Recorder redesign** (before the design was cut later the same
  day): a young-apprentice flow and a warmer page; the web recorder
  became an installable PWA; the Android APK was rebuilt on the new
  toolchain. (`f76f922`, `0482fc5`, `1b6d9de`)

### Removed
- **The elaborate design, cut from the product.** Blind AI apprentice,
  SAM overlay as hero visual, recorder protocol and step names,
  correct-once ceremony — cut after a hands-on test found the capture
  flow cumbersome and Claude/Wonder critiques showed the apprentice's
  failures were scripted defaults. README and submission draft
  rewritten to match what is actually built; **submission undecided**,
  personal use first. The cut code remains in the tree as retired
  experiments (`harness/`, `pipeline/sam_overlay.py`,
  `pipeline/frames.py`). (`7ad887b`)
- **The page, as a core output.** Demoted to optional: `make_page.py`
  assembles a guide/manual from the three core outputs later, when
  there is a recipient. Nothing in the core depends on it.
  (`b506a24`, `03172d7`)

## 2026-10-26

### Added
- **Project scaffold** — design README, boundary prompts, and the
  mechanic-test harness with a fictional sample. (`212b54e`; a
  duplicate scaffold commit `9057ff9` is the empty-repo bootstrap
  artifact.)
- **Process test on the Muse stack** — Spark drafts, Wonder
  apprentices; the earlier stack's test superseded. (`9ece9ca`)
- **ELI5 explainer video** linked from the README (hosted outside the
  repo). (`15c1408`)
- **Web recorder app** — the Pixel 2 "fake robot" apprentice recorder,
  plus the first hackathon submission draft. (`c6d9446`)
- **Session pipeline v1** — media in, card + SAM overlay + hand-it-on
  page out; synthetic end-to-end test passes the same evening.
  (`6c5eb02`, `0e3c7bb`)
- **Wisdom extraction** — the drafter captures the teacher's judgment
  in a separate section; the design made craft-agnostic by
  construction. (`dea0449`)
- **Recorder v6** — one file, three roles, every device in the room
  useful. (`4c89d86`)
- **Native Android recorder** — minSdk 26 (Pixel 2), C++ core
  (AAudio + luma/flash detection), Camera2 recording, no INTERNET
  permission; Wonder-coded in three passes, integrated and
  build-verified; APK committed, with a work log and Legion handoff
  doc. (`0c0ed9d`, `dd71dc1`)

### Changed
- **Terminology** — the artifact's units renamed on the owner's call:
  "tricks" → each correction is a **technique**; together they are
  **the Knack**. Demo title set in the owner's exact wording: "Mom's
  Bread: 4 techniques, a knack never written down." (`480b2d9`,
  `8a93a84`, `46e8751`)
- **Wisdom timing** — the wisdom Q&A moved to after the teacher's
  reaction, on Claude's approved fix. (`5494b7c`)
- Docs wording and code comments polished; a stray build file
  removed. (`7deb025`, `e2415a7`)

### Fixed
- **Silent-mic guard** — a recorder can no longer pass a session with
  a silently dead microphone unnoticed (Claude review). (`0bc8577`)
- **Correctness fixes** from Claude's first review pass — no design
  change. (`569a2d6`)
- **Wonder full-code review fixes** — recorder v6.1, pipeline honesty
  rules (stale artifacts deleted up front; a run fails unless its
  outputs were produced this run), harness hardening. Tests 9 → 16.
  (`b4f70b7`)
