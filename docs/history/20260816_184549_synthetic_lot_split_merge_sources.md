# 125-wafer SPLIT/MERGE source fixture

## Request

Generate virtual source data for five ROOT LOTs (`NAB123`, `NAB115`, `NAB122`,
`NAB163`, `NAB539`), 25 wafers per root, with SPLIT/MERGE events inside process
`STEP_SEQ` 1..100.  Every child lot must append `TA`, `TB`, `TC`, ... to its root.

## Decision

- The fixture writes the exact current `source_config.xlsx`-derived columns.  It does not
  add `step_seq` to `lot_event`; an event shares `event_time` with the process step it
  precedes.
- Each root performs four splits and four merges at deterministic random steps.  Child
  lots are `<ROOT>TA` through `<ROOT>TD`, and every wafer returns to its root by step 100.
- One split/merge remains two source rows.  Split rows are post-event snapshots; merge
  source/destination rows are pre/post snapshots.  Slot and wafer lists remain positional.
- Generation is staging-only.  It cannot write the owner database or a watched `raws`
  directory.

## Implementation

- `server/source_fixtures/lot_split_merge.py`: generator, invariants, UTF-8 CSV writer.
- `server/scripts/generate_syn_lot_split_merge_sources.py`: thin CLI.
- `server/tests/test_syn_lot_split_merge_source.py`: schema, counts, pairing, and
  reproducibility checks.

## Verification

- Focused pytest: **9 passed**.
- Generated rows: `lot_event=80`, `process_event=12,500`, unique wafers `125`.
- Generated CSV headers equal the current `table_config.json` display columns exactly.
- Python compilation passed for the generator module and CLI.
