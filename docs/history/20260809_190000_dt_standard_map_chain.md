# DT standard map chain

`dt_inventory.dt_frame` is compressed into portable DT coordinate equations:
`dt_x/dt_y = select(X|Y, raw_x, raw_y) * sign + offset`. Coefficients are read
from `map_overlay.make_frame_transform`, not reimplemented from rotation strings.

The S3 chain first upserts `wafer_map_metadata` for the same `dt_job` as an
ancillary write (standard start 1/1, rotation 0, front side, and the source
frame's `valid_die_ref`), then projects each `dt_log` job's raw `dt_x/dt_y` and
`c_bn` into the standard-coordinate `dt_map`. This is part of S3, not a
separate metadata chain. It replaces only the `{dt_job: ...}` scope, guarded by
`allow_replace_map: true`, so frame reconfirmation cannot leave stale cells or
purge another job's map.

`core_*` fields remain unset: no confirmed core frame/meta is present in this
chain, and deriving them from DT metadata would be an unsupported guess.

Verification: Python compilation succeeded; an existing confirmed DT frame
produced a valid equation and a scoped replacement batch.

Admin visibility: the Chain Rules table now displays the directed table flow,
batch/row execution, cascade permission, target-map metadata permission,
scoped-replace permission, and the real `enabled` state. Selecting a rule shows
the same permissions in an operator-facing narrative instead of only raw JSON.

The S3 metadata writer now reads `valid_die_ref` directly from
`wafer_map_metadata(dt_log, dt_job)`, rather than trusting an older copied
`dt_frame`, and applies that declaration onto derived `dt_map` metadata.

Formula correction: a confirmed `dt_frame` with `valid_die_ref` stores an
origin calculated against the valid-die mask box so the editor redraws its raw
map correctly. The equation extractor had used circle boxes instead, which
shifted the derived standard map by two rows for the observed R90 and R180 SYN
jobs. S2 now resolves and caches the declared reference through the same
confirmation loader, then supplies its mask boxes to
`map_overlay.make_frame_transform`. When a reference cannot be resolved, it
deliberately retains the former circle-box behavior rather than inventing a
mask. Regression coverage fixes the mask-aware R90/R180 standard-y origin.

Admin replay correction: R1 previously accepted only a mapper's ordinary
`updates` list. The S3 standard-map mapper intentionally returns
`map_metadata_updates` plus job-scoped `replace_map` batches, so the Admin run
queued successfully but wrote zero cells. R1 now validates and applies those
two existing chain envelopes with the same target/permission/scope guards as
the live worker, writing metadata before the scoped map replacement.

Synthetic core fixture: `seed_syn_core_defect_jobs.py` writes one `CORE_DT`
wafer as a spatially clustered bin/defect map, registers its editor metadata
under `core_wafer_map`, then divides its dies without overlap across two or
three synthetic DT jobs using the `PRD-A_DT13` destination map. Core TL/TR is
the top valid die of the slice's outermost occupied column, never an empty grid
corner. Core recording-frame truth is independent of DT rotation; it is test
fixture truth only, not an inference rule. `CORE_DT` itself is likewise a
fixture reference, while production core valid-die references must resolve from
the DT-job/product mapping.

`dt_inventory` now also receives `core_wafer_list`: a stable JSON array grouped
from all `dt_log` cells of that job. Each entry keeps `core_wafer`, fallback
`core_lot`/`core_slot`, and `die_count`, so a missing wafer ID does not erase the
job's core usage. The S2 mapper performs one grouped source read for its whole
batch rather than one query per job.

Core alignment review now has an isolated `dt_core_view` map namespace. It is
the raw `core_x`/`core_y`/`c_bn` projection for one `dt_job`, keyed by that job,
and is deliberately separate from both `dt_log` (whose metadata is the DT
frame) and `core_wafer_map` (the physical wafer map). This follows the actual
metadata identity `(target_table, map_id)`: storing a second core frame beneath
`wafer_map_metadata(dt_log, dt_job)` would overwrite or ambiguously reinterpret
the DT frame.

The `core_frame_review` alignment rule is manual-only (`auto_confirm: false`)
and opens `dt_core_view` with `core_x`, `core_y`, and `c_bn`; selecting the
product-specific core valid-die reference borrows its geometry without writing
a source frame declaration. The synthetic clustered-core seed now populates
this view for its three 87-die job slices. It is a visual/scoring workbench,
not an automatic core-frame or canonical-core-map pipeline.

The core fixture now also removes deterministic physical dies: perimeter bites,
an interior chip, and distributed dropouts leave 183 (70%) of the 261 `CORE_DT`
reference cells. Its three job slices therefore contain 61 dies each instead
of a misleading full footprint. Seed application uses exact scoped
`replace_map` writes for the synthetic core wafer and each generated DT job,
so rerunning it deletes stale fixture cells as well as writing the new gaps.
Before writing, it purges only older `SYN-CORE-CLUSTER-*` job scopes, which is
necessary because fixture-content hashes change when the yield changes.

Adding that second alignment rule exposed a Map Editor 2 bootstrap defect: the
client correctly declines to propose one rule when more than one rule declares
`alignment: true`, but its served HTML lacked the `me2-rule-select` control.
No rule could then be selected, so catalog/worklist loading never began and
the screen remained in its loading shell. The question bar now publishes the
rule selector before the table/coordinate/reference controls; the built static
page carries the same markup for immediate server use.

`dt_core_view` now carries `dt_index` as an exact copy of the source DT-log
index and declares that existing name as its alignment index axis. No invented
`core_index` is stored: the review view names the provenance honestly, and a
future core-specific recorder sequence can be added only when it actually
exists upstream.
