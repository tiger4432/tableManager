# Core wafer map alignment catalog

## Change

- Added `core_wafer_map` to `map_alignment.floor_tables()` alongside `valid_die_ref`.
- The Map Editor 2 reference picker uses this shared catalog, so physical core bin/defect maps with registered metadata are now selectable as alignment references.
- `core_wafer_map` alone may use auto-registered physical geometry as an alignment reference. Core review compares its declared grid, occupancy, and bin fingerprint; synthetic 1x1 chip dimensions are not evidence needed for that comparison. `valid_die_ref` retains the physical-geometry refusal gate.
- Raised the reference-catalog cap from 50 to 500. The live environment has 201 core-map metadata rows; the former global cap allowed only 42 of them after eight valid-die references.
- This only expands the read-only scoring candidates. It does not add an auto-confirm rule or alter frame writes.

## Reason

Core defect maps arrive and are managed at wafer-ID granularity. Core-frame review must be able to inspect a DT core-coordinate view against the corresponding physical core map before the `(core_lot, core_slot) -> core_wafer_id` enrichment is used to narrow the choice automatically.

## Verification

- `C:\\Users\\kk980\\anaconda3\\envs\\assy_manager\\python.exe -m pytest server/tests/test_map_alignment_references.py --basetemp .tmp\\core-ref-catalog -p no:cacheprovider`
- Result: 22 passed.

## Operational note

The already-running server process must reload/restart to read this Python change. Then refresh Map Editor 2 and select `core_frame_review`; registered `core_wafer_map` entries appear in the reference selector.
