-- ============================================================================
-- REVERSE of server/migrations/drop_map_doe_tables.sql.
--
-- Recreates `map_doe` and `map_doe_source` EMPTY, with the exact column set,
-- defaults, primary key and indexes they had in the live database on
-- 2026-08-13. The definitions were read out of `information_schema.columns` /
-- `pg_indexes` on the running `assy_manager`, NOT transcribed from the
-- `product_tables.py` declaration the same change deleted - a declaration says
-- what the installer would create, and the physical table is what actually
-- existed (e.g. `band_seq` and `qty_total` are `double precision` here because
-- they were declared "number", and the seven `row_id`/`created_at`/graph-sync
-- columns are the generic dynamic-table preamble that no declaration mentions).
--
-- WHAT THIS CANNOT DO: bring rows back. The forward migration refuses to run
-- against a non-empty table precisely because nothing here can undo a delete.
-- If you need the data, restore from a backup, not from this file.
--
-- A .sql file cannot check WHICH database it is in. Before running:
--
--     SELECT current_database(), current_user, inet_server_addr();
--     psql -v ON_ERROR_STOP=1 -d <db> -f server/migrations/drop_map_doe_tables_reverse.sql
--
-- Recreating the tables is NOT enough to make them work again: the product
-- declarations were removed from `server/product_tables.py` and from
-- `server/config/sample/table_config.json.sample`, and the two index entries from
-- `server/scripts/setup_transfer_plan_indexes.py`. Without a declaration in the
-- site's live `table_config.json` the generic table API does not know these
-- tables exist, so a bare CREATE leaves them invisible to every route. Restore
-- the code side too (git revert of the retirement commit), or re-add the
-- declaration by hand, before expecting anything to read them.
--
-- Idempotent: IF NOT EXISTS throughout, so running it twice changes nothing.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.map_doe (
    "row_id" character varying NOT NULL,
    "business_key_val" character varying,
    "created_at" timestamp with time zone DEFAULT now(),
    "updated_at" timestamp with time zone DEFAULT now(),
    "is_graph_synced" boolean,
    "needs_graph_rollback" boolean,
    "graph_synced_at" timestamp with time zone,
    "doe_key" character varying,
    "ref_table" character varying,
    "map_key" character varying,
    "doe_value" character varying,
    "band_seq" double precision,
    "stack_band" character varying,
    "qty_total" double precision,
    "knobs" character varying,
    "note" character varying,
    "updated_by" character varying,
    "eventtime" character varying,
    CONSTRAINT map_doe_pkey PRIMARY KEY (row_id)
);
CREATE INDEX IF NOT EXISTS idx_map_doe_bk ON public.map_doe USING btree (business_key_val, row_id);
CREATE INDEX IF NOT EXISTS idx_map_doe_updated ON public.map_doe USING btree (updated_at, row_id);
CREATE INDEX IF NOT EXISTS ix_map_doe_business_key_val ON public.map_doe USING btree (business_key_val);
CREATE INDEX IF NOT EXISTS ix_map_doe_created_at ON public.map_doe USING btree (created_at);
CREATE INDEX IF NOT EXISTS ix_map_doe_is_graph_synced ON public.map_doe USING btree (is_graph_synced);
CREATE INDEX IF NOT EXISTS ix_map_doe_needs_graph_rollback ON public.map_doe USING btree (needs_graph_rollback);
CREATE INDEX IF NOT EXISTS ix_map_doe_row_id ON public.map_doe USING btree (row_id);
CREATE INDEX IF NOT EXISTS ix_map_doe_updated_at ON public.map_doe USING btree (updated_at);

CREATE TABLE IF NOT EXISTS public.map_doe_source (
    "row_id" character varying NOT NULL,
    "business_key_val" character varying,
    "created_at" timestamp with time zone DEFAULT now(),
    "updated_at" timestamp with time zone DEFAULT now(),
    "is_graph_synced" boolean,
    "needs_graph_rollback" boolean,
    "graph_synced_at" timestamp with time zone,
    "source_key" character varying,
    "ref_table" character varying,
    "map_key" character varying,
    "doe_value" character varying,
    "band_seq" double precision,
    "source_lot" character varying,
    "source_slot" character varying,
    "qty" double precision,
    "note" character varying,
    "updated_by" character varying,
    "eventtime" character varying,
    CONSTRAINT map_doe_source_pkey PRIMARY KEY (row_id)
);
CREATE INDEX IF NOT EXISTS idx_map_doe_source_bk ON public.map_doe_source USING btree (business_key_val, row_id);
CREATE INDEX IF NOT EXISTS idx_map_doe_source_updated ON public.map_doe_source USING btree (updated_at, row_id);
CREATE INDEX IF NOT EXISTS ix_map_doe_source_business_key_val ON public.map_doe_source USING btree (business_key_val);
CREATE INDEX IF NOT EXISTS ix_map_doe_source_created_at ON public.map_doe_source USING btree (created_at);
CREATE INDEX IF NOT EXISTS ix_map_doe_source_is_graph_synced ON public.map_doe_source USING btree (is_graph_synced);
CREATE INDEX IF NOT EXISTS ix_map_doe_source_needs_graph_rollback ON public.map_doe_source USING btree (needs_graph_rollback);
CREATE INDEX IF NOT EXISTS ix_map_doe_source_row_id ON public.map_doe_source USING btree (row_id);
CREATE INDEX IF NOT EXISTS ix_map_doe_source_updated_at ON public.map_doe_source USING btree (updated_at);
