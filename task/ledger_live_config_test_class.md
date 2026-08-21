# The live-config test class — a full count

**Measurement only.** Nothing in `server/` or `server/tests/` was changed. No fix is proposed
here; the lead rules on the remedy.

Ordered by the lead in `task/IMPLEMENTER_ORDERS.md` (cb9bc7f8):

> 전수로 센다 — 라이브 설정(`load_setup` 등)을 읽는 테스트가 «몇 개»이고
> 그중 «값을 손으로 박은» 것이 몇 개인가

---

## What counts as "live"

Two files, both **gitignored**, both edited by the owner from the screen:

| file | `.gitignore` line | who edits it |
|---|---|---|
| `server/config/ontology/ledger_config.json` | 61 `server/config/ontology/*` | the owner, from the ontology screen |
| `server/config/table_config.json` | 52 `server/config/*` | the owner, from the admin screen |

`load_setup()` reads **both** — the second through `live_physical_catalog()`, which
`load_setup` calls whenever `catalog=` is omitted. So a test that only says `load_setup()` has
taken a dependency on two owner-edited files, not one.

A third, older file — `server/config/ledger_config.json` (the *legacy* `ledger.config`
grammar, not the ontology one) — is also live and gitignored, and `ledger.config.load()`
falls back to `config/sample/ledger_config.json.sample` when it is absent. It is counted
separately at the end because its absence-fallback makes it a different risk.

The **sample** is `server/config/sample/ontology/transfer_explorer/ledger_config.json`
(tracked) plus its own catalog `server/tests/support/transfer_explorer_table_config.json`
(tracked), reached through `tests/support/ontology_explorer_sample.load_transfer_sample_setup`.

🔴 **The sample is a different plant, and it shares almost no names with live.** Measured
today:

| | live `server/config/ontology/ledger_config.json` | sample `transfer_explorer/ledger_config.json` |
|---|---|---|
| `sources` | `dt_job`, `lot_event` | `dt_log` |
| `vocabulary` | `derived_from@1`, `has_netdie@1`, `has_wafer@1`, `register@1`, `slot_map@1` | `component_of@1`, `contains_dt_die@1`, `occupies_slot@1`, `transferred_to@1` |
| `entities` | `DTJob@1`, `Lot@1`, `Wafer@1` | `BondComponent@1`, `CoreDie@1`, `DTDie@1`, `DTJob@1`, `FinalChip@1`, `LotSlot@1` |

Only `DTJob@1` appears in both. So "movable to the sample" below never means "the same literal
still passes" — it means **the test's subject exists there in some form**. And the point of the
move is not that the literal disappears: a literal against a *tracked* file only changes when
somebody commits a change to it, which is a review, not a screen edit at 4pm.

For the record, live `lot_event` today reads `identity: ["event_group_key"]`,
`order_by: ["event_time", "row_id"]` — the `txn_seq` → `row_id` edit the lead made is visible
in `order_by`, which is what the four red tests are pinned against.

## How the sweep was done

1. **Static, whole-directory.** All 218 files under `server/tests/` were parsed with an AST
   walk (not a grep of a chosen subset), resolving each test function's body *plus* the
   bodies of the module-level fixtures and helpers it requests, looking for `load_setup`,
   `live_physical_catalog`, `physical_catalog_path`, `DEFAULT_ONTOLOGY_ROOT`,
   `setup_main`, `load_setup_bundle`, `setup_from_document`, and any string naming
   `ledger_config`.
2. **Dynamic, whole-suite.** The full suite (4568 collected tests) was run once under a
   read-only pytest plugin that wraps `io.open`/`builtins.open` and records, per test
   nodeid, every file opened under `server/config/`. This is what catches a reach that no
   grep would find. (Plugin lives in the scratchpad, not in the repo.)

## Pin vs invariant

- **Pin** — an equality against a hard-coded value that comes *from the declaration*: a
  column name, a tuple of columns, a source id, a predicate id, a relation name, a count
  derived from those. Goes red when the owner edits the screen.
- **Invariant** — an equality between two derived things (`{row["source_id"] for row in
  report} == set(setup.source_ids)`). Survives a screen edit. Worked example with its
  reasoning written out: `test_operator_report_is_ready_and_explicitly_non_destructive`.
- **Code literal** — an equality against a refusal `code`/`path`/`message` that the *Python*
  owns (`unknown_field`, `destructive_approval_required`). Not a pin: the screen cannot move
  it. Recorded but not counted as a pin.

### What each instrument is blind to (measured, not assumed)

- The **tracer misses `shutil.copytree`**. Verified directly: wrapping `builtins.open`/`io.open`
  and copying `server/config/ontology/` records **zero** opens on this CPython 3.12.13
  (conda-forge, Windows) — `copyfile` takes a native fast path. So every `copied_root`
  fixture reaches the live file without appearing in the trace.
- The **AST sweep misses an indirect reach** (a helper in another module, a service that
  resolves a path at runtime).

The rows below are the **union** of both, which is why both were run.

---

## The table

Legend for *reaches live*: **L** = live ontology `ledger_config.json`; **C** = live
`table_config.json` (via `live_physical_catalog()`); **copy** = live root copied with
`copytree` and then read from the copy — still a live dependency, because the copy is a copy
*of the owner's current file*.

### `server/tests/test_ledger_setup_boundary.py` — 20 functions / 23 cases

| test | how it reaches live | pins a literal? | what literal | movable to sample? | if not, why live |
|---|---|---|---|---|---|
| `test_one_file_is_the_only_entry_and_compiles_deterministically` | `load_setup()` ×2 + direct read of `L` | **no — invariant** | — | **yes** | — (works on any root; live adds nothing) |
| `test_loaded_setup_carries_the_adaptation_of_the_live_table_config` | `load_setup()` + `physical_catalog_path()` (L, C) | **partly** | `"lot_event"` as the relation key; `row_id` + its unique index | **yes**, with `lot_event`→any declared relation | — |
| `test_a_tables_section_in_the_ledger_file_is_refused_by_name` | `copied_root` (copy of L) + `live_physical_catalog()` (C) | code literal only | `unknown_field`, `ledger_config.tables` | **yes** | — |
| `test_operator_report_is_ready_and_explicitly_non_destructive` | `load_setup()` (L, C) | **no — invariant** (the worked example) | `readiness == "ready"` is live-dependent; the rest is code literal | **yes** | — |
| 🔴 `test_existing_cursor_selects_only_physical_lot_event_columns` | `load_setup()` (L, C) | **YES** | the 8-tuple `lot_id, event_type, slotnumbers, waferids, parent_lot, child_lot, txn_seq, event_time` | **yes** | — |
| 🔴 `test_live_physical_batch_normalizes_then_uses_stage6_compiler_path` | `load_setup()` (L, C) | **YES** | `atom_count == 10`, `molecule_count == 1`, predicate set `{register, has_wafer, derived_from, slot_map}`, `source_who == "lot_event"`, and the frame's 8 column names | **yes** | — |
| 🔴 `test_selected_execute_reuses_preview_candidates_and_existing_store_transaction` | `load_setup()` (L, C) | **YES** | `cursor_value == {"event_time": …, "txn_seq": "R2"}` — the cursor **column names** | **yes** | — |
| `test_unknown_source_is_rejected_by_name` | `load_setup()` (L, C) | code literal only | `unknown_source`, `sources.unknown` | **yes** | — |
| `test_cutover_module_exposes_no_reset_or_legacy_removal_capability` | **does not reach live** | no | — | n/a | n/a |
| `test_backfill_runs_the_ontology_root_without_being_asked_to` | `backfill.run(ontology_root=DEFAULT_ONTOLOGY_ROOT)` → `load_setup` (L, C) | **YES, one** | `source="lot_event"` must be a declared source | **yes** | — |
| `test_v2_backfill_refuses_reset_controls_before_store_access` | same (L, C — confirmed by trace: `backfill.run` calls `load_setup` at line 277, *before* `_require_declared_source`) | code literal + **soft pin** | `destructive_approval_required`; but `lot_event` must still be declared, or `unknown_source` fires first and the assertion fails on the wrong code | **yes** | — |
| `test_existing_legacy_cursor_shape_blocks_v2_before_source_read` | same (L, C) | **YES** | the fake cursor `{"event_time": …}` is "wrong shape" only relative to the declared cursor; path `ledger_cursor.lot_event.cursor_value` | **yes** | — |
| `test_operator_cli_has_no_legacy_escape_hatch` | **path only** — `run` is monkeypatched; no file is read (confirmed: absent from trace) | no | — | n/a | asserts the CLI default *is* the live root — that is the point |
| `test_operator_cli_blocks_reset_and_replay_before_io` ×2 | **does not reach live** | code literal only | — | n/a | n/a |
| 🔴 `test_existing_other_snapshot_cursor_blocks_before_source_read` | `backfill.run(ontology_root=DEFAULT_ONTOLOGY_ROOT)` (L, C) | **YES** | fake cursor `{"event_time": …, "txn_seq": "R2"}` — the declared cursor columns | **yes** | — |
| `test_verify_without_root_still_reads_the_live_config` | `setup_main([])` (L, C) | no (path identity) | — | **no** | its whole subject is "no `--root` reads the live root"; and it asserts the live config **validates** |
| `test_verify_with_root_reads_the_draft_and_says_which_file_it_read` | `copied_root` (copy of L) + C | code literal only | — | **partly** — needs *a* valid root; sample would do, but the contrast is against the live path | contrast assertion `!= DEFAULT_ONTOLOGY_ROOT` needs the live path (not its content) |
| `test_verifying_a_draft_does_not_touch_the_live_config` | reads the live bytes before/after (L, C) | **no — invariant** (`before == after`) | — | **no** | it is an assertion *about the live file* |
| `test_a_wrong_root_is_a_named_refusal_not_a_traceback` ×3 | `copied_root` (copy of L), content never read | code literal only | — | **yes** | — |
| `test_verify_reports_every_problem_not_only_the_first` | **sample only** — `SAMPLE_ROOT` + monkeypatched `live_physical_catalog` | derived from the sample at runtime (`sorted(raw[...])[0]`) | — | already there | the docstring states the reason: the live root is hand-edited and gitignored |

**File totals (pytest collects 23 cases):** **18 reach live**, of which **7 pin a declaration
literal** (4 of them are the four the lead reddened today), **3 are pure invariants**, 8 assert
only code-owned literals. 5 do not reach live at all, and one of those
(`test_verify_reports_every_problem…`) is already on the sample — the second worked example of
the shape the lead wants.

### `server/tests/test_ledger_registration_probe.py` — 6 functions / 15 cases

Every case reaches live: the module's helper `_plan_with_probe` calls `load_setup()` and then
mutates `bundle["sources"]["lot_event"]` in memory. Confirmed on both instruments.

| test | how it reaches live | pins a literal? | what literal | movable to sample? | if not, why live |
|---|---|---|---|---|---|
| `test_the_declaration_reproduces_the_retired_literals_exactly` ×5 (`split`, `merge`, `split_child_row_missing`, `track_in`, `blank_and_padded`) | `load_setup()` (L, C) | **YES** | `sources["lot_event"]` must exist; module constant `LOT_EVENT_PROBE` names `lot_id/parent_lot/child_lot/waferids`, types `Lot@1`/`Wafer@1`, separator `":"` | **yes** — the frames are the module's own, only the *host source* comes from live | — |
| `test_the_probe_is_a_superset_so_an_extra_column_cannot_move_atoms` | same | **YES** | same columns + `txn_seq` + `CL-2601-007-A1` | **yes** | — |
| `test_a_missing_separator_would_probe_the_unsplit_string` | same | **YES** | `waferids`, `"W31:W32:W33"` | **yes** | — |
| `test_no_probe_answers_None_rather_than_an_empty_set` | same | **YES, one** | `sources["lot_event"]` | **yes** | — |
| `test_a_malformed_probe_is_refused_at_load_with_its_own_code` ×6 | same | mixed | refusal codes are code literals; `lot_id`/`child_lot`/`Lot@1` are declaration literals | **yes** | — |
| `test_the_shipped_config_still_loads_without_a_probe` | `load_setup()` (L, C) | **YES** | `source_plans["lot_event"].driver.registration_probe == ()` | **no** | its subject is literally "adding the field did not invalidate **the operator's** root" |

**File totals:** 15 cases, **15 reach live** (confirmed on both instruments), **15 pin a
declaration literal**, **0 invariants**, **1 must stay live** (and only that one).

⚠️ This file is the largest single concentration of the class and it is **not** in the lead's
red four — it is green today only because `lot_event` still declares those four columns. A
screen edit that renames `waferids`, or removes `lot_event`, reddens all 15 at once.

### `server/tests/test_ontology_config_explorer.py` — 54 functions / 55 cases

Three distinct ways in. `active_setup` is a **module-scoped** fixture calling `load_setup()`, so
the trace records the live read only against the first test that used it — the other eleven
depend on it just as hard. `copied_root` is `copytree` of the live root (tracer-blind, see
above). And two tests reach the live `table_config.json` **indirectly**, through the explorer
service, while pointing the ontology root at `tmp_path` — the AST sweep would not have found
those.

| test | how it reaches live | pins a literal? | what literal | movable to sample? | if not, why live |
|---|---|---|---|---|---|
| `test_actual_snapshot_enumerates_every_registry_and_declaration` | `active_setup` (L, C) | **mixed** | the bijection sum is a model invariant; but `expected` hard-codes 9 node ids (`predicate\|slot_map@1`, `entity\|Lot@1`, `profile\|lot_event#profile`, `mapping\|lot_event#profile#mapping:split_slot_carry`, `preparer\|lot_event#preparation`, `mapper\|lot_event#mapper`, `source_plan\|lot_event`, `binding\|…#binding:subject`, `table\|lot_event`) | **yes** | — |
| `test_every_resolved_edge_has_symmetric_used_by_and_exact_pointer` | `active_setup` (L, C) | **mixed** | symmetry loop is an invariant; then pins `mapping\|lot_event#profile#mapping:split_slot_carry → predicate\|slot_map@1` and the exact pointer string | **yes** | — |
| `test_actual_round_trip_source_profile_mapping_predicate` | `active_setup` (L, C) | **YES** | three edge triples naming `lot_event`, `split_slot_carry`, `slot_map@1` | **yes** | — |
| `test_view_uses_one_context_token_and_kind_specific_integrity` | `active_setup` (L, C) | **YES, one** | `selection="entity\|Lot@1"` | **yes** | — |
| `test_search_is_server_paged_and_deterministic` | `active_setup` (L, C) | **YES** | `query="lot"` must match **more than 2** nodes in the live root | **yes** | — |
| `test_reference_extraction_is_registry_driven_for_transfer_fixture` | `active_setup` (L, C) — despite the name, this is the **live** root | **YES** | `sources["dt_job"]["bind"]["mappings"]["register"]` and its `bind.occurred_at` / `bind.subject.keys.dt_job` | **yes**, but the source is `dt_log` in the sample, not `dt_job` | — |
| `test_authorable_sections_match_where_the_index_actually_puts_things` | `active_setup` (L, C) | **mostly invariant** | one soft pin: `len(AUTHORABLE_SECTIONS & observed) >= 3` — a floor measured on the live root | **yes**, if the sample declares all three kinds | — |
| `test_referenced_declaration_refuses_removal_and_names_who_points_at_it` | `active_setup` (L, C) | **no — invariant** (derives the subject, asserts non-vacuity) | — | **yes** | — |
| `test_a_source_plan_holds_its_profile_and_nothing_points_back` | `active_setup` (L, C) | **no — invariant** (loops every source plan) | — | **yes** | — |
| `test_derivations_rebuild_by_force_what_the_operator_typed_by_hand` | `active_setup` + direct read of `L` + `live_physical_catalog()` | **one field name** | `source["map"]["input_columns"]`; also asserts the live bundle validates | **no** | its stated subject is the acceptance question — "does the screen reproduce **the live artifact**" |
| `test_every_deficit_lands_on_a_field_rather_than_a_loose_error_list` | direct read of `L` + `live_physical_catalog()` | **YES** | `sources.dt_job.bind.mappings.counted.bind.value`, `sources.lot_event.bind.mappings.in_slot.bind.slot`, `blocked == {"sources"}` | **yes** | — |
| `test_column_candidates_are_three_universes_and_not_one` | direct read of `L` + `live_physical_catalog()` | **YES** | `sources.lot_event.read.identity`, `.read.order_by`, `sources.lot_event.prepare.output_columns` | **yes** | — |
| `test_draft_save_keeps_active_bytes_and_valid_preview_is_separate` | `copied_root` (copy of L) + C | **YES** | `predicate\|derived_from@1` must exist **and** carry `object.qualifiers` | **yes** | — |
| `test_invalid_signature_is_classified_with_json_pointer` | `copied_root` + C | **YES** | `predicate\|has_wafer@1` + `object.qualifiers.required` | **yes** | — |
| `test_catalog_declaration_is_read_only_and_unknown_selection_fails_closed` | `copied_root` + C | **YES** | `table\|lot_event` | **yes** | — |
| `test_invalid_draft_falls_back_to_active_without_fake_preview` | `copied_root` + C | **YES** | `predicate\|derived_from@1` | **yes** | — |
| `test_stale_draft_is_labeled_stale_in_active_fallback` | `copied_root` + C | **YES** | `predicate\|derived_from@1` | **yes** | — |
| `test_changed_target_is_labeled_conflict_not_plain_stale` | `copied_root` + C | **YES** | `predicate\|derived_from@1` | **yes** | — |
| `test_review_revision_is_immutable` | `copied_root` + C | **YES** | `predicate\|derived_from@1` | **yes** | — |
| `test_activation_is_cas_atomic_and_matches_reviewed_preview` | `copied_root` + C | **YES** | `predicate\|derived_from@1` + `object.qualifiers` | **yes** | — |
| `test_a_refused_convergence_still_keeps_what_was_written` ×2 | `copied_root` + C | **YES** | `derived_from@1` + `vocabulary["derived_from@1"]["object"]["qualifiers"]["optional"]` | **yes** | — |
| `test_api_returns_structured_context_and_strict_draft_contract` | `copied_root` + C | **YES** | `predicate\|slot_map@1` | **yes** | — |
| `test_deletion_preview_names_the_declaration_that_stops_being_read` | `copied_root` + C | **no — invariant** (derives the predicate/reader pair from the document; the docstring says why) | — | **yes** — and the docstring already argues the case | — |
| `test_authoring_answers_on_a_blank_root_where_the_compiled_view_cannot` | ontology root is `tmp_path`, but the service reads the **live `table_config.json`** (C) — trace only | no | — | **yes** (inject a catalog) | — |
| `test_the_whole_walk_works_on_a_freshly_bootstrapped_config` | same — `tmp_path` root, live `C` | no | — | **yes** (inject a catalog) | — |

**File totals:** 55 cases; **26 reach live**, of which **20 pin a declaration literal**,
**3 are pure invariants**, 1 is mixed with a soft count floor, and 2 touch only the live
catalog with no declaration assertion. 12 cases are already on the **sample**
(`transfer_sample_setup`) and 17 use only in-test fixtures.

⚠️ Ten of the twelve `copied_root` cases hang on the single predicate id `derived_from@1`.
Deleting or renaming that one word from the screen reddens ten tests that have nothing to do
with it.

### `server/tests/test_ledger_v2_pg.py` — 9 cases, 1 in the class

| test | how it reaches live | pins a literal? | what literal | movable to sample? | if not, why live |
|---|---|---|---|---|---|
| `test_stage7_manifest_selected_lot_event_uses_existing_store_cursor_transaction` | `backfill.run(ontology_root=DEFAULT_ONTOLOGY_ROOT)` (L, C) | **YES** | creates a `lot_event` table with the 8 declared columns; `molecules == 1`, `inserted == 10`, `cursor["txn_seq"] == "R2"` | **yes** | — |

The other 8 PG cases build their own bundle root and are not in the class.
**Not observed at runtime on this box** — the whole file skipped (no PostgreSQL), so this row is
static only. It carries the *same* `txn_seq` pin as the lead's red four and would go red on a PG
box today.

### The legacy grammar — `server/config/ledger_config.json`

A different live file: `ledger.config.load()` with no argument, which falls back to the tracked
`config/sample/ledger_config.json.sample` when the live file is absent. **It is absent on this
box**, so every one of these read the sample during the sweep; on a box where the operator has
one, they read live.

| test | how it reaches live | pins a literal? | what literal | movable to sample? | if not, why live |
|---|---|---|---|---|---|
| `test_ledger_transfer_unit.py::test_the_live_declaration_validates_and_declares_this_source` | `ledger_config.load()` | **YES** | `"dt_log"`, `SOURCE_KIND_TRANSFER`, the derivation triple, `{"Wafer"}` | **yes** (it already resolves to the sample here) | its name claims the live declaration |
| `test_ledger_observed_unit.py::test_the_lineage_declaration_still_validates_unchanged` | `ledger_config.load()` | **YES** | `lot_event`→`lineage`, `void_obs`→`observation`, `["first_sight","observation_row"]` | **yes** | — |
| `test_ledger_admin_setup.py::test_the_previews_translator_version_is_the_one_a_real_run_would_stamp` | `ledger_config.load()` ×2 | **no — invariant** (two translator versions compared), with a `.get("lot_event") or {…}` default | — | **yes** | — |
| `test_ledger_trace_contract.py::test_every_declared_derivation_is_explicitly_classified` | `_declared_configs()` — reads `.sample` **and** the live file if present | **no — invariant**, and the good pattern: it iterates every source of every config | — | n/a | it is *designed* to also see the live file, deliberately (docstring) |
| `test_ledger_trace_contract.py::test_the_confirmed_derivations_are_ranked_by_the_resolver_not_just_listed` | same | **no — invariant** | — | n/a | same |

### The wider live-config surface (adjacent, not the ledger class)

The completed whole-suite trace recorded these opens under `server/config/` (samples excluded).
Reported because the lead's question was "라이브 설정을 읽는 테스트", and these are live,
gitignored, screen-edited files too. **Counts are cases that actually opened the file**, so
`copytree` and cached module fixtures are under-counted here for the same reason as above.

| live file | cases | test files | note |
|---|---|---|---|
| `audit_history_config.json` | 461 | 46 | the largest live-config dependency in the suite |
| `ingestion_settings.json` | 241 | 23 | the leak `tests/isolated_data_root.py` was written for |
| `table_config.json` | 101 | 19 | includes every `load_setup()` |
| `virtual_join_rules.json` | 82 | 41 | |
| `map_overlay_config.json` | 52 | 6 | |
| **`ontology\ledger_config.json`** | **33** | **3** | 15 probe + 13 boundary + 5 explorer — the directly-observed part of the 60 |
| `suggest_config.json` | 25 | 1 | |
| `enrichment_rules.json` | 16 | 7 | |
| `effort_metric.json` | 7 | 2 | |
| `chain_rules.json` | 4 | 2 | |
| `supervisor_status.json` | 3 | 1 | |
| `auto_update_control.json` | 2 | 2 | |
| `scheduler_status.json`, `maps.json`, `mechanism_models.json` | 1 each | 1 each | |

Deliberate live readers of `table_config.json` outside the ledger:
`test_declared_key_indexes.py::test_live_config_every_table_is_decided`,
`test_dt_standard_map_mapper.py::test_the_live_dt_map_declaration_is_the_physical_unit`,
`test_enrichment.py::test_the_live_declaration_is_read_rather_than_backfilled`, and
`test_void_schema.py` (at import).

One more that belongs in the class by shape even though it is not the ledger:
`server/tests/test_void_schema.py` reads the live `table_config.json` **at import time**
(module constant `DECLARED`, deliberately, with the reason written out) and pins `void_obs` /
`inspection_run`. Its `test_the_sample_declares_the_same_thing_as_the_live_config` is an
explicit live-vs-sample drift pin — the one case in the sweep where reading live *is* the
assertion, and it says so.

🔴 `test_declared_key_indexes.py::test_live_config_every_table_is_decided` is the **third worked
example** of the shape the lead is asking for, and it is the most complete one: it reads the
live file, `pytest.skip`s when there is none, sweeps **every** declared table, and derives every
expectation from the row it is looking at. It pins nothing and it still refuses.

---

## Totals

| | cases |
|---|---|
| collected in `server/tests/` | **4568** |
| reach the live **ontology** `ledger_config.json` (or a `copytree` of it) | **60** |
| — of those, **pin a declaration literal** | **43** |
| — of those, **pure invariants** | **6** |
| — of those, mixed (invariant + a soft count floor measured on live) | **1** |
| — of those, assert only code-owned literals / no declaration assertion | **10** |
| reach only the live `table_config.json` (no ontology read) | **2** in the explorer + ~30 incidental elsewhere |
| reach the legacy live `server/config/ledger_config.json` (sample-fallback today) | **5** |

Per file:

| file | cases | reach live | pin | invariant |
|---|---|---|---|---|
| `test_ledger_setup_boundary.py` | 23 | 18 | 7 | 3 |
| `test_ledger_registration_probe.py` | 15 | 15 | 15 | 0 |
| `test_ontology_config_explorer.py` | 55 | 26 | 20 | 3 (+1 mixed) |
| `test_ledger_v2_pg.py` | 9 | 1 | 1 | 0 |
| **ledger/ontology total** | **102** | **60** | **43** | **6** (+1 mixed) |

The four the lead reddened today are 4 of the 43. **The pin count is ten times the size of the
symptom**, and the largest single block (15 cases in `test_ledger_registration_probe.py`) is
green only by accident of which column the lead happened to change.

## Could move to the sample with no loss of what it catches

**55 of the 60.** Every row above whose "movable" column says **yes** — i.e. all of them except
the five in-the-60 rows listed under "must genuinely read live" below (the other three entries
in that list are outside the 60: two are the legacy grammar, one reads no file at all). The three worked examples
already prove the move is possible without losing the guard:
`test_verify_reports_every_problem_not_only_the_first` (sample root + monkeypatched catalog),
the twelve `transfer_sample_setup` cases in the explorer, and
`test_ledger_implementations.py::test_transfer_sample_draft_validates_unchanged_with_a_non_lot_event_implementation`
(found by the tracer, reads the sample ontology config directly).

The mechanical requirement is already in place: `load_setup(root, catalog=…)`,
`setup_from_document(document, catalog=…)` and the `setup_loader` seam on
`OntologyExplorerService` all let a caller supply both halves, and
`tests/support/ontology_explorer_sample.py` already carries the sample's own
`table_config.json`.

## Must genuinely read live — 8 cases (5 of them inside the 60)

| test | in the 60? | why |
|---|---|---|
| `test_ledger_setup_boundary.py::test_verify_without_root_still_reads_the_live_config` | yes | its subject *is* "no `--root` means the live root", and it asserts the live config validates |
| `test_ledger_setup_boundary.py::test_verifying_a_draft_does_not_touch_the_live_config` | yes | asserts the live file's bytes are unchanged — a fact about that file |
| `test_ledger_setup_boundary.py::test_verify_with_root_reads_the_draft_and_says_which_file_it_read` | yes | needs the live **path** for the `!=` contrast (not its content) |
| `test_ledger_registration_probe.py::test_the_shipped_config_still_loads_without_a_probe` | yes | its subject is "the optional field did not invalidate **the operator's** root" |
| `test_ontology_config_explorer.py::test_derivations_rebuild_by_force_what_the_operator_typed_by_hand` | yes | the acceptance question is whether the screen reproduces **the live artifact** with less work |
| `test_ledger_setup_boundary.py::test_operator_cli_has_no_legacy_escape_hatch` | no — path only, no read | asserts the CLI default is the live root |
| `test_ledger_trace_contract.py::test_every_declared_derivation_is_explicitly_classified` | no — legacy grammar | designed to see the live file *in addition to* the sample; already pins nothing |
| `test_ledger_trace_contract.py::test_the_confirmed_derivations_are_ranked_by_the_resolver_not_just_listed` | no — legacy grammar | same |

Note the shape: of the eight that must read live, **six assert nothing about the declaration's
content** — they assert a path, a byte-identity, or a sweep. Only
`test_the_shipped_config_still_loads_without_a_probe` and
`test_derivations_rebuild_by_force…` name a declared thing, and both name it only as the host
they operate on.

## Could not determine

| item | why |
|---|---|
| `test_ledger_v2_pg.py::test_stage7_manifest_selected_lot_event_uses_existing_store_cursor_transaction` | **skipped on this box** (no PostgreSQL) — classified statically only; not observed reaching live |
| `test_ledger_l1_pg.py` (3 cases naming `ledger_config`) | **resolved statically, not at runtime** — they build `_profile_mapper_cfg()` themselves and only call `ledger_config.validate(cfg)`, so they are **not** in the class. Unconfirmed at runtime because the whole file skips (no PostgreSQL). Separately noted while reading them: `backfill.run(ledger, cfg, source="lot_event", …)` passes `cfg` in the position that now means `source`, which `run()`'s positional guard refuses by name — not measured, because the file never ran here |
| whether the **legacy** `server/config/ledger_config.json` exists on the owner's box | it does not exist here, so the 5 legacy rows resolved to the tracked `.sample` during the sweep. If the owner has one, those 5 are live-reaching and 2 of them pin `dt_log`/`void_obs` literals |
| whether `test_search_is_server_paged_and_deterministic`'s `total > 2` is a real floor | it depends on how many live nodes contain the substring "lot" — measured true today, not derived |
| the whole-suite pass/fail summary from the traced run | `conda run` died printing its own output (`UnicodeEncodeError: 'cp949'`) after the tests finished, so the summary line was lost. The **trace file is complete** (1090 records, every test ran). The four ledger/ontology files were therefore re-run directly with the env interpreter — see below |

## Current state of the 102 ledger/ontology cases (re-measured)

```
4 failed, 89 passed, 9 skipped        (the 9 skips are all of test_ledger_v2_pg.py — no PostgreSQL)
FAILED test_ledger_setup_boundary.py::test_existing_cursor_selects_only_physical_lot_event_columns
FAILED test_ledger_setup_boundary.py::test_live_physical_batch_normalizes_then_uses_stage6_compiler_path
FAILED test_ledger_setup_boundary.py::test_selected_execute_reuses_preview_candidates_and_existing_store_transaction
FAILED test_ledger_setup_boundary.py::test_existing_other_snapshot_cursor_blocks_before_source_read
```

Exactly the four the lead named, and no others — **left red on purpose.** The other 39 pins are
green today only because the lead's edit happened to be `order_by`. They are the same class,
not a different one.

## What was NOT done

No fix is proposed and none was applied. No test file, no `server/` module, and no config was
modified; no `git` state-changing command was run. The four tests the lead named are still red.
The only file this round wrote is this one.

⚠️ **The tree moved under the measurement.** At session start `git status` showed
`server/dt_map_derivation.py`, `server/map_alignment.py`, `server/map_overlay.py` modified. By
the end it also showed `server/ledger/source_preparation.py` (+27) and
`server/mappers/ledger_v2_lot_event_role_mapper.py` (+13) — another lane's edits, landing
mid-sweep and inside the ledger. The counts above are static facts about test files, which
nobody touched, so they stand; but the **red/green measurement is a snapshot** of a tree that
was being written to while it was taken.

