# Primary-core automatic frame chain

## Change

- Added the `dt_log_to_primary_core_frame` chain rule.
- It atomically writes `dt_inventory.core_frame` and `core_x_base/sign/offset`, `core_y_base/sign/offset`; `dt_core_view` remains a Map Editor review projection and is not a chain hop.
- The mapper groups a completed `dt_job` by configured core identity and selects the group with the smallest `dt_index` (then stable configured tie breakers). All rows from the selected group are scored together.
- The physical reference is fully configuration-driven: `reference.table`, `reference.map_id_template`, and `reference.fields` determine the defect/bin map. The shipped rule uses `core_wafer_map:{core_lot}_{core_slot}`; wafer-ID keyed production maps can switch the template to `{core_wafer}` without Python changes.
- The persisted `core_frame.valid_die_ref` is copied from the selected `core_wafer_map` metadata; the physical core map identifies the fingerprint, while its declared valid-die reference remains the product die-domain authority.
- `x_col`, `y_col`, `value_col`, `index_col`, accepted metrics, assumed-geometry permission, and acceptance thresholds are rule fields. The shipped empty `index_col` deliberately uses bin/defect values and occupancy rather than transfer order.
- The shared alignment service now supports validated equality-only source filters. The core mapper uses that to score primary-core rows directly from `dt_log`, without persisting an intermediate map, and explicitly ignores `dt_log`'s DT-coordinate metadata while evaluating core coordinates.

## Verification

- JSON parse: `server/config/chain_rules.json` and `server/config/chain_rules.json.sample`.
- `C:\Users\kk980\anaconda3\envs\assy_manager\python.exe -m pytest server/tests/test_core_alignment_mapper.py server/tests/test_map_alignment_references.py --basetemp .tmp\core-auto -p no:cacheprovider`
- Result: 27 passed.
- Read-only live mapper check for `SYN-CORE-CLUSTER-P2-R90-HDF4BBF90`: selected `SYN-CORE-WAFER-01`, resolved `core_wafer_map:SYN-CORE-CLUSTER_S01`, and produced `rot0_tl` / `rotation=0, side=front`, matching the fixture's `core_truth=rot0_front`.

## Operational note

Restart/reload the worker after deploying the mapper and rule. Existing jobs can be evaluated with the normal rule replay; jobs whose configured physical reference has no registered metadata remain a safe no-op.
