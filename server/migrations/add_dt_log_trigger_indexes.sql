-- Indexes the two dt_map REVISIT triggers need before they can be enabled.
--
-- NOT RUN. Shipped as a prerequisite, not as a change. Measured on the dev database
-- 2026-08-04: `dt_log` carries indexes on `row_id` and `business_key_val` and nothing
-- else useful here. Both revisit triggers select by a column that is not indexed:
--
--   dt_job_attribution_to_dt_map     WHERE dt_job = ?
--   eqp_frame_attribution_to_dt_map  WHERE dt_eqp = ? AND product = ?
--
-- On the 8,700-row dev fixture a sequential scan is invisible. At the project's
-- 10,000,000-row planning figure each trigger firing is a full scan of the table, and
-- the frame trigger fires once per corrected (equipment, product) row.
--
-- `business_key_val` cannot stand in for the first one. It stores
-- `<dt_job>_<dt_x>_<dt_y>`, so `dt_job` is a left-anchored prefix -- but a prefix
-- predicate only uses a plain btree under the C collation, and this database is not
-- created under it. Relying on that would be an index that works until someone reads
-- the collation. A real index on the real column is the honest form.
--
-- CONCURRENTLY so this can run against the live stack without taking a write lock.
-- It cannot run inside a transaction block: invoke each statement on its own.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dt_log_dt_job
    ON dt_log (dt_job);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dt_log_eqp_product
    ON dt_log (dt_eqp, product);

-- The retraction path selects positively what a source owns: `dt_map WHERE dt_job = ?`.
-- Without this, every retraction plan is a full scan of the map table.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dt_map_dt_job
    ON dt_map (dt_job);
