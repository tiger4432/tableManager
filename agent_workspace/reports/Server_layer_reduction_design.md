# LAYER-①③ Phase 1 — Design proposal for `cell_sources` and insert-audit reduction

**Status:** proposal only. **No code was changed.** `server/database/crud.py` was read, never edited.
**Box:** this workstation, database `assy_manager` (`postgresql://…@localhost:5432/assy_manager`, resolved from `DEFAULT_PG_URL`, `DB_URL_SOURCE=default`). **This is not production.** Every number below is a measurement of *this* box unless it is explicitly attributed to the product owner. Read-only queries only; nothing was written, no DDL, no DROP.
**pytest was not run.**

---

## 0. Headline: the brief's basis number was wrong, and the reason is a bigger finding than ①

The brief motivated ① with "8,839,232 `cell_sources` rows over ~1.77M data rows" on `bonding_map`. I measured the parent table before using that ratio.

```
bonding_map data rows (SELECT count(*))                         413
cell_sources rows WHERE table_name='bonding_map'          8,839,232
distinct row_id among those layers                        1,763,686
layers whose parent data row NO LONGER EXISTS             8,837,167   (99.98%)
```

There are not 1.77M `bonding_map` rows on this box. There are 413. The 1,763,686 distinct `row_id`s in the layer table are almost entirely **identifiers of data rows that no longer exist**, and the "sources per cell" distribution in the brief was computed over that dead population.

The lead PM sent the same correction mid-task. The two derivations were independent and agree.

### 0.1 The ratio survives; the basis does not

Re-measured over **live-parent cells only** (join `cell_sources` to the parent table on `row_id`), across 14 tables:

| population | cells | 1 source | 2+ sources |
|---|---:|---:|---:|
| all layers (incl. orphans) | 12,517,983 | 12,063,583 (96.37%) | 454,400 (3.63%) |
| **live-parent layers only** | **481,660** | **481,042 (99.87%)** | **618 (0.13%)** |

Per table (live-parent only):

| table | live data rows | live cells | 2+ sources |
|---|---:|---:|---:|
| bonding_map | 413 | 2,065 | 0 |
| core_wafer_map | 24,200 | 193,600 | 0 |
| dt_log | 9,132 | 134,820 | 0 |
| bonding_log | 5,296 | 68,848 | 0 |
| core_defect_map | 5,152 | 30,912 | 0 |
| valid_die_ref | 4,337 | 26,022 | 0 |
| eds_fail_map | 2,576 | 18,032 | 0 |
| dt_map | 513 | 2,997 | 0 |
| wafer_map_metadata | 677 | 2,588 | 603 (23.3%) |
| inventory_master | 15 | 60 | 15 (25.0%) |
| map_split_registry | 159 | 1,408 | 0 |

**So the premise of ① holds — 99.87% of live cells carry exactly one source — but the 8.8M-row basis for the savings estimate does not.** On this box, ① applied to the *live* population would save on the order of 480,000 layer rows, not 8.8M. The 10M-row projection in §3 is therefore built from the *ratio* and the *measured per-row byte cost*, never from the 8.8M figure.

Note also that the two tables where multi-source is common (`wafer_map_metadata` 23.3%, `inventory_master` 25.0%) are the ones with the fewest rows. The tables that would actually reach 10M rows — the map tables — show **zero** multi-source live cells. This makes ① *more* attractive at scale than the DB-wide average suggests, and it also means the promotion path (§2.3) will be exercised rarely and therefore will be **under-tested by ordinary use**. That is an argument for a strict test, not for skipping the path.

### 0.2 The orphan leak — report only, not fixed

`cell_sources` is 9,488 MB of a 14 GB database (**68%**). The great majority of it is provenance for rows that are gone.

Orphan share by table (this box):

| table | layer rows | live-parent | orphan | orphan % |
|---|---:|---:|---:|---:|
| bonding_map | 8,839,232 | 2,065 | 8,837,167 | 99.98% |
| inventory_master | 1,830,439 | 75 | 1,830,364 | 100.00% |
| eds_fail_map | 739,312 | 18,032 | 721,280 | 97.56% |
| core_defect_map | 649,152 | 30,912 | 618,240 | 95.24% |
| wafer_process | 267,886 | 308 | 267,578 | 99.89% |
| bonding_log | 293,380 | 68,848 | 224,532 | 76.53% |
| large_table_100 | 197,775 | 0 | 197,775 | 100.00% |
| dt_map | 23,755 | 2,997 | 20,758 | 87.38% |
| dt_log | 148,900 | 134,820 | 14,080 | 9.46% |
| core_wafer_map | 194,095 | 193,600 | 495 | 0.26% |
| valid_die_ref | 26,022 | 26,022 | 0 | 0.00% |

**Is it every purge path, or one?** It is **none of the three current purge paths.** All three cascade correctly to `cell_sources`:

- `crud.py:2693-2708` — `replace_map` purge, deletes `CellSource` then `CellOverwrite` then the data rows, by `row_id.in_(purged_row_ids)`.
- `crud.py:2934-2948` — the `replace_map` scope-diff path, same three deletes by `row_id.in_(removed_row_ids)`.
- `crud.py:3103-3116` — `delete_rows_batch`, same three deletes by `row_id.in_(row_ids)`.

The leak is **table-level, not row-level**. Two signatures:

1. **The parent table was dropped entirely.** 500,310 layer rows point at six tables that do not exist in `information_schema` at all — `hvy_drill_big` (500,040), `hvy_drill_small` (120), `transfer_plan_doe` (99), `transfer_plan` (21), `transfer_plan_map` (20), `map_band_registry` (10). A `DROP TABLE` (or a table removed from `table_config.json`) takes no layers with it. `server/scripts/drop_legacy_tables_20260725.sql` is a DROP script with a careful pre-flight checklist that does not mention `cell_sources` at all.
2. **The parent table was truncated or rebuilt out-of-band.** The remaining ~12M orphans point at tables that still exist. Timestamps are decisive: on `bonding_map`, orphan layers span `2026-06-20 20:05:32` → `2026-07-31 21:45:07`, while **every** live layer falls inside `2026-08-02 01:34:31` → `2026-08-02 01:34:32`. The live data is a single fresh load; everything older was left behind when the data rows went away by a route that did not go through the three cascading paths above.

**Is the orphan reachable by any reader?** Essentially no, and that is what makes it invisible. Every display-side reader keys by `(table_name, row_id, column_name)` with `row_id` supplied by a live data row — the grid provenance (`main.py:688-775` `fetch_and_merge_metadata`), the source popup (`main.py:3607-3649`, `main.py:3901-3990`), and the CSV export (`main.py:1847`, which reads no `cell_sources` at all). An orphan can never be addressed. Two paths *do* see them: `chain_replay.count_withdrawable` (`chain_replay.py:446-462`) counts claims without joining the parent — its own docstring at `chain_replay.py:434` already admits "a `cell_sources` row whose dynamic row no longer exists is counted here" — and every sequential scan and index build pays for them.

**Does anything clean them?** **No.** The only orphan sweep in the repo is `server/scripts/graph_orphan_sweep.py`, which is for `graph_nodes`/`graph_edges`. There is no sweep, no FK, and no retention policy for `cell_sources`. `models.CellSource` declares no foreign key to any parent (it cannot — parents are dynamic tables).

**Dev-box caveat, stated plainly:** this workstation has had its data tables dropped, reseeded and rebuilt many times during development, so the *magnitude* here is very likely a dev artifact and I do not claim production carries 8.8M orphans. What is **not** an artifact is the mechanism: a `DROP TABLE` or an out-of-band table rebuild leaves its layers behind permanently, nothing reclaims them, and `hvy_drill_big`'s 500,040 layers for a table that does not exist is the proof that the mechanism has fired. Whether production has fired it is a question for a production measurement, not for this box.

**Why this outranks ①:** ① changes what a *live* row costs. The leak means dead rows cost the same as live ones forever. A shape that stores one provenance row per data row instead of seven still leaves 1/7 as many **permanently orphaned** rows unless the drop/rebuild path is taught to take them. Reclaiming space is, on the evidence here, more a purge problem than a per-cell-shape problem — and I say that knowing it makes my assigned item smaller.

### 0.3 A third finding, free of both: the index bloat is structural and partly duplicated

`cell_sources` is 2,153 MB of heap under **7,335 MB of indexes** — indexes are 3.4× the data. Verbatim from `pg_indexes`:

| index | size | definition |
|---|---:|---|
| `idx_sources_lookup_source` | 2,690 MB | UNIQUE btree (table_name, row_id, column_name, source_name) |
| `idx_sources_lookup` | 1,777 MB | btree (table_name, row_id, column_name) |
| `idx_sources_by_source` | 1,626 MB | btree (table_name, source_name, column_name, row_id) |
| `ix_cell_sources_row_id` | 419 MB | btree (row_id) |
| `ix_cell_sources_id` | 314 MB | btree (id) |
| `cell_sources_pkey` | 314 MB | UNIQUE btree (id) |
| `ix_cell_sources_column_name` | 98 MB | btree (column_name) |
| `ix_cell_sources_table_name` | 95 MB | btree (table_name) |

Two observations that need no measurement to believe, because they are definitional:

- **`ix_cell_sources_id` is byte-for-byte redundant with `cell_sources_pkey`** — both are plain btrees on `id` alone, 314 MB each. It exists because `models.py:267` declares `id = Column(..., primary_key=True, index=True)`; `index=True` on a `primary_key` column makes SQLAlchemy emit a second index the primary key already provides. The same bug is present on `audit_logs` (`ix_audit_logs_id` 61 MB vs `audit_logs_pkey` 61 MB) and `cell_overwrites` (3,640 kB vs 3,608 kB). **~380 MB on this box, reclaimable by deleting three characters of model declaration, with zero behavioural change.**
- **`idx_sources_lookup` (1,777 MB) is a strict column prefix of `idx_sources_lookup_source` (2,690 MB)**, so every lookup it serves the unique index can also serve.

At the 10M-row target these are not 380 MB and 1.8 GB — they scale with the table. This is the cheapest, lowest-risk item in this entire report and it is independent of ① and ③. I did not touch it; recommending it is all I am doing. (Statistical caution per the standing lesson on `pg_stat_*`: I am **not** resting this on `idx_scan` counters, which can be reset out from under a reader. The redundancy above is read from index *definitions*, which cannot be lost.)

---

## 1. ① — Reader inventory

Full inventory in the appendix table below. The question the brief asked was: *which readers need per-column granularity for a single-source cell?*

**Answer: almost all of them.** Per-column is not a display convenience; it is the grain the layering engine resolves on.

**Hard per-column dependencies — these cannot be served by a `(table, row_id, source_name)` record alone:**

| reader | file:line | why per-column |
|---|---|---|
| `fetch_and_merge_metadata` | `main.py:688-775` (query 715-732) | builds `sources_map[(row_id, column_name)][source_name] = value` and feeds `crud.compute_priority_value` **per column**. `priority_source` and `is_overwrite` are per-column facts on the wire contract. |
| `get_cell_sources` (source popup) | `main.py:3607-3649` | route path carries `col_name`; filters `column_name == col_name` |
| `query_cells_sources` (batch popup) | `main.py:3901-3990` | `column_name.in_(col_names)`, keyed `(row_id, column_name)` |
| `_load_metadata_row_cell` | `crud.py:1765-1848` (SELECTs 1796-1800, 1811-1815) | predicate is exactly `(table, row_id, column_name)` — the hot write path |
| `delete_cell_source_batch` | `crud.py:3149-3212` | delete keyed on the exact 4-tuple |
| `set_cell_manual_priority_batch` | `crud.py:3310-3420` | a pin is a per-(row, column, source) fact |
| `withdraw_source` | `chain_replay.py:520-627` | withdraws one source from one column, recomputes per column, deletes grouped by column (617-627) |
| `find_unresolved_cells` | `enrichment_candidates.py:533-555` | 🔴 **the sharpest one.** `column_name.in_(target_fields)` returns which *cells* are unclaimed. A row-level record would make a row with **any** provenance look fully resolved, silently blocking every absent-only enrichment fill. The code comment at `enrichment_candidates.py:620-624` argues exactly this. |
| `_load_best_cell_sources` | `graph_materializer.py:500-547` | per-column edge provenance, `column_name.in_(identity cols)` |
| `derived_cell_scope` | `frame_confirmation.py:752-761` | docstring states the scope must be at `cell_sources` grain, not row grain (spec §0.3 note 4) — an explicit prior rejection of row-level provenance |
| client grid + popups | `client2/src/main.js:1258-1500`, `grid.js:184-205,351-378` | cell contract `{value, is_overwrite, sources, updated_by, priority_source}` is one object per column |

**Readers a row-level record would satisfy:** only the bulk row-purge deletes (`crud.py:2695`, `2938`, `3108`) and `dt_map_derivation.py:727-733` (which already reads `CellOverwrite.row_id` alone).

**Not a reader, contrary to the brief's guess:** CSV export. `GET /tables/{t}/export` (`main.py:1847`) streams the materialised columns and touches `cell_sources` zero times. The history timeline is also not a reader — `client2/src/timeline.js` renders `audit_logs.source_name`, never `cell_sources`. So two of the four consumers the brief listed drop out; the grid and enrichment are the real constraints.

**Tests that pin the grain as load-bearing:** `tests/test_enrichment_candidates.py:1179-1197` (`test_cell_sources_already_says_which_columns_the_sweep_decided`) and `tests/test_frame_confirmation.py:193-217`. Both would have to be rewritten, and both were written deliberately to stop this collapse.

---

## 2. ① — The proposed shape, and what it gives up

### 2.1 What the proposal actually has to store

"One row instead of five" is only true if the row-level record still answers *which columns* and *with what value*. `find_unresolved_cells` needs the column set; `fetch_and_merge_metadata` and `compute_priority_value` need the per-column value. So the collapsed record is not a narrower row — it is a row carrying `{column_name: value}` as a JSON map.

🔴 **That is a partial revert of a completed migration.** `server/migrations/normalize_schema.py:118-146` (`migrate_row_sources`) is the one-time migration that took provenance **out of** a JSONB blob and **into** `cell_sources` rows, exactly one row per `(table, row, column, source)`. Proposing to put the column→value map back into a JSON column re-creates the shape that migration was written to remove. That does not make it wrong — the migration was normalising a per-*row* JSONB blob that also held the materialised values, which is a different thing — but it must be argued explicitly rather than discovered afterwards, and `docs/guide/data_preservation_and_signature_change.md` applies.

### 2.2 Two candidate encodings

**(a) Sentinel column in the same table** — a row-level record is a `cell_sources` row with `column_name = '*'` and `value = {col: val, …}`. Cheapest storage, worst blast radius: every one of the ~25 per-column readers listed above filters `column_name == c` and would silently miss the sentinel. Silent misses in provenance are the failure mode this system's first core value exists to prevent. **I do not recommend this.**

**(b) Separate table `cell_row_sources(table_name, row_id, source_name, values JSON, ingested_at, updated_by, confirmation_uid)`** with UNIQUE `(table_name, row_id, source_name)`. Readers gain an explicit second lookup rather than a silent omission — a missing fallback shows up as an empty result at a named call site, not as a wrong winner. Migration is additive (`create_all` builds it, per the standing lesson that new tables avoid the ALTER-ordering hazard that took the admin tab down). **This is the shape I would propose if ① proceeds.**

### 2.3 Where promotion happens, and whether it is atomic

Promotion trigger: a write arrives for `(table, row, column c)` from source B, and a `cell_row_sources` record exists for `(table, row, A)` whose `values` map contains `c`.

**Where:** inside `_load_metadata_row_cell` (`crud.py:1765-1848`), which is already the single funnel every writer passes through to obtain a cell's source list — it is called from `apply_row_update_internal:1912` and `:1940`, and its batch-prefetch sibling is `crud.py:2820-2843`. Promotion belongs there and nowhere else, because that is the only place that has both the incoming write and the existing provenance in hand.

**Atomicity:** achievable, and only if promotion runs **inside the writing transaction** — never as a background job, never in a second connection. Under Postgres READ COMMITTED a concurrent reader sees either the whole pre-state or the whole post-state of that transaction, so a cell can never be observed as "no provenance". The ordering inside the transaction must be **insert-then-narrow**:

1. INSERT per-column `cell_sources` rows for `(r, c, A)` (A's value lifted out of the map) and `(r, c, B)`.
2. Remove key `c` from A's `cell_row_sources.values` map.

Never the reverse. If step 2 preceded step 1 and the transaction were split (or a reader used a separate snapshot), `c` would be momentarily unprovenanced. With insert-first, the worst intermediate state is `c` appearing in *both* records with the *same* value for A — a duplicate, not a loss, and `compute_priority_value` is idempotent over a duplicate `{source: value}` key because it resolves a dict.

**The failure mode I would guard hardest:** promotion that runs but does not narrow, leaving A's value in both places. If A's value is later corrected in the per-column row, the stale copy in the map becomes a second, invisible answer. The invariant to assert is: *no column key may appear in both `cell_row_sources.values` and `cell_sources` for the same `(table, row, source)`*. That invariant is checkable by a query and should be a test, not a comment.

### 2.4 Does the layering verdict change?

**It must not, and under shape (b) it need not.** `compute_priority_value` (`crud.py:1075-1095`) takes a dict `{source_name: {value, timestamp, updated_by}}` and is indifferent to where the entries were read from. The verdict changes only if a *reader assembles a different dict*. So the correctness condition reduces to one statement:

> For every `(table, row, column)`, the union of per-column `cell_sources` rows and the row-level records whose `values` map contains that column must be **exactly** the set of rows `cell_sources` holds today.

`user` (priority 0) still beats everything, `SOURCE_PRIORITY` still decides, and the `user` layer is never itself collapsed — see §2.6.

The real risk is not the resolver, it is the **~25 call sites that must each grow the second lookup**. A single missed site does not error; it returns a smaller dict and therefore a *different winner*. That is a silent wrong-value defect in the system's first core value. Per the standing lesson on identity lookups having two doors, the mitigation is to make the fallback **impossible to omit**: the union must live in one function that every reader calls, and the raw `db.query(models.CellSource)` pattern must disappear from the ~25 sites rather than being supplemented at each of them. If ① is implemented by adding a fallback at each call site, it will be wrong at at least one.

### 2.5 Migration of existing rows

Given §0.2, the migration question changes shape. My answer:

1. **Sweep orphans first, as a separate change, before any migration.** On this box that removes ~12M of 13.7M layer rows. Migrating orphans into a new shape would be migrating garbage, and the collapse ratio measured over orphans is the wrong ratio (96.37% vs the true 99.87%).
2. **Then collapse, dual-read during the window.** Readers query the union (per-column rows ∪ row-level records) from day one; the backfill moves eligible single-source cells one table at a time in 1,000-row chunks. Dual-read costs one extra indexed lookup per cell-metadata fetch — on the batch path that is one extra prefetch query per batch (`crud.py:2820-2843` already does exactly one), not one per row.
3. **Never collapse `user`.** See below.
4. **Cost:** the backfill rewrites every eligible row, so it generates dead tuples equal to the rows it moves and needs a `VACUUM` per table. That is the same hazard already recorded on the board for the `replace_map` purge, and the chunking discipline is the same.

### 2.6 The user layer

`user` holds **118,731** `cell_sources` rows on this box (matching the brief exactly). Split by parent liveness: **29,655 live-parent, 89,076 orphaned** — so three quarters of the "untouchable" user layer is already provenance for rows nobody can reach. That is a fact worth the product owner's attention on its own, and it is *not* an argument for deleting them: a user layer whose parent is gone may be the only surviving trace of a human decision, and the orphan sweep in §0.2 must therefore treat `source_name = 'user'` rows as a **separate, opt-in decision** rather than sweeping them with the rest.

For ① itself the rule is simple and absolute: **a `user` row is never collapsed into a row-level record.** It is priority 0, it is the layer the whole design exists to protect, it is 0.9% of the table, and collapsing it buys nothing while putting the one irreplaceable layer into a new code path.

---

## 3. ① — Honest savings estimate at the 10M-row target

Measured per-row cost on this box (relation size ÷ row count, so indexes included):

| table | rows | heap | indexes | total | bytes/row |
|---|---:|---:|---:|---:|---:|
| `cell_sources` | 13,721,563 | 2,153 MB | 7,335 MB | 9,488 MB | **725** |
| `audit_logs` | 2,830,578 | 1,059 MB | 655 MB | 1,714 MB | **635** |

(Cross-checked against `pg_column_size`: `cell_sources` heap 170.0 B/row measured vs 164.5 B/row derived; `audit_logs` 391.1 vs 392. The two methods agree, so the per-row figures are sound.)

Projection at 10M data rows, using the brief's 7 layers + 1 audit per data row:

| | rows | bytes/row | total |
|---|---:|---:|---:|
| `cell_sources` today | 70,000,000 | 725 | **50.7 GB** |
| `audit_logs` today (insert rows) | 10,000,000 | 635 | **6.4 GB** |

Under ① shape (b), for the 99.87% single-source case:
- 1 row per (data row, source) instead of 7 → **10M rows**.
- Heap per row grows: the `values` map holds 7 column names + 7 values instead of one of each. Estimate ~400 B vs 164.5 B.
- Index bytes per row shrink modestly (drop `column_name` from the composites, ~15% narrower keys) and the *count* of index entries drops 7×. Estimate ~477 B/row.
- Promotion overhead for the 0.13% that stack: 0.0013 × 10M × 7 × 725 ≈ 66 MB. Negligible.

| | rows | bytes/row | total |
|---|---:|---:|---:|
| `cell_sources` under ① | ~10,000,000 | ~877 | **~8.8 GB** |

**Estimated saving from ①: ~42 GB of ~50.7 GB (≈83%) at the 10M-row target.**

**Confidence, stated honestly.** The *ratio* (7 rows → 1) is solid — it follows from the measured 99.87% single-source rate on live cells, and the tables that will actually reach 10M rows show 0% multi-source. The *bytes* are an estimate with one soft assumption: the ~400 B heap for the JSON map is reasoned, not measured, because the shape does not exist yet. If the map turns out to cost 700 B the saving drops to ~38 GB — still the dominant term. The estimate is not sensitive to that assumption because **560 of the 725 bytes are index, not heap**, and the index saving comes from having 7× fewer entries, which is a certainty of the shape rather than an estimate.

**The number that should temper all of this:** on the current live population, ① saves roughly 480,000 rows — about 340 MB. The 42 GB is entirely a projection about a future 10M-row production, while the ~7 GB of orphan and redundant-index waste measured in §0.2 and §0.3 is present *today*. If the goal is to reclaim space on the 14 GB production database now, ① is not the lever; the purge and the duplicate indexes are.

---

## 4. ③ — Audit on first INSERT

### 4.1 Can insert and update be distinguished at write time? **Yes, reliably.**

The write path knows. `_get_or_create_row` returns `is_new` (`crud.py:1643-1667`):

```
1643	    is_new = False
1644	    if not row:
...
1660	        db.add(row)
1661	        is_new = True
...
1667	    return row, is_new
```

Bound at `crud.py:1893` (`row, is_new = _get_or_create_row(...)`) and still in scope at **both** audit call sites — `crud.py:2123` and `crud.py:2151`. The ingestion branch **already branches on it**: `crud.py:2139` `if is_new:` sets `old_summary = None` and the message prefix `"신규 데이터 생성: "`. So ③ requires no new knowledge; the flag is already there and already consulted at the exact line that writes the row.

`is_new` is more trustworthy than `old_val is None`, and the codebase already knows that. `old_val is None` cannot distinguish "row did not exist" from "row existed with a null cell" — which is why the change guard at `crud.py:2103-2110` must special-case `is_new` *before* it may use nullness at all. A further trap: `AuditLog.old_value` is a SQLAlchemy `JSON` column, so Python `None` is stored as JSON `'null'`, **not** SQL NULL. Measured on this box: `old_value IS NULL` → **0 rows**; `old_value::text = 'null'` → **2,645,543 rows**. Any consumer written as `WHERE old_value IS NULL` matches nothing today.

One caveat worth carrying into implementation: `is_new` can be **demoted to False mid-function** at `crud.py:2181-2197`, when a business-key collision merge finds a pre-existing row and deletes the just-created shell. That is semantically correct — the surviving row is old — but it means `is_new` at the audit call site is the post-merge truth. For ③ that is the *right* value, so it is a note rather than an obstacle.

**Verdict: ③ is viable as stated. The escape hatch is not needed.**

### 4.2 How many rows, and are they cleanly identifiable?

Three independent predicates were measured and **agree exactly**:

```
audit_logs total                                                   2,830,578
column_name = 'ROW_UPDATE'                                         2,659,179   (94.0%)
  ... AND old_value::text = 'null'                                 2,479,921
  ... AND new_value matches the '신규 데이터 생성' create prefix    2,479,921
  ... AND source_name <> 'user'                                    2,479,921
```

The ingestion-insert set is **2,479,921 rows = 87.6% of the entire audit table**, and every one of them is non-`user`. Three predicates converging on the same count is strong evidence the set is cleanly delimited.

`CREATE` rows (the UI "new empty row" marker, `crud.py:3061`) number only **113** and are a different thing — they are the *only* record of a UI-created row and must stay.

### 4.3 What reads `audit_logs`, and what would notice

| consumer | file:line / route | would it notice? |
|---|---|---|
| `audit_cache` (`AuditLogCache`) | `server/audit_cache.py`, singleton l.195 | **Yes.** A first-insert transaction writing no rows produces no group; `total_count` under-reports for mixed transactions. |
| `GET /audit_logs/recent` | `main.py:915` | **Yes.** Whole transactions vanish from the global timeline. |
| `GET /audit_logs/transaction/{tx_id}` | `main.py:960`, DB fallback 1001-1007 | **Yes — 404 "Transaction not found".** |
| 🔴 **grid `transaction_id` filter** | `main.py:1514`, `1769`, `1869` | **Yes, and this is the worst one.** "Show me the rows transaction X touched" resolves *solely* through `db.query(AuditLog.row_id).filter(transaction_id == …)`. A freshly ingested file's transaction would return an **empty grid**, silently. |
| `GET /tables/{t}/rows/{row_id}/history` | `main.py:2257` | **Yes.** A row loaded and never edited shows empty history. |
| `GET /tables/{t}/rows/{row_id}/cells/{col}/history` | `main.py:2283` | Yes, same. |
| `GET /dashboard/summary` → `today_updates` | `main.py:1161`, count at 1195 | **Yes.** Drops by exactly the suppressed count. |
| `get_effort_stats` denominator | `crud.py:1311-1384`, audit read 1367-1372 | **Yes.** Shrinks `total_user_tx`, inflating `measured_ratio` — possibly above 1.0. Only affects `source_name='user'` transactions, which ③ does not target, so in practice: no. |
| `get_recorrection_stats` | `crud.py:1203-1257` | **It gets *better*.** It already subtracts null→null first-insert rows by hand at `crud.py:1236-1238` (measured 4,290 such rows). Removing them upstream removes that workaround's reason to exist. |
| `get_deleted_row_business_key` | `main.py:834-851`, bulk 871-888 | **Yes, potentially severe.** This is the only way a *deleted* row's business key is recoverable. If the insert row was the only audit row that row ever had, the key is unrecoverable. |
| client timeline | `client2/src/timeline.js:14,33,36,218`; `CREATE`/`DELETE`/`ROW_UPDATE` special-case at 131-158 | **Yes, visibly.** The "🆕 N행 생성" and "신규 데이터 생성" cards stop appearing. |
| admin KPI cards | `client2/src/admin.js:1460-1554` via `/dashboard/summary` | Yes, indirectly. |

### 4.4 Is the insert audit row the only record that a row arrived?

**Not of arrival — but yes, of the transaction.**

Arrival itself is recoverable elsewhere: every dynamic table has `created_at` (`server_default=func.now()`, and `_get_or_create_row` deliberately leaves `updated_at` unset on INSERT at `crud.py:1645-1656`, so `created_at == updated_at` marks a never-edited row); `cell_sources.ingested_at` stamps first arrival per cell; `file_ingestion_logs` (`models.py:186-198`) and `file_ingestion_checkpoints.processed_rows` (`models.py:200-245`) record file-level arrival.

**What is irrecoverable is the `transaction_id → row_id` mapping.** No other table holds it durably — `database_outbox` does, for 7 days only. That mapping is what `main.py:1514/1769/1869` depend on. **This is the fact that dropping the row would lose and nothing else holds.**

### 4.5 The `user`-triggered ambiguity — a decision for the product owner, not for me

The brief says `user` audit rows are untouchable, "and so is anything a human triggered, whatever the source name." Measured `updated_by` on the 2,479,921 non-user first-insert rows:

```
system                    2,170,482
kk980                       308,407     <-- a human's username
seed_dt_index_walk              874
bonding_plan_demo               160
enrichment_backfill             124
chain_worker                     97
seed_valid_die_ref_floor         89
tester                           65
client-pm-cleanup                23
transfer_plan_demo                3
```

**308,407 rows carry a human's username in `updated_by` while carrying a CSV filename in `source_name`** — these are web-uploaded files. A human triggered the upload; the row content is a bulk load, not a correction. Under the literal reading of "anything a human triggered" they are protected and ③ shrinks by 12%. Under the value-5 reading ("the lineage of corrections, not of loading") they are in scope. **I am not deciding this.** It changes the saving by ~0.8 GB at the 10M target and it is a judgement about what the audit trail is *for*.

### 4.6 What I would propose for ③ instead

③ as literally stated — *stop writing the insert audit row* — is viable at the write path but **breaks four real consumers**, one of them silently (the grid transaction filter returning an empty result set). I do not recommend it.

**Counter-proposal: keep the row, shrink it.** The bytes are not in the row's existence, they are in `new_value`. A measured first-insert row is **403.4 bytes**, and its `new_value` is a full Korean restatement of every column the row already holds:

```
"신규 데이터 생성: base: 505fefc5-a2b9-4c0f-a0e8-dbf1083f1d99, x: 100, y: 88,
 leg: LEFT, pkg_id: 505fefc5-a2b9-4c0f-a0e8-dbf1083f1d99..."
```

This is exactly the redundancy the brief identified — "the row's own existence and provenance already state it" — but the redundancy lives in the *payload*, not in the *row*. Replacing `new_value` with a compact marker (and letting the client render "신규 데이터 생성" from `column_name = 'ROW_UPDATE'` + null `old_value`, which it already special-cases at `timeline.js:131-158`) keeps `row_id`, `transaction_id`, `timestamp` and `business_key` — so **every consumer in §4.3 keeps working**, including the grid transaction filter and the deleted-row business-key recovery.

| option | rows/row | bytes/row | 10M total | consumers broken |
|---|---:|---:|---:|---|
| today | 1 | 635 | 6.4 GB | — |
| ③ as stated (drop) | 0 | 0 | 0 GB | **4, one silently** |
| ③ shrink `new_value` | 1 | ~350 | ~3.5 GB | **0** |

**Estimated saving from the shrink variant: ~2.9 GB of 6.4 GB (≈45%) at the 10M-row target, with no consumer loss.** That is less than half of what dropping the row would save, and it is the version I would put my name on. If the product owner wants the full 6.4 GB, the prerequisite is a durable `transaction_id → row_id` index that does not live in `audit_logs` — which is a new table, not a deletion, and would eat much of the saving.

---

## 5. Interaction with the outbox lane (④) — noted, not designed

Only one interaction, and it runs the other way from what one might expect. The `created_logs` payload the watcher and chain worker post to `/internal/events/*` is built from the audit rows accumulated in `apply_batch_updates` (`crud.py:2960-2975`), truncated at the sender per `server/event_constants.py` (`MAX_NOTIFY_CREATED_LOGS`), with the true count carried separately as `total_log_count` (`run_watcher.py:125`). **Shrinking `new_value` (§4.6) shrinks that payload proportionally**, which is a direct win for the incident class recorded in the server-pm memory file (the 2026-07-25 ~50 MB payload that froze the web server for tens of seconds). Dropping the rows entirely would empty `created_logs` and remove the timeline's live "N행 생성" push. Neither ① nor ③ changes any outbox event name or payload shape. **No boundary contract is touched by anything proposed here.**

---

## 6. Recommendation, ordered by value per unit of risk

| # | item | saving (10M target) | saving today | risk | in this brief? |
|---|---|---|---|---|---|
| 1 | Remove `index=True` from the three `primary_key` `id` columns (`CellSource`, `AuditLog`, `CellOverwrite`) | scales with table | ~380 MB | **none** — the pkey already provides the index | no (found in passing) |
| 2 | Orphan `cell_sources`/`audit_logs` sweep + teach the DROP/rebuild path to cascade | unbounded (it is a leak) | ~7 GB | low, but `user` rows need an explicit decision | no (found in passing) |
| 3 | ③ shrink variant — keep the audit row, compact `new_value` | ~2.9 GB | ~1.0 GB | low — no consumer changes | yes |
| 4 | Drop `idx_sources_lookup` (strict prefix of the unique index) | scales | ~1.8 GB | low, wants an EXPLAIN check first | no |
| 5 | ① row-level provenance with promotion | ~42 GB | ~0.3 GB | **high** — ~25 reader call sites, first core value | yes |
| 6 | ③ as stated (drop the row) | ~6.4 GB | ~1.6 GB | **high** — 4 consumers, one silent | yes |

**The blunt summary:** ① is the largest number on the page and the smallest present-day effect, and it is the only item that puts the layering verdict at risk. Items 1 and 2 are not in my brief, were found while checking my brief's basis number, and together reclaim more space on the production-sized database *today* than ① would. I would sequence 1 → 2 → 3 and treat ① as a scale-out decision to be taken once the leak is closed and the collapse ratio can be measured against a population that is actually alive.

---

## Appendix — provenance of every number

All measurements: read-only queries via `conda run -n assy_manager`, scripts under the session scratchpad prefixed `L13_`. Database `assy_manager` on this workstation, 2026-08-07. No writes, no DDL, no DROP, no isolated env needed. `pytest` not run.

| claim | how obtained |
|---|---|
| layer/audit row counts, per-table splits | `SELECT count(*) … GROUP BY table_name` |
| orphan counts | `NOT EXISTS (SELECT 1 FROM <parent> d WHERE d.row_id = cs.row_id)` per table |
| live-parent distribution | `JOIN <parent> d ON d.row_id = cs.row_id`, then `GROUP BY row_id, column_name` |
| table-gone orphans | set difference against `information_schema.tables` |
| sizes | `pg_total_relation_size` / `pg_relation_size` / `pg_indexes_size` |
| bytes per row | relation size ÷ `count(*)`, cross-checked against `avg(pg_column_size(t.*))` over a 20k–50k sample |
| index definitions | `pg_indexes.indexdef` (**not** `pg_stat_user_indexes` counters, which can be reset) |
| insert-audit identification | three independent predicates on `column_name`, `old_value::text`, `new_value #>> '{}'`, all returning 2,479,921 |

**Not measured, and therefore not claimed:** anything about production. The product owner has confirmed that production shows the same single-source dominance; the product owner has **not** confirmed anything about orphan share, and the orphan magnitude here is very likely inflated by this box's development history. Before item 2 is scheduled, the orphan share should be measured on production with the same query.

**Proposed memory lesson (for the lead PM to accept or reject, not added by me):**
> **함정**: 비율은 맞는데 분모가 죽어 있다. 「99.7%가 단일 소스」는 참이었지만 그 8.8M 행의 99.98%가 **이미 사라진 부모 행**의 provenance였다 — 살아 있는 셀로 다시 재면 같은 비율(99.87%)이지만 모수는 481,660개, 즉 18배가 아니라 **26배** 작다. 절감 추정을 그 분모에 얹었으면 42GB를 0.3GB로 착각하는 대신 그 반대를 저질렀을 것이다.
> **올바른 방법**: 메타데이터 테이블의 통계를 인용하기 전에 **부모 테이블의 행 수를 먼저 센다.** `cell_sources`·`audit_logs`처럼 부모에 FK가 없는 테이블은 부모가 사라져도 조용히 남으므로, `count(*)`는 언제나 「살아 있는 것 + 아무도 못 지운 것」의 합이다. 비율은 살아남고 모수는 죽는다.
