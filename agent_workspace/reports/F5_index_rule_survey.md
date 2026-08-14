# F5 — The index rule: mechanism, gap table, and cost

**Ruling:** R-2026-08-14-A F5 (`docs/process/LEDGER_RULINGS.md:305`, commit `e58e884`) — *do not add
the index, find the rule.* This is an investigation. **Nothing was fixed, no index was created on
`assy_manager`, no config or code was changed, nothing was committed.**

**Measurement provenance.** All `assy_manager` figures are from a read-only session
(`psycopg2 set_session(readonly=True)`). Probe DDL ran **only** on `assy_qa`, in a throwaway probe
table, and was dropped — proof in §6. This box is not production (`this-box-is-not-production`);
every number below describes the owner's dev copy.

---

## 1. Verdict on the mechanism

**The ruling's suspicion is half right, and the half it gets wrong changes the repair.**

There is not one mechanism. There are two, and they have opposite characters:

| | **A — framework indexes** | **B — predicate indexes** |
|---|---|---|
| Who creates them | `models.init_dynamic_models` | humans, per feature |
| Coverage | **every** dynamic table, automatically | opt-in, one table at a time |
| Driven by | a hard-coded column list | whatever the author remembered |
| Reads `map_key_columns`? | **never** | no — column names are re-typed by hand |
| Landed on `assy_manager` | 8–9 per table, all 17 tables | **3 indexes on 3 tables** |

So the observed shape — audit columns indexed, query predicate not — is **real and it is a rule**,
but it is not one rule producing both halves. It is one automatic mechanism producing the audit
half universally, and the **absence of any mechanism** for the other half. The predicate half is
manual, and manual work has the coverage you would expect from manual work.

### 1a. Mechanism A — the builder, and the fixed set

`server/database/models.py:763` `init_dynamic_models`. Every dynamic table gets exactly this,
regardless of what the table is for:

```python
columns = [
    Column("row_id", String, primary_key=True),
    Column("business_key_val", String, index=True, nullable=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), index=True),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), index=True),
    Column("is_graph_synced", Boolean, default=False, nullable=True, index=True),
    Column("needs_graph_rollback", Boolean, default=False, nullable=True, index=True),
    Column("graph_synced_at", DateTime(timezone=True), nullable=True),
]
...
table_args = (
    Index(f"idx_{table_name}_bk", "business_key_val", "row_id"),
    Index(f"idx_{table_name}_updated", "updated_at", "row_id"),
)
```

That is **8 indexes per table**: 1 pkey + 5 single-column `ix_<t>_<col>` + 2 composites. The user
columns are appended immediately below (`models.py:823-834`) and **not one of them ever receives an
index** — the loop only maps a type and appends a bare `Column`.

**The set is written down in exactly one place: that literal list.** There is no config key, no
policy table, no doc that declares it. `init_dynamic_models` reads only `column_types`,
`business_key` and `composite_key_*` from `table_config.json` (confirmed in
`docs/architecture/CODE_MAP.md:1233`). **`map_key_columns` is never read by the builder** — grep for
it returns map/chain/alignment call sites only, never `models.py`.

The 8-vs-9 discrepancy: 12 tables also carry `ix_<t>_row_id`, a duplicate of the pkey. `models.py:800`
carries a `[D3]` comment retiring that declaration and stating it produced 26 of 29 measured
duplicates. The 5 tables **without** it (`core_usage_map`, `dt_core_view`, `dt_inventory`,
`inspection_run`, `void_obs`) are the ones created after the retirement. `create_all` never drops
indexes, so the other 12 keep theirs. (The exact retirement commit is not established; the
mechanism is, and is self-consistent with which tables carry it.)

### 1b. Mechanism B — and the proof that it is not a mechanism

Six hand-written artefacts declare predicate indexes:

- `server/scripts/setup_bonding_plan_indexes.py` (5)
- `server/scripts/setup_transfer_plan_indexes.py` (8)
- `server/migrations/add_core_wafer_map_key_index.sql` (1)
- `server/migrations/add_bonding_base_join_index.sql` (1)
- `server/migrations/add_dt_log_trigger_indexes.sql` (3, header says **NOT RUN**)
- `server/migrations/add_void_schema_indexes.sql` (4)

**Which of the 16 declarations actually exist, measured on both dev copies:**

| Index | Table | `assy_manager` | `assy_qa` | Declared in |
|---|---|---|---|---|
| `idx_core_wafer_map_map_key` | core_wafer_map | **PRESENT** | absent | `add_core_wafer_map_key_index.sql` |
| `idx_wafer_map_metadata_target_map` | wafer_map_metadata | **PRESENT** | absent | `setup_bonding_plan_indexes.py` |
| `idx_map_split_registry_ref_map` | map_split_registry | **PRESENT** | absent | `setup_transfer_plan_indexes.py` |
| `idx_bonding_log_base_position` | bonding_log | absent | **PRESENT** | `add_bonding_base_join_index.sql` |
| `idx_void_obs_run` | void_obs | absent | **PRESENT** | `add_void_schema_indexes.sql` |
| `idx_void_obs_package` | void_obs | absent | **PRESENT** | `add_void_schema_indexes.sql` |
| `idx_void_obs_area` | void_obs | absent | **PRESENT** | `add_void_schema_indexes.sql` |
| `idx_inspection_run_layer` | inspection_run | absent | **PRESENT** | `add_void_schema_indexes.sql` |
| `idx_dt_log_dt_job` | dt_log | absent | absent | `add_dt_log_trigger_indexes.sql` |
| `idx_dt_log_eqp_product` | dt_log | absent | absent | 〃 |
| `idx_dt_map_dt_job` | dt_map | absent | absent | 〃 |
| `idx_bonding_log_core_lot_slot` | bonding_log | absent | absent | `setup_bonding_plan_indexes.py` |
| `idx_dt_map_lot_slot` | dt_map | absent | absent | `setup_transfer_plan_indexes.py` |
| `idx_dt_log_tape_lot_slot` | dt_log | absent | absent | 〃 |
| `idx_dt_log_core_lot_slot` | dt_log | absent | absent | 〃 |
| `idx_bonding_map_base` | bonding_map | absent | absent | 〃 |

🔴 **The two dev databases' hand-added index sets are DISJOINT.** `assy_manager` has three that
`assy_qa` lacks; `assy_qa` has five that `assy_manager` lacks; the intersection is empty. Nine of
sixteen declarations exist nowhere. **No mechanism produces a result like this.** If a builder,
migration runner, or setup script owned predicate indexes, the two copies would converge. They
diverge completely, which is the signature of per-box, per-lane, hand-run DDL.

Two further symptoms of hand-authorship — the scripts have **drifted from the config they serve**:

- `setup_transfer_plan_indexes.py:32` declares `idx_dt_map_lot_slot ON dt_map (lot, slot)`. `dt_map`'s
  declared `map_key_columns` is `["dt_lot", "dt_slot"]`. The columns `lot`/`slot` do not exist on
  that table, so the statement could only ever have failed.
- `setup_bonding_plan_indexes.py:22` declares `idx_bonding_log_core_lot_slot ON bonding_log
  (core_lot, core_slot)`. `bonding_log`'s map key is `["bond_lot", "bond_slot"]`.
- `setup_transfer_plan_indexes.py` also names four tables that are not registered at all
  (`core_defect_map`, `eds_fail_map`, `map_source_region`, `sample_map`) — those rows can only print
  `[skip]`.

**Answer to the ruling's question, in one line:** the audit half is a mechanism with a hard-coded
list in `models.py:800-822`; the predicate half is not a mechanism at all, and the observation that
"twice is a rule" is correct because the rule is *nothing indexes the predicate unless a human
remembers to*.

---

## 2. The full gap table

Row counts are from `assy_manager` on 2026-08-14. **Fixture disclosure** (board ⚠️ block,
`docs/process/PROJECT_STATUS.md:1-45`): `void_obs` and `inspection_run` are 100 % synthetic,
`bonding_log` 98.5 %, `wafer_map_metadata` 72.9 %. Rows marked 🧪 include fixture; the real figure
follows in the note column where it changes the verdict.

`distinct` = number of distinct predicate values (i.e. number of maps). `rows/key` = average
selectivity of one predicate lookup. Index scan counts are `pg_stat_user_indexes.idx_scan`;
`stats_reset` is NULL and postmaster started **2026-08-13 08:37 KST**, so the window is roughly one
day of dev-box workload — good for *which* indexes are used, useless as a production volume claim.

| # | Table | Rows | Declared `map_key_columns` | Hot read predicate (from code) | Covering index? | distinct / rows-per-key | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | `core_wafer_map` | 24,749 | `core_lot, core_slot` | `WHERE core_lot=? AND core_slot=?` — `map_alignment._cells_of`:5028, `_count_cells`:6495, `map_overlay.get_overlay`:1994, `crud.derive_replace_map_scope` DELETE:3186 | ✅ `idx_core_wafer_map_map_key` | 203 / 121.9 | **COVERED.** 4,949 scans — the busiest index on the table. Landed `4ed34a9`. |
| 2 | `wafer_map_metadata` | 3,431 🧪 | *(none)* | `WHERE target_table=? AND map_id=?` — `map_overlay._meta_select`:300, `map_alignment`:6533, :6348 | ✅ `idx_wafer_map_metadata_target_map` | 3,431 / 1.0 | **COVERED.** 32,046 scans — hottest index in the whole registered set. Real rows 931, all unique. ⚠️ not UNIQUE — see §5. |
| 3 | `map_split_registry` | 162 | `ref_table, map_key` | `WHERE ref_table=? AND map_key=?` — `main.py`:5232, `transfer_plan.py`:927 | ✅ `idx_map_split_registry_ref_map` | 69 / 2.3 | **COVERED.** 17 scans. Tiny table; index harmless either way. |
| 4 | `bonding_log` | 357,796 🧪 | `bond_lot, bond_slot` | map key via `build_key_filters`; **and** `(base_id, bx, by)` for the void→die join (`add_bonding_base_join_index.sql`) | ❌ **none** | 2,620 / 136.6 (real: 120 / 44.1) | 🔴 **GAP, and the only one that is large today.** 350 MB heap+idx. Real data is 5,296 rows / 120 maps; the 2,620-map figure is the fixture. Also missing `idx_bonding_log_base_position`, which `assy_qa` has. |
| 5 | `dt_log` | 13,789 | `dt_job` | `WHERE dt_job=?` and `WHERE dt_eqp=? AND product=?` — both named in `add_dt_log_trigger_indexes.sql`, both live in `dt_map_mapper.py`:187, `dt_standard_map_mapper.py`:178 | ❌ **none** | 246 / 56.1 | 🟡 **GAP, small today.** The migration that fixes it exists and its own header says **NOT RUN**. 20 MB. |
| 6 | `dt_map` | 5,619 | `dt_lot, dt_slot` | map key; **and** `WHERE dt_job=?` for retraction (`dt_map_derivation.py`:779) | ❌ **none** | **2** / 2809.5 | ⚪ **Gap is nominal.** Two distinct map keys in the whole table — a btree on 2 values cannot beat a seq scan. `dt_job` is the predicate that would actually pay. |
| 7 | `valid_die_ref` | 4,598 | `product, type` | `WHERE product=? AND type=?` — the floor table, `_cells_of` / `_count_cells` / `_count_cells_bulk` | ❌ **none** | **8** / 574.8 | ✅ **Ruling F5 was right, and here is the number.** 8 distinct values over 97 pages: 12.5 % selectivity, well past the point where the planner prefers a seq scan. An index here is write cost for no read. |
| 8 | `core_usage_map` | 366 | `core_wafer` | map key; replace_map scope (`core_usage_mapper.py`:84) | ❌ **none** | **2** / 183.0 | ⚪ 14 pages. Nothing to index. |
| 9 | `dt_core_view` | 366 | `dt_job` | map key + replace_map scope | ❌ **none** | 6 / 61.0 | ⚪ 22 pages. Nothing to index. |
| 10 | `bonding_map` | 413 | `base` | `WHERE base=?`; also `lower(base) COLLATE "C"` prefix in `value_suggest.py` | ❌ **none** | **1** / 413.0 | ⚪ One distinct value here. ⚠️ *but* `value_suggest.py` cites a 1.75 M-row `bonding_map` elsewhere — this box's copy is not representative. Re-measure before ruling. |
| 11 | `inspection_run` | 77,500 🧪 | *(none)* | `(base_wafer_id, base_x, base_y, stack_gate, observed_at DESC)` — `add_void_schema_indexes.sql` §3 | ❌ **none** | — | 🔴 **GAP by row count (47 MB), but 100 % fixture — zero real rows.** The fix exists and is applied on `assy_qa`. |
| 12 | `void_obs` | 91,756 🧪 | *(none)* | `WHERE run_uid=?`; `(base_wafer_id, base_x, base_y, stack_gate)` — same migration §2/§4 | ❌ **none** | — | 🔴 **Same shape, same caveat: 100 % fixture, zero real rows.** Three indexes exist on `assy_qa`, none here. |
| 13 | `lot_event` | 44 | *(none)* | `event_time > ?` ORDER BY `(event_time, row_identity)` — `ledger/backfill.py`:86 | ❌ **none** | — | ⚪ 44 rows. Revisit only when the ledger backfill runs at scale. |
| 14 | `dt_inventory` | 251 | *(none)* | `<job column> IN (...)` — `core_usage_mapper.py`:164 | ❌ **none** | — | ⚪ 251 rows. |
| 15 | `wafer_id_status` | 59 | *(none)* | **no read filter found anywhere in live code** | ❌ **none** | — | ⚪ No predicate to cover. |
| 16 | `production_plan` | 10 | *(none)* | **no read filter** — mapper reads the outbox payload only | ❌ **none** | — | ⚪ Nothing to index. |
| 17 | `inventory_master` | 15 | *(none)* | `business_key_val` only | ✅ framework | — | ⚪ Already covered. |

**Summary of the gap: 14 of 17 registered tables carry zero non-framework indexes.** Of the 14, the
gap is materially expensive on **one** table with real data (`bonding_log`), marginal on one
(`dt_log`), fixture-only on two (`void_obs`, `inspection_run`), and **nominal or actively harmful**
on the remaining ten because their predicate cardinality is in the single digits.

### 2a. Are the framework indexes earning their keep?

The same survey answers the converse question, and the answer is the more interesting one.

| Framework column | Real predicate? | Where | Scans (24 h, all 17 tables) |
|---|---|---|---|
| `business_key_val` | ✅ yes, hot | `crud.get_row_by_business_key`:1253, `_get_or_create_row`:2190, `_find_business_key_conflict`:2251 | 541 |
| `updated_at` | ⚠️ marginal | one `WHERE updated_at >= ?` in `graph_sync_worker.py`:813, inside a function marked **`[DEPRECATED — C-7]`** (:757); otherwise only opt-in `?order_by=` | 32 |
| `is_graph_synced` | ⚠️ marginal | `graph_sync_worker.py`:788 — **same deprecated function** | 27 |
| `needs_graph_rollback` | ⚠️ marginal | 〃 | 27 |
| `created_at` | ❌ **none** | **no filter on any dynamic table.** Every `created_at <` hit is on `DatabaseOutbox` | **0** |

`ix_<t>_created_at` has **zero scans on all 17 tables** and is maintained on every insert of every
one of them. `idx_<t>_bk` is at zero on 16 of 17 (the single-column `ix_<t>_business_key_val` wins
the lookups). On `core_wafer_map` specifically, **five of the ten indexes have never been scanned**
— `pkey`, `idx_bk`, `ix_business_key_val`, `ix_created_at`, `ix_updated_at` — while the one
hand-added index took 4,949 scans.

That is the finding underneath the ruling's observation: the system is **not** merely missing
predicate indexes, it is **paying for audit indexes nobody reads**. Both halves are the same defect
— a fixed list nobody has re-derived from live predicates.

---

## 3. The third table — prediction and result

**Prediction, recorded before querying** (in the working transcript, before the index dump was
read): *if the rule is real, `core_usage_map` — the map-layer sibling of `core_wafer_map`, same
layer, same query shape, nobody has looked at it — will show the same framework set and nothing on
its declared `map_key_columns` (`core_wafer`).*

**Result: confirmed.** `core_usage_map` carries 8 indexes — `pkey`, `idx_bk`, `idx_updated`, and
`ix_*` on `business_key_val`, `created_at`, `updated_at`, `is_graph_synced`, `needs_graph_rollback`.
**Zero** cover `core_wafer`.

**The prediction generalised further than asked, and that is the stronger result:** the same check
run across all 17 tables found the shape on **14 of them**, not three. The three exceptions are
exactly the three tables where a human ran a script (§1b). The hypothesis is not "a third table
looks like this" — it is "**every** table looks like this unless someone intervened by hand", and
the intervention list is short enough to enumerate.

**One way the prediction was wrong, and it matters.** I predicted the gap would be against
`map_key_columns`. On the two tables with the *hottest* predicate indexes, the covered predicate is
**not** `map_key_columns`: `wafer_map_metadata` (32,046 scans) declares no `map_key_columns` at all
and is read by `(target_table, map_id)` — its `composite_key_source`. So a canon rule phrased as
"index every table's `map_key_columns`" would have **missed the single most-read predicate in the
system** and indexed ten tables that do not need it. The predicate that matters is *the one the read
path issues*, and `map_key_columns` is only sometimes that.

---

## 4. Cost

Measured on `assy_qa` in a probe table built with `LIKE bonding_log`, the 8 framework indexes plus
pkey, versus the same plus one `(bond_lot, bond_slot)` index. 40,546 rows inserted per run,
5 alternating rounds for timing, `ANALYZE` after load (a temp table has no statistics — that error
has been made here before).

| Metric | Framework only (9 idx) | + map-key (10 idx) | Marginal cost of the 10th |
|---|---|---|---|
| INSERT time, median of 5 | 1.529 s | 1.729 s | **+13.1 %** (min-to-min +14.5 %) |
| WAL generated | 46,827,200 B | 49,859,232 B | **+3,032,032 B = +74.8 B/row (+6.5 %)** |
| Index storage | 16,465,920 B | 16,793,600 B | +327,680 B = **+8.1 B/row** |

Timing samples: framework `1.655 / 1.462 / 1.514 / 1.846 / 1.529`; +map-key `1.674 / 1.825 / 1.696 /
1.729 / 2.033`. The distributions overlap at the edges, so treat **+13 %** as the honest figure and
**WAL as the decidable one** — WAL was byte-identical across repeat runs (46,827,280 / 46,827,200).

**+74.8 B/row of WAL is the number to rule on**, and it sits right next to the ledger's +95 B/atom
precedent the ruling cites. Note the gap between WAL (+74.8 B/row) and storage (+8.1 B/row): btree
deduplication compacts a low-cardinality key on disk, but **the write path pays the full record
regardless**. Sizing an index by `pg_relation_size` understates its write cost by ~9× on this shape.

### Which tables cannot afford it

Ingestion targets, where an extra index is paid on every ingested row and a lock is a stalled lane
(`add_core_wafer_map_key_index.sql:21` states this in its own header):

- 🔴 **Highest churn — `replace_map` deletes the whole map then reinserts it**: `dt_map`,
  `dt_core_view`, `core_usage_map`. Every index is rewritten for every row of every touched map.
  These are also the three with 2, 6 and 2 distinct map keys — **worst cost, least benefit.**
- 🔴 **Parser targets**: `void_obs`, `inspection_run`, `core_wafer_map`, `bonding_log`, `dt_log`,
  `lot_event`, `bonding_map`.
- 🟡 **Chain targets**: `dt_inventory`, `inventory_master`, `wafer_map_metadata` (auto-registered per
  ingested map).
- ⚪ **Read-mostly, an index is nearly free**: `valid_die_ref` (product-owned floor, seeded),
  `map_split_registry`, `production_plan`, `wafer_id_status`.

The irony worth putting in front of the ruling: **`valid_die_ref` is one of the few tables where an
index costs almost nothing** — and it is also the one where it would buy almost nothing (8 distinct
values). F5's "not now" holds for the benefit reason, not the cost reason.

---

## 5. Flagged, not fixed

1. 🔴 **`assy_manager` has no `uq_bk_*` unique index on any of the 17 tables.** `assy_qa` has two
   (`uq_bk_void_obs`, `uq_bk_inspection_run`). `models.py:806-813` explains this by design — the
   builder keeps `business_key_val` non-unique and delegates enforcement to
   `server/migrations/add_business_key_unique_index.py` — and the same comment warns that *"a
   FRESHLY created database is unprotected until the migration is run."* On the owner's working
   database that migration has not been run for any table. This is an identity-integrity gap, not a
   performance one, and it is a bigger finding than anything in the gap table. **Not repaired —
   reporting per instruction.**
2. 🔴 **`wafer_map_metadata` has no unique index on `(target_table, map_id)`** despite it being the
   most-scanned predicate in the system (32,046 scans). Flagged independently at
   `server/map_overlay.py:292` and `server/map_alignment.py:6343` as an R6/R7 hazard: the same map
   can read different geometry between refreshes.
3. 🟡 **`setup_transfer_plan_indexes.py` and `setup_bonding_plan_indexes.py` are stale.** Four of
   their declarations name unregistered tables and two name columns that do not exist
   (`dt_map (lot, slot)`, `bonding_log (core_lot, core_slot)`). They print `[skip]`/`[fail]` and
   continue, so running them looks like success. A permanent `[skip]` teaches the operator to ignore
   skips — a lesson `setup_transfer_plan_indexes.py:34` already wrote down about a different row.
4. 🟡 **`add_dt_log_trigger_indexes.sql` says NOT RUN and is still not run**, on either dev copy,
   while its three predicates are live in the mappers.
5. 🟡 **`ix_<t>_created_at` on all 17 tables has zero scans and zero known predicates.** So does
   `idx_<t>_bk` on 16 of 17. Retirement candidates with a measured basis.
6. ⚠️ **`_count_cells_bulk` (`map_alignment.py`:6456) issues `GROUP BY <key cols>` with no `WHERE`**
   — a full scan of the floor table per catalog request. This is the statement `valid_die_ref` takes
   once per catalog request, and it is the one predicate on that table an index *could* help
   (GroupAgg instead of HashAgg), independent of the 8-value selectivity argument. Commit `4ed34a9`
   measured that swap on `core_wafer_map` as 7.9 ms → 4.8 ms.

---

## 6. Cleanup proof

Probe objects existed only on `assy_qa`: table `f5_probe_bonding`, indexes `f5p_bk`, `f5p_upd`,
`f5p_ix_bkv`, `f5p_ix_cre`, `f5p_ix_gs`, `f5p_ix_ngr`, `f5p_ix_rid`, `f5p_ix_upd`, `f5p_mapkey`.
Final query at the end of both probe runs:

```
=== CLEANUP PROOF (pg_indexes / pg_tables on assy_qa) ===
  leftover probe indexes: NONE
  leftover probe tables : NONE
```

`SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'f5p%'` → 0 rows.
`SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'f5_probe%'` → 0 rows.

**`assy_manager` received no DDL of any kind.** Every connection to it was opened with
`set_session(readonly=True)`, which makes DDL fail at the server rather than relying on discipline.
Databases present after the round: `assy_manager`, `assy_qa` — no probe DB was created.

---

## 7. What is decidable from these numbers

Offered as the input the ruling asked for, not as a recommendation to act on.

**On canon promotion of an index policy — the numbers say a `map_key_columns`-driven rule should
NOT be promoted**, for three measured reasons:

1. It would index ten tables whose predicate cardinality is 1–8 distinct values, at +74.8 B/row of
   WAL each, three of them on the `replace_map` delete-and-reinsert path.
2. It would **miss** the most-read predicate in the system (`wafer_map_metadata`, no
   `map_key_columns` declared, 32,046 scans), and the second-most-read one on `dt_log`/`dt_map`
   (`dt_job` on `dt_map`, whose declared map key is `dt_lot, dt_slot`).
3. The measurement that would justify it — scans per index — already exists and disagrees with the
   declaration: the framework list it would extend has an index with **zero** scans on all 17 tables.

**What the numbers do support**, if the ruling wants a rule rather than a policy: a **gate, not a
generator**. The evidence for it is that nine of sixteen hand-written declarations exist on neither
database and two name columns that do not exist. A check that reads `pg_indexes` against the
predicates the code issues and *reports* the gap would have caught every item in §5 without creating
a single index. `server/scripts/audit_schema_canon.py` already walks `table_config` and buckets
findings, including a `no_map_key_columns` bucket at :676 — this is a bucket in an existing tool,
not a new mechanism.

**Per-row verdicts for the ruling to rule on** (row numbers refer to §2):

| Row | Table | Recommendation | Basis |
|---|---|---|---|
| 4 | `bonding_log` | **The one real candidate.** But re-measure on real data first — 98.5 % of this table is fixture, and real data is 5,296 rows / 120 maps. | 350 MB, but real footprint unknown |
| 5 | `dt_log` | Run the existing `add_dt_log_trigger_indexes.sql` when the triggers are enabled — not before. Its header already says so. | predicates live, table 13.8 k rows |
| 7 | `valid_die_ref` | **Confirm F5's "not now."** 8 distinct values / 97 pages. | selectivity 12.5 % |
| 6, 8, 9, 10 | `dt_map`, `core_usage_map`, `dt_core_view`, `bonding_map` | **Do not index the map key.** 1–6 distinct values, and all four are `replace_map` churn targets. | worst cost / least benefit |
| 11, 12 | `inspection_run`, `void_obs` | Apply `add_void_schema_indexes.sql` to `assy_manager` **only if** the two copies are meant to converge — today the rows are 100 % fixture, so nothing real is being scanned. | zero real rows |
| — | `ix_<t>_created_at` (×17) | Retirement candidate. Zero scans, zero known predicates, paid on every insert of every table. | measured |
| — | `uq_bk_*` (§5.1) | **Separate and more urgent than any of the above** — this is identity enforcement, not performance. | absent on all 17 |

---

## Proposed lessons (for `agent_workspace/memory/server-pm.md` — not added directly)

- **함정**: 인덱스의 존재를 «선언»에서 읽는다. 마이그레이션 산문과 셋업 스크립트는 무엇을
  만들려 했는지 말할 뿐 무엇이 있는지는 말하지 않는다 — 이번 라운드에서 손으로 선언된 16개 중
  9개가 **양쪽 DB 어디에도 없었고**, 두 개발 DB의 수동 인덱스 집합은 **교집합이 공집합**이었다.
  **올바른 방법**: 인덱스 유무는 `pg_indexes`로 «각 DB마다» 실측한다. 그리고 두 개발 사본이
  갈라져 있을 수 있다는 것을 기본 가정으로 둔다.
- **함정**: 인덱스 비용을 `pg_relation_size`로 잰다. 저(低)카디널리티 키는 btree 중복제거로
  디스크에서 압축돼(+8.1 B/행) **쓰기 비용(+74.8 B/행 WAL)을 9배 과소평가**한다.
  **올바른 방법**: 쓰기 비용은 `pg_current_wal_lsn()` 차분으로 잰다 — 반복 실행에서 바이트가
  동일해 시간보다 판정 가능하다.
- **함정**: 「선언된 키」를 「뜨거운 술어」와 동일시한다. 이 시스템에서 가장 많이 스캔된 인덱스
  (32,046회)가 붙은 표는 `map_key_columns`를 **선언하지 않는다**. 선언 기반 규칙이었다면 그
  술어를 놓치고 쓸모없는 표 열 개에 인덱스를 얹었을 것이다.
  **올바른 방법**: 술어는 config가 아니라 **읽기 경로 코드**에서 도출하고, `idx_scan`으로 검산한다.
