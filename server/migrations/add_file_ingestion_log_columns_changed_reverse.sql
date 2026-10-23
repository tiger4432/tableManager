-- Reverse of add_file_ingestion_log_columns_changed.sql. Run it only after the code that writes the column is
-- reverted - a running watcher writes it on every read.

SET lock_timeout = '20s';

ALTER TABLE file_ingestion_logs DROP COLUMN IF EXISTS columns_changed;
