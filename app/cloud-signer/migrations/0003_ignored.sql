-- Unwritten Craft — ignored videos (Cloudflare D1, which is SQLite).
--
-- One row per Stream video the operator set aside as not-a-lesson:
-- the pipeline's cloud state marks it `ignored` and syncs the marker
-- here (pipeline/publish.py --sync-ignored). The in-app hub never
-- lists these (sessions exclude them, list and detail); the recorders
-- read them back for the ignored badges on the Record screen.
CREATE TABLE IF NOT EXISTS ignored_videos (
  video_id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  reason TEXT NOT NULL DEFAULT '',
  ignored_at INTEGER NOT NULL DEFAULT 0
);
