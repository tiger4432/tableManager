# R2 - Server lens: what gets written, and can it be undone

> Design analysis only. No code changed, no harness written, `server/tests/` untouched.
> All DB figures measured 2026-08-04 on the live database (`assy_manager`, `DB_URL_SOURCE=default`),
> read-only psycopg2 session (`set_session(readonly=True)`), no DDL, no writes.

---

## 0. Headline - four premises in the brief are wrong

| # | Premise as briefed | What is actually true |
|---|---|---|
| P1 | "`dt_map_derivation.py` has NOT been run yet. This is a preventable moment, not a cleanup." | `dt_map` holds **81 rows** (all `dt_job='a_01'`). `cell_sources` carries **16,555 `user` claims** on `dt_map` plus **4,608 claims from three `dt_tape_map_*.csv` files**; `cell_overwrites` holds **16,555 rows** for the table. The first derivation is a MERGE into an occupied, human-corrected, already-multi-source table. |
| P2 | Spec `MAP_ALIGNMENT_SPEC.md:171` - "8,700 rows are blocked on `HOLD_FRAME_MISSING`; filling the 4 attribution rows unblocks them." | The call **never reaches the frame gate**. `dt_map.map_key_columns = ['dt_job']` (live `table_config.json`) but `dt_log_confirmed_attribution` exposes only `['dt_lot_confirmed','dt_slot_confirmed']`, so `resolve_identity_sources` (`dt_map_derivation.py:280-296`) raises `REFUSE_IDENTITY_UNDECLARED` at `:551` before any frame work. Enabling the rule today derives **0** and holds back **0**. Two independent repairs are needed, not one. |
| P3 | Mapper docstring `dt_map_mapper.py:37-41` - three rules share the mapper. | Live `chain_rules.json` has **one**: `dt_log_to_dt_map` (`enabled: false`). The two *revisit* rules (`dt_job_attribution_to_dt_map`, `eqp_frame_attribution_to_dt_map`) do not exist. The mechanism that makes the 40%-absent population recoverable is designed and **undeployed**. |
| P4 | "`ontology_mapping.json` materializes `dt_log -> CoreCell` by raw coordinate equality" and the two consumers answer the same question. | It **declares** it; it materializes nothing. `graph_edges` has **0** `FROM_CORE_CELL` rows. The 89,358 live edges are `FROM_CORE` (17,457) / `BONDED_TO` (16,210) / `TRANSFERRED_TO` (1,280) etc., types the current mapping does not declare, and `CoreCell` props are `cx`/`cy` while the declaration says `core_x`/`core_y`. The graph was materialized under a **superseded** mapping; `is_graph_synced = 0` for **all** 8,700 `dt_log` / 24,200 `core_wafer_map` / 5,296 `bonding_log` rows. **0** `DtCellClaim` nodes exist, so the claim-vs-link distinction the config congratulates itself on is unmaterialized too. |

---

## Q1. Does derivation know whether the frame was confirmed?

### How the frame is chosen - file:line

The **source** frame is honest and reads exactly one declared column.

- `FRAME_COLUMN = "dt_frame"` (`dt_map_derivation.py:110`), exposed by the verified virtual join
  `dt_log_frame_attribution` (`:104`), keyed `(dt_eqp, product)` - not per job, not per map.
- Loaded once per batch, chunked, index-backed: `load_attribution` `:396-438`, called `:588-590`.
  Both required UNIQUE indexes physically exist (`uq_vjoin_dt_job_attribution_dt_job`,
  `uq_vjoin_eqp_frame_attribution_dt_eqp_product`), so `join_rule`'s verification gate passes.
- `resolve_frame` `:441-455`: blank -> `HOLD_FRAME_MISSING`; unparsable -> `HOLD_FRAME_UNREADABLE`.
  `parse_frame` `:313-336` accepts **only** `rot{0,90,180,270}_{front,back}`. It never infers,
  never defaults, never borrows `core_frame` (`FORBIDDEN_FRAME_SUBSTITUTE`, `:111`).
- Disagreeing evidence refuses rather than picks: `resolve_frame_candidates` `:458-473`.

### Can it distinguish confirmed from auto-registered? **No - and the gate that exists is bypassable.**

`dt_map_derivation.py` contains the string "geometry" **zero times**. It never calls
`map_overlay.geometry_declaration`. It loads the target meta at `:631-636` and checks only
*presence* (`HOLD_TARGET_META_MISSING`).

The `auto_registered` refusal lives in exactly one place - `make_frame_transform`
(`map_overlay.py:514-523`, the only consumer of `geometry_refusal` anywhere in `server/`).
Whether the derivation reaches it is decided upstream:

```
dt_map_derivation.py:640   src_meta = source_meta_for_frame(target_meta, frame_text)
dt_map_derivation.py:642   map_overlay.resolve_map_transform(src_meta, target_meta)
map_overlay.py:584-586     if frame_axes(src) == frame_axes(tgt):  return identity   <-- shortcut
map_overlay.py:620-623     transform = make_frame_transform(...)  only when origin == derived
dt_map_derivation.py:663   if transform is None:  placed = nums       <-- RAW coords written
```

`source_meta_for_frame` (`:339-353`) builds the source meta **from the target meta**, replacing
only `rotation` and `side`. Every other axis in the `frame_axes` 8-tuple - `grid_y_invert`,
`start_x`, `start_y`, `cols`, `rows`, phys signature - is **equal by construction**. So the
shortcut fires whenever `parse_frame(dt_frame) == (target.rotation, target.side)`, and on that
branch **no geometry check runs at all**: the raw `dt_log` coordinate is written to disk as the
map coordinate.

**This is the general shape of the defect, not a dt_map detail: any refusal added inside
`make_frame_transform` is skipped by the identity shortcut above it.** In the plan path
(`bonding_plan.py:752`, `transfer_plan.py:1591`) the shortcut is much harder to hit, because the
two metas are independent rows and `frame_axes` includes the phys signature - an
`auto_registered` synthetic signature (chip 1x1 / offset 0) cannot equal a declared one. In the
derivation it is the *common* path.

### Measured exposure

- 668 metas: **320 auto_registered, all of them `rotation=0, side=front`** (the synthetic
  default, `map_meta_registrar.py:186-187`). Split: `core_wafer_map` 200/200 and `bonding_log`
  120/120 are auto_registered.
- `dt_map`: **146 metas, 0 auto_registered, 0 y-inverted**. **120 of them match a live
  `dt_log.dt_job`; 0 `dt_job` lacks a meta**, so `HOLD_TARGET_META_MISSING` would be 0.
- Declared frames of those 120: `rot0/back` 40, `rot90/front` 40, `rot0/front` 20,
  `rot180/front` 20. So **one** `dt_frame` value per `(dt_eqp, product)` must serve 20-40 jobs
  whose maps declare **four different canonical frames**; at most a third of them can take the
  identity branch for any single choice, and the unchecked branch will be **interleaved** with
  checked ones map by map, silently.

So today the derivation's blind spot does not bite `dt_map` (0 auto-registered metas), and it
bites hard on `core_wafer_map` and `bonding_log` - which is precisely the 320 maps the alignment
round exists to fix. **The hole opens as the alignment work succeeds**, when newly aligned maps
get declared frames that match the equipment frame.

### A second, unlabelled inheritance

`dt_frame` is a **2-axis vocabulary** (rotation, side; 8 values) standing in for a **4-axis**
frame. `grid_y_invert` and `grid_start_x/y` are silently taken from the target
(`:350-352`). Per the lead's correction the y-invert half cancels on the production path
(`_frame_phys_params` flips offset signs, `map_overlay.py:426-436`), so it is currently harmless
in value. The `start` half is **not** covered by that cancellation and remains an unlabelled
assumption. Census: 2 metas with `grid_y_invert=true`, 5 with a decentred bbox.

### What it does when the frame is absent

Correct and worth preserving: named, aggregated, split holdback (`HoldBack` `:480-507`,
`format_holdback_summary` `:510-526`, primary reasons split at `:134`). It refuses, it never
defaults. That part of the design needs no change.

---

## Q2. Provenance - what must a `dt_map` row carry to be re-derivable?

### First: the brief conflates two questions

- **(A) Which rows must be recomputed when an upstream declaration changes?**
- **(B) May a reader trust the coordinate that is on disk right now?**

(A) is **already solved, three times over**. (B) is not solved at all, and it is the only thing
that needs designing. Adding a "which declaration was used" column to answer (A) would be a
fourth spelling of a solved problem - invariant I6 territory.

### (A) is solved - do not build it again

| Existing primitive | file:line | What it answers |
|---|---|---|
| Trigger scoping by the *same* join key the gate uses | `dt_map_mapper.py:111-133` (`_payload_filters` reads the virtual-join `join_key` verbatim) | "which source rows does this corrected attribution cover" |
| Fan-out sizing **before** fetching, with a named refusal | `dt_map_derivation.py:360-385`, `SCOPE_ROW_CAP = 50000` at `:150` | "how big is that" |
| Full re-application over current contents, keyset-paged, real mapper, real write path | `chain_replay.replay_rule` (R1) | "recompute everything the rule now says" |
| Withdrawal of a stale source's **cell-layer** claim, revealing the layer beneath | `chain_replay.withdraw_source` (R2) `chain_replay.py:465`, `count_withdrawable` `:420` | "the rule no longer produces a value here" - which R1 structurally cannot say (`SKIP_BLANK`) |
| Row-level orphan removal by **positive selection**, dry-run first, 50% budget guard, human-touched rows protected | `dt_map_derivation.plan_retraction` `:739-801`, `_human_touched_row_ids` `:720-736` | "which cells does this source no longer own" |
| The index that makes all of the above affordable at scale | `models.py:279-289` - `(table_name, source_name, column_name, row_id)`, added because the alternative was a full Seq Scan (measured 861ms / 263,369 buffers on 13,148,355 rows) | "which cells does this source claim" |

Measured fan-out for the frame trigger, which is the dangerous one: **4** `eqp_frame_attribution`
rows cover **all 8,700** `dt_log` rows -
`(DT-EQP-02, PRD-A) 2,892 rows / 40 jobs`, `(DT-EQP-01, PRD-A) 2,889 / 40`,
`(DT-EQP-02, PRD-B) 1,473 / 20`, `(DT-EQP-01, PRD-B) 1,446 / 20`. One row = **33.2%** of the
table. Both `SCOPE_ROW_CAP` and `plan_retraction`'s budget guard are correctly sized for this.

### (B) is the gap - and with N sources it cannot be a row-level column

The corrected purpose chain makes the die map a **consolidation of N aligned sources**. A field
that says "this row was derived under frame F" is already wrong at the grain: two sources
contributing to one die can have been aligned under different claims. The field must live at
**(row, column, source)** grain - which is exactly `cell_sources`' grain
(`models.py:264-278`, UNIQUE on `(table_name, row_id, column_name, source_name)`).

Minimum set, each with the question it answers and what breaks without it:

| | Field | Question | What breaks without it |
|---|---|---|---|
| F1 | source identity | which input minted this cell | already carried: `dt_map.dt_job` (`dt_map_derivation.py:677`) plus `cell_sources.source_name`. Without it `plan_retraction` could only guess stale cells by set difference - its own docstring says so. **Exists. Keep.** |
| F2 | frame stamp = the `frame_axes` 8-tuple in force at derivation time (source and target) | is what is on disk still what the current declarations imply | invalidation can only be *detected* by re-deriving everything, and a half-re-derived table is byte-indistinguishable from a fully re-derived one. Use `frame_axes` (`map_overlay.py:367-389`) - it is already the cache key everywhere. Do **not** stamp the meta `row_id`: that is a second spelling of "which frame" and I6 says it will diverge. |
| F3 | confirmation state at derivation time (human/`auto_confirm` vs auto-registered/unchecked) | may a plan treat this die as identified | the plan cannot refuse. This is the whole point of the four-step chain. |
| F4 | **new, from the corrected chain**: the alignment claim per contributing source - which other sources this cell was consolidated against, and under which correspondence | is this die the *agreed* die or one source's opinion | "die map confirmed" becomes inexpressible. A cell backed by 4 agreeing sources and a cell backed by 1 unchecked source are the same byte. |

### Where they should live - recommendation

**Not new `dt_map` columns.** Two reasons, both concrete: (i) widening an existing table means
`create_all` does not ALTER, so a migration that does not run before every reader takes the
admin tab down with `UndefinedColumn` 500 - this repo has already paid that (server-pm memory);
(ii) a per-source fact at per-row grain is wrong under N-ary consolidation.

**F2 and F3 belong in the `cell_sources` source vocabulary.** `chain_replay` R2 already withdraws
*by* `source_name`; the covering index already exists; the layering already protects `user`. A
structured token (`chain:dt_map:<frame_axes_hash>`) makes F2 a query and F3 a prefix, with no
schema change and no new table.

Name the two costs honestly, because both are real and both are fixable in one place:
1. `resolve_priority_map` maps **unknown** source names to **99** (`crud.py:1081-1086`), the
   bottom tier. A proliferating token silently drops below every declared source unless the
   priority map learns prefixes.
2. It breaks `chain_replay`'s deliberate property that "a replayed cell is indistinguishable
   from an incrementally-ingested one" (`chain_replay.py:70-73`, `R1_SOURCE_NAME`). That property
   was chosen for a reason and must be re-argued, not silently discarded.

**F4 has no home in either, and must not be invented as a column.** The consolidation decision
*is* an enrichment decision: `decision_key` = the map, `target_fields` = the agreed frame/basis,
`reference_views` = the scoring, `auto_confirm` = the promotion gate. Live
`enrichment_rules.json` already carries `eqp_product_frame_attribution`
(`decision_key=[dt_eqp, product]`, `target_fields=[core_frame, dt_frame]`, `auto_confirm=false`,
4 reference views) and `dt_job_lot_slot_attribution` (`auto_confirm=true`, 5 views, **120 rows,
5 filled**). Spec section 5 got this right and stopped one rule short: the missing rule is the
**per-map correspondence decision**, not a column.

---

## Q3. Refuse or label?

### Where the vocabulary lives

`config_resolve_report.py:80-81` is the definition site (`REASON_NOT_DECLARED`,
`REASON_MAPPING_UNAVAILABLE`) and `:404` states the governing rule: *new words are not invented;
adding vocabulary is a contract change*. Reused verbatim at `graph_stale_edges.py:58-59`,
`bonding_plan.py:333-341`, `main.py:2947-2956`, `map_preset_routing.py:90-101`,
`enrichment_candidates.py:131`. `map_overlay.py:78` `STATUS_ALIGN_UNAVAILABLE`,
`map_overlay.py:1081` `STATUS_NOT_DECLARED`, `crud.py:127` `REASON_VERSION_UNORDERABLE`.
`미상` is the virtual join `unresolved_label`, declared on **both** live rules.

### How consumers handle them today

They refuse coordinates and keep counts. `bonding_plan.py:759-767` demotes to
`connected(align_unavailable)`; `:793-795` then serves `region_counts = 0` rather than computing
from raw coordinates. `transfer_plan.py:1589,1596` returns `(None, "align_unavailable", False)`.
This split - **counts survive an unknown frame, coordinates do not** - is the right one and
already exists. It needs no new machinery.

### Recommendation: **label, per source, in refusal shape**

Refusing to derive is what happens today, and it is exactly what has kept the rule off. Refusal
has no gradient: it cannot express "3 of 4 sources agree", which under the four-step chain is the
common case, not an edge case.

Three cell-level states, all spellable in the existing vocabulary:

- `align_unavailable` - this source's coordinate cannot be moved into the map frame at all. The
  cell has **no vote**. (`map_overlay.py:78`, already exists.)
- `unconfirmed` - the source voted, but under a frame nobody checked. A vote of unknown weight.
- confirmed - a human, or an `auto_confirm` sweep, confirmed the frame.

A consolidated `dt_map` cell carries the **weakest** of its contributing sources. Do not invent
that rule: `graph_materializer.py:180-190` already uses it for edge provenance ("a relational
claim is trusted only as far as its least trusted input"). Reuse the spelling.

### What the bonding plan must do when it meets the label

Exactly what `bonding_plan.py:793-795` already does with `align_unavailable`: serve the count,
refuse the coordinates, demote the status string. What must be **added** is a middle rung -
today the only two are `connected` and `connected(align_unavailable)`, and there is no way to say
"moved, but on a frame nobody checked". Without that rung, `unconfirmed` has to be spelled as
either of the two existing ones, and both spellings are lies.

### What happens today if a plan meets an unlabelled unconfirmed frame

Two different things, and one of them is the silent case the brief said is not an option:

1. **Independent metas, one auto-registered:** `frame_axes` includes the phys signature, so a
   synthetic `chip 1x1` signature cannot equal a declared one -> `origin = derived` ->
   `make_frame_transform` raises (`map_overlay.py:514-523`) -> `align_unavailable`, region
   counts 0. **Honest.** This is the D1 fix working as designed.
2. **A meta compared against a meta derived from itself** - i.e. the derivation path
   (`source_meta_for_frame`): the phys signature is equal by construction, so the identity
   shortcut fires and the raw coordinate is written with no geometry check at all
   (`dt_map_derivation.py:663-664`). **Silent.** All 320 auto-registered rows are `rot0/front`,
   i.e. maximally likely to match whatever default they are compared against.

So "silently proceed" is not one of the three options, but it **is** the current behaviour on one
branch, and that branch is the one the derivation takes.

---

## Q4. Do the two consumers agree today? **They cannot disagree, because neither answers.**

### The framing is wrong: they are not two spellings of one question

`FROM_CORE_CELL` (`server/config/ontology_mapping.json:153`) joins `dt_log`'s **core**
coordinates to `core_wafer_map` - the `core_frame` axis. `bonding_plan.py:752` and
`transfer_plan.py:1591` transform on the **bonding / DT** axes. The system's own schema declares
the core axis to be an *unsolved* frame problem: `dt_log_frame_attribution` exposes **both**
`core_frame` and `dt_frame`, and `dt_map_derivation.py:111` names `core_frame`
`FORBIDDEN_FRAME_SUBSTITUTE` precisely because it is a different frame of a different wafer.

So the ontology edge asserts raw equality on an axis the schema separately declares unknown.
That **is** the layer-4 gap - but it is a **third** instance of it, not the same one, and layer 4
must cover three axes (core, DT, bonding), not two.

### Neither path produces an answer today - measured

- Ontology path: **0** `FROM_CORE_CELL` edges. Graph materialized under a superseded mapping
  (edge types and prop names do not match the current declaration); `is_graph_synced = 0` on all
  three feeding tables; **0** `DtCellClaim` nodes.
- Transform path: **200/200** `core_wafer_map` metas are `auto_registered`, so
  `make_frame_transform` refuses (`map_overlay.py:514-523`) for **every** core map. Its answer is
  `align_unavailable`, not a cell.

**That settles it without a numeric comparison.** One path would produce a confident cell for
every row; the other produces none. A stated "these do not compare" is the honest result here.

### The number that matters when the edge is turned on

Raw-coordinate equality of `(core_lot, core_slot, core_x, core_y)` between `dt_log` and
`core_wafer_map`, measured:

| | rows |
|---|---|
| `dt_log` total | **8,700** |
| carry a core lot/slot at all | **7,440** (1,260 cannot form the identity) |
| match an existing `core_wafer_map` row | **4,450** (51.1% of all; 59.8% of those with a core identity) |
| **point at a die `core_wafer_map` does not have** | **2,990** |

Those 2,990 will **not** surface as failures.
`graph_materializer.extract_graph_items` does `node_map.setdefault(target_key, {})`
(`graph_materializer.py:187`) for the edge target: the edge cannot fail to find a node, it
**mints** one. A wrong frame on the core axis therefore produces a graph in which every
`dt_log` row carries a confident `FROM_CORE_CELL` edge, ~40% of them to dies that do not exist,
and the **edge count is identical either way**. That is invariant I1 at graph granularity, and it
is the argument for spec section 9-b (`CoreCellClaim`) being a *correctness* fix, not a
cosmetic one.

### Scale through each path today

| path | tables bound | rows |
|---|---|---|
| `bonding_plan` transform family | `bonding_log`, `core_defect_map` (x2), `eds_fail_map`, `wafer_map_metadata`, `wafer_process` | `bonding_log` 5,296 |
| `transfer_plan` transform family | `bonding_map`, `dt_log` (x3), `map_split_registry`, `wafer_map_metadata` | `dt_log` 8,700, `bonding_map` 413 |
| ontology `FROM_CORE_CELL` | declared over `dt_log` | 0 materialized / 8,700 pending |
| **`dt_map`** | **bound by neither plan config** | 81 |

**The terminus of the purpose chain is not wired to the table this question is about.** No plan
reads `dt_map`. `transfer_plan` reads `dt_log` **raw**. (Separately: its `bonding` stage binds
`dt_log` columns `x`/`y`/`lot`/`slot`, which do not exist on `dt_log` - those bindings are
currently unresolvable and demote.)

---

## Q5. Layer 4 as server code

### It is `make_frame_transform` promoted, plus three things it does not have

Proposed signature (returns a record, not a bare callable - the callable is what makes the
current identity conflation invisible):

```
correspond(source: MapRef, target: MapRef, *, basis: BasisChoice) -> Correspondence

Correspondence = {
    map          : (x, y) -> (x, y) | None      # None == identity, as today
    claim        : "confirmed" | "unconfirmed" | "refused"
    basis        : "circle" | "ref" | "refused"
    source_frame : frame_axes 8-tuple           # canonical form, for comparison only
    target_frame : frame_axes 8-tuple
    reason       : str | None
}
```

Refuses on: grid dimensions differ (already, `map_overlay.py:508-511`); geometry not `declared`
on either side (already, `:514-523`); **NEW** - a basis that resolves on one side and not the
other; **NEW** - a source frame whose non-`(rotation, side)` axes were *inherited* rather than
declared (today's `source_meta_for_frame`, silently).

### What it must gain

**1. The basis as an explicit parameter.** This is the client/server divergence the lead
measured (165/165 cells shift). The server's `_frame_transformer` (`map_overlay.py:457-466`)
always constructs a bare `PhysicalWaferEngine`, so `get_wafer_bounding_box` is circle-only; the
client swaps in the valid-die mask bbox when `valid_die_ref` resolves. **The abstraction the
server needs already exists one screen away**: `resolve_valid_die_basis`
(`map_overlay.py:1398-1441`) returns `{basis, source: circle|ref|refused, reason}` and its
docstring already states the invariant layer 4 needs - *"the resolver owns the coordinate system,
so the two bases are interchangeable at one site"*. It is simply not threaded into
`_frame_transformer`. Layer 4's first job is to thread it and make the choice **explicit on both
sides** rather than implicit and different.

Do not size this exposure by today's count. **8 metas declare a `valid_die_ref`** (`bonding_map`
7, `dt_map` 1) out of 668 - but `valid_die_ref` itself holds **2,631 rows** and is the mechanism
the 320 unmeasured maps are supposed to be repaired *with*. The exposure grows exactly as the
alignment work succeeds.

**CACHE HAZARD - name it in the design.** `frame_axes` (`map_overlay.py:367-389`) is the cache
key for `_FRAME_TF_CACHE` (`:439-470`) and `_CIRCLE_MASK_CACHE` (`:1348-1367`), and it does
**not** include the basis choice. If the basis becomes pluggable without entering that tuple,
two different bases share one cached transformer and the second caller silently receives the
first caller's bounding box. This is a coordinate-wide silent wrong answer waiting to be written.

**2. Provenance in the return.** `resolve_map_transform` returns `origin` as only
`"derived" | "identity"` (`map_overlay.py:573-574`), and `"identity"` currently conflates two
very different facts: *the two frames are genuinely the same* and *we had no basis to think
otherwise* (`:577-580` returns identity for absent metas). The derivation's silent branch
(`dt_map_derivation.py:663-664`) exists **only because that conflation is available**. Splitting
it closes the Q1 hole at the source rather than patching each caller.

**3. Canonical spelling - for comparison, not for coordinates.** Per the lead's correction delta
is 0 on the production path, so canonicalization is not needed for coordinate correctness. It is
still needed for **cache and equality** correctness: `frame_axes` puts the raw `grid_y_invert`
in the key (`:387`), so two spellings of one orientation occupy two cache entries, compare
unequal, and make `resolve_align`'s identity shortcut (`:585`) *miss* on an aliased pair - after
which it composes a transform that is the identity anyway. Wasteful, and it makes "same frame?"
answerable two ways. Canonicalize **on read, at the comparison**, never on write - exactly as
spec section 2.1-3 says.

### What must be deleted or rerouted

**Nothing needs deleting.** `make_frame_transform` is already the single transform. Call-site
census (`server/`, excluding `server/tests/`):

| symbol | definitions | non-test call sites | test references |
|---|---|---|---|
| `make_frame_transform` | 1 (`map_overlay.py:473`) | **1** (`map_overlay.py:623`) | 24 combined |
| `resolve_map_transform` | 1 (`map_overlay.py:608`) | **5** - `map_overlay.py:955` (overlay), `map_overlay.py:1603` (valid-die reference), `bonding_plan.py:752`, `transfer_plan.py:1591`, `dt_map_derivation.py:642` | |
| `geometry_declaration` | 1 (`map_overlay.py:333`) | **1 gating site** - `map_overlay.py:514-517` via `geometry_refusal` | |

The second copy that once lived in `bonding_plan.py` was already deleted
(`dt_map_derivation.py:80-81`). So promoting `make_frame_transform` to layer 4 is a **5-call-site
signature change**, not a migration.

**What must be REROUTED is the ontology materializer.** `FROM_CORE_CELL`
(`ontology_mapping.json:153`) resolves its target through
`target_identity_from: [core_lot, core_slot, core_x, core_y]`, composed by `compose_identity` at
`graph_materializer.py:169` - a pure per-row loop with **no transform hook anywhere in the
function**. Two options:

- **(a)** the config declares a correspondence for the edge and the materializer calls layer 4.
  This puts a DB-reading, meta-loading call inside a loop that runs over 24,200 + 8,700 rows, so
  it must be a per-**map-pair** cache, never per row. Correct end state; not cheap.
- **(b)** spec section 9-b: retarget the edge to a `CoreCellClaim` label. **One config line, no
  code**, and it makes the graph stop asserting a resolved link nobody established.

**Recommend (b) now, (a) only after layer 4 exists.** (b) costs one line and stops the lie today;
(a) is the real fix and depends on work that has not started. `CLAIMS_DT_CELL -> DtCellClaim`
(`ontology_mapping.json:226`) is the precedent the same file already set for the lot/slot axis
and argues for at length - the coordinate axis was simply not given the same treatment.

---

## Appendix - production census used above

All read-only, `assy_manager`, 2026-08-04.

| | |
|---|---|
| `dt_log` | 8,700 rows / 120 `dt_job` / 4 `(dt_eqp, product)` / 370 `(core_lot, core_slot)` / 73 `(dt_lot, dt_slot)` |
| `dt_map` | **81 rows**, 1 distinct `dt_job` (`a_01`) |
| `dt_map` cell sources | `user` 16,555 · `dt_tape_map_20260726_103603.csv` 1,536 · `..._103902.csv` 1,536 · `..._104202.csv` 1,536 |
| `dt_map` cell overwrites | 16,555 |
| `core_wafer_map` | 24,200 rows / 200 distinct maps |
| `bonding_log` / `bonding_map` | 5,296 / 413 |
| `wafer_map_metadata` | 668 (`core_wafer_map` 200, `dt_map` 146, `bonding_log` 120, `core_defect_map` 80, `eds_fail_map` 80, `bonding_map` 32, `valid_die_ref` 4, `sample_map` 4, `test` 2) |
| auto_registered | 320 - all `rot0/front`; `core_wafer_map` 200/200, `bonding_log` 120/120, everything else 0 |
| metas declaring `valid_die_ref` | 8 (`bonding_map` 7, `dt_map` 1); `valid_die_ref` table itself 2,631 rows |
| `eqp_frame_attribution` | 4 rows, `dt_frame` **0/4** filled, `core_frame` **0/4** filled |
| `dt_job_attribution` | 120 rows, `dt_lot_confirmed` **5/120**, `dt_slot_confirmed` **5/120** |
| `graph_nodes` / `graph_edges` | 40,074 / 89,358 - under a **superseded** mapping; `is_graph_synced=0` on all feeder tables |
| `dt_log` legacy duplicate coordinate spellings | `cx`/`cy` and `tx`/`ty` columns exist and are **100% NULL** (0/8,700) - dead second spellings still in the schema |

---

## Proposed lessons for `agent_workspace/memory/server-pm.md`

(Proposal only - not added.)

1. **A gate inside a transform is skipped by any identity shortcut above it.**
   `resolve_align` returns identity *before* `make_frame_transform` runs
   (`map_overlay.py:584-586` vs `:620-623`), so every refusal added to the transform is bypassed
   when the two frames' axes are equal. In `dt_map_derivation` the source meta is **built from**
   the target meta, so all but two axes are equal by construction and the bypass is the *common*
   path. Before adding a gate, find the shortcut upstream of it and decide whether the gate
   belongs there instead.
2. **A derived table's declared map key must be checked against the join meant to fill it.**
   `dt_map` declares `map_key_columns=['dt_job']` while the confirmed-attribution join exposes
   only `*_confirmed` lot/slot; the whole derivation refuses at the identity gate
   (`dt_map_derivation.py:551`), and the board attributed the blockage to the frame gate instead.
   Blame the first refusal in the call order, not the most interesting one.
3. **Do not design a re-derivation column set before reading `chain_replay`.** R1 (re-apply)
   + R2 (`withdraw_source`) + `plan_retraction` + the `(table_name, source_name, column_name,
   row_id)` covering index already answer "what must be recomputed when an upstream declaration
   changes". The unsolved question is the different one: "may a reader trust what is on disk".
