# P2 live drills — D1 / D2 / D3 in the isolated environment

- Executed by: server-pm · 2026-07-27 00:13–01:25 KST
- Environment: **isolated only** — API `127.0.0.1:8081`, DB `assy_qa`, data root `dev_env/`
- Feature under test: P2 (offset checkpoint resume + sha256 file dedup + issue #10), commit `f78ab0a`, merged and live
- **No source file was modified.** Production was not written to (§6).
- First use of the isolated environment built in `Server_dev_env_isolation.md`.

## Verdict

| drill | result | the number that decides it |
|---|---|---|
| **D1 — checkpoint resume** | **PASS** | killed at a durable offset of **30,000 / 100,000**; finished with **100,000** rows and **100,000** distinct keys, zero missing expected keys |
| **D2 — signature dedup** | **PASS** | identical re-drop **1.22 s / SKIPPED / +0 rows**; `__force__` re-drop **1,687.21 s / SUCCESS / full reload** — a **1,383×** separation |
| **D3 — issue #10** | **PASS** | two targets under one chain tx, counts **5** and **2**, history total **7**; the pre-fix SET semantics would have shown **2** |
| **regression watch** | **PASS** | 11,371 event-loop samples, p50 5.1–5.2 ms, **zero** samples >250 ms; chain `notify=` 0–31 ms; checkpoint overhead below the measurement noise floor |

Nothing about P2 failed. Four findings — three about the **tooling**, one about a
pre-existing runtime behaviour — are in §7. Two of them are real isolation gaps.

---

## 1. Watcher target proof — before a single drill file was fed

`devenv up` deliberately starts no watcher and has no flag to start one, so the watcher was
started by a purpose-written launcher that **refuses to start** unless the running process itself
proves it is isolated. The assertions are made from inside the process, not from the environment
variables the parent believes it set.

```
[iso-watcher] env ASSY_DATA_ROOT = 'C:\Users\kk980\Developments\assyManager\dev_env'
[iso-watcher] env DATABASE_URL = 'postgresql://postgres:admin@localhost:5432/assy_qa'
[iso-watcher] env API_BASE_URL = 'http://127.0.0.1:8081'
[iso-watcher] paths.SERVER_DIR    = C:\Users\kk980\Developments\assyManager\server
[iso-watcher] paths.DATA_ROOT     = C:\Users\kk980\Developments\assyManager\dev_env
[iso-watcher] paths.CONFIG_DIR    = C:\Users\kk980\Developments\assyManager\dev_env\config
[iso-watcher] paths.WORKSPACE_DIR = C:\Users\kk980\Developments\assyManager\dev_env\ingestion_workspace
[iso-watcher] paths.IS_ISOLATED   = True
[iso-watcher] engine.url          = postgresql://postgres:***@localhost:5432/assy_qa
[iso-watcher] LIVE CONNECTION      -> current_database='assy_qa' port=5432 backend_pid=1320 user='postgres'
[iso-watcher] ALL TARGET ASSERTIONS PASSED - starting watcher
```

`LIVE CONNECTION` is the load-bearing line: it is the answer from an actually-opened
`SessionLocal()`, i.e. the database the watcher's own connection pool reaches — not a string
parsed out of a variable. Any failed assertion exits 9 before a single watchdog handler is
registered. `run_watcher.API_BASE_URL` is re-checked after import, because `:8080` there would
have posted every progress and completion event into the **production** web server.

Registered watch, from the watcher's own log:

```
[Watcher.DirectoryWatcher] Watching: ...\dev_env\ingestion_workspace\p2drill_resume\raws (Std-parser workspace (table_config resolved), Table: p2drill_resume)
```

### 1.1 Sentinel — one row, then identical queries against both databases

A one-row CSV carrying `P2DRILL_SENTINEL_9c41ab7e` was dropped into the isolated `raws/`. The
watcher ingested it (14 changed cells, archived, `SUCCESS`). Then the **same query text** was run
against both databases. The isolated column is the sensitivity control — it is what a non-zero
answer looks like.

```
### assy_qa (isolated)                              ### assy_manager (PRODUCTION)
                                                    [read-only guard verified: SQLSTATE 25006]
   drill table exists                        -> 1      drill table exists                        -> 0
   file_ingestion_logs filename              -> 1      file_ingestion_logs filename              -> 0
   file_ingestion_logs table_name p2drill%   -> 1      file_ingestion_logs table_name p2drill%   -> 0
   file_ingestion_checkpoints filename       -> 1      file_ingestion_checkpoints filename       -> 0
   cell_sources table_name p2drill%          -> 14     cell_sources table_name p2drill%          -> 0
   audit_logs table_name p2drill%            -> 1      audit_logs table_name p2drill%            -> 0
   audit_logs new_value carries sentinel     -> 1      audit_logs new_value carries sentinel     -> 0
   database_outbox payload carries sentinel  -> 1      database_outbox payload carries sentinel  -> 0
```

Eight probes, eight non-zero isolated, eight zero in production. The production session was opened
`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` and **self-tested**: a write was attempted
and required to fail with SQLSTATE `25006` before any row was read.

The drill table `p2drill_resume` was added to `dev_env/config/table_config.json` only.
`server/config/table_config.json` is proven byte- and mtime-identical across the whole session
in §6.

---

## 2. D1 — checkpoint resume

**File**: `p2_drill_100k.csv`, 16,000,051 B, 100,000 data rows, 14 columns (`item_id` + `c1..c13`).
16 MB ≥ the 10 MB default threshold, so it took the **heavy lane** — the path the feature exists for.

### 2.1 The kill landed mid-file

Progress was polled at 0.25 s from `GET /admin/file-ingestion/active`. At the first sample in the
30–50 % band the **durable** offset was read straight from the database, then the watcher — and
only the watcher — was killed with `taskkill /F`.

```
00:25:20.046 DROPPED ...\p2drill_resume\raws\p2_drill_100k.csv  (16,000,051 bytes)
00:25:20.053 watcher pid = 47128
00:29:00.426 KILL TRIGGER at active-API progress=30%  processed_rows=30000
00:29:00.426   checkpoint BEFORE kill: {'processed_rows': 30000, 'chunk_index': 30, 'status': 'IN_PROGRESS',
                                        'total_rows': 100000, 'source_kind': 'std', 'note': None}
00:29:00.426   p2drill_resume count(*) BEFORE kill: 30,000
00:29:01.018   taskkill rc=0 SUCCESS: The process with PID 47128 ... has been terminated.
00:29:03.022   checkpoint AFTER kill (+2s): {'processed_rows': 30000, 'chunk_index': 30, 'status': 'IN_PROGRESS', ...}
00:29:03.022   p2drill_resume count(*) AFTER kill (+2s): 30,000
00:29:03.022   file still in raws/: True
```

- `0 < 30,000 < 100,000` — **strictly mid-file**. Not a resume from zero, not a resume of an
  already-complete file.
- `count(*) == processed_rows == 30,000` **exactly**, under a hard `taskkill /F`. That is P2's
  atomicity claim (the offset UPDATE rides the chunk's own transaction) observed under a real
  process kill rather than an injected exception. The unit test proved it with a simulated crash;
  this is the real thing.
- API, chain worker and graph worker were untouched — only pid 47128 died.

### 2.2 The resume

Watcher restarted at 00:29:26. The startup sweep found the file still in `raws/`:

```
00:29:33,010 [p2drill_resume] 📥 New file detected: p2_drill_100k.csv
00:29:33,010 [p2drill_resume] 🐘 Routed to heavy lane queue (size, 16,000,051B): p2_drill_100k.csv
00:29:33,731 🧹 Sweep: attempted 1 pre-existing file(s) in raws/.
00:29:35,743 [p2drill_resume] 🧰 Std parser accepted 'p2_drill_100k.csv' (encoding=utf-8-sig, delimiter=',', data_rows=100000)
00:29:35,747 [p2drill_resume] ⏩ [resume] 이전 실행의 체크포인트 30,000행에서 재개 (총 100,000행, chunk_index=30) — p2_drill_100k.csv
00:29:36,022 [p2drill_resume] ⏩ Resumed ingestion: skipped 30,000 already-committed row(s) of 100,000 — p2_drill_100k.csv
00:29:43,031 [p2drill_resume] 💾 Local batch update success (1000 rows). Changed cells: 14000
00:29:43,034 Ingestion progress for p2_drill_100k.csv on p2drill_resume: 31% (31000/100000)
```

The exact line the drill specifies is present with `N = 30,000`, and the first post-restart chunk
lands at **31 %**, not 1 %.

**What the feature bought, measured**: skipping those 30,000 rows took **275 ms**
(00:29:35.747 → 00:29:36.022, parse-only). Re-ingesting them at the measured 7.3 s/chunk would
have cost **~219 s**. On the 99,999-row / ~7-minute loss that motivated P2, the saving is the
whole file.

### 2.3 Completion — zero loss, zero duplication

```
checkpoint row: {'table_name': 'p2drill_resume', 'filename': 'p2_drill_100k.csv', 'source_kind': 'std',
                 'total_rows': 100000, 'processed_rows': 100000, 'chunk_index': 100, 'status': 'DONE',
                 'note': '[resume] 이전 실행의 체크포인트 30,000행에서 재개 (총 100,000행, chunk_index=30)',
                 'started_at': 2026-07-27 00:25:21.997516+09:00,
                 'updated_at': 2026-07-27 00:38:13.586459+09:00}
count(*)                     = 100,000
count(DISTINCT business_key) = 100,000
ZERO LOSS       (== 100000): True
ZERO DUPLICATION (== count): True
duplicate business keys: 0 []
expected keys P2D-0000001..P2D-0100000 missing from table: 0
```

The last line is the stronger check — a `generate_series` anti-join, which catches
"100,000 rows but the wrong 100,000", something `count(*)` plus a distinct count cannot.

Boundary spot-check across the resume seam (values, not just keys):

```
P2D-0000001 | c1=C1VAL-0000001 | c2=1000001 | c13=C13VAL-0000001
P2D-0030000 | c1=C1VAL-0030000 | c2=1030000 | c13=C13VAL-0030000   <- last row committed before the kill
P2D-0030001 | c1=C1VAL-0030001 | c2=1030001 | c13=C13VAL-0030001   <- first row written after the resume
P2D-0100000 | c1=C1VAL-0100000 | c2=1100000 | c13=C13VAL-0100000
```

No off-by-one at the seam and no column misalignment.

### 2.4 admin File tab detail carries `[resume]`

`GET http://127.0.0.1:8081/admin/file-ingestion/logs` — the endpoint the admin File tab reads:

```json
{
 "id": 9004,
 "filename": "p2_drill_100k.csv",
 "filepath": "...\\dev_env\\ingestion_workspace\\p2drill_resume\\archives\\p2_drill_100k.csv",
 "table_name": "p2drill_resume",
 "status": "SUCCESS",
 "error_message": "[resume] 이전 실행의 체크포인트 30,000행에서 재개 (총 100,000행, chunk_index=30)",
 "retry_count": 0,
 "created_at": "2026-07-27T00:38:13.590877+09:00"
}
```

All four D1 expectations met.

---

## 3. D2 — signature dedup

Both phases re-drop the **byte-identical** archived file (16,000,051 B, same sha256), so the only
variable is the filename token.

### 3.1 D2a — identical re-drop

```
p2drill_resume count(*) before = 100,000
checkpoint before = {'filename': 'p2_drill_100k.csv', 'status': 'DONE', 'processed_rows': 100000,
                     'chunk_index': 100, 'updated_at': 2026-07-27 00:38:13.586459+09:00}
dropped p2_drill_100k.csv at t0
ELAPSED drop -> FileIngestionLog row: 1.22s
log #9005 filename=p2_drill_100k.csv status=SKIPPED
     detail: [dedup-skip] 동일 내용 파일이 이미 적재 완료됨 — 재처리 생략
             (기존 적재: 'p2_drill_100k.csv', 100,000행, signature=sha256:16000051:860c682…).
             강제 재처리하려면 파일명에 '__force__'를 포함하거나 ingestion_settings.json의
             dedup_by_signature를 false로 두십시오.
p2drill_resume count(*) after  = 100,000  (delta +0)
checkpoint after = {... 'updated_at': 2026-07-27 00:38:13.586459+09:00}      <- unchanged
file left in raws/? False   in archives/? True
```

`1.22 s` of which ~1 s is the watcher's fixed copy-settle debounce. **Zero rows written**, and the
checkpoint's `updated_at` did not move — the skip is genuinely a skip, not a fast no-op reload.
The file was moved to `archives/` so the periodic sweep cannot re-pick it forever.

### 3.2 D2b — `__force__` re-drop

```
00:46:11,876 [p2drill_resume] 🔁 Force re-ingestion requested by filename token ('__force__') — dedup skip bypassed
00:46:12,762 [p2drill_resume] ⚠️ [resume-abort] 체크포인트를 사용할 수 없어 처음부터 재처리
             — 사유: 사용자 명시 재처리(force) 요청 (기록된 오프셋 100000행은 폐기)
...
ELAPSED drop -> FileIngestionLog row: 1687.21s
log #9006 filename=p2_drill_100k__force__.csv status=SUCCESS
     detail: [resume-abort] ... 사용자 명시 재처리(force) 요청 (기록된 오프셋 100000행은 폐기)
p2drill_resume count(*) after  = 100,000  (delta +0)
checkpoint after = {'filename': 'p2_drill_100k__force__.csv', 'status': 'DONE',
                    'processed_rows': 100000, 'chunk_index': 100,
                    'updated_at': 2026-07-27 01:14:17.853468+09:00}
```

Same content, same signature row — but the offset was discarded and all 100 chunks were
re-processed from row 1. `count(*)` stayed at exactly 100,000, so a full forced reload is
idempotent (no duplication).

### 3.3 The two paths are not the same path

| | D2a (dedup) | D2b (`__force__`) | ratio |
|---|---|---|---|
| elapsed drop → log row | **1.22 s** | **1,687.21 s** (28 min 7 s) | **1,383×** |
| FileIngestionLog status | `SKIPPED` | `SUCCESS` | different |
| detail prefix | `[dedup-skip]` | `[resume-abort]` | different |
| chunks processed | **0** | **100** | different |
| checkpoint `updated_at` | unchanged | advanced 36 min | different |

Equal timings would have meant the dedup branch was never taken. Three orders of magnitude and
four independent differences say it was.

Incidental measurement worth recording: the forced reload logged
`Changed cells: 0` on every chunk, yet ran at **16,792 ms/chunk** against the table's original
**7,315 ms/chunk** (§5.3) — re-ingesting an identical file into a populated table is **2.3× more
expensive** than the original load, because every row still costs an existence lookup and a cell
comparison. That is the cost dedup avoids, and it is larger than the naive intuition.

---

## 4. D3 — issue #10, total across both target tables

`production_plan` has two chain rules pointing at two different targets:
`production_to_inventory_reservation_batch` → `inventory_master` (from `chain_rules.json`), and
`enrichment_dedup:line_model_owner_attribution` → `line_model_registry` (synthesised from
`enrichment_rules.json` by `load_chain_rules`). One source transaction therefore produces **two**
broadcasts carrying the **same** `chain_<tx>` id — exactly where the old `override_total_count`
SET assignment erased the earlier total.

### 4.1 Keeping the defect axis live

Three conditions had to hold or the drill would have proved nothing:

1. **The cache had to be warm.** `audit_cache.add_logs_batch` — where the bug lived — returns
   immediately when `is_loaded` is false, and a later `GET /audit_logs/recent` would then rebuild
   `total_count` from the database, which is correct by construction. So the drill primes it
   first: `GET /audit_logs/recent -> 200, 100 cached group(s)`.
2. **Two messages had to actually arrive** under one chain tx. With one message, SET and
   accumulate are indistinguishable.
3. **The two per-table counts had to differ.** The first run produced 4 and 4; that result (8)
   was still discriminating, but "the sum" and "twice the last" are not separable when the
   operands are equal, so it was re-run with a deliberately asymmetric payload. Both runs are
   reported; the asymmetric one is the evidence.

### 4.2 Result

Five `production_plan` rows in one transaction `p2d3-multi-69B50D` — four sharing one
`(prod_line, model_name)` pair with four different `target_qty`, one on a second pair.

```
DB audit_logs for chain_p2d3-multi-69B50D, grouped by table:
    inventory_master         5
    line_model_registry      2
    SUM                      7

history total_count reported by GET /audit_logs/recent : 7
  == SUM across both tables ?  True
  distinct target tables in this tx: 2
  the two per-table counts are equal? False

  chain worker sent 2 batch execution(s) under the SAME chain tx:
    [1] 'inventory_master' under tx 'chain_p2d3-multi-69B50D' (size: 5)
    [2] 'line_model_registry' under tx 'chain_p2d3-multi-69B50D' (size: 2)
  LAST message targeted 'line_model_registry' carrying 2 log(s)
  OLD (SET) semantics -> total_count would read 2; observed 7; true sum 7
```

5, 2 and 7 are three distinct numbers. The last broadcast carried 2, so the pre-fix code would
have displayed **2**. The observed value is **7**.

(First run, symmetric: `inventory_master 4` + `line_model_registry 4`, total `8`, last message
`4` — same conclusion, weaker separation.)

### 4.3 Single-target control

An `inventory_master` user edit fires only the `inv` rule, i.e. one target table:

```
DB audit_logs for chain_p2d3-single-69B50D, grouped by table:
    inventory_master         1
history total_count reported: 1  == sum 1 ? True
distinct target tables: 1 (control: must be 1)
```

Accumulate does not inflate a single-message transaction. Together with §4.2 this separates
"the sum is right" from "the number happened to match".

---

## 5. Regression watch

### 5.1 Event loop — `:8081` polled at 0.25 s throughout both drills

| window | samples | errors | p50 | p95 | p99 | max | >100 ms | >250 ms | longest consecutive run >250 ms |
|---|---|---|---|---|---|---|---|---|---|
| D1 (1,202 s, incl. kill + resume + D3) | 4,649 | 0 | **5.1 ms** | 17.4 ms | 20.6 ms | 204.3 ms | 7 (0.15 %) | **0** | **0** |
| D2 (1,743 s, incl. the 28-min force reload) | 6,722 | 0 | **5.2 ms** | 17.9 ms | 20.6 ms | **29.8 ms** | **0** | **0** | **0** |

All seven >100 ms samples in the D1 window fall in 00:33:06–00:33:10 — the D3 script's
`GET /audit_logs/recent` cache priming, which loads 100 transaction groups from the database.
That is the instrument's own traffic, not a stall. No freeze anywhere: zero samples above 250 ms
across 11,371 measurements, and the D2 window's *maximum* (29.8 ms) is below the D1 p99.

For reference, P1's equivalent measurement on production was p50 3.5 / p95 26.0 / max 845.5 ms
with 11 samples >100 ms. The isolated numbers are tighter — as expected with no live collectors —
so this is a "no regression" reading, not a claim of improvement.

### 5.2 Chain worker `[Latency]`

```
[Latency] tx=p2d3-multi-F5F8AF   wake=15ms mapper=938ms commit=0ms  notify=31ms total=984ms ok=True
[Latency] tx=p2d3-single-F5F8AF  wake=0ms  mapper=31ms  commit=16ms notify=0ms  total=47ms  ok=True
[Latency] tx=p2d3-multi-69B50D   wake=16ms mapper=62ms  commit=0ms  notify=16ms total=94ms  ok=True
[Latency] tx=p2d3-single-69B50D  wake=0ms  mapper=31ms  commit=0ms  notify=0ms  total=31ms  ok=True
```

`notify=` 0–31 ms, every tx `ok=True`, no retries. P1's live window measured notify 15–32 ms.
Unchanged. The 938 ms `mapper=` on the first multi-target tx is the enrichment mapper's cold
first call (the same tx type ran at 62 ms once warm).

### 5.3 Chunk processing time vs the pre-checkpoint baseline

**The cross-run comparison the task asks for cannot be made honestly, and saying so matters more
than producing a number.** The only pre-checkpoint measurement on record is P1's live drill:
415.5 s for 100,000 rows, i.e. ~4.16 s per 1,000-row chunk — but that was a **100-column** table,
on the **13 GB production** database, on a machine running only the production stack. D1 is a
14-column table on a 422 MB snapshot, on a machine simultaneously running the production
5-process stack, the isolated 4-process stack, and a concurrent agent's 457-test pytest run.
Presenting 7.3 s against 4.2 s as a checkpoint regression would be false.

So the question — *does the extra indexed UPDATE per chunk cost anything?* — was answered
directly, two ways.

**(a) The statement itself.** `record_chunk_progress` issues exactly one UPDATE. Measured against
the real `assy_qa` table (686 rows at the time):

```
Update on file_ingestion_checkpoints  (actual time=0.067..0.068 rows=0.00 loops=1)
  Buffers: shared hit=6
  ->  Index Scan using idx_fic_signature on file_ingestion_checkpoints  (actual time=0.036..0.038 rows=1.00)
        Index Cond: ((file_signature)::text = 'sha256:16000051:860c682…'::text)
        Filter: ((table_name)::text = 'p2drill_resume'::text)

300 timed UPDATE+commit executions: min=0.469ms  p50=0.709ms  p95=0.918ms  max=2.245ms
```

Index scan, 6 buffer hits, no sequential scan — so the cost does not grow with the checkpoint
ledger. **0.709 ms against a 7,315 ms chunk is 0.0097 %**, and inside a chunk the UPDATE rides the
chunk's existing transaction, so the real figure is lower still.

**(b) A true A/B of the exact call sequence.** `_send_to_upsert`'s per-chunk sequence was
reproduced in a harness against the isolated DB and run both ways, interleaved A/B/A/B so machine
drift cancels — 8 chunks of 1,000 rows per arm:

```
WITH       n=8 min=6219 p50=6616 mean=6595 max=6742 ms
WITHOUT    n=8 min=6584 p50=6647 mean=6649 max=6726 ms

median delta = -30.2 ms per 1,000-row chunk (-0.45% of the no-checkpoint chunk)
```

The checkpointed arm measured *faster*, which is physically impossible as a real cost — the effect
is below this measurement's noise floor (~±150 ms, from the arms' fully overlapping ranges).
Combined with (a): **the per-chunk checkpoint UPDATE is ~0.01 % of a chunk and is not detectable
in end-to-end timing.** The P2 report's prediction holds.

Per-chunk distributions actually observed (from the watcher's own log timestamps):

| run | chunks | min | p50 | p95 | max |
|---|---|---|---|---|---|
| D1 initial + resumed (empty → 100 k rows) | 100 | 6,877 ms | **7,315 ms** | 8,063 ms | 42,647 ms\* |
| D2b forced reload (into 100 k existing rows) | 100 | 15,909 ms | **16,792 ms** | 18,298 ms | 19,021 ms |

\* the 42,647 ms outlier is the kill-to-restart gap, not a chunk.

---

## 6. Production untouched — with its control

Manifest captured before the first drill file (00:13:48) and after cleanup (01:23:16): per-table
row counts plus sha256 + mtime + size for every file under `server/config/**`,
`server/ingestion_workspace/**` and `server/mappers/**` (9,527 → 9,658 files).

### 6.1 The files this drill would have damaged

```
config/table_config.json                       identical=True  sha=226d7956824b1bb0  mtime=18:31:00.877
config/maps.json                               identical=True  sha=5fcc8c8af26624fd  mtime=10:34:54.678
config/chain_rules.json                        identical=True  sha=cfcf357550739a49  mtime=06:38:54.980
config/enrichment_rules.json                   identical=True  sha=382a7d84f70a579e  mtime=21:45:59.101
workspace/inventory_master/config/config.json  identical=True  sha=a4fbcee2619989e6  mtime=21:35:42.826
workspace/production_plan/config/config.json   identical=True  sha=387f1a737ca5bfd3  mtime=11:42:26.421
mappers/production_mapper.py                   identical=True  sha=4717436403481d0f  mtime=06:56:56.735
mappers/inv_man.py                             identical=True  sha=0ae21147d69a8352  mtime=06:48:16.515
mappers/base.py                                identical=True  sha=b88f7425bdaca42e  mtime=06:19:17.460
```

`config/table_config.json` is the decisive one — I added a table to the isolated copy of it. The
production original is unchanged in content **and** never opened for write; its mtime predates the
session by six hours. The two mappers the D3 chain rules execute are likewise untouched.

### 6.2 Every stable file that *did* change, attributed

Nine stable files moved. All nine are attributable to the live system or to the concurrent agent
whose commit `4ba13ae` landed at 00:40:40 mid-session.

| file | mtime → | whose |
|---|---|---|
| `config/scheduler_status.json` | 00:13:04 → 01:23:05 | **the live scheduler's cron** — this is the control |
| `config/{bonding_plan,map_overlay,transfer_plan}_config.json` + three `*.bak-20260727_004642` | all at **00:46:42** | the alignment-consolidation migration (timestamped-backup signature); at 00:46:42 my only activity was the force reload against `dev_env/` |
| `config/table_config.json.sample` | 21:34 → 00:33:12 | in commit `4ba13ae` (`server/config/table_config.json.sample \| 1 +`) |
| `mappers/__init__.py` | TOUCHED, **same bytes**, epoch `1780839067.0` → `1780839067.4746883` | the isolation agent's `mappers/` guard test. The mtime is a **June 7** timestamp whose *fractional part* changed — the signature of a file rewritten and then restored with its original mtime, which is exactly the snapshot-and-repair fixture their commit message describes. Reads and imports do not do this; `__pycache__` is excluded from the manifest |

I never called `POST /admin/scripts/code`, never ran a migration, and my tooling only reads
`server/config/`.

### 6.3 The control makes "unchanged" mean something

Two independent proofs that the instrument is awake, not asleep:

- `scheduler_status.json` **content-changed** on the live scheduler's own cadence inside the same
  window. A flat reading elsewhere therefore means "never opened", not "instrument dead".
- `mappers/__init__.py` was flagged from a **sub-second mtime bump with identical sha256**. The
  instrument catches a rewrite that produces the same bytes — the exact case a content-only check
  would miss.

### 6.4 The database side

Twelve production tables moved (`inventory_master` +210, `bonding_log` +193, `graph_nodes` +338,
`database_outbox` actually *down* 2,937,134 → 2,923,456, `file_ingestion_checkpoints` 751 → 879).
That is the live system: collectors on a 2-minute cron, and the production watcher writing its own
P2 checkpoints for real files. **Production row counts are not usable as evidence of agent
activity** — which is why §1.1's sentinel absence, not counts, carries the proof. Production's
`file_ingestion_checkpoints` contains zero rows matching any drill filename, and production has no
`p2drill_resume` table at all.

Every production query this session ran in a session self-tested read-only (SQLSTATE `25006`).

### 6.5 The live server was not restarted

The production process table is unchanged — **the same six PIDs** observed at session start are
still running at session end, so nothing was stopped, restarted, or replaced:

```
33192  run_decoupled_app.py --server-only     45956  run_graph_sync.py
24480  uvicorn main:app --port 8080           30300  run_chain_worker.py
32352  run_watcher.py                         47380  run_auto_update.py

GET http://127.0.0.1:8080/tables -> 200        (production, healthy)
GET http://127.0.0.1:8081/tables -> connection refused   (isolated, taken down)
```

The only process killed all session was pid **47128** — the isolated watcher I started myself
(§2.1), later replaced by pid 41764 and stopped at the end.

### 6.6 Cleanup

Drill artefacts removed; the snapshot database is left in place, as instructed.

```
removed dev_env/ingestion_workspace/p2drill_resume (4 files)
removed 'p2drill_resume' from dev_env/config/table_config.json (24 tables remain)
dropped assy_qa.p2drill_resume; deleted 3,024,000 cell_sources / 116,001 audit_logs /
  116,024 outbox / 3 file_ingestion_logs / 2 checkpoints rows; D3 rows removed from
  production_plan, inventory_master, line_model_registry

residual scan of assy_qa (all must be 0):
  p2drill table exists 0 | cell_sources 0 | audit_logs 0 | p2d3/abbench tx 0 |
  checkpoints 0 | file_ingestion_logs 0 | outbox 0 |
  production_plan P2D3% 0 | inventory_master INV_P2M% 0 | line_model_registry P2L_% 0
  file_ingestion_checkpoints total 684 (= the snapshot's original count)
  database_outbox total 3 (= the DEVENV_ISO_PROBE rows predating this session)
```

Kept on purpose, both inside `dev_env/`: `dev_env/logs/iso_watcher.log` (91 KB) and
`dev_env/logs/iso_watcher_stdout.log` (94 KB) — the raw drill evidence quoted above.

The isolated stack was stopped with `devenv down`, returning the machine to the state I found it
in (nothing isolated was running at 00:13). `devenv up` restores it in seconds.

---

## 7. Findings

### F1 — [medium] The isolated processes write into the **production** log tree

`utils/logger.get_process_logger` resolves its file handler to `server/<name>.log` from its own
`__file__`. It is not covered by `ASSY_DATA_ROOT`, so **every process `devenv up` starts appends to
the user's live log files**.

Proof — transaction ids that exist only in `assy_qa` appear in the production log file:

```
$ grep -c "p2d3-multi" server/chain_worker.log
6
$ grep "p2d3-multi" server/chain_worker.log | tail -1
[Chain] [2026-07-27 00:35:04,835] INFO - [Latency] tx=p2d3-multi-69B50D wake=16ms mapper=62ms commit=0ms notify=16ms total=94ms ok=True
```

`server/*.log` is gitignored, so no tracked asset is at risk and the manifest does not cover it.
But it contaminates the very files a reviewer reads to reconstruct a production incident — my
isolated chain worker's lines are now interleaved with the live one's, in the same file, at the
same second. I worked around it for the watcher by patching `get_process_logger` in my launcher
(so `server/watcher.log` contains **zero** `p2drill` lines), but the three processes `devenv up`
starts had no such protection.

**Fix**: route the log filename through `paths.DATA_ROOT` — `os.path.join(paths.DATA_ROOT,
log_filename)` — which is a one-line change and preserves production behaviour exactly when
`ASSY_DATA_ROOT` is unset.

### F2 — [medium] `devenv` has no watcher, so every ingestion drill re-implements the safety rail

Not starting a watcher by default is right — the churn is the problem. But "no flag at all" means
the next agent who needs one writes their own launcher, and the single highest-risk action in this
task (a watcher pointed at production would ingest drill files into live data) is left to each
agent's care. My launcher's assertion block is ~40 lines and should not be re-derived.

**Fix**: add `devenv.py watcher-up` / `watcher-down` that starts `run_watcher.py` under
`isolated_env()` **and** performs the §1 assertions (resolved `paths.*`, `engine.url`, a live
`SELECT current_database()`, `API_BASE_URL`) before registering any handler, refusing to start
otherwise. Keep it a separate verb so `up` stays churn-free.

### F3 — [low] `resume_from_checkpoint: false` does not disable checkpointing

The name reads like a master switch for the feature. It is not: `_plan_checkpoint` only converts
it into `force_restart=True`, so `plan_ingestion` still returns an **active** plan and
`record_chunk_progress` still issues its UPDATE on every chunk. The setting disables *resuming*,
not *checkpointing*.

Consequence for verification: the checkpoint's overhead A/B cannot be produced through
configuration, which is why §5.3(b) needed a harness. Consequence for operations: an operator who
sets this to disable the feature (e.g. suspecting the checkpoint of causing write load) will see
no change in write load.

**Fix**: either document the actual scope in `ingestion_settings.json.sample` — the description
there should say "disables resuming; progress is still recorded" — or add a genuine
`checkpoint_enabled` switch that returns `CheckpointPlan.disabled()`.

### F4 — [low] A table removed from `table_config.json` is resurrected as an empty physical table

Observed during cleanup, reproduced deliberately. After removing `p2drill_resume` from
`dev_env/config/table_config.json` and running `DROP TABLE p2drill_resume`, the table came back —
empty — while the isolated api/chain/graph processes were still running. Dropping it again with
**nothing** isolated running left it dropped (verified 60 s later).

Mechanism from the code: `init_dynamic_models` only adds and hot-swaps; it never removes entries
from `DYNAMIC_TABLES`. `refresh_dynamic_models` then calls `create_missing_dynamic_tables`, which
iterates `DYNAMIC_TABLES.items()` — still containing the removed table — finds
`inspector.has_table(...) == False`, and CREATEs it. I could not pin the emitting process because
the `[Schema Sync] Created missing physical table` line was not present in any of the three
isolated logs, so treat the *mechanism* as inferred from source and the *behaviour* as measured.

This is pre-existing and unrelated to P2. Impact is small (an empty table reappears; no data
moves), but it means "remove a table from config" does not retire it, and any long-running worker
can undo a manual drop.

### F5 — informational: the concurrent work looks complete, not half-written

Commit `4ba13ae` landed at 00:40:40, mid-session, and includes `server/tests/test_dev_env_isolation.py`
(333 lines) and the `mappers/` write guard at `main.py:_resolve_admin_script_path`. The guard reads
as finished: it resolves before any filesystem access, refuses non-relocated prefixes for writes
while `paths.IS_ISOLATED`, keeps reads allowed, and looks the flag up at call time so it stays
patchable. I deliberately **did not exercise it** — probing it means aiming a write at production,
which the constraints forbid.

That commit also touched `server/database/crud.py` and `server/parsers/directory_watcher.py`, but
only path plumbing (`paths.config_path(...)` replacing `__file__`-relative joins); no P2 logic. All
P2-relevant sources were last written before my processes started
(`directory_watcher.py`/`crud.py` 23:55:33, `ingestion_checkpoint.py`/`audit_cache.py` 17:04:43,
`main.py` 00:09:43 vs API start 00:16:37 and watcher start 00:18:47), so every drill ran against
exactly the code now committed.

---

## 8. Proposed lessons (`agent_workspace/memory/*.md` — not applied, for review)

**Shared section:**

> - **함정**: 격리 환경을 세워도 **프로세스 로그 파일은 격리되지 않는다** — `utils/logger.get_process_logger`가
>   `server/<name>.log`를 자기 `__file__` 기준으로 잡아 `ASSY_DATA_ROOT`를 타지 않는다. `devenv up`이 띄운
>   격리 chain/graph/api 워커의 로그가 운영 `server/*.log`에 그대로 섞인다(2026-07-27 실측: `assy_qa`에만
>   존재하는 tx `chain_p2d3-multi-*` 6줄이 운영 `server/chain_worker.log`에 존재).
>   **올바른 방법**: 격리 프로세스를 손으로 띄울 땐 `get_process_logger`를 dev_env로 리다이렉트하고,
>   도구 쪽은 로그 경로도 `paths.DATA_ROOT`를 따르게 고친다. "격리했다"의 점검 목록에 **로그 파일**을 넣을 것.
> - **함정**: 운영과 격리를 같은 머신에서 동시에 돌리면 **처리량 절대치는 다른 실행과 비교할 수 없다**
>   (본 드릴 중 운영 5프로세스 + 격리 4프로세스 + 타 에이전트 457건 pytest 동시 구동). P1(운영·100컬럼)
>   4.16s/청크 vs D1(격리·14컬럼) 7.32s/청크는 회귀가 아니라 **비교 불가**다.
>   **올바른 방법**: 성능 회귀 판정은 **같은 실행 안의 인터리브 A/B**로만 한다. 절대치 비교는 컬럼 수·DB 크기·
>   동시 부하를 함께 적지 못하면 쓰지 않는다.

**server-pm section:**

> - **함정**: 킬/재기동 드릴에서 "재개했다"는 로그만 보고 통과시키면 **0에서 재개했거나 이미 완료된 파일을
>   재개한 경우와 구분되지 않는다**.
>   **올바른 방법**: 킬 시점의 **durable 오프셋**을 DB에서 읽어 `0 < offset < total`을 수치로 남기고
>   `count(*) == offset`(원자성)까지 같이 확인한다. 완료 후에는 `count(*)`·distinct에 더해 **기대 키 전량
>   anti-join**(`generate_series` LEFT JOIN)으로 "100,000행이지만 엉뚱한 100,000행"을 배제하고, 재개 이음매
>   양쪽 행의 **값**까지 대조한다(키만 맞고 컬럼이 어긋난 경우 차단).
> - **함정**: 캐시가 개입하는 결함(#10 `audit_cache.add_logs_batch`)은 **캐시가 cold면 결함 경로를 아예 타지
>   않는다** — 나중에 `/audit_logs/recent`가 DB에서 재구성하면 총계가 구조적으로 맞아 "통과"가 나온다.
>   **올바른 방법**: 트리거 전에 `GET /audit_logs/recent`로 캐시를 예열하고, ① 같은 tx로 **메시지가 2건 이상
>   실제 도착**했는지(체인 워커 로그 `Executing chained batch updates to ... under tx 'chain_...'` 2줄) ②
>   **두 기여분이 서로 다른 값**인지를 단언한다. 두 값이 같으면 합계와 마지막 값이 구분되지 않는다.
> - **함정**: 설정 스위치 이름이 기능 전체를 끄는 것처럼 읽히지만 실제로는 일부만 끈다 —
>   `resume_from_checkpoint: false`는 **재개만** 막고 청크당 체크포인트 UPDATE는 그대로 발행한다
>   (`_plan_checkpoint`가 `force_restart=True`로 바꿀 뿐 `plan.active`는 True).
>   **올바른 방법**: 오버헤드 A/B를 설정으로 만들 수 없으면 **해당 문장만 떼어낸 하네스**로 A/B를 재현하고,
>   스위치의 실제 차단 범위를 `.sample`에 명시한다.
> - **함정**: `init_dynamic_models`는 추가·핫스왑만 하고 `DYNAMIC_TABLES`에서 **제거하지 않는다**. 따라서
>   table_config에서 테이블을 지우고 물리 DROP을 해도, 살아 있는 워커의 다음 `refresh_dynamic_models` →
>   `create_missing_dynamic_tables`가 **빈 테이블로 되살린다**.
>   **올바른 방법**: 테이블 회수는 관련 프로세스를 내린 뒤 수행하고, 회수 후 존재 여부를 재확인한다.

---

## 9. Handover

**Changed** — nothing under `server/`, `client2/`, or `docs/`. The only repository-tracked file
added is this report. `dev_env/config/table_config.json` was modified and restored (the drill table
entry was added and removed; it is a gitignored copy).

**Verified** — D1/D2/D3 all PASS with the defect axis live in each; event loop and chain notify
unchanged; checkpoint overhead below the noise floor; production byte- and mtime-identical with
two independent sensitivity controls.

**Open / next**

1. F1 (isolated processes writing into `server/*.log`) — one-line fix in `utils/logger.py`, but it
   touches every process, so it wants a deliberate decision rather than a drive-by edit.
2. F2 — `devenv.py watcher-up` with the assertion block, so the next ingestion drill does not
   hand-roll its own safety rail.
3. F3 — decide: document `resume_from_checkpoint`'s real scope, or add a true off switch.
4. F4 — pre-existing, unrelated to P2; worth a board entry, not urgent.
5. P2's remaining open items from `Server_large_file_p2_report.md` §9 are unaffected by these
   drills: the `SKIPPED` badge/Retry-button treatment in `client2/src/admin.js:843-844` is still
   outstanding, and this drill produced a real `SKIPPED` row (§3.1), so it is now reproducible in
   the isolated environment.
