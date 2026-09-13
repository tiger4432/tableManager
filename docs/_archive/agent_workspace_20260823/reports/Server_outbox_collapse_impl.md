# OUTBOX-④ Phase 2 — the collapse, implemented

**Every number below was produced on this workstation, which is a simulation.** Writes ran
through the real code path against a session-unique isolated PostgreSQL database
`assy_obx2_6f856759`, now **dropped**. Remaining `assy%` databases: `assy_manager` (14 GB,
owner `postgres`) and `assy_qa` (642 MB, owner `postgres`) — neither created by this round.

**No pytest was run** (a suite run is serialized by the lead). `server/database/crud.py` was
NOT edited and did not need to be. `client2/` and `server/map_alignment.py` untouched.
Nothing committed; `git add <path>` only.

Probes: `OBX2_measure.py`, `OBX2_consume.py`, `OBX2_reexpand.py`, `OBX2_drop.py` under the
session scratchpad.

---

## 1. What the product owner's direction changed, and what it confirmed

The direction — *the outbox carries only the trigger `row_id` and the table; the derivation
reads the main table, the way chain replay already does* — is the shape phase 1 proposed,
with one thing settled that phase 1 had left as an open question (mapper contract, Q2).

I did **not** invent a payload-rebuilding convention. `chain_replay._to_payloads`
(`server/chain_replay.py:185`) already synthesizes `{"row_id", "data": {col: {"value": v}}}`
by reading the trigger table's current contents, and `enrichment_backfill` does the same. The
new expander is that construction, extended with the envelope keys the live path carries
(`transaction_id` drives grouping, `source_name` drives the circular-loop filter). So the live
trigger path now derives the same way replay does, instead of a third format existing.

**How the two shapes coexist:** the user-owned mappers keep getting exactly what they got.
`server/mappers/production_mapper.py:11` (`payload.get("data", {})`) and
`server/mappers/utils.py:15` (`p.get("data", {})` then `cell_detail["value"]`) are a contract
this round cannot edit, and they are unedited. What moved is only where the values come from:
the row, not the event. Measured equality below (§3).

### The semantic change, named rather than discovered

| Case | Before (snapshot) | After (pointer) |
|---|---|---|
| Row updated twice quickly | each event derives its own point-in-time value | **both derive the final state** — idempotent, and the derived table never briefly holds a value the source no longer has. The chain no longer observes intermediate states of its trigger row. |
| Row **deleted** before consumption | the payload still carries it and derives from a row that is gone | **derives nothing — and is counted.** `expand_events` logs table, transaction, count and a sample of the unresolved ids at WARNING. |

The deleted-row answer **matches chain replay** rather than inventing: replay walks current
contents, so a deleted row is simply not in the page. The addition is that it is never silent.

---

## 2. Measured: before and after on the same input

dt_log-shaped table (16 columns), 20,000 rows, written through
`crud.apply_batch_updates` in 1,000-row chunks in both modes. Real `database_outbox` DDL,
all seven indexes, `VACUUM ANALYZE` before sizing.

| | per-row (today) | collapsed |
|---|---:|---:|
| outbox rows | 20,000 | **20** |
| **events per ingested row** | 1.0000 | **0.0010** |
| heap B / ingested row | 2,048.0 | 0.4 |
| index B / ingested row | 63.1 | 4.9 |
| **total B / ingested row** | **2,113.5** | **36.0** |
| extrapolated to 10,000,000 rows | 19.7 GiB | **343 MiB** |

**1,000× fewer rows, 58.6× fewer bytes.** (Phase 1 predicted 27.2 B/row from a synthetic
payload; the real path measures 36.0 B/row. The difference is the per-event fixed cost —
`event_uuid`, timestamps, seven index entries — amortized over 1,000 rows instead of the
payload alone. The prediction was optimistic by 32%; the conclusion is unchanged.)

**The framing to keep is the drain ceiling, not the size.** `OUTBOX_PURGE_CHUNK (1000) ×
OUTBOX_PURGE_MAX_CHUNKS (50)` per hourly cycle = **1,200,000 rows/day is the drain's sustained
state**, and above it the table has none. 10M ingested rows now produce 10,000 outbox rows —
**one fifth of a single purge cycle.** No purge knob was touched; the point is that at this
event rate they no longer need to be.

### The consumer-side cost — and the instrument error I nearly reported as a finding

The lead asked for numbers if the re-read costs more than it saves. **My first measurement said
it did, and my first measurement was wrong.** It timed `get_payload_dict` on already-loaded
events (149 ms) against the collapsed arm's load *and* expansion (2,045 ms) — the per-row arm's
JSONB decode happened inside `.all()`, outside the timer. Reported as-is, that is a 13.7×
regression that does not exist.

Re-measured with both arms including their own load, three repetitions, 20,000 rows:

| rep | per-row: load + decode 20,000 events | collapsed: load 20 events + re-read 20,000 rows | ratio |
|---|---:|---:|---:|
| 0 | 2,705.4 ms | 1,768.8 ms | 0.65× |
| 1 | 2,053.9 ms | 1,727.5 ms | 0.84× |
| 2 | 1,993.4 ms | 1,725.4 ms | 0.87× |

**The re-read is cheaper, not more expensive** — an indexed `row_id IN` fetch of 20 chunks
beats decoding 20,000 JSONB payloads, and it is also far more stable across repetitions. Phase
1 §5.5 flagged this as "a prediction, not a measurement"; it is now measured, and it holds.

---

## 3. Equality of the expanded payload with the one the producer would have written

Same 20,000 rows, both modes, compared after expansion:

- expanded rows == ingested rows: **True**
- column set equal to per-row: **True** (producer and expander share
  `event_constants.OUTBOX_PAYLOAD_EXCLUDED_COLUMNS`, so they cannot rebuild different sets)
- cell shape equal to per-row: **True**
  - expanded: `{'value': 'B_val_1_0', 'is_overwrite': False, 'updated_by': 'system'}`
  - per-row:  `{'value': 'A_val_1_0', 'updated_by': 'system', 'is_overwrite': False}`

---

## 4. Quarantine granularity — the ruling, implemented and exercised

**Re-expansion works. It did not need to be refused.** But it required one thing the ruling
did not name, and without it the re-expansion would have bought nothing:

🔴 **The worker's unit of failure is the transaction GROUP, not the event.** One poison row
fails the mapper for every event grouped with it. Re-expanding under the original
`transaction_id` puts all 1,000 rows back into one group where they fail together again. So
each re-expanded event gets **its own** `transaction_id` (`<tx>#row#<row_id>`), making each row
its own group — 999 succeed and the poison row is quarantined **alone**, which is exactly the
granularity the collapse was accused of losing.

**Placed at the quarantine boundary, not at the first failure.** The chunk is retried *as* a
chunk while `retry_count < 3`, so a transient failure (dead connection, lock) recovers without
ever paying per-row cost; re-expansion **replaces** quarantine rather than replacing retry.
This is the ruling's own principle — "you pay the per-row cost only where something actually
broke" — and a blip is not a broken row.

**Termination is structural**, not a counter: a re-expanded event carries `data` and no
`row_ids`, so `is_collapsed_payload` is False for it and it can never re-expand again.

Verified against real PostgreSQL through the real `process_pending_groups` with a mapper that
always fails (`OBX2_reexpand.py`):

```
control  per-row  : status=FAILED processed=True rows 20000->20000 (unchanged)
collapsed chunk   : 1000 rows, status=FAILED error_log.reexpanded_into=1000
                    outbox rows 20->1020
children          : 1000, distinct tx_ids 1000, collapsed-shape among children: {False}
child state       : {('PENDING', False, 0)}
child has values  : c01={'value': 'B_val_1_0', 'updated_by': 'system', 'is_overwrite': False}
child tx sample   : tx-B#row#019fd882-ffb6-7948-81ee-101523c0e05f
re-expand a child : 0  (terminates by construction)
```

The control arm is the point: the same code on a per-row event still quarantines exactly as it
always did, so the new branch is the collapsed one and not a change to everyone's retry
semantics.

**Two costs of the failure path, stated:** (a) the re-expanded groups run one mapper call and
one commit per row for that chunk; (b) the HOL guard (`blocked_targets`) means the poison row,
if it sorts first, defers its 999 siblings for that batch — they return next batch, and after
three batches the poison row is quarantined and the rest flow. Slower, bounded, terminating.

---

## 5. What was built

| File | Change |
|---|---|
| `server/event_constants.py` | **The shared contract symbols**: `OUTBOX_MODE_PER_ROW`/`_COLLAPSED`, `OUTBOX_COLLAPSE_CHUNK_ROWS`, `OUTBOX_GROUP_MAX_ROWS`, `OUTBOX_PAYLOAD_EXCLUDED_COLUMNS`, `is_collapsed_payload`, `payload_row_count`, `trim_events_to_row_budget`. |
| `server/database/context.py` | `request_outbox_mode` (default `"per_row"`) + `outbox_mode(mode)` context manager. |
| `server/database/database.py` | `auto_stage_database_outbox` accumulates row_ids per `(table, event_type)` in collapsed mode; new `stage_collapsed_event`; NOTIFY latch factored to `_notify_outbox_once` so both producers share it; `stage_event` now takes its excluded-column list from the shared frozenset. |
| `server/outbox_expand.py` | **NEW.** `expand_events` (pointer → the nested payload, chain-replay's construction), `load_rows_by_ids`, `reexpand_collapsed_event`. |
| `server/chain_ingestion_worker.py` | expansion before any rule runs; mapper hand-off iterates rows not events; chain's own derived writes opt into collapsed; re-expansion at the quarantine boundary; batch budget re-charged in rows. |
| `server/graph_materializer.py` | collapsed arm routes to the **existing** `resync_table(..., row_ids=[...])`; that function gained `updated_by` / `event_time` / `commit_chunks` so the incremental path does not lose provenance, event time, or its caller's transaction. |
| `server/graph_sync_worker.py` | batch budget re-charged in rows. |
| `server/parsers/directory_watcher.py` | **the one place that opts in** — around the whole file loop, restored in `finally`. |
| `server/tests/test_outbox_collapse.py` | **NEW**, 16 tests. |

### Consumers re-verified rather than trusted

- **Values needed** — `production_mapper.py:11`, `mappers/utils.py:15`: re-read, unedited, shape equality measured (§3).
- **Row-like wanted** — `dt_map_mapper` / `dt_map_derivation:580`: now gets rows re-read from the DB on the live path too.
- **"Rows in this set changed"** — `_group_target_tables:362`, circular filter `:380`, sweep `:832-853`, all three WS paths, `health.probe_outbox`, `/admin/outbox/{failed,retry-failed}`: **no change needed**, and I checked each. `event_type` deliberately stays CREATE/EDIT and `transaction_id`/`source_name`/`table_name` stay top-level, which is what makes that true. Health judges on **age**, not count, so its verdict is unaffected by the count changing meaning.
- **Graph** — `resync_table(..., row_ids=[...])` used, not duplicated.
- **`graph_sync_worker.build_queries_for_event`** (reads `payload["data"]`) is fed only by `create_light_event_mock` from ORM rows, never from the outbox — checked, unaffected.

### Constraints that outranked the size win

- **Transactional outbox preserved.** `row_id` is minted in Python (`crud._get_or_create_row`), so the id list is complete at `before_flush`; the chunk event is `session.add`-ed on the same session in the same flush, exactly as `stage_event` is. One transaction, one commit.
- **Undelivered-marker contract untouched.** `internal_event_client.py:135-142` and `chain_ingestion_worker.py:884-889` are unmodified; `processed_chain` / `status` / `broadcast_at` keep their meanings, so no shared symbol was needed there. (The collapse's own shared symbols *were* introduced for the same reason that contract is dangerous.)
- **Purge knobs untouched.**
- **DELETE never collapses** in either mode — a pointer cannot name a row that no longer exists.

### The batch budget — a change I had to make, flagged because it was not in the brief

`LIMIT 20000` (chain tx completion guard) and `GRAPH_BATCH_LIMIT = 1000` counted **events**.
While events were per-row that meant rows. After the collapse, left alone, one batch would pull
20,000 chunks = **20,000,000 rows** into a single mapper call — a 1,000× amplification of the
working set. `OUTBOX_GROUP_MAX_ROWS` re-charges the same budget in rows, keeping the batch the
size it was. **This is the old cap keeping its meaning, not a new knob**, and it is not the
backpressure round (phase 1 Q3 is still open and unanswered). Trimming keeps a **prefix**, so
the tail stays `processed_chain=False` and returns in the same order.

---

## 6. Tests written (not run)

`server/tests/test_outbox_collapse.py`, prefix `obxcol_` so it cannot collide with the user's
gitignored config. **Every test that scores the new behaviour runs the old one on the same
input** — the per-row arm is not decoration, it is the proof that the collapsed arm is what is
being measured:

- `test_default_mode_is_per_row` — pins `context.py`'s spelled-out literal to the constant.
- `test_before_and_after_on_the_same_input` — 5 rows → 5 events, then 1 event; the per-row arm's assertions ARE the pre-change behaviour.
- `test_events_per_ingested_row`, `test_chunk_cap_splits_a_huge_flush`, `test_delete_never_collapses`.
- `test_expanded_payload_matches_what_the_producer_would_have_written` — both modes, compared field by field including the column set.
- `test_expansion_is_load_bearing` — **the injection**: asserts the RAW collapsed payload fails the exact accessor the user-owned mappers use (`payload.get("data", {})` → `{}`), so the expansion cannot be green by accident.
- `test_per_row_events_pass_through_expansion_unchanged`.
- `test_a_row_deleted_before_consumption_derives_nothing_and_is_counted` — including the WARNING.
- `test_reexpansion_gives_every_row_its_own_group`, `test_third_failure_reexpands_instead_of_quarantining_the_chunk` (with a per-row **control arm**), `test_cheap_retries_come_first`.
- `test_batch_budget_is_charged_in_rows_not_events`, `test_row_count_survives_a_missing_count_field`.
- `test_graph_materializes_a_collapsed_event_the_same_as_a_per_row_one` — path equivalence across the collapse.

Three of these paths were additionally exercised against **real PostgreSQL** by the probes
(collapse, expansion equality, re-expansion), which is the evidence that does not depend on the
suite run.

---

## 7. Open items

1. 🔴 **`execute_custom_mapper` nested-payload finding — STATIC READ, NOT REPRODUCED LIVE.**
   `mappers/dt_map_mapper.py:200` hands nested payload dicts to `derive_cells`, whose accessor
   is `row.get(col)` (`dt_map_derivation.py:580`), so `payload.get("lot_id")` is `None` while
   the value sits at `payload["data"]["lot_id"]["value"]`. Statically this reads as "the live
   `dt_log` → `dt_map` trigger path derives nothing" while the correction path works because it
   re-reads ORM rows. **I did not reproduce it and did not touch it.**
   *What a live reproduction looks like:* ingest one `dt_log` row through the watcher with the
   `dt_log → dt_map` rule enabled and `is_batch` true; then compare the `dt_map` rows the live
   trigger produced against the rows `chain_replay.replay_rule` produces for the same rule on
   the same input. If the trigger path is broken, replay writes cells the live path left blank.
   Note this round **narrows** it but does not close it: the live path now hands the mapper a
   payload synthesized by re-reading the row — the same nested shape as before, so the accessor
   mismatch at `:200`/`:580` is unchanged. It argues for the design (the accessor wants a
   row-like object) without being fixed by it.
2. **Phase 1 Q3 (the `LIMIT 20000` completion guard) is still open.** This round preserved its
   meaning; it did not decide whether the value is right.
3. **Retroactive sweeps still stage per-row.** Phase 1 listed them as an opt-in candidate; I
   scoped this round to file ingestion and the chain's derived writes and left them on the safe
   default. They are the "reingest everything" path, so they are the next candidate.
4. **Dual-shape handling cannot be removed for `OUTBOX_RETENTION_DAYS` (7) after deploy** — old
   per-row events will still be in the table. Every branch added here handles both by design.
5. **Admin `/admin/outbox/failed` shows a chunk, not a row**, for a failed chunk that could not
   re-expand. Diagnostic degradation only; the `error_log.reexpanded_into` field says when it
   did re-expand.

---

## 8. QA round — six findings addressed (2026-08-07)

QA returned GO-WITH-FIXES. All six are fixed and **re-verified against real PostgreSQL** in a
second session-unique database `assy_obx2f_6f856759`, now **dropped** (remaining `assy%`:
`assy_manager`, `assy_qa`, both owner `postgres`). Probe: `OBX2_qafix.py`.

### HIGH 1 — the graph worker's budget came from the wrong constant

`OUTBOX_GROUP_MAX_ROWS` (20,000) is the **chain worker's** `LIMIT 20000` in rows. The graph
worker's pre-change cap was `GRAPH_BATCH_LIMIT = 1000` events = **1,000 rows**. Charging it
20,000 multiplied that batch by 20 — on the arm running `commit_chunks=False`. Fixed:
`graph_sync_worker` now trims to `GRAPH_BATCH_LIMIT` rows.

```
HIGH1 graph cap = 1000  chain cap = 20000  materializer chunk = 1000
HIGH1 graph keeps 1 event(s) = 1000 rows; chain keeps 20 = 20000 rows       PASS
```

**And C-7 is stated, not left reversed.** C-7 targets `resync_table`'s **full-table** mode.
With the corrected budget the collapsed arm holds at most `GRAPH_BATCH_LIMIT` = 1,000 rows =
**one `CHUNK_SIZE`** — the same amount the per-row arm has always held, since
`materialize_events` never committed mid-batch either. Deferring the commit is what keeps
"materialize + advance cursor" atomic, which is what makes a crash replay-safe. Because that
bound comes from a *caller's* discipline it is now **checked**: a batch exceeding one chunk on
this path gets a named warning instead of a silent multi-chunk transaction.

### HIGH 2 — collapsed materialization took the first event's identity

Fixed: the group key is `(table_name, updated_by, event_time)`.

```
HIGH2 fixture: events = 2  updated_by = ['chain_worker', 'watcher_ingest']  collapsed = True
HIGH2 edge updated_by per row: {'K0': 'watcher_ingest', 'K1': 'watcher_ingest',
                                'K2': 'chain_worker',   'K3': 'chain_worker'}   PASS
```

**And the net was proven to ring**, by injecting the old grouping on the same fixture:

```
INJECT old-grouping edge updated_by: {'K0': 'watcher_ingest', 'K1': 'watcher_ingest',
                                      'K2': 'watcher_ingest', 'K3': 'watcher_ingest'}
INJECT the net DISCRIMINATES: True
```

QA's criticism of the test was the sharper half of the finding and it is accepted verbatim:
`assert len(all_edges) > len(per_row_edges)` was **a liveness check wearing an equivalence
claim's name**. Both arms are now normalized to a shared alphabet (`type`, cell-layer
`source_name`, `updated_by`, **business key** — because `row_id`/`source_row_ref` differ
between the control table and the mirror by construction) and compared with `==`. A second
test, `test_two_collapsed_events_do_not_share_the_first_ones_identity`, uses **two** events
with two `updated_by` values: with one event, "first" and "each" are the same thing and the
defect is invisible.

### MED 3 — partial re-expansion committed alongside the quarantine

Fixed: every child is built **before** any `db.add`, and the add loop expunges on failure.
The caller commits regardless — that is the point, and it is what the probe reproduces:

```
MED3 raised=True  outbox 2->2   PASS      (a partial re-expansion writes nothing at all)
```

### MED 4 — the retry button re-expanded, unbounded

Fixed on both halves. `reexpand_collapsed_event` refuses a payload already carrying
`error_log.reexpanded_into`; `POST /admin/outbox/retry-failed` skips such parents and **says
so** (`skipped_reexpanded` in the response, and a message naming the `<tx>#row#` ids where the
rows went) rather than reporting a reset that would be a no-op at best.

```
MED4 first=2  second=0  children=2   PASS
```

### LOW — both

- `expand_events` is keyed on **`event_uuid`**, and the two chain-worker lookups are now
  **indexed** rather than `.get(..., ())` — a missing key means the expander and the loop
  disagree about the batch, and deriving nothing silently is exactly the failure to avoid.
  ```
  LOW1 keyed on event_uuid: True | re-fetched list resolves: True
  ```
- The collapsed-mode token is now scoped to **the single `apply_batch_updates` call**, not the
  enclosing block. That removes the whole class: no `await`, and no map-meta / enrichment hook,
  runs inside it.

### Docs

`event_driven_backend.md` §2.4's HIGH-1 bullet is rewritten (two workers, two caps, plus the
C-7 statement and the grouping key). The three owner-mandated documents QA named are now in
the diff: `architecture/PRIMITIVES.md` §6 (new primitive entry — the collapse, with the trap
list this round earned), `qa/FEATURE_CHECKLIST.md` §2.7 (six checks, including **"the human
path is NOT collapsed"** as an immediate NO-GO), and `spec/ONTOLOGY_GRAPH_SPEC.md` §5.1
(`resync_table`'s three new parameters and why each exists).

**One line of QA's message I am adopting as a rule**, since it is the lead's own correction:
*a re-derived limit must be checked against each consumer's own pre-change value, separately.*

---

## 9. Suite round — the two failures that were mine (2026-08-07)

Both fixed. Because I may not run pytest, I built a **standalone harness**
(`OBX2_harness.py`) that rebuilds conftest's `db_session` environment and calls each test
function directly with fixture shims (`monkeypatch`, `caplog`, `tmp_path`, `TestClient`). It
**reproduced the suite's two failures exactly** before the fixes and reports **21/21 passing**
after. No pytest, no database.

### 9.1 `test_a_row_deleted_before_consumption…` — a test bug, feature untouched

`r.message % r.args` re-applied args to a string the handler had **already formatted**.
Replaced with `r.getMessage()`, which renders msg+args exactly once. I grepped the file: this
was the only log-assertion in it, so there is no second instance of the pattern.

### 9.2 `test_graph_materializes_a_collapsed_event_the_same_as_a_per_row_one` — real, and the net caught it

**The control arm was not empty. I measured it after something had already destroyed it.**

Root cause, measured rather than reasoned (`OBX2_graph_why.py`):

```
AFTER control arm (per-row): 3 edge row(s)
    upsert-key=(from=4, type=OBXCOL_ON_EQP, to=1, source=DT_LOG_20260807.csv)  ref=obxcol_src:019f…
    …
  _edges_of(obxcol_src) = 3

AFTER collapsed arm (mirror): 3 edge row(s)
    upsert-key=(from=4, type=OBXCOL_ON_EQP, to=1, source=DT_LOG_20260807.csv)  ref=obxcol_mirror:019f…
    …
  _edges_of(obxcol_src)    = 0        <-- the control arm's rows, overwritten
  _edges_of(obxcol_mirror) = 3
```

My fixture gives the two tables the **same node identity** (`ObxcolRow` keyed on `key_id`, same
business keys) and the **same ingest `source_name`**, so both arms produce the same edge under
the store's declared unique key `(from_node, type, to_node, source_name)`. The mirror's write
therefore **replaces** the control's rows. That is correct idempotent MERGE behaviour of the
edge store — the defect was entirely in *when* my test measured.

**Not fixed by relaxing anything.** Each arm is now measured while it is the current state, and
the collision is asserted rather than left as a comment (`len(all_edges) == len(per_row_norm)`
and `_edges_of("obxcol_src") == set()` after the mirror runs), so a future fixture change that
made the arms occupy different edges fails loudly instead of silently invalidating the
ordering. The equality assertion is unchanged and still an equality.

### 9.3 The claim the suite actually exposed — closed

Your distinction was the right one: a probe proving the **fix** is not proof that the
**committed test** would catch a regression. So I injected the defects into the path the tests
call and confirmed each net rings (`OBX2_inject.py`):

| | equivalence test (1 event) | two-event identity test |
|---|---|---|
| baseline | PASS | PASS |
| **`first-identity-wins`** (the HIGH-2 defect) | PASS | **RED** — *"the second collapsed event's rows must carry their OWN updated_by, not the first event's"* |
| **identity dropped to `graph_resync`** | **RED** — *"collapsed and per-row materialization must agree on … provenance, updated_by …"* | PASS |

Each net rings on exactly the defect it owns, and neither on the other. Note the top-right
cell: the single-event equivalence test **cannot** catch HIGH 2 — with one event, "first" and
"each" are the same thing. That is the concrete demonstration that the two-event case you asked
for was mandatory, not belt-and-braces.

Open item 7-1 (`dt_map_mapper:200`) remains a static read, unclosed.

---

## 10. Proposed lessons (for the lead to accept into `agent_workspace/memory/server-pm.md`)

- **함정**: 두 팔의 소비 비용을 비교하면서 **한쪽의 디코드를 타이머 밖에 둔다.** ORM `.all()`이 JSONB를 이미 풀어 놓으므로, 그 뒤에 `get_payload_dict`만 재면 149 ms가 나오고 상대 팔은 로드까지 포함해 2,045 ms가 나온다 → **「재읽기가 13.7배 비싸다」는 없는 결함**. 실제로는 로드를 양쪽에 포함하면 0.65~0.87배로 **재읽기가 더 싸다.**
  **올바른 방법**: 비교 팔은 **같은 경계**에서 시작·종료한다(로드 포함 여부를 먼저 선언). 그리고 **한쪽이 다른 쪽보다 10배 이상 빠르면 그 팔이 일을 덜 하고 있는지부터 본다.**
- **함정**: 재시도·격리의 입도를 **이벤트 단위**로 생각한다. 이 워커의 실패 단위는 **트랜잭션 그룹**이다 — 같은 `transaction_id`로 재확장하면 1,000행이 다시 한 그룹에서 함께 실패해 재확장이 **아무것도 사지 못한다**.
  **올바른 방법**: 입도를 잘게 만들려면 **그룹 키를 갈라야** 한다(`<tx>#row#<row_id>`). 그리고 재확장 산출물이 **다시 확장될 수 없는 모양**인지 구조로 확인한다(카운터가 아니라 형태로 종료).
- **함정**: 상한 상수가 **무엇을 세는지** 확인하지 않고 이벤트 모양만 바꾼다. `LIMIT 20000`·`GRAPH_BATCH_LIMIT`은 이벤트를 셌고, 이벤트가 1,000행이 되는 순간 같은 상수가 **작업집합을 1,000배**로 키운다.
  **올바른 방법**: 이벤트의 **단위 무게**를 바꾸는 변경은 그 이벤트를 세는 **모든 상한을 함께 재유도**한다(값이 아니라 **의미**를 보존).
  🔴 **그리고 재유도는 소비자마다 따로 한다 (QA 2026-08-07, 총괄 공동 판정).** 나는 상한 **하나**를 만들어 소비자 **둘**에 먹였고, 그 상수는 체인 워커의 20,000행이었다. 그래프 워커의 변경 전 값은 1,000행이라 **그 배치를 20배로** 키웠고, 하필 커밋 없이 도는 팔이었다. **재유도된 상한은 각 소비자의 자기 변경 전 값과 대조**한다 — 「의미 보존」은 소비자 수만큼 증명해야 하는 문장이다.
- **함정**: 두 팔을 **같은 저장소 자리에 쓰게 해 놓고**, 한 팔을 다른 팔이 지나간 **뒤에** 잰다. 내 그래프 동등성 테스트는 두 테이블에 같은 노드 신원·같은 `source_name`을 줬고, 엣지 유니크 키가 `(from, type, to, source_name)`이라 뒤 팔의 UPSERT가 앞 팔의 행을 **덮어썼다**. 통제군은 비어 있던 게 아니라 **내가 재기 전에 지워져 있었다** — 그리고 그 동등성은 「빈 집합 == 빈 집합」이 될 뻔했다.
  **올바른 방법**: 각 팔은 **자기가 현재 상태인 순간에** 잰다. 그리고 겹침을 **주석이 아니라 단언으로** 적어라(행 수·덮인 쪽이 비었음) — 픽스처가 바뀌어 두 팔이 갈리면 조용히 무의미해지는 대신 빨개진다.
- **함정**: **초록을 「그물이 있다」로 읽는다.** 실기 프로브로 *수리*를 증명한 것과, *커밋될 테스트가 회귀를 잡는다*는 것은 **다른 주장**이다(총괄 판정 2026-08-07). 실제로 내 단일 이벤트 동등성 테스트는 HIGH-2 결함을 **주입해도 통과**했다 — 이벤트가 하나면 「첫」과 「각각」이 같은 뜻이기 때문이다.
  **올바른 방법**: 그물마다 **자기가 잡아야 할 결함을 주입해 빨개지는 것까지** 확인하고, **어느 그물이 어느 결함을 잡는지 표로** 남긴다(둘 다 잡는 그물이 없으면 그물이 부족한 것이다). pytest를 못 돌리는 라운드라면 **conftest 환경을 재현하는 하네스**를 만들어서라도 확인한다 — 「돌려보지 않은 테스트」를 납품하지 않는다.
- **함정**: 여러 이벤트를 한 배치로 묶으면서 **키에 신원을 빼먹는다.** 테이블만으로 묶고 **첫** 이벤트의 `updated_by`/시각을 쓰면 뒤 이벤트 행들이 앞 이벤트 신원으로 적재되는데, 받는 쪽은 **멀쩡한 문자열**을 받으므로 아무것도 실패하지 않는다.
  **올바른 방법**: 묶음 키에 **행마다 달라질 수 있는 필드를 전부** 넣는다. 그리고 🔴 **회귀 그물은 이벤트가 둘이어야 한다** — 하나면 「첫」과 「각각」이 같은 뜻이라 결함 축이 죽는다. (내 그물은 이벤트 하나였고, 게다가 동등성 주장에 `>`를 썼다: **`>`는 생존 확인이지 동등성이 아니다.**)
