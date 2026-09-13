# P3 — Large-file ingestion, phase 1: the profile

**Lane:** P3 (queue item 2) · **Tier:** T3 · **Date:** 2026-08-06
**Production code changed: none.** Every number below comes from runtime
monkeypatching inside a throwaway harness under the session scratchpad
(`P3_*.py`), never from an edit under `server/`.

---

## 0. Where the numbers came from, and what they are not

| | |
|---|---|
| Box | **this workstation** — a simulation, NOT production. Every timing below is a shape, not a production SLA. |
| Database | `assy_qa` on `localhost:5432` (the isolated snapshot), reached via `DATABASE_URL`; `ASSY_DATA_ROOT=dev_env`. Isolation asserted in-process before each run (`P3_env.assert_isolated`). |
| Server processes | **none running.** `api`/`chain`/`graph` were down for the whole sweep. That is deliberate: it removes churn, and it also means **nothing was draining `database_outbox`** — see §6. |
| Harness | `IngestionHandler(ws, None, archives, table, heavy_lane=None).process_with_retry(path, delay=0)` — fully inline, synchronous, no watchdog, no 1 s debounce in the numbers. |
| Probe table | `p3prof_map`, a byte-for-byte clone of `eds_fail_map`'s config (7 display columns, `composite_key_source=[lot,slot,x,y]`, `map_key_columns=[lot,slot]`) — the shape of the two tables that actually grow. |
| Input | synthetic CSV, `chip_key` left empty so the composite key is assembled by `crud` — the real map-ingestion shape. Std parser path (no custom script). |
| Reset | every sweep point deletes the probe table's rows + its `cell_sources`/`cell_overwrites`/`audit_logs`/`database_outbox`/checkpoint rows first, so each point is a **first ingest** (insert path), not an update. |

**Caps and samples, stated up front:** the sweep tops out at **100,000 rows
(3.0 MB)**, not 10,000,000. 10M was not run — at the measured rate it is a
~20 hour single-threaded run and would have added ~50 GB to `assy_qa`. The
10M figures below are **extrapolations from a four-point curve**, and the
curve is not flat (§2), so they are lower bounds. Parse-only micro-benchmarks
were run up to 1,000,000 rows because they cost no database.

---

## 1. The headline

Ingesting a **100,000-row / 3 MB** map file through the standard path takes
**729 seconds** on this box — **7.3 ms per row** — and issues **301,222 SQL
statements**, i.e. **3.01 statements per data row**, at every scale measured.

Of those 729 seconds, **722 (99.1%) are inside `crud.apply_batch_updates`.**
Parsing the file is **1.6 seconds (0.22%)**. Hashing it is **0.015 seconds
(0.002%)**.

Naive extrapolation to ten million rows: **~20 hours, ~30 million SQL
statements, ~50 GB of new database**, for one file, on one thread.

---

## 2. The curve

Fresh-insert sweep, 4 map keys per file, probe table reset before each point.

| rows | file | wall | **ms / row** | SQL stmts | stmts/row | SQL client time | RSS peak |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 0.028 MB | 8.41 s | 8.41 | 3,034 | 3.03 | 2.73 s | 147 MB |
| 5,000 | 0.145 MB | 29.35 s | 5.87 | 15,082 | 3.02 | 10.36 s | 151 MB |
| 20,000 | 0.586 MB | 131.72 s | 6.59 | 60,262 | 3.01 | 45.78 s | 152 MB |
| 100,000 | 3.014 MB | 729.19 s | **7.29** | 301,222 | 3.01 | 254.09 s | 155 MB |

Two things this curve says that a single-point profile could not:

1. **It is not flat.** After fixed startup amortises away (the 1k point is
   distorted by a one-time ~1.2 s `pandas` import, §5.5), per-row cost
   **rises 24% from 5k to 100k** (5.87 → 7.29 ms). The work per row is
   constant; what grows is the table and the indexes the three per-row
   statements probe. Extrapolating the same slope over the remaining two
   decades to 10M gives **9–11 ms/row, i.e. 25–30 hours**, not 20.
2. **Memory does not grow at all.** Peak RSS moves 147 → 155 MB across a
   100× input range. The std-parser path is genuinely streaming and peak
   memory is `O(chunk)`, exactly as `std_parser.py`'s docstring claims.

---

## 3. Where the time actually goes (100,000-row point)

Decomposition is close to non-overlapping; the children of
`apply_batch_updates` sum to 701.5 s of its 722.3 s.

| stage | seconds | % of wall | of which SQL (client-observed) |
|---|---:|---:|---:|
| `apply_row_update_internal` (per-row loop, ×100,004) | **361.9** | **49.6%** | 189.2 s (two SELECTs/row) |
| `bulk_upsert_cell_sources` (×101 chunks, 700k rows) | **223.2** | **30.6%** | 60.2 s |
| ORM `flush` (100k data-row INSERTs + outbox staging) | **106.9** | **14.7%** | 49.3 s + 8.2 s |
| `bulk_insert_audit_logs` (100k rows) | 9.5 | 1.3% | 6.6 s |
| `stage_event` outbox staging, Python side (×100,004) | 8.7 | 1.2% | — |
| `_resolve_rows` setup (one-time `pandas` import) | 2.0 | 0.3% | — |
| std parser: count pass + streaming yield | **1.6** | **0.22%** | — |
| `commit` | 0.5 | 0.06% | — |
| whole-file **sha256** | **0.015** | **0.002%** | — |
| checkpoint plan | 0.027 | 0.004% | — |
| archive (move) | 0.005 | 0.001% | — |

Total SQL client time is 254 s of 729 s — **65% of the wall clock is Python
and SQLAlchemy, not the database.**

### 3.1 The three per-row statements

Every data row of a fresh map file costs exactly three round trips:

| statement | site | stmts @100k | client time | server time (EXPLAIN ANALYZE) |
|---|---|---:|---:|---|
| `SELECT … WHERE business_key_val = ?` | `crud.get_row_by_business_key` (`crud.py:1051`) via `_get_or_create_row:1510` | 100,000 | 68.1 s | **0.095 ms** (Index Scan `ix_p3prof_map_business_key_val`, 4 buffers) |
| `SELECT … WHERE business_key_val = ? AND row_id != ?` | **composite-key collision probe, `crud.py:1990-1993`** | 100,000 | 60.7 s | **0.032 ms** (same index, 4 buffers) |
| `INSERT INTO p3prof_map … RETURNING created_at, updated_at` | ORM flush, one statement per row | 100,000 | 49.3 s | — |

🔴 **Both SELECTs are already index scans that touch four buffers and finish
in tens of microseconds.** 68 seconds divided by 100,000 statements is 0.68 ms
*per statement*, against 0.095 ms of execution and 0.255 ms of planning. The
cost is **statement count** — round trip, re-planning, SQLAlchemy Core
construction — not scanning. Any repair framed as "add an index" or "improve
the plan" addresses nothing here.

Full plans are in §9.

### 3.2 What `bulk_upsert_cell_sources` actually spends

223.2 s for 700,000 mappings in 101 calls, of which only **60.2 s is SQL**
(701 `INSERT … ON CONFLICT DO UPDATE` statements — the function chunks by
`BULK_CHUNK_SIZE`). The remaining **163 s is Python**: the dedup dict, the
`sorted()` over the key tuples, and above all SQLAlchemy compiling a
multi-row `VALUES` clause per chunk. This is the single largest block of
non-database time in the run.

---

## 4. Storage: the constraint nobody listed

Measured with `pg_column_size` on the 100,000 probe rows actually written
(`assy_qa`, isolated):

| what one ingested data row creates | rows | avg heap bytes each |
|---|---:|---:|
| the data row itself | 1 | 174 B |
| `cell_sources` (one per column) | **7** | 148.7 B → 1,041 B |
| `audit_logs` | 1 | 351 B |
| `database_outbox` | 1 | **999 B** (payload alone 810 B) |
| **heap total** | **10 rows** | **≈ 2.57 KB** |

Indexes are not a rounding error: for the probe table alone, heap 18 MB vs
**indexes 37 MB** — indexes are 2× the heap, across nine of them
(`ix_*_business_key_val`, `idx_*_bk`, `ix_*_row_id`, `ix_*_created_at`,
`ix_*_updated_at`, `idx_*_updated`, `ix_*_is_graph_synced`,
`ix_*_needs_graph_rollback`, pkey). `cell_sources` carries six indexes,
`audit_logs` five, `database_outbox` seven.

**One ten-million-row file therefore writes ~100 million rows and, with
index overhead at the observed ratio, on the order of 50 GB.** The whole
production database is 14 GB today. This is a harder wall than the 20 hours.

---

## 5. Verdict on the board's seven guesses

The board's ordering is **wrong at the top and wrong at the bottom**. Measured
ranking, at 100k rows, fresh insert, std-parser path:

| rank | cost centre | share | board's rank |
|---|---|---:|---|
| 1 | per-row loop in `apply_row_update_internal` (3 round trips + Python) | 49.6% | #2, and half-located |
| 2 | `cell_sources` bulk upsert, mostly SQLAlchemy compile | 30.6% | not listed |
| 3 | ORM flush: one INSERT per data row | 14.7% | not listed |
| 4 | audit + outbox writes | 2.5% | #3 |
| 5 | parse | 0.22% | **#1** |
| 6 | sha256 | 0.002% | #5 |
| 7 | script discovery / `.lower()` loop | see §5.4/5.6 | #4, #6 |

### 5.1 Guess #1 — pandas whole-file load — **OVERTURNED as a TIME cost; REAL, and the only OOM risk, as a MEMORY cost**

`BasePipelineParser.parse` vs `std_parser.parse_std_file` on the same file,
no database, peak RSS sampled at 10 ms (this box):

| rows | file | std time | **std peak RSS** | pandas time | **pandas peak RSS** | sha256 |
|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.32 MB | 0.141 s | 0.2 MB | 0.133 s | 5.6 MB | 0.0012 s |
| 100,000 | 3.36 MB | 1.175 s | 0.0 MB | 1.284 s | 65.0 MB | 0.0059 s |
| 500,000 | 17.52 MB | 5.648 s | 0.0 MB | 6.362 s | 343.6 MB | 0.0293 s |
| 1,000,000 | 35.47 MB | 12.251 s | 0.0 MB | 13.504 s | **682.4 MB** | 0.0418 s |

Two corrections to the board's reading:

* **Pandas is not slower.** 13.5 s vs 12.3 s at one million rows — a 10%
  difference. Against a ~20-hour ingest, parsing ten million rows costs about
  **two minutes either way (0.15%)**. The `to_dict` + per-cell `pd.isna` loop
  is real and it does not matter for throughput.
* **Pandas costs 19× the file size in RAM, and the streaming path costs
  nothing.** 682 MB peak for a 35 MB file. Linear: a ten-million-row CSV of
  this shape is ~355 MB and would peak at **≈ 6.8 GB**. That is the one place
  in the whole path where something plausibly dies before ten million rows —
  and it only happens on a workspace that has a matching custom script,
  because a script bypasses the streaming std parser entirely
  (`_resolve_rows:1686` tries pipeline discovery first).

So guess #1 belongs on the list, but under "does anything OOM?", not under
"where does the time go?".

### 5.1b Does anything OOM before ten million rows?

**On the shipped std path, no.** Peak RSS was 147 → 155 MB across a 100×
input range (§2) and the parse itself allocates nothing measurable. The chunk
loop holds 1,000 rows plus the batch's accumulators; the only per-file
accumulators are bounded (`MAX_NOTIFY_CREATED_LOGS = 500`, dropped-column
counts ≤ `MAX_DROPPED_COLUMNS_REPORTED`).

**On a custom-script path, yes — ~6.8 GB projected at ten million rows.** The
reason the rest of the path is safe is that the big accumulators are
allocated inside `apply_batch_updates`, i.e. **per 1,000-row chunk, not per
file** (`cell_sources_to_upsert`, `logs_to_cache`, `row_cache`,
`sources_cache`), so they stay `O(chunk × cols)`. The genuinely file-scoped
accumulators are `all_created_logs` (hard-capped at 500) and the
`meta_collector` bboxes (O(distinct map keys)) — both bounded.

### 5.2 Guess #2 — `_get_or_create_row` misses the prefetch — **REAL, top of the list, but mislocated**

Confirmed: a fresh file's rows are absent from the prefetch by construction,
so `_get_or_create_row` falls to `get_row_by_business_key` for **every** row.
`crud.py:2545-2555` already says so and the measurement agrees.

But the board's own comment says "1-2 SELECTs per row" and treats the second
as uncertainty. It is not uncertain and it is **not in `_get_or_create_row`**:
the second SELECT is the **composite-key uniqueness/collision probe at
`crud.py:1990-1993`**, which fires for every row whose composite key is
assembled — i.e. every row of every map file. Closing only
`_get_or_create_row` removes one of the two, and one of three round trips.
This is the same failure mode the memory file already records: *"「캐시에 없음」은
「배제됨」이 아니다 — 도달 경로를 전부 세고 전부 막는다."* Here there are two
identity gates, not one.

### 5.3 Guess #3 — `before_flush` outbox listener — **REAL, but misranked and mis-framed**

At ingestion time it is cheap: 8.7 s of Python staging + 8.2 s of INSERT at
100k rows = **2.3% of wall**. It is not a time cost centre.

Its real cost is elsewhere, and it is severe — see §6.

### 5.4 Guess #4 — per-cell `.lower()`, O(cols × declared_cols) — **REAL, but only for wide tables**

The inner normaliser at `directory_watcher.py:1842-1858` was lifted verbatim
into the harness and run against 20,000 rows at four column counts (no
database, this box):

| declared columns | µs / row | **seconds per 10 M rows** |
|---:|---:|---:|
| 7 (`eds_fail_map`, `core_defect_map`) | 7.8 | **78 s** |
| 14 (`wafer_process`) | 22.0 | 220 s |
| 50 | 213.0 | 2,130 s |
| 100 (`large_table_100`) | 866.2 | **8,662 s = 2.4 hours** |

Quadratic, as the code shape predicts. At the seven columns the two real
growth tables declare, it is **78 seconds inside a twenty-hour run (0.1%) —
noise**. At a hundred columns it is **2.4 hours of nothing but `str.lower()`**,
and `large_table_100` is a declared table in the shipped config. So the guess
is correct in kind and its urgency is entirely a function of which table hits
ten million rows first. For the map tables, which are the ones actually
growing, it is not worth a round.

(The fix is trivial and unconditional whenever someone is in this function
anyway: hoist a `{d.lower(): d for d in defined_cols}` map out of the loop.)

### 5.5 Guess #5 — whole-file sha256 before parsing — **OVERTURNED, decisively**

**0.015 s on a 3 MB file — 0.002% of the run.** The module docstring's own
2026-07-26 measurement (935 MB/s, 0.535 s for 500 MB) reproduces — the
micro-benchmark independently measured 0.0418 s for 35.5 MB, i.e. 850 MB/s.
A ten-million-row map CSV of this shape is 300–355 MB and would spend
**~0.4 s hashing inside a ~20 hour run**.
"The big file is read twice" is true and it does not matter. Do not spend a
round on this.

### 5.6 Guess #6 — `exec_module` of every script per file — **OVERTURNED (per-FILE, ~1 ms per script)**

`_discover_and_execute_pipeline` timed with a synthetic `scripts/` folder
(each probe script imports pandas + numpy and subclasses `BasePipelineParser`):

| scripts in folder | seconds per file |
|---:|---:|
| 0 | 0.0002 |
| 1 | 0.0014 |
| 5 | 0.0049 |

≈ **1 ms per script per file.** For the large-file problem this is
unmeasurable — five scripts cost 5 ms inside a twenty-hour ingest. Two
caveats worth writing down rather than acting on:

* the cost is **per file, not per row**, so it is a small-file-throughput
  concern, not a large-file one;
* the numbers above are a **floor**: the probe scripts import modules already
  in `sys.modules`. A user script whose module-level code is expensive pays
  that on every file, because `exec_module` re-executes the module body each
  time. That is a latent trap, not a measured cost.

The one-time cost that *is* visible in the sweep lives here too: the first
call imports `pipeline_base`, which imports pandas — **1.2–2.0 s once per
process** (the `s3_resolve_rows_setup` row in §3). It is why the 1,000-row
point in §2 looks worse per row than the 5,000-row point.

### 5.7 Guess #7 — single heavy-lane daemon thread — see §7

---

## 6. Downstream: the outbox cannot be drained at this scale

This is the finding that changes the repair ordering, and none of it is a
timing on this box — it is arithmetic over constants in the shipped code.

* The watcher gives the **whole file one `transaction_id`**
  (`directory_watcher.py:1784`, `file_tx_id` reused by every chunk).
* `before_flush` stages **one `database_outbox` row per data row**, payload =
  full column dump, measured **999 bytes stored / 810 bytes of JSON**.
* The chain worker fetches 200 pending events, then — because the last one
  belongs to a transaction — pulls **all remaining events of that same tx up
  to `.limit(20000)`** (`chain_ingestion_worker.py:1052-1060`). With one
  tx per file, a 10M-row file makes that guard fire on **every iteration**,
  loading 20,000 ORM rows (~16 MB of JSON before ORM overhead) each time,
  ~500 times.
* Purge is capped at `OUTBOX_PURGE_CHUNK 1000 × OUTBOX_PURGE_MAX_CHUNKS 50`
  per `OUTBOX_PURGE_INTERVAL 3600 s` = **50,000 rows/hour = 1.2 M rows/day**,
  and only after `OUTBOX_RETENTION_DAYS = 7`.

**A single ten-million-row ingest produces 10 M outbox rows (~10 GB) and the
purge can retire 1.2 M/day.** Draining one file's outbox takes **8.3 days of
purge budget that only starts on day 7**. Two such files a week and the table
grows monotonically forever. The memory file already records
`database_outbox` as the one genuinely bloated table today (89,250 rows /
384,027 pages) at a fraction of this load.

---

## 7. Is the single heavy-lane thread a ceiling? — **Yes, and widening it as threads barely helps**

Two files, two different workspaces/tables, 8,000 rows each, three ways
(this box, `assy_qa`):

| run | wall | what it proves |
|---|---:|---|
| **A** serial, one after the other | 130.5 s | baseline |
| **B** both submitted to one `HeavyIngestionLane` | 144.5 s | **strictly serial** — both jobs ran on the single `watcher-heavy-lane` thread, per-file 73.5 s + 71.0 s = 144.5 s, i.e. zero overlap |
| **C** two free threads, no lane | **101.9 s** | **speedup 1.28×**, not 2× |

**B answers the ceiling question directly.** `HeavyIngestionLane` is one
daemon thread draining one FIFO queue (`directory_watcher.py:346-394`), and
the measurement shows the two per-file durations summing exactly to the wall
clock. Files from *different* workspaces do not overlap. The lane's stated
purpose — removing head-of-line blocking from the watchdog dispatch thread —
is achieved, but it moves the head-of-line block, it does not remove it.

(B being 10.7% above A is a single unrepeated measurement and I am not
claiming it as lane overhead.)

**Where it binds, in numbers from this box:** at 7.3 ms/row the lane's total
throughput is **~137 rows/s ≈ 11.8 M rows/day for every workspace combined**.
A single ten-million-row file therefore occupies the entire heavy lane for
**20–30 hours**, during which every large file for every table waits behind
it. It binds the first time two large files arrive inside one file's
processing window — which at these durations means "almost always".

**C is the answer to repair candidate #5, and it is discouraging.** Doubling
the worker count doubles nothing: 1.28×. The reason is §3 — **65% of the wall
clock is Python and SQLAlchemy, not the database**, so worker *threads*
contend on the GIL. To convert worker count into throughput the workers would
have to be *processes*, which is a much larger change (connection pool,
`_workspace_serial_locks` is a module-level in-process dict and would need a
cross-process equivalent, `processing_files` likewise).

---

## 8. The five candidate repairs, ranked by what the measurement says

**Two of the five are already shipped.** Before ranking anything, that has to
be said plainly, because a round spent re-implementing them buys zero.

| repair | verdict | evidence |
|---|---|---|
| **#3 `batch_row_upsert` row-data cap** | **ALREADY SHIPPED — premature for the ingestion path** | Two separate mechanisms already cover it. (a) The watcher never emits `batch_row_upsert` at all: `run_watcher.trigger_ws_refresh:108-128` posts `{table_name, change_count, created_logs?}` to `/internal/events/batch-refresh` — a count, not rows. (b) For the senders that do build items (`main.py`, `chain_ingestion_worker.py:519`), `event_constants.py:63 BROADCAST_ITEM_LIMIT = 100` degrades them to `batch_refresh_required` above 100 rows, **decided before the items are built**. And `MAX_NOTIFY_CREATED_LOGS = 500` is applied to the *accumulator* at `directory_watcher.py:1900-1904`, so a ten-million-row file holds 500 log dicts, not ten million. |
| **#4 audit `old/new_value` length cap** | **ALREADY SHIPPED — premature** | `event_constants.py:69 MAX_AUDIT_VALUE_CHARS = 4096` + `truncate_audit_value`, applied to both values in `create_audit_log` at **`crud.py:1117-1118`**, to the DB record and the notification dict alike, with an explicit truncation marker. Test: `tests/test_ingestion_checkpoint.py:657`. ⚠️ The brief cites `crud.py:224-236` for this; that range is now `_parse_version`. The line numbers in the board entry have drifted — the feature is at 1117. |
| **#2 PG COPY bulk path** | **URGENT — the only one that moves the curve** | targets `bulk_upsert_cell_sources` (30.6%) + the per-row data INSERT (14.7%) = **45% of wall**, and the SQLAlchemy `VALUES` compilation that is 163 s of the 223 s (§3.2). |
| **#1 downstream backpressure** | **SECOND — prevents an unbounded failure the profile proves will occur** | §6: 10 M outbox rows (~10 GB) per file vs a purge budget of 1.2 M rows/day that only starts on day 7. |
| **#5 configurable heavy-worker count** | **PREMATURE as specified** | §7: two worker threads gave **1.28×**, not 2×, because 65% of the wall is GIL-bound Python. As a config key over *threads* it sells a knob that does not turn. |

### Recommendation: #2 first — but only if it is scoped as a *set-based write path*, not as `COPY`

A literal `COPY` on `cell_sources` alone is worth about 30% and does not
help the biggest block. The measurement says the win is in replacing
**per-row statements with per-chunk statements**, in this order:

1. **The three per-row round trips (§3.1) — 49.6% of wall, and not on the
   candidate list at all.** Both SELECTs are 0.03–0.10 ms index scans; the
   cost is entirely that there are 200,000 of them per 100,000 rows.
   * SELECT #1 (`get_row_by_business_key`) — the prefetch at `crud.py:2570`
     already *proves* which business keys are absent; `_get_or_create_row`
     just does not read that proof. `crud.py:2552-2555` names this exact fix
     and defers it.
   * SELECT #2 (`crud.py:1990`, the composite-key collision probe) — a second
     identity gate the board did not list. Fixing only the first leaves two
     of three round trips.
   * The INSERT — one statement per row out of the ORM flush. A chunk-level
     bulk insert is what `COPY` (or `insertmanyvalues`) buys here.
2. **`cell_sources` (30.6%)** — `COPY` into a temp table + one
   `INSERT … SELECT … ON CONFLICT DO UPDATE` per chunk. This is the piece the
   candidate as written actually describes.

Even done perfectly this is a **2.5–3× improvement, not an order of
magnitude**: the remaining ~24% is per-row Python inside
`apply_row_update_internal` (priority resolution, per-column dict building),
which no bulk write path touches. Ten million rows would go from ~20–30 hours
to **~7–10 hours**. That is the honest ceiling of repair #2.

### And the thing no candidate addresses

**Storage (§4).** Ten million data rows write ~100 million rows and on the
order of 50 GB against a 14 GB production database. No amount of `COPY` or
backpressure changes that; it is a consequence of one `cell_sources` row per
column per *source name* (§10.2), one `audit_logs` row and one 999-byte
`database_outbox` row per data row. If "nearly ten million rows" is a real
target, this is the design question that has to be answered before the
throughput one — because a faster ingest just fills the disk sooner.

---

## 9. Query plans (EXPLAIN ANALYZE, BUFFERS — `assy_qa`, probe table at 100,000 rows)

Run against the probe table with 100,000 rows and 700,000 `cell_sources`
rows present. These are the actual plans, not a reading of comments.

```
--- get_row_by_business_key   (crud.py:1051)
Limit  (cost=0.42..8.44 rows=1 width=56) (actual time=0.079..0.079 rows=1.00 loops=1)
  Buffers: shared hit=2 read=2
  ->  Index Scan using ix_p3prof_map_business_key_val on p3prof_map
        Index Cond: ((business_key_val)::text = 'P3LOT0000_01_0_0'::text)
        Index Searches: 1   Buffers: shared hit=2 read=2
Planning Time: 0.255 ms      Execution Time: 0.095 ms

--- composite-key collision probe   (crud.py:1990-1993)
Limit  (cost=0.42..8.44 rows=1 width=56) (actual time=0.020..0.020 rows=1.00 loops=1)
  ->  Index Scan using ix_p3prof_map_business_key_val on p3prof_map
        Index Cond: ((business_key_val)::text = 'P3LOT0000_01_0_0'::text)
        Filter: ((row_id)::text <> '00000000'::text)
        Index Searches: 1   Buffers: shared hit=4
Planning Time: 0.170 ms      Execution Time: 0.032 ms

--- cell_sources prefetch, 1000 row_ids   (crud.py:2597-2608 shape)
Nested Loop  (actual time=1.734..14.213 rows=7000.00 loops=1)
  Buffers: shared hit=3956 read=207
  ->  HashAggregate (1000 ids)
  ->  Index Scan using ix_cell_sources_row_id on cell_sources  (loops=1000)
        Index Cond: ((row_id)::text = ("ANY_subquery".row_id)::text)
        Filter: ((table_name)::text = 'p3prof_map'::text)
Planning Time: 9.279 ms      Execution Time: 14.823 ms
```

Reading:

* Both per-row statements are **index scans on `ix_*_business_key_val`,
  4 shared buffers, 0.03–0.10 ms**. There is no plan defect to fix. The 129 s
  they cost at 100k rows is 100,000 × (round trip + planning + Core
  construction), and **`Planning Time` alone (0.17–0.26 ms) already exceeds
  `Execution Time`** — these statements are re-planned every row.
* The `cell_sources` prefetch does 1,000 index probes per chunk (one per
  row_id) rather than one range scan, and pays **9.3 ms of planning** to do
  it. At 1,000-row chunks that is 15 ms per chunk — 1.5 s per million rows,
  tolerable, but it scales with chunk count, which is a reason `batch_size`
  should be a knob (§10).
* Index inventory is not lean: the probe table carries **nine** indexes
  (heap 18 MB vs indexes 37 MB), `cell_sources` six, `audit_logs` five,
  `database_outbox` seven. Every per-row INSERT maintains all of them.

---

## 10. Things found on the way that are not in the brief

Reported, not fixed — this lane changed no production code.

1. **The heavy-lane threshold is a SIZE, and rows are what cost.**
   `_classify_lane:964` routes on `st_size` against `heavy_file_mb` (default
   10 MB). A 300,000-row map CSV of the shape measured here is **~9 MB** — it
   stays in the *normal* lane and blocks the watchdog dispatch thread for
   **~35 minutes**. The threshold that decides "this will take a long time"
   is measured in bytes and the thing that takes a long time is rows. A
   seven-column map row is ~30 bytes; a hundred-column row is ~400. The same
   10 MB is 330,000 rows of one and 25,000 of the other.

2. **`cell_sources` grows per (row, column, SOURCE NAME), and the source name
   is the file's own basename.** Re-dropping the same content under a new
   filename does not update the existing source layer — it adds a whole new
   one. Observed directly: ingesting identical 1,000-row content twice under
   two different filenames left **14,000 `cell_sources` rows for 1,000 data
   rows across 1,000 distinct `row_id`s** — 7 columns × 2 sources. Production
   collectors that emit dated filenames therefore multiply `cell_sources` by
   the number of drops, forever. This is very likely why production
   `cell_sources` is 1,204 MB for 470,000 rows.

3. **The whole file shares one `transaction_id`.** `file_tx_id` at
   `directory_watcher.py:1784` is generated once and reused by every chunk.
   That is what makes the chain worker's "fetch all remaining events of this
   tx" guard (`.limit(20000)`) fire on every iteration for a large file (§6),
   and it also means the audit trail cannot distinguish chunk boundaries.

4. **`batch_size = 1000` deserves to be a config key, but not for the reason
   assumed.** It is hardcoded at `directory_watcher.py:1786` with no key and
   no env var. The measurement says the per-row costs (3 round trips, the
   Python loop) are chunk-size *independent*, so tuning it will not move the
   headline. What it does control is the number of prefetch/planning cycles
   (9.3 ms planning per chunk, §9) and the peak size of
   `cell_sources_to_upsert`. Worth exposing; not worth expecting a win from.

5. **`ingestion_settings.json` is re-read from disk on every file event**
   (`load_ingestion_settings:214`, no cache; called by
   `get_heavy_threshold_bytes`, `dedup_by_signature_enabled`,
   `resume_from_checkpoint_enabled`, `nested_dirs_enabled` — four separate
   reads per file). Irrelevant for a 20-hour file; a real per-file tax on a
   workspace receiving thousands of small ones.

6. **Resume saves database time, not parse time** — as the brief said, and
   the profile now prices it: parse is 0.22% of the run, so a resume at 90%
   still skips 90% of the cost. The `islice` re-parse is the right trade.

---

## 11. Reproducing this

Every artefact is in the session scratchpad (nothing under `server/`):

| file | what it does |
|---|---|
| `P3_env.py` | isolation bootstrap (`assy_qa` + `dev_env`), asserted in-process |
| `P3_setup.py` | declares `p3prof_map` in the **dev_env** config copy and creates it |
| `P3_profile.py` | the end-to-end profile (`--rows N --maps M --reset`) |
| `P3_micro.py` | parse / normaliser / discovery micro-benchmarks (no DB) |
| `P3_lane.py` | heavy-lane serialisation + thread-scaling probe |
| `P3_explain.py`, `P3_size.py` | plans, index inventory, per-row storage |
| `P3_show.py` | formats the result JSONs |

**What is left behind: nothing.** `P3_cleanup.py` dropped `p3prof_map` and
`p3prof_map2`, deleted their rows from `cell_sources`, `cell_overwrites`,
`audit_logs`, `database_outbox`, `file_ingestion_checkpoints` and
`wafer_map_metadata`, removed both keys from the **dev_env copy** of
`table_config.json` (back to its original 23 tables — the user's
`server/config` was never touched), and removed the two probe workspaces.
Verified after cleanup: no relation matching `p3prof%` remains, and the
database list is `assy_manager 14 GB` / `assy_qa 1825 MB` — no probe database
was ever created. `assy_qa` is 5 MB larger than before the sweep (dead
tuples pending autovacuum). `assy_manager` was read for size metadata only
and never written. `P3_setup.py` rebuilds the whole rig in seconds if phase 2
wants it back.
