# QA-D3 — adversarial review, unique business key round

**Verdict: GO-WITH-FIXES.** The 29 dropped indexes are proven structurally per index and
that half is sound; the wrapper's control flow is bounded, narrow and logged. But the
replay reuses a batch object that the first attempt mutated, and on the legacy
`replace_map` derivation that silently narrows a whole-map purge to a single row — a
"quietly wrong" outcome on the layering core, which is the one class this project's
core value #3 forbids.

---

## 0. What was in the tree when I ran pytest

`HEAD = 4738d84` (the brief's stated baseline; the system snapshot naming `a14a098` was
stale and does not describe this worktree).

- **Staged (24 paths)**: 3 lane reports, 6 docs, `server/{chain_ingestion_worker,
  database/context, database/crud, database/database, database/models, event_constants,
  graph_materializer, graph_sync_worker, main, outbox_expand, parsers/directory_watcher,
  migrations/add_business_key_unique_index}.py` + 3 new test files.
- **Unstaged**: `docs/architecture/backend.md`, `docs/architecture/data_model.md`,
  `docs/process/PROJECT_STATUS.md` only. Docs cannot affect pytest.
- **Untracked and COLLECTED BY PYTEST**: `server/tests/test_set_based_write_path.py`
  (md5 `e60b6b9910c557dfaf7df4d83969fc9a`) — the P3 lane's test file for the already-
  committed `4738d84`. Also junk `server/align_test.log.1`.
- md5 of all 15 changed `server/**` files recorded before the run and re-checked after:
  **identical**. The tree did not move under the run.

🔴 **The brief's premise is wrong on one point: the console-safe logging change is not
uncommitted — it is already IN the baseline.** `server/utils/logger.py` and
`server/map_alignment.py` are both clean against HEAD, and `make_console_safe` /
the `UnicodeEncodeError` rescue in `logger.py:50-67` are present in
`git show 4738d84:server/utils/logger.py`. It landed *in* `4738d84`, so the brief's own
baseline (`3 failed, 3105 passed, 12 skipped, 1 xfailed`) already measured it.
**This run therefore covers exactly two uncommitted changes** — the outbox collapse and
D3 — plus the untracked P3 test file. Any delta from the baseline belongs to those two,
and none of it can be attributed to console-safe logging.

---

## 1. Suite

Run twice, on the same still tree (md5s of all 15 changed `server/**` files re-verified
identical before the second run, and `server/tests/test_set_based_write_path.py` unchanged
at `e60b6b9910c557dfaf7df4d83969fc9a`). **The first run's number was discarded by my own
error, not by the tree**: I piped it through `tail -60`, and a `directory_watcher`
background thread emitted a ~50-line teardown traceback (`no such table:
file_ingestion_logs`, then `ValueError: I/O operation on closed file` out of
`server/utils/logger.py:55`) **after** pytest's summary line, so the summary scrolled out of
the window. That teardown noise is pre-existing and unrelated to either change under
review. The second run captures the whole stream to a file.

md5s of all 15 changed `server/**` files were re-checked **after** the second run and are
still byte-identical to the pre-run record; `HEAD` is still `4738d84`. **The tree did not
move through either run.**

**Final line, verbatim:**

```
5 failed, 3172 passed, 12 skipped, 1 xfailed, 115 warnings in 1362.39s (0:22:42)
```

Baseline at `4738d84`: `3 failed, 3105 passed, 12 skipped, 1 xfailed`.

### Attribution — failure by failure. **None of the five is D3's.**

| # | test | owner | what it is |
|---|---|---|---|
| 1 | `test_composite_key_prefetch_budget.py::test_inserting_new_rows_still_probes_once_per_row` | **baseline** | `assert 1 == (200 + 1)` — the test still demands the 200 per-row probes that `4738d84` deliberately removed. This is the "legitimately-superseded assertion" already adjudicated in the baseline's three. |
| 2 | `test_config_reload_integrity.py::test_inv_9_1_atomic_save_event_applies_physical_alter` | **baseline** | `'qty' not in _physical_columns(...)` — atomic save did not reach the physical schema. `config_watcher.py` is untouched by both lanes. Also one of the baseline three. |
| 3 | `test_outbox_collapse.py::test_a_row_deleted_before_consumption_derives_nothing_and_is_counted` | **outbox lane** | 🔴 **The test is broken, not the feature.** Both feature assertions passed; it then dies at `test_outbox_collapse.py:294` on `r.message % r.args` — `LogRecord.message` is already formatted, so re-applying `%` raises `TypeError: not all arguments converted`. The captured log shows the real warning was emitted correctly (`[OUTBOX-4] 1 of 3 row(s) … derive NOTHING … Sample: [...]`). Fix the assertion helper, not `outbox_expand.py`. |
| 4 | `test_outbox_collapse.py::test_graph_materializes_a_collapsed_event_the_same_as_a_per_row_one` | **outbox lane** | `assert per_row_norm, "the control arm must actually produce edges"` → `assert set()`. The **control** (per-row) arm produced no graph edges at all, so the equivalence comparison never ran. Either the fixture never materialised, or `graph_materializer` regressed on the per-row path. This one is a real open question and belongs to that lane. |
| 5 | `test_set_based_write_path.py::test_a_user_layer_still_beats_a_later_parser_write` | **P3 (committed at `4738d84`) + untracked test file** | 🔴 `sqlalchemy.exc.NoResultFound: No row was found when one was required`. A **layering** test — "a user layer still beats a later parser write" — cannot find the row it wrote. This is the most alarming line in the run and it sits on already-committed code with a test that was never committed. **Route it to the P3 lane; it is not D3's and it is not the outbox lane's.** |

**D3's own 30 tests are all green** — zero occurrences of `test_business_key` in the failure
list; `test_business_key_conflict_retry.py` (12) and `test_business_key_unique_migration.py`
(18) both pass in full. But read §F4/§F5 before treating that as coverage.

Arithmetic: total collected went 3121 → 3190 (+69). The three new files contribute 49 test
functions; the remainder is `test_set_based_write_path.py` (14) plus parametrisation. Two
baseline failures persist, three are new, and **all three new ones belong to the outbox lane
or to P3.**

---

## 2. Confirmed defects

### F1 · 심각도 **중** (성격은 높음: 조용히 틀린다. 도달 조건이 좁아 중으로 둔다) — the replay re-derives the `replace_map` purge scope from a payload the first attempt mutated

`server/database/crud.py:2682` (retry loop) · `crud.py:2744`
(`scope_filters = derive_replace_map_scope(table_name, batch)`) · `crud.py:2882-2883`
(the `assemble_composite_business_key` loop) · `crud.py:1701-1743` (the mutation) ·
`crud.py:2461-2530` (`derive_replace_map_scope`, legacy branch).

The comment guarding the ordering sits at `crud.py:2875-2881` and its last sentence is now
false: **"Here, the resolver sees exactly the payload it saw before."** On the replay it
does not.

`assemble_composite_business_key` has **two** side effects, and its own docstring names the
ordering constraint that D3 breaks:

```
⚠️ AND ONE ORDERING CONSTRAINT. Writing `updates[key_col]` is visible to
`derive_replace_map_scope`, whose LEGACY (undeclared `map_key_columns`) branch
derives the purge filters from every non-coordinate column present in the first
payload row - and the business key column is not in its skip list. Running this
before that resolver would narrow a whole-map purge down to a single die.
```

`_apply_batch_updates_once` honours that by calling the resolver first (`crud.py:2740`) and
`assemble` after (`crud.py:2883`). **The wrapper replays the same `batch` object**, so on
attempt 2 the resolver runs against a payload where `assemble` has already inserted
`updates[business_key]`. The guard inside `assemble` (`if update_item.row_id or
update_item.business_key_val: return False`) makes the *key* idempotent — it does not undo
the write into `updates`.

**Failure scenario.** `wafer_map_metadata` (`composite_key_source`
`["target_table","map_id"]`, **no** `map_key_columns` → legacy derivation; same for
`lot_event`, `wafer_id_status`, `eqp_frame_attribution`). Client pushes a whole-map
`replace_map` batch. Attempt 1 resolves scope `{target_table, map_id}` → purges the map →
another process commits the same business key mid-batch → `IntegrityError` on `uq_bk_*` →
`db.rollback()` restores the map. Attempt 2's resolver now also sees `map_pk` in
`updates[0].updates`, so the scope becomes `{target_table, map_id, map_pk}` — **one row**.
The batch commits, the client gets HTTP 200 with `scope.deleted: 1` and `scope.filters`
listing a column it never sent, and **every stale row of that map survives**. Nothing
fails, nothing is logged as wrong.

**Measured, not argued** (this box, `TESTING=1`, real `TABLE_CONFIG`, no DB — the two
functions are pure):

```
config: {'business_key': 'map_pk', 'composite_key_source': ['target_table','map_id'],
         'map_key_columns': None}
attempt 1 scope : {'target_table': 'bonding_map', 'map_id': 'LOT1_01'}
payload after assemble: {..., 'map_pk': 'bonding_map_LOT1_01'}
attempt 2 scope : {'map_pk': 'bonding_map_LOT1_01', 'target_table': 'bonding_map',
                   'map_id': 'LOT1_01'}
SAME SCOPE ON REPLAY: False
```

**Reachability, stated honestly**: only the four tables with `composite_key_source` and no
`map_key_columns` (`lot_event`, `wafer_id_status`, `eqp_frame_attribution`,
`wafer_map_metadata`), and only on a `replace_map` batch that loses a BK race. All seven
shipped *map* tables declare `map_key_columns` and are unaffected. What makes it worth
fixing anyway is that the ordering constraint is now broken **by construction** — any table
that later ships without `map_key_columns` inherits it, and the failure is a silent partial
delete reported as a success.

**Recommended fix**: snapshot/deep-copy `batch.updates` (or at minimum the `updates` dicts)
before the first attempt and restore it in the `except` branch, or resolve
`derive_replace_map_scope` **once** in the wrapper and pass it down. A test must assert the
scope dict is equal across attempts — not that the batch "looks the same".

### F2 · 심각도 **중** — §2 reports "dropped" without ever verifying the index is gone

`server/migrations/add_business_key_unique_index.py:401-403`

```python
conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS public.{r['index']}"))
dropped.append(r)
```

`IF EXISTS` cannot raise on a name mismatch, and the index name is interpolated
**unquoted**. §1 explicitly refuses this reasoning for itself (`build_index`,
lines 295-302: *"the statement did not raise" is not enforcement*), and §2 does not apply it.

**Failure scenario.** An index created as `CREATE INDEX "ix_Foo_Id" ...` (quoted, mixed
case) passes the name gate (`startswith("ix_")`). The DROP folds the unquoted identifier to
`ix_foo_id`, which does not exist, `IF EXISTS` swallows it, the row lands in `dropped`, and
the run prints `Reclaimed 314.0 MB across 1 indexes` having reclaimed nothing. The operator
records the space as recovered.

**Recommended fix**: quote the identifier (`public."{name}"`) and re-query `pg_class` after
the DROP, exactly as `build_index` re-queries `indisvalid`. Failing that verification is a
`failed`, not a `dropped`.

### F3 · 심각도 **중** — the redundancy proof omits `indoption`, and the docs call it complete

`add_business_key_unique_index.py:326-350` compares `indkey`, `indclass`, `indcollation`,
`amname`, `indpred`, `indexprs`. It does **not** compare `indoption`, which carries `DESC`
and `NULLS FIRST/LAST` per key column. The module docstring (line 72) and
`data_model.md §3.2` both describe the comparison as identity.

**Failure scenario.** A table whose primary key is multi-column, with a hand-tuned
`ix_*`-named index on the same columns but `(a, b DESC)`. Backward index scan makes a
*single*-column DESC index equivalent; a **mixed-order multi-column** index is not, and it
is the only index that can serve `ORDER BY a, b DESC` without a sort. It is proven
"identical" and dropped, and the query silently acquires a sort node on a 14 GB table.
Not reachable from `models.py` today; reachable from an operator's index.

**Recommended fix**: add `AND xd.indoption = xp.indoption` and pin it in the SQL-clause test
beside `indclass`.

### F4 · 심각도 **중** — `run()` and `redundant_pk_indexes()` have **zero** test coverage, including the one defect the lane actually found

`server/tests/test_business_key_unique_migration.py` — grep for `mig.run`,
`redundant_pk_indexes`, `invalidate`, `read_only`: **no hits**. `redundant_pk_indexes` is
monkeypatched away in every §2 test (`_redundant()`, line 170), and the helper `_row()`
(line 175) **recomputes `droppable` itself** rather than exercising the real gate at
`add_business_key_unique_index.py:365-366`.

Consequences, by inspection rather than by mutation (no mutation was injected — a shared
tree):

- Deleting `conn.invalidate()` (line 480) — the fix that cost the lane an end-to-end run
  and produced its best lesson — **leaves the suite green**. The `SET SESSION
  default_transaction_read_only` pin riding a pooled connection into the next checkout has
  no regression net at all.
- Changing line 365 to `"droppable": True` **leaves the suite green**, because no test
  calls that function. The lane's mutation table entry "name gate removed → 1 test red" is
  true only for the *consumer* half of the gate (`if not r["droppable"]` at line 389).
- `tables_with_business_key`, and the real bodies of `duplicate_census`,
  `existing_unique_index`, `index_exists` are likewise never executed.

The test file's docstring is honest that catalogue SQL cannot run on SQLite; it does not say
that the orchestration function is untested. **The 18/18 green number describes a smaller
surface than it appears to.**

### F5 · 심각도 **중** — nothing exercises the merge; "the retry IS the merge" is prose

Every test in `server/tests/test_business_key_conflict_retry.py` monkeypatches
`crud._apply_batch_updates_once` (lines 84-96, 223) and drives fake exceptions against a
`FakeDB`. That proves the wrapper's control flow — detector narrowness, rollback count,
bound, logging, 4-tuple, out-param — and nothing about the claim that carries the layering
risk: that the replay's fresh prefetch resolves onto the winner's row while `SOURCE_PRIORITY`
still decides and `user` still beats `automatic`.

It cannot be tested as written: the suite runs on SQLite and `models.py` declares
`business_key_val` **non-unique** there (`models.py:686`), so no real BK unique violation can
occur in the suite. The lane's live PostgreSQL probe measured the **detector**
(`pgcode='23505' constraint_name='uq_bk_d3_clean'`), not the merge.

**Recommended**: a PostgreSQL-marked test (or a documented manual FEATURE_CHECKLIST item)
where a second connection commits the key mid-batch and the assertion is on **content** —
`cell_sources.source_name`, priority, audit rows, outbox rows — not on row counts.

### F6 · 심각도 **낮음** — the exhaustiveness claim on call sites is false; 13, not 8

`Server_D3_unique_business_key.md` §2 names eight and says a grep including the gitignored
user areas "found no other caller". The gitignored areas are clean (verified:
`server/mappers/`, `server/ingestion_workspace/`, `server/config/` — only prose hits). But
**`server/scripts/` was not swept**:

- `server/scripts/seed_dt_index_walk.py:362`, `:364`, `:377`
- `server/scripts/seed_valid_die_ref_floor.py:262`, `:266`

Same behavioural change applies (raw raise on an exhausted BK conflict). Also an anchor
drift: the report cites `chain_ingestion_worker.py:473`; the call is at **`:486`**.

### F7 · 심각도 **낮음** — an unresolved BK conflict reaches the REST client as HTTP 500

`server/main.py:2489-2493` maps only `ValueError` → 400. After the migration lands, a genuine
duplicate identity produces `IntegrityError` out of `apply_batch_updates` → FastAPI 500 with
an opaque body. This is strictly better than the silent duplicate it replaces, but 409 with
the offending key is the honest code, and `replace_report` is never read on that path.

---

## 3. Hypotheses I tried to break and could not

- **Does `db.rollback()` leave the once-per-transaction NOTIFY latch set, so the replay
  commits without waking the chain worker?** No. `database.py:91-123`
  `_clear_outbox_notify_latch` fires on `after_transaction_end` for every origin except
  `SUBTRANSACTION`, i.e. rollback clears it. The replay sends a fresh `NOTIFY`.
- **Does a non-BK `IntegrityError` get retried?** No. `crud.py:2686-2687` re-raises before
  `db.rollback()`. The PostgreSQL branch (`crud.py:2626-2630`) `return`s on `pgcode ==
  "23505"` and never falls through to the message test, so a 23505 on `idx_sources_lookup_col`
  or a hand-named unique index on `business_key_val` is correctly refused.
- **Is the retry bounded?** Yes. `range(BK_CONFLICT_MAX_RETRIES + 1)` with
  `if attempt >= BK_CONFLICT_MAX_RETRIES: raise` — exactly 3 executions max, then
  `[BK Conflict Unresolved]` at ERROR and a re-raise. The loop cannot fall through.
- **Does `assemble_composite_business_key` recompute a different key on replay?** No — the
  `row_id or business_key_val` guard returns False. (The *other* side effect is F1.)
- **Do the 26 dropped `ix_<table>_row_id` leave any query without an index?** No — the
  catalogue proof requires `xd.indkey = xp.indkey` against the table's own PK index, so the
  PK btree covers exactly the same key. The proof is per index, not per assumption.
- **Does anything re-create the dropped indexes?** No. `models.py` lost the flag in all five
  declarations, `create_all` never adds to existing tables, and no code path emits an `ix_*`
  name (the only `ix_*` literals in `server/` outside the migration are
  `setup_db_performance.py:273-277`, which **drops** four of them).
- **Does the read-only pin survive `run()`?** No, `conn.invalidate()` at line 480 in a
  `finally`, and it is gated on `readonly_pinned` which is only set in the non-writing branch.
  Correct — but see F4 for the missing net.
- **Same shape elsewhere?** Two sites, neither newly broken: `server/scripts/dev_env/
  snapshot_db.py:75-76` pins `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` +
  `default_transaction_read_only` and never invalidates — contained, because it builds its own
  dedicated engine and never writes to the source. `server/scripts/diagnose_db_health.py:213-225`
  sets session-level `statement_timeout` and resets it in a `finally` whose reset is itself
  wrapped in `except: pass` — an aborted transaction there returns a timeout-carrying
  connection to the pool. Pre-existing, script-scoped, out of D3's scope; worth a follow-up.
- **Does the retry double-count `replace_report`?** No, all writes are assignments
  (`crud.py:2825-2839`, `:3062-3063`, `:3127-3129`) under branch conditions that are stable
  across attempts — except the scope itself, which is F1.
- **Does `--drop-redundant` need `--apply`?** No, and `writes = apply or drop_redundant`
  (line 421) correctly skips the read-only pin in either case.

---

## 4. Needs runtime verification (cannot be settled from code)

1. **The merge itself** (F5) — that a real cross-process conflict on PostgreSQL replays into
   the winner's row with layering intact. Content assertions, not counts.
2. **Whether §2's drop actually reclaims what it prints** (F2) — needs a live re-query after
   the DROP.
3. **Driver coupling of the detector.** `pgcode` is psycopg2. If this deployment ever moves to
   psycopg3 the branch falls through to the message test, whose narrowness guarantee is
   weaker than what `data_model.md §3.1` documents. Measured live by the lane on *this*
   box only.
4. **Production census.** Every duplicate figure in this round is from this workstation, a
   simulation. Nothing here says production is clean; the pre-flight is the only instrument
   that can answer that, and it must run on the production box.
5. **`CREATE`/`DROP INDEX CONCURRENTLY` under production load.** No `lock_timeout` is set
   (consistent with the existing `setup_db_performance.py` precedent), and `duplicate_census`
   runs a full `GROUP BY` per table on **every** run including idempotent re-runs
   (`plan_table:259` censuses before checking for an existing index — pinned as intentional by
   `test_duplicates_are_measured_even_when_the_index_already_exists`). Neither the guide nor
   the report states an expected duration on a 14 GB database.

---

## 5. Document coherence

1. 🔴 **`docs/architecture/data_model.md` §3.2 (unstaged, `@@ +174`) says "선언은 **넷**이었고"
   and then lists **five**** — `AuditLog.id` · `FileIngestionLog.id` · `CellOverwrite.id` ·
   `CellSource.id` · the dynamic `row_id`. The lane's own report and `models.py` both say five.
   The cardinal is a second copy of the list and it is already wrong on the day it landed.
2. 🔴 **`docs/guide/POSTGRES_OPERATIONS_GUIDE.md` quotes a verdict string the tool never
   prints**: the new §3.1-bis says the invalid leftover is reported as
   `refused_invalid_leftover`; the constant is `REFUSED_INVALID_INDEX =
   "refused_invalid_index"` (`add_business_key_unique_index.py:247`). An operator grepping the
   output during an incident for the documented word finds nothing.
3. 🔴 **The now-false "one path" sentence survives in `docs/README.md:78`** — "운영 DB 반영
   경로는 `setup_db_performance.py` 하나뿐". The lane corrected the copy inside
   POSTGRES_OPERATIONS_GUIDE and did not sweep for the others. (The two remaining "유일한
   경로" sentences at POSTGRES_OPERATIONS_GUIDE:165/:172 are about `idx_sources_by_source` and
   the suggest indexes specifically and remain true.)
4. **Overstated narrowness.** `data_model.md §3.1` says the detector fires "SQLSTATE 23505 +
   제약 이름이 `uq_bk_` 접두일 때만". There is also a message-based fallback
   (`crud.py:2632-2633`) for any driver without `pgcode`. Say so.
5. **Overstated name gate.** The module docstring (line 74) and the operations guide both say
   the gate requires "SQLAlchemy's auto-generated `ix_<table>_<column>` form". The code checks
   `startswith("ix_") and len > 3` (line 365). Any hand-made `ix_`-prefixed index is droppable.
   Either tighten the check or soften the sentence.
6. **`server/scripts/setup_db_performance.py` Step 3.5 already drops four PK-duplicating
   `ix_*` indexes by hardcoded name** (lines 265-283, incl. `ix_database_outbox_id`, "pkey와
   완전 중복"). D3 §2 generalises it and now overlaps it. Neither document points at the other;
   an operator has two tools that drop the same index and no statement of which is canonical.
7. **No `docs/qa/FEATURE_CHECKLIST.md` item for D3.** The staged `+9` there is entirely the
   outbox lane's. D3 introduces an operator-visible refusal (`[BK Conflict Unresolved]`) and a
   new mandatory production migration, and neither has a manual check.
8. **No `docs/architecture/PRIMITIVES.md` entry for D3.** The staged `+13` is the outbox
   lane's. Two of D3's lessons are cross-domain primitives, not server-pm memory: *"a
   read-only-pinned connection must be thrown away, not returned to the pool"* and *"`CREATE
   ... IF NOT EXISTS` succeeding is not enforcement — verify `indisvalid`"*. Lead PM's call.

**Staging note confirmed.** `docs/architecture/data_model.md` and `backend.md` are still
unstaged and each carries another lane's hunks: data_model `@@ -1,6` (Last-verified header)
and `@@ -84,6` (P3 §2.1-quater) beside D3's `@@ -164,6 +174,24`; backend `@@ -1,8` beside
D3's `@@ -367,7 +370,21`. **Stage by hunk, not by file.**

---

## 6. Proposed lesson for `agent_workspace/memory/qa-reviewer.md`

- **함정: 「테스트 N개 전부 초록」을 커버리지로 읽는다.** 이번 라운드에서 §2의 두 게이트 중
  하나(`redundant_pk_indexes`의 이름 판정)와 오케스트레이션 함수(`run()` — 그 라운드에서
  **실제로 발견된 유일한 결함**이 사는 자리)는 **어떤 테스트도 호출하지 않았다**. 테스트
  헬퍼(`_row()`)가 판정 필드를 **자기가 다시 계산**했기 때문에 겉으로는 그 게이트를 검사하는
  것처럼 보였다.
  **올바른 방법**: 초록 개수를 세지 말고, **판정 함수 이름을 테스트 파일에 grep**해라. 이름이
  0건이면 그 함수는 채점되지 않은 것이고, 구현자의 변이 표에 그 이름이 있어도 변이가
  **소비자 쪽**에 꽂혔을 수 있다.
