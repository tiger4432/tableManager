# DT alignment replay payload

## Problem

Live ingestion and `chain_replay` both use the durable outbox source-row shape
`data.<column>.value`. The DT alignment metadata mapper incorrectly read a
nonexistent flat field, so no path had a usable `dt_job` decision key and
silently produced no metadata updates.

## Change

The mapper now reads its decision key from the one canonical payload shape.
Live ingestion and replay therefore reach the same alignment and metadata
projection path by the same contract.

## Verification

- `SYN-TR-R270-N064-H123A2C34-269838749511604796616678240761231031151`
  was projected to `wafer_map_metadata(target_table=dt_log, map_id=dt_job)`
  with `rot270_tr`, then cascaded to `dt_inventory.dt_frame`.
- `python -m pytest server/tests/test_dt_alignment_metadata_mapper.py
  --basetemp C:\\tmp\\assy_manager_pytest_dt_replay_4 -p no:cacheprovider`
  passed: 6 tests.
