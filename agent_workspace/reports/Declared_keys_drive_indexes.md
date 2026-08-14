# F6 — The builder now indexes the DECLARED keys

**Round:** builder rule + migration + policy document. Ruling context `R-2026-08-14-B`
(`docs/process/LEDGER_RULINGS.md`), which declined a canon `map_key_columns` rule and asked for a
policy driven by measured need.

**Nothing was committed, added, pushed or stashed. `assy_manager` received NO DDL of any kind** —
every connection to it was opened read-only and PostgreSQL enforced it. All write probing happened on
`assy_qa` and on one session-scoped probe database, and all of it was undone (§7).

---

## 0. 🔴 CONTRADICTS THE FACTS IN THE BRIEF — read this first

The brief restates `agent_workspace/reports/F5_index_rule_survey.md`. Nine of its statements are no
longer true, and three of them change a decision.

| # | The brief / F5 says | Measured 2026-08-14 (this round) | Does it change anything |
|---|---|---|---|
| 1 | "17 registered tables" | **18.** `delam_obs` was registered after the survey (0 rows then, **10,421** now — another lane is seeding it). | Every "all 17" claim below is "all 18". `assy_qa` still has 17 — `delam_obs` is not physically there, and the migration reports it as "declared but not present". |
| 2 | F5 §5.1: "`assy_manager` has **no** `uq_bk_*` unique index on any of the 17 tables" — flagged as bigger than anything in the gap table | **Closed. `uq_bk_<t>` exists on all 18 tables.** | 🔴 **Changes a decision.** With `uq_bk_<t>` (UNIQUE, single column `business_key_val`) present, the builder's `ix_<t>_business_key_val` is **structurally 100% redundant** on that database. I did **not** retire it — see §6.1 for why that knot should not be pulled by this round. |
| 3 | "`idx_<t>_bk` is at zero on 16 of 17" | Zero on **all 18, on both dev copies.** | Strengthens the retirement; the migration still gates it structurally, not on this number. |
| 4 | "`ix_<t>_created_at` has **zero scans on all 17 tables**" | True on `assy_manager` (18/18). **False as a universal**: `ix_production_plan_created_at` on `assy_qa` read **1**. | 🔴 **Changes the design.** A blanket `DROP` list would have been wrong on one box. The migration's gate is the **live counter on the target database**, so it refused that one by itself. 35 of 36 (table, database) pairs are zero. |
| 5 | "`wafer_map_metadata` 32,046 scans (hottest)"; "`idx_core_wafer_map_map_key` 4,949 scans" | **44,103** and **28,027** — same day, ~6 h later. | The *ranking* is unchanged (`wafer_map_metadata` still first) but the absolute figures move fast. Anything quoting them must date them. |
| 6 | `idx_bonding_log_base_position` listed only as "present on `assy_qa`" | **61,813 scans — the busiest index measured on either box.** | 🔴 **Changes the argument.** It is `(base_id, bx, by, row_id) INCLUDE (stack_height)` and is **not derivable from any declaration**. The busiest index on each box now sits on opposite sides of the automation line: `assy_manager`'s (44,103) is derivable, `assy_qa`'s (61,813) is not. |
| 7 | F5 row 7: `valid_die_ref` — "an index here is write cost for no read" | The equality argument still holds (**8 distinct / 97 pages**). But `_count_cells_bulk` issues `SELECT product, type, count(*) … GROUP BY 1,2` **with no WHERE, once per catalog request**, and that statement shape measured **7.899 ms → 4.782 ms** (HashAgg → GroupAgg) on `core_wafer_map`. | F5's "not now" was right for the reason it gave; there is a **second consumer** it did not have. Documented rather than used as a lever. |
| 8 | `inspection_run` 77,500 rows | **107,500** — still **100% synthetic**. | The widest declared key (6 columns) sits on the fastest-growing fixture table. Cost measured explicitly for that shape (§4). |
| 9 | "8 indexes per table" from the builder | Was 8 (1 pkey + 5 single + 2 composite). **Now 7.** | — |

**One framing in the brief is also worth correcting.** The brief presents the index as a cost
(`+13.1% insert, +74.8 B/row WAL`). Measured with the two retirements included, **the net effect of
this round on the write path is negative** — see §4. There is no cost/benefit trade to adjudicate.

---

## 1. The rule, and the evidence for it

```
declared_key_columns(table_cfg)  ->  (columns, source_declaration)

    map_key_columns          if declared
    composite_key_source     else, if declared
    [business_key]           else, if business_key is a declared column
                                   AND the table declares no composite_key_source
    []                       else, with a stated reason
```

One index per table, `idx_<table>_declared_key`. Spelled once, in
`server/database/models.py::declared_key_columns`.

**Why this and not "index `map_key_columns`".** The brief already carries the counter-example; here is
what makes the fallback the *right* fallback rather than a patch:

1. **It retro-predicts every hand-added index that has readers.** Three predicate indexes exist on
   `assy_manager`, written independently by humans at different times. The rule derives **all three,
   column-for-column**:

   | Existing, hand-written | Rule derives | From |
   |---|---|---|
   | `idx_core_wafer_map_map_key (core_lot, core_slot)` — 28,027 scans | same | `map_key_columns` |
   | `idx_wafer_map_metadata_target_map (target_table, map_id)` — 44,103 scans | same | `composite_key_source` |
   | `idx_map_split_registry_ref_map (ref_table, map_key)` — 17 scans | same | `map_key_columns` |

   The migration discovers this itself and reports `already covered by <name>` — it does not create a
   duplicate. That output is the validation, produced by the tool rather than argued in prose.

2. **The tier order is load-bearing, not stylistic.** On all nine tables that declare both,
   `map_key_columns` is a **leading prefix** of `composite_key_source` (verified against the live
   config, all 18 tables). So tier 1 is the *narrower* index for the same lookups, and width is WAL
   per row on every insert.

3. **Tier 3 is not decoration — it covers a real predicate nothing indexes today.** `dt_inventory`
   declares no map key and no composite key; its `business_key` is `dt_job`, a real column, and
   `mappers/core_usage_mapper` issues `WHERE dt_inventory.dt_job IN (all_jobs)`.
   `business_key_val` **cannot serve that** — it is a different column. `chain_bindings.identity_column`
   was already making exactly this judgement (map key first, then `business_key` gated on the absence
   of a composite key); the index layer was the only thing not reading it. `declared_key_columns`
   generalises that primitive from arity 1 to any arity rather than re-spelling it.

4. **All-or-nothing.** A declaration naming a column the table lacks refuses the whole index and says
   so at build time. A partial tuple would be a *different* index than the one declared, created
   silently — ruling F3's "drift wearing a declaration's clothes".

### 1.1 A declaration kind that should NOT be indexed

**The `business_key` column of any table that declares a `composite_key_source`.** Those business
keys (`core_cell_key`, `dt_cell_key`, `cell_key`, `bond_cell_key`, `pkg_id`, `split_key`, `map_pk`,
`void_uid`, `delam_uid`, `wid_key`, `event_id`, `run_uid`, `plan_id`, `part_no`) are **joins of other
columns**, and a census over `server/**` found **not one WHERE predicate on any of them** — identity
lookups all go through the framework's `business_key_val`. The `composite_key_source` gate in tier 3
is what keeps them out. Without it the rule would add 15 indexes with zero readers.

Two further kinds are excluded and the reason is in `docs/architecture/INDEX_POLICY.md` §2:
`display_columns` (presentation, never a predicate) and the general user column (the AG-Grid
`?filters=` path can filter *any* declared column — using that as a justification means indexing
every column of every table).

---

## 2. What changed

| File | Change |
|---|---|
| `server/database/models.py` | `declared_key_columns()` added (the whole rule + its reasoning). Builder: `index=True` removed from `created_at`; `Index(idx_<t>_bk, business_key_val, row_id)` removed; `Index(idx_<t>_declared_key, *cols)` added. Refusals print once at build time. |
| `server/migrations/align_indexes_to_declarations.py` | **New.** Read-only by default (PostgreSQL-enforced), `--apply` to write, `--reverse --apply` to undo. Reuses `drop_redundant_layering_indexes`'s catalogue readers (`index_facts`, `stats_are_trustworthy`, `_drop`, `quote_ident`, `rollback_ddl`) rather than re-spelling them. |
| `server/migrations/add_core_wafer_map_key_index.sql` + `_reverse.sql` | **Deleted**, replaced by `add_core_wafer_map_key_index.RETIRED.md` (map_doe / `migrate_map_meta_to_wafer_id` discipline). Superseded exactly: the rule derives the identical column list. Its four measurements were moved to `INDEX_POLICY.md` §2.1 before deletion, and the marker says so. |
| `server/tests/test_declared_key_indexes.py` | **New**, 20 tests. |
| `docs/architecture/INDEX_POLICY.md` | **New** — the per-table policy document (Korean). |
| `docs/architecture/data_model.md` §1.2 · `docs/guide/config/table_config.md` · `docs/guide/DEPLOY_SETUP.md` §6 8-quinquies · `docs/process/PRODUCTION_READINESS.md` C5 + summary table + recommended order · `docs/process/DOC_OWNERSHIP.md` | Pointers and the operator step. |

### 2.1 The migration's two gates are deliberately different

- `idx_<t>_bk` — **structural**: dropped only when another valid, non-partial btree on that table
  leads with `business_key_val`. That proof lives in `pg_index` and survives a statistics reset.
- `ix_<t>_created_at` — **counter-gated**, and the counter is a *refusal* gate, never a reason. It
  refuses outright when **every** index on the table reads zero (a fresh restore or a reset stats
  file — that zero is absence of evidence, not evidence of absence). It refused 4 tables on
  `assy_manager` and 7 on `assy_qa` for exactly this.

Exit code is 1 when anything was refused. That is not failure; it is "this box has not proved that
item".

---

## 3. Demonstrations (what you said you would check)

### 3.1 A new table created THROUGH the builder

Run on a session-scoped probe database `assy_f6_e47e3a33`, created and dropped in the same script
(neither dev copy touched). Path is the real runtime one: `init_dynamic_models` →
`create_missing_dynamic_tables` → physical `CREATE`. The config is synthetic and lives only in that
process — `server/config/*` was never written.

```
[Schema] 'f6demo_broken_table': no declared-key index - 'map_key_columns' names
         ['column_that_does_not_exist'] which are not declared columns; refusing a partial index
[Schema Sync] Created missing physical table 'f6demo_map_table' at runtime.   (+3 more)

== f6demo_map_table   (7 indexes)   declared key: ['demo_lot','demo_slot'] <- map_key_columns
     f6demo_map_table_pkey                      btree (row_id)
     idx_f6demo_map_table_declared_key          btree (demo_lot, demo_slot)     <-- THE RULE
     idx_f6demo_map_table_updated               btree (updated_at, row_id)
     ix_f6demo_map_table_business_key_val       btree (business_key_val)
     ix_f6demo_map_table_is_graph_synced        btree (is_graph_synced)
     ix_f6demo_map_table_needs_graph_rollback   btree (needs_graph_rollback)
     ix_f6demo_map_table_updated_at             btree (updated_at)

== f6demo_meta_table  (7)  declared key: ['demo_target_table','demo_map_id'] <- composite_key_source
     idx_f6demo_meta_table_declared_key         btree (demo_target_table, demo_map_id)
== f6demo_master_table (7) declared key: ['demo_part_no'] <- business_key
     idx_f6demo_master_table_declared_key       btree (demo_part_no)
== f6demo_broken_table (6) declared key: NONE  <- refusing a partial index
     (no *_declared_key index; the other six are unchanged)

--- the two retired families must be ABSENT on every table ---
  ix_*_created_at / idx_*_bk present: NONE
```

All three tiers plus the refusal, on real physical tables read back out of `pg_indexes`.

### 3.2 Before / after index count per existing table — `assy_qa`, `--apply`, then `--reverse --apply`

`assy_manager` is read-only for me, so the real forward run was on `assy_qa`. `delam_obs` is declared
but not physically present there and was skipped by name.

| table | before | after (forward) | after (reverse) |
|---|---|---|---|
| bonding_log | 10 | **9** | 10 |
| bonding_map | 9 | **8** | 9 |
| core_usage_map | 8 | 8 | 8 |
| core_wafer_map | 9 | **8** | 9 |
| dt_core_view | 8 | 8 | 8 |
| dt_inventory | 8 | **7** | 8 |
| dt_log | 9 | **8** | 9 |
| dt_map | 9 | **8** | 9 |
| inspection_run | 10 | **9** | 10 |
| inventory_master | 9 | 9 | 9 |
| lot_event | 9 | 9 | 9 |
| map_split_registry | 9 | 9 | 9 |
| production_plan | 9 | 9 | 9 |
| valid_die_ref | 9 | **8** | 9 |
| void_obs | 12 | **11** | 12 |
| wafer_id_status | 9 | 9 | 9 |
| wafer_map_metadata | 9 | **8** | 9 |
| **TOTAL** | **155** | **145** | **155** |

Forward: **17 created, 27 dropped, 7 refused.** Reverse: **27 created, 17 dropped, 0 refused** —
back to 155, table for table. `assy_qa` is exactly as I found it (§7).

**`assy_manager`, projected (read-only run, nothing written):** 176 indexes across 18 tables today.
Would create **15** declared-key indexes (3 already covered by their hand-written equivalents), drop
**18** `idx_<t>_bk` and **14** `ix_<t>_created_at`, refuse **4** `ix_<t>_created_at`
(`bonding_map`, `inventory_master`, `production_plan`, `wafer_id_status` — every index on those tables
reads zero). Net **176 → 159**.

---

## 4. Cost — the number that settles it

`assy_qa` probe tables, 40,546-row INSERT, 5 alternating rounds, **per-statement WAL via
`EXPLAIN (ANALYZE, WAL)`** so a concurrent workload on the box cannot contaminate it (the F5 round
used a `pg_current_wal_lsn()` delta, which can). Probes dropped.

| shape | config | idx | WAL B/row | ms (median) | index bytes |
|---|---|---|---|---|---|
| `bonding_log` (2-col key) | today | 8 | 741.9 | 1,826 | 8,298,496 |
| | **proposed** | **7** | **661.0** | **1,611** | **6,463,488** |
| | today + key (no retirement) | 9 | 820.8 | 1,942 | 8,921,088 |
| `inspection_run` (6-col key) | today | 8 | 744.4 | 1,837 | 8,298,496 |
| | **proposed** | **7** | **715.8** | **1,732** | 9,027,584 |
| | today + key (no retirement) | 9 | 875.6 | 2,239 | 11,485,184 |

- Marginal cost of the declared-key index alone: **+78.9 B/row** (2 cols), **+131.2 B/row** (6 cols).
  F5 measured **+74.8 B/row** for the same 2-column shape with a *different instrument*. **Two
  instruments agree within 5%** — the number is not an artefact of the harness.
- **Net of the whole round: `bonding_log` shape −80.9 B/row (−10.9% WAL, −11.8% insert time);
  `inspection_run`, the widest key in the config, −28.6 B/row (−3.8%, −5.7%).** The worst case is
  still negative.
- WAL was **byte-identical across all five repeats** for every proposed config
  (`bonding_log` proposed: 26,801,713 five times). WAL is the decidable number; the timing
  distributions overlap.
- ⚠️ Storage moves the other way for the wide key: −22% for 2 columns, **+8.8%** for 6.
  `pg_relation_size` is the wrong instrument for write cost in both directions.
- ⚠️ WAL FPI was 1 per run except two checkpoint-adjacent outliers (61 and 24). Medians unaffected;
  disclosed rather than dropped.

---

## 5. Tests

`server/tests/test_declared_key_indexes.py` — **20 passed**. Table names are `f6idx_`-prefixed so they
cannot collide with the user's gitignored `table_config.json`.

**The alarm was rung before delivery.** Two defects injected into `models.py`, both reverted
byte-for-byte afterwards (`grep INJECTED` returns nothing; the file's diff is only the intended
change):

| Injected | Result |
|---|---|
| `_KEY_TIERS = ("map_key_columns",)` — i.e. the naive rule ruling B rejected | 🔴 `test_the_naive_rule_is_not_reintroduced` **FAILED**, plus 6 others |
| `index=True` back on `created_at` | 🔴 `test_the_two_unread_families_are_gone` **FAILED on all 5 tables**, `test_every_index_names_a_declaration` on all 5 |

13 failed / 7 passed under injection; 20/20 after revert. `test_the_naive_rule_is_not_reintroduced`
is the one that matters — every other test in the file still passes if someone "simplifies"
`declared_key_columns` back to one tier.

Also re-run green after the change, in three batches (counting each file once):
`test_audit_schema_canon` · `test_business_key_unique_migration` · `test_schema_drift_startup` ·
`test_system_schema_drift` · `test_schema_map_push_ok` · `test_config_reload_integrity` ·
`test_composite_business_key` · `test_void_schema` (**162 passed**), `test_api` ·
`test_index_group_count` · `test_chain_key_gate` · `test_dt_map_derivation` ·
`test_alignment_batched_reads` · `test_capped_reads_have_a_total_order` (**120 passed, 1 skipped,
1 pre-existing failure — see below**), plus the new file (**20 passed**). **302 distinct tests green.**
Not a full-suite gate: these are the files that build dynamic models, check schema canon, or assert
index shape.

⚠️ **One pre-existing red, not mine:** `test_dt_map_derivation.py::test_all_three_declared_rules_ship_disabled`
— it opens `server/config/chain_rules.json.sample` and expects 3 `dt_map` rules, finds 2. It imports
no model and reads no database. The file is unmodified in the working tree; its last change is commit
`4d5198c` ("dt_map follows the physical unit…"), which reduced the count. That is the chain lane's.

---

## 6. Flagged, not fixed

1. 🟡 **`ix_<t>_business_key_val` is now fully redundant on `assy_manager`.** `uq_bk_<t>` is a UNIQUE
   btree on the same single column, so it serves every lookup the plain one serves, and both are
   maintained on every insert (`ix_bonding_log_business_key_val` alone is **20 MB**). I did not pull
   this: dropping it physically is safe today, but the builder would keep creating it on fresh
   databases, and *removing it from the builder* would leave a fresh database with **no**
   `business_key_val` index until the unique migration runs — the exact window `models.py` warns about
   in its own comment. The clean fix is for the builder to declare `unique=True`, which is an
   **identity-semantics change**, not a performance one. Needs a ruling.
2. 🟡 **`server/enrichment_backfill.py` (~:182)** says `business_key_val` is indexed **twice**
   (`index=True` + `idx_<table>_bk`). My change makes that sentence false. **It is outside the files I
   was scoped to** (`models.py`, `migrations/`, tests), so I stopped rather than editing. One-line
   comment fix, no behaviour.
3. 🟡 **Index-name convergence needs the `server/scripts/` lane.**
   `idx_wafer_map_metadata_target_map` and `idx_map_split_registry_ref_map` are created by
   `setup_bonding_plan_indexes.py` / `setup_transfer_plan_indexes.py`. They have the same columns as
   the rule's index under different names. The migration skips them (idempotent **by column list, not
   by name**), so nothing is duplicated — but a fresh database gets `idx_<t>_declared_key` while
   `assy_manager` keeps the legacy name. `ALTER INDEX … RENAME` is metadata-only and instant, but
   renaming before those scripts stop declaring them would make the next script run recreate the old
   names as duplicates. **Order: retire those two declarations first, then rename.** Documented in
   `INDEX_POLICY.md` §6.1.
4. 🟡 **The two graph-flag indexes** (`is_graph_synced`, `needs_graph_rollback`) are boolean 2-value
   btrees read by a function marked `[DEPRECATED — C-7]` in `graph_sync_worker`. They are *read*
   (354 scans on `assy_qa`'s `dt_inventory`), so "nobody reads it" does not apply — but partial
   indexes are the right shape and the deprecated reader is the right question. Next round.
5. 🟡 **`ix_<t>_updated_at` is structurally dominated** by `idx_<t>_updated` `(updated_at, row_id)`.
   Not retired: "nobody reads it" and "the one beside it can substitute" are different claims, and
   this round only enforces the first.
6. ⚪ **`add_dt_log_trigger_indexes.sql` still says NOT RUN and is still not run**, on either copy,
   while its predicates are live inside `enrichment_rules.json`'s reference views.
7. ⚪ **Runtime config reload does not move indexes.** `init_dynamic_models`' hot-swap branch only
   appends columns; changing `map_key_columns` on a live system needs a process restart for the model
   and the migration for the physical index. Documented in `INDEX_POLICY.md` §6.3.

---

## 7. Cleanup proof

```
=== databases on this server (owner) ===
    assy_manager / owner: postgres
    assy_qa      / owner: postgres          <- probe DB assy_f6_e47e3a33 is gone

=== assy_manager CLEANUP PROOF (pg_indexes / pg_tables) ===
   f6p* cost-probe indexes           : NONE
   *_declared_key indexes            : NONE
   f5p* (previous round)             : NONE
   f6p* probe tables                 : NONE
   f6demo* demo tables               : NONE
   f5_probe* (previous round)        : NONE
   total indexes on the 18 declared tables: 176      <- unchanged, no DDL

=== assy_qa CLEANUP PROOF ===
   (same six lines, all NONE)
   total indexes on the 18 declared tables: 155      <- as found (155 -> 145 -> 155)
```

`assy_manager` was only ever opened with `set_session(readonly=True)` / `db_safety.open_readonly_engine`,
which makes DDL fail at the server rather than relying on discipline. No process on `:8080` or `:8021`
was restarted; `client2/**` and `server/scripts/` were not touched.

---

## 8. History entry — draft (not written; index not regenerated, three lanes are live)

> **`feat(schema): the builder stops reading a list and starts reading the declaration`**
>
> `init_dynamic_models` attached a hardcoded set of indexes to every dynamic table and never read
> `map_key_columns` at all — the audit half of every table was indexed automatically and the half the
> read path actually filters on was indexed by whoever remembered. It now derives one
> `idx_<table>_declared_key` from `map_key_columns` → `composite_key_source` → a single-column
> `business_key`, and that order is not cosmetic: the naive `map_key_columns` rule would have missed
> the busiest index in the system, because the table that carries it (`wafer_map_metadata`,
> 44,103 scans) declares no map key. The rule retro-predicts, column for column, all three predicate
> indexes humans had already built by hand.
>
> The same blindness has a reverse face and it is retired in the same change: `ix_<t>_created_at` read
> zero on 35 of 36 (table, database) pairs and `idx_<t>_bk` read zero on every one, both maintained on
> every insert of every table. The two retirements pay for the new index and then some — measured
> −80.9 B/row of WAL and −11.8% insert time on the `bonding_log` shape, and still negative
> (−28.6 B/row) on the widest key in the config. Existing databases move via
> `align_indexes_to_declarations.py`, which re-proves every action against the live catalogue and
> refused eleven of them across the two dev copies rather than trusting a list validated elsewhere.

---

## 9. Proposed lessons for `agent_workspace/memory/server-pm.md` (not added directly)

- **함정**: 어제 라운드의 조사 보고서를 **오늘의 사실**로 인용한다. 이 라운드에서 F5 조사의 문장 아홉
  개가 반나절 만에 낡았다 — 표가 17 → 18로 늘었고(다른 레인이 등록), 「가장 시급」이라던 `uq_bk_*`
  부재는 **이미 해소**돼 있었으며, 스캔 수는 6시간 만에 4,949 → 28,027로 움직였다. 그중 둘은
  **판정을 바꾸는** 항목이었다.
  **올바른 방법**: 조사 보고서는 **가설의 출처**이지 사실의 출처가 아니다. 착수 첫 동작으로 그
  보고서의 수치를 **라이브에서 다시 뜬다**. 특히 「없다·전부·유일」류 전칭 문장은 반드시 재측정한다.
- **함정**: 「전 표에서 스캔 0」 같은 **전칭 명제를 한 DB에서 확인하고 마이그레이션에 하드코딩**한다.
  이번에 36개 (표, DB) 쌍 중 **정확히 하나**가 0이 아니었고(`assy_qa`의 `production_plan`),
  하드코딩 DROP 목록이었다면 그 박스에서 틀렸을 것이다.
  **올바른 방법**: 파괴적 동작은 **대상 DB에서 런타임에 다시 증명**하고, 증명 실패는 **이름과 이유를
  찍고 거절**한 뒤 나머지를 계속 진행한다(`drop_redundant_layering_indexes` 선례).
- **함정**: 인덱스 비용을 「추가 인덱스 하나」로만 재고 **은퇴분을 안 뺀다.** 그러면 순비용이 음수인
  변경이 「+13% 비용」으로 보고돼 승인 논쟁이 생긴다.
  **올바른 방법**: 인덱스 변경은 **집합 대 집합**으로 잰다(오늘 8개 vs 제안 7개). 그리고 문장 단위
  WAL은 `EXPLAIN (ANALYZE, WAL)`로 뜬다 — `pg_current_wal_lsn()` 차분과 달리 **동시 워크로드에
  오염되지 않는다**(PG 13+).
- **함정**: config 선언에서 파생하는 규칙을 만들 때 **가장 뜨거운 소비자가 그 선언을 «안» 하는 경우를
  못 본다.** 이번 시스템 최다 스캔 인덱스(44,103회)가 정확히 그 경우였다.
  **올바른 방법**: 선언 기반 규칙은 **이미 손으로 만들어진 것들을 재현하는지**로 검산한다. 셋 중 셋을
  컬럼까지 재현하면 규칙이고, 하나라도 못 내면 그건 규칙이 아니라 취향이다.
