CREATE TABLE IF NOT EXISTS intersections (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cameras (
 id TEXT PRIMARY KEY, intersection_id TEXT NOT NULL REFERENCES intersections(id), config TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS videos (
 id TEXT PRIMARY KEY, intersection_id TEXT NOT NULL REFERENCES intersections(id),
 camera_id TEXT NOT NULL REFERENCES cameras(id), filename TEXT NOT NULL, storage_path TEXT NOT NULL,
 status TEXT NOT NULL, progress REAL NOT NULL DEFAULT 0, stage TEXT NOT NULL DEFAULT 'queued',
 error TEXT, metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS videos_intersection ON videos(intersection_id,created_at);
CREATE TABLE IF NOT EXISTS frames (
 video_id TEXT NOT NULL REFERENCES videos(id), frame_index INTEGER NOT NULL, timestamp REAL NOT NULL,
 inference_ms REAL NOT NULL, object_count INTEGER NOT NULL, PRIMARY KEY(video_id,frame_index)
);
CREATE TABLE IF NOT EXISTS tracks (
 video_id TEXT NOT NULL REFERENCES videos(id), track_id INTEGER NOT NULL, class TEXT NOT NULL,
 first_seen REAL NOT NULL, last_seen REAL NOT NULL, summary TEXT NOT NULL,
 PRIMARY KEY(video_id,track_id)
);
CREATE TABLE IF NOT EXISTS trajectory_points (
 video_id TEXT NOT NULL, track_id INTEGER NOT NULL, timestamp REAL NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(video_id,track_id,timestamp), FOREIGN KEY(video_id,track_id) REFERENCES tracks(video_id,track_id)
);
CREATE INDEX IF NOT EXISTS trajectory_time ON trajectory_points(video_id,timestamp);
CREATE TABLE IF NOT EXISTS traffic_metrics (
 video_id TEXT NOT NULL REFERENCES videos(id), timestamp REAL NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(video_id,timestamp)
);
CREATE TABLE IF NOT EXISTS safety_events (
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id), timestamp REAL NOT NULL,
 severity TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS safety_time ON safety_events(video_id,timestamp);
CREATE TABLE IF NOT EXISTS forecasts (
 id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(id), payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, intersection_id TEXT REFERENCES intersections(id),
 payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO schema_migrations VALUES (1);
