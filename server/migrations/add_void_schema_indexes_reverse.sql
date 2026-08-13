-- REVERSE of add_void_schema_indexes.sql.
--
--   psql "$DATABASE_URL" -f server/migrations/add_void_schema_indexes_reverse.sql
--
-- Drops only the indexes. It does NOT drop `void_obs` or `inspection_run` and
-- does not delete a row: the tables are owned by `table_config.json`, so
-- reversing the SCHEMA is done by removing the declarations there, and
-- reversing the DATA is a decision no migration should take on someone's
-- behalf. To retire the tables completely, after this file:
--
--   1. remove the "void_obs" / "inspection_run" entries from
--      server/config/table_config.json AND .sample
--   2. restart (a declaration removed from config does not drop a table)
--   3. DROP TABLE void_obs, inspection_run;      -- deliberate, irreversible
--
-- 🔴 READ THIS BEFORE DROPPING SECTION 1. `uq_bk_void_obs` /
-- `uq_bk_inspection_run` are what MAKE `business_key_val` an identity. Without
-- them `crud.apply_batch_updates`'s conflict recovery can never fire, because
-- the `IntegrityError` it recovers from is raised BY these indexes - two
-- processes upserting one key then produce two rows with no error at all. Drop
-- them only if you are retiring the tables; do not drop them "to speed up
-- ingestion", which is the reason someone will want to.
--
-- Order matters in one direction only: sections 5-2 are pure performance and
-- may be dropped at any time, so they go FIRST. If you interrupt this file
-- part-way through, you have lost indexes and kept correctness.
--
-- CONCURRENTLY for the same reason as the forward file - no write lock on
-- tables the ingestion lane writes. Cannot run inside a transaction block.
-- `IF EXISTS` throughout, so running this twice, or against a database that
-- only got some of the forward statements, is not an error.

-- 5. area expression index (never had a consumer; safest to drop)
DROP INDEX CONCURRENTLY IF EXISTS idx_void_obs_area;

-- 4. package-layer lookup on the observations
DROP INDEX CONCURRENTLY IF EXISTS idx_void_obs_package;

-- 3. denominator lookup
DROP INDEX CONCURRENTLY IF EXISTS idx_inspection_run_layer;

-- 2. the run join
DROP INDEX CONCURRENTLY IF EXISTS idx_void_obs_run;

-- 1. 🔴 identity. See the warning above - this is the one with teeth.
DROP INDEX CONCURRENTLY IF EXISTS uq_bk_inspection_run;
DROP INDEX CONCURRENTLY IF EXISTS uq_bk_void_obs;
