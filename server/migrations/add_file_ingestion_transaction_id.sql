-- The transaction a file's read wrote under (lead 10-20): on its completion record (file_ingestion_logs), and on its
-- checkpoint (file_ingestion_checkpoints) so a read resumed after a restart writes under the same one.
--
-- NOT REQUIRED: the boot schema sync (models.sync_dynamic_tables_schema, which reaches both tables through
-- SCHEMA_SYNCED_SYSTEM_TABLES) adds them at the start of the server, the watcher and the chain worker, under the
-- DDL lock limit. This file is the by-hand way, for a database to be ready before a restart.
--
--   psql "$DATABASE_URL" -f server/migrations/add_file_ingestion_transaction_id.sql
--
-- Nullable, no default: an ADD COLUMN that rewrites no row. Rows written before stay null.
-- Reverse: add_file_ingestion_transaction_id_reverse.sql.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS transaction_id VARCHAR(64);
ALTER TABLE file_ingestion_checkpoints ADD COLUMN IF NOT EXISTS transaction_id VARCHAR(64);
