-- REVERSE of add_file_ingestion_transaction_id.sql.
--
-- 🔴 Revert the code FIRST (the commit that declared these columns) and restart: while the model declares them, the
-- boot schema sync adds them back at the next start, and a process still running the old model fails every read
-- of these tables on the dropped columns.
--
--   psql "$DATABASE_URL" -f server/migrations/add_file_ingestion_transaction_id_reverse.sql
--
-- Loses only each file's transaction; a resumed read after it writes under a new one.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS transaction_id;
ALTER TABLE file_ingestion_checkpoints DROP COLUMN IF EXISTS transaction_id;
