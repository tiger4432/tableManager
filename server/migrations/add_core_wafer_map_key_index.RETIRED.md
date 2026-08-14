# RETIRED — `add_core_wafer_map_key_index.sql` (+ `_reverse.sql`)

**Retired 2026-08-14 by the F6 round** (builder rule + `align_indexes_to_declarations.py`), under the
policy ruling `R-2026-08-14-B` in `docs/process/LEDGER_RULINGS.md`. The pair being retired landed in
`4ed34a9` and was not modified afterwards.

This marker follows the discipline of the `map_doe` retirement set (`c0fb735`) and
`migrate_map_meta_to_wafer_id.RETIRED.md` (`R-2026-08-14-A` F1): a retirement leaves a durable, named
artifact next to what it retired, stating the approval, the measured reason, what the retirement
cannot undo, and the exact conditions under which the thing comes back. The archive is git.

## What they were

- `add_core_wafer_map_key_index.sql` — `CREATE INDEX CONCURRENTLY IF NOT EXISTS
  idx_core_wafer_map_map_key ON core_wafer_map (core_lot, core_slot);`
- `add_core_wafer_map_key_index_reverse.sql` — the matching `DROP INDEX CONCURRENTLY IF EXISTS`.

## Why they are retired — the file's own warning came true in the good direction

The forward file said this about itself:

> ⚠️ THE COLUMN LIST IS CONFIG-DRIVEN, so this file has an expiry condition rather than a lifetime:
> if `map_key_columns` is ever re-declared, this index stops matching the predicate and silently
> becomes dead weight. It does not fail, it just stops being used. Whoever changes that declaration
> owns this file too.

That is exactly the defect the F6 rule removes. `models.declared_key_columns` re-derives the column
list from `table_config.core_wafer_map.map_key_columns` on every build, so the index **follows** a
re-declaration instead of silently falling behind it. Keeping this file would leave **two mechanisms
producing one index**, which is the F3 hazard ("the truth in two spellings will diverge, and today
was that day") aimed at the index layer.

`core_wafer_map`'s declared key resolves to `(core_lot, core_slot)` — byte-identical to what this
file created — so the retirement changes nothing about which columns get indexed.

## What retiring them does NOT do

- **It does not drop `idx_core_wafer_map_map_key`.** That index exists on `assy_manager` and is the
  busiest index on its table (28,027 scans measured 2026-08-14, roughly one day of dev workload).
  `align_indexes_to_declarations.py` detects it **by column list, not by name**, reports
  `already covered by idx_core_wafer_map_map_key`, and creates nothing beside it.
- **It does not lose the measurements.** The forward file carried four results that exist nowhere
  else, and they now live in `docs/architecture/INDEX_POLICY.md`:
  - cell read `LIMIT 2` 3.615 ms → 0.082 ms; one-key `COUNT(*)` 3.727 ms → 0.050 ms; `GROUP BY` key
    7.899 ms → 4.782 ms (HashAgg → GroupAgg) — measured on `assy_qa`, 24,200 rows / 200 maps,
    `ANALYZE` before each plan;
  - the **negative** result for the covering variant `(core_lot, core_slot, core_y, core_x, row_id)
    INCLUDE (c_bn)`: 0.110 ms vs 0.082 ms on the cell read and the `GROUP BY` pushed back to
    HashAgg — six columns of write amplification bought with nothing;
  - `GET /api/maps/alignment/references` 0.332 s with the index vs 1.128 s without, 200 maps;
  - the reason it is neither UNIQUE nor partial: `(core_lot, core_slot)` is a **map** identity, and
    hundreds of cells share one.
- **It does not remove the ability to drop that index.** `align_indexes_to_declarations.py --reverse
  --apply` drops the declared-key index it created; for the legacy-named one, the reverse statement
  is one line and is printed by the migration's `ROLLBACK:` line before it acts.
- **No consumer is affected.** At retirement, `add_core_wafer_map_key_index` appeared in no code, no
  test, and no config — only in `docs/` prose and `agent_workspace/reports/`.

## What is NOT retired alongside it, and why

`add_bonding_base_join_index.sql`, `add_void_schema_indexes.sql` and `add_dt_log_trigger_indexes.sql`
stay. Their indexes **cannot be derived from any declaration** — package identity with an `INCLUDE`
payload, a leading column that is not the declared one plus `observed_at DESC`, an expression index,
and join predicates that live inside SQL strings in `enrichment_rules.json`. The full list with the
reason for each is `docs/architecture/INDEX_POLICY.md` §5.

## Revival conditions

1. **The rule must stop producing this index.** Concretely: `models.declared_key_columns` no longer
   returns `(core_lot, core_slot)` for `core_wafer_map` — because the tier order changed, or because
   `table_config.core_wafer_map.map_key_columns` was re-declared and the new declaration is not the
   predicate `map_overlay.build_key_filters` issues. Until then a restored copy would create a
   duplicate of an index the builder already declares.
2. **Then restore from git.**

   ```
   git show 4ed34a9:server/migrations/add_core_wafer_map_key_index.sql \
       > server/migrations/add_core_wafer_map_key_index.sql
   git show 4ed34a9:server/migrations/add_core_wafer_map_key_index_reverse.sql \
       > server/migrations/add_core_wafer_map_key_index_reverse.sql
   ```

   or, if that sha becomes inconvenient, find the deletion and take its parent:

   ```
   git log --diff-filter=D --oneline -- server/migrations/add_core_wafer_map_key_index.sql
   git show <sha>^:server/migrations/add_core_wafer_map_key_index.sql > <same path>
   ```

   **Read the restored header against the config before running it.** Its column list is a copy of a
   declaration, and a copy of a declaration is the thing this retirement was about.
