-- Unwritten Craft — URL fetch queue (Cloudflare D1, which is SQLite).
--
-- One row per video URL the apps queue for the pipeline: YouTube and
-- watch pages the browser cannot download itself, listed here by the
-- recorders (POST /fetch/jobs) and claimed one at a time by the
-- pipeline machine (GET /fetch/jobs?claim=1), which downloads the
-- video (yt-dlp or direct) and runs it like any session. Terminal
-- states mirror the cloud fetcher: failed stays failed until the
-- pipeline reclaims it with ?includeFailed=1 (--retry-failed).
CREATE TABLE IF NOT EXISTS fetch_jobs (
  id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  claimed_by TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  session TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL DEFAULT 0,
  updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fetch_jobs_status ON fetch_jobs(status, created_at);
