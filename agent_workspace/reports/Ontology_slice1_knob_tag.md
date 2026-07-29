# Ontology Slice 1 — Knob Tag Tracing: Implementation Report

> **Author:** ontology-pm · **Date:** 2026-07-29 · **Status:** IMPLEMENTED, not committed
> **Board:** items 9 / 9b · **Spec:** `docs/spec/ONTOLOGY_GRAPH_SPEC.md` §7.5b, §7.5c
> `[measured]` = read directly from a live DB or source in this session. `[judgement]` = my reading.
> **No live DB writes. No live user config writes. No commit.** All execution against the isolated
> stack (`assy_qa` + `dev_env/config`), guarded by an assertion that refuses to run otherwise.

---

## 1. What landed

| file | change |
|---|---|
| `server/ontology_config.py` | `event_time_column` + `node_class` declarations; **unknown keys now rejected** |
| `server/graph_materializer.py` | edge `event_time` resolved from the declared column, at the single shared point |
| `server/config/ontology_mapping.json.sample` | label split (`Core`/`Tape`), `dt_log`, `Knob`/`Recipe`, reversal record |
| `server/scripts/graph_orphan_sweep.py` | **new** — bounded orphan cleanup, dry-run default, budget guard |
| `server/tests/test_ontology_event_time.py` | **new** — 19 tests |
| `server/tests/test_ontology_slice1_chain.py` | **new** — 8 tests |

**Not touched:** the live `server/config/ontology_mapping.json` (user-owned, gitignored). The exact
edit is handed over in §6 for you to apply. Concurrent-round files (`crud.py`, `config_watcher.py`,
`main.py`, `chain_ingestion_worker.py`, `map_editor.js`, `CODE_MAP.md`) untouched.

---

## 2. Baseline measurement (live `assy_manager`, read-only)

| | value |
|---|---|
| `graph_nodes` / `graph_edges` | **20,545** / **40,416** |
| `BONDED_FROM` | **11,106** (the 7,765 in the brief was one day old — **+43% in a day**) |
| `Wafer` label | **103** = 87 composite (`LOT-A\|05`) + 16 plain (`WF-A-05`) |
| retarget scope | **20,217 edges** (20,206 in + 11 out), not 7,765 |
| orphan composite nodes | **6** with no backing row anywhere |

`event_time` drift `[measured]`: `EXECUTED_BY` n=9,087 min −20.2h avg **+13.1h** max **+89.6h**
(the strategy report's +65.3h has grown). `PLACED_ON` n=11,106 max +9.2h.
All five candidate real-time columns parse **100%** (`wafer_process.start_time` 4,359 distinct,
all OK), so nothing degrades to NULL.

Degree `[measured]`: `Wafer LOT-A|07` **1,827** · `LOT-A|05` 1,800 · `Eqp` avg **1,136**.
`GRAPH_TRACE_NODE_CAP` = **1,000**. Five live nodes already exceed the spec's own §7.5c ceiling.

---

## 3. The identity question — resolved, and recorded so it can be reversed

Your confirmation: `dt_log.tape_lot/tape_slot` is the tape; the local data is simulator output.
Implemented as **option B**.

Three disjoint namespaces `[measured]`:

| namespace | example | owner |
|---|---|---|
| core | `LOT-A\|05` | `bonding_log.core_*`, `wafer_process.lot/slot`, `core_wafer_map`, `core_defect_map`, `eds_fail_map`, **`dt_log.core_*`** |
| tape | `TAPE-A\|01` | **`dt_log.tape_*`**, `dt_map.lot/slot` |
| wafer | `WF-LOT-A-05` | `wafer_process.wafer_id`, `wafer_slot_history.wafer_id`, `core_wafer_map.wafer_id` |

Overlap of `bonding_log`'s 80 distinct pairs: `dt_log.tape_*` **0/80** · `dt_map` **0/80** ·
`core_wafer_map` **80/80** · `wafer_process(lot,slot)` **80/80** · `core_defect_map` **80/80**.

The label map now declared:

| label | identity | source of record |
|---|---|---|
| `Wafer` | `wafer_id` | `wafer_slot_history` |
| `Core` | `core_lot\|core_slot` | `core_wafer_map`; targeted by `bonding_log`, `wafer_process`, `dt_log` |
| `Tape` | `tape_lot\|tape_slot` | `dt_log` — **new** |
| `DTEvent` | `dt_id` | `dt_log` — **new** |
| `Knob` / `Recipe` | `knobs` / `recipe_id` | `wafer_process` — **new** |

The reversal record lives in the config itself (`__comment_bonding_lot_is_core_here` and
`__comment_how_to_revert_to_tape`) and states the **trigger** ("when `bonding_log`'s lot/slot
values start overlapping `dt_log.tape_*` — i.e. when `TAPE-*` appears"), the **edit** (one string,
`target_label` `Core` → `Tape`), and the **follow-up** (resync, then the orphan sweep). No code
change, no migration.

`core_wafer_map`'s node label `Wafer` → `Core` also fixed a latent absurdity for free:
`_default_label_for_field` derives the `RESOLVED_AS` target from the field name `wafer_id`, so the
edge was previously `Wafer → Wafer`, a self-edge. It is now `Core → Wafer`, a real cross-link.
**Zero code change** — verified in the isolated loader output.

---

## 4. Verification

### 4.1 INV-O-2 — event_time

Isolated snapshot (`assy_qa`), before → after resync:

| | before | after |
|---|---|---|
| `EXECUTED_BY` drift | min −20.2h avg 11.7h max 41.6h | **min 0.00 avg 0.52** |
| `WENT_THROUGH` drift | avg 2.62h | **0.00 / 0.00 / 0.00** |
| edges with NULL `event_time` | 0 | **0** |
| `wafer_process` EXECUTED_BY agreeing with source row | **0 / 3,107** | **3,107 / 3,107** |

Before, six consecutive process steps all carried the identical stamp `2026-07-26 00:00:04.85`.
After, each carries its own `start_time`. Entity-level spot check 6/6 MATCH.

> ⚠️ **Honest caveat — 45 + 370 edges still carry the old time, and it is not this change.**
> `[measured]` 830 surplus edges of 15,970 (5.2%) are duplicate `(from, type, to)` triples with two
> different `source_name`s — the same logical rows re-ingested from a differently *named* CSV
> (`eqp_wafer_process_20260725_220603.csv` **and** `...20260726_220603.csv`).
> `_retarget_stale_edges` matches on the triple and deliberately ignores `source_name`, so the
> superseded edge survives every resync, carrying its original ingestion time forever.
> Measured on the current-source edge only, agreement is **3,107/3,107 = 100%**.
> This is the stale-edge class (board 9b), pre-existing. The sweep script reports it read-only.

### 4.2 INV-O-3 — 🔴 my proposed scoping was wrong, and I found out by running it

The `edge_types` set I proposed in the plan **fails**:

```
A  scope incl. EXECUTED_BY : nodes=1000 truncated=True  ProcessEvent=918 Core=63 Eqp=8  DTEvent=0
```

`[judgement]` **I mis-diagnosed this in the plan.** I wrote that §7.5c's four rules "would not fix
this". That was wrong. Including `EXECUTED_BY` routes the walk through `Eqp` — a static master with
degree ~1,150 — which back-expands into 918 unrelated `ProcessEvent`s and eats the entire budget.
That is **exactly** rule 4 (static→dynamic forbidden), and dropping `EXECUTED_BY` is hand-applying
it. Both mechanisms matter: rule 4 for the `Eqp` flood, the degree ceiling for the `Chip→Wafer`
D→D fan-out. I over-claimed and the measurement corrected me.

```
B  scope without EXECUTED_BY : nodes=1000 truncated=True  ProcessEvent=302 Core=63 DTEvent=634
```

**What I scoped, and what this trace therefore cannot see** (stated plainly so a narrowed result
does not read as a wide one):

| included | excluded — and the cost |
|---|---|
| `USED_KNOB`, `PERFORMED_ON`, `TRANSFERRED_FROM`, `ONTO_TAPE` | `EXECUTED_BY` → **which equipment ran any of it is invisible** |
| | `BONDED_FROM`, `PLACED_ON` → **no chip-level or base/jig history** |
| | `WENT_THROUGH` → **no process-step history from `wafer_slot_history`** |
| | `USED_RECIPE` → **recipe not shown** |

Single-call is **truncated** for the largest knob: the complete answer is 1,136 nodes
(302 + 63 + 768 + 3) against a hard 1,000 cap. Not a bug — a real limit, honestly flagged by
`truncated: true`.

**Two-step declared query is exact** `[measured]`:

```
step 1  seed Knob, depth 2, ["USED_KNOB","PERFORMED_ON"]        -> 63 Core
step 2  seed those Cores, depth 2, ["TRANSFERRED_FROM","ONTO_TAPE"]
        nodes=834 truncated=False   Core=63  DTEvent=768  Tape=3
        DTEvent oracle=768 trace=768  identical=True
        Tape    oracle=3   trace=3    identical=True
```

Compared **entity-by-entity against independent SQL**, as sets of identities — not counts.

> **Verdict on INV-O-3: conditionally met.** The chain exists and is walkable by edges alone
> (proved end-to-end in `test_ontology_slice1_chain.py`). At live scale a *single* call reaches DT
> history but truncates; the exact answer needs two scoped calls. The gap is the node cap, and it
> closes with the degree ceiling in 9b.

### 4.3 INV-O-5 — no guessed edges

`[measured]` isolated: `wafer_process` 3,107 rows, 980 with no knob, `USED_KNOB` edges **2,127**
= 3,107 − 980 exactly. Placeholder `Knob` nodes minted for missing data: **0**. The row still
exists as a node and keeps its other edges — it is not dropped, merely not guessed at.

Deliberately **not** mapped, with reasons: `map_split_registry.knobs` / `map_doe.knobs` (empty `{}`
/ 0 rows) · `mat_1h/mat_mid/mat_top` (14 rows, values are test junk — `QERWER`, `TAERF`) ·
`dt_map` cells (cells are not nodes; 14 of 21 keys are test junk).

### 4.4 INV-O-4 — regression

- Full server suite: **1,179 passed, 1 failed**. The failure is
  `test_config_reload_integrity.py::test_h3_cross_directory_replace_applies_physical_alter` — the
  **other round's** in-progress `config_watcher` test (zero ontology references, verified by grep).
- Ontology suites: 27 existing G1 + 19 + 8 new = **54 passed**.
- **Blast radius of the strict-key change on the live config: zero.** The same 5 tables load, the
  same 2 drop (`transfer_plan`/`transfer_plan_doe`, for the pre-existing reason that they are not in
  `table_config.json`), and the live file contains no unknown keys at any level.
- `client2/src/graph.js` and `trace.js` contain **zero** hardcoded labels or edge types, so the
  viewers follow the relabel automatically.

### 4.5 Mutation testing — 9/9 killed

A test that does not fail on a broken implementation proves nothing.

| mutation | result |
|---|---|
| M1 revert edge `event_time` to ingestion time | KILLED |
| M2 fall back to ingestion time when declared value unparseable | KILLED |
| M3 drop the unresolved warning (silent NULL) | KILLED |
| M4 unknown keys ignored again (**the original defect**) | KILLED |
| M5 `event_time_column` skipped in column-existence check | KILLED |
| M6 `node_class` dropped instead of preserved | KILLED |
| M7 `node_class` vocabulary left open | KILLED |
| M8 INV-O-5 broken: mint a placeholder instead of refusing | KILLED |
| M9 identity separator collision unescaped | KILLED (by the existing G1 suite) |

M9 first survived my new tests; rather than claim coverage I re-pointed it and confirmed
`test_ontology_g1.py::test_compose_identity_normalization` kills it. Sources restored and verified
byte-clean afterwards.

### 4.6 The orphan sweep, exercised

Dry-run after the relabel found 75 orphan `Wafer` nodes (the old `LOT-*|NN` composites, now `Core`)
plus `WF-LIVE-G1-TEST`. **The budget guard fired**:

```
Wafer  75/99 = 76%  REFUSE
REFUSING to delete: ['Wafer'] would lose more than 50% of their population.
A mapping typo can look exactly like this.
```

That is the guard doing its job — this loss was intended, but it is indistinguishable from a typo
without a human. Re-run as `--label Wafer --max-fraction 0.9 --apply` → deleted 75.

Orphan is defined as **zero edges AND not producible by any current mapping**. Zero-edges alone
would be catastrophic: `SplitCondition` has average degree 0.2, so a naive sweep would delete the
DOE vocabulary. Producibility is evaluated through `graph_materializer.compose_identity` — the same
function the materializer writes with — so the script cannot become a second identity
implementation that drifts.

---

## 5. ⚠️ Scope honesty — what this slice does and does not prove

**It proves: process-event knob → process history → core → DT → tape, by edge traversal.**

**It does not prove the sentence you started from — "자재의 knob tag".** `wafer_process.knobs` is a
knob attached to a *process event*, not a tag on a *material*. The material-side knob has no data
to stand on `[measured]`: `map_split_registry.knobs` is `{}` in all 15 non-null rows, `map_doe` and
`map_doe_source` have **0 rows**, and the material token arrays are 14 rows of mostly test strings.

That the two are structurally the same is a **hypothesis this slice did not test**. It is
plausible — both are "a condition node that events converge on" — and if it holds, the material
case attaches to the same `Knob` label with a second inbound edge and no new machinery. The next
use case is what tests it. Please do not let this be read as material-knob tracing being done.

---

## 6. Hand-off: the exact live config edit (I did not apply it)

`server/config/ontology_mapping.json` is user-owned and gitignored. Mirror
`server/config/ontology_mapping.json.sample`, or apply these five edits:

1. `bonding_log`: add `"event_time_column": "eventtime"`; `BONDED_FROM.target_label` `"Wafer"` → `"Core"`
2. `wafer_slot_history`: add `"event_time_column": "event_time"`
3. `core_wafer_map`: add `"event_time_column": "eventtime"`; `node.label` `"Wafer"` → `"Core"`
4. `wafer_process`: add `"event_time_column": "start_time"`; `PERFORMED_ON.target_label` `"Wafer"` →
   `"Core"`; add `USED_KNOB` → `Knob` (`knobs`) and `USED_RECIPE` → `Recipe` (`recipe_id`)
5. add the `dt_log` block; **delete** the dead `transfer_plan` / `transfer_plan_doe` blocks
   (already dropped on every load — removal only silences a false drift signal)

Then, in order: `POST /api/graph/sync` per table → `graph_orphan_sweep.py` (dry-run) → inspect →
`--label Wafer --max-fraction 0.9 --apply`. Expect the guard to refuse the first `--apply`; that is
correct.

⚠️ On live data the relabel touches **20,217 edges**. Everything uses `resync_table`'s existing
keyset chunking; no new full scan. `bonding_map` (1.76M rows) remains unmapped.

---

## 7. Findings for the board

1. **Superseded-source duplicate edges** — 830 of 15,970 (5.2%) isolated; re-ingesting the same rows
   from a differently named file leaves a permanent second edge that no resync refreshes. Belongs
   with 9b's stale-edge policy.
2. **Degree ceiling** — five live nodes exceed the spec's own 1,000 threshold; the complete answer
   for one knob seed is 1,136 nodes against a 1,000 cap.
3. **Rule 4 matters as much as the ceiling** — correcting my own plan: excluding `EXECUTED_BY` (i.e.
   static→dynamic) is what unblocked DT reachability. Both mechanisms are needed.
4. **Fourth identity fracture, untouched** — `wafer_process.wafer_id` ∩ `wafer_slot_history.wafer_id`
   = **0/80** (`WF-LOT-A-05` vs `WF-A-05`), with `core_wafer_map` supplying a third set. Splitting
   `Wafer` by identity shape does not fix it; the plain bucket is three disjoint claims.
5. **`wafer_process.wafer_id` is invisible to the graph** — 9,130 non-null values, 80 distinct, and
   the ontology targets `lot|slot` instead. That column is the natural bridge to the real-wafer layer.
6. **`enrichment_rules.json` still reads `bonding_log` lot/slot as core** — its reference views query
   `wafer_process WHERE lot = :core_lot AND slot = :core_slot`. Consistent with what we declared
   today, but it must move in lockstep whenever the tape switch is thrown.

---

## 8. Proposed lessons for `agent_workspace/memory/ontology-pm.md`

> Proposals only, per the operating rule — not added by me.

- **Trap:** citing an edge/node count from a report as the current population.
  `BONDED_FROM` went 7,765 → 11,106 in one day.
  **Right way:** re-measure at the start of every round; a report figure is a dated floor.
- **Trap:** treating a statement about the production floor as a fact about the local data.
  **Right way:** before a relabel, measure overlap against the tables that **own** the target
  namespace. 0/80 means the edge would be fabricated no matter how right the declaration is.
- **Trap:** adding a key to `ontology_mapping.json` and expecting it to work. The validator built a
  fixed dict and dropped unknown keys — which is why `node_class` never did anything.
  **Right way (now enforced):** unknown keys are rejected with the offending key named.
- **Trap:** assuming a fan-out problem has one cause. `Chip→Wafer` is D→D (needs the degree
  ceiling); `→Eqp→` is D→S→D (needs rule 4). I asserted the rules were irrelevant here and the
  measurement proved me wrong.
  **Right way:** name which mechanism a given blow-up needs, and run the traversal before claiming.
- **Trap:** proposing an acceptance criterion without executing it. My `edge_types` set was wrong
  and only running it revealed that.
  **Right way:** run the acceptance query during planning, not after implementing.
- **Trap:** `conda run` cannot take multiline `python -c` — it fails with an unrelated-looking
  conda crash report. (Already in the lessons file; it bit me again.)
