-- What a file's read came to, on its completion record (lead e390600d6): the write door's own counts, the reader,
-- the source, and for a failure its one-line reason and the frame it broke in.
--
-- NOT REQUIRED: the boot schema sync (models.sync_dynamic_tables_schema, which reaches file_ingestion_logs through
-- SCHEMA_SYNCED_SYSTEM_TABLES) adds these at the start of the server, the watcher and the chain worker, under the
-- DDL lock limit. This file is the by-hand way, for a database to be ready before a restart.
--
--   psql "$DATABASE_URL" -f server/migrations/add_file_ingestion_log_results.sql
--
-- All nullable, no default: an ADD COLUMN that rewrites no row. Rows written before stay null (the screen draws «—»).
-- Reverse: add_file_ingestion_log_results_reverse.sql.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS rows_read INTEGER;
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS rows_new INTEGER;
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS rows_changed INTEGER;
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS rows_unchanged INTEGER;
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS rows_refused INTEGER;
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS reader VARCHAR(300);
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS source VARCHAR;
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS reason VARCHAR(500);
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS failed_at VARCHAR(500);
