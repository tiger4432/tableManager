# QA - Live incident diagnosis: `idx_fic_identity` UniqueViolation on checkpoint planning

Incident timestamp: 2026-07-31 20:39:06,297 (`wafer_process`)
Mode: diagnose only, read-only. No file was edited, no DDL/DML was issued.
All DB access used `psycopg2` with `set_session(readonly=True, autocommit=True)`.

---

## Verdict up front

| Question | Answer |
|---|---|
| Q1 - Is the fallback ingestion running on a poisoned transaction? | **No.** The aborted session is process-local to `_plan_checkpoint`, rolled back and closed before the fallback runs. The "ingested from row 0" log line is truthful. |
| Q1' - Was the work lost to a supervisor restart instead? | **No.** Both ingestions committed and the winner's DONE marker is in the DB with `updated_at = 20:39:06.476285`. |
| Q2 - User-visible consequence | **Duplicate rows in the live table.** The file was ingested twice in full; the upsert is a non-atomic SELECT-then-INSERT on an un-constrained `business_key_val`, so it *appended*. Measured: 15 stored rows for 10 parsed `proc_id`s from this one file; **59 surplus rows in `wafer_process`**, **389 surplus rows** across `wafer_process`/`bonding_log`/`inventory_master` carrying the concurrency signature. |
| Q3 - Root cause of the missed lookup | **Concurrency**, discriminated and proven: **two `run_watcher.py` processes** were alive from 20:28:21, each ingesting the same file. Key mismatch and snapshot staleness are both ruled out (evidence below). |

The `UniqueViolation` is the loud symptom. The silent damage is the duplicate business-key rows, which the operator is never told about.

---

## 1. Q1 - transaction lifetime across the `except` boundary

**Finding: contained. The fallback ingestion does not write on the aborted session.**

Trace, with file:line:

1. `server/parsers/directory_watcher.py:1231` - `_plan_checkpoint` opens **its own** session: `db = SessionLocal()`.
   `SessionLocal` is a plain `sessionmaker` (`server/database/database.py:60`), **not** a `scoped_session`, so this is a fresh session on its own pooled connection. There is no thread-local sharing to poison.
2. `server/ingestion_checkpoint.py:171` - the INSERT is flushed by `db.commit()`; the flush raises `UniqueViolation` and SQLAlchemy deactivates that session's transaction.
3. `server/parsers/directory_watcher.py:1237-1245` - the handler calls `db.rollback()` **first** (`:1238`), then logs, then returns `CheckpointPlan.disabled(note=...)`.
4. `server/parsers/directory_watcher.py:1246-1247` - `finally: db.close()` returns the connection to the pool.
5. The fallback ingestion uses a **different** session created per chunk at `server/parsers/directory_watcher.py:1787` (`db = SessionLocal()` inside `_send_to_upsert`), committed at `:1807`, closed at `:1822`.
6. `record_chunk_progress` would be the one call that writes checkpoint state on the *ingestion* session (`:1801-1803`), but it short-circuits on an inactive plan (`server/ingestion_checkpoint.py:231-232`), so it never runs on this path.

This is the shape `f9289f6` established (isolate at the statement-execution point). Here the isolation is structural - the checkpoint machinery never shares a session with the data path - and it holds.

**Confirmed by measurement, not by reading:**

- The winner's checkpoint row exists and is complete:
  `SELECT id, filename, status, processed_rows, started_at, updated_at FROM file_ingestion_checkpoints WHERE file_signature = 'sha256:1808:da97...96a12'`
  -> `id=12424, eqp_wafer_process_20260731_203903.csv, DONE, processed_rows=10, started_at=2026-07-31 20:39:06.293882+09, updated_at=2026-07-31 20:39:06.476285+09`
- The loser's data committed too:
  `SELECT proc_id, row_id, created_at FROM wafer_process WHERE proc_id LIKE 'WP-203903-%'`
  -> 15 rows, two creation instants 1 ms apart: `20:39:06.299158` and `20:39:06.300193`.
- Both runs wrote their own ingestion-log row:
  `SELECT id, status, left(coalesce(error_message,''),60) FROM file_ingestion_logs WHERE filename='eqp_wafer_process_20260731_203903.csv'`
  -> `20672 SUCCESS "[checkpoint-off] ..."` (the loser) and `20673 SUCCESS ""` (the winner).

**Discriminating "aborted transaction" from "killed by a supervisor restart"** (per the coordinator's 20:47 `/health` data, Backend FastAPI Server `restarts: 6`, `last_exit_code: 1`):

Neither happened to this ingestion. The evidence is positive, not absence-of-evidence:

- The watcher process was **not** restarted in this window. `server/launcher.log` shows "Stopping File Ingestion Watcher" at **20:39:32**, 26 s *after* the incident; the previous stop was at 19:18:58.
- The ingestion ran to completion inside 200 ms: `watcher.log` 20:39:06,435 and 20:39:06,461 both log `Local batch update success (10 rows). Changed cells: 70`, then `Successfully processed and archived` at ,452 and ,477, then `File processed ... (SUCCESS)` at ,456 and ,480.
- The DONE marker committed (`updated_at 20:39:06.476285`), which is exactly the marker the `f3fd785` incident *lost*. It is present here.
- The restarts the coordinator measured are on the **API server** process, a different process from the watcher. Nothing on the checkpoint/ingestion path can make the API process exit: every failure in `_plan_checkpoint` is caught at `:1237` and every failure in `_send_to_upsert`'s chunk is caught at `:1817`.

**Could anything I found be causing exit code 1?** Not directly, but the same root condition is in the frame: two launcher instances were supervising simultaneously, so **two uvicorn processes were being pointed at `0.0.0.0:8080`**. I could not confirm a bind failure - `server/server.log` around 20:45:25-26 shows the second app completing startup ("Dynamic table config watcher started", "Decoupled mode active") and then shutting down ~1 s later, and the launcher reports "up 4.0s", which does not match a `WSAEADDRINUSE` (that kills uvicorn before app startup). **Left as runtime-verification.**

---

## 2. Q2 - user-visible consequence of losing checkpointing

### 2a. Does the sha256 dedup still apply?

Yes, but it is not what protects you here.

- `_try_dedup_skip` (`directory_watcher.py:1160-1221`) runs at `:1074`, **before** `_plan_checkpoint` at `:1094`, on its own session (`:1184`). It is untouched by the checkpoint failure.
- In this incident it correctly returned `False` for *both* processes, because at the moment each of them looked, no `DONE` row existed yet. Dedup only defends against a *later* arrival of the same content, never against a simultaneous one.
- The loser never writes a DONE marker: `_finalize_checkpoint` returns immediately on an inactive plan (`directory_watcher.py:1250-1251`, and again in `ingestion_checkpoint.mark_done:246-247`). The marker for this file exists only because the winner wrote it.

Consequence of `plan.active == False` for the loser: no resume offset. For a 10-row demo file that is free. For the 15.6 MB / 415 s files this feature was built for (`ingestion_checkpoint.py:21-25`), a crash mid-file costs the whole file again - the exact P1 regression the module exists to prevent.

### 2b. Re-ingest: upsert or append?

**It appends.** The write path is `_get_or_create_row` (`server/database/crud.py:853-887`): look up by `row_id`, else by `business_key_val` (`:866`), else `db.add()` a brand-new row with a fresh `uuid7()` (`:876-880`). That is a check-then-insert with no `ON CONFLICT` and no unique constraint behind it:

```
SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='wafer_process'
```
-> 24 indexes. The only UNIQUE one is `wafer_process_pkey` on `row_id`. `ix_wafer_process_business_key_val` and `idx_wafer_process_bk` are plain btree. **Nothing in the schema prevents two rows with the same business key.**

So two concurrent ingestions of the same file both find nothing, both mint a fresh `row_id`, and both insert. Idempotency of the upsert is a *single-writer* property, and the module docstring's promise (`ingestion_checkpoint.py:37-39`, "재개 지점이 어긋나도 적재는 business key 기준 upsert이므로 중복 행이 생기지 않는다") is true only under that assumption. It is not true here.

(Note: `server/database/crud.py` is dirty in the working tree, but the dirty hunks are confined to lines 308-386 - `cast_value_by_type` / `clean_str_value`. `_get_or_create_row` at :853 is unchanged from HEAD. Verified with `git diff -U0 server/database/crud.py`.)

### 2c. Do duplicate rows actually exist? Measured: yes.

This file:
```
SELECT count(*) AS rows_stored, count(DISTINCT proc_id) FROM wafer_process WHERE proc_id LIKE 'WP-203903-%'
```
-> `rows_stored = 15, distinct_proc = 10`. Five of the ten `proc_id`s exist twice, each pair created 1 ms apart with different `row_id`s.

Whole table:
```
SELECT count(*) , count(DISTINCT business_key_val), count(DISTINCT proc_id) FROM wafer_process
```
-> `13091 | 13032 | 13032` at the time of measurement (the demo generator adds rows every 3 min). **59 surplus rows.**

All dynamic tables carrying `business_key_val` (per `server/config/table_config.json`):

| table | rows | distinct bk | surplus |
|---|---:|---:|---:|
| bonding_map | 1,760,231 | 1,757,918 | 2,313 |
| inventory_master | 339,370 | 339,168 | 202 |
| bonding_log | 15,470 | 15,341 | 129 |
| wafer_process | 13,093 | 13,034 | 59 |
| **total** | | | **2,703** |

Attribution test - a duplicate produced by this race has all its copies created within milliseconds. Query per table:
```
SELECT count(*) AS dup_groups,
       count(*) FILTER (WHERE spread <= interval '1 second') AS within_1s,
       count(*) FILTER (WHERE spread >  interval '1 second') AS wider
  FROM (SELECT business_key_val, max(created_at)-min(created_at) AS spread
          FROM <t> WHERE business_key_val IS NOT NULL
         GROUP BY business_key_val HAVING count(*) > 1) d
```

| table | dup groups | within 1 s | wider | earliest / latest group |
|---|---:|---:|---:|---|
| wafer_process | 59 | **59** | 0 | 2026-07-28 01:51 / 2026-07-31 20:39:06 |
| bonding_log | 129 | **129** | 0 | 2026-07-28 01:44 / 2026-07-31 20:42 |
| inventory_master | 202 | **201** | 1 | 2026-06-14 00:29 / 2026-07-31 20:43 |
| bonding_map | 1,878 | 628 | 1,250 | 2026-07-17 22:05 / 2026-07-25 07:01 |

`wafer_process`, `bonding_log`, `inventory_master`: **389 duplicate groups, 100% (or 201/202) with the concurrency signature**, and the earliest ones land on 2026-07-28 01:44-01:51, i.e. minutes after the first `UniqueViolation` in the log (2026-07-28 01:38:06). This population is this defect.

`bonding_map` is **a different population and I am not attributing it here**: only 628/1878 groups fit the signature, 1,250 of them share a single day (2026-07-23) with wide spreads, and none is newer than 2026-07-25 - the table has not been touched by the recent double-watcher windows at all. Separate investigation; do not fold it into this fix's blast radius.

### 2d. What the operator sees

- **The grid shows duplicated rows** and the file tab shows **two SUCCESS entries** for one file, one carrying a `[checkpoint-off]` explanation and one carrying nothing.
- The refresh notification fires twice (`watcher.log` 20:39:06,442 and ,467: `Refresh required for wafer_process: 70 rows updated`).
- History is split across two transaction ids for one file:
  ```
  SELECT transaction_id, count(*), min(timestamp) FROM audit_logs
   WHERE table_name='wafer_process' AND row_id IN (SELECT row_id FROM wafer_process WHERE proc_id LIKE 'WP-203903-%')
   GROUP BY transaction_id
  ```
  -> `c769570c...` (5 entries, t0 20:39:06.374615) and `9371480c...` (5 entries, t0 20:39:06.378615), plus one older tx from a 2026-07-28 file.
- **Nothing anywhere tells the operator that the file was ingested twice or that duplicate rows were created.** The only visible artefact is an error message about checkpointing, which is the least important consequence.

This is a direct hit on core value #3 (real-time trust propagation): the grid is fast, is confidently pushed, and is quietly wrong.

---

## 3. Q3 - root cause, discriminated

### It is concurrency. Which two, and what makes them concurrent:

**Two whole `run_watcher.py` processes**, started by two launcher instances, watching the same `ingestion_workspace/*/raws` folders.

Proof chain:

1. `server/launcher.log` - watcher starts, with no intervening stop:
   - `[2026-07-31 19:19:01,819] Starting File Ingestion Watcher: ... run_watcher.py`
   - `[2026-07-31 20:28:21,235] Starting File Ingestion Watcher: ... run_watcher.py` **<- no "Stopping" between these two**
   - `[2026-07-31 20:39:32,737] Stopping File Ingestion Watcher...`
   The incident at 20:39:06 sits inside the overlap.
2. `server/watcher.log` - detections per file, counted with
   `grep -o "New file detected: eqp_wafer_process_2026073[01]_[0-9]*\.csv" watcher.log | sed 's/.*: //' | sort | uniq -c`:
   - every file up to `..._202704.csv` -> **1** detection
   - every file from `..._203002.csv` -> **2** detections
   The transition is exactly the second watcher's start. Same for the 2026-07-28 cluster: `launcher.log` shows a bare `Starting File Ingestion Watcher` at `2026-07-28 01:36:33,514` with no preceding stop, and the first `UniqueViolation` follows at `01:38:06`.
3. Interleaving proves overlap rather than serialization. For the incident file: `No custom pipeline matched` at 06,291 **and** 06,292; `Std parser accepted` at 06,292 **and** 06,293; both parses complete before either plans a checkpoint. The two `Local batch update success` lines are 26 ms apart.
4. The in-process defences cannot see across processes, and this is documented, not accidental:
   - `self.processing_files` + `self._processing_lock` (`directory_watcher.py:639-644`) is per handler instance.
   - `get_workspace_serial_lock` (`directory_watcher.py:274-281`) is module-level, and its own comment at `:269` states the scope: "프로세스 간 배타는 범위 밖".
   - Within one process the loser would have been re-routed to the heavy-lane queue (`:942-946`) and would have logged `Routed to heavy lane queue`. **No such line appears** in the incident window, which is independent confirmation that the two were not in the same process.
   - The retry poller in the watcher process *does* take the workspace lock (`server/run_watcher.py:258-260`), so it is not the second racer. Neither is the admin retry at `server/main.py:4868` - no retry activity for this file.
5. Race window measured: winner's `started_at = 20:39:06.293882`; loser's error at 20:39:06,297. **~3.5 ms.**

### Key mismatch - ruled out

`find_checkpoint` (`ingestion_checkpoint.py:132-139`) filters on exactly `table_name` and `file_signature`, which is exactly `Index("idx_fic_identity", "table_name", "file_signature", unique=True)` (`models.py:242`). No status filter, no extra scope column, no expression/cast asymmetry. Lengths are within the declared limits (`String(100)` / `String(120)` vs `"wafer_process"` and a 76-char signature). And decisively: **the row the loser collided with did not exist when the loser looked** - `file_ingestion_checkpoints.started_at` for that signature is `20:39:06.293882`, i.e. *after* the loser's own SELECT and before its INSERT. A key mismatch would have produced a row with an older `started_at`.

### Snapshot staleness - ruled out

The engine (`server/database/database.py:41-51`) sets no `isolation_level`, so sessions run PostgreSQL's default READ COMMITTED, which takes a fresh snapshot per statement; and the unique check on INSERT reads latest-committed regardless of snapshot. Additionally the session is brand new at `_plan_checkpoint:1231` - the SELECT is the first statement in the transaction, so there is no older snapshot to inherit. The 3.5 ms gap between the winner's commit and the loser's INSERT is the whole story.

### The latent defect that survives fixing the double-launch

Even with exactly one watcher, `plan_ingestion` (`ingestion_checkpoint.py:163-172`) is a check-then-insert with no `ON CONFLICT`, and `_get_or_create_row` (`crud.py:853-887`) is a check-then-insert with no unique constraint. The admin retry endpoint (`server/main.py:4868`) runs in the **API server process** and takes no cross-process lock, so a retry clicked while the watcher is ingesting the same content reproduces both failures. The double-launch made a latent race routine; it did not create it.

---

## 4. The `lot`/`slot` vs `lot_id`/`slot_no` duplication - does it interact?

Marginally, and not causally.

- `server/ingestion_workspace/wafer_process/auto_update/generate_wafer_process.py:126-127` writes `lot_id = lot` and `slot_no = slot` by construction, so the duplicate columns are always equal and the duplicated *rows* carry both pairs identically. It neither causes nor worsens the race.
- Where it does compound: the 59 surplus rows inflate the `bonding_log ⋈ wafer_process (lot, slot)` virtual join fan-out (`server/virtual_join_config.py:10`) and show up as repeated process-history entries in the `wafer_process` reference view (`server/enrichment_config.py:425`, `limit: 50`) - a view whose whole job is to be the operator's evidence.
- The generator's own coverage probe (`generate_wafer_process.py:71`, `SELECT DISTINCT lot, slot`) is immune - `DISTINCT` absorbs the duplicates.

**Separate finding, noticed in passing (not part of this incident):** `proc_id` is `WP-<HHMMSS>-<seq>` (`generate_wafer_process.py:122`), so it collides across days. Rows `WP-203903-000..004` in the live table were created `2026-07-28 20:39:06` and were silently **overwritten** by today's file, which reused the same `proc_id`s. That is a demo-generator key-design defect, independent of the race, and it means the "no duplicate rows" outcome for those five keys was destruction, not idempotency.

---

## 5. Queries run (all read-only)

Every DB connection used `set_session(readonly=True, autocommit=True)`.

1. `SELECT id, table_name, filename, source_kind, total_rows, processed_rows, chunk_index, status, started_at, updated_at, left(note,60) FROM file_ingestion_checkpoints WHERE file_signature = %s`
2. `SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('file_ingestion_logs','wafer_process') ORDER BY ordinal_position`
3. `SELECT id, table_name, status, left(coalesce(error_message,''),60) FROM file_ingestion_logs WHERE filename = %s ORDER BY id`
4. `SELECT business_key_val, count(*) FROM wafer_process GROUP BY business_key_val HAVING count(*) > 1 ORDER BY 2 DESC LIMIT 10`
5. `SELECT proc_id, count(*) FROM wafer_process GROUP BY proc_id HAVING count(*) > 1 ORDER BY 2 DESC LIMIT 10`
6. `SELECT count(*), count(DISTINCT business_key_val), count(DISTINCT proc_id) FROM wafer_process`
7. `SELECT proc_id, row_id, created_at, updated_at FROM wafer_process WHERE proc_id LIKE 'WP-203903-%' ORDER BY proc_id`
8. `SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='wafer_process'`
9. `SELECT proc_id, count(*), min(created_at), max(created_at) FROM wafer_process GROUP BY proc_id HAVING count(*)>1 ORDER BY min(created_at)`
10. `SELECT count(*), count(DISTINCT transaction_id), count(DISTINCT (row_id,column_name)) FROM audit_logs WHERE table_name='wafer_process' AND row_id IN (SELECT row_id FROM wafer_process WHERE proc_id LIKE 'WP-203903-%')`
11. `SELECT transaction_id, count(*), min(timestamp), max(timestamp) FROM audit_logs WHERE ... GROUP BY transaction_id ORDER BY 3`
12. `SELECT filename, table_name, count(*) FROM file_ingestion_logs WHERE created_at >= '2026-07-31 19:00+09' GROUP BY 1,2 HAVING count(*)>1 ORDER BY 3 DESC, 1 LIMIT 20`
13. `SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'`
14. per table: `SELECT count(*), count(DISTINCT business_key_val) FROM public."<t>" WHERE business_key_val IS NOT NULL`
15. per table: the `spread <= interval '1 second'` attribution query in section 2c
16. `SELECT date_trunc('day', first_seen), count(*) FROM (...bonding_map dup groups...) GROUP BY 1 ORDER BY 1`

Non-DB measurements: `grep`/`awk` over `server/watcher.log`, `server/launcher.log`, `server/server.log`; `Get-CimInstance Win32_Process`; `Get-NetTCPConnection -State Listen -LocalPort 8080,8081`.

**Not run:** the pytest suite. A `pytest server/tests/ -q` was already in flight on this box (PID 39952, started 20:44) against the shared isolated database; starting a second one would have contended with the user's run and produced meaningless results. No code changed, so there is no diff to regress.

---

## 6. Proposed fix (PROPOSED - not applied)

Three independent layers. They are not alternatives; the first two are the correctness fix and the third is the operability fix.

### P1 - make both check-then-insert sites atomic (the real fix, ~15 lines)

- `server/ingestion_checkpoint.py:163-172` - replace `find_checkpoint` -> `db.add` -> `commit` with a PostgreSQL `INSERT ... ON CONFLICT (table_name, file_signature) DO NOTHING RETURNING id`, then re-read on conflict and fall through to the existing "row already exists" branch at `:174`. The branch is already written and already handles every state (DONE / parser mismatch / offset damage); the loser should *land in it* instead of throwing. SQLite variant needed for the test path (`sqlite_on_conflict` / plain retry).
- `server/database/crud.py:853-887` - `_get_or_create_row` needs a **unique index on `(business_key_val)` per dynamic table** plus an insert that tolerates the conflict, otherwise nothing structurally prevents duplicates no matter how the callers are serialized. The index must be created `CONCURRENTLY` and only after the existing duplicates are cleaned, and `bonding_map` at 1.76 M rows needs a measured window. **This is the change that actually protects the data**, and it is also the riskiest - it should be its own dispatched round with its own QA.

### P2 - stop the double launch (removes today's trigger)

`run_decoupled_app.py` has no singleton guard (grepped: no lockfile, no pid file, no port pre-check). A second launcher silently supervises a second copy of all five processes. Proposed: a boot-time exclusive lock (a lock file under `server/config/` or an exclusive bind on the API port before spawning children) that makes the second launcher refuse with a clear message naming the running instance's PID. This also removes the most likely explanation for two uvicorns fighting over `0.0.0.0:8080`, which is worth checking against the API server's exit-code-1 restarts.

### P3 - stop lying by omission (small, do it regardless)

`_plan_checkpoint`'s message (`directory_watcher.py:1239-1245`) reports the least important consequence. When the failure is specifically a `UniqueViolation` on `idx_fic_identity`, that is *positive evidence that another writer is processing this exact content right now* - the correct response is to log it as a concurrent-ingestion warning naming the other writer's `filename`/`started_at` (both readable from the conflicting row), and ideally to **abandon this ingestion** rather than duplicate it. At minimum the `[checkpoint-off]` detail surfaced to the operator should say "this file may already be ingested by another process".

### Cleanup (user's call, user's hands)

389 surplus rows across `wafer_process` / `bonding_log` / `inventory_master` carry the concurrency signature and are safe to identify with the section 2c query. **I did not delete anything.** Deleting them requires deciding which `row_id` survives (the copies are not identical - they carry different `row_id`s and separate `audit_logs` transactions, and `cell_sources`/`cell_overwrites` rows are keyed by `row_id`). `bonding_map`'s 2,313 surplus rows are a **different** population and must not be swept up in the same operation.

---

## 7. Runtime verification still needed

1. Why the API server exits with code 1. The 20:45 evidence shows full startup then shutdown ~1 s later, which is *not* a port-bind failure; the launcher's "up 4.0s" does not fit `WSAEADDRINUSE` either. Needs the child's stderr, which the supervisor does not appear to route into `server.log`.
2. Whether `bonding_map`'s 1,250 wide-spread duplicate groups (all 2026-07-23) are a third defect or an intentional re-map.
3. Whether the admin retry path (`server/main.py:4868`, API process) can reproduce the same collision with a single watcher running. Predicted yes from code; not observed live.

## 8. Proposed lesson for `agent_workspace/memory/qa-reviewer.md`

> **함정**: "동시성 의심"을 프로세스 내부 락만 보고 판정하면, 같은 스택이 **두 번 기동된** 상황을 놓친다. 모듈 레벨 락은 프로세스 경계를 넘지 못하고, 코드에는 그 사실이 주석으로만 적혀 있다.
> **올바른 방법**: 중복 로그 라인이 보이면 먼저 `launcher.log`에서 "Starting X" 앞에 대응하는 "Stopping X"가 있는지 확인하고, 중복 시작 시각과 증상 시작 시각을 대조한다. 프로세스 목록(`Get-CimInstance Win32_Process`)은 현재 시점만 보여주므로 과거 창을 증명하지 못한다.

> **함정**: "업서트라서 중복이 안 생긴다"는 문서/주석의 주장을 그대로 받으면, 그 멱등성이 **단일 기록자 가정**에 의존한다는 것을 놓친다.
> **올바른 방법**: 업서트 주장을 만나면 `pg_indexes`에서 그 키에 **UNIQUE 제약이 실제로 있는지** 확인한다. 없으면 그것은 업서트가 아니라 "보통은 맞는 SELECT-then-INSERT"다.
