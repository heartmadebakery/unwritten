-- Unwritten Craft — session parts (Cloudflare D1, which is SQLite).
--
-- One row per Stream video tied into a multi-part session: a lesson
-- filmed in several takes, uploaded in pieces, or fetched from more
-- than one link reads in the hub as one overall session. group_id is
-- opaque ("grp_..."); position orders the parts. A row may name a
-- video the pipeline has not published yet — the apps tie a take as
-- soon as its upload has an id — and the hub counts it as still
-- processing until it is. Untied videos have no row at all.
CREATE TABLE IF NOT EXISTS session_parts (
  video_id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL,
  position INTEGER NOT NULL DEFAULT 0,
  linked_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_session_parts_group ON session_parts(group_id, position);
-- A queued link can continue a session: the worker ties the fetched
-- video onto join_to when the pipeline reports the job done.
ALTER TABLE fetch_jobs ADD COLUMN join_to TEXT NOT NULL DEFAULT '';
