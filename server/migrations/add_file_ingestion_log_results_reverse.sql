-- REVERSE of add_file_ingestion_log_results.sql.
--
-- 🔴 Revert the code FIRST (the commit that declared these columns) and restart: while the model declares them, the
-- boot schema sync adds them back at the next start, and a process still running the old model fails every read
-- of file_ingestion_logs on the dropped columns.
--
--   psql "$DATABASE_URL" -f server/migrations/add_file_ingestion_log_results_reverse.sql
--
-- Loses only the per-file results; status, error_message and the rest of each row stay.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS rows_read;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS rows_new;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS rows_changed;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS rows_unchanged;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS rows_refused;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS reader;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS source;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS reason;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS failed_at;
