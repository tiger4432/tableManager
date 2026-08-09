# DT/Core frame chain operating documentation and config snapshots

## What changed

- Added the active architecture record `docs/architecture/DT_CORE_FRAME_CHAINS.md`.
  It defines the two independent coordinate spaces in `dt_log`, their ownership,
  frame equations, chain order, replace-map boundaries, and the core-usage map
  identity rule.
- Added `docs/guide/DT_CORE_FRAME_CHAINS_GUIDE.md` for configuration order,
  replay/verification sequence, and high-signal failure handling.
- Recreated all supported configuration snapshots from the active configuration:
  `server/config/*.json.sample` and `docs/guide/config_reference/*.json`.
- Validated every supported active JSON configuration with Python's JSON parser
  before taking the snapshots.  PowerShell's display/parser path was not used
  as the JSON authority because it misreported UTF-8 Korean text in this
  workspace.

## Important decisions recorded

- `dt_log` is source data; `dt_inventory` is the integrated per-job frame
  record; `dt_map` and `core_usage_map` are derived replace-map outputs.
- DT frame metadata lives in `wafer_map_metadata`; core frame metadata is not a
  second wafer-map metadata target and lives in `dt_inventory.core_frame`.
- `dt_core_view` remains visual-review-only and the former
  `frame_confirmation` history is retired.
- `core_usage_map` uses enriched `core_wafer` alone as its map identity, so
  partially enriched lot/slot inputs cannot create two maps for one wafer.

## Verification

- Parsed active `chain_rules.json`, `table_config.json`, and
  `enrichment_rules.json` as JSON after snapshot generation.
- Compared each active supported config against both snapshot locations for
  byte equality.
- Ran focused DT/core mapper and alignment tests; see the commit handoff for
  exact commands/results.
