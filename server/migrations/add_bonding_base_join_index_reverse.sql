-- REVERSE of server/migrations/add_bonding_base_join_index.sql.
--
--   psql "$DATABASE_URL" -f server/migrations/add_bonding_base_join_index_reverse.sql
--
-- Dropping this index costs nothing but the join's speed - no data lives in it, and
-- rebuilding it is one CONCURRENTLY statement. Check where you are first:
--   SELECT current_database();
--
-- CONCURRENTLY for the same reason the forward file uses it: a plain DROP INDEX
-- takes an ACCESS EXCLUSIVE lock on `bonding_log` and stalls every reader.

DROP INDEX CONCURRENTLY IF EXISTS idx_bonding_log_base_position;
