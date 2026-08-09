# SYN DT alignment samples and CSV export

**Date:** 2026-08-09  
**Status:** Verified end-to-end on 2026-08-09

## Generated sample set

`server/scripts/seed_syn_dt_alignment_samples.py` reads the live
`valid_die_ref:PRD-A_DT13` cells and their physical metadata. It creates eight
reproducible jobs: top-left/top-right start multiplied by rotations 0/90/180/270.
Each job has all 88 PRD valid dies, unique DT destinations, and a continuous
`dt_index` range 1..88. `TR` means only that index 1 is the top-right die; it
does not mirror the coordinate map or change the frame side. Both TL and TR use
the same `rot<0|90|180|270>_front` frame for a given rotation.

The current generator instead chooses a deterministic random upper bound `N`
per `(seed, corner, rotation)` and emits a sparse subset of `dt_index=1..N`.
It always retains 1 and N, then deterministically skips at least one middle
index when one exists. Job ids carry both `N` and an eight-character SHA-256 plan hash:
`SYN-TR-R90-N042-H1A2B3C4-20260809`. The hash covers the reference prefix and
generation inputs, so a CSV/job id identifies the exact synthetic sample plan.

The script is dry-run by default, writes UTF-8 CSV files with `--csv-dir PATH`,
and writes `dt_log` only with `--apply`. On 2026-08-09 it created 704 DT rows
under the `SYN-*-20260809` job keys and exported eight CSVs to
`agent_workspace/syn_dt_alignment_csv/20260809/`.

## Alignment result, bootstrap, and verification

The initial reference config used a slash key (`PRD-A/DT13`) while the actual
metadata map id is `PRD-A_DT13`; the config was corrected. The R0 top-left
sample now scores with index winner `rot0_tl`, margin 80, and 88 usable indices.

The source `dt_log` map has no prior metadata, so the alignment engine reports
`geometry_assumed=true`. The approved S1 rule now opts into
`geometry_bootstrap: "reference_only"`: it accepts this condition only with an
explicit resolved reference and wholly absent source geometry. All normal gates
(winner/index/ranking/no default thresholds/no truncation) remain mandatory.

The eight scoped SYN S1 events were replayed after correcting the pre-existing
`dt_inventory.dt_frame` physical column from `double precision` to `text`.
`table_config` intentionally retains `dt_frame: "string"`; S2 writes a canonical
serialized JSON string because dynamic table config has no native JSON type.
All 8 S1 outbox events reached `SUCCESS`, all 8 inventory rows received
`dt_frame`, and each stored value parsed as JSON with `valid_die_ref.map_id =
PRD-A_DT13`.
