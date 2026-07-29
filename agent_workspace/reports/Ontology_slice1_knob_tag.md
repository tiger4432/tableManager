# Ontology Slice 1 — Material Knob Tag Tracing: Pre-Implementation Plan

> **Author:** ontology-pm · **Date:** 2026-07-29 · **Status:** PLAN — awaiting approval, nothing implemented
> **Board:** items 9 / 9b · **Spec:** `docs/spec/ONTOLOGY_GRAPH_SPEC.md` §7.5b, §7.5c
> **Notation:** `[measured]` = read directly from the live DB or source in this session. `[judgement]` = my reading.
> **No writes were performed.** Every number below comes from read-only queries against `assy_manager`.

---

## 0. One paragraph

I measured before designing, and the measurement changed the design. Three things came back different from
what the brief assumed. **(1)** The retarget population is **20,217 edges, not 7,765** — the graph grew and is
still growing. **(2)** `bonding_log`'s `core_lot|core_slot` values live in the **core** namespace (`LOT-A|05`),
and they join **0/80** to the only two tables that own the tape namespace (`dt_log.tape_*`, `dt_map`) while
joining **80/80** to every core-side table — so relabelling those 11,106 edges to a `Tape` label would
manufacture 11,106 identities that no tape-owning table contains. That is INV-O-5 firing on the largest edge
population in the graph, so I stopped rather than guess. **(3)** The acceptance criterion INV-O-3 cannot pass
as written: the trace node cap is **1,000** and five `Wafer` nodes already have degree **1,600–1,827**, while a
`Knob` node would land at **~1,083**. Below: the numbers, two questions only you can answer, and a phased plan
where the parts that do not depend on those answers can start immediately.

---

## 1. Measurement — the baseline the brief asked for

### 1.1 Graph totals `[measured]`

| | value |
|---|---|
| `graph_nodes` | **20,545** |
| `graph_edges` | **40,416** |
| `BONDED_FROM` | **11,106** (strategy report 2026-07-28 said 7,765 — grew 43% in one day) |

The simulator feeds continuously, so every count here is a moving floor, not a fixed number.

### 1.2 Issue #15 — the `Wafer` label, counted `[measured]`

| shape | count | example |
|---|---|---|
| composite (`lot\|slot`) | **87** | `LOT-A\|05` |
| plain (`wafer_id`) | **16** | `A123`, `WF-A-05`, `WF-LOT-A-07` |
| **total** | **103** | |

Backing of the 87 composite nodes — checked row-by-row against the source tables:

| backed by | count |
|---|---|
| `core_wafer_map` ∩ `bonding_log` ∩ `wafer_process` (all three) | **80** |
| `dt_log.tape_lot\|tape_slot` only | **1** (`TAPE-A\|01`) |
| **nothing at all — orphans** | **6** |

Orphans: `B1TEST|01`, `QAM2B-T|01`, `TAPE_A|01`, `TAPE_B|02`, `TESTPLAN_M2VERIFY|01`, `UXTEST_BASE|01`
— residue from tests and from the now-dead `transfer_plan` mappings.

### 1.3 Retarget scope — the real number `[measured]`

Edges **into** composite `Wafer`:

| type | source table | count |
|---|---|---|
| `BONDED_FROM` | `bonding_log` | **11,106** |
| `PERFORMED_ON` | `wafer_process` | **9,087** |
| `PLANS_USE` | `transfer_plan_doe` (dead mapping) | 8 |
| `ON_TARGET` | `transfer_plan` (dead mapping) | 5 |

Edges **out of** composite `Wafer`: `RESOLVED_AS` → plain `Wafer`, **11** (from `core_wafer_map`).
Edges touching plain `Wafer`: `RESOLVED_AS` in 11, `WENT_THROUGH` out 7.

> **Retarget population = 20,206 in + 11 out = 20,217 edges.** The brief's 7,765 was a day-old figure for
> `BONDED_FROM` alone.

### 1.4 `event_time` drift, live `[measured]`

`event_time − props.<real time column>`, in hours:

| edge type | n | min | avg | max |
|---|---|---|---|---|
| `EXECUTED_BY` (`wafer_process.start_time`) | 9,087 | −20.2 | **+13.1** | **+89.6** |
| `PLACED_ON` (`bonding_log.eventtime`) | 11,106 | −0.9 | +0.1 | +9.2 |
| `WENT_THROUGH` (`wafer_slot_history.event_time`) | 7 | −0.5 | +2.6 | +4.9 |

The strategy report measured max +65.3h on 2026-07-28. It is now **+89.6h**. The drift grows because
`event_time` is ingestion time and the backlog lengthens. `BONDED_FROM` and `PERFORMED_ON` declare no time
prop at all, so their drift is unmeasurable but they carry the same wrong stamp.

**Every candidate real-time column parses 100%** `[measured]` — no honest-degradation NULL problem:

| column | distinct values | `datetime.fromisoformat` OK |
|---|---|---|
| `wafer_process.start_time` | 4,359 | **4,359** |
| `bonding_log.eventtime` | 2,181 | **2,181** |
| `dt_log.eventtime` | 3 | 3 |
| `core_wafer_map.eventtime` | 80 | 80 |
| `wafer_slot_history.event_time` | 7 | 7 |

Edges whose `event_time` would change: `bonding_log` 22,212 + `wafer_process` 18,174 + `core_wafer_map` 11 +
`wafer_slot_history` 7 = **40,404 of 40,416** (99.97%).

### 1.5 Degree distribution — this is what blocks INV-O-3 `[measured]`

| label | n | max degree | avg | p95 |
|---|---|---|---|---|
| `Wafer` | 103 | **1,827** | 196 | 224 |
| `Eqp` | 8 | **1,166** | 1,136 | 1,166 |
| `Base` | 94 | 197 | 118 | 166 |
| `ProcessEvent` | 9,087 | 2 | 2.0 | 2 |
| `Chip` | 11,102 | 2 | 2.0 | 2 |

Top nodes: `Wafer LOT-A|07` **1,827** · `LOT-A|05` **1,800** · `LOT-B|01` **1,704** · `LOT-B|03` **1,679** ·
`LOT-A|12` **1,639**.

A hypothetical `Knob` node, had we promoted `wafer_process.knobs` today:

| knob | would-be degree |
|---|---|
| `{"pressure":3.5,"slurry":"SL-2","pad":"IC1000"}` | **1,167** |
| `{"temp_c":420,"thickness_nm":180}` | 1,130 |
| `{"dose_mj":28,"focus":0.02}` | 1,083 |

`GRAPH_TRACE_NODE_CAP = 1000` (`server/main.py:2310`). §7.5c's super-hub ceiling is also 1,000.
**The live graph already exceeds the spec's own ceiling on five nodes, and a Knob layer would add five more.**

### 1.6 Knob and material data — what actually exists `[measured]`

| source | populated? | shape |
|---|---|---|
| `wafer_process.knobs` | **yes** — 8,254 / 9,130 rows, 18 distinct | `{"dose_mj":28,"focus":0.02}` |
| `wafer_process.recipe_id` | **yes** — 8,254 rows, 7 values | `R-CMP-01` … |
| `map_split_registry.knobs` | **no** — `{}` in all 15 non-null rows | empty object |
| `map_split_registry.mat_1h/mat_mid/mat_top` | 14 of 114 rows | `["TAPE-B_02_14_4"]`, `["3MID","AAA"]`, `["QERWER"]` |
| `map_doe`, `map_doe_source` | **0 rows** | — |

> **The literal "material's knob tag" does not exist as populated data.** `map_split_registry.knobs` is empty
> in every row that has it, `map_doe` is empty, and the material token arrays are 14 rows of mostly test junk
> (`QERWER`, `TAERF`, `SFSDFDS`). The only real knob datum in the system is **a knob on a process event**.

### 1.7 Dead mappings still declared `[measured]`

`transfer_plan` and `transfer_plan_doe` are declared in `ontology_mapping.json` but absent from
`table_config.json`, so `ontology_config._validate_table_mapping` drops them on every load with a WARNING.
Graph residue: `ExperimentPlan` 7 nodes, `DEFINED_IN` 14, `ON_TARGET` 5, `PLANS_USE` 8. Unchanged since
2026-07-28. They contribute 13 of the 20,217 edges in the retarget scope.

### 1.8 Consumers — the good news `[measured]`

`client2/src/graph.js` and `client2/src/trace.js` contain **zero** hardcoded label or edge-type strings
(grep clean for `Wafer`, `BONDED_FROM`, `PERFORMED_ON`, `RESOLVED_AS`). The viewers are label-agnostic and
render whatever `/graph/stats` and `/graph/trace` return. **A label rename cannot break them.** Hardcoded
labels exist only in `server/tests/test_ontology_g1.py`, `test_graph_trace_api.py`, `test_graph_viewer_api.py`
and in the config itself.

---

## 2. 🔴 Two questions I will not answer by guessing

### Q1 — Which column pair is the tape?

The brief states as settled fact: *"`bonding_log`'s lot/slot is tape — not core"*, and derives
*"`core_wafer_map.core_lot|core_slot` is a tape position, not a wafer."*

The data disagrees, and the disagreement is not marginal. There are **three** distinct value namespaces:

| namespace | example | owned by |
|---|---|---|
| **core lot/slot** | `LOT-A\|05` | `bonding_log.core_*`, `wafer_process.lot/slot` + `lot_id/slot_no`, `wafer_slot_history.lot/slot`, `core_wafer_map.core_*`, `core_defect_map`, `eds_fail_map`, **`dt_log.core_lot/core_slot`** |
| **tape lot/slot** | `TAPE-A\|01` | **`dt_log.tape_lot/tape_slot`**, `dt_map.lot/slot` |
| **wafer id** | `WF-LOT-A-05` | `wafer_process.wafer_id`, `wafer_slot_history.wafer_id`, `core_wafer_map.wafer_id` |

Measured overlaps of `bonding_log`'s 80 distinct pairs:

| target | overlap |
|---|---|
| `dt_log.tape_lot\|tape_slot` | **0 / 80** |
| `dt_map.lot\|slot` | **0 / 80** |
| `core_wafer_map.core_lot\|core_slot` | **80 / 80** |
| `wafer_process.lot\|slot` | **80 / 80** |
| `core_defect_map.lot\|slot` | **80 / 80** |

And `dt_log`'s own 6 core-side pairs → `core_wafer_map` **6/6**, `core_defect_map` **6/6**.

`dt_log` is the one table that holds **both** namespaces in the same row, and it separates them by column name:

```
tape_lot='TAPE-A' tape_slot='01' tx=8 ty=2  |  core_lot='LOT-A' core_slot='05' cx=15 cy=1  dt_eqp='DT-02'
```

Two more pieces of live evidence pointing the same way:
- `dt_map.val` is the **core** attribution vocabulary — `LOT-A_05` (140 cells), `LOT-B_01` (128) … — keyed on
  `dt_map.lot|slot = TAPE-A|01`. Tape map cell → core code. Exactly the DT-map role §7.5b describes.
- `enrichment_rules.json` → `core_wafer_attribution` resolves `bonding_log(core_lot, core_slot)` → `wafer_id`
  and its reference views read `wafer_slot_history WHERE lot = :core_lot AND slot = :core_slot` and
  `wafer_process WHERE lot = :core_lot AND slot = :core_slot`. **The live enrichment config already treats
  `bonding_log`'s lot/slot as a core wafer's lot/slot.** Declaring it tape makes that rule semantically wrong
  too — it would be resolving a tape position to a wafer id.

`[judgement]` Both statements can be true at once: your declaration is about the **production** factory, and
this DB is simulator output (`BL-AUTO-*` prefixes) that never built a tape layer, so it put core values in the
column that production fills with tape values. But I cannot act on the declaration in **this** data without
creating 11,106 `Chip → Tape(LOT-A|05)` edges whose target identity appears in **no** tape-owning table. That
is a fabricated claim at the largest scale in the graph, and it would make the DT join return zero while
looking authoritative — the exact "quietly wrong" failure mode this repo has paid for twice.

> **What I need, one line:** In `dt_log`, is `tape_lot/tape_slot` the tape (as its name and its `TAPE-*`
> values say)? If yes, then in **this** database `bonding_log.core_lot/core_slot` is core-namespace, and I
> should declare it as such with a note, rather than relabel it to `Tape`.

**Three options — your call:**

| | option | consequence |
|---|---|---|
| **A** | Declare `bonding_log → Tape`, matching production semantics | 11,106 edges point at identities with 0 backing in tape tables. DT trace returns empty. Correct for production, useless for demo. |
| **B** ⭐ | Declare `bonding_log → Core` **in config, explicitly**, with a comment recording that production semantics say tape and the simulator is the reason | Graph is true to the data it has. When the simulator or real logs supply tape values, it is a **one-string config change**, no code, no migration. |
| **C** | B now + a separate task to make the simulator emit a real tape layer | Ends the ambiguity permanently. Out of slice 1's scope; belongs to whoever owns `server/ingestion_workspace/*/auto_update/`. |

`[judgement]` I recommend **B**, and C as a follow-up board item. B is the only option that satisfies
"data accuracy > coverage" and "honest degradation" simultaneously — it does not claim anything the data
cannot support, and it costs one string to reverse.

### Q2 — Which knob is the seed?

| reading | seed | data status |
|---|---|---|
| **R1 — knob on a process event** | `Knob(dose_mj=28\|focus=0.02)` from `wafer_process.knobs` | **8,254 rows, 18 distinct — fully populated** |
| **R2 — knob tag on a material** | `map_split_registry.knobs` / `map_doe.knobs` per material token | **`{}` in every row; `map_doe` has 0 rows — empty** |

R2 is the literal reading of "자재의 knob tag", and it is the reading that connects to the DOE/material track
(`mat_1h/mat_mid/mat_top`). But building it today produces a demo with **no data in it** — a trace that
returns nothing proves nothing, and per rule ⑤ I should refuse to build edges from an empty vocabulary rather
than ship a hollow slice.

R1 is fully populated, is the same *shape* of thing (a knob condition as a node, events attached to it), and
**is the exact structure R2 will need** — when `map_doe.knobs` starts carrying values, the same `Knob` label
and the same `USED_KNOB` edge type serve both, and material tokens simply become a second in-bound source.

> **What I need:** confirm slice 1 seeds on **R1** (process knob, real data now) with R2 arriving free once
> DOE knobs are populated — or tell me R2 is the point and the slice should wait for that data.

---

## 3. 🔴 INV-O-3 is unreachable as written — and the fix is small

The acceptance criterion is *"seed a knob tag into `POST /graph/trace` → process history and DT history follow."*

Measured obstruction:
- `GRAPH_TRACE_NODE_CAP = 1000`, `GRAPH_TRACE_DEPTH_CAP = 3`
- Seed `Knob(pressure=3.5…)` → hop 1 pulls **1,167** `ProcessEvent` nodes → **cap hit at hop 1**
- Even seeding a single core, hop 1 from `Wafer LOT-A|07` pulls **1,683 Chips** — cap hit before DT is reached

`_expand_graph_subgraph` truncates and sets `truncated: true`, so it fails **honestly**, not silently. But it
fails. The DT history sits 3+ hops out and the chip fan-out consumes the entire budget at hop 1.

`[judgement]` The 4 traversal rules of §7.5c would **not** fix this — `Chip → Wafer` is D→D, which rule 1
permits. What blocks it is the **super-hub ceiling**, a different mechanism. So "build the policy engine" is
both out of scope *and* the wrong tool.

**Two ways forward, in increasing cost:**

| | approach | cost | honesty |
|---|---|---|---|
| **1** ⭐ | Acceptance test passes `edge_types` to scope the traversal (e.g. `["USED_KNOB","PERFORMED_ON","TRANSFERRED_FROM","ONTO_TAPE","RESOLVED_AS"]`, excluding `BONDED_FROM`) | **zero new code** — `/graph/trace` already accepts `edge_types` | The query says what it wants. Honest, but it is a hand-written query — not yet "edge trace alone". |
| **2** | Implement only the **degree ceiling** from §7.5c: entering a node above threshold reports a rollup count instead of expanding | small, self-contained, testable | Generic. Turns the cap from "truncated, contents arbitrary" into "N neighbours, not expanded". |

I propose **1 for slice 1** (it keeps the slice thin and proves the chain), and I recommend the lead **schedule
2 into 9b with the measured justification above** — the ceiling is no longer theoretical, five live nodes
exceed it today. Declaring a **named traversal profile in config** (a declared `edge_types` set with a name)
would be the natural bridge between 1 and 2, and is the shape the strategy report's §6-3 "declared queries"
argues for. I have not built it and am not proposing it for this slice.

---

## 4. A fourth fracture the brief did not know about `[measured]`

Issue #15 describes `Wafer` splitting into two identities. There are **three**, and the third is inside the
"real wafer" namespace that the plan intended to keep as `Wafer`:

| table | `wafer_id` for `LOT-A\|05` | distinct values |
|---|---|---|
| `wafer_process` | `WF-LOT-A-05` | 80 |
| `wafer_slot_history` | `WF-A-05` | 5 |
| `core_wafer_map` | `A123` | 11 non-null of 80 |

`wafer_process.wafer_id` ∩ `wafer_slot_history.wafer_id` = **0 / 80**.

> Splitting `Wafer` by *identity shape* (`|` vs no `|`) does **not** fix this. The plain-shape bucket is itself
> three disjoint claims about the same physical wafers.

`[judgement]` This is not a blocker for slice 1 — it is a **data quality** finding, and it is why
`wafer_slot_history` (7 rows, 5 wafers) makes such a thin `Wafer` layer. Two observations worth recording:

- `wafer_process` carries a `wafer_id` column with **9,130 non-null values / 80 distinct** that the ontology
  **does not use at all** — `PERFORMED_ON` targets `lot|slot` instead. That column is the natural bridge from
  process history to the real-wafer layer and it is currently invisible to the graph.
- `core_wafer_map.wafer_id` is the human-corrected answer (11 of 80 resolved), and its values are a *mix* of
  both synthetic conventions plus `A123`. That is enrichment doing its job on inconsistent inputs.

I propose slice 1 **leaves this alone and states it**, rather than papering over it. It belongs on the board.

---

## 5. Plan

### Phase 0 — blocking (you)
Answer Q1 and Q2. Nothing below phase 1 can be built correctly without them.

### Phase 1 — `event_time` correction (INV-O-2) · **independent of Q1/Q2, can start now**

The validator (`ontology_config._validate_table_mapping`) returns a **fixed dict** and silently discards
unknown keys. So writing `event_time_column` into the JSON has **zero effect** until the validator is
extended — the same trap that makes `node_class` a no-op today (strategy report §1-4). Any plan that only
edits JSON is a no-op. Changes:

1. `server/ontology_config.py` — accept optional `event_time_column` on the table mapping (and optional
   per-edge override), validated against `table_config` columns exactly like `identity` and `props` are.
   Undeclared → current behaviour, byte-identical.
2. `server/graph_materializer.py` — resolve `event_time` inside **`extract_graph_items`**, from the declared
   column when present, falling back to `row["event_time"]` otherwise. One point, so the **incremental**
   (`materialize_events`) and **resync** (`resync_table`) paths stay equivalent for free — the same discipline
   `attach_col_sources` already established for H1 provenance.
3. `server/config/ontology_mapping.json` — declare:

| table | column | edges affected |
|---|---|---|
| `wafer_process` | `start_time` | 18,174 |
| `bonding_log` | `eventtime` | 22,212 |
| `core_wafer_map` | `eventtime` | 11 |
| `wafer_slot_history` | `event_time` | 7 |

Parse rate is **100%** on all four `[measured]`, so no edge becomes NULL. Declared-but-unparseable will yield
`NULL` (honest "unknown time") rather than falling back to ingestion time — mixing two time semantics under
one field is the L1/L2 confusion the spec forbids. I will report the count if it is ever non-zero.

**Rollback:** delete the four declarations and resync. The code change is inert without them.

### Phase 2 — label split (INV-O-1) · **needs Q1**

Under recommendation **B**, the declared split:

| label | identity | owner table(s) |
|---|---|---|
| `Wafer` | `wafer_id` | `wafer_slot_history` — sole owner |
| `Core` | `core_lot\|core_slot` | `core_wafer_map`, `bonding_log`(→ `BONDED_FROM`), `wafer_process`(→ `PERFORMED_ON`), later `dt_log.core_*` |
| `Tape` | `tape_lot\|tape_slot` | `dt_log.tape_*` — **new**, no existing edges |

`ontology_config._default_label_for_field` derives the target label from the field name, so
`core_wafer_map`'s `RESOLVED_AS` already targets `Wafer` from `wafer_id`. Changing only that table's
`node.label` from `Wafer` to `Core` turns today's meaningless `Wafer → Wafer` self-edge into a correct
`Core → Wafer` cross-link, with **no code change**.

Retarget mechanism: **reuse `resync_table`** (keyset-chunked, provenance-restoring, per-chunk commit). It is
already a complete rebuilder — I am not writing a new one. `_retarget_stale_edges` is scoped by
`source_row_ref`, so the 20,217 edges are retargeted with provenance preserved, following the H1/H2-b pattern
exactly as the brief requires.

**The one gap I must close honestly:** there is **no `graph_nodes` DELETE path anywhere in production code**
(verified). After the relabel, the 87 old composite `Wafer` nodes remain with zero edges, and `/graph/stats`
would still show `Wafer: 103` — a visible lie. So Phase 2 includes a **one-shot, enumerated orphan sweep**:

- dry-run by default, prints the exact identity list before touching anything
- scoped to *only* the nodes this relabel orphans (enumerated, not a predicate over the whole table)
- **sweep budget guard**: if it would delete more than a declared fraction of a label's population, it stops
  and reports instead of deleting — a mapping typo must not be able to quietly empty the graph
- `--apply` required, and it runs against the isolated env first

This is **not** the general DELETE policy (still 9b). It is a bounded cleanup of a mess this change creates.

### Phase 3 — `dt_log` mapping + `Knob`/`Recipe` promotion · **needs Q1 + Q2**

`dt_log` (768 rows) is the frame bridge and currently unmapped. Proposed:

```
DTEvent(dt_id)  -[ONTO_TAPE]->      Tape(tape_lot|tape_slot)
                -[TRANSFERRED_FROM]-> Core(core_lot|core_slot)
                -[EXECUTED_BY]->    Eqp(dt_eqp)
                event_time_column: eventtime
```

`dt_eqp` reuses the existing `Eqp` label — `DT-02` joins the same equipment master as `EQP-04`. `[judgement]`
This is right: they are both equipment, and keeping them in one label is what lets "which tool touched this"
be one question.

`Knob` / `Recipe` from `wafer_process`, as **additional edges on the existing `ProcessEvent` node** — no new
node source table, no re-materialisation of 9,087 rows beyond the resync already needed for Phase 1:

```
ProcessEvent(proc_id) -[USED_KNOB]->   Knob(knobs)
                      -[USED_RECIPE]-> Recipe(recipe_id)
```

**Per rule ⑤, three things I will NOT map and why:**

| not mapped | reason |
|---|---|
| `map_split_registry.knobs` / `map_doe.knobs` → `Knob` | vocabulary is empty (`{}` / 0 rows). An edge from an empty vocabulary is a guess. |
| `mat_1h/mat_mid/mat_top` → material nodes | 14 rows, values are test junk (`QERWER`, `TAERF`); no declared identity scheme; would repeat #15 one layer down. |
| `dt_map` cells → nodes | 2,313 cells; strategy report §6-2 decided cells are not nodes, and `dt_map.lot|slot` contains 21 keys of which ~14 are test junk (`AAA`, `DSFS`, `11`). Region rollup belongs to a later slice. |

Also proposed, zero behaviour change: **delete the dead `transfer_plan` / `transfer_plan_doe` declarations**
from `ontology_mapping.json`. They are already dropped on every load; removing them only silences a false
drift signal. Their 13 residual edges fall to the Phase 2 sweep.

### Phase 4 — acceptance (INV-O-3, INV-O-4, INV-O-5)

All of it in the isolated env (`devenv.py up`, `assy_qa` on :8081/:8091). **No live DB writes at any point.**

| # | test | pass criterion |
|---|---|---|
| A | `POST /graph/trace` seeded on a `Knob`, `edge_types` scoped | Returns **the specific `ProcessEvent` ids, `Core` identities and `DTEvent` ids** predicted by an independent SQL query — **compared entity-by-entity, not by count**. Counts matching while pointing at different nodes has actually happened here. |
| B | `event_time` ordering | Process history for one core sorts by real process time. Verified by injecting a **deliberately wrong** declaration and confirming the test fails — an unexercised branch proves nothing. |
| C | **S→D / forbidden direction** | Not applicable this slice (no policy engine). Stated explicitly rather than silently skipped. |
| D | INV-O-4 regression | `/graph/stats` label set and per-label counts compared against a pre-change snapshot, plus `graph.html` and `trace.html` loaded against the isolated server. |
| E | INV-O-5 refusal | A mapping with an unresolvable target produces **no edge and a logged reason** — verified by injecting one. |
| F | Smoke seeding | Re-seed with **changed values** — identical re-seeding does not fire the outbox and the smoke test spins silently. |

**Scale:** `bonding_map` (1,756,794 rows) is **not** in this slice and stays unmapped. Everything above uses
`resync_table`'s existing keyset chunking. No new full scan is introduced.

---

## 6. What this slice deliberately does not do

§7.5c `node_class` rollout · the 4-rule policy engine (G2.5) · M3's 390k map-key backfill · G3 defect
inference (PPR / heat propagation) · the general DELETE / stale-edge policy · the `wafer_id` three-way
fracture (§4 above) · material and DOE knob promotion (empty data) · `dt_map` region nodes.

Two items I recommend the lead **add** to 9b with the measurements above as justification:
1. **Super-hub degree ceiling** — five live nodes already exceed the spec's own 1,000 threshold (§3).
2. **`wafer_id` namespace reconciliation** — 0/80 overlap between the two synthetic conventions (§4).

---

## 7. Proposed lessons for `agent_workspace/memory/ontology-pm.md`

> Proposals only, per the operating rule — not added by me.

- **Trap:** citing an edge/node count from a report as the current population. The graph is fed continuously —
  `BONDED_FROM` went 7,765 → 11,106 in one day.
  **Right way:** re-measure at the start of every round; treat report figures as a floor with a date attached.
- **Trap:** taking a semantic declaration ("this column means X") as licence to relabel edges, without
  checking whether the *values in this database* live in X's namespace.
  **Right way:** before a relabel, measure the overlap against the tables that **own** the target namespace.
  0/80 overlap means the edge would be fabricated, regardless of how correct the declaration is for production.
- **Trap:** adding a key to `ontology_mapping.json` and expecting it to take effect.
  `_validate_table_mapping` returns a fixed dict and silently discards unknown keys — `node_class` and
  `event_time_column` are both no-ops until the validator is extended.
  **Right way:** config-only ontology changes are only real for keys the validator already returns.
- **Trap:** assuming §7.5c's four traversal rules solve fan-out. `Chip → Wafer` is D→D, which rule 1 permits.
  **Right way:** fan-out is bounded by the **degree ceiling**, a separate mechanism. Name which of the two
  a given problem needs.
