# Server M3 Report — Auto-register `wafer_map_metadata` for ingested maps

Status: **DONE** (full suite green x2, isolated E2E PASS with negative control)
Baseline noted as `55ddffd` in the brief; work done on the shared main working tree, which also carries a concurrent agent's in-flight edits to `transfer_plan.py` / `map_overlay.py` / `bonding_plan.py` — **I did not touch those files** (read/import only).

## 1. Mechanism (file:line)

| Piece | Location |
|---|---|
| Registrar module (new) | `server/map_meta_registrar.py` (362 lines) — `MapMetaCollector`, `compose_map_id`, `synthesize_grid_meta`, `auto_register_enabled` |
| Watcher hook: collector construction (file-boundary knob/config snapshot, D1) | `server/parsers/directory_watcher.py:1686` |
| Watcher hook: O(rows) bbox accumulation per chunk (normalized updates) | `server/parsers/directory_watcher.py:1724` |
| Watcher hook: post-commit absent-only flush, failure-isolated | `server/parsers/directory_watcher.py:1783-1795` |
| Chain worker hook (per target table, validated batch items) | `server/chain_ingestion_worker.py:445-455` |
| Knob doc + default | `server/config/ingestion_settings.json.sample` (`auto_register_map_meta`, default true, hot at next work unit) |
| Guide section | `docs/guide/INGESTION_GUIDE.md` §1.10 |

Design points:
- **Trigger**: table declares `map_key_columns` AND resolves a coordinate binding via `map_overlay.resolve_binding` (declared > derived — the shared rule; imported, not duplicated). Registry-shaped tables (`map_split_registry`: keys but no x/y) are skipped naturally.
- **Honest minimum meta**: batch bbox grid with `grid_start_x/y = min x/y` (deliberate divergence from the editor's standard choice's `start=0`: the editor shifts loaded coordinates under that interactive choice; ingested rows keep raw coordinates, so the frame must start where the data starts), rotation 0, side front, mask-neutral physical vocabulary mirroring map_editor.js `[fix C]` (chip 1x1 / offset 0 / margin 3 / dia = max(300, ceil(2*(halfdiag+4)))). `auto_registered: true` provenance field (additive).
- **Absent-only**: existence check first; existing rows never written. Created rows carry source `auto_map_meta` (priority 99 = lowest), so a later user edit always wins in the layering model.
- **Scale (10M discipline)**: one indexed `business_key_val IN (...)` existence query per distinct key set per work unit (1000-key chunks), never per row; process-lifetime known-present cache (bounded 200k, cleared on overflow — worst case one redundant indexed check). Cache caveat: a meta row hard-deleted mid-run is not re-registered until process restart (documented in module).
- **Events**: meta rows go through `crud.apply_batch_updates` (normal write path) → outbox events flow; the chain worker's undelivered-broadcast sweep delivers `batch_refresh_required` for `wafer_map_metadata` to clients. No feedback loop: registrar explicitly refuses `META_TABLE` (belt) and the meta table declares no `map_key_columns` (suspenders); chain-side creations are additionally bounded because a second pass is absent-only.
- **Failure isolation**: a registrar crash is logged and swallowed in both writers — file/chain ingestion (already committed) completes normally. Covered by test.

## 2. Composition site for tomorrow's 7b integration

- **The one composition call site**: `server/map_meta_registrar.py` → `compose_map_id(key_columns, row)` (line ~131, `TODO(7b)` marker at line 135). It is the only place this feature composes a map_id; route it through the shared canonicalization fn when 7b lands.
- Current semantics (pinned by `test_map_id_composition_pinned_for_7b`): `'_'`-join of `map_key_columns` values, each normalized by `crud.clean_str_value` (integral floats lose `.0`, strings trimmed). Divergence from the editor's lenient join, kept deliberately: a missing/empty key part returns None (row contributes nothing) — ingestion must not register a partial identity.
- The meta row's bk is composed by crud's composite assembly (`target_table + '_' + map_id`); the registrar mirrors it only for the indexed existence check (commented).

## 3. E2E transcript (isolated, :8082 — :8081 was occupied by the already-running dev_env stack, untouched)

Environment: own data root under session scratchpad (`ASSY_DATA_ROOT`), `DATABASE_URL=sqlite:///...e2e.db`, uvicorn `main:app` on 127.0.0.1:8082 inline-watcher mode. Config contained ONLY `e2e_map` (bonding_map-shaped: composite bk [base,x,y], `map_key_columns:["base"]`) + `wafer_map_metadata`. Zero live writes; `/tables` served exactly those two tables (proof of isolation). Port check first: 8081 LISTEN (dev_env api pid 9812), 8082 free.

1. `GET /tables/wafer_map_metadata/data` → `total: 0`.
2. Dropped `e2e_fresh.csv` (key `E2E_FRESH_01`, x∈{3..9}, y∈{2..6}, 5 rows) into `ingestion_workspace/e2e_map/raws/`.
3. Watcher ingested: `e2e_map total: 5`; meta appeared: `map_pk=e2e_map_E2E_FRESH_01`, `grid_metadata = {"grid_cols": 7, "grid_rows": 5, "grid_start_x": 3, "grid_start_y": 2, "grid_y_invert": false, "rotation": 0, "side": "front", "phys_wafer_dia": 300, "phys_chip_x": 1, "phys_chip_y": 1, "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3, "auto_registered": true}` — exact file bbox.
4. Browser (`/map-editor` on :8082): selected `e2e_map`, base `E2E_FRESH_01`, Load → **no choice modal** (`choice-modal` computed display `none`), toast "5셀 로드 완료", editor adopted the auto-registered frame (panel cols=7 rows=5 startX=3 startY=2, painted cells at raw coordinates).
5. **Negative control (proves the check is not vacuous + knob hot reload live)**: wrote `{"auto_register_map_meta": false}` into the isolated `ingestion_settings.json` mid-run, dropped `e2e_ctrl.csv` (fresh key `E2E_CTRL_02`) → rows ingested (total 7), **no meta row** (still total 1), and loading `E2E_CTRL_02` in the editor showed the "No Grid Metadata Detected" choice modal — the exact friction M3 removes.
6. Teardown: server killed, 8082 free, browser tab closed. Repo tree clean of E2E artifacts (all under scratchpad).

## 4. Tests

New file `server/tests/test_map_meta_registrar.py` (12 tests, `mmrauto_test_*` prefix):
- `test_absent_key_creates_meta_with_bbox` — absent→created; non-trivial bbox (start 2,1) pins the axis; mask-neutral phys asserted
- `test_synthetic_dia_circumscribes_large_grids` — dia leaves the 300 floor on a 1000x1000 grid (1423)
- `test_existing_meta_is_never_overwritten` — seeded user meta (rotation 90) byte-identical after re-ingest; inequality precondition asserted
- `test_batch_dedup_one_existence_check_per_work_unit` — 5,000 rows / 2 keys → exactly ONE existence SELECT (cursor-event counted); second work unit on cached keys → ZERO
- `test_knob_off_disables_and_rewrites_hot` / `test_knob_non_boolean_falls_back_to_default_on`
- `test_recursion_guard_meta_table_never_self_registers` (belt + suspenders assert) / `test_registry_shaped_table_without_coordinates_is_skipped`
- `test_map_id_composition_pinned_for_7b` — composition pin (see §2)
- `test_watcher_send_to_upsert_registers_meta` — real sqlite E2E through `_send_to_upsert`, incl. idempotent re-ingest
- `test_watcher_meta_failure_does_not_fail_ingestion` — registrar crash swallowed, data lands
- `test_chain_worker_registers_meta` — real `process_chain_transaction_group` run with a mapper rule → meta created from chain-written rows

**Defect-injection proof (memory rule ⓐ)**: two temporary defects were injected and both were caught — (1) `grid_start` forced to 0,0 → 3 tests failed; (2) absent-only filter removed → overwrite test failed. Code restored; both injections verified via test runs, not inspection.

**Suite count**: full suite `conda run -n assy_manager python -m pytest server/tests/ -q` → **905 passed** (run twice, both green; was 893 before this task — +12). Runs included the concurrent agent's in-flight working-tree changes.

## 5. Boundary contracts

No REST signature, WS event, cell shape, or schema contract changed. Meta rows flow through existing tables/events. New knob is additive config.

## 6. History draft (for lead integration — not written to docs/history per tonight's docs ownership)

> feat(ingestion): auto-register wafer_map_metadata for ingested maps (M3) — new `server/map_meta_registrar.py` (absent-only, bbox-honest, mask-neutral synthetic frame mirroring the editor's standard choice); hooks in directory_watcher `_send_to_upsert` and chain worker `process_chain_transaction_group`; knob `auto_register_map_meta` (default ON, hot); one indexed existence check per distinct key + process cache; recursion-guarded; 12 tests incl. defect-injection-verified bbox/absent-only axes; isolated E2E on :8082 (fresh key → meta row → editor opens without choice modal; knob-off control shows the modal).

## 7. Unresolved / next steps

- **7b integration (tomorrow)**: reroute `map_meta_registrar.compose_map_id` through the shared canonicalization fn; the pin test makes it a provable no-op.
- **Docs owned by tonight's docs agent** (I only touched INGESTION_GUIDE per the brief): `guide/CONFIG_GUIDE.md` + `guide/config/` need the new `auto_register_map_meta` knob row; `architecture/backend.md` ingestion section; PRIMITIVES.md entry for "absent-only meta auto-registration"; CODE_MAP anchors for the new module.
- **Backfill is out of scope**: this covers maps ingested from now on; the existing ~390k meta-less bonding_map keys get rows only on re-ingest. If M4 wants a one-shot backfill, it is a separate script decision (lead call).
- Small duplication noted: registrar has a local 10-line `_load_ingestion_settings` (importing `directory_watcher` from the chain worker would drag watchdog + the legacy import shim). Commented in code.
- Lesson proposal (for server-pm memory, lead review): *When mirroring an interactive-UI default into an automated path, check which parts of the default are only valid because the UI transforms the data at the same time* — the editor's standard choice writes `start=(0,0)` but also shifts loaded coordinates; copying the meta without the shift would have mis-framed every auto-registered map. Caught by reading the consumer's load path before mirroring.
