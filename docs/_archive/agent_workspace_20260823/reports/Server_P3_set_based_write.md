# P3-IMPL — the set-based write path

**Lane:** P3 (queue item 2, phase 2) · **Tier:** T2 (adversarial QA follows) · **Date:** 2026-08-07
**Box:** this workstation, isolated `assy_qa` snapshot + `dev_env` config copy. **Nothing here is a
claim about production.** `assy_manager` was read for schema metadata only and never written.
**Not committed.** `git add <path>` discipline observed; no `-a`/`-A`.

---

## 0. Headline

Same input as the profiling round — one 100,000-row / 3 MB map file through
`crud.apply_batch_updates` in 1,000-item chunks, exactly the shape `directory_watcher` sends,
probe table reset to empty before each run so both are a **fresh insert**.

| | before | after | |
|---|---:|---:|---|
| wall clock | 796.2 s | **375.8 s** | **2.12×** |
| ms / row | 7.962 | **3.758** | |
| **SQL statements** | **301,100** | **1,200** | **251×** |
| **statements / row** | **3.011** | **0.012** | |
| data rows written | 100,000 | 100,000 | identical |
| `cell_sources` | 700,000 | 700,000 | identical |
| `audit_logs` | 100,000 | 100,000 | identical |
| `database_outbox` | 100,000 | 100,000 | identical |

The before-run reproduces the profile (729 s / 301,222 / 3.01 there; 796 s / 301,100 / 3.011 here —
same shape, this box 9% slower on the day, other lanes were active).

Statement census after, per 1,000-row chunk: **1** prefetch SELECT + **1** data INSERT + **7**
`cell_sources` INSERT + **1** `audit_logs` + **1** `database_outbox` + **1** NOTIFY = 12.
Before, the same chunk cost 3,011.

Naive extrapolation to ten million rows on this box: **22.1 h → 10.4 h**. The profile's stated
honest ceiling was 2.5–3×; this is 2.12×, and §6 says where the rest went and why I stopped.

---

## 1. Path correction confirmed, and the stale anchor located

The file is `server/database/crud.py`. Every anchor in the brief verified before editing.
**The audit cap the profile mis-cited:** `MAX_AUDIT_VALUE_CHARS = 4096` is **not in `crud.py` at
all** — it is defined at **`server/event_constants.py:69`** together with `truncate_audit_value`
(`:72`), imported by `crud.py:34`/`:38`, and **applied at `crud.py:1117-1118`** inside
`create_audit_log`. The brief's `crud.py:224-236` is inside **`parse_version_key`** (defined at
`crud.py:194`) — there is no `_parse_version` in the file; that name has drifted too.

---

## 2. What changed, and why each is safe

All in `server/database/crud.py`. No signature of any public function changed; the two new
parameters are keyword arguments defaulting to `None`, so every caller outside the batch loop
behaves exactly as before.

### 2.1 `ProbedIdentity` — identity resolved set-wise (removes 2 of the 3 per-row statements)

`apply_batch_updates` already runs one prefetch per chunk:
`row_id IN (target_ids) OR business_key_val IN (target_bks)`. It now also computes the values that
came back **empty**, and hands that to the loop:

```python
_found_ids = {r.row_id for r in existing_rows_list}
_found_bks = {r.business_key_val for r in existing_rows_list if r.business_key_val}
probed_identity = ProbedIdentity(
    row_ids=frozenset(target_ids) - _found_ids,
    business_keys=frozenset(target_bks) - _found_bks,
)
```

🔴 **The subtraction is the whole correctness argument, and my first draft did not have it.**
Without it the sets say "we asked", and the consumers then have to lean on `row_cache` to know
whether an answer came back — but **the loop mutates `row_cache`**: renaming a row's business key
deletes the old key from it. A later item in the same batch naming that old key finds the cache
empty, reads "we asked" as "nothing exists", and mints a duplicate row where today's code resolves
onto the renamed one. With the subtraction the sets are a statement about the **database at
prefetch time**, which nothing in the loop can change (nothing is flushed inside `no_autoflush`).
**I measured that duplicate** — see §3.1.

Two gates were closed, not one — the brief was right that fixing only `_get_or_create_row` leaves
most of the 49.6% standing:

* `_get_or_create_row` → `get_row_by_business_key` (`crud.py:1041`).
* the **composite-key collision probe**, now extracted as `_find_business_key_conflict`. It fires
  on every row of a map file whose payload carries the key column **empty**: the row is created
  with `business_key_val=''`, which never equals the assembled key, so `current_bk != new_bk_val`
  on every row. Its skip is deliberately more conservative than the other one — **any** entry in
  `row_cache` for that key sends the call to the database unchanged, because the column has no
  unique index and a second holder the cache overwrote must still be merged.

### 2.2 The ORM flush now batches (removes the third)

`_get_or_create_row` no longer sets `updated_at=func.now()` on the new instance. The column carries
`server_default=func.now()`, so an INSERT that omits it stores **the same transaction timestamp
from the same database clock** — the stored value is unchanged. What changes is that the parameter
set no longer contains a SQL expression, which is what stopped SQLAlchemy folding the rows into one
`insertmanyvalues` batch. The UPDATE path still sets it explicitly (`if not is_new:`).

The diagnosis came from the profile's own table: the **outbox rows written in the same flush** —
plain values, batchable — cost 8.2 s for 100,000 rows while the data rows cost 49.3 s for the same
count.

**Verified before relying on the default**: every `updated_at` column of every table in `assy_qa`
(24 declared + every other public table) carries a `DEFAULT`; zero exceptions. A probe asserts the
column lands non-NULL and within a second of `created_at`.

### 2.3 `bulk_upsert_cell_sources` / `_overwrites` — compile once, send parameters

`.values(chunk)` built a fresh multi-row VALUES clause and compiled it per chunk (163 s of the
223 s at 100k). The fast path builds the statement once and hands the driver a parameter list per
chunk. `_is_executemany_safe` gates it on two properties (uniform key sets, no `ClauseElement` in
any value) and otherwise **falls back to the exact old path**.

🔴 **`BULK_CHUNK_SIZE` chunking does not move.** It is the int16 parameter-count correctness bound
documented at its definition, and the fast path still hands `chunk_size` rows per call — what
changed is *how* they are sent, never *how many go at once*. The existing
`test_bulk_chunking_budget.py` assertions (`len(inserts_into(...)) == ceil(cells/1000)`) therefore
still hold: one `before_cursor_execute` per chunk, as before.

Three `func.now()` values the collision-merge path put into these dicts are now real datetimes —
which is what every other producer in the same function already wrote (`datetime.now()` at the
source and overwrite blocks).

### 2.4 The per-row Python: stop building mapped instances that are never persisted

A cProfile of the post-change run showed **45,000 ORM instance constructions per 5,000 rows** — 9
per ingested row, 7 of them `CellSource`. On the batch path those objects are **never added to the
session** (the write comes out of `cell_sources_to_upsert`); they exist only to join `col_srcs` for
`compute_priority_value`, which reads exactly the attributes `LightCellSource` carries — and which
is **already handed `LightCellSource` instances by the prefetch**. Same for `CellOverwrite`.

The mapped instance is still built when there is no accumulator (`cell_sources_to_upsert is None`),
because there that object *is* the write. This is what took the run from 425.5 s to 375.8 s.

---

## 3. Correctness — what was asserted, and where

**pytest was NOT run** (another lane owns it this round). Instead:

* **`server/tests/test_set_based_write_path.py`** — new, 14 test functions (18 cases with the parametrised one), written but not executed. It is
  handed over for the serialized suite run.
* **14 probes driven against real PostgreSQL** (isolated `assy_qa`), which is a stronger dialect
  than the suite's SQLite. All 14 pass. Scenarios: statement budget; fresh-insert identity;
  re-push updates rather than duplicates; a business key with surrounding whitespace; rename-then-
  old-key inside one batch; collision merge onto a row outside the prefetch; **`user` layer still
  beats a later `pipeline_parser` write and both layers are stored**; outbox event per new row with
  the right business key; audit row per ingested row; `updated_at` non-NULL; `user` push writes
  every overwrite marker and an unchanged re-push does not add more; bulk-upsert fallback on a SQL
  expression; ragged list still refused; ON CONFLICT still updates; chunk boundaries at 0 / 1 /
  999 / 1000 / 1001.
* **Old-vs-new differential runs** on the two paths where I suspected a behaviour change
  (`P3I_dbg_bk.py`, `P3I_dbg_collision.py`, `P3I_dbg_ow.py`): a copy of `crud.py` at HEAD was
  imported as a sibling module and driven through the same scenarios. Output identical in all
  three, including the two pre-existing defects in §5.

### 3.1 The nets were made to ring

Three defects were injected into the live module and the probe suite re-run:

| injected defect | must ring | result |
|---|---|---|
| collision probe always answers "no conflict" | `collision_merge_outside_prefetch` | rang, and only it |
| `probed_identity` built **without** the subtraction | `rename_then_old_key_no_duplicate` | rang, and only it |
| `_absence_is_proven` always true | (see below) | rang only the rename probe |

🔴 **The first two runs of this harness were SILENT, and that silence is what found the missing
subtraction.** Two mutations changed nothing observable because `row_cache` answers first on every
ordinary path — the same two-gate shape the memory file already records. Only after I built the
rename-inside-one-batch probe did the defect become visible; it is the **only** net over it, and
the report's own claim ("proved to ring") is written into that test's docstring so the next author
cannot mistake it for a routine assertion.

---

## 4. Failure shape for the six-plus callers of `apply_batch_updates`

**Nothing new can refuse.** This round added no raise, no validation and no new error path. The
funnel is unchanged in order and content:

1. `refuse_virtual_join_columns` is still the **first statement**, ahead of `transaction_context`
   and ahead of the `replace_map` purge — verified by reading, and by the `replace_map` diff probe
   still reporting `mode="diff"`, `deleted=6`.
2. The `replace_map` unresolvable-scope `ValueError` is unchanged.

So every caller sees exactly what it saw before: `main.py` maps `ValueError` → 400; the other
callers (`chain_ingestion_worker`, `chain_replay`, `enrichment_candidates`, `enrichment_backfill`,
`map_meta_registrar`, `frame_confirmation`, `parsers/directory_watcher`,
`scripts/seed_dt_index_walk`, `scripts/seed_valid_die_ref_floor`, `dt_map_derivation`) still let it
propagate as they do today. The 4-tuple return is unchanged, and the `replace_report` out-param
keys are unchanged.

The one behaviour that could in principle differ is the rename-inside-one-batch case in §2.1, and
the subtraction makes it identical to HEAD — asserted, with the defective version measured.

---

## 5. Found on the way — NOT fixed, and both reproduce identically on HEAD

These are pre-existing defects of the shared write path, both exposed by the very payload shape the
profile used (a map CSV that carries its business-key column **empty**). I verified each against a
HEAD copy of `crud.py`: byte-identical outcome, so neither is this round's doing.

1. 🔴 **A second push wipes `business_key_val`; a third push duplicates every row.**
   `_update_row_business_key` sets `row.business_key_val = ''` from the empty key column. On a
   *new* row the composite block then repairs it (`is_new` → recompute). On an *existing* row whose
   composite-source columns did not change, the block is skipped and the row is left with
   `business_key_val = ''` and its key column NULL. The next push cannot match it and creates a
   fresh row. Measured, 5 rows, three pushes: `rows=5 distinct_bk=5` → `rows=5 distinct_bk=1` →
   **`rows=10`**. Reproduction: `P3I_dbg_bk.py`.
2. **Collision merge leaves its shell row behind.** After switching onto the conflict row,
   `db.delete(row_to_delete)` is called on a still-**pending** instance inside a bare
   `except Exception: pass`; the object stays in `session.new` and is INSERTed. The merge itself is
   correct (the conflict row gets the new values); the discarded shell survives with
   `business_key_val = NULL`. Reproduction: `P3I_dbg_collision.py`.

**Isolated-environment gap (repaired, and worth a decision).** `assy_qa.cell_sources` was missing
`confirmation_uid` while `assy_manager` has it, so **any ORM read of `CellSource` against the
snapshot died with `UndefinedColumn`** — including `_load_metadata_row_cell`, i.e. the entire
collision-merge path and every non-batch cell read. The snapshot predates
`server/migrations/add_frame_confirmation.py`. I added **only that one column** (additive,
NULL-allowed, no default — catalog-only) rather than running the whole migration, because the
alignment lane is live in that area. Someone should decide whether `assy_qa` is refreshed or the
full migration is run there.

---

## 6. Reported, not fixed (as instructed) — and where the remaining time went

* **Storage.** One ingested row still writes ~10 rows / ~2.57 KB heap (1 data + 7 `cell_sources` +
  1 audit + 1 outbox), indexes ~2× heap. Ten million rows ≈ 100 million rows / ~50 GB against a
  14 GB production database. **This round makes it arrive sooner, not smaller.** A capacity decision
  for the product owner.
* **`cell_sources` is keyed by `source_name` = the file's basename**, so re-dropping identical
  content under a new filename adds a whole source layer (profile measured 14,000 `cell_sources`
  rows for 1,000 data rows after two drops).
* **`_classify_lane` routes on BYTES while cost is ROWS** (`directory_watcher.py:964`, `st_size`
  vs `heavy_file_mb`). At the new rate a 300,000-row / ~9 MB map CSV stays in the normal lane and
  blocks the dispatch thread ~19 minutes instead of ~36. Still the wrong axis.
* **Backpressure** (one file → 10M outbox rows, ~10 GB; purge capped at
  `OUTBOX_PURGE_CHUNK 1000 × OUTBOX_PURGE_MAX_CHUNKS 50` per `OUTBOX_PURGE_INTERVAL 3600 s` =
  50,000/hour, starting only after `OUTBOX_RETENTION_DAYS = 7`, all at
  `chain_ingestion_worker.py:182-185`) — **not started**, as instructed. 🔴 It is now the binding
  constraint: the producer got 2.1× faster and the drain did not move.

**Where the remaining 375.8 s is** (cProfile, 5,000-row run, 28.5 s total):

| | s | share |
|---|---:|---:|
| `psycopg2 cursor.executemany` (the `cell_sources` upsert, 35 calls) | 11.97 | 42% |
| `psycopg2 cursor.execute` (data INSERT + prefetch + audit + outbox) | 2.01 | 7% |
| `apply_row_update_internal` own Python (priority resolution, per-column dicts) | 1.54 | 5% |
| ORM attribute machinery (`__set__` ×335,000, `_initialize_instance` ×10,000) | ~2.5 | 9% |
| `auto_stage_database_outbox` + `stage_event` Python | 1.53 | 5% |

**Half the run is now the database actually writing `cell_sources`**, which is the shape you want
and the point at which further Python work stops paying. The next real lever is not a faster write
path — it is writing **fewer rows** (§ storage), which is the product owner's question.

---

## 7. Files

| path | what |
|---|---|
| `C:\Users\kk980\Developments\assyManager\server\database\crud.py` | the change (see §2) |
| `C:\Users\kk980\Developments\assyManager\server\tests\test_set_based_write_path.py` | new, 14 test functions, **not executed** |
| `C:\Users\kk980\Developments\assyManager\docs\architecture\backend.md` | §3 **2-ter** new; the P6 bullet's closing sentence ("the insert path is a separate correctness argument, deliberately not made") corrected — this round made it |
| `C:\Users\kk980\Developments\assyManager\docs\architecture\data_model.md` | §2.1-quater new (layering unchanged; what the `LightCellSource` swap does and does not mean) |
| `C:\Users\kk980\Developments\assyManager\docs\history\20260807_003000_the_prefetch_already_proved_the_row_was_absent_and_two_per_row_selects_asked_anyway.md` | history + `gen_index.py` run |

`PROJECT_STATUS.md`, the history index beyond `gen_index.py`, and every file owned by another live
lane (`server/map_alignment.py`, `server/scripts/seed_dt_index_walk.py`, the alignment tests) were
not touched.

**Left behind in the isolated environment: nothing.** `p3iw_map` and `p3ip_map` dropped, their rows
removed from `cell_sources` / `cell_overwrites` / `audit_logs` / `database_outbox` /
`file_ingestion_checkpoints`, both keys removed from the **dev_env copy** of `table_config.json`
(back to its original 23 tables — `server/config` was never touched). Verified after cleanup: no
`p3i%` relation remains, zero rows with a `p3i%` table name, databases are
`assy_manager 14 GB` / `assy_qa 1829 MB`, no probe database was ever created. The one deliberate
residue is the `cell_sources.confirmation_uid` column added to `assy_qa` (§5).

Harness (session scratchpad, prefix `P3I_`): `P3I_env.py` (isolation bootstrap) · `P3I_setup.py` ·
`P3I_bench.py` (the before/after benchmark) · `P3I_probe.py` (14 correctness probes) ·
`P3I_mutate.py` (defect injection) · `P3I_dbg_bk.py` / `P3I_dbg_collision.py` / `P3I_dbg_ow.py`
(old-vs-new differentials) · `P3I_prof_after.py` · `P3I_defaults.py` · `P3I_schema_gap.py` ·
`P3I_cleanup.py`.

---

## 8. Handover

**Next steps, in order.** ① Serialize a full `pytest` run — `test_set_based_write_path.py` has
never been executed by pytest, and `test_bulk_chunking_budget.py` /
`test_composite_key_prefetch_budget.py` / `test_replace_map_scope_diff.py` /
`test_virtual_join_executor.py` are the ones this change is most likely to move. ② Adversarial QA
(T2) on the four changes in §2, with §2.1's subtraction as the first thing to attack. ③ Decide the
two pre-existing defects in §5 — the empty-key one duplicates production map rows on every third
drop and is worth its own round. ④ Backpressure is now the binding constraint.

**Proposed memory entries (not added — for the Lead PM to rule on):**
* *"「물었다」와 「물었는데 안 왔다」는 다른 집합이다"* — a prefetch's coverage is not a proof of
  absence; the proof is coverage **minus what came back**. The difference only shows up where a
  mutable cache stopped answering first, which is exactly where it is most expensive.
* *"매핑 인스턴스를 만들고 세션에 안 넣는 코드는 계산용 객체를 잘못 고른 것이다"* — 5,000 rows
  cost 45,000 ORM constructions, 35,000 of which were thrown away; the lightweight class the
  prefetch already used was sitting in the same module.
