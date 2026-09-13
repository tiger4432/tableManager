# D3 — "one row per business key" is now an invariant the database enforces

**Tier T2. Built, exercised against a real PostgreSQL, mutation-checked. Not committed.**
`pytest` was NOT run (per instruction); the two new test files are written and every test
body in them was executed outside pytest, plus **18 injected mutations** were confirmed to
turn them red.

---

## ROUND 2 — QA's GO-WITH-FIXES, all seven addressed

| # | Fix | Where |
|---|---|---|
| **F1** | The replay no longer re-derives the purge scope from a payload attempt 1 mutated. `crud._replay_sensitive_key_column` / `_snapshot_payload_identity` / `_restore_payload_identity`, called from the wrapper. **5 new tests.** | `crud.py` |
| **F2** | §2 verifies the drop against the catalogue instead of trusting the return code, and quotes the identifier (`quote_ident`). **3 new tests.** | migration |
| **F3** | `indoption` added to the redundancy proof. **1 new test.** | migration |
| **F4** | The read-only-pin/`invalidate` path and the **producer** half of the name gate are now netted. **4 new tests** (`CatalogueConn`/`FakeEngine` doubles). | tests |
| **F5** | **The merge is measured**, two processes, real PostgreSQL — see below. No longer an argument. | measurement |
| **F6** | 13 call sites, corrected below. | report |
| **F7** | Unresolved conflict → **409**, not 500. | `main.py` |
| docs | `넷`→`다섯`, `refused_invalid_leftover`→`refused_invalid_index`, `docs/README.md:78`, Step 3.5 reconciliation, plus the missing FEATURE_CHECKLIST row and PRIMITIVES entries. | docs |

### F5 — the merge, measured

Two real OS processes on an isolated PostgreSQL, 5,000-item batch, **race key last**, both
on an absolute wall-clock barrier. The slow writer holds the window open **in its own
process only** (a runtime wrap of `crud.apply_row_update_internal`; nothing on disk
touched) between the prefetch and the flush — leaving it to wall-clock luck made the
result a coin flip, and its failure mode is the dangerous one: when the fast writer
commits *after* the slow one the answer is COUNT 1 **with no race at all**, which is
indistinguishable from a successful merge unless you also require the recovery log line.
I hit exactly that twice before pinning it. **3 consecutive runs, identical:**

| arm | difference | rows for one business key | `[BK Conflict Recovered]` |
|---|---|---|---|
| **A** (control) | no unique index | **2** — the silent duplicate | 0 |
| **B** | `uq_bk_production_plan` | **1** — merged | **1** |

Arm A is what makes arm B mean something: it proves the window really opened. And note
what happened in between — arm A's duplicate made my own migration **refuse to build the
index**, twice, before I added the de-duplication step. The refusal path was exercised by
accident, correctly.

The suite still cannot measure this (SQLite declares `business_key_val` non-unique, so no
real violation is reachable in the suite dialect) and I did **not** add a skipped
PostgreSQL-only test — an alarm that never fires is not a net. The probe is
`…/scratchpad/D3_merge.py` + `D3_merge_writer.py`, reproducible in ~90 s.

### F6 — the corrected call-site count

**13, not 8.** The five I missed are all in `server/scripts/`, which my sweep excluded:
`seed_dt_index_walk.py:362,364,377` and `seed_valid_die_ref_floor.py:262,266`. All 13 go
through the public name with the unchanged 4-tuple, so none needed editing — but the
number was wrong and the sweep that produced it was wrong. (`contracts/blank_predicate/`
has 3 more in a test harness.)

---

## 0. What shipped

| Path | What |
|---|---|
| `server/migrations/add_business_key_unique_index.py` | **new.** §1 `uq_bk_<table>` UNIQUE indexes, CONCURRENTLY, measure-before-build, refuse-by-name. §2 `--drop-redundant` (the added scope). Read-only by default. |
| `server/database/crud.py` | `apply_batch_updates` is now a wrapper; the body is `_apply_batch_updates_once`. Adds `_is_business_key_unique_violation`, `BK_UNIQUE_INDEX_PREFIX`, `BK_CONFLICT_MAX_RETRIES`. |
| `server/database/models.py` | removes `index=True` from **five** `primary_key=True` declarations. |
| `server/tests/test_business_key_conflict_retry.py` | **new**, 17 tests. |
| `server/tests/test_business_key_unique_migration.py` | **new**, 26 tests. |
| `docs/guide/POSTGRES_OPERATIONS_GUIDE.md` | §3.1 operator procedure for both sections; corrects the now-false "there is only one path to add indexes". |
| `docs/architecture/data_model.md` | new §3.1 (the invariant + the recovery) and §3.2 (no `index=True` on a PK). |
| `docs/architecture/backend.md` | new §3 2-quater — the D3 pairing that §3 2-ter (P3) requires. |
| `server/main.py` | **[F7]** an unresolved business-key conflict answers **409**, not 500. Narrow: any other `IntegrityError` keeps its 500. |
| `server/scripts/setup_db_performance.py` | comment only — reconciles Step 3.5 with §2 (which is authoritative for which class). |
| `docs/qa/FEATURE_CHECKLIST.md` | new §1.11 inventory row. |
| `docs/architecture/PRIMITIVES.md` | two new §2 entries (the invariant; no `index=True` on a PK). |
| `docs/README.md` | the "only one path to add indexes" sentence, corrected here too. |

**Staging: see §8.3.** Several of these files carry another lane's uncommitted hunks, so
they are deliberately left unstaged for hunk-level staging rather than `git add`-ed whole.

---

## 1. Section 1 — the UNIQUE index

`uq_bk_<table>` on `(business_key_val)`, one per table that actually has the column
(asked of `information_schema`, not of `table_config.json` — config declares intent, the
migration must act on what exists).

**Default run is read-only** and pins the session with
`SET SESSION default_transaction_read_only = on`, so the production pre-flight cannot
write even if the code were wrong. `--apply` builds. The two sections are independent
flags so an operator can take one and not the other.

Per table, in this order: **census → verdict → maybe build → verify the build came out
valid.** Verdicts are named states, not a count:

- `already_enforced` — a valid unique index on exactly that one column already exists.
- `created`
- `refused_duplicates` — **that table is refused by name, with its duplicate-key count,
  its surplus row count and its top offending keys, and the run continues.** Never aborts
  the whole migration, never skips silently.
- `refused_invalid_index` — an index under the wanted name exists with `indisvalid =
  false` (a cancelled CONCURRENTLY build). 🔴 This is the trap `IF NOT EXISTS` sets:
  it matches on the NAME, so a re-run reports success forever while the column is
  unprotected. It is its own verdict and prints the `DROP INDEX CONCURRENTLY` command.
  **The script drops nothing here.**
- `failed` — the DDL raised, or returned without raising and left an invalid index. "The
  statement did not raise" is not enforcement, and is not reported as one.

Exit code is 1 if anything was refused or failed.

**NULLs stay legal and that is required, not tolerated.** A plain PostgreSQL UNIQUE index
treats NULLs as distinct; `crud.create_empty_rows_batch` inserts rows with no business
key, so `NULLS NOT DISTINCT` would break "add empty row" on the second click. Verified
empirically — the probe table had 2 NULL-key rows and the build succeeded.

### Why not declare `unique=True` in `models.py` instead
`create_all` does not add indexes to tables that already exist, so the declaration would
be a silent no-op on exactly the databases where duplicates can have accumulated (same
class as `idx_sources_by_source`). **The honest cost, stated in the model comment and
worth a decision: a freshly created database is unprotected until the migration runs, so
the migration belongs in the setup sequence, not only the upgrade one.** I did not add it
to any setup script — that is a wiring decision, and `run_decoupled_app` / setup ordering
was not in my scope this round.

---

## 2. Section 1 — the `IntegrityError` recovery

`apply_batch_updates` became a thin wrapper. The 4-tuple return and the `replace_report`
out-param are carried through unchanged, so **all eight call sites are untouched**
(`main.py:2490`, `chain_ingestion_worker.py:473`, `chain_replay.py:310`,
`enrichment_backfill.py:432`, `enrichment_candidates.py:759`, `frame_confirmation.py:391`,
`map_meta_registrar.py:364`, `directory_watcher.py:1909`). Grep including the gitignored
user areas (`config/`, `mappers/`, `ingestion_workspace/`) found no other caller.

**The retry IS the merge — and that is now measured, not argued (see F5 above).** The
rollback ends the failed transaction, so the replay's
prefetch runs in a new READ COMMITTED snapshot and now sees the row the winner committed;
`row_cache` picks it up and `_get_or_create_row` resolves onto it. There is no second
merge implementation to keep in step with the first — which matters here specifically,
because "two spellings of identity resolution" is how this subsystem has been burned
before.

**The detector is deliberately narrow, and this is the load-bearing design decision.**
Retrying on any `IntegrityError` would swallow a NOT NULL breach, a `cell_sources` unique
collision, or a genuine same-payload key conflict and replay it until it gave up —
replacing one invisible failure with another, which is exactly what the brief warned
against. It fires only on SQLSTATE 23505 with a constraint name starting `uq_bk_`, or (on
SQLite, which is what the suite runs) a unique-violation message naming
`business_key_val`.

🔴 **That constraint-name assumption was measured, not assumed.** Against a real
PostgreSQL with a real duplicate insert:

```
pgcode='23505' constraint_name='uq_bk_d3_clean'
crud._is_business_key_unique_violation -> True
```

Had PostgreSQL reported the table name or nothing, the recovery would have been dead code
in production while passing every test.

**Named and logged, always** — `[BK Conflict Recovered]` at WARNING on each recovery,
`[BK Conflict Unresolved]` at ERROR plus a re-raise once `BK_CONFLICT_MAX_RETRIES` is
exhausted. A genuine duplicate identity fails the batch; it is not replayed forever.

### [F1] The replay must un-write the payload first
`assemble_composite_business_key` writes the assembled key back into
`update_item.updates[key_col]` **in place**, and `derive_replace_map_scope`'s legacy
branch builds its purge filters from every non-coordinate column of the first payload
row. So attempt 1 leaves behind a column that attempt 2's resolver reads as an extra
filter — QA measured a whole-map scope narrowing to one row, with the route still
answering 200 and `deleted: 1`.

That function's own docstring calls the ordering an **ORDERING CONSTRAINT** and ends
*"the resolver sees exactly the payload it saw before"* — true for a single pass, false
by construction the moment a replay exists. The wrapper now snapshots the two fields that
function writes (**not** a deep copy: three references per item) before attempt 1 and
restores them before each replay.

It costs nothing unless BOTH hold: the write is a `replace_map`, **and** the table
assembles its key from its own columns. So a 100,000-row ingestion batch pays zero.
Reachable today on the four tables with `composite_key_source` and no `map_key_columns`
(`lot_event`, `wafer_id_status`, `eqp_frame_attribution`, `wafer_map_metadata`); the
seven shipped map tables take the declared branch. **Fixed anyway** — "no shipped table
hits it" is a fact about today's config, not an invariant.

### ⚠️ One cost of the rollback, named rather than left to be found
`ingestion_checkpoint.record_chunk_progress` deliberately issues its offset UPDATE **in
this session immediately before** the call, so that "rows committed == offset recorded"
holds atomically — that is its own docstring's contract. A rollback here discards it, and
the replay commits the chunk with the offset unadvanced. The consequence is the degraded
mode that module already documents and accepts: a later crash re-processes that chunk,
and the upserts are idempotent, so it is re-ingestion, not loss. Restoring full atomicity
needs the caller to re-issue its pre-write statements on replay, which the wrapper cannot
do from inside. `directory_watcher.py` is off-limits this round anyway.

---

## 3. Section 2 — the coordinator's scope addition, verified before acting

**The claim holds, and the extension is 29 indexes / 382.3 MB, not 3.**

Live dev catalogue, 2026-08-07, structural comparison (not `idx_scan`, which lives in the
resettable stats collector and is a hint at best):

| table | redundant index | duplicates | size |
|---|---|---|---|
| `cell_sources` | `ix_cell_sources_id` | `cell_sources_pkey` | 314.2 MB |
| `audit_logs` | `ix_audit_logs_id` | `audit_logs_pkey` | 60.7 MB |
| `cell_overwrites` | `ix_cell_overwrites_id` | `cell_overwrites_pkey` | 3.6 MB |
| + 26 more | `ix_<table>_row_id` | `<table>_pkey` | 3.8 MB combined here |

Both members of every pair are `btree`, single key, no predicate, no expression, and
identical `indkey` / `indclass` / `indcollation`. Nothing in the repo references any of
the three named indexes by name (grep over `*.py`, `*.sql`, `*.md`, `*.json`, excluding
worktrees) — the only hits are the sibling lane's own report.

**The 26 extra come from two more declarations of the same mistake**, which reading the
three named classes would have missed: `FileIngestionLog.id`, and the shared dynamic-table
column `Column("row_id", String, primary_key=True, index=True)` — one duplicate per
dynamic table. Their sizes are trivial on this box and will not be in production, where
`bonding_map` alone is ~1.76M rows. All five declarations are fixed in `models.py`.

**Two independent gates before anything is dropped:**

1. **The catalogue query is the proof**, re-run every time — never a hardcoded list. Each
   clause earns its place: dropping the `indclass` comparison would make a
   `text_pattern_ops` prefix index look like a PK duplicate and delete the one index a
   prefix search needs; dropping the `btree` restriction would do the same to a GIN index.
   Both are pinned by a test.
2. **The name must be SQLAlchemy's auto-generated `ix_*`.** Anything structurally
   redundant under a hand-written name is **reported and left alone** — a name someone
   chose is a decision, and dropping the wrong index on a 14 GB database is not repaired
   by re-running. Verified live: a deliberately hand-named redundant index
   (`idx_handwritten_clean`) survived an `--apply --drop-redundant` run that dropped the
   two `ix_*` ones beside it.

`DROP INDEX CONCURRENTLY IF EXISTS`, outside a transaction block, idempotent in both
directions (the discovery returns nothing on a re-run).

---

## 4. Production posture — this box is a simulation

**I have written no claim that production is clean anywhere, and the migration's own
comment says so.**

- **Dev census, measured today:** 25 tables carry `business_key_val`, 52,725 rows,
  `count(bk) == count(DISTINCT bk)` in every one, **surplus 0**. That is a third
  independent measurement agreeing with the lead PM's and the race lane's.
- **Enforcement before this lane:** 50 indexes mention the column, `indisunique` true on
  **0**; zero unique/PK constraints. (The board's 54 is stale; the load-bearing 0 is not.)
- **D2 is not a blocker here**, and the migration's docstring says so by name so the next
  reader does not re-block on a resolved prerequisite. The board's old duplicate figures
  (`bonding_log` 117, `wafer_process` 43, `inventory_master` 163) are **absent from this
  database today** — cleaned, or re-seeded; nobody knows which, and I did not guess.
- **The pre-flight is the thing to run on production first**, and it is the *same*
  decision code as `--apply`, so it cannot disagree with what the apply will then do:

```bash
conda run -n assy_manager python server/migrations/add_business_key_unique_index.py
```

It reports, per table, rows / null keys / duplicate keys / surplus / verdict, plus the
full section-2 list with sizes, and writes nothing. Real output against the dev DB: 25
tables `buildable`, 0 refused; section 2 found 29 / 382.3 MB.

---

## 5. Verification — what was actually executed

**A. Real PostgreSQL end-to-end**, isolated probe DB `assy_d3_6f856759` (session-suffixed,
seeded with one clean table incl. 2 NULL-key rows, one table with 10 duplicate keys, two
`ix_*` PK duplicates and one hand-named one):

| run | result |
|---|---|
| read-only pre-flight | correct verdicts; catalogue **byte-identical** afterwards |
| `--apply --drop-redundant` | `uq_bk_d3_clean` created **valid**; `d3_dirty` refused by name with its 10 keys / 10 surplus and the run continued; 2 `ix_*` dropped; hand-named one left alone |
| re-run, same flags | `already_enforced`, nothing created, nothing dropped — **idempotent** |
| duplicate INSERT | `23505` / `constraint_name='uq_bk_d3_clean'` / detector returns True |

Probe DB dropped. Remaining `assy%` databases: `assy_manager` (14 GB, the dev DB — not
mine), `assy_qa` (642 MB, shared isolated — not mine). The `assy_obx2_6f856759` the race
lane reported is gone.

**B. 🔴 That end-to-end run found a defect no unit test could have.** The first version
set `SET SESSION default_transaction_read_only = on` for the check mode and then returned
the connection to the pool with `conn.close()` — which **does not close it**. The next
checkout inherited the read-only flag and every `CREATE`/`DROP` in the apply run failed
with `ReadOnlySqlTransaction`. Fixed by `conn.invalidate()` in a `finally`, i.e. throwing
the connection away rather than relying on a reset statement that an exception could skip.
The check mode was doing its job so well it disabled the apply.

**C. All 43 new test bodies executed** (outside pytest, via a scratch driver that supplies
monkeypatch/caplog/setitem doubles): 17 + 26 pass. Re-verified after every round-2 change.

**D. 18 mutations injected into the real source text, 18/18 rang:**

| mutation | tests that went red |
|---|---|
| detector widened to any `IntegrityError` | 4 |
| `db.rollback()` removed from the recovery | 2 |
| retry bound removed (unbounded replay) | 2 |
| recovery no longer logged by name | 1 |
| invalid leftover folded into `already_enforced` | 2 |
| duplicate census no longer refuses | 1 |
| build reports success without checking `indisvalid` | 1 |
| name gate removed (drops hand-named indexes) | 1 |
| check mode writes anyway | 1 |
| `indclass` comparison dropped from the redundancy proof | 1 |
| **F1** replay restore removed | 2 |
| **F1** restore pops the key column unconditionally | 1 |
| **F1** cost gate removed (snapshot taken for every batch) | 8 |
| **F2** drop counted without checking the catalogue | 2 |
| **F2** identifier no longer quoted | 3 |
| **F3** `indoption` comparison dropped | 1 |
| **F4** read-only connection returned to the pool | 1 |
| **F4** every discovered index reported droppable | 1 |

---

## 6. The virtual-join refusal — **D3 does not fix it, and here is the proof**

Every probe run in the race lane printed
`[VirtualJoin:dt_log_confirmed_attribution] rejected: no unique index covers dt_job_attribution(dt_job)`.

**That rejection wants a unique index on `dt_job_attribution(dt_job)` — a different
column from `business_key_val`.** `virtual_join_config.unique_index_covering` compares
the index's key expressions against the declared `right_columns`, which
`virtual_join_rules.json` gives as `dt_job`. `dt_job_attribution`'s `business_key` **is**
`dt_job`, so `uq_bk_dt_job_attribution` would enforce the same *fact* — in a different
column, which the checker (correctly) will not accept.

Second correction, and it is why I checked rather than inheriting the claim: **that
refusal no longer reproduces on this box.** The dev catalogue already carries
`uq_vjoin_dt_job_attribution_dt_job` (valid, unique, on `dt_job`). **No code creates it** —
`virtual_join_config.required_index_ddl` only prints the DDL for an operator to run, so
somebody ran it by hand after the race lane's probes (`seed_dt_index_walk.py:375` refers
to the index but does not create it). The refusal quoted in that report is real but stale,
and it is *not* evidence that D3 resolved anything.

---

## 7. Reuse note (why a fourth index-name helper exists)

`unique_index_name` folds to 63 bytes with a digest, the same discipline as
`virtual_join_config.required_index_name` and `value_suggest.suggest_index_name`. I did
not import either: both bake in their own prefix and their own key-set semantics, and
`virtual_join_config` additionally carries notation-folding. Three ~10-line functions
with the same shape is the honest cost; a shared helper would need the prefix and the
key-list as parameters and would sit in a module none of the three currently import.
**Worth a follow-up, not worth a cross-module dependency in this round.**

---

## 8. Open items for the lead PM

1. **Production is a different machine.** Ship the pre-flight first. If it refuses tables,
   that is D2's real scope and it is measured, per table, with the offending keys.
2. **A freshly created database is unprotected until the migration runs** (§1). Wiring it
   into the setup sequence is a decision I did not make unilaterally.
3. **🔴 Staging — five files carry another lane's uncommitted hunks. Stage by hunk.**

   | file | hunks | MINE |
   |---|---|---|
   | `server/main.py` | 5 | `@@ +2` (import), `@@ +2495` (the 409) — the three at `+4031/+4048/+4071` are the outbox lane's |
   | `docs/architecture/data_model.md` | 3 | `@@ +177` only |
   | `docs/architecture/backend.md` | 3 | `@@ +370` only |
   | `docs/qa/FEATURE_CHECKLIST.md` | 2 | `@@ +212` only |
   | `docs/architecture/PRIMITIVES.md` | 2 | `@@ +136` only |

   Exclusively mine and already staged: `server/migrations/add_business_key_unique_index.py`,
   the two test files, `server/database/crud.py`, `server/database/models.py`,
   `docs/guide/POSTGRES_OPERATIONS_GUIDE.md`, `docs/README.md`,
   `server/scripts/setup_db_performance.py`, and this report.
4. **F7 changes a REST status code** (500 → 409 on an unresolved business-key conflict).
   You asked for it, so I built it, but it is a boundary contract: no client code reads
   409 today, and a client that treats non-2xx uniformly is unaffected. Flagging rather
   than assuming.
5. **`pytest` not run.** The two new files need your serialized run — 43 tests.
6. **History entry not written**, per the shared-tree rule. Draft below.

### History draft
> **D3 — `business_key_val` uniqueness becomes a database invariant, and 382 MB of
> self-duplicating index goes back.** Adds `server/migrations/add_business_key_unique_index.py`:
> per-table `uq_bk_<table>` UNIQUE indexes built CONCURRENTLY after a per-table duplicate
> census, refusing any table that cannot take one **by name** while the rest of the run
> continues, plus a read-only pre-flight for production. Pairs with `4738d84` (P3): that
> commit widened a cross-process duplicate window from microseconds to a measured 2.4 s,
> and `apply_batch_updates` now catches the resulting `IntegrityError` — only for
> `uq_bk_*`, never for any other constraint — rolls back, and replays so the fresh
> prefetch merges into the row the other process committed. **Production must not receive
> `4738d84` without this.** Second, independent section: 29 indexes that were byte-for-byte
> copies of their own table's primary-key index (382.3 MB, led by `ix_cell_sources_id` at
> 314 MB) are discovered from `pg_index` — never a hardcoded list — and dropped
> CONCURRENTLY, with `models.py` losing `index=True` from all five `primary_key=True`
> declarations that were producing them. `apply_batch_updates` also un-writes the payload
> its first attempt mutated before replaying, so a `replace_map` that loses a race cannot
> re-derive a narrower purge scope than the one it was asked for, and an unresolved
> conflict reaches REST as 409 rather than 500.

---

## 9. Lessons proposed for `agent_workspace/memory/server-pm.md` (not added directly)

- **함정**: **읽기 전용으로 고정한 세션을 풀에 돌려준다.** `SET SESSION`은 DBAPI 커넥션에
  살고 `conn.close()`는 커넥션을 **닫지 않고 풀에 반납**한다. 그래서 사전점검 한 번이
  같은 프로세스의 이후 쓰기를 전부 `ReadOnlySqlTransaction`으로 죽인다 — 이번 라운드에서
  check 다음에 apply를 돌리다 실제로 겪었고, **단위 테스트로는 절대 안 잡힌다**(가짜
  커넥션에는 풀이 없다).
  **올바른 방법**: 세션 수준 설정을 건 커넥션은 `conn.invalidate()`로 **버린다**. 「끝나고
  되돌리는」 문장은 예외 하나에 건너뛰어지는 두 번째 할 일이다.
- **함정**: **`index=True`를 `primary_key=True` 옆에 쓴다.** PK가 만드는 UNIQUE btree와
  키·opclass·collation이 같은 두 번째 인덱스가 생겨 쓰기마다 유지되고 아무도 안 읽는다
  (실측 29개·382.3MB, 최대 314MB 한 개).
  **올바른 방법**: PK 컬럼에는 절대 `index=True`를 붙이지 않는다. 그리고 **이런 부류를
  셀 때는 클래스를 읽지 말고 카탈로그에 술어를 먹여라** — 이번에도 이름난 것은 셋인데
  외연은 29였고, 26개가 **선언 한 줄**(동적 테이블 공용 `row_id`)에서 나왔다.
- **함정**: **재시도를 얹으면서 입력이 그대로일 거라고 가정한다.** 1차 시도가 페이로드를
  제자리에서 고쳐 놓으면(여기서는 `assemble_composite_business_key`가 `updates[key_col]`을
  쓴다) 재실행의 **판정이 달라진다** — 실측으로 `replace_map`의 purge 범위가 맵 전체에서
  한 행으로 좁아졌고, 라우트는 그대로 200에 `deleted: 1`을 냈다. 더 나쁜 것은 그 함수의
  주석이 **「해석기는 이전과 정확히 같은 페이로드를 본다」**고 단언하고 있었다는 점이다 —
  1패스에 대해서는 참이었고, **재시도를 만든 순간 구조적으로 거짓**이 됐다.
  **올바른 방법**: 재시도를 넣을 때 **그 경로가 입력에서 결정을 유도하는지** 먼저 세고,
  유도한다면 1차 시도 **전에** 되돌릴 것을 잡아 둔다(깊은 복사가 아니라 **바뀌는 필드만**).
  그리고 재시도가 무효화하는 **주석의 단언**을 찾아 고쳐라 — 낡은 불변식 주장은 다음 사람을
  정확히 그 함정으로 안내한다.
- **함정**: **동시성 실험에서 창을 벽시계 운에 맡긴다.** 늦은 쪽이 뒤에 커밋하면 결과는
  **경합이 없었던 COUNT 1**인데, 그것이 **병합에 성공한 COUNT 1과 겉모습이 같다**. 이번에
  두 번 그 초록을 받았다.
  **올바른 방법**: 프리페치와 flush **사이**에서 느린 쪽을 **런타임 패치로 붙잡아** 창을
  결정적으로 연다(디스크는 안 건드린다). 그리고 **양성 대조군**(가드 없는 팔)이 실제로
  중복을 만드는지 같은 실행에서 확인하고, 초록의 근거를 **행 수 하나에 두지 말고 회복
  로그가 실제로 찍혔는지**까지 요구한다.
- **함정**: 인덱스를 만드는 마이그레이션이 **`CREATE ... IF NOT EXISTS`가 성공했다는 것을
  강제의 증거로 읽는다.** 취소된 CONCURRENTLY 빌드가 남긴 INVALID 인덱스는 **이름을 잡고
  있어서** 재실행이 영원히 건너뛴다 — 몇 번을 돌려도 컬럼은 무방비다.
  **올바른 방법**: 빌드 뒤에 `indisvalid`를 **직접 확인**하고, 이름만 있고 invalid인 상태는
  「이미 됨」이 아니라 **별개의 거부 상태**로 이름 붙여 DROP 명령과 함께 보고한다.
  🔴 **같은 규율을 DROP에도 적용하라** — `DROP ... IF EXISTS`는 **아무것도 안 맞은 것**을
  조용한 성공으로 바꾸므로, 「314MB 회수」를 찍고 하나도 회수하지 않을 수 있다. 그리고
  식별자를 **따옴표 없이** 보간하면 PostgreSQL이 대소문자를 접어 **다른 이름**을 지운다.
