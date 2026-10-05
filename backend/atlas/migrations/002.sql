ALTER TABLE videos ADD COLUMN updated_at TEXT;
UPDATE videos SET updated_at=created_at WHERE updated_at IS NULL;
INSERT INTO schema_migrations VALUES (2);
