# OUTBOX-④ Phase 1 — collapsing the per-row outbox event: design and measurement

**Status: PROPOSAL. No production code was changed.** No pytest was run (a QA lane owns it).
All numbers below were produced on **this workstation**, which is a simulation, in a
session-unique isolated PostgreSQL database `assy_obx_6f856759`. That database has been
**dropped**; the remaining `assy%` databases are `assy_manager` (14 GB, owner `postgres`)
and `assy_qa` (361 MB, owner `postgres`), neither created by this round.

Probe scripts: `OBX_payload_size.py`, `OBX_physical_size.py`, `OBX_drain_guard.py`,
`OBX_collapsed_size.py`, `OBX_drop.py` under the session scratchpad.

---

## 1. The question you asked first: does each consumer need the row's VALUES?

**Answer: exactly one consumer family does, and it is not the one carrying the volume.**
Everything else needs only "the rows in this set changed".

| Consumer | Needs the row's VALUES from the event? | Evidence |
|---|---|---|
| chain worker — **nested-payload mappers** | **YES** | `server/mappers/production_mapper.py:11` `row_data = payload.get("data", {})`; `server/mappers/utils.py:15` `raw_data = p.get("data", {})` then `cell_detail["value"]` |
| chain worker — **row-like mappers** (`dt_map`) | **NO** — wants row-shaped objects and already re-reads them | `server/dt_map_derivation.py:580` `pick(row,col) = row.get(col) if isinstance(row,dict) else getattr(row,col,None)`; `server/mappers/dt_map_mapper.py:181` `rows.extend(q.all())` — this mapper's correction path **already** takes ORM rows re-read from the DB |
| chain worker — target/HOL estimation | **NO** — `table_name`, `event_type`, `source_name` only | `chain_ingestion_worker.py:359-363` |
| chain worker — tx grouping + completion guard | **NO** — `transaction_id` only | `:1049`, `:1059`, `:1079` |
| chain worker — undelivered sweep | **NO** — `transaction_id` + `table_name` only | `:832-853` |
| graph materializer | Reads values, **but is not self-sufficient on them today** and the pointer-shaped path already exists | reads at `graph_materializer.py:427-431`; then `attach_col_sources` (`:500`) goes **back to the DB** for `CellSource` provenance; and `resync_table(db, table, mappings, row_ids=[...])` (`:519`) is the same materialization driven purely by row ids |
| WS broadcast — chain writes | **NO** — built from `crud.apply_batch_updates` return values, and above `BROADCAST_ITEM_LIMIT=100` degrades to a bare count | `chain_ingestion_worker.py:519-579` |
| WS broadcast — human edits | **NO** — built in-process from crud's return, never touches the outbox | `main.py:3796-3829` |
| WS broadcast — file ingestion | **NO** — table-level refresh, no items at all | `run_watcher.py:108-128` |
| `/admin/outbox/failed` | displays `payload` (diagnostic only) | `main.py:3992-4029` |
| `health.py` outbox depth | count only | `health.py:370-377` |

Two consequences worth stating plainly:

1. **The per-row granularity is already discarded on every path that reaches a screen.**
   The human path never reads the outbox; the ingestion path emits a table-level refresh;
   the chain path throws the items away above 100. Nothing a user sees depends on the
   outbox carrying a row's values.
2. **The graph consumer already has the collapsed shape implemented.** `resync_table(...,
   row_ids=[...])` builds the identical `{"row_id","values","updated_by","event_time"}`
   dicts by re-reading the table (`:541-550`) and hands them to the same
   `attach_col_sources` / `materialize_rows` pair the incremental path uses. Per the
   charter's "check existing primitives first": ④ does not need a new mechanism for the
   graph, it needs the existing one wired to a range instead of to payloads.

So ④ is **cheap for every consumer except the nested-payload mappers**, and those are
user-owned files in the gitignored `server/mappers/` tree.

### An out-of-scope defect this survey turned up — flagging, not chasing

`chain_ingestion_worker.execute_custom_mapper` passes the **nested** outbox payload
(`get_payload_dict(e)`) straight through. `dt_map_mapper.build_dt_map_batch_df` on the
`trigger == source_table` arm does `rows = list(payloads)` (`dt_map_mapper.py:200`) and
hands those nested dicts to `derive_cells`, whose accessor is
`row.get(col)` (`dt_map_derivation.py:580`). On a nested payload
`payload.get("lot_id")` is `None` — the values live under
`payload["data"]["lot_id"]["value"]`. Statically this reads as "the live `dt_log` →
`dt_map` trigger path derives nothing", while the correction path (`expand_trigger`,
which re-reads ORM rows) works. **This is a static read, not a live reproduction** — I
did not run it, and the dt-to-core lane is active in this tree. Escalating rather than
touching it.

It also cuts in ④'s favour: the accessor the derivation module actually wants is a
**row-like object**, which is exactly what re-reading gives you.

---

## 2. Measured current cost

### 2a. Payload size per event, per configured table

Rebuilt exactly what `database.stage_event` writes (`database.py:167-191`), from the live
`server/config/table_config.json`, with a 12-character representative value per cell.

| table | columns in payload | JSON bytes |
|---|---:|---:|
| `dt_log` | 16 | 1,623 |
| `bonding_log` | 13 | 1,374 |
| `map_split_registry` | 13 | 1,366 |
| `lot_event` | 9 | 1,045 |
| `core_wafer_map` | 8 | 951 |
| … 14 tables total | mean 7.6 | mean 909, min 612, max 1,623 |

The board's ~999 B is right. `dt_log`, the file that motivates this round, is the worst
at 1,623 B.

### 2b. Physical cost in PostgreSQL, indexes included

100,000 rows inserted per table into a real `database_outbox` (the DDL from
`models.py:118-175`, all seven indexes), then `VACUUM ANALYZE`:

| table | heap B/row | index B/row | toast B/row | **TOTAL B/row** | **at 10,000,000 rows** |
|---|---:|---:|---:|---:|---:|
| `dt_log` | 2,048 | 59 | 1 | **2,108** | **19.6 GiB** |
| `bonding_log` | 1,638 | 59 | 1 | **1,698** | **15.8 GiB** |
| `core_wafer_map` | 1,170 | 59 | 1 | **1,230** | **11.5 GiB** |

**The board's 10 GB estimate is low by roughly 2×** for `dt_log`: JSONB adds per-key
overhead the raw JSON byte count does not show, and the tuple stays just under the 2 KB
TOAST threshold so nothing is compressed (toast = 1 B/row).

*Instrument caveat, stated because it flatters the result:* the 59 B/row index figure is
an **underestimate for the general case**. All 100,000 probe rows share one
`transaction_id` and one `status`, so PostgreSQL's B-tree deduplication collapses
`idx_outbox_txid` and `idx_outbox_pending` almost to nothing. For the single-file case
this is the honest number (a file really is one `transaction_id` — see 2d), but across
many files the index term grows. It does not change the conclusion: heap is 97% of the
bill.

### 2c. The purge maths, done out

From `chain_ingestion_worker.py:182-185`:

- `OUTBOX_PURGE_CHUNK (1000) × OUTBOX_PURGE_MAX_CHUNKS (50)` = **50,000 rows per cycle**
- `OUTBOX_PURGE_INTERVAL = 3600.0` → **50,000 rows/hour = 1,200,000 rows/day**
- `OUTBOX_RETENTION_DAYS = 7` → nothing is eligible for the first 7 days

One 10M-row file: **7 days of waiting, then 8.33 days of purging ≈ 15.3 days** carrying
the bloat on a table that sits in the read path.

The sharper statement is not about backlogs at all: **1.2M rows/day is the drain's
sustained ceiling.** A single 10M-row file is 8.3× a full day's drain capacity. At any
ingestion rate above 1.2M rows/day the outbox does not have a steady state — it grows
without bound, and the purge's own comment (`:183`, 「시간당 삭제량은 시간당 유입량 수준의
소량」) states the assumption that is being violated.

### 2d. Producer-side cost, and the drain guard

**One `transaction_id` per file — verified, not inherited.**
`parsers/directory_watcher.py:1784` `file_tx_id = str(uuid.uuid4())` is created once per
file and passed to every 1,000-row chunk at `:1880`. P3's claim holds.

**The completion guard therefore fires on every drain iteration.** Replaying the two
queries the worker actually issues (`:1009` `LIMIT 200`, then `:1052-1060` `LIMIT 20000`)
against 100,000 `core_wafer_map` events sharing one `transaction_id`:

```
pending batch=200
Limit  (actual time=0.101..12.485 rows=20000 loops=1)
  ->  Seq Scan on database_outbox  (rows=20000, Buffers: shared hit=2887)
Execution Time: 13.161 ms

guard pulled 20,000 extra events, 19.1 MiB of payload in ONE group (avg 1,004 B/event)
=> one drain iteration builds a mapper group of 20,200 events
```

The query itself is fast (the Seq Scan aborts at the LIMIT because nearly every row
matches). The cost is what comes back: **19.1 MiB of JSONB decoded into ORM objects and
handed to a mapper as a single group, ~495 times** over a 10M-row file. On `dt_log`
(2,108 B/row) the same iteration is ~40 MiB.

**Producer side.** The comment at `crud.py:1650-1661` records an in-repo measurement:
the outbox rows written in the same flush as a 100,000-row file cost **8.2 s** — i.e.
~**13.7 minutes of pure outbox insertion per 10M rows**, on top of the write P3 just made
2.12× faster. (Cited from the repo, not re-measured by me.)

---

## 3. Proposed event shape

One event per `(table_name, event_type)` per **flush**, carrying the explicit row-id list
of that flush:

```json
{
  "event_type": "BATCH_UPSERT",          // and BATCH_DELETE
  "table_name": "core_wafer_map",
  "payload": {
    "table_name": "core_wafer_map",
    "row_ids": ["0198...", "0198...", ...],   // explicit list, not a range
    "row_count": 1000,
    "transaction_id": "<file_tx_id>",
    "chunk_index": 17,
    "updated_by": "batch_ingester",
    "source_name": "DT_LOG_20260807_001.csv",
    "timestamp": "2026-08-07T..."
  }
}
```

**Why a list and not a `(lo, hi)` range.** `row_id` is a client-side uuid7 string
(`crud.py:1659` `row_id=update_item.row_id or str(uuid6.uuid7())`), so new rows are
time-ordered and would range cleanly — but an upsert chunk also touches **existing** rows
whose ids were minted long ago. The ids in one chunk are not contiguous. A range would
silently over- or under-select.

**Why this preserves the transactional-outbox guarantee.** Because `row_id` is generated
in Python rather than by a SERIAL, the id list is fully known at `before_flush` time — no
round trip is needed to learn it. The chunk event is `session.add`-ed on the **same
session inside `before_flush`**, exactly as `stage_event` does today, so it commits in the
same transaction as the rows it names. The `NOTIFY` latch (`_OUTBOX_NOTIFY_SENT`) is
already per-transaction and needs no change.

### Measured cost of the proposed shape

2,000 collapsed events covering 2,000,000 ingested rows, same table DDL:

| | per-row (today, `core_wafer_map`) | collapsed |
|---|---:|---:|
| outbox rows per 10M ingested | 10,000,000 | **10,000** |
| JSON bytes per event | 951 | 40,259 |
| **total bytes per INGESTED ROW** | 1,230 | **27.2** |
| **total size at 10M rows** | 11.5 GiB | **260 MiB** |

**1,000× fewer rows, 45× fewer bytes.** The 40 KB payload exceeds the TOAST threshold, so
it is stored out of line and pglz-compressed to ~27 KB — which is where most of the byte
win comes from, and which is also a cost (see §5).

**And the purge maths dissolves:** 10,000 rows is one fifth of a *single* purge cycle
(cap 50,000). Minutes of drain, not 15 days. I have changed no purge knob, as instructed —
the point is that at this production rate they no longer need changing.

---

## 4. The human path must NOT be collapsed (Value 3)

Human edits and bulk ingestion need **different treatment**, and the reason is not
symmetry-breaking for its own sake:

- A human edit's own screen update does not go through the outbox at all
  (`main.py:3796-3829`), so collapsing could not delay it. **But** the derived tables a
  human correction feeds *do* travel the outbox, and that derived write is what closes
  the correction loop on screen. A human correction is one row; there is nothing to
  collapse and no size argument for touching it — so the risks in §5 (snapshot→pointer,
  chunk-wide quarantine) would be taken for zero gain.
- Bulk ingestion is where the 10M rows are and where per-row granularity is already
  thrown away downstream.

**Recommended discriminator: an explicit opt-in, not inference.** Add
`request_outbox_mode` to the `sys._context_vars_cache` singleton in
`server/database/context.py` (alongside `request_user` / `request_transaction_id` /
`request_source`), **defaulting to `"per_row"`** — i.e. every existing caller, including
every `main.py` endpoint, keeps today's behaviour without being edited. The bulk callers
opt in: `parsers/directory_watcher.py` (file ingestion), the chain worker's own
`chain_ingestion` writes, and retroactive sweeps.

I specifically do **not** recommend inferring bulk-ness from `request_source` (it is a
*filename* for ingestion — `directory_watcher.py:1769-1779` — so a table with a
filename-shaped user source would misroute) nor from row count in the flush (a human map
push is thousands of rows and is still a human path).

**The undelivered-marker contract is untouched.** Nothing in this proposal changes the
meaning of `processed_chain`, `status`, or `broadcast_at`; the chunk event flows through
`process_pending_groups` and gets stamped exactly like a per-row event, and
`internal_event_client.record_undelivered_notification` never goes through `before_flush`
at all. The only shift is granularity: one `broadcast_at` stamp now covers 1,000 rows.
Since `sweep_undelivered_broadcasts` fires a **table-level** `batch_refresh_required`
(`:868-873`), a coarser marker loses nothing — the recovery signal was already
table-level.

---

## 5. What each consumer would have to change, and what the design gives up

### Changes required

| Consumer | Change |
|---|---|
| `database.py` `auto_stage_database_outbox` / `stage_event` | Accumulate row ids per `(table, event_type)` and stage one event when `request_outbox_mode == "collapsed"`. Per-row path unchanged. |
| `chain_ingestion_worker` normalize/group (`:1033-1084`) | `transaction_id` is still in the payload; grouping is unchanged. The `LIMIT 20000` completion guard now pulls **chunk** events, so 20,000 of them would cover 20M rows — the cap should come down, but that is a §6 question. |
| `chain_ingestion_worker` → mapper hand-off (`:407`, `:416`) | Must **materialize** chunk events into the shape mappers expect: `SELECT ... WHERE row_id IN (...)` chunked at 1,000, then either (a) rebuild the nested `{col:{value,...}}` dicts so `production_mapper` / `payloads_to_df` are byte-identical, or (b) pass ORM rows, which is what `dt_map_derivation.pick` wants. **(a) is required for compatibility; (b) is what the code wants.** Recommend (a) with a shared helper so both families keep working. |
| `graph_materializer.materialize_events` (`:423-431`) | On a chunk event, take the `row_ids` and go through the **existing** `resync_table(..., row_ids=[...])` path (`:519`) instead of `flatten_payload_data`. No new machinery. |
| `_group_target_tables`, sweep, WS, health, admin | **No change.** They read `table_name` / `event_type` / `transaction_id` / counts only. |

### What it gives up

1. **The event stops being a snapshot and becomes a pointer.** A consumer that drains
   late sees the row's *current* value, not its value at event time. For a derived-table
   chain that is arguably more correct, but it is a real semantic change and it must be
   said out loud rather than discovered.
2. **DELETE cannot be a pointer.** A deleted row cannot be re-read. `BATCH_DELETE` must
   keep carrying enough of the row (business key + the mapper key columns) to be
   actionable, or deletions must stay per-row. Recommend: keep DELETE per-row — the
   volume is in CREATE/EDIT, not DELETE.
3. **Retry quarantine gets 1,000× coarser.** Today one poison row fails three times and is
   quarantined alone (`process_pending_groups:757-773`). Collapsed, one poison row
   quarantines its whole 1,000-row chunk. This is the most user-visible loss and it
   deserves an explicit ruling.
4. **Every chunk read is a TOAST fetch.** 40 KB payloads live out of line. Cheap relative
   to what it replaces, but it is not free, and a variant worth considering is a side
   table `outbox_chunk_rows(event_id, row_id)` — which trades TOAST for rows again and is
   probably the wrong trade.
5. **The re-read is new work the consumer pays.** It should be *cheaper* than what it
   replaces (an indexed `row_id IN` fetch instead of decoding 19–40 MiB of JSONB per
   iteration) — but that is a prediction, not a measurement, and it must be measured in
   phase 2 before the change lands.
6. **Both shapes must be handled for at least the 7-day retention window.** Old per-row
   events will still be in the table after the deploy. Every consumer branch above needs
   a dual-shape arm, and it cannot be removed until `OUTBOX_RETENTION_DAYS` has elapsed.
7. **The admin FAILED view shows a chunk, not a row** (`main.py:3992-4029`). Diagnostic
   degradation only.

---

## 6. Open questions for your ruling before phase 2

1. **Quarantine granularity (§5.3)** — is a chunk-wide quarantine acceptable, or must
   phase 2 add a fall-back that re-expands a failing chunk into per-row events for the
   retry pass?
2. **Mapper contract** — collapse rebuilds the nested payload so `server/mappers/` is
   untouched (recommended), or the mapper input contract changes to row-like objects
   (which is what `dt_map_derivation` already wants, but breaks `production_mapper` /
   `payloads_to_df` and every user mapper in the gitignored tree)? This is a **boundary
   contract** in substance even though it is not one of the four listed in my charter —
   the files are user-owned.
3. **The `LIMIT 20000` completion guard** — with chunk events this cap covers 20M rows.
   Lower it, or is that the backpressure round?
4. **The `dt_map_mapper` nested-payload finding in §1** — do you want that opened as its
   own item, and should it go to the dt-to-core lane?

No living documents were updated and no history entry was written: this round changed no
code. If ④ is approved, `architecture/event_driven_backend.md` and
`architecture/backend.md` are the rows `docs/process/DOC_OWNERSHIP.md` points at for
`server/database/database.py` and `server/chain_ingestion_worker.py`.
