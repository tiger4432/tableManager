-- ============================================================================
-- FORWARD: retire the deprecated plan tables `map_doe` and `map_doe_source`.
--
-- Approved by the product owner 2026-08-13. Both tables lost their last writer
-- at M2.6 (2026-07-27), when the DOE became the `map_split_registry` row itself
-- (one value = one row). Their declarations, their index entries and their
-- `table_config.json.sample` members were removed in the same change, so a
-- deploy run of `install_product_tables.py` can no longer re-add them and the
-- config watcher can no longer re-CREATE them.
--
-- ---------------------------------------------------------------------------
-- READ THIS BEFORE RUNNING - a .sql file cannot check WHICH database it is in.
--
-- This script guards the CONTENT of the tables, not the identity of the server.
-- Nothing in here can tell production from a dev copy. Confirm the target
-- yourself, in the same session, before you paste anything:
--
--     SELECT current_database(), current_user, inet_server_addr();
--
-- and run with errors fatal, e.g.
--
--     psql -v ON_ERROR_STOP=1 -d <db> -f server/migrations/drop_map_doe_tables.sql
--
-- The guard and the DROPs live in ONE DO block on purpose: psql runs each
-- top-level statement in its own transaction, so a guard in a separate block
-- would raise, print red, and the DROPs underneath would still execute.
-- ---------------------------------------------------------------------------
--
-- REFUSAL: if either table still holds a row, this script aborts and drops
-- NOTHING. Both dev copies on the build box measured 0 rows on 2026-08-13, but
-- a dev copy's zero is not evidence about production - that is the entire
-- reason the refusal exists. If it fires, export the rows (they are readable;
-- the column set is in drop_map_doe_tables_reverse.sql) and decide deliberately.
--
-- REVERSE: server/migrations/drop_map_doe_tables_reverse.sql recreates both
-- tables, empty, with the column set and indexes taken from the live database.
-- It cannot bring rows back. There is no undo for the data - only for the shape.
-- ============================================================================

DO $$
DECLARE
    n_doe     bigint := NULL;   -- NULL means "table already absent"
    n_source  bigint := NULL;
    n_side    bigint;
BEGIN
    IF to_regclass('public.map_doe') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM public.map_doe' INTO n_doe;
    END IF;
    IF to_regclass('public.map_doe_source') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM public.map_doe_source' INTO n_source;
    END IF;

    RAISE NOTICE 'target database : %', current_database();
    RAISE NOTICE 'map_doe         : %',
        CASE WHEN n_doe IS NULL THEN 'ABSENT (nothing to drop)' ELSE n_doe::text || ' row(s)' END;
    RAISE NOTICE 'map_doe_source  : %',
        CASE WHEN n_source IS NULL THEN 'ABSENT (nothing to drop)' ELSE n_source::text || ' row(s)' END;

    IF COALESCE(n_doe, 0) > 0 OR COALESCE(n_source, 0) > 0 THEN
        -- One dollar-quoted literal, not several adjacent ones: plpgsql's RAISE
        -- takes a single string literal and rejects SQL literal concatenation
        -- (the first draft of this file did exactly that and would not parse).
        RAISE EXCEPTION $msg$REFUSING TO DROP - the retired plan tables are NOT empty in "%".
    map_doe        : % row(s)
    map_doe_source : % row(s)
Nothing was dropped. This database still holds DOE data that no code reads any
more, which means it exists ONLY here. Export it, or migrate it into
map_split_registry, and re-run. Do not "fix" this by deleting the rows without
reading them first.$msg$,
            current_database(),
            COALESCE(n_doe::text, 'ABSENT'),
            COALESCE(n_source::text, 'ABSENT');
    END IF;

    -- Layering / history rows scoped to these table NAMES are deliberately NOT
    -- touched. On the build box's `assy_manager` there were 110 + 100 cell_sources,
    -- 110 + 100 cell_overwrites and 288 + 229 audit_logs rows naming the two tables
    -- while the tables themselves held 0 rows - i.e. already orphaned before this
    -- drop. audit_logs is history and has to outlive what it describes; the two
    -- layering tables are dead weight, but deleting a user's pinned cells is a
    -- separate decision needing its own approval. Counted and reported, not removed.
    IF to_regclass('public.cell_sources') IS NOT NULL THEN
        EXECUTE $q$SELECT count(*) FROM public.cell_sources
                    WHERE table_name IN ('map_doe','map_doe_source')$q$ INTO n_side;
        RAISE NOTICE 'orphan cell_sources rows naming these tables    : % (left in place)', n_side;
    END IF;
    IF to_regclass('public.cell_overwrites') IS NOT NULL THEN
        EXECUTE $q$SELECT count(*) FROM public.cell_overwrites
                    WHERE table_name IN ('map_doe','map_doe_source')$q$ INTO n_side;
        RAISE NOTICE 'orphan cell_overwrites rows naming these tables : % (left in place)', n_side;
    END IF;
    IF to_regclass('public.audit_logs') IS NOT NULL THEN
        EXECUTE $q$SELECT count(*) FROM public.audit_logs
                    WHERE table_name IN ('map_doe','map_doe_source')$q$ INTO n_side;
        RAISE NOTICE 'audit_logs rows naming these tables             : % (kept: history)', n_side;
    END IF;

    -- Empty (or already gone) -> drop. RESTRICT, not CASCADE: both tables were
    -- measured to have no inbound foreign key and no dependent view, so anything
    -- CASCADE would have to remove is something this migration did not foresee and
    -- must not silently destroy.
    DROP TABLE IF EXISTS public.map_doe RESTRICT;
    DROP TABLE IF EXISTS public.map_doe_source RESTRICT;

    -- Worded as a state, not as an action: this block is idempotent, so on a
    -- second run nothing was dropped and saying "dropped" would be a lie.
    RAISE NOTICE 'done: map_doe and map_doe_source do not exist in "%"', current_database();
END
$$;
