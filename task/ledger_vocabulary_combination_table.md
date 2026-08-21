# Ledger vocabulary — what can be declared vs. what the compiler reads

Measurement only. No code changed. Measured 2026-08-21 against the working tree at
`C:\Users\kk980\Developments\assyManager`.

Axes as ordered: `object.kind` (none | value | entity_ref) × `object.qualifiers` (empty | filled)
× `subjects` (empty | filled) × `object.types` (empty | filled) = 24 cells.

**Two spellings of "types is empty" were measured separately**, because the validator answers
them differently: `types` **absent** and `types` present as `[]`. The 24-row table uses
*absent* for the 빔 column and the `[]` result is recorded in a footnote row per cell.

**A fourth `object.kind` exists.** `setup_bundle._OBJECT_KINDS` (setup_bundle.py:125) is
`{none, entity_ref, value, event_ref}`. `event_ref` was not on the ordered axis; it is measured
in an appendix at the end, because it changes the count of "declarable but unread" cells.

## Method

- **Declarable?** — a synthetic one-predicate bundle was fed to
  `setup_bundle.validate_bundle_errors(bundle, catalog={})` for each cell. Bundle shape:
  `setup_version: 5`, two entities (`Lot@1`, `Wafer@1`), `sources: {}`, one vocabulary entry
  `p@1` with `status: active`, `layer: raw`. Empty `sources` isolates the vocabulary rules from
  every source/binding/catalog rule. Probe script kept at
  `C:\Users\kk980\AppData\Local\Temp\claude\C--Users-kk980-Developments-assyManager\bb9c475d-6f85-4fe4-bc97-76584eed703b\scratchpad\probe.py`.
- **Compiler reads?** — traced and then mutated. See the "Reader map" section below.
- **Live n / sample n** — read from `server/config/ontology/ledger_config.json` (the live,
  gitignored file, named by path, not discovered) and
  `server/config/sample/ontology/transfer_explorer/ledger_config.json`.

## Section 1 — Declarability (measured, all 48 variants)

Only **7 of 48** variants are accepted; **5 of them** fall inside the three-kind axis as ordered
(the other two are `event_ref`, see Section 5). Rows below are compressed with `*` where the
refusal is the same across the remaining spellings; every one of the 48 was run.

| kind | qualifiers | subjects | types | validator |
|---|---|---|---|---|
| none | empty | filled | absent | **ACCEPT** |
| none | empty | filled | `[]` | refuse `invalid_predicate @ …object.types` — `'none' object must not declare entity types` |
| none | empty | filled | filled | refuse `invalid_predicate @ …object.types` |
| none | empty | empty | absent | refuse `invalid_type @ …subjects` — `must be a list with at least one item` |
| none | filled | filled | absent | refuse `invalid_predicate @ …object.qualifiers` — `none object cannot declare payload qualifiers` |
| none | filled | filled | filled | refuse (qualifiers + types, two refusals) |
| none | filled | empty | * | refuse (qualifiers + subjects, and types when present) |
| value | empty | filled | absent | **ACCEPT** |
| value | empty | filled | `[]`/filled | refuse `invalid_predicate @ …object.types` — `'value' object must not declare entity types` |
| value | empty | empty | absent | refuse `invalid_type @ …subjects` |
| value | filled | filled | absent | **ACCEPT** |
| value | filled | filled | `[]`/filled | refuse `invalid_predicate @ …object.types` |
| value | filled | empty | * | refuse `invalid_type @ …subjects` (+ types when present) |
| entity_ref | empty | filled | absent | refuse `missing_field @ …object.types` — `entity_ref object requires types` |
| entity_ref | empty | filled | `[]` | refuse `invalid_type @ …object.types` — `must be a list with at least one item` |
| entity_ref | empty | filled | filled | **ACCEPT** |
| entity_ref | empty | empty | filled | refuse `invalid_type @ …subjects` |
| entity_ref | filled | filled | absent | refuse `missing_field @ …object.types` |
| entity_ref | filled | filled | `[]` | refuse `invalid_type @ …object.types` |
| entity_ref | filled | filled | filled | **ACCEPT** |
| entity_ref | filled | empty | filled | refuse `invalid_type @ …subjects` |

Three structural facts fall out, and they are what collapse 48 variants to 6:

1. **`subjects` empty is never declarable, for any kind.** `_validate_vocabulary`
   (setup_bundle.py:930) calls `_nonblank_list` with the default `allow_empty=False`.
   That kills half of every axis at once — 24 of 48 variants, 12 of the 24 ordered cells.
2. **`types` is a hard function of `kind`, in both directions.** `entity_ref` without `types`
   is `missing_field` (setup_bundle.py:940-942); any other kind *with* `types` — including an
   empty list — is `invalid_predicate` (setup_bundle.py:945-947). So `kind × types` has exactly
   two live squares out of six, and `types` is never a free choice.
3. **`kind: none` + qualifiers is refused by name** (setup_bundle.py:962-966,
   `none object cannot declare payload qualifiers`).

## Section 2 — Reader map (who reads which field, and where it branches)

Traced by exhaustive grep across `server/` (tests excluded), then confirmed by execution.
"Branch" = the value selects between outcomes. "Copy" = the value is carried into a
structure but no rule tests it.

| field | branch sites | copy sites |
|---|---|---|
| `object.kind` | `setup_bundle.predicate_claim` (setup_bundle.py:455-466 — picks the object Role and gates the emitted qualifiers); `roleframe._object_value` (roleframe.py:558); `roleframe.validate_role_frame` (roleframe.py:1100, 1104, 1125-1143 — payload shape + refusal); `config_authoring._vocabulary_fields` (config_authoring.py:678 — whether a `types` row is drawn) | `setup_registry._compile_vocabulary` (:805) |
| `subjects` | `setup_bundle._cross_vocabulary` (:1547 — `unknown_entity_type`); `setup_bundle._cross_binding_entity_types` (:1643 — `invalid_entity_ref`, subject binding outside the signature); `roleframe.validate_role_frame` (:1095 — runtime refusal); `config_explorer` (:826-831 — `subject_entity` graph edge) | `setup_registry._compile_vocabulary` (:804); `config_authoring._vocabulary_fields` (:662, form row) |
| `object.types` | `setup_bundle._cross_vocabulary` (:1554, **entity_ref only**); `setup_bundle._cross_binding_entity_types` (:1651 — target binding outside the signature); `roleframe.validate_role_frame` (:1105, **entity_ref only**); `config_explorer` (:834-839 — `object_entity` graph edge) | `setup_registry._compile_vocabulary` (:806) |
| `object.qualifiers.required` | `setup_bundle.predicate_claim` (:467-468 — an `attribute` Role, `required: True`) and (:463-466 — an `emit.object.qualifiers` entry, **only when kind != none**); `setup_bundle._cross_profile_contract` (:1575-1599 — `unknown_role` / `missing_required_role` on every source binding); `roleframe.validate_role_frame` (:1111-1118 — `missing_required_payload`); `config_authoring._mapping_fields` (:881-903 — the binding rows the source screen lays out) | `setup_registry._compile_vocabulary` (:807) |
| `object.qualifiers.optional` | same as `required`, with `required: False` and `${name}?`; `roleframe` (:1112, 1119-1123 — widens `allowed_qualifiers`, `unknown_payload_field`) | `setup_registry._compile_vocabulary` (:808) |

Every one of the five fields is also inside `source_cursor_fingerprint`
(setup_registry.py:766-769, `_semantic_plain(snapshot.vocabulary[predicate_id])`), so editing
any of them resets that source's cursor. That is a **copy**, not a read, by the definition the
order gives — it does not select an outcome, it only says "something moved".

### Measured: `predicate_claim` reads exactly two of the four axes

Swept all 24 ordered cells through `setup_bundle.predicate_claim` and compared outputs:

- Changing `subjects` (빔 ↔ 참) changed the output in **0 of 12** pairs.
- Changing `types` (빔 ↔ 참) changed the output in **0 of 12** pairs.
- Changing `kind` and `qualifiers` changed it every time.

So the central derivation is blind to `subjects` and `object.types` by construction. Those two
are read only by the validator's cross-checks, by `roleframe` at runtime, and by
`config_explorer`'s graph — never by the thing that lays out the slots.

## Section 3 — The 24-row table

빔 = empty (`[]` for lists; for `types`, **absent** — the `[]` spelling is refused separately, see Section 1).
참 = filled (`qualifiers.required: ["slot"]`, `subjects: ["Lot@1"]`, `types: ["Wafer@1"]`).

| # | kind | qual | subj | types | declarable? | compiler reads it? | live n | sample n |
|--:|---|---|---|---|---|---|--:|--:|
| 1 | none | 빔 | 빔 | 빔 | **no** — `invalid_type @ …subjects` | n/a | 0 | 0 |
| 2 | none | 빔 | 빔 | 참 | **no** — `…subjects` + `invalid_predicate @ …object.types` | n/a | 0 | 0 |
| 3 | none | 빔 | 참 | 빔 | **yes** | yes — `kind` and `subjects` both branch | 1 | 0 |
| 4 | none | 빔 | 참 | 참 | **no** — `invalid_predicate @ …object.types` (`'none' object must not declare entity types`) | n/a | 0 | 0 |
| 5 | none | 참 | 빔 | 빔 | **no** — `…object.qualifiers` + `…subjects` | n/a | 0 | 0 |
| 6 | none | 참 | 빔 | 참 | **no** — three refusals | n/a | 0 | 0 |
| 7 | none | 참 | 참 | 빔 | **no in the file** — `invalid_predicate @ …object.qualifiers` (`none object cannot declare payload qualifiers`) · **yes in the form** — see Section 4.1 | **partly** — `predicate_claim` puts the qualifier in `roles`, and drops it from `emit` | 0 | 0 |
| 8 | none | 참 | 참 | 참 | **no** — qualifiers + types | n/a | 0 | 0 |
| 9 | value | 빔 | 빔 | 빔 | **no** — `invalid_type @ …subjects` | n/a | 0 | 0 |
| 10 | value | 빔 | 빔 | 참 | **no** — subjects + types | n/a | 0 | 0 |
| 11 | value | 빔 | 참 | 빔 | **yes** | yes — `kind`, `subjects` | 1 | 0 |
| 12 | value | 빔 | 참 | 참 | **no** — `invalid_predicate @ …object.types` (`'value' object must not declare entity types`) | n/a | 0 | 0 |
| 13 | value | 참 | 빔 | 빔 | **no** — `invalid_type @ …subjects` | n/a | 0 | 0 |
| 14 | value | 참 | 빔 | 참 | **no** — subjects + types | n/a | 0 | 0 |
| 15 | value | 참 | 참 | 빔 | **yes** | yes — `kind`, `subjects`, and the qualifier reaches both `roles` and `emit` | **0** | **0** |
| 16 | value | 참 | 참 | 참 | **no** — `invalid_predicate @ …object.types` | n/a | 0 | 0 |
| 17 | entity_ref | 빔 | 빔 | 빔 | **no** — `missing_field @ …object.types` + `…subjects` | n/a | 0 | 0 |
| 18 | entity_ref | 빔 | 빔 | 참 | **no** — `invalid_type @ …subjects` | n/a | 0 | 0 |
| 19 | entity_ref | 빔 | 참 | 빔 | **no** — `missing_field @ …object.types` (`entity_ref object requires types`) | n/a | 0 | 0 |
| 20 | entity_ref | 빔 | 참 | 참 | **yes** | yes — all three declared fields branch | 1 | 3 |
| 21 | entity_ref | 참 | 빔 | 빔 | **no** — types + subjects | n/a | 0 | 0 |
| 22 | entity_ref | 참 | 빔 | 참 | **no** — `invalid_type @ …subjects` | n/a | 0 | 0 |
| 23 | entity_ref | 참 | 참 | 빔 | **no** — `missing_field @ …object.types` | n/a | 0 | 0 |
| 24 | entity_ref | 참 | 참 | 참 | **yes** | yes — all four declared fields branch | 2 | 1 |

Live total 5 = rows 3 (`register@1`) + 11 (`has_netdie@1`) + 20 (`derived_from@1`) + 24
(`has_wafer@1`, `slot_map@1`). Sample total 4 = row 20 (`contains_dt_die@1`,
`occupies_slot@1`, `component_of@1`) + row 24 (`transferred_to@1`).

**5 of 24 cells are declarable. 19 are refused.** `subjects: 빔` alone kills 12 of the 24;
the `kind × types` coupling kills 6 more; `kind: none` + qualifiers kills the last one.

## Section 4 — Cells to rule on

Within the 24 ordered cells there is **no cell where the file may declare it and no consumer
reads it.** Every field the validator lets into the file is read by something that branches on
it. But three findings need a ruling, and one of them is the lead's.

### 4.1 — Row 7: declarable on the SCREEN, refused by the validator

This is the finding the order named, and it reproduces exactly:

    predicate_claim("p@1", {"object": {"kind": "none",
                                       "qualifiers": {"required": ["slot"],
                                                      "optional": ["note"]}}})
      roles                    -> ['note', 'occurred_at', 'slot', 'subject']
      emit.object.qualifiers   -> ABSENT   (the object_kind != "none" gate, setup_bundle.py:462)

    _compile_vocabulary -> PredicateDescriptor.required_qualifiers = ('slot',)
    _compile_claims     -> ClaimDescriptor.emission.qualifiers     = {}
    roleframe.py:1113   -> required_qualifiers <= carried  ==  False,  missing ['slot']

`validate_bundle_errors` refuses that vocabulary entry (`invalid_predicate @
bundle.vocabulary.p@1.object.qualifiers`), so **live reachability through a validated config is
0 — confirmed.** But it is reachable through the authoring screen, today, and by design:

- `ledger_skeleton.json` puts a `when` gate only on `object.types` (`{field: kind, is:
  entity_ref}`, :223). `object.qualifiers` is `required: true` with **no gate**, so the
  skeleton-generated form offers `required`/`optional` boxes for **every** `object.kind`,
  `none` included.
- `config_explorer_service.authoring()` (config_explorer_service.py:525-554) **deliberately
  bypasses validation** — its own docstring says the authoring screen "is needed exactly when
  it does not [validate]". It reads the raw file and hands it to `authoring_plan`.
- `predicate_claim` is documented as tolerant for that reason (setup_bundle.py:440-442), and
  `config_authoring._mapping_fields` (:881) lays out one binding row per Role it returns.

So the sequence is: an author types `slot` into the qualifiers box of a `kind: none` predicate →
the source screen lays out a `slot` binding row → the author binds a column to it → the save is
refused, at `bundle.vocabulary.<id>.object.qualifiers`, not at the row they were just filling.
**That is a square a person can fill that is never carried, and the refusal points elsewhere.**

*What a refusal would have to say, at the row:*
`bundle.sources.<src>.bind.mappings.<sentence>.bind.slot` —
"낱말 `<id>`의 목적어가 `none`이라 `slot`은 원자에 실리지 않는다. `object.kind`를
`value`/`entity_ref`로 바꾸거나 `object.qualifiers.required`에서 `slot`을 뺀다."

The same fact could instead be said one step earlier, by gating the form's qualifiers boxes —
but `ledger_skeleton.json`'s `when` is `{field, is: <single value>}` equality at all six sites,
with no negation and no `in`, and "not none" is not expressible in it. **Not proposing an
operator — the lead already ruled that out.** Stating it so the ruling has the constraint in
front of it.

### 4.2 — Row 15 is declarable, fully read, and has never been written

`value` + qualifiers is accepted by the validator, carried into `roles` **and** `emit`, and
checked by `roleframe`. Live n = 0, sample n = 0. Not a defect — an untravelled path. Worth
naming because rows 7 and 15 differ only in `object.kind`, and row 15 is the working shape a
refusal for row 7 would point an author toward.

### 4.3 — `object.qualifiers.optional` is live-count 0 everywhere

Across both files, all nine predicates declare `optional: []`. So `predicate_claim`'s `${name}?`
branch (setup_bundle.py:465, 469-470) and `roleframe`'s `unknown_payload_field` widening
(roleframe.py:1112, 1119-1123) are exercised **0 times** in live and sample config. Declarable,
read, never used.

## Section 5 — Appendix: the fourth object kind

`event_ref` is in `_OBJECT_KINDS` (setup_bundle.py:125) and was not on the ordered axis.
Measured on the same sub-cells:

| kind | qual | subj | types | declarable? | compiler reads it? | live n | sample n |
|---|---|---|---|---|---|--:|--:|
| event_ref | 빔 | 참 | 빔 | **yes** | yes — `predicate_claim` gives it a `value` Role of kind `identity` (`_OBJECT_VALUE_ROLE_KINDS`, setup_bundle.py:421); `roleframe.py:1137` wraps it as `{"event": …}` | **0** | **0** |
| event_ref | 참 | 참 | 빔 | **yes** | yes — qualifiers reach both `roles` and `emit` | **0** | **0** |
| event_ref | * | 빔 | * | **no** — `invalid_type @ …subjects` | n/a | 0 | 0 |
| event_ref | * | * | 참 or `[]` | **no** — `invalid_predicate @ …object.types` | n/a | 0 | 0 |

So the true declarable count is **7 combinations, not 5**, and two of the seven have never been
written in either file. `event_ref` is fully wired end to end — this is not a dead kind, it is
an unused one.

## Section 6 — Could not measure

1. **End-to-end compile of the live config was not run.** `compile_setup_snapshot` needs
   `table_config.json` and the trusted-implementation registry resolved against this box, and
   this box is not production — a compile here would measure this machine, not the operator's.
   Measured instead at the layer below: `validate_bundle_errors`, `_compile_vocabulary`,
   `_compile_claims`, and `predicate_claim`, all executed directly. Every "compiler reads it"
   verdict above is either an executed measurement or a cited branch site, never an inference
   from the fingerprint.
2. **The authoring screen was not driven in a browser.** Section 4.1's claim that the form
   offers a qualifiers box under `kind: none` is read from `ledger_skeleton.json` (no `when` on
   `object.qualifiers`) plus `config_explorer_service.authoring()`'s documented validation
   bypass. The pixel behaviour was not observed. If the ruling depends on what the operator
   actually sees, that needs a browser pass.
3. **`roleframe.validate_role_frame` was not executed** on a row-frame for row 7 — that path
   needs a compiled snapshot and a live mapper. What was executed is the input to its check:
   `required_qualifiers = ('slot',)` against `emission.qualifiers = {}`, which is the exact
   comparison at roleframe.py:1113. The refusal it would raise is stated, not observed.
4. **Live counts are of the working tree as of 2026-08-21.** This is a shared tree with other
   people editing it; `server/config/ontology/ledger_config.json` is gitignored and was read by
   path, not discovered by scan. It held 5 vocabulary entries at read time. The five
   `ledger_config.json.before_*` siblings in that directory were **not** counted.
