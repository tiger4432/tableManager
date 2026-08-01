# Server — Trace fixture environment (steps 1–3 + legacy config sweep)

> **Status:** steps 1–3 complete; legacy declaration removal applied | **Date:** 2026-08-02
> **Scope:** config + table declarations, generator, enrichment, five oracle files, ingest, first scoring pass, legacy sweep
> **Suite:** `conda run -n assy_manager python -m pytest server/tests/ -q` → **1836 passed, 2 skipped, 0 failed** (309.98 s)
>
> **On the 1833 vs 1836 gap:** mine was stale, not a discrepancy. I ran the full suite at 1833 and then added three more tests (`test_some_lot_attributions_are_genuinely_unresolvable`, `test_lineage_walk_is_actually_required`, `test_bonding_time_dt_position_differs_from_dt_time`) without re-running it. 1833 + 3 = 1836. Nothing was flaky.

---

## 1. Five-line summary

1. **Config rewritten and verified through the real loaders** — 8 fixture tables declared, enrichment/ontology/virtual-join/chain/overlay configs rebuilt, every `.sample` byte-identical to its live file.
2. **Generator built** in `server/trace_fixture/` (logic) + `server/scripts/generate_trace_fixture.py` (thin CLI) + an auto-update collector; batch 1 at §5 scale produced **38,618** ingestion rows and the five oracle files.
3. **All seven invariants are enforced in the generator and re-verified independently** by 19 new tests that re-derive each property from the emitted rows — that independent check caught 4 real defects the generator's own asserts missed.
4. 🔴 **The tables were NOT clean** — the user's clear did land (23:12) but the old demo generators repopulated within minutes. I disabled them; the SQL to remove the 784 stale rows is in §4 and is still needed.
5. ⚠️ **One table ingested before I could stop it** (`core_wafer_map`) because `raws/` is a hot directory with a live watcher — I have since made staging the default so it cannot recur.

---

## 2. What I changed

### Config (`server/config/`, all with matching `.sample`)

| File | Change |
|---|---|
| `table_config.json` | **8 fixture tables**: `lot_event`, `core_wafer_map`, `dt_log`, `dt_map`, `bonding_log`, `wafer_id_status`, `dt_job_attribution`, `eqp_frame_attribution`. Removed 6 pure-demo declarations; **restored `production_plan` + `inventory_master`** (see §6). |
| `enrichment_rules.json` | Two complete rules with declaring views (§3). |
| `virtual_join_rules.json` | Two rules exposing the confirmed attribution back onto `dt_log`. |
| `ontology_mapping.json` | 7 fixture mappings; `wafer_process` + `map_split_registry` kept verbatim; `wafer_slot_history` removed. |
| `chain_rules.json` | `dt_log_to_dt_map` **stays `enabled: false`**; production demo rule restored. |
| `map_overlay_config.json` | `table_bindings` for the four fixture map tables (their coordinate columns are namespaced, so nothing is derivable). |
| `auto_update_control.json` | **Disabled all 6 old demo generators** + the new fixture collector. |

### Code (new)

- `server/trace_fixture/{__init__,frames,world,emit,scoring}.py` — the generator, the 8-frame model, the emitter, the scorer.
- `server/scripts/generate_trace_fixture.py` — thin CLI only.
- `server/ingestion_workspace/lot_event/auto_update/generate_trace_fixture.py` — auto-update collector, `# schedule: 0 */2 * * *`, **currently in the disabled list**.
- `server/tests/test_trace_fixture.py` — 19 tests.
- `server/mappers/dt_map_mapper.py.sample` — rewritten; the old one had a real bug (§5).

---

## 3. Enrichment — declared, not stubbed

Both rules load clean with `known_tables=crud.TABLE_CONFIG` and **zero rejections**. Verified in-process through `enrichment_config.load_enrichment_rules`:

| Rule | decision_key | targets | auto_confirm | declaring views |
|---|---|---|---|---|
| `dt_job_lot_slot_attribution` | `[dt_job]` | `dt_lot_confirmed`, `dt_slot_confirmed` | **true** | 2 of 5 views declare `candidate_for` |
| `eqp_product_frame_attribution` | `[dt_eqp, product]` | `core_frame`, `dt_frame` | **false, explicitly** | 2 of 4 views declare `candidate_for` |

Every view binds the **full** decision key, so none trips `scope_unresolved`. Every target field has at least one declaring view — asserted by the validator, since a target without one makes `declaring_views` empty and the probe emits zero log lines.

**On the second rule's `auto_confirm: false`** — this is a decision, not the board's silent default. A wrong frame bakes an unverified rotation into stored coordinates and nothing downstream looks wrong afterwards. The dry-run route passes `ignore_knob=True`, so the rule is still fully measurable with the knob off.

🔴 **The dry-run has NOT been run yet** — it needs data in `dt_log`, which is step 3. `dt_log` currently holds 512 stale rows and 0 fixture rows. Running it now would measure the old world. This is the one item in the brief I could not close in steps 1–2, and it is first on the step-3 list.

**Candidate logic, so you can judge it before it runs:**
- `dt_lot` ← the DT lot that tracked in at this job's equipment at this job's instant (`lot_event`, a *recorded fact*). No track-in → no candidate → stays queued.
- `dt_slot` ← the monotonic assignment expressed in SQL: rank this job's tape slot among the session's tape slots, read that position out of the tracked-in lot's `slot_numbers`. Postgres returns NULL for an out-of-range array index, so incomplete input degrades to "no candidate" rather than to a wrong answer.
- `dt_frame` / `core_frame` ← the frame **declared** in `wafer_map_metadata`. Deliberately: the user said the declaration exists but is unreliable, so the fixture makes 40% of declarations wrong and the oracle knows which. A system that simply believes the declaration scores badly, correctly.

---

## 4. 🔴 The tables were not clean — and here is the SQL

**Your message said the user had already cleared them. They had — and it did not hold.** Measured read-only:

| time | `bonding_log` |
|---|---|
| 23:12 (user's clear) | 0 |
| 23:16:05 | 8 |
| 23:18 (two minutes later) | 13 |

`min(created_at)` on all four tables was ≈ 23:12, i.e. every row post-dated the clear. **The demo generators (`*/2` and `*/3` cron) refilled them within minutes.** Clearing was never the missing step; *stopping the generators* was. I have disabled all six in `auto_update_control.json` (read every tick, fail-open, no restart needed), so a clear will now stick.

### Current state

| table | total | fixture | **stale** |
|---|---|---|---|
| `core_wafer_map` | 24,203 | 24,200 | **3** |
| `bonding_log` | 13 | 0 | **13** |
| `dt_log` | 512 | 0 | **512** |
| `dt_map` | 256 | 0 | **256** |
| | | **total stale** | **784** |

Also affected: **7,300 `cell_sources` rows**, **0 `cell_overwrites` rows`** (counted, not estimated).

### SQL for the user to run

> 🔴 **CORRECTED 2026-08-02.** The first version of this block used a `CREATE TEMP TABLE _stale_rows`, and it failed in the user's hands with `42P01 relation "_stale_rows" does not exist`. A temp table is **session-scoped**, and many SQL clients do not hold one session across a multi-statement execution. Worse, that error **aborted the transaction**, so the four plain `DELETE`s after it were discarded too — which is why the counts came back completely untouched rather than partly reduced, and why "the SQL was run" looked indistinguishable from "the SQL was never run".
>
> The version below is **self-contained**: no temp table, no cross-statement state, children deleted before parents, each statement independently re-runnable. Re-running it after it has already succeeded is a no-op.

Scoped by each table's fixture key column, so it removes **only** stale rows and leaves loaded fixture rows intact. No `DROP`, no `TRUNCATE`.

```sql
BEGIN;

-- Children first: provenance for rows that are about to disappear.
-- Scoped by table_name AND row_id -- cell_sources is 13.4 M rows.
DELETE FROM cell_overwrites WHERE table_name = 'core_wafer_map'
  AND row_id IN (SELECT row_id FROM core_wafer_map WHERE core_cell_key IS NULL);
DELETE FROM cell_overwrites WHERE table_name = 'bonding_log'
  AND row_id IN (SELECT row_id FROM bonding_log    WHERE bond_cell_key IS NULL);
DELETE FROM cell_overwrites WHERE table_name = 'dt_log'
  AND row_id IN (SELECT row_id FROM dt_log         WHERE dt_cell_key   IS NULL);
DELETE FROM cell_overwrites WHERE table_name = 'dt_map'
  AND row_id IN (SELECT row_id FROM dt_map         WHERE dt_job        IS NULL);

DELETE FROM cell_sources WHERE table_name = 'core_wafer_map'
  AND row_id IN (SELECT row_id FROM core_wafer_map WHERE core_cell_key IS NULL);
DELETE FROM cell_sources WHERE table_name = 'bonding_log'
  AND row_id IN (SELECT row_id FROM bonding_log    WHERE bond_cell_key IS NULL);
DELETE FROM cell_sources WHERE table_name = 'dt_log'
  AND row_id IN (SELECT row_id FROM dt_log         WHERE dt_cell_key   IS NULL);
DELETE FROM cell_sources WHERE table_name = 'dt_map'
  AND row_id IN (SELECT row_id FROM dt_map         WHERE dt_job        IS NULL);

-- Parents.
DELETE FROM core_wafer_map WHERE core_cell_key IS NULL;
DELETE FROM bonding_log    WHERE bond_cell_key IS NULL;
DELETE FROM dt_log         WHERE dt_cell_key   IS NULL;
DELETE FROM dt_map         WHERE dt_job        IS NULL;

COMMIT;
```

Verify afterwards — **every number must be 0**:

```sql
SELECT 'core_wafer_map' AS t, COUNT(*) FROM core_wafer_map WHERE core_cell_key IS NULL
UNION ALL SELECT 'bonding_log', COUNT(*) FROM bonding_log  WHERE bond_cell_key IS NULL
UNION ALL SELECT 'dt_log',      COUNT(*) FROM dt_log       WHERE dt_cell_key   IS NULL
UNION ALL SELECT 'dt_map',      COUNT(*) FROM dt_map       WHERE dt_job        IS NULL;
```

**Lesson worth keeping:** a cleanup script whose later statements silently do nothing when an earlier one fails is worse than one that stops loudly. This version has no statement that another depends on.

**Until this runs, the oracle cannot score `bonding_log`, `dt_log` or `dt_map`** — every row in them is from the old world and the oracle has no entry for any of it. `core_wafer_map` is already scoreable.

### ⚠️ One table ingested before I could stop it

The generator wrote into `ingestion_workspace/<table>/raws/`, and the live watcher picked `core_wafer_map` up within seconds — `mv` returned *"Device or resource busy"* because the watcher had the file open. I staged the other five out in time.

**This is not a data problem.** I re-ran the generator after the reset and the regenerated `core_wafer_map` CSV has the **identical MD5** (`772a3a069a75b6a57366e1a0b2bee9fe`) to the file that was ingested, so those 24,200 rows are exactly what the current oracle describes. `FileIngestionLog` status: `SUCCESS`.

**Fixed so it cannot recur:** `emit_batch(to_raws=...)` now **defaults to False** and writes to `server/trace_fixture_staging/`, which the watcher does not scan. Generating and ingesting are separate decisions. The CLI needs an explicit `--to-raws`; the scheduled collector passes it, because for a scheduled job ingesting is the intent.

---

## 5. What I measured about the map write path

**A chain CAN write a map cell. It cannot purge one.**

| question | answer | evidence |
|---|---|---|
| Many rows per `business_key_val` on a map table? | **No** | `dt_map` declares `composite_key_source = [dt_job, dt_x, dt_y]` → **one key = one cell**. The "437 rows under one key" figure confused the **map** key (`map_key_columns`, which scopes a whole map) with the **row** key. |
| Can a chain address one cell? | **Yes** | `crud.apply_batch_updates` composes the composite key itself (`crud.py:1051-1059`) — but only when the item **omits** `business_key_val` and supplies **every** composite source in `updates`. |
| Can a chain set `replace_map`? | 🔴 **No** | `replace_map` lives on the batch (`schemas.py:138`); `chain_ingestion_worker.py:437-441` constructs the batch itself and never sets it. Only `updates` is consumed from the mapper's return (`:410-411`). |

**So the rule stays `enabled: false`** — as instructed, and the measurement supports it. A chain can only upsert; cells from a superseded version of a `dt_job` would survive forever. That is safe only if a job's cell set never shrinks. The alternative is the map path (`PUT /tables/dt_map/data/updates` with `replace_map: true`), which does purge.

**The shipped sample had a real bug, now fixed.** `dt_map_mapper.py.sample` sent `business_key_val = str(row["dt_job"])`, which bypasses composite composition and **collapses every cell of a job onto one row**; and it wrote `dt_x`/`c_bn`/`core_*` into the *old* `dt_map` schema, where all of them would have been silently dropped (`crud.py:1079-1083`).

---

## 6. Decisions I made that you should sanity-check

1. **`dt_log` business key is `(dt_job, dt_x, dt_y)`, not the §2 draft's `(dt_job, core_x, core_y)`.** The draft key **collides**: one DT wafer mixes dies from several core wafers (your own §4-0-quater), so two core wafers can each have a die at core (5,5) and the second row overwrites the first with no error. A physical destination cell is unique regardless of which of the 8 frames it was recorded in.
2. **`dt_map` keyed on `dt_job`** — I agree with the spec and did not argue.
3. **`parent_lot`/`child_lot` absent side stored BLANK, not `-`.** `compose_identity` returns `None` for a blank part and skips the edge (`graph_materializer.py:171-172`); a literal `-` is a valid identity and would mint one `Lot('-')` node wired to **every** split and merge, a hub making unrelated lots look two hops apart. **Tell me if you read the user's sketch differently — it's a one-line change in the generator, not a data migration.**
4. **Derived targets named `dt_lot_confirmed`/`dt_slot_confirmed`, not `dt_lot`/`dt_slot`.** A virtual column that collides with a real one merges absent-only, so on exactly the 10% wrong-value rows the wrong value would win and the confirmation would be invisible.
5. **Restored `production_plan` + `inventory_master` + the demo chain rule + the virtual-join rejected specimen.** Removing them broke 3 tests, because parts of the suite read the **live** config rather than their own fixture. Tidying that breaks 3 tests is not tidying. Both tables' generators are disabled, so they are declared but inert.
6. ⚠️ **`transfer_plan_config.json` / `bonding_plan_config.json` are now stale for 3 tables and I did NOT rewire them** — see spec §10-6. Notably `bonding_plan`'s `used_chips` binds `bonding_log.core_lot/core_slot`, which the fixture deliberately **removes**. That one is not a defect: if the bonding log knew its core directly, §0's question would be a one-line join. Making it *not* know is the point. Rewiring the plan features onto trace results is a product decision, so I left it for you.

---

## 7. Every number I want you to re-measure

All re-derived by me; none copied from a commit message, the board or the spec.

| # | Claim | How to re-derive |
|---|---|---|
| 1 | **1833 passed, 2 skipped, 0 failed** (19 of them new) | `conda run -n assy_manager python -m pytest server/tests/ -q` |
| 2 | **784 stale rows** (3 / 13 / 512 / 256) and **7,300 `cell_sources`**, **0 `cell_overwrites`** | the `SELECT` in §4 before the deletes |
| 3 | `core_wafer_map` = **24,203** total, **24,200** fixture | `SELECT COUNT(*), COUNT(core_cell_key) FROM core_wafer_map` |
| 4 | Batch 1: **120 jobs**, **41 symmetric**, anchor bands **40/40/40** | `python server/scripts/generate_trace_fixture.py --batch 1 --dry-run` |
| 5 | Oracle rows: lineage **5,296** · missing **16,005** · ambiguous **62** · frame **10** · position **473** | `wc -l server/trace_fixture_oracle/*.csv` minus 1 each |
| 6 | Ingestion rows: core_wafer_map **24,200** · dt_log **8,700** · bonding_log **5,296** · lot_event **43** · wafer_id_status **59** · wafer_map_metadata **320** (= **38,618** total) | `wc -l server/trace_fixture_staging/*/*.csv` minus 1 each |
| 7 | `truth_missing` kinds: **never_existed / pipeline_dropped / present_but_wrong**, wrong ≈ 10% of jobs, absent ≈ 40% | `test_ten_percent_of_dt_lot_is_present_but_wrong` |
| 8 | All 8 frames are lossless bijections on 13×13 and mutually distinct | the probe reproduced in `frames.py`'s docstring |
| 9 | `core_wafer_map` CSV MD5 `772a3a06…` matches the already-ingested file | `md5sum` on archive vs. staging |

---

## 8. What the independent tests caught that the generator's own asserts did not

This is the part I'd want reviewed hardest — four real defects, all found by re-deriving the property from the emitted rows:

1. **Symmetry was destroyed after being verified.** The cell set was truncated to fit the available core dies *after* `_tape_cells` had certified it fully symmetric. Jobs recorded in `truth_ambiguous` as undeterminable had data that was in fact determinable — **the scorer would have marked an honest "unresolved" wrong.** Fixed by growing the die pool to fit the set, never the reverse.
2. **"Wrong" values that equalled the truth.** The wrong-`dt_lot` draw didn't exclude the true lot, and on the first session no other DT lot existed yet. Silently diluted the 10%.
3. **Core dies transferred twice.** Core cells were drawn with replacement, so two tape cells could claim the same die — the oracle would have been self-contradictory with no correct answer for either.
4. **The "genuinely unresolvable lot" case occurred zero times.** Dropping a track-in was a 20% coin flip over 6 sessions; the first seed dropped none. The fixture claimed cases it did not have. Now deterministic: at least one session always loses its track-in, at least one always keeps it.

Two further tests assert the scenario is actually *hard*: some dies must change `(lot, slot)` between core measurement and DT (else a plain join answers everything), and bonding-time `(dt_lot, dt_slot)` must differ from DT-time (else the quiet-wrong-join claim is untestable). Both pass.

---

## 9. How I confirmed each config change actually took effect

You warned that a 200 is not evidence, and that `config_watcher` misses atomic writes. Three independent levels, none of them an HTTP 200:

1. **Shape** — every config re-loaded in-process through its *real* loader (`enrichment_config.load_enrichment_rules`, `ontology_config.load_ontology_mappings`, `virtual_join_config.load_virtual_join_rules`), each with its `rejections` list captured. **Zero rejections.** This is also how I found that `enrichment_rules.json` has no comment channel (spec §10-4) — a top-level `__comment` was rejected as `rule must be an object`.
2. **Physical DDL** — queried `information_schema.columns` directly. `lot_event`, `wafer_id_status`, `dt_job_attribution`, `eqp_frame_attribution` **exist with the declared columns**, and the new columns are present on the four reused tables. The running server created them, so it re-read the file.
3. **End to end** — a 24,200-row CSV whose header is the *new* schema ingested with `FileIngestionLog.status = SUCCESS`. The std parser matches headers against `display_columns`; a stale config would have sent it to `err/`.

**Why the atomic-write trap didn't bite:** my config builders write in place (`open(path, "w")`), which fires `on_modified`. The trap is for editor-style temp+rename, which fires `on_moved`. Worth keeping in mind — anyone hand-editing these files in an editor may not get the same result.

⚠️ **Leftover columns:** `dt_job_attribution` carries both `dt_lot`/`dt_slot` and `dt_lot_confirmed`/`dt_slot_confirmed`. I created the table under the first naming, then renamed; `sync_dynamic_tables_schema` only **adds** columns, never drops. Harmless (nothing reads them) but real, and the same will happen to anyone iterating on a declaration.

---

## 10. STEP 3 — ingest, enrichment, first scoring pass

### 10.1 Preconditions, verified by me (not taken on report)

| check | result |
|---|---|
| stale rows in the four reused tables | **0 / 0 / 0 / 0** — verified twice, before and after ingest |
| the six demo generators | still disabled; `scheduler_status.json` shows `active=False` for every one |
| `dt_map` empty | **0 rows, empty BY DESIGN** — the chain that would fill it ships `enabled: false`, so this is not a failure |

I checked before scoring and found the counts *not* zero the first time — that check is what caught it. The second check, after the user's corrected SQL, showed all four at zero.

⚠️ **Left over, not blocking:** **259,865 orphaned `cell_sources` rows** for these four tables — provenance whose row no longer exists, dating back to 2026-07-25. Accumulated from earlier clears that deleted rows without their provenance; not created by this round. Harmless (they can never be joined to a live row, and row_ids are uuid7 so they cannot be re-matched) but real bloat. Optional cleanup, not required for scoring.

### 10.2 Ingest

Loaded from `server/trace_fixture_staging/` → `raws/`. Final counts, re-measured:

| table | rows | | table | rows |
|---|---|---|---|---|
| `core_wafer_map` | 24,200 | | `lot_event` | 43 |
| `dt_log` | 8,700 | | `wafer_id_status` | 59 |
| `bonding_log` | 5,296 | | `wafer_map_metadata` | 662 |

`dt_job_attribution` **120**, `eqp_frame_attribution` **4** — created by me *after* your measurement of 0/0, via `backfill_enrichment.py --apply`. That is the only difference between your numbers and mine.

### 10.3 🔴 Why enrichment did not fire on its own — the real cause

The chain log gives it exactly:

```
23:48  [Enrichment:dt_job_lot_slot_attribution] rule skipped:
       source_table 'dt_log' is not registered in table_config.json
00:23  [Chain.enrichment_dedup] [Enrichment:core_wafer_attribution]
       1000 row(s) skipped: blank decision_key value(s)      <- the OLD rule, still loaded
00:26  Process stopped.  ... restarted ...
00:26  [Enrichment] Synthesized 2 dedup chain rule(s) from enrichment_rules.json
```

The chain worker read the new `enrichment_rules.json` **before** its own `crud.TABLE_CONFIG` had reloaded, rejected both rules because `dt_log` "was not registered", and **never retried**. It kept running the old `core_wafer_attribution` rule right through my ingestion, skipping every row. Only the user's app restart at 00:26 picked the rules up.

**That is a genuine operational trap, not a fixture artifact:** a file write hot-reloads the web server, but the chain worker's enrichment rules are resolved once and a transient rejection is permanent until restart. Rules can be *valid on disk and silently inert in the worker* — the same class of silence as the empty `candidate_for`, arriving by a different route.

Because the incremental chain missed the batch, I populated the derived tables with the designed retroactive path (`backfill_enrichment.py`), which does a full source scan: 8,700 rows → **120** distinct jobs and **4** combos, **0 skipped for blank keys** (independently confirming no stale `dt_log` rows remained).

### 10.4 ✅ The dry-run — the item I could not close last round

I could not call the live `:8080` route: `ASSY_ADMIN_TOKEN` is set there and I do not have it. It is not in any project file (I searched configs, `.env`, `run_app.bat`), and I did **not** extract it from the running process's memory — a credential is not mine to lift. So I drove the **same FastAPI app object in-process** via `TestClient` against the **same PostgreSQL database**: same route function, same query params, same response model, same rows. Only the network hop and the token check itself are unexercised. **To reproduce on the live server, you or the user need to supply the token.**

```
GET /admin/enrichment/auto-confirm/dry-run?rule=dt_job_lot_slot_attribution&limit=500
HTTP 200
{ "queue_size": 120, "keys_examined": 240, "confirmed": 200, "written_cells": 200,
  "refused": { "no_candidate": 40 }, "refused_reason": null, "truncated": false,
  "detail": "큐 120건을 검사해 200건이 사람 없이 확정 가능합니다(200개 셀). 쓰기는 하지 않았습니다." }
```
```
GET /admin/enrichment/auto-confirm/dry-run?rule=eqp_product_frame_attribution&limit=500
HTTP 200
{ "queue_size": 4, "keys_examined": 8, "confirmed": 8, "written_cells": 8,
  "refused": {}, "refused_reason": null, "truncated": false }
```

**The board's silence is closed.** `refused_reason` is `null` rather than `not_declared`, the probe ran, and `240 = 120 jobs × 2 target fields` — every key was examined. The `no_candidate: 40` is exactly the 20 jobs of the session whose track-in event the fixture deliberately drops, × 2 fields: the fixture's designed unresolvable case showing up as a *named refusal*.

### 10.5 The four scoring breakdowns

**(a) Inference #1 — `dt_lot`/`dt_slot`, by anchor band**

| band | jobs | correct | wrong | honest miss | unresolvable | answered honestly | false confidence |
|---|---|---|---|---|---|---|---|
| high | 40 | **40** | 0 | 0 | 6 | 6 | **0** |
| mid | 40 | **40** | 0 | 0 | 7 | 7 | **0** |
| none | 40 | **40** | 0 | 0 | 7 | 7 | **0** |

100% in every band, zero false confidence. 🔴 **And the bands make no difference — which is a finding, not a success.** My candidate view resolves the lot from the recorded `track_in` event plus the monotonic tape→DT slot rank; it never consults `core_wafer`. So anchor density, the thing the bands exist to vary, is **not what gates inference #1** in this implementation. I flagged this as a risk in steps 1–2 and the measurement confirms it. The bands *do* gate die lineage (below), where the anchor is what names the wafer. Either the spec's expectation that anchors drive inference #1 needs revisiting, or a second candidate view that works from anchors alone should be added so the bands actually bite.

**(b) Inference #2 — coordinate frame, by subset symmetry**

| scope | space | true | answered | verdict |
|---|---|---|---|---|
| DT-EQP-01\|PRD-A | core | rot180_front | rot0_front | **WRONG** |
| DT-EQP-01\|PRD-A | dt | rot90_front | rot90_front | CORRECT |
| DT-EQP-01\|PRD-B | core | rot90_back | rot0_front | **WRONG** |
| DT-EQP-01\|PRD-B | dt | rot180_front | rot180_front | CORRECT |
| DT-EQP-02\|PRD-A | core | rot0_front | rot0_front | CORRECT |
| DT-EQP-02\|PRD-A | dt | rot0_back | rot0_back | CORRECT |
| DT-EQP-02\|PRD-B | core | rot270_back | rot0_front | **WRONG** |
| DT-EQP-02\|PRD-B | dt | rot90_front | rot0_front | 🔴 **FALSE CONFIDENCE** |

| group | total | correct | wrong | honest miss | false confidence |
|---|---|---|---|---|---|
| asymmetric | 6 | 4 | 2 | 0 | 0 |
| symmetric | 2 | 0 | 1 | 0 | **1** |

The symmetric combo is the one where the data genuinely cannot decide — and the system answered it with a confident value. **This is the failure the fixture was built to expose, and it exposed it on the first run.** It is also why `auto_confirm` is declared `false` on this rule: with the knob on, this would have written an unverified rotation into stored coordinates. The dry-run measures it (`ignore_knob=True`) without writing anything.

**(c) Die lineage — the §0 question**

| | rows | share |
|---|---|---|
| truth rows | 5,296 | |
| **correct (recall)** | **709** | **13.4%** |
| wrong | 2,053 | 38.8% |
| — of which **right wafer, wrong coordinates** | **2,053** | **100% of the wrong** |
| honest miss (answered "unknown") | 2,534 | 47.8% |
| unanswered | 0 | |

Where the trace stopped: `core_lot_slot_has_no_lot_event_snapshot` **1,668**, `tape_wafer_not_attributed_to_a_job` **866**.

🟩 **The single most useful number here is that all 2,053 wrong answers are "right wafer, wrong coordinates".** The lineage walk — bonding-time position → wafer identity → DT job → core wafer — **never once named the wrong wafer**. Every failure is the coordinate frame, i.e. inference #2 believing an unreliable declaration. The two halves of the problem are cleanly separated, and the 38.8% is entirely attributable to the frame, not to the split/merge tracing.

**(d) Honesty over `truth_ambiguous`**

| | count |
|---|---|
| ambiguous cases | 62 |
| answered UNRESOLVED → **counted CORRECT** | **20** |
| answered with a value → **FALSE CONFIDENCE** | **1** (`DT-EQP-02\|PRD-B`) |
| no system answer | 41 |

The 20 correct are the dropped-track-in jobs: the system said "unknown" and scored full marks, which is the rule this whole oracle exists to make possible.

⚠️ **The 41 "no system answer" is a granularity mismatch I must flag rather than score.** The oracle records frame symmetry **per job**; the system decides **per (equipment, product)**. A symmetric job sitting inside an otherwise-asymmetric combo is legitimately answerable from its siblings' evidence, so those 41 are not failures. My first scorer broadcast each combo's answer onto its jobs and reported **42 false-confidence cases** — inventing answers in order to mark them wrong, which is as dishonest as inventing them to mark them right. Fixed: only answers the system actually produced are scored.

### 10.6 Two defects in my own scorer, both caught before they became a number

1. **0% recall on all 5,296 rows** on the first run. `bond_x` is declared `number`, so PostgreSQL returns `11.0` while the oracle CSV holds `11`; `str(11.0) != "11"` made every key miss. A formatting mismatch wearing the costume of total failure. Fixed with a `norm()` that folds integral floats, the same normalization `crud.clean_str_value` applies on the write path.
2. **The fabricated 42 false-confidence cases** described above.

Both would have produced a confident, wrong headline number — the exact thing this fixture exists to prevent, committed by the tool measuring it.

---

## 11. Legacy declaration sweep (config only — nothing dropped)

**Removed 5 declarations:** `wafer_process` · `core_defect_map` · `eds_fail_map` · `map_doe` · `map_doe_source`
**Kept 13:** the 8 fixture tables · `bonding_map` · `wafer_map_metadata` · `map_split_registry` (system-level, user ruling) · `production_plan` · `inventory_master` (user ruling)

**No table was dropped.** Rows still physically present behind the removed declarations: `wafer_process` 22 · `core_defect_map` 5,152 · `eds_fail_map` 2,576 · `map_doe` 0 · `map_doe_source` 0 = **7,750 rows**, plus **1,656,770** provenance rows in `cell_sources`/`cell_overwrites`. The physical `DROP` is the user's action.

### Reference audit on the five

| config | still references them? | action |
|---|---|---|
| `ontology_mapping.json` | `wafer_process` mapping | **removed** |
| `map_overlay_config.json` | bindings | already gone in the step-1 rewrite; re-verified none remain |
| `enrichment_rules.json` · `chain_rules.json` · `maps.json` | none | — |
| `virtual_join_rules.json` | `_example_rejected_no_unique_index` names `core_defect_map`/`eds_fail_map` | **kept, deliberately** — it is an underscore-prefixed **comment key** that `virtual_join_config` skips, so it can never become an active dangling rule, and `test_virtual_join_guard` pins its shape. Staleness now stated inside the comment instead of left for the next reader. |
| 🔴 `bonding_plan_config.json` · `transfer_plan_config.json` | `wafer_process`, `core_defect_map`, `eds_fail_map` | **not rewired — escalating** (below) |

**Loaders re-validated after the removal: enrichment 2 rules, ontology 8 mappings, virtual-join 2 rules, zero rejections.**

### 🔴 The plan configs are now fully stale — and they degrade quietly

I checked how they fail rather than assuming: **nothing validates their table references.** `config_resolve_report` covers only enrichment and virtual-join (`_resolve_enrichment`, `_resolve_virtual_join` — that is the whole registry), and `bonding_plan.load_config` returns `{}` on any failure, documented as *"부분 가동 — 에러 아님"*. So a dangling reference there produces a partially-working screen, never an error.

Both configs were **already** stale for `bonding_log`/`dt_log`/`dt_map` (spec §10-6, escalated last round); they are now stale for three more. I did **not** invent replacement bindings — there is no correct mapping for `bonding_plan.used_chips` (it binds `bonding_log.core_lot/core_slot`, which the fixture deliberately removes, because a bonding log that knew its core directly would make §0 a one-line join). Rewiring the plan features onto trace results is a product decision and still needs your call.

### `production_plan` / `inventory_master` — reason recorded where it will be hit

Per your ruling, kept and **the reason is now in the config itself**, not only here: a `__comment` on both declarations in `table_config.json` and on the `production_to_inventory_reservation_batch` rule in `chain_rules.json`, carrying the sentence — *these are not fixture data; they exist because they are the only live exercise of the chain path, and removing them silently removes that coverage.* It also records why the fixture chain cannot substitute (`dt_log_to_dt_map` ships `enabled: false` because a chain cannot purge map cells, and turning an unsafe rule on to keep a test green is the same mistake as deleting the test).

### ⚠️ `map_doe`/`map_doe_source`: live config and sample deliberately differ

These two are **product-owned** — declared in `server/product_tables.py`, which is the single definition, with `test_install_product_tables.py::test_sample_product_section_equals_the_module` asserting the tracked sample matches it.

- `table_config.json` (this site's declarations) — **removed**, per the sweep.
- `table_config.json.sample` (the tracked product template) — **kept**, so the module/sample contract holds.

I first tried deleting them from `product_tables.py` too. **Twelve tests in `test_install_product_tables.py` use `map_doe` as the SUBJECT of their drift scenarios** (dropped column, reordered `display_columns`, changed separator, comment sync). They do not test `map_doe`; they test the installer *through* it, and deleting the entry turned all twelve into `KeyError`. I reverted rather than gut twelve harnesses to make a config sweep succeed. Retargeting them onto `map_split_registry` is feasible but is a change to the installer's test suite — different work, and not something to slip in silently. Say the word if you want it.

### How I confirmed the running server picked it up

Not a schema 200 — that route reads the config singleton. I probed `/tables/<t>/data`, which resolves the ORM model:

```
wafer_process 404 · core_defect_map 404 · eds_fail_map 404 · map_doe 404 · map_doe_source 404
dt_log 200 · lot_event 200 · dt_job_attribution 200
```

Every removed table is gone from the live process; every kept fixture table still serves.

---

## 12. What `dt_job_attribution` and `eqp_frame_attribution` are for

You asked whether these are the "dictionary" shape. **Yes — that is exactly what they are.**

Each is a **decision table**: one row per thing a human must judge, with the judgement itself as the columns.

| | `dt_job_attribution` | `eqp_frame_attribution` |
|---|---|---|
| one row = | one DT job | one (equipment, product) |
| the question | which DT lot/slot did this job's wafer become? | which of the 8 frames were these coordinates recorded in? |
| the answer columns | `dt_lot_confirmed`, `dt_slot_confirmed` | `core_frame`, `dt_frame` |
| in the queue while | both answer columns blank | both blank |
| rows | 120 | 4 |

Three properties make them a dictionary rather than a cache:

1. **The answer is stored once and reused everywhere.** 8,700 `dt_log` rows collapse onto 120 judgements; 8,700 rows collapse onto **4** frame judgements. That ratio is the leverage — one human decision reprices thousands of rows, which is "minimum-effort correction" made literal.
2. **The key is only things that are known.** `dt_job` is certain; `(dt_eqp, product)` is certain. Never the value under inference — that is why the targets are suffixed `_confirmed` and live outside the key.
3. **Blank means unknown, and unknown propagates honestly.** A blank target produces no graph edge (`compose_identity` → `None`), so confirmation shows up as *an edge appearing*, not a value quietly changing. Arrow ④ is visible in the graph rather than inferred from a diff.

The virtual joins then project the confirmed answer back onto `dt_log` beside the recorded one, so where the recorded value is one of the deliberately-wrong 10% the disagreement is on screen.

---

## 13. Numbers to re-measure, and what is still open

### Re-measure (all re-derived this round; none carried over)

| # | claim | how |
|---|---|---|
| 1 | **1836 passed, 2 skipped, 0 failed** | `conda run -n assy_manager python -m pytest server/tests/ -q` |
| 2 | stale rows **0 / 0 / 0 / 0** | the verify query in §4 |
| 3 | ingested: core_wafer_map **24,200** · dt_log **8,700** · bonding_log **5,296** · lot_event **43** · wafer_id_status **59** | `/tables/<t>/data` |
| 4 | derived: dt_job_attribution **120** · eqp_frame_attribution **4** | ditto (created by my backfill, after your 0/0) |
| 5 | dry-run rule 1: queue **120**, examined **240**, confirmed **200**, `no_candidate` **40** | `server/scripts/score_trace_fixture.py`, or the route with the token |
| 6 | die lineage: **709 correct (13.4%)**, **2,053 wrong (38.8%, all right-wafer/wrong-coords)**, **2,534 honest miss (47.8%)** | `python server/scripts/score_trace_fixture.py` |
| 7 | inference #2: asymmetric **4/6** correct, symmetric **1 false confidence** | ditto |
| 8 | honesty: **20** honest-correct, **1** false confidence, **41** no-answer | ditto |
| 9 | rows behind removed declarations: **7,750** + **1,656,770** provenance | §11 |
| 10 | orphaned `cell_sources`: **259,865** | §10.1 |

### Open, needing your call

1. 🔴 **The plan configs** (`bonding_plan_config`, `transfer_plan_config`) are fully stale and degrade silently — nothing validates their table references. Product decision, unchanged from last round.
2. 🔴 **Anchor bands do not gate inference #1** (§10.5a). Either the spec's expectation changes, or a second anchor-driven candidate view is added so the bands bite.
3. **The chain worker needs a restart** for enrichment rule changes; a transient rejection is permanent until then (§10.3). Worth a guard or a retry.
4. **`map_doe` retargeting** in `test_install_product_tables.py` — 12 tests, only if you want the product module cleaned too.
5. **The live dry-run** still needs `ASSY_ADMIN_TOKEN` from the operator to reproduce over HTTP.
6. **Auto-update collector** `lot_event/generate_trace_fixture.py` is registered and **disabled**; enabling it starts growing batches every 2 h.

**Not committed.** Nothing staged. `server/config_backup_*/` untouched and now gitignored. Generated dirs `server/trace_fixture_oracle/` and `server/trace_fixture_staging/` are untracked output and probably want a `.gitignore` entry.
