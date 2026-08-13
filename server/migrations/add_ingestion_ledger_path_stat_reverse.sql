-- REVERSE of add_ingestion_ledger_path_stat.sql.
--
-- Run this to put `file_ingestion_checkpoints` back the way it was.
--
--   psql "$DATABASE_URL" -f server/migrations/add_ingestion_ledger_path_stat_reverse.sql
--
-- 🔴 BEFORE YOU RUN IT, PUT THE FILES BACK IN MOTION. Set
-- `archive_processed_files: true` in `ingestion_settings.json` and restart the
-- watcher FIRST. Without these columns tier 1 can never hit, so a watcher that
-- is also no longer moving files will re-hash the entire `raws/` tree on every
-- sweep - correct, but 39x more expensive per sweep at this box's tree size, and
-- growing with the tree. Reversing the schema without reversing the setting is
-- the one ordering that hurts.
--
-- Dropping the columns is NOT data loss for anything but the tier-1 fast path:
-- the content signature is still the authority on "have I ingested this", and
-- `filepath` (the column being demoted back to a marker) is untouched.
--
-- The rows this migration's forward half enabled - `status = 'FAILED'` ledger
-- entries - are NOT removed. They are readable without these columns and
-- deleting them would erase failures an operator may not have seen yet. They
-- become inert once files move to `err/` again. To clear them deliberately:
--
--   DELETE FROM file_ingestion_checkpoints WHERE status = 'FAILED';
--
-- CONCURRENTLY on the drop for the same reason as the create: no write lock on
-- a table the ingestion lanes write to. Cannot run inside a transaction block.

DROP INDEX CONCURRENTLY IF EXISTS idx_fic_path_stat;

ALTER TABLE file_ingestion_checkpoints
    DROP COLUMN IF EXISTS file_size;

ALTER TABLE file_ingestion_checkpoints
    DROP COLUMN IF EXISTS file_mtime;
