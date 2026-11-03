-- Duration for hub rows: seconds, shown to the right of date.
ALTER TABLE sessions ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 0;
