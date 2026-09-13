# Server Report — 7b (canonical key values, server half) + 7c (`transfer_log: "none"`)

Status: **DONE** (full suite 944 passed x2; 3 source-level mutants + 2 in-suite mutation twins all killed; isolated read-only live verification on :8082 — :8081 occupied by dev_env pid 9812, untouched; NO live writes; verification server stopped, port freed).
Baseline `55ddffd`. Work done on the shared main working tree. **Nothing committed — lead reviews the diff** (see §7 for the exact file split between my change set and the concurrent M3 agent's uncommitted change set that shares this tree).

---

## 1. 7b — ONE shared canonicalization function

**Function location:** `server/map_overlay.py`
- `canonical_key_value(value, col_type)` (~line 118) — THE implementation. `number`: integer-parse → str honoring the single-integer-judge semantics (`'01'`/`'1'`/`' 1 '`/`1.0`/`'1.0'` → `'1'`; `'7.5'` kept; unreadable values keep their trimmed original — a lookup misses honestly, never invents a key). `string`/undeclared: trim only (**padding is significant for strings** — by spec). Floats fold their `.0` repr artifact under every type (mirrors `crud.clean_str_value`, which the registration path had pinned).
- `declared_column_type(table, column)` — reads the live `crud.TABLE_CONFIG` singleton through the module attribute (hot-reload safe; it is mutated in place).
- `canonical_bind_value(table, column, value)` / `canonical_role_value(src_cfg, role, value)` — lookup conveniences (no second canonicalization logic).
- `compose_map_id(identity_cols, values, binding)` — the ONE map-identity composer; canonicalizes each component per the **looked-up table's** declared types (the meta row was registered from that table's stored values).

**Composition sites routed (4):**
1. `transfer_plan._origin_map_id` (now a thin wrapper over `compose_map_id`; callers pass the frame-defining/fail table as `binding`) — feeds `_canonical_origin_meta` and `_canonical_fail_set`.
2. `bonding_plan.get_core_summary` (old line 287 single compose → per-source `_map_id_for(src)`; canonical-frame and per-role meta lookups both).
3. `map_meta_registrar.compose_map_id` — the **registration side** (see §3; it carried an explicit `TODO(7b)` addressed to this round).
4. `map_overlay.build_key_filters` — map_key decomposition binds each part canonically (compare-by-decomposition site).

**Pool bind sites routed (16):** every `(lot, slot)` filter in the availability engines now goes through `_identity_filters` / `canonical_role_value`:
- `transfer_plan.py` (13): `_summarize_inline` total_chips / transfer_log / origin_log / self-frame fail / origin_area_map / region-total fetch; `_canonical_fail_set`; `_collect_history`; `_bins_block` (via `_bin_axis_binding`, which now returns `(model, cols, src_cfg)`); `_lot_slots`; `load_source_region` (source_lot/source_slot; ref_table/map_key stay opaque equality by the no-parsing invariant); `_core_region_counts` total + used.
- `bonding_plan.py` (3): map-role counts (~357), used_chips (~412), process_history (~442).

**Deliberately NOT canonicalized:** opaque `map_key`/`target_key` passed whole to `load_map_meta`/`get_overlay` — the server cannot decompose an opaque identity safely (lot may contain `_`); the fix for those lives at composition time (server sites above; client compose is tomorrow's half).

### Cured vs needs-client-half
**Cured by the server half alone:**
- Meta lookups for every identity the SERVER composes: fail-projection frames (`_canonical_fail_set`/`_canonical_origin_meta`), M1 core-summary frames — including the `1.0` Float round-trip axis (number-declared origin_slot returns 1.0 from the ORM; previously composed `LOT_1.0` and silently fell to identity alignment).
- Availability pool binds fed by parsed tokens (validate's demand loop → `get_stage_source_summary`, direct API calls with padded/whitespace tokens) against number-declared and whitespace-padded-vs-string pools.
- **Registration**: raw pre-cast `'01'` arriving for a number-declared key column now registers meta as `LOT_1` (previously `LOT_01` while the stored cell cast to `1` — unfindable forever after).
- Live-verified read-only: whitespace-padded token `' 01 '` now finds TAPE-A/01's 256-chip pool (same numbers as canonical); dt(M1) stage serves the documented 1288/334/124 with `aligned:180` intact.

**Needs the client half (tomorrow):**
- map_id/map_key strings the CLIENT composes and sends whole (`getMapIdFromMeta`-style compose, editor load keys, overlay source keys). The server treats them as opaque; a client-composed `LOT_01` against meta `LOT_1` still misses until the client canonicalizes at compose time.
- Cross-representation string pools (string-declared column storing `'1'` queried with `'01'`): by spec, string padding is data — not fixable by either half; only a declaration change fixes it.

## 2. 7c — `"transfer_log": "none"` declared-absent consumption

Only the **exact string** `"none"` declares it (JSON `null`, absent key, `"None"` → previous `missing` behavior, byte-for-byte — null is indistinguishable from an accidental delete). Constants: `TRANSFER_LOG_NONE` / `STATUS_TRANSFER_UNTRACKED` / `WARN_TRANSFER_UNTRACKED` / `EFFECT_REMAINING_UPPER_BOUND` (transfer_plan.py ~213).

**Response shape for untracked** (`GET /api/transfer-plan/source-summary`):
```
sources.transfer_log      = "connected(untracked)"        (NOT degraded — _status_is_degraded returns False; no source_degraded warning)
chips.transferred         = null                          (unknown — never 0)
chips.remaining           = null
chips.remaining_reliable  = false
chips.remaining_upper_bound = total − |fail-union|        (genuine bound: dropping the used subtraction only raises the value)
warnings += { type: "transfer_untracked", role: "transfer_log",
              status: "connected(untracked)", effect: "remaining_upper_bound", detail: ... }
by_core[i].used = null, by_core[i].remaining = null       (fail/total stay real; both log and area_map paths)
region_chips.transferred = null                           (reliable: false)
bins.entries[i] (when only untracked, per bin):
  { status: "ok", transferred: null, remaining: null, reliable: false,
    transfer_untracked: true, remaining_upper_bound: |bin∩total| − |bin∩fail|,
    reason: "전사 기록이 '없음'으로 선언됨(transfer_log: none) — 잔여는 상한(≤)만 제공" }
  (bin_absent / truncation entries unchanged; when another degradation overlaps, the bound is not claimed — existing unknown handling)
/api/transfer-plan/stages roles.transfer_log = "connected(untracked)"
validate: availability_unreliable's degraded_roles now also names transfer_log via the untracked warning; untracked warnings are excluded from the history-fail rebroadcast.
```
`_bins_block` honesty check (as instructed): with `used_set` empty by declaration, `_region_block`'s remaining degrades to exactly `|bin∩total| − |bin∩fail|` — the union semantics make it a true upper bound, so it is served under its own name, never as `remaining`. `base_reliable` passed to bins now EXCLUDES the untracked cause (`bins_base_reliable`) so the bound is only claimed when untracked is the sole reason.

**Known limitation (decision left to lead):** `scope=lot` (`_merge_bins_over_slots`) treats untracked entries as unreliable → lot-scope bins read `unknown` rather than summing bounds. Summing upper bounds IS a valid upper bound; wiring it is a small follow-up if the site wants `≤N` at lot scope. Also M1 path: `bonding_plan_config.used_chips` has no "none" declaration (spec named the inline `transfer_log` key only) — a core-kind site without a consumption log still reads degraded.

## 3. Territory note (two files beyond the named territory — justification)

- `server/bonding_plan.py`: the named requirement "applied at EVERY server-side point … source-summary pool binds, meta lookups" — the dt stage's source-summary binds and frame lookups live here (M1 delegation). Edits are strictly the compose+bind routing (25 lines).
- `server/map_meta_registrar.py`: **another agent's uncommitted M3 file** — but its `compose_map_id` carried `TODO(7b): route this through the shared canonical … fn` and M3's report §2 explicitly hands the site to this round ("route it … when 7b lands"), with a pin test (`test_map_id_composition_pinned_for_7b`) written to prove the rerouting a no-op for undeclared types. Routed accordingly (signature gained optional `table_name`; sole caller updated); M3's pin test passes unchanged. Without this, ingestion would keep REGISTERING the very identities the lookup half canonicalizes away.

## 4. Tests (39 new; all named)

`server/tests/test_key_canonicalization.py` (28):
- `test_canonical_key_value_matrix` (20 params: padding/whitespace/float-roundtrip/non-integral/unreadable/bool/string-padding-untouched/undeclared/None), `test_nan_and_inf_are_preserved_not_invented`
- Integration + mutation twins (SQLite Float affinity absorbs `'01'`/`' 1 '`, so the engine-independent axes are composition and string-column whitespace — chosen deliberately):
  `test_float_stored_slot_composes_canonical_map_id_and_meta_is_found` (1.0→`CLOT_1`, `aligned:180` engaged) / `test_mutation_raw_composition_loses_the_rotated_fail` (raw-str mutant: eds fail vanishes, identity-by-accident)
  `test_whitespace_padded_token_finds_the_pool` / `test_mutation_raw_bind_misses_the_pool`
- `test_declared_column_type_reads_the_live_table_config`, `test_compose_map_id_canonicalizes_per_binding`, `test_build_key_filters_binds_canonical_literals` (bound literal `'1'` asserted engine-independently), `test_registration_composes_the_same_canonical_identity`

`server/tests/test_transfer_untracked.py` (11):
`test_stages_report_untracked_not_missing`, `test_untracked_serves_upper_bound_not_a_number` (ub=4≠total=8 asserts the fail axis is live; seeded bonding_log rows must be IGNORED — a binding-resolving mutant would emit transferred=3/remaining=2), `test_untracked_by_core_used_and_remaining_are_null`, `test_untracked_region_transferred_is_null`, `test_untracked_bins_serve_per_bin_upper_bounds` (bound=2, not the consumed 1), `test_untracked_bin_absent_is_still_absent`, `test_absent_key_stays_missing`, `test_json_null_stays_missing_not_untracked`, `test_case_variant_is_not_a_declaration`, `test_mutation_untracked_branch_is_load_bearing` (constant repointed → falls to missing).

**Mutation runs (source-level, reverted after each):** M1 bins `untracked=False` → killed by `test_untracked_bins_serve_per_bin_upper_bounds`; M2 `transferred=used_count` → killed by `test_untracked_serves_upper_bound_not_a_number`; M3 `_canonical_fail_set` `binding=None` → killed by `test_float_stored_slot_composes_canonical_map_id_and_meta_is_found`. Reverts verified by suite green afterward.

**Suite count: 944 passed, 0 failed** (`conda run -n assy_manager`, ~100s; includes M3's 20-odd registrar tests unchanged). Live user config audited: this dev machine declares all map key columns `string` → zero behavioral delta here (probes confirmed identical numbers); the number-declared axis is the production site's shape, pinned by tests.

## 5. Config guide + sample (permitted docs scope only)

- `docs/guide/config/transfer_plan_config.md`: two role rows appended — `identity: {compose}` (7b canonicalization row) and `transfer_log` (7c "none" declaration row). Nothing else touched.
- `server/config/transfer_plan_config.json.sample`: `__transfer_log_none_comment` added (code-side artifact).

## 6. Handoff for doc agents (I did not touch these — out of my scope tonight)

- CODE_MAP: `map_overlay.py` +~110 lines (new §: canonical key values; `build_key_filters` semantics), `transfer_plan.py` +~150 (7c constants ~213, `_identity_filters` ~300, `_bin_axis_binding` 3-tuple, `_bins_block` `untracked` param, `_origin_map_id` binding param), `bonding_plan.py` `_map_id_for`, `map_meta_registrar.compose_map_id(…, table_name)`. Hashes in CODE_MAP header are now stale for all four.
- backend.md / DOE band model spec: untracked status vocabulary + `transfer_untracked` warning; PRIMITIVES.md: `canonical_key_value` is a new primitive (key canonicalization) — register it so nobody forks it.
- **History draft (for lead to land with the commit):** `feat(transfer-plan): canonical key values by declared type (7b server half) + transfer_log "none" declared-untracked consumption (7c)` — one shared `map_overlay.canonical_key_value`; 4 composition + 16 bind sites routed incl. registration (M3 TODO honored); untracked = `connected(untracked)` + `remaining_upper_bound` + `transfer_untracked` flag, transferred/by_core-used null, per-bin bounds; 39 tests, 3 mutants killed, suite 944.

## 7. Uncommitted working-tree split (IMPORTANT for the morning merge)

Mine: `server/transfer_plan.py`, `server/map_overlay.py`, `server/bonding_plan.py`, `server/config/transfer_plan_config.json.sample`, `docs/guide/config/transfer_plan_config.md`, new `server/tests/test_key_canonicalization.py`, new `server/tests/test_transfer_untracked.py`, plus a 20-line edit ON TOP of M3's untracked `server/map_meta_registrar.py` (compose routing only).
M3's (already reported DONE in `Server_M3_auto_register_map_meta_report.md`, not mine): `server/parsers/directory_watcher.py`, `server/chain_ingestion_worker.py`, `server/config/ingestion_settings.json.sample`, `docs/guide/INGESTION_GUIDE.md`, new `server/map_meta_registrar.py`, new `server/tests/test_map_meta_registrar.py`.
Suggested sequencing: commit M3 first (its file predates my edit), then mine — or one combined commit; either way the suite is green on the combined tree (that is the state 944 was measured on).

## 8. Memory-lesson proposals (for lead review — not self-added)

1. SQLite numeric affinity silently converts `'01'`/`' 1 '` when the column is Float — a bind-canonicalization mutant is INVISIBLE under SQLite on number columns. Choose mutation axes that are engine-independent (string equality on composed identities; string-declared columns for whitespace) and probe affinity BEFORE writing the mutation twin.
2. `conda run` crashes with a conda error report when the child exits non-zero (e.g., a pytest run with expected failures) — for runs that may fail, invoke the env python directly (`~/anaconda3/envs/assy_manager/python.exe`).
3. Before editing a file in a shared working tree, `git status` FIRST — an untracked file may be a concurrent agent's uncommitted deliverable (M3's registrar here; its in-code TODO + report §2 made the edit a sanctioned handoff, but only the report proved that).
