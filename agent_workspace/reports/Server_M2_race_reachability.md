# M2-REACH — is P3's cross-process duplicate race reachable?

**REACHABLE, AND REPRODUCED.** Two real OS processes, production-sized chunk (1,000 items),
isolated `assy_qa` database: the write path produced **two rows carrying the same
`business_key_val`**, silently, with no error. The same experiment with P3's proof
neutralised at runtime produced **one** row. Tier T3, no code changed, no commit.

---

## 0. The one-line mechanism

`apply_batch_updates` (`server/database/crud.py:2769-2821`) prefetches identity once per
call and builds `ProbedIdentity` = *values asked about minus values returned* = "these do
not exist in the table". `_get_or_create_row` (`crud.py:1620-1640`) then skips its SELECT
for any value in that set. The proof is sound against **this session's** loop (nothing is
flushed inside `no_autoflush`), and the docstring says exactly that. It is not sound
against **another process committing**, and nothing in `server/` provides cross-process
exclusion — `grep -rn "pg_advisory" server/` returns **zero hits**, and the only
serialization that exists is a `threading.Lock` whose own comment says
`(프로세스 간 배타는 범위 밖)` (`server/parsers/directory_watcher.py:329,334`).

---

## 1. Which process hosts which caller

`run_decoupled_app.py:301-318` starts five children. Data-writing callers of
`crud.apply_batch_updates` map onto them as follows (call sites are live, tests excluded):

| Process | Module → call site | Tables written |
|---|---|---|
| **Backend FastAPI Server** (`server/main.py`, `DECOUPLED=True`) | `main.py:2287` batch route; `frame_confirmation.py:391` (imported `main.py:4385`); `map_alignment.py:435` → registrar; map push | any data table; `wafer_map_metadata` |
| **File Ingestion Watcher** (`run_watcher.py`) | `parsers/directory_watcher.py:1894`; `map_meta_registrar.py:364` (imported `directory_watcher.py:55`) | watched ingestion tables; `wafer_map_metadata` |
| **Chained Ingestion Worker** (`run_chain_worker.py`) | `chain_ingestion_worker.py:445`; `enrichment_candidates.py:759` (imported `chain_ingestion_worker.py:38`); `map_meta_registrar.py:364` (imported `:34`) | chain **target** tables; enrichment derived tables; `wafer_map_metadata` |
| **Auto Update Scheduler** (`run_auto_update.py`) | `import retroactive` at `run_auto_update.py:733` → `retroactive._run_chain_replay` → `chain_replay.py:310`; `_run_enrichment_backfill` → `enrichment_backfill.py:432`; `_run_enrichment_confirm` → `enrichment_candidates.py:759` | **the same chain target / derived tables as the chain worker** |
| **Graph DB Sync Worker** (`run_graph_sync.py`) | none | — |
| ad-hoc CLI (6th process, operator-run) | `scripts/backfill_enrichment.py`, `scripts/chain_replay_cli.py`, `scripts/seed_*.py` | same tables again |

So **four** long-lived processes write data tables, not one. The task brief listed six
call sites; the load-bearing correction is that `chain_replay` / `enrichment_backfill` /
`enrichment_candidates` are **not** chain-worker-only — `retroactive` pulls all three into
the **scheduler** process.

## 2. A concrete reachable pairing with an *identical* business key

**Chain worker (process 3) vs. `chain_replay` running inside the scheduler (process 4),
on the same chain target table.**

This is the strongest pairing because the two sides are *guaranteed* to compose the same
key rather than merely permitted to. Both invoke the **same** mapper through the same
helper: `chain_ingestion_worker.py:409/416` and `chain_replay.py:262-265` both call
`execute_custom_mapper(module_name, func_name, db, payload, rule=rule)` with the rule read
from the same `chain_rules.json`, and both write `item["business_key_val"]` straight
through (`chain_replay.py:297`). Replaying a rule over rows the live chain is deriving at
the same instant yields byte-identical business keys on the same `target_table`.

Nothing prevents the overlap. `run_auto_update.py:707-753` guards only against a **second
retroactive run in its own process** (`retroactive_busy()` inspects `self._retroactive_thread`);
its docstring's stated concern is two concurrent replays, and it is silent about — and
structurally blind to — the chain worker in another process. Replays are operator-triggered
via an outbox event, i.e. at an arbitrary moment relative to ingestion traffic.

Two further pairings, both with the same key and both real, ranked lower only because they
need a narrower coincidence:

- **`wafer_map_metadata`, three-way.** `map_meta_registrar.meta_business_key(target_table, map_id)`
  (`map_meta_registrar.py:156`) is a pure function of table + map id, and the registrar is
  reached from the watcher (`directory_watcher.py:55`), the chain worker
  (`chain_ingestion_worker.py:34`) and the web server (`frame_confirmation.py:338`,
  `map_alignment.py:435`). Any table that is both a watched ingestion target and a chain
  target gives two processes the identical meta key for the identical map. The registrar's
  own existence check (`map_meta_registrar.py:327-340`) is itself a proof-of-absence with
  the same flaw, so it does not help; pre-P3 the per-row SELECT was the backstop, and P3
  removes it.
- **Web grid/map write vs. watcher ingestion** on the same table. Same key only when the
  operator's new row and the file's row resolve to the same composite key — plausible for
  a map push into a table a file is landing in, but it needs both sides to *insert*, so it
  is genuinely narrower than the two above.

Pairings that **cannot** collide: anything the graph sync worker does (no data writes), and
two files into the same table from the watcher — that is serialized *within* the process by
`get_workspace_serial_lock`.

## 3. The missing unique index is universal, not partial

Measured read-only against the dev database `localhost:5432/assy_manager` (this box), today:

- **50** indexes mention `business_key_val`, over **25** tables — exactly two per table,
  `idx_<t>_bk` and `ix_<t>_business_key_val`.
- **`indisunique = true` on 0 of 50.**
- **0** unique or primary-key *constraints* anywhere mention `business_key_val`.
- **0** tables carry a `business_key_val` column without an index (the column and the
  non-unique index are co-extensive).

So the answer is *every* map/data table, with no exceptions to carve out. (The brief's
figure of 54 does not match today's catalogue; 50/25/0-unique is what the live catalogue
returns now. The important number — unique = 0 — is the same either way.)

**Unexpected, and it matters for the board:** the duplicate census is currently **clean**.
Across all 25 tables, 52,725 rows, `count(business_key_val) = count(DISTINCT business_key_val)`
in every one — **zero surplus rows**. D2 was carried as "surplus 389 rows cleanup, which D3
requires first". On *this box, today*, D3 has nothing blocking it. I did not verify
production, and D2 may have been measured elsewhere or already cleaned; that is a question
for the lead PM, not a claim I can settle from here.

## 4. Reproduction — two processes, `assy_qa`, production chunk size

No `server/` file was touched. Probe: `…/scratchpad/M2R_writer.py` (two roles), table
`production_plan` (declared in `dev_env/config/table_config.json`, `business_key: plan_id`),
DB `postgresql://…/assy_qa`, `ASSY_DATA_ROOT=dev_env`. Both processes wait on a shared
wall-clock barrier so the race is not an artefact of process-startup jitter.

**Run D — the headline, at the chunk size real callers use.** `directory_watcher.py:1892`
chunks at 1,000 (`# 1,000건 청크 단위로…`); `chain_replay.WRITE_CHUNK = 1000`;
`enrichment_backfill.DEFAULT_CHUNK_SIZE = 1000`; `map_meta_registrar.CHUNK_SIZE = 1000`.

```
[slow] 04:19:19.009  enters apply_batch_updates, 1000 items (race key last)
[fast] 04:19:20.007  another PROCESS calls apply_batch_updates, 1 item, same key
[fast] 04:19:20.965  committed          <- 1.96 s into the window, 0.42 s before the flush
[slow] 04:19:21.382  returned after 2.37 s
```

Result: **COUNT 2.**

```
('M2R_RACE_D', '019fd884-0bee-7789-aa46-965a6360b198', 'SLOW', ...19.238)
('M2R_RACE_D', '019fd884-0e43-7c39-9212-632d8f3ea95e', 'FAST', ...20.844)
```

Both rows persist. No error, no warning, no constraint violation — the silent outcome the
brief predicted. Runs A and B (20,001 items, ~44 s window) reproduced it identically.

**The counterfactual, which is what pins the cause on P3.** Run C, same two processes, same
timing, with `crud._absence_is_proven` monkeypatched to `False` **inside the probe process
only** (nothing on disk modified) — i.e. the pre-P3 per-row SELECT: **COUNT 1**. The slow
writer found the other process's committed row and updated it, which is the correct merge.

Two details that make this result trustworthy rather than lucky:

- **The race item is placed LAST in the batch.** With it first, even the pre-P3 SELECT runs
  before the other process commits, and both arms produce a duplicate — the experiment would
  have "passed" while proving nothing. Position is the axis that activates the defect.
- **The mutation was sufficient.** Outcome changed 2 → 1, so `_absence_is_proven` really is
  the gate. (This is the lesson from the earlier round where a one-gate mutation changed no
  behaviour: `row_cache` is consulted first, so a mutation that only touches the DB lookup
  can be inert. Here it was not.)

Side observation, not the point but worth recording: the nop3 arm took **69.9 s** where P3
took **44.0 s** on the same 20,001 items. P3's performance win is real and large.

## 5. Severity and what closes it

**Recommendation: this is a real data-integrity defect, not a theoretical one, but it is
pre-existing in kind and P3 widens it by roughly three orders of magnitude in time —
per-row (microseconds) to per-chunk (2.4 s measured, 3.7 s per QA).** The honest framing
is that P3 does not *create* an unguarded write path; it removes the last accidental
guard from one that was never protected by design.

I do not think the hold should stay on P3 *specifically*, and here is why: the structural
fix is already named on the board. **D3 (`business_key_val` UNIQUE index)** converts every
scenario above from a silent duplicate into a loud `IntegrityError` — for the pre-P3 code
as well, which is the tell that this was never P3's bug to own. And **D2**, the cleanup D3
was waiting on, measures **zero surplus rows on this box today** (§3). If that holds where
it matters, D3 is unblocked and is a short piece of work.

Concretely, one of:

1. **Ship D3** (unique index / constraint on `business_key_val` per table), and give
   `apply_batch_updates` an `IntegrityError` retry that re-prefetches and merges. Closes the
   whole class, for every caller, in every process. Preferred.
2. If D3 must wait: a per-table `pg_advisory_xact_lock` around the write in
   `apply_batch_updates`. Serializes cross-process writers to one table. Cheap to write,
   but it converts a correctness problem into a throughput problem and needs its own
   measurement — and today's zero-duplicate census argues D3 is the better trade.

Doing nothing is defensible only for as long as the exposure is understood: a duplicate is
silent, and by the time it is noticed the layering caches (`CellSource` / `CellOverwrite`)
have already been written against two different `row_id`s for one business identity.

## 6. Which box every number came from, and what would change the answer

- §3 catalogue and duplicate census: **dev DB `assy_manager` on this workstation**, read-only.
- §4 reproduction: **isolated `assy_qa` on this workstation**, two `conda run` processes.
- Timings (2.37 s / 44 s / 69.9 s) are **this workstation's**, single developer, otherwise
  idle. Production is a different machine.

**This box is a simulation.** For the answer to be *less* severe in production, one of these
would have to be true: the chain worker and the scheduler never write the same table (a
`chain_rules.json` fact, not a code fact — check the deployed rules); or production writes a
far smaller chunk; or production is fast enough that the window closes below the arrival rate
of conflicting writes. For it to be *more* severe: production has more concurrent ingestion,
more operators, and — from the memory file — a corporate proxy and real multi-user traffic.
More concurrency widens the window's hit rate linearly. The mechanism itself does not depend
on anything specific to this box: it is READ COMMITTED plus an absent unique index, and both
are properties of the schema, not of the machine.

Note also that the reported "no unique index" has a second live consequence I stumbled on:
every probe run printed
`[VirtualJoin:dt_log_confirmed_attribution] rejected: no unique index covers dt_job_attribution(dt_job)`.
Some feature is already being refused for want of exactly the indexes D3 would add.

## 7. Housekeeping

- **No code changed.** `git status` on `server/` is untouched by this lane.
- Probe rows removed from `assy_qa`: 81,007 `production_plan` rows, 240,018 `cell_sources`
  rows, 81,008 outbox rows. `production_plan` and its `cell_sources` are back to 0.
- Databases remaining on this server: `assy_manager` (14 GB, the dev DB — not mine),
  `assy_qa` (642 MB, the shared isolated env — not mine, left up),
  **`assy_obx2_6f856759` (353 MB)** — carries this session's id suffix but was **not created
  by this lane**; it is presumably a sibling lane's probe DB, so I left it. If no lane claims
  it, it should be dropped.
- Probes under `…/scratchpad/M2R_*.py` — `M2R_writer.py`, `M2R_check.py`, `M2R_indexes.py`,
  `M2R_counts.py`, `M2R_cleanup.py`, `M2R_dbs.py`. Reproducible; nothing needs preserving.
- **`pytest` was not run**, per instruction.

## 8. Lessons proposed for `agent_workspace/memory/server-pm.md` (not added directly)

- **함정**: 동시성 재현 실험에서 **경합 항목을 배치 앞쪽에 둔다.** 그러면 결함 있는 코드와
  없는 코드가 **똑같이 중복을 만들거나 똑같이 안 만든다** — 프리페치 직후에 처리되므로
  per-row SELECT도 상대의 커밋을 못 본다. 실험은 「통과」하면서 아무것도 증명하지 않는다.
  **올바른 방법**: 경합 항목을 **배치 끝**에 둔다. 그리고 반드시 **반대 팔**(결함 제거 버전)을
  같은 타이밍으로 돌려 결과가 갈리는지 확인한다 — 2 대 1로 갈려야 원인이 고정된다.
- **함정**: 두 프로세스를 각각 띄우고 `sleep`으로 타이밍을 맞춘다. 프로세스 기동·import
  비용이 수 초라 실제 경합 창(2.4초)보다 크고, 창을 20배 넓혀야 겨우 맞는다.
  **올바른 방법**: 양쪽이 import를 끝낸 뒤 **절대 시각 배리어**에서 동시에 출발시킨다.
  그래야 **운영과 같은 청크 크기**로 잰 숫자를 말할 수 있다.
