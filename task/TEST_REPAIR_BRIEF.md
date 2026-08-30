# Test repair lane — the 21 reds left on `main`

**Baseline (measure this first; do not trust this file's number):**
```
cd server
C:/Users/kk980/anaconda3/envs/assy_manager/python.exe -m pytest tests/ -q -p no:randomly
```
At `50be7eb6` this gave **21 failed · 4,072 passed · 167 skipped · 1 xfailed** in 17 minutes.
The lens matters: this is the WHOLE suite with random ordering off. A `-k` selector gives a
different number and a different set — an earlier round reported "9" from `-k ledger` and
the truth was 49. Report the lens with every count you give.

Interpreter: the conda env above, invoked directly. `conda run` hangs on this box.

---

## The two rules that decide most of this round

### 1. The live declarations are NOT yours. They are gitignored and the owner writes them.

```
server/config/*.json            IGNORED   (only config/sample/*.sample is tracked)
server/config/ontology/*.json   IGNORED
server/mappers/*.py             IGNORED   (only mappers/*.py.sample is tracked)
```

Several of these failures come from a test reading the LIVE file on this box and finding
something it did not expect. **Do not edit a live file to make a test pass.** A prior round
overwrote the owner's live config twice believing it was its own work.

If a test fails because live and `.sample` disagree, the standing rule is that the sample
follows the live file in the same commit as the live change — but that rule is for whoever
made the live change. You did not make it. Measure the diff, name it, report it. Do not
sync a sample whose diff is somebody's debug edit.

Worked example, already measured, so you need not redo it:

```
test_dt_alignment_metadata_mapper::test_live_mapper_and_tracked_sample_are_byte_identical
   the diff is ONE line: sample has print(payloads), live has print(rule)
   both are debug prints; the live file is gitignored and belongs to the operator
   => report it. Touch neither side.
```

### 2. A pin whose subject changed is a ruling, not a repair.

Some of these tests exist to PIN something — an identity, a column contract, a rule count.
When the declaration moved out from under the pin, rewriting the pin to match makes the test
green and destroys the thing it protected. The sentence survives and the claim becomes false.

Worked example, already measured:

```
test_void_base_join_fixture::test_base_columns_are_not_key_material
   the test pins    bonding_log composite_key_source == [bond_lot, bond_slot, bond_x, bond_y]
   live AND sample                                   == [base_lot, base_slot, bonding_index, b_wx, b_wy]
   the two files AGREE, so this is not live drift — the table was redefined,
   most likely by 347c9069 "the transfer log gets its own table, and the seeder aims at it"
   the pin's own docstring says re-keying moves 5,296 rows
   => STOP. Report as a ruling for the lead. Do not update the pin.
```

**How to tell a repair from a ruling:** if going green requires changing what the test
ASSERTS (not how it sets up), it is a ruling. If it requires changing a fixture, an import,
a path, or the code under measurement, it is a repair. When unsure, it is a ruling.

---

## The 21

Group them yourself from your own run; this listing carries ids only, so a stale grouping
cannot mislead you.

```
tests/test_composite_key_prefetch_budget.py::test_inserting_new_rows_still_probes_once_per_row
tests/test_config_reload_integrity.py::test_h3_cross_directory_replace_through_real_watchdog
tests/test_config_resolve_report_contract.py::test_the_vocabulary_is_borrowed_from_the_runtime_not_invented
tests/test_dt_alignment_metadata_mapper.py::test_live_mapper_and_tracked_sample_are_byte_identical
tests/test_dt_inventory_metadata_mapper.py::test_copies_dt_log_metadata_to_matching_inventory_job
tests/test_dt_inventory_metadata_mapper.py::test_skips_other_metadata_targets_invalid_json_and_duplicate_jobs
tests/test_dt_map_derivation.py::test_all_three_declared_rules_ship_disabled
tests/test_dt_standard_map_mapper.py::test_the_live_dt_map_declaration_is_the_physical_unit
tests/test_dual_stack_bind.py::test_the_launcher_default_is_the_dual_stack_host
tests/test_entrypoint_import_isolation.py::test_no_server_module_imports_the_web_entrypoint
tests/test_frame_confirmation_meta.py::test_the_confirmation_records_the_valid_die_area_it_was_scored_against
tests/test_job_column_from_config.py::test_standard_map_scopes_the_replace_by_the_configured_name
tests/test_ledger_setup_boundary.py::test_live_physical_batch_normalizes_then_uses_stage6_compiler_path
tests/test_ledger_setup_boundary.py::test_selected_execute_reuses_preview_candidates_and_existing_store_transaction
tests/test_map2_seam_contract.py::test_scoring_rebuilds_a_full_meta_per_candidate
tests/test_ontology_config_explorer.py::test_derivations_rebuild_by_force_what_the_operator_typed_by_hand
tests/test_ontology_config_explorer.py::test_every_deficit_lands_on_a_field_rather_than_a_loose_error_list
tests/test_prod_import_env.py::test_every_runtime_import_resolves_without_server_scripts_on_the_path
tests/test_trace_fixture.py::test_emitted_columns_satisfy_the_ingestion_contract
tests/test_void_base_join_fixture.py::test_base_columns_are_declared
tests/test_void_base_join_fixture.py::test_base_columns_are_not_key_material
```

### What is already known about four of them

```
test_prod_import_env
   two imports do not resolve, and both sites are under server/_archive/ :
      _archive/tests/test_audit_changeset.py:45      audit_changeset
      _archive/tests/test_enrichment_actions.py:4    enrichment_actions
   the modules they name were archived, so the scanner is scanning archived tests.
   Measure what the scanner globs before changing either side.

test_entrypoint_import_isolation
   ledger_api/ontology_config_explorer_router.py:240 and :257 do `import main as app_main`
   inside function bodies. The test's own message states the remedy: move the shared symbol
   to a non-entry-point module and re-export it from main.py. This one is a real repair.

test_ontology_config_explorer (the two remaining)
   ONE is the in_slot bind that lot_event's event-unit mapper cannot express. That is the
   same cause as the open A-1 agenda item and is NOT yours — leave it and say so.
   The OTHER reports the live declaration failing its own validator:
      bundle.sources.dt_job.map.unit.columns: group_by columns must be mapper input
      columns: ['dt_job']
   That is a live-declaration question. Report it; do not edit the live file.
```

---

## Scope

```
DO      repair tests and non-live code where the failure is mechanical
DO      report, with numbers, every failure that turns out to be a ruling or a live-file question
DON'T   edit server/config/**  or  server/mappers/**   (gitignored live files)
DON'T   change what a test ASSERTS in order to make it pass
DON'T   add tests, guards, helpers, or refactors nobody asked for
DON'T   use `git add -a` or `-A`; add explicit paths, and put the same paths on `git commit`
```

Commit messages go through `git commit -F <file>`, never `-m` with backticks in the text —
the shell executes what is inside them.

## Stop conditions — report, do not decide

```
- the fix needs a live gitignored file edited
- the fix needs an assertion, a pinned identity, or a declared contract changed
- the fix grows past the module the failure is in
- two failures disagree about what the correct behaviour is
```

## Report back

One line per test:

```
<test id>   REPAIRED <what changed>  |  RULING <the question, with the two numbers posing it>  |  NOT-MINE <why>
```

Then the closing full-suite run with its lens, and the list of paths you committed. Do not
report a count you did not measure at the end.
