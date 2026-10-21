-- REVERSE of add_file_ingestion_log_stamp.sql.
--
-- 🔴 Revert the code FIRST (the commit that declared these columns) and restart: while the model declares them, the
-- boot schema sync adds them back at the next start, and a process still running the old model fails every read
-- of this table on the dropped columns.
--
--   psql "$DATABASE_URL" -f server/migrations/add_file_ingestion_log_stamp_reverse.sql
--
-- Loses only the checklist's stamps; the reverted code does not read them.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS file_mtime;
ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS file_size;
