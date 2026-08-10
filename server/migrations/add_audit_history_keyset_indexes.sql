-- Indexes the row/cell audit-history keyset pagination needs.
--
-- Declared in `server/database/models.py` (AuditLog.__table_args__) so that NEW
-- databases get them from `create_all`. `create_all` never adds an index to a
-- table that already exists, so every EXISTING database - production included -
-- needs this file run once.
--
-- WHY THEY ARE NOT OPTIONAL. `LIMIT` alone does not bound the database's work.
-- Measured on the isolated `assy_qa` copy 2026-08-11, one row inflated to
-- 300,019 audit entries inside a 1,131,008-row `audit_logs`, with `LIMIT 201`
-- ALREADY IN THE QUERY:
--
--   before  Parallel Bitmap Heap Scan on ix_audit_logs_row_id + top-N sort of
--           all 300,019 matches        ->  9,421 buffers, 121.6 ms
--   after   Index Scan, stops at 201   ->    207 buffers,   0.4 ms
--
-- The LIMIT removed 54 MB of rows from the wire and from pydantic. It did NOT
-- stop the scan from growing with everything ever written to that row. Only
-- these do.
--
-- The second index exists because the first one leaves `column_name` as a
-- Filter inside the row's range, so the cell tab costs "walk until the page is
-- full". That is cheap for a column written on every ingest and unbounded for a
-- column a human touched twice. Measured on a column with ONE entry inside that
-- 300,019-deep row: 9,421 buffers / 117.7 ms with only the row index (the
-- planner abandons it and falls back to the bitmap scan), 5 buffers / 0.09 ms
-- with this one.
--
-- ASC, although the query sorts `timestamp DESC, id DESC`: a btree is scanned
-- backwards at the same cost. Measured both ways on the same data - same
-- `Index Scan Backward`, same `Index Cond` (including the row-value keyset
-- bound), same buffers, same 91 MB. ASC is what `models.py` can declare without
-- raw SQL, so one declaration covers PostgreSQL and the SQLite test database.
--
-- SIZE, measured twice on `assy_qa`. On the real 210,196-row snapshot after the
-- probe data was removed and the table was VACUUM FULLed: 19 MB + 20 MB, i.e.
-- ~195 bytes per audit row across the pair. On the 1,131,008-row inflated
-- fixture: 91 MB + 101 MB, ~170 B/row. Budget ~200 B per audit row; the width
-- is driven by `row_id` (a 36-char UUID) repeated in both indexes.
--
-- CONCURRENTLY so this can run against the live stack without taking a write
-- lock. It cannot run inside a transaction block: invoke each statement on its
-- own (psql runs each top-level statement in its own transaction only with
-- autocommit on - `psql -f` does, a wrapping BEGIN does not).
--
--   psql "$DATABASE_URL" -f server/migrations/add_audit_history_keyset_indexes.sql
--
-- If a CREATE INDEX CONCURRENTLY is interrupted it leaves an INVALID index
-- behind that costs writes and serves no reads. Check afterwards:
--
--   SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
--   WHERE NOT i.indisvalid AND c.relname LIKE 'idx_audit_%_history';
--
-- and DROP + re-run any row it returns.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_row_history
    ON audit_logs (table_name, row_id, "timestamp", id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_cell_history
    ON audit_logs (table_name, row_id, column_name, "timestamp", id);
