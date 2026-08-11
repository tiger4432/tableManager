# DT/Core frame derivation chains

> **Status:** active implementation | **Owner:** Lead / Backend | **Last verified:** 2026-08-11

## Purpose

`dt_log` is the immutable measurement source.  A DT job contains two independent
coordinate spaces: DT coordinates (`b_wx`, `b_wy`) and the coordinates of the
source core (`c_wx`, `c_wy`).  This design resolves both frames once, records
them on the job inventory, and derives replaceable standard-coordinate maps.

```mermaid
flowchart LR
  L[dt_log: raw cells] --> A[DT alignment]
  A --> M[wafer_map_metadata: DT job metadata]
  L --> I[dt_inventory: job integration record]
  M --> I
  I --> D[dt_map: standard DT map]
  L --> C[primary-core alignment]
  C --> I
  I --> U[core_usage_map: standard core cells]
  L --> U
  R[core_wafer_map: physical valid/defect reference] --> C
```

`dt_core_view` is only a Map Editor review namespace.  It is not part of the
production automatic chain.  The retired `frame_confirmation` history is not
an authority and must not be reintroduced.

## Authority and outputs

| Data | Authority | Key / scope | Role |
|---|---|---|---|
| `dt_log` | ingest | `dt_job` raw cells | source coordinates, bin, core identity |
| `wafer_map_metadata` | DT alignment | `target_table=dt_log`, `map_id=dt_job` | DT grid metadata only |
| `dt_inventory` | chain integration record | `dt_job` | `dt_frame`, `core_frame`, equations, enriched core list |
| `dt_map` | derived replace-map | `dt_job` | DT cells in standard coordinates |
| `core_wafer_map` | physical reference | configured lot/slot map id | core valid-die and defect/bin reference |
| `core_usage_map` | derived replace-map | `core_wafer` | cells used by DT jobs after core standardization |

The standard-map target metadata is always `front`, rotation `0`, and
`grid_start_x=grid_start_y=1`.  `dt_map` retains the DT valid-die reference
selected for the source job.  `core_frame.valid_die_ref` is copied from the
selected physical `core_wafer_map` metadata, never from the map table name.

## Frame equations

An accepted frame is persisted as JSON and as six scalar fields for each
coordinate space.  The generic equation is:

```text
standard_x = IF(x_base = 'X', source_x, source_y) * x_sign + x_offset
standard_y = IF(y_base = 'X', source_x, source_y) * y_sign + y_offset
```

DT uses `dt_x_base`, `dt_x_sign`, `dt_x_offset`, `dt_y_base`, `dt_y_sign`, and
`dt_y_offset` against `b_wx`/`b_wy`.  Core uses the identically shaped
`core_*` fields against `c_wx`/`c_wy`.  A mapper writes neither frame nor its
equations if the selected alignment cannot be represented by this equation.

## Active chains

1. `dt_log_to_alignment_metadata` aligns the DT grid and writes the DT job's
   `wafer_map_metadata` record.
2. `wafer_map_metadata_to_dt_inventory` copies that DT metadata into
   `dt_inventory.dt_frame`, derives DT equations, and records the job's core
   wafer list.
3. `dt_inventory_to_standard_dt_map` replaces the complete `dt_map` scope for
   the job from raw `dt_log` cells and the DT equations.
4. `dt_log_to_primary_core_frame` selects the first configured core identity
   for the job (ordered by `dt_index`, then core identity), aligns its raw
   `c_wx`/`c_wy` cells to a configured `core_wafer_map`, and writes
   `dt_inventory.core_frame` plus core equations.
5. `dt_inventory_to_core_usage_map` replaces the usage cells for an enriched
   `core_wafer` after core equations change.  `dt_log_to_core_usage_map` also
   runs for raw ingest/enrichment changes so a later `core_wafer` attribution
   is reflected without manual reconstruction.

Both standard-map outputs use `replace_map`.  A successful rerun replaces only
the declared map scope; it does not append a second version of the same map.
The ingestion worker permits the inventory-to-map dependency explicitly, while
cycle validation continues to reject unapproved chain loops.

## Core selection and evidence

One DT job can consume multiple core wafers.  The automatic core-frame rule is
intentionally configured to resolve one primary core: a job does not change
its coordinate frame during execution, so one unambiguous reference is enough
to establish the equation for all its rows.  The rule's `primary_selector`,
`reference`, `columns`, accepted `metrics`, and thresholds live in
`server/config/chain_rules.json`.

Core alignment must read raw `dt_log` while ignoring that row's DT map metadata:
the latter describes the DT frame and is not evidence about the core frame.
`source_filters` constrain the selected identity to the configured core group.
Value and occupancy matching search an unrestricted shift; TL/TR is meaningful
only to index matching and does not constrain those modes.

`core_usage_map` is deliberately keyed solely by enriched `core_wafer`.  Some
logs arrive with only lot/slot while others arrive with wafer ID; adding lot/slot
to the replace-map identity would split one physical wafer into two maps.  Rows
without `core_wafer` safely produce no usage output until enrichment supplies it.

## Operational invariants

- Never edit `dt_map` or `core_usage_map` as source data; rerun their owner
  chain after changing the frame or source rows.
- A missing core physical reference or unresolved `core_wafer` is a legitimate
  no-output state, not an invitation to synthesize a frame.
- Candidate thresholds are quality gates.  Lowering a margin to force a winner
  hides ambiguity; fix the reference, coordinates, or configuration instead.
- Load table declarations before map metadata, then chain rules, then
  enrichment rules.  A process restart is required after a signature/config
  surface change so all workers share the same configuration snapshot.
- 🔴 **The job column is spelled nowhere in these mappers (2026-08-11).** Every
  table in the authority table above states its own job-column name, and the four
  mappers read each name from `table_config` (a single-column `map_key_columns`,
  or a single-column `business_key` where there is no `composite_key_source`) or
  from an explicit `chain_rules.json` override. **There is no `dt_job` default.**
  A name that can be resolved from neither is refused by name — the chain aborts
  and says which rule, which key and which table — instead of assuming a spelling
  that is only correct on the development box. Rename the column in
  `table_config.json` and all four chains follow; nothing in mapper code has to
  change. Resolver: `server/chain_bindings.py`.
- ⚠️ **One mapper spans three tables and they are three separate names.**
  `dt_standard_map_mapper` reads a `dt_inventory` payload, queries `dt_log`, and
  writes `dt_map`; `core_usage_mapper` reads its trigger (`dt_inventory` on one
  rule, `dt_log` on the other), queries `dt_log`, and reads `dt_inventory`.
  Renaming the column on only one of them is a legitimate configuration that the
  code now expresses; a single literal could not.

## Related implementation

- `server/chain_bindings.py` (job-column resolution: declaration > derivation > refusal)
- `server/mappers/dt_inventory_metadata_mapper.py`
- `server/mappers/dt_standard_map_mapper.py`
- `server/mappers/core_alignment_mapper.py`
- `server/mappers/core_usage_mapper.py`
- `server/dt_frame_transform.py`
- `docs/guide/DT_CORE_FRAME_CHAINS_GUIDE.md`
