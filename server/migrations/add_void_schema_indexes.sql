-- VOID SCHEMA - the indexes `void_obs` and `inspection_run` are declared to have.
--
--   psql "$DATABASE_URL" -f server/migrations/add_void_schema_indexes.sql
--
-- 🔴 ORDER. The two TABLES are created by the platform, not by this file:
-- declaring them in `table_config.json` and calling `POST /admin/reload-configs`
-- (or restarting) runs `models.create_missing_dynamic_tables`. Run this file
-- AFTER that. It will fail with `relation "void_obs" does not exist` otherwise,
-- which is the correct and loud failure - creating the tables here by hand would
-- produce a second, divergent definition of a shape the config already owns.
--
-- Verify the tables are there first:
--   SELECT to_regclass('void_obs'), to_regclass('inspection_run');
--
-- 🔴 THIS FILE NAMES A DATABASE NOWHERE, so it cannot refuse the wrong one -
-- `psql` connects wherever you point it. Check before you run:
--   SELECT current_database();
-- (SCHEMA_CANON §3 asks a migration to refuse an unspecified DB; a `.sql` file
-- cannot, and pretending otherwise would be worse than saying so. The two
-- statements below are additive and IF NOT EXISTS, so the blast radius of a
-- wrong target is an unused index, not data.)
--
-- CONCURRENTLY on every index: a lock here is a stalled ingestion lane. It
-- cannot run inside a transaction block - `psql -f` runs each top-level
-- statement in its own transaction, and a wrapping BEGIN would break that.
--
-- If a CREATE INDEX CONCURRENTLY is interrupted it leaves an INVALID index that
-- costs writes and serves no reads. Check afterwards and DROP + re-run any row:
--
--   SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
--   WHERE NOT i.indisvalid AND c.relname LIKE '%void_obs%'
--      OR NOT i.indisvalid AND c.relname LIKE '%inspection_run%';
--
-- REVERSE: server/migrations/add_void_schema_indexes_reverse.sql
--
--
-- ================================================================
-- 1. R2 - a declared business_key OBLIGES a unique index
-- ================================================================
-- `void_obs.void_uid` and `inspection_run.run_uid` are declared business keys,
-- and SCHEMA_CANON R2 is explicit that an unindexed one is "선언이 아니라 희망":
-- `crud.apply_batch_updates`'s conflict guard recovers from `IntegrityError`,
-- and that exception is only ever raised BY this index. Without it two
-- processes writing the same key produce two rows, silently (measured window
-- 2.4 s, `add_business_key_unique_index.py`).
--
-- 🔴 SAME INDEX NAME as `server/migrations/add_business_key_unique_index.py`
-- produces (`uq_bk_<table>`), deliberately. That script builds this index for
-- every declared table and skips one that is already present BY NAME, so the
-- two files converge in either order and neither builds a duplicate. Running
-- that script instead of this section is equally correct - it additionally
-- takes a duplicate census first, which is the better tool on a database that
-- already holds rows. This section exists so a FRESH database is protected in
-- one step, since a new table has no duplicates to census.
--
-- NULLs stay legal: a plain PostgreSQL unique index treats them as distinct, so
-- the keyless rows manual grid work creates can still coexist (ruling 818c9c0).

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_bk_void_obs
    ON void_obs (business_key_val);

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_bk_inspection_run
    ON inspection_run (business_key_val);


-- ================================================================
-- 2. The join `void_obs` exists to be read through
-- ================================================================
-- "the voids of this run" is the read this schema is for, and `run_uid` has no
-- index of its own - at 10M rows that is a sequential scan per run. `row_id` is
-- the second column for R7: a capped read needs a TOTAL order, and `run_uid`
-- alone leaves ties for the planner to break differently on each refresh (the
-- /view incident, R7).

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_void_obs_run
    ON void_obs (run_uid, row_id);


-- ================================================================
-- 3. The denominator lookup
-- ================================================================
-- "was this package layer ever scanned, and when last" - the question that
-- distinguishes 'clean' from 'never scanned'. Leading with the package columns
-- so the same index also serves "every scan of this package" (prefix), and
-- `observed_at DESC` so "the latest one" is the first row rather than a sort.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_inspection_run_layer
    ON inspection_run (base_wafer_id, base_x, base_y, stack_gate,
                       observed_at DESC);


-- ================================================================
-- 4. Voids of a package layer, without going through the run
-- ================================================================
-- `void_obs` carries the package columns so it can be read on its own (the grid
-- read path never joins), and this is the index that makes that read affordable.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_void_obs_package
    ON void_obs (base_wafer_id, base_x, base_y, stack_gate, row_id);


-- ================================================================
-- 5. AREA - the expression index that replaces a stored column
-- ================================================================
-- 🔴 THE POINT OF THIS SECTION. Area is π·rx·ry. It is NOT a column, because a
-- stored derived value is the ROOT_DEFECTS '박제' root and because pass/fail
-- depends on a RECIPE threshold that changes - a stored verdict makes history
-- un-re-judgeable. The proposal answers "then how do I query 'voids larger than
-- X'" with: an expression index. This is that index, so the answer is
-- demonstrated rather than promised.
--
-- The planner only uses it for a predicate written in the SAME expression:
--
--   SELECT * FROM void_obs WHERE pi() * radius_x * radius_y > 12.5;
--
-- `pi()` and float multiplication are IMMUTABLE, which is what makes the
-- expression indexable at all.
--
-- ⚠️ IT HAS NO CONSUMER TODAY. No route and no query in this repository
-- filters on area yet, so this index is currently maintained on every write and
-- read by nothing. It is safe to SKIP this statement until the first such query
-- exists, and dropping it later costs nothing (section 5 of the reverse file).
-- It ships because the alternative it displaces - a stored `area` column - is
-- far harder to remove once written.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_void_obs_area
    ON void_obs ((pi() * radius_x * radius_y));


-- ================================================================
-- NOT DONE: TIME PARTITIONING - and why, since "from day one" was the rule
-- ================================================================
-- These tables are NOT partitioned, and that is a decision rather than an
-- omission. Adding partitioning later IS a rewrite, so it is recorded here:
--
--   a) `void_obs` has no time column to partition BY. The inspection time lives
--      on `inspection_run` (one home per fact), so partitioning the
--      observations by time would first require denormalising `observed_at`
--      onto every void row - a second home for the fact this schema was careful
--      to keep in one place.
--   b) PostgreSQL requires the partition key to be part of every UNIQUE index.
--      The identity here is `row_id` (primary key) and `business_key_val`, both
--      built by the SHARED dynamic-table definition in `models.py`. Partitioning
--      would mean changing that shared shape for two tables - i.e. new ORM
--      machinery, which this work was scoped to avoid.
--   c) `create_missing_dynamic_tables` emits a plain `CREATE TABLE`. A
--      partitioned table cannot come from it, so these two tables would need a
--      creation path no other declared table has.
--
-- The cost of that decision, stated plainly: if `void_obs` reaches a size where
-- retention needs `DROP PARTITION` rather than `DELETE`, converting it is a
-- full table rewrite plus an index rebuild. What makes that affordable-ish is
-- that nothing here depends on the table being unpartitioned; the conversion is
-- mechanical, just not online.
