-- ============================================================================
-- REVERSE of server/migrations/drop_graph_storage.py (ruling R-2026-08-14-H).
--
-- Recreates `graph_nodes`, `graph_edges` and `graph_sync_state` EMPTY, with the
-- column set and indexes taken from server/database/models.py (GraphNode ~467,
-- GraphEdge ~484, GraphSyncState ~512).
--
-- IT RESTORES THE SHAPE. IT CANNOT BRING ROWS BACK. There was no archive - the
-- owner re-confirmed that in the ruling, on the grounds that every row here was
-- DERIVED from a source table that still exists and was never touched. The one
-- value that was not derived is `graph_sync_state.last_outbox_id`, the
-- materializer's cursor; a revived branch must do a full resync rather than
-- resume from a number this script cannot know.
--
-- ---------------------------------------------------------------------------
-- READ THIS BEFORE RUNNING - a .sql file cannot check WHICH database it is in.
-- Confirm the target yourself, in the same session, before you paste anything:
--
--     SELECT current_database(), current_user, inet_server_addr();
--
-- and run with errors fatal, e.g.
--
--     psql -v ON_ERROR_STOP=1 -d <db> -f server/migrations/drop_graph_storage_reverse.sql
-- ---------------------------------------------------------------------------
--
-- 🔴 THIS FILE ALONE DOES NOT REVIVE THE GRAPH BRANCH. Five code changes closed
-- the paths that used to fill these tables; the full list is in the module
-- docstring of drop_graph_storage.py under REVERSE. Running only this script
-- leaves three empty tables that nothing writes and nothing reads - which shows
-- on screen as "the graph is empty" instead of "the graph is retired", the exact
-- dishonest state the ruling's execution order was written to prevent.
--
-- `IF NOT EXISTS` throughout: this is idempotent and will not clobber a table
-- that somehow survived.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.graph_nodes (
    id            bigserial PRIMARY KEY,
    label         varchar(100) NOT NULL,
    -- multi-column identities are normalised into a "|"-joined string
    -- (graph_materializer.compose_identity)
    identity_key  varchar      NOT NULL,
    props         jsonb,
    created_at    timestamptz DEFAULT now(),
    updated_at    timestamptz DEFAULT now()
);

-- (label, identity_key) UNIQUE — the physical substance of exact-match MERGE.
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_nodes_identity
    ON public.graph_nodes (label, identity_key);


CREATE TABLE IF NOT EXISTS public.graph_edges (
    id              bigserial PRIMARY KEY,
    type            varchar(100) NOT NULL,
    from_node       bigint       NOT NULL,
    to_node         bigint       NOT NULL,
    props           jsonb,
    -- edge provenance = the graph extension of cell layering
    source_name     varchar      NOT NULL DEFAULT 'unknown',
    source_row_ref  varchar,        -- "table_name:row_id"
    updated_by      varchar,
    event_time      timestamptz,
    created_at      timestamptz DEFAULT now()
);

-- k-hop traversal must be a chain of index lookups; no unindexed edge access.
CREATE INDEX IF NOT EXISTS idx_graph_edges_from_type
    ON public.graph_edges (from_node, type);
CREATE INDEX IF NOT EXISTS idx_graph_edges_to_type
    ON public.graph_edges (to_node, type);
-- Idempotent UPSERT key. `source_name` is NOT NULL with a default precisely so
-- that NULL cannot be used to slip duplicates past this unique index.
CREATE UNIQUE INDEX IF NOT EXISTS idx_graph_edges_upsert
    ON public.graph_edges (from_node, type, to_node, source_name);
-- Retarget path: find the stale edges a given source row once asserted.
CREATE INDEX IF NOT EXISTS idx_graph_edges_row_ref
    ON public.graph_edges (source_row_ref);


-- The materializer's own outbox cursor. Single row, id = 1 by convention.
-- Deliberately recreated EMPTY: see the note about last_outbox_id above.
CREATE TABLE IF NOT EXISTS public.graph_sync_state (
    id              integer PRIMARY KEY,
    last_outbox_id  bigint NOT NULL DEFAULT 0,
    updated_at      timestamptz DEFAULT now()
);
