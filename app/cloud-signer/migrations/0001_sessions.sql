-- Unwritten Craft — hub store (Cloudflare D1, which is SQLite).
--
-- One row per published lesson, keyed by the Stream video id the apps
-- already carry in their cloud links. The pipeline pushes finished runs
-- here (pipeline/publish.py); the recorders read it back for the
-- in-app hub. Video bytes stay in Stream — only playback URLs and the
-- text artifacts (write-up, corrections, chapters, glossary) live here.
CREATE TABLE IF NOT EXISTS sessions (
  video_id TEXT PRIMARY KEY,
  library_id TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  lesson_date TEXT NOT NULL DEFAULT '',
  hls_url TEXT NOT NULL DEFAULT '',
  mp4_url TEXT NOT NULL DEFAULT '',
  writeup_md TEXT NOT NULL DEFAULT '',
  corrections_json TEXT NOT NULL DEFAULT '[]',
  chapters_json TEXT NOT NULL DEFAULT '[]',
  glossary_json TEXT NOT NULL DEFAULT '{}',
  published_at INTEGER NOT NULL DEFAULT 0
);
