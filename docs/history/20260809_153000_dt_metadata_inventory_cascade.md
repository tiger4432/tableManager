# DT metadata to inventory cascade

**Date:** 2026-08-09  
**Status:** Implemented and verified

## Decision implemented

```text
dt_log -> wafer_map_metadata(target_table=dt_log, map_id=dt_job)
       -> dt_inventory(dt_job).dt_frame
```

`dt_inventory.dt_frame` receives the serialized `grid_metadata` JSON unchanged.
Only DT metadata rows (`target_table=dt_log`) participate; other map metadata is
not projected accidentally.

## Worker safety contract

Chain-created events stay blocked by default. A downstream rule must declare
`allow_chain_trigger: true` to receive one. The worker filters at rule level, so
an opt-in rule cannot cause another rule sharing its trigger table to run. At
configuration load it rejects any cycle made of opt-in edges.

The enabled S2 rule is the sole approved second hop. `dt_map` projection and its
`replace_map` contract remain out of scope.

## Verification

- New cascade/identity tests: 13 passed.
- DT alignment mapper and alignment-route regression tests: 48 passed.
- Mapper live files are byte-identical to their tracked `.sample` counterparts.
