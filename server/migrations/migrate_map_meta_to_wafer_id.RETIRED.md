# RETIRED — `migrate_map_meta_to_wafer_id.py`

**Retired 2026-08-14 by ruling `R-2026-08-14-A` F1** (`docs/process/LEDGER_RULINGS.md`,
commit `e58e884`). The file it replaces was added by `c723585` (2026-08-11) and was
never modified afterwards.

This marker follows the discipline the `map_doe` retirement set (`c0fb735`): a
retirement leaves a durable, named artifact next to what it retired, and that artifact
states the approval, the measured reason, what the retirement cannot undo, and the
exact conditions under which the thing comes back. The `map_doe` artifacts are
`.sql` because the thing retired was a pair of tables; here the thing retired is a
script, so the artifact is prose and the archive is git.

## What it was

A manual, dry-run-by-default migration that rewrote `wafer_map_metadata.map_id`
(plus `map_pk` and `business_key_val`, which are pure functions of it) for
`target_table = 'core_wafer_map'`, from the composite spelling
`core_lot || '_' || core_slot` to the single column `wafer_id`.

## Why it is retired — it implements a rejected direction

Its own docstring asserted:

> `core_wafer_map` ... On 2026-08-10 its declaration was corrected in BOTH config files
> that carry the identity ... to `["wafer_id"]`.

**That is no longer true, and has not been true since 2026-08-13.** Measured
2026-08-14 on this checkout:

- `table_config.core_wafer_map.map_key_columns` = `["core_lot", "core_slot"]`.
  `272da5b` restored the composite in the tracked `.sample` on 2026-08-13 (the live
  config had never carried `["wafer_id"]`), because `wafer_id` is not in
  `composite_key_source` = `["core_lot", "core_slot", "core_x", "core_y"]` and so
  violates R3 in `SCHEMA_CANON`.
- `wafer_id` is DELIBERATELY SPARSE by declaration — its own column comment says
  "absence is the enrichment work item". Product owner's measurement 2026-08-14:
  blank on 9,674 of 24,749 rows.
- `map_overlay_config.table_bindings.core_wafer_map.columns.key_columns` was the last
  surviving copy of the `wafer_id` identity; it was repaired, and then deleted
  outright by ruling F3 in this same round.

The script's own cross-check therefore already refused. Reproduced 2026-08-14 with a
deliberately unreachable `DATABASE_URL`, which proves the refusal happens **before any
connection is opened**:

```
mode       : DRY RUN (writes nothing)
REFUSED: table_config declares core_wafer_map.map_key_columns = ['core_lot', 'core_slot'],
         but this run would migrate to ['wafer_id'].
```

A guard that blocks a rejected direction is exactly the situation the ruling addresses:
**the guard is correct today and guards age.** `--target-table` / `--new-key` are CLI
options, so the guard is also steerable off the case it was written for. Git history is
the archive; the tool does not need to sit in the tree to remain recoverable.

## What retiring it does NOT do

- It does not change any data. Nothing was ever migrated by this script on this box —
  the guard has refused since 2026-08-13.
- It does not remove the ability to move map ids. It removes one *pre-aimed* mover.
- No consumer is affected: at retirement, `migrate_map_meta_to_wafer_id` appeared in
  no code, no test and no config — only in this marker, `LEDGER_RULINGS.md`, two
  `docs/history/` entries and one `agent_workspace/reports/` file.
- No `journal_map_meta_wafer_id_*.json` existed in `server/migrations/`, so no revert
  material was orphaned.

## Revival conditions — BOTH are required, in this order

1. **The identity axis ruling must be reversed first**, and reversed in the
   declarations, not in prose. Concretely, all three must hold before the tool has a
   job again:
   - `table_config.core_wafer_map.composite_key_source` contains `wafer_id`
     (otherwise R3 is violated the moment `map_key_columns` names it);
   - `table_config.core_wafer_map.map_key_columns` is `["wafer_id"]` **in both the live
     file and `.sample`** — they are separate files by design and only `.sample` is
     tracked;
   - `wafer_id` is actually populated. A key column that is blank on ~39% of rows
     scopes `replace_map` by nothing: the route returns 200 and deletes no rows for
     every unenriched row.

   Until (1) holds, restoring the script only restores a `REFUSED`.

2. **Then restore the file from git.** It is unchanged from the commit that added it:

   ```
   git show c723585:server/migrations/migrate_map_meta_to_wafer_id.py \
       > server/migrations/migrate_map_meta_to_wafer_id.py
   ```

   or, if that sha ever becomes inconvenient, find the deletion and take its parent:

   ```
   git log --diff-filter=D --oneline -- server/migrations/migrate_map_meta_to_wafer_id.py
   git show <sha>^:server/migrations/migrate_map_meta_to_wafer_id.py > <same path>
   ```

   **Read the restored docstring against the config before running it.** Its
   "corrected on 2026-08-10" paragraph is what outlived the fact once already; a
   restored copy will still say it.
