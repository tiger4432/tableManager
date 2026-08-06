# QA-P3 — adversarial review of the set-based write path

**Tier:** T2 · **Date:** 2026-08-07 · **Reviewer:** qa-reviewer
**Subject:** `server/database/crud.py` (+297, unstaged) — the P3 set-based write path
**Lane report reviewed:** `agent_workspace/reports/Server_P3_set_based_write.md`
**No code was modified. No commit was made.** Probe files were added to `server/tests/`
for the differential runs and removed afterwards; `crud.py` and `map_alignment.py`
md5 are unchanged from before my first run to after my last.

---

## 1. Verdict

### **GO-WITH-FIXES**

The change is **correct**. I ran HEAD's `crud.py` and the working tree's `crud.py`
through the same scenarios against the same schema and diffed the *content* of every
table the write path touches — data rows, `cell_sources`, `cell_overwrites`,
`audit_logs`, `database_outbox`. **Byte-identical in all five, in every scenario.**
Layering did not move.

The fixes are not in the change; they are in what the change left red.
**Two suite failures must be resolved before this is committed**, and exactly one of
them is a legitimate supersession that requires editing a test rather than the code.

---

## 2. The clean suite run

Run once, `PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest server/tests/ -q`.

**Final line, verbatim:**

```
3 failed, 3105 passed, 12 skipped, 1 xfailed, 108 warnings in 802.51s (0:13:22)
```

```
FAILED server/tests/test_composite_key_prefetch_budget.py::test_inserting_new_rows_still_probes_once_per_row
FAILED server/tests/test_config_reload_integrity.py::test_inv_9_1_atomic_save_event_applies_physical_alter
FAILED server/tests/test_set_based_write_path.py::test_a_user_layer_still_beats_a_later_parser_write
```

### What was in the tree when I ran — this number is NOT clean, and covers TWO changes

| in tree | state |
|---|---|
| `server/database/crud.py` (+297) | **unstaged, P3 — the change under review** |
| `server/map_alignment.py` (+291), `server/scripts/seed_dt_index_walk.py` | **staged, the alignment lane's** |
| `server/tests/test_bin_fingerprint_shift.py`, `test_dt_index_walk_core_axis.py`, `test_index_group_count.py` | **staged, new, the alignment lane's** |
| `server/tests/test_set_based_write_path.py` | untracked, P3's, **never executed before this run** |
| `client2/src/map2/main.js`, `map_editor2.js`, `tests/map_editor2_shell_harness.mjs` | unstaged, client lane's — cannot affect pytest |
| `docs/architecture/backend.md`, `data_model.md`, `history/README.md`, `process/PROJECT_STATUS.md` | unstaged, mixed sessions |

**Attribute this number to both server changes, not to `crud.py` alone.**

**Contamination check (this is the thing the last run got wrong).** Server-side mtimes
at run start: `crud.py` 03:13:55, `map_alignment.py` 03:19:08 — both **predate** the run
(started 03:32:36, finished 03:46). The only file that moved during the run was
`client2/src/map2/main.js` at 03:26:57 — before the run, and outside pytest's reach
either way. md5 of `crud.py` and `map_alignment.py` identical before and after.
**The server tree was still for this run.**

**Lost run, disclosed.** My first run (PID 42376, started 03:22:15) survived the host
process exiting but its stdout went to a dead pipe — the output file was 0 bytes and
unrecoverable. I killed it and started over rather than report a number I did not read.
I did not run two pytest processes concurrently.

---

## 3. Confirmed findings

### 🔴 H1 [HIGH] — `test_inserting_new_rows_still_probes_once_per_row` is red, and the expectation IS legitimately superseded

`server/tests/test_composite_key_prefetch_budget.py:139-154`

```
E   AssertionError: one prefetch that matches nothing, plus one futile probe per row
E   assert 1 == (200 + 1)
```

**Adjudication: superseded, not a behaviour loss.** The measured value is **1** — the
chunk's single prefetch SELECT — and the 200 futile per-row probes are gone. That is
exactly what the test's own docstring named as future work:

> *"Closing this needs a business-key equivalent of `prefetched_row_ids`, which is a
> separate correctness argument and is not made here."*

P3 made that argument (`ProbedIdentity`). Nothing was lost: `test_QAP3` differential
scenario `fresh_then_repush` proves the same rows land with the same content.

**Required fix — edit, do not delete.** Change the assertion to `== 1`, rewrite the
docstring to say the proof is now read, and name the round that closed it. Also fix
the **module docstring at `:22-26`**, which still lists this as one of "two things this
deliberately does not fix". Deleting the test would remove the only budget net on the
insert path, which is precisely the path P3 changed.

### 🔴 H2 [HIGH] — `test_a_user_layer_still_beats_a_later_parser_write` is red, and it is **NOT a P3 regression** — but the lane must not ship it red

`server/tests/test_set_based_write_path.py:247-276` (the lane's own new test, first executed by me)

```
sqlalchemy.exc.NoResultFound: No row was found when one was required
  db_session.query(model).filter(model.business_key_val == "LP_01_2_2").one()
```

I ran **the exact body of that test against a HEAD copy of `crud.py`** loaded as a
sibling module. Result:

```
[QAP3 HEAD] rows matching key LP_01_2_2: 0
[QAP3 HEAD] ALL rows: [('', None, 'USER_VALUE')]
[QAP3 NEW]  rows matching key LP_01_2_2: 0
[QAP3 NEW]  ALL rows: [('', None, 'USER_VALUE')]
```

Identical. This is the lane's own **pre-existing defect #1** (a payload carrying its key
column empty wipes `business_key_val` on the second push), which the lane documented and
deliberately did not fix — and then wrote a new test whose `_item()` helper always sends
`cell_key=""`, so the test walks straight into it.

🟩 **The core value HELD, on both.** I dumped the resolved value and every stored layer:

```
[QAP3 HEAD] row bk='' resolved_bn='USER_VALUE'
            sources={'pipeline_parser': 'PARSER_VALUE', 'user': 'USER_VALUE'} ow=(True, None)
[QAP3 NEW]  row bk='' resolved_bn='USER_VALUE'
            sources={'pipeline_parser': 'PARSER_VALUE', 'user': 'USER_VALUE'} ow=(True, None)
```

A human's correction beat the later automatic write, both layers are stored, the
overwrite marker is set — identically before and after. **The test fails on
findability-by-key, not on the layering verdict.** Its message is misleading about what
broke, which is worth fixing on its own.

**Required fix:** the test must resolve the row by `row_id` or by `lot`, with a comment
naming the pre-existing defect it is steering around — or the defect gets fixed first
and the test keeps its current shape. Either way, do not commit with this red.

### 🟠 M1 [MEDIUM] — the third failure is flaky and unrelated to `crud.py`

`server/tests/test_config_reload_integrity.py::test_inv_9_1_atomic_save_event_applies_physical_alter`

Reran that file alone: **32 passed**. The captured teardown log shows the ALTER
*succeeding* (`Successfully added column 'qty' to table 'cfgint_alter_0'`) — i.e. the
debounced watchdog reload lands **after** the assertion under full-suite CPU load. A
timing race in a filesystem-watcher test, not a write-path defect. Do not block on it;
it is worth its own item if it recurs.

### 🟠 M2 [MEDIUM] — the proof of absence is now stale for the length of a chunk, and that window is only closed WITHIN a process

`server/database/crud.py:2816-2820` (built once), consumed at `:1670`/`:2239` throughout the loop.

`ProbedIdentity` is a statement about the database **at prefetch time**. The lane's
correctness argument — "nothing in the loop can change it, nothing is flushed inside
`no_autoflush`" — is sound *for this transaction*. It says nothing about **other
processes**.

Same-table ingestion is serialized by `get_workspace_serial_lock`
(`server/parsers/directory_watcher.py:334`), whose own comment reads
`프로세스 간 배타는 범위 밖 — 기존과 동일`. This system runs 5 processes, and at least
three of them call `apply_batch_updates`: the API (`main.py` — grid edit, map push), the
watcher, and `chain_ingestion_worker`.

**Failure scenario.** Watcher prefetches a 1,000-row chunk at T0 and proves business key
`K` absent. At T1 the API process commits a row carrying `K` (an operator's map push into
the same table). At T2 the watcher reaches the item for `K`: on HEAD its per-row
`get_row_by_business_key` sees the committed row (READ COMMITTED) and **updates** it; with
P3 the stale proof says "absent" and it **mints a second row with the same business key**.
There is no unique index on `business_key_val`, so nothing refuses it. The operator sees
a duplicate die.

The window widens from roughly zero to one chunk's processing time — **~3.7 s at 1,000
rows** by the lane's own measurement. Partially self-healing: the next push's
`_find_business_key_conflict` would find and merge the pair.

**Not reproducible from code alone** — I could not drive two processes at one table.
Routed to §5 (runtime verification). If cross-process concurrent writes to one table are
possible in production, this deserves either a chunk-scoped re-probe on the insert branch
or a unique index.

### 🟡 L1 [LOW] — the `updated_at` removal rests on a physical DEFAULT the suite can never check

`server/database/crud.py:1645-1658` (the `updated_at=func.now()` removal),
`server/database/models.py:666` (`server_default=func.now()`).

`test_new_rows_still_get_an_updated_at` (`test_set_based_write_path.py:115`) **passed**,
and my own probe confirmed non-NULL on a fresh insert. But SQLite always builds the table
from the model, so that declaration is always present in the suite — **the test cannot
fail**, whatever a production table actually carries. This is the "SQLite accepts what
Postgres refuses" class, inverted.

The lane checked `assy_qa` and found a DEFAULT on every `updated_at`; `assy_qa` is a
snapshot of this box, not production evidence.

**Damage is bounded** if the DEFAULT is ever missing: `stage_event`
(`server/database/database.py:169`) explicitly **excludes** `updated_at` from the outbox
payload, and `main.py:648`/`:1180` coalesce to `created_at`. What would degrade is
`order_by=updated_at` — the **Sort Latest** default path (`main.py:1620`, `:1888`;
`client2/src/api.js:267`) — where NULLs sort to one end. Verification SQL in §5.

### 🟡 L2 [LOW] — the collision-merge path changed the KIND of timestamp it stores

`server/database/crud.py:2276` (`cell_overwrites.updated_at`), `:2341`, `:2372`
(`cell_sources.ingested_at`): `func.now()` → `datetime.now()`.

That is DB-clock tz-aware → Python-local **naive**, written into a
`DateTime(timezone=True)` column. It is consistent with every other producer in the same
function, and it cannot move a layering verdict — `compute_priority_value`
(`crud.py:1075-1095`) sorts by `resolve_priority_map` alone and never reads a timestamp,
which I verified rather than assumed. But it **is** a stored-value change against HEAD in
a column the history/timeline surfaces, and if the PG session `TimeZone` differs from the
box's local zone the two spellings differ by that offset. Worth one line in the round's
notes; not worth blocking.

### 🟡 L3 [LOW] — one doc now states a false claim in the affirmative

**`docs/architecture/CODE_MAP.md:741`** — the row for `_get_or_create_row`:

> *"⚠️ 프리페치의 부재 증명을 읽지 않는다 — 그래서 신규 행 삽입은 여전히 행당 `SELECT`를 낸다"*

It reads it now, and the signature gained `probed_identity`. Four new symbols are absent
from the map entirely: `ProbedIdentity`, `_absence_is_proven`,
`_find_business_key_conflict`, `_is_executemany_safe`. (code-mapper's territory, but the
claim is load-bearing and now false.)

**`docs/spec/batch_update_technical_specification.md`** is the DOC_OWNERSHIP row-110 doc
for `crud.apply_batch_updates`; its code listings at `:270` and `:506` still show the two
`func.now()` sites this round changed, and its performance table at `:611` claims
`배치 루프 내 SELECT 쿼리 수 = 0회` — a claim that was *false before* and is much closer to
true now. **Downgraded to LOW** because that document's own 2026-08-06 status header
already declares its code blocks stale copies. One `Last-verified` bump plus §611, not a
rewrite.

I checked `docs/process/DOC_OWNERSHIP.md` by code path rather than trusting the lane's
follow-up list: rows 96 (데이터 모델/레이어링), 97 (버전 게이트), 110 (배치 업서트) are the
`crud.py` rows. The lane covered 96's target (`data_model.md`) and `backend.md`
correctly and thoroughly; 110's target and CODE_MAP are the gaps. Row 97's version gate
is untouched by this diff — confirmed, `version_gate_verdict` is not in the diff and does
not read `updated_at`.

---

## 4. Hypotheses I tried to break and could not

Each was attacked with a probe or a specific code path, not by reading and concluding.

| hypothesis | why it is safe |
|---|---|
| **Layering moved / a different source wins** | Differential HEAD vs working tree over 5 scenarios (`fresh_then_repush`, `three_pushes_empty_key`, `user_then_parser`, `rename_then_old_key`, `whitespace_key`): data rows, `cell_sources` (source_name/value/updated_by), `cell_overwrites` (is_overwrite/updated_by/manual_priority_source), `audit_logs` (old/new/source/updated_by), `database_outbox` (event_type/business_key/payload key set) — **identical in every one**. This is content, not counts. |
| **`LightCellSource` is immutable, so `src_obj.value = …` silently no-ops or throws** | `crud.py:395-404` — plain class, `__slots__` carrying all 7 fields, ordinary `__init__`. The mutations at `crud.py:1997-1999` work, and `compute_priority_value` reads only fields it carries. |
| **`LightCellOverwrite` reaches `db.delete(ow)`** | That branch (`crud.py:2100`) only runs when `cell_overwrites_to_delete is None`; `apply_batch_updates` always passes it. And the prefetch already put Light objects in `overwrites_cache` at HEAD, so the exposure is pre-existing either way. |
| **A padded business key becomes permanently unprovable and duplicates** | `get_row_by_business_key` compares `business_key_val == str(v).strip()` with **no DB-side TRIM** (`crud.py:1043-1053`), and `target_bks` is built with the same `.strip()` (`crud.py:2773`) — the prefetch answers exactly the question the skip asks. Differential scenario `whitespace_key` identical. |
| **`_found_bks` is contaminated by rows the prefetch matched on `row_id`** | It is — those rows' business keys are subtracted too. That only **shrinks** the proven-absent set, i.e. more DB queries. Safe direction. |
| **`_find_business_key_conflict` skips a real conflict** | `crud.py:2234-2244`: it skips only when the key is BOTH absent from `row_cache` AND in the proven-absent set. `probed` answers the strictly stronger "no row at all holds this value", which implies "no *other* row holds it". |
| **`new_bk_val` (built from row values) vs `target_bks` (built from payload) diverge and the skip fires wrongly** | Divergence can only make a value *not* found in the proven set → falls through to the query. Slower, never wrong. The set is a fact about the value, not about which item asked. |
| **Empty or ragged mapping list crashes the new fast path** | Both bulk functions `return` on empty before reaching `_is_executemany_safe`; the predicate refuses ragged key sets and any `ClauseElement`, falling back to the exact old `.values(chunk)` path. `test_a_ragged_mapping_list_is_still_refused` and `test_bulk_upsert_falls_back_when_a_mapping_holds_a_sql_expression` both green. |
| **The outbox event is lost when the INSERT becomes `insertmanyvalues`** | `auto_stage_database_outbox` fires on **`before_flush`** over `session.new`/`session.dirty` (`server/database/database.py:128-152`) — before any SQL, indifferent to statement batching. Data rows are still ORM instances. `test_every_new_row_still_stages_an_outbox_event` green. |
| **The outbox payload carried `updated_at` and now carries None** | `stage_event` **excludes** `updated_at` from `data_dict` by name (`database.py:169`). Zero effect. |
| **The virtual-join refusal funnel moved** | `refuse_virtual_join_columns` is still the **first statement** of `apply_batch_updates` (`crud.py:2609`), ahead of `transaction_context` (`:2616`) and the `replace_map` purge (`:2625`). `test_S8b_...` **PASSED** — see the correction below. |
| **A caller sees a changed failure shape** | Zero added `raise` in the diff (grep on the diff for `^+.*raise `: 0). `apply_batch_updates`' signature and 4-tuple return are unchanged; the two new parameters are defaulted keyword args on *internal* functions. All 13 call sites re-enumerated; none unpacks differently. |
| **Pre-existing defect #1 is actually this round's** | Measured per push, HEAD and NEW: `(rows, distinct_bk)` = **`(5,5) → (5,1) → (10,6)`** on both. Reproduces the lane's 5→5→10 exactly. **Not this round's.** |
| **Pre-existing defect #2 (collision shell row) is this round's** | The lane's `test_collision_merge_still_fires_against_a_row_outside_the_prefetch` passed and deliberately does not pin the row count for this reason. Differential shows identical content. **Not this round's.** |

### Correction to the brief's premise

**`test_S8b_the_write_guard_does_not_read_the_announcement_structurally` PASSED in my
clean run.** It AST-parses `crud.refuse_virtual_join_columns` — a function this diff does
not touch — and asserts it calls `virtual_only_columns`, which it still does at
`crud.py:2561`. The test never mentions `_get_or_create_row`. Its earlier red was
contamination or misattribution, not this lane.

---

## 5. Runtime verification required (cannot be settled from code)

1. **M2 — cross-process concurrency.** Is it possible in production for two processes to
   write the *same table* through `apply_batch_updates` at overlapping times (operator map
   push during a file ingestion into the same table; `chain_ingestion_worker` writing a
   derived table the watcher also feeds)? If yes, M2 is a real duplicate-row path.
2. **L1 — the `updated_at` DEFAULT, on production, not on this box.** One read-only query:
   ```sql
   SELECT table_name FROM information_schema.columns
   WHERE table_schema='public' AND column_name='updated_at' AND column_default IS NULL;
   ```
   Any row returned is a table where a P3 insert lands `updated_at` NULL.
3. **The benchmark numbers themselves.** 796.2 s → 375.8 s and 301,100 → 1,200 are the
   lane's, on this box, in an isolated `assy_qa`. I did not re-run them. I verified the
   *shape* of the claim independently: the suite's own budget test now measures **1**
   data-table SELECT where it measured **201**, which is the 251× statement claim in
   miniature and is consistent.
4. **The mutation harness's silence (brief item 4).** I did **not** re-inject the
   un-subtracted `probed_identity` — that requires editing `crud.py`, which this review
   forbids. What I can report: `test_a_rename_inside_one_batch_does_not_orphan_the_old_key`
   passed in the clean run, and by the lane's own account it is the **only** net over that
   defect while the other 13 stayed silent. **That is a coverage finding regardless of the
   fix being right** — the harness went silent on 2 of 3 injected defects. A single bespoke
   probe standing between a subtle cache-ordering bug and a duplicated row is thin cover
   for the layering core.

---

## 6. Doc consistency

- ✅ `docs/architecture/backend.md` §3 2-ter and `data_model.md` §2.1-quater are accurate,
  and both correctly retract the previous round's closing sentence rather than editing it
  away. `data_model.md`'s claim "우선순위 판정은 한 줄도 바뀌지 않았다" is **true** — I
  verified `compute_priority_value`, `resolve_priority_map` and `SOURCE_PRIORITY` are
  untouched by the diff and confirmed the outcome empirically.
- ⚠️ **Overstatement in the lane report §3, and it matters.** *"pytest was NOT run …
  `server/tests/test_set_based_write_path.py` — new, 14 test functions"* is presented
  beside "**14 probes … All 14 pass**". A reader skims that as "14 tests pass". **One of
  the 14 pytest functions fails** — and it is the one named for the system's first core
  value. The lane's PostgreSQL probe with the same name passed because the probe did not
  look the row up by business key. Two nets with the same name and different verdicts is
  exactly the shape that hides a defect.
- ⚠️ Lane report §5's isolated-environment note (a `confirmation_uid` column added to
  `assy_qa`) is a deliberate residue in a shared environment and needs a Lead PM ruling —
  refresh the snapshot or run `server/migrations/add_frame_confirmation.py` there.
- ❌ `docs/architecture/CODE_MAP.md:741` false (L3). `docs/spec/batch_update_technical_specification.md`
  stale but self-disclosed (L3).
- The two pre-existing defects are **correctly** reported as not this round's, and I
  confirmed both reproduce identically on a HEAD copy. **They should be routed as separate
  items and must not block this change.** Defect #1 is serious on its own terms — measured
  `(5,5) → (5,1) → (10,6)`, i.e. every map row duplicated on the third push of a file whose
  key column is empty — and it is what makes the lane's own layering test red.

---

## 7. What to do, in order

1. Fix **H1**: `test_inserting_new_rows_still_probes_once_per_row` → assert `== 1`,
   rewrite its docstring and the module docstring at `:22-26`. Do not delete it.
2. Fix **H2**: `test_a_user_layer_still_beats_a_later_parser_write` must not assert
   findability by business key while pre-existing defect #1 stands — or fix that defect
   first. The layering assertion itself is sound and should stay.
3. Re-run the suite. Expected: `1 failed` (the flaky config-reload race) or `0 failed`.
4. Correct **L3** (CODE_MAP:741 + the four new symbols).
5. Route pre-existing defects #1 and #2 as their own items. #1 first — it duplicates
   production map rows.
6. Answer **M2** (cross-process concurrency) and run the **L1** SQL against production
   before deploy.

---

## 8. Proposed memory entries (for the Lead PM to rule on — not added)

- **「테스트를 썼다」와 「테스트가 초록이다」는 다른 주장이다.** 같은 이름의 프로브와
  pytest 함수가 서로 다른 판정을 낼 수 있다 — 프로브는 `row_id`로 찾고 테스트는 업무
  키로 찾았고, 그 차이에 미수리 결함이 숨어 있었다. 실행하지 않은 테스트는 산출물이
  아니라 부채다.
- **빨강의 소유자를 diff로 정하지 말고 HEAD 사본으로 정하라.** 이번 라운드의 빨강 셋 중
  **하나도** 이 변경의 회귀가 아니었다(하나는 정당한 승계, 하나는 기존 결함, 하나는
  플래키). HEAD 복사본을 형제 모듈로 로드해 같은 시나리오를 돌리는 것이 30초짜리
  판정 장치다.
- **부재 증명은 트랜잭션 안에서만 참이다.** `no_autoflush`가 막는 것은 *내* 루프이지 옆
  프로세스가 아니다. 프리페치 증명을 루프 전체에 걸쳐 쓰는 순간, 창은 「한 행」에서
  「한 청크」로 넓어진다.
