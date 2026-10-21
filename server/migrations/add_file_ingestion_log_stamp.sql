-- The file as it was when a log row's read came to its answer (owner 10-21, the checklist): file_ingestion_logs's
-- file_mtime and file_size. A row with the file's (mtime, size) checks it - the watcher does not read it again.
--
-- NOT REQUIRED: the boot schema sync (models.sync_dynamic_tables_schema, through SCHEMA_SYNCED_SYSTEM_TABLES) adds
-- them at the start of the server, the watcher and the chain worker, under the DDL lock limit. This file is the
-- by-hand way, for a database to be ready before a restart.
--
--   psql "$DATABASE_URL" -f server/migrations/add_file_ingestion_log_stamp.sql
--
-- Nullable, no default: an ADD COLUMN that rewrites no row. Rows written before stay null - unchecked - until
-- scripts/stamp_read_files.py stamps the ones whose file has not changed since (RUN.md, before the restart).
-- Reverse: add_file_ingestion_log_stamp_reverse.sql.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS file_mtime TIMESTAMP WITH TIME ZONE;
ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS file_size BIGINT;
