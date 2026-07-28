# Server Report — U9 STACK 0 Marker (server half) + U8 bin_map Declaration E2E

Baseline: working tree on `408070f` + map-pm's uncommitted client/contract changes (untouched).
`client2/**` and `contracts/**` content untouched, as instructed. Live :8080 / live config /
live DB untouched — zero live writes.

## Part 1 — Marker semantics in `server/transfer_plan.py`, scored against vectors v3

### Implementation points (file:line, post-change)

| Point | Location |
|---|---|
| `STACK_MARKER = "marker"` constant (+ why `_int_state` stays untouched) | `server/transfer_plan.py:1821-1825` |
| `stack_state`: exactly 0 (or `"0"`) → `(0, marker)`; blank stays blank; negatives stay invalid with value | `server/transfer_plan.py:2011-2020` (branch at 2016) |
| `mid_zone`: marker → `{from:null, to:null, size:0, known:true}` (known-empty, never unknowable) | `server/transfer_plan.py:2035-2039` |
| `zone_layers`: marker → `[]` for every zone regardless of typed content | `server/transfer_plan.py:2054-2058` |
| `validate_zone_plan`: V6 emission + full suppression (`continue` — V5/V2/V1/V4/W-DUP never fire on a marker row) | `server/transfer_plan.py:2218-2234` |
| V3 pool scan skips marker rows | `server/transfer_plan.py:2300-2306` |
| `material_rollup_rows`: marker rows absent (not present-with-zero) | `server/transfer_plan.py:2357-2363` |
| `validate_plan` demand loop: markers naturally excluded via `layers==0` (comment documents it) | `server/transfer_plan.py:2878-2884` |
| Module docstring: V1~V6 + marker contract | `server/transfer_plan.py:39-45` |

`zone_demand` needed no change — it derives 0 from `zone_layers() == []` (share `ceil(0/n) = 0`),
exactly what the `marker_value_demands_nothing_however_much_is_painted` vector pins.
`/api/transfer-plan/validate` needed no wiring change: V6 flows out as `zone_rule_violation`
(advisory — endpoint never gates), and marker materials are never resolved/queried/demanded
(no `source_unresolved`/`source_scope_unpriced` noise on marker rows).

### Vector groups scored server-side

All **8 server groups** of v3 are consumed (`stack_cases`, `zone_extent_cases`, `plan_cases`,
`material_token_cases`, `demand_cases`, `rollup_cases`, `remaining_cases`, `legacy_band_cases`);
`tsv/paste/roundtrip` stay declared client-only. v3 added no new *groups*, only new cases inside
existing groups — the generic loops score them automatically. To make that loud rather than
silent I added in `server/tests/test_doe_zone_model.py`:
- `version >= 3` pin (scoring a pre-marker snapshot now fails, `test_...consumed_or_declared_client_only`)
- per-group minimum case counts raised to v3 sizes (stack 12 / extent 7 / plan 15 / demand 8 / rollup 5)
- `V6` added to the must-all-fire rule set
- 5 marker-axis tests: declaration-vs-blank, known-empty-vs-unknowable, V6-only suppression scope,
  V3-exclusion-is-the-marker-state control (same token pair blocks V3 once stack becomes real),
  rollup absence.

### Mutation results — 9/9 killed

| # | Injected defect | Result |
|---|---|---|
| M1 | marker folded back into invalid (pre-U9 revert) | KILLED |
| M2 | blank folded into marker (`Number('')===0` accident) | KILLED |
| M3 | marker `mid_zone` collapses into unknowable (`known:false`) | KILLED |
| M4 | marker `zone_layers` returns `None` instead of `[]` | KILLED |
| M5 | V6 branch falls through (V5/V4 also fire) | KILLED |
| M6 | V3 scan no longer skips markers | KILLED |
| M7 | rollup keeps markers (present-with-zero) | KILLED |
| M8 | V6 never fires | KILLED |
| M9 | marker zones cover layer 1 (demand invented from a condition) | KILLED |

Original file restored byte-exact after each run (CRLF trap avoided by byte-level restore).

## Part 2 — U8 isolated-env (:8081) bin_map E2E

### Structural finding (this is the headline)

**A `bin_map` declaration on an M1-delegated stage can never light the axis.**
`get_stage_source_summary` answers any bins request on the `source_config_ref` path with an
unconditional `_bins_unavailable("core-kind(M1 위임) 소스는 BIN별 감산을 계산할 좌표 집합을
갖지 않습니다...")` (`server/transfer_plan.py:1561-1567`); `_bin_axis_binding` is only consumed
by `_summarize_inline`. Live's dt stage is M1-delegated — so the site-authored fix for dt is an
**inline `source` block**, not just a `bin_map` key. Additionally, an inline stage without
`origin_log` is force-degraded (`statuses["origin_log"]="missing"` → `remaining_reliable=False`
→ every BIN entry `unknown`, `remaining: null`). For a **root** source (core) the declaration
that satisfies this honestly is an **origin_log self-join** (chips originate from themselves).

### What was done (isolated env ONLY — `dev_env/`, assy_qa DB, port 8081)

1. `devenv.py bootstrap --force` — the dev_env config copy was stale (pre-M2.6 v1 `plan_store`);
   refreshed from live so the QA round sees the current registry shape.
2. `dev_env/config/transfer_plan_config.json`: dt stage converted from `source_config_ref` to an
   inline `source` mirroring `bonding_plan_config` role bindings (total_chips=core_defect_map,
   transfer_log=dt_log core-side, defect frame=self, process_history=wafer_process,
   **origin_log = core_defect_map self-join**), plus the declaration under test:
   ```json
   "bin_map": { "table": "dt_map",
                "columns": { "lot": "lot", "slot": "slot", "x": "x", "y": "y", "bin": "val" } }
   ```
   A `__isolated_scratch_comment` in the file records why.
3. Seeded scratch BIN cells into assy_qa `dt_map` for (LOT-A, 05): 1288 cells copied from the
   core_defect_map coordinate universe, val `1` (x≤20) / `2` (x>20), + 5 non-integer cells to
   exercise `unbinned_cells`. Scratch registry rows for (dt_map, LOT-A_05): one real DOE
   (stack "4", MID `LOT-A_05`) and one **U9 marker** (stack "0", MID `MID9`).
4. `devenv.py up` — stack started on :8081; startup `sync_dynamic_tables_schema` ALTERed the
   zone columns (`stack`,`mat_1h`,`mat_mid`,`mat_top`) into assy_qa `map_split_registry`
   (verified via information_schema, not the schema API).

### E2E transcript (declaration → axis connected → numbers)

- `GET /api/transfer-plan/stages` → dt roles all `connected` (total_chips/transfer_log/
  process_history/origin_log/defect), `plan_store.registry: connected`.
- `GET /api/transfer-plan/source-summary?stage=dt&lot=LOT-A&slot=05&bins=` →
  `chips {total 1288, fail 347, transferred 128, remaining 840, remaining_reliable true}`,
  **`bins.axis: "connected"`**, `unbinned_cells 5`, entries **matching the independent oracle
  computed straight from SQL before the server ever ran**:
  - bin 1: `{cells 644, total 644, fail 174, transferred 65, remaining 415, reliable true}`
  - bin 2: `{cells 644, total 644, fail 173, transferred 63, remaining 425, reliable true}`
- `bins=1,9` → bin 9 `bin_absent`, `remaining: null` (never 0) — contract held.
- `scope=lot&bins=` → `slots_origin:"map"` + `lot_membership_degraded` warning,
  `by_slot [{slot "05", map_exists true, chips_total 1288}]`, merged bins with
  `basis:"pool_sufficiency"` — the 잔여/맵여부 scenario raw material for the QA round.
- `GET /api/transfer-plan/validate?ref_table=dt_map&map_key=LOT-A_05` → status `warnings`
  (non-blocking), **V6 fired through the live API** on the marker row ("값 '2' ... STACK 0(상태
  표시 값)인데 구역에 자재가 있습니다 — MID: MID9 ..."), marker's `MID9` produced no lookup, no
  demand, no rollup row; the real DOE derived required 2576 (=644×4) vs available 840 →
  `qty_shortage` fired correctly.

**The isolated stack on :8081 is RUNNING and left in place** (declaration + scratch data intact)
for the QA round.

### Doc corrections

CONFIG_GUIDE §5.8's claimed shape `bin_map: {table, columns: {lot, slot, x, y, bin}}` **was
accurate** — verified live. What it did NOT say (and now does):
- `docs/guide/CONFIG_GUIDE.md` §5.8: STACK 0 marker semantics on the `stack` row; V1~**V6**;
  bin_map paragraph now states the M1-delegation caveat + the inline-`source`/`origin_log`
  requirement + that the shape was E2E-verified on :8081. Header badge updated.
- `docs/spec/MAP_EDITOR_SPEC.md`: §6 layer-structure row (marker), §6.0-bis retitled V1~V6 with
  a V6 row (suppression scope), §6.1-bis bin_map delegation caveat. Header badge updated.
- History: `docs/history/20260728_091500_u9_stack0_marker_v6_server_u8_binmap_e2e.md` + index
  regenerated (230 entries).

## Suite

`PYTHONIOENCODING=utf-8 conda run -n assy_manager python -m pytest server/tests/ -q` →
**820 passed** (test file grew from 24 to 29 tests, so the pre-change baseline count was 815;
`test_doe_zone_model.py` alone: 29 passed, 9/9 mutations killed and re-verified green after restore).

## Modified files

- `server/transfer_plan.py` — marker semantics (see table above)
- `server/tests/test_doe_zone_model.py` — v3 scoring + marker axes
- `docs/guide/CONFIG_GUIDE.md`, `docs/spec/MAP_EDITOR_SPEC.md` — living docs
- `docs/history/20260728_091500_...md` + regenerated `docs/history/README.md`
- (isolated, not repo) `dev_env/config/transfer_plan_config.json`, assy_qa scratch rows

## Open items / next steps

- **Escalation for lead**: if live ever wants the dt BIN axis, the dt stage must be converted to
  an inline `source` in the LIVE config (site decision — which table really carries core BINs;
  `dt_map.val` is the origin-core identifier live, so it is NOT the answer there). The
  `origin_log` self-join pattern for root sources may deserve first-class documentation or a
  relaxation of the origin_log degradation rule for core-kind stages — boundary-adjacent, so I
  changed no code there.
- The isolated dt stage now behaves slightly differently from live dt (inline vs M1 reshape) —
  by design for this E2E; QA should know.
- `_stage_role_statuses` does not surface `bin_map`/`lot_membership` connection status in
  `/stages` roles — a UI could not tell today whether the BIN axis is wired without asking for
  bins. Candidate small follow-up.

## Proposed memory lessons (server-pm)

1. Trap: declaring `bin_map` on a `source_config_ref` (M1-delegated) stage does nothing — that
   path answers bins with unconditional `unavailable` before ever consulting `_bin_axis_binding`.
   Correct: BIN axis requires an inline `source` block, and reliable per-BIN numbers additionally
   require `origin_log` connected (for a root source, a self-join binding is legitimate).
2. Trap: assy_qa snapshot tables have no identity defaults (`row_id` is plain varchar, no
   sequence) — direct seeding must supply `row_id` (uuid4) explicitly or the insert fails.
