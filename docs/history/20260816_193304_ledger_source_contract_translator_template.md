# Ledger Source Contract and translator template

## Request

Unify the authoring workflow that previously required reading `ledger_config`, a Python
translator, and the vocabulary separately.  For source shapes that still need Python,
provide a copyable design-pattern example where the author changes only the domain parts.

## Decision

- Keep runtime responsibilities separate, but compile them into one operator-facing
  **Source Contract**: physical columns → translator profile → every possible Claim → live
  vocabulary signature.
- Validate every possible branch statically.  A 20-row dry run remains the empirical proof;
  it cannot prove that an unsampled branch is legal.
- Prefer `declared` for one-row-to-N-Claim sources.  Use the Template Method only for
  grouping, positional pairing, or external lookups that are clearer in Python.
- A coded translator author changes four blocks: names, possible emissions, molecule
  grouping, and `claim_drafts`.  Time, provenance, first-sight registration, raw reference,
  all-or-nothing refusal, and registration rollback remain in the base class.
- Example profiles are not runtime-registered.  Copying the example alone must write zero
  rows; runtime registration and page-boundary wiring remain explicit architecture work.

## Implementation

- `server/ledger/source_contract.py`: compiles source declaration, executable translator
  profile, source-enabled subjects/derivations, and live vocabulary signatures.
- `server/ledger/translator_pattern.py`: safe Template Method and immutable `ClaimDraft`.
- `server/ledger/examples/grouped_translator_template.py`: four-block grouped job example.
- `server/ledger_admin.py`: refuses translator/vocabulary conflicts before dry run and
  exposes translator metadata with each source kind.
- `server/main.py`: source dry-run responses include the Source Contract next to actual
  sample atoms.
- `client2/src/ledger_setup*.js`: renders profile, molecule, configured-by location,
  possible Claims, and resolved vocabulary signature.
- `lot_event_translator.py`: source provenance is no longer hardcoded to `lot_event`,
  datetime molecule refs are stable, and `emit_register: false` is now actually enforced.
- `backfill.py` and `observability.py`: an unstarted timestamp cursor no longer compares a
  timestamp column to the empty string; datetime cursor values are serialized safely.

## Verification

- Python compilation: passed for all changed ledger/server modules.
- Focused ledger contract suite: **119 passed**.
- New Source Contract/template tests: **9 passed**, including an actual
  `emit_register: false` translation, late-generator refusal rollback, and timestamp-cursor
  first-page/probe behavior.
- Client contract checks: **7/7 passed**; gated harnesses: **51/51 green**. Five existing
  harnesses remain on the repository's declared known-red list.
- Vite production build: **103 modules transformed, completed successfully**.
- A broader earlier admin batch still had four pre-existing `WaferLeg` expectation failures;
  this change does not modify that retired-model debt.

## Documentation maintenance

- Rewrote `CONFIG_GUIDE`, `LEDGER_GUIDE`, and `ONTOLOGY_LEDGER_SETUP` as current-task guides, removing
  incident timelines, commit narratives, duplicated contracts, and environment snapshots.
- Kept referenced section numbers stable so ownership, QA, and architecture links continue
  to resolve.
- Added Source Contract ownership, code-map, API parameter, QA, and SSOT entries.
- Added a repository rule: living guides contain current choices and procedures; historical
  evidence belongs in `docs/history/`.
