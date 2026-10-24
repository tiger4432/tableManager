-- Which columns a file's read changed, on how many rows (lead 10-23): file_ingestion_logs.columns_changed, JSON text
-- {column: rows}. The file screen's Result counts say «Changed in <column>» under Changed.
--
-- NOT REQUIRED: the boot schema sync (models.sync_dynamic_tables_schema, through SCHEMA_SYNCED_SYSTEM_TABLES) adds
-- it at the start of the server, the watcher and the chain worker, under the DDL lock limit. This file is the
-- by-hand way, for a database to be ready before a restart.
--
--   psql "$DATABASE_URL" -f server/migrations/add_file_ingestion_log_columns_changed.sql
--
-- Nullable, no default: an ADD COLUMN that rewrites no row. Rows written before stay null.
-- Reverse: add_file_ingestion_log_columns_changed_reverse.sql.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs ADD COLUMN IF NOT EXISTS columns_changed VARCHAR;
