# Core alignment fingerprint proposal

Status: proposal — no production core-frame confirmation or canonical core-map
write is enabled by this document.

## Decision

Core alignment shall align a recorded partial core bin map against its physical
`core_wafer_map`, not against `valid_die_ref` values and not from a DT frame.
The core wafer map's own `wafer_map_metadata.valid_die_ref` is geometry only;
its `c_bn` cells are the fingerprint evidence.

```
dt_log raw core coordinates
  -> core alignment observation (one dt_job + one core wafer)
  -> align against core_wafer_map(core_lot, core_slot; c_bn fingerprint)
  -> reviewed/accepted core frame + shift
  -> dt_inventory core-frame decision JSON
  -> optional canonical core-map projection
```

`dt_core_view` is currently the visual prototype of the observation stage. It
contains `core_x`, `core_y`, `c_bn`, and `dt_index`: although recorded in the
DT log, this is the order in which dies were taken from the core and is the
core index. It remains available in the view but is intentionally not the
default generic-scoring axis until the core walk mode exists. It must not be
mistaken for the final multi-core identity.

## Why the current visual view cannot auto-confirm

1. `dt_index` is core pick order, but the existing generic index scorer assumes
   row-first serpentine traversal. Core order instead starts at the upper die
   of the outermost occupied left/right column and advances column-first. The
   existing scorer therefore cannot use this true index until it receives a
   core walk mode; treating it as a generic DT serpentine produces a false
   refusal.
2. `valid_die_ref/CORE_DT` has occupancy geometry and value `1`; source bins
   are `B0`/`B1`/etc. Their vocabularies are intentionally disjoint. Scoring
   those values falls back to occupancy and cannot use the defect fingerprint.
3. A DT job may contain cells from more than one physical core wafer. A map
   keyed only by `dt_job` pools unrelated fingerprints and has no single
   reference core map.
4. A core map is usually partial. A correct candidate needs a larger shift
   search against the physical core map; a DT-map fixed window or a DT-derived
   inverse rotation is not evidence.

## Phase 1 — explicit core observation identity

Replace the prototype's map identity with:

| Item | Contract |
| --- | --- |
| observation key | `dt_job`, `core_wafer` (fallback: `core_lot`, `core_slot`) |
| cell key | observation key + raw `core_x`, `core_y` |
| cells | `core_x`, `core_y`, `c_bn`, copied `dt_index` |
| reference | `core_wafer_map` map ID from `core_lot/core_slot` |
| reference geometry | that core map's WMM, including its resolved product valid-die reference |

This means the durable implementation must either rename/supersede
`dt_core_view` or expand its map key and composite key. It cannot preserve
`map_key_columns=[dt_job]` once multi-core jobs are admitted.

The review decision key is the same observation identity. `dt_inventory` then
stores a JSON object keyed by physical-core identity rather than one scalar
`core_frame`; one job-level scalar cannot truthfully represent multiple core
wafer decisions.

## Phase 2 — existing scorer, core-specific evidence policy

Use the existing alignment endpoint with:

```text
source:    core observation core_x / core_y / c_bn
reference: core_wafer_map core_x / core_y / c_bn
frames:    rot0..rot270 × TL/TR, front only until real side evidence exists
placement: wider bounded shift search, reported explicitly in the result
```

Candidate ranking order:

1. core-topology index agreement: candidate-transformed source cells are
   walked column-first from their outermost occupied column, top die first;
   both TL and TR starts are candidates. Source `dt_index` is compared to that
   candidate walk after its observed minimum is normalized to 1;
2. exact normalized `c_bn` agreement on overlapping source/reference cells;
3. occupied-cell overlap as the fallback when bin values are absent.

The topology index is translation-invariant and must not require a full map:
missing dies are skipped in the candidate's source-cell walk. Its role is to
select frame/start orientation; the bin fingerprint then resolves the physical
core-map shift. This is intentionally different from the DT row-serpentine
walk.

The source bin vocabulary and physical core-map bin vocabulary are generated
from the same die data in the synthetic fixture, so clustered B1/B2/B3 regions
break otherwise similar partial-map placements. Missing bins must degrade to
occupancy rather than inventing a replacement signal.

## Phase 3 — gates and writes

Initially manual review only. Automatic confirmation may be enabled only after
fixture and production replay establish all of the following for each
observation:

- reference core map resolves uniquely;
- source has one physical-core identity;
- enough overlapping fingerprint cells and a measured first/second margin;
- winner shift is not at the configured search boundary;
- no user-confirmed frame conflicts with the proposed result.

On confirmation, record `{frame, shift, reference, evidence summary}` under
the observation identity in `dt_inventory` JSON. Do not overwrite
`core_wafer_map`: it is the measured physical reference. A later canonical
projection is a separate scoped `replace_map` output after the write contract
is approved.

## Synthetic acceptance harness

The current `SYN-CORE-CLUSTER` fixture provides one 70%-yield physical wafer,
clustered bins, and three 61-die DT slices with independent hidden core frames.
Before automation, add tests that:

- select each job's own physical core map as the reference;
- recover its hidden frame/start from core-topology `dt_index`, then its shift
  from `c_bn` fingerprint evidence;
- remove bin values and verify an honest occupancy-only/no-winner result;
- demonstrate the generic serpentine walk fails the same fixture while the
  core column walk succeeds.

## Approval required

Approve Phase 1 identity migration before implementation. It changes the
core-observation map key and promotes `dt_inventory.core_frame` from a scalar
placeholder to per-core JSON decisions.
