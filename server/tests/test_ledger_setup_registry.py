"""Stage 3 tests for config-only registries and immutable setup snapshots."""
from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
import notation_norm

from ledger import setup_bundle as setup_bundle_module
from ledger import setup_registry as setup_registry_module
from ledger.setup_bundle import (
    LedgerSetupBundle,
    LedgerSetupValidationError,
)
from ledger.setup_registry import (
    ClaimDescriptor,
    EntityTypeDescriptor,
    EntityTypeRegistry,
    MapperDescriptor,
    PredicateDescriptor,
    RoleDescriptor,
    SourcePlan,
    TrustedImplementationCatalog,
)
# `validate_bundle` / `load_setup_bundle` here are the bundle suite's catalog-defaulting
# wrappers, NOT the raw `ledger.setup_bundle` functions -- those now refuse by name when
# no physical catalog is supplied.  `DEFAULT_CATALOG` is the fixture plant's physical
# half, written out separately from the bundle under test; see the docstring on
# `logical_catalog` there for why it must never be derived from the bundle.
from test_ledger_setup_bundle import (
    DEFAULT_CATALOG,
    MAPPER_PATH,
    PROFILE_PATH,
    driver_mapper,
    load_setup_bundle,
    logical_bundle,
    objectless_register_bundle,
    reverse_mappings,
    source_profile,
    validate_bundle,
    write_tree,
)
# ⚰️ [총괄 ae3d408ae ③] `verified_join_contract` - the physical verifier's descriptor and its
# issuer - retired with its last product reader (the preparer's compile of verified joins,
# setup_version 6), and with it the three tests that scored the issuer's fence.


def compile_setup_snapshot(bundle, trusted, *, catalog=None):
    """Fixture-defaulting wrapper. Production callers resolve the catalog once in
    `ledger.setup`; here the fixture plant's catalog stands in for `table_config.json`."""
    return setup_registry_module.compile_setup_snapshot(
        bundle, trusted, catalog=DEFAULT_CATALOG if catalog is None else catalog)


def snapshot_compile_errors(bundle, trusted, *, catalog=None):
    return setup_registry_module.snapshot_compile_errors(
        bundle, trusted, catalog=DEFAULT_CATALOG if catalog is None else catalog)


def trusted_implementations():
    return TrustedImplementationCatalog.build(mappers=[("map-transition-role", 1)])


def snapshot(bundle=None, trusted=None, *, catalog=None):
    """`catalog` names the physical plant the bundle is judged against; omitting it uses
    the fixture plant.  A bundle describing a DIFFERENT plant (see the DT chain fixture in
    `test_ledger_source_preparation`) passes its own, exactly as a different deployment
    would ship its own `table_config.json`."""
    raw = bundle or logical_bundle()
    return compile_setup_snapshot(
        validate_bundle(raw, catalog=catalog),
        trusted or trusted_implementations(),
        catalog=catalog,
    )


def test_registry_tree_compiles_predicate_claim_role_and_source_plan():
    compiled = snapshot()

    predicate = compiled.vocabulary["moves_to@1"]
    entity = compiled.entities["InputEntity@1"]
    # `compiled.packs["movement@1"].claims["transition"]` until 2026-08-21. One registry,
    # keyed by the PREDICATE, because that is the declaration the Claim is derived from.
    claim = compiled.claims["moves_to@1"]
    role = claim.roles["subject"]
    source = compiled.source_plans["input_rows"]

    assert isinstance(predicate, PredicateDescriptor)
    assert predicate.version == 1
    assert isinstance(entity, EntityTypeDescriptor)
    assert entity.identity_keys == ("input_id",)
    assert isinstance(claim, ClaimDescriptor)
    assert claim.claim_id == "moves_to@1"
    assert claim.config_path == "bundle.vocabulary.moves_to@1"
    assert isinstance(role, RoleDescriptor)
    assert role.allowed_binding_kinds == ("entity",)
    assert isinstance(source, SourcePlan)
    # Keyed by the SOURCE now: the mapper is that source's clause, not a named
    # declaration it points at.
    assert source.driver.mapper is compiled.mappers["input_rows"]
    assert source.profile is compiled.profiles["input_rows"]


def test_objectless_emission_compiles_without_an_object_role():
    compiled = snapshot(objectless_register_bundle())
    emission = compiled.claims["register@1"].emission

    assert compiled.compiler_contract_version == 4
    assert compiled.vocabulary["register@1"].object_kind == "none"
    assert emission.object_kind == "none"
    assert emission.object_role is None


def test_role_binding_kinds_use_the_same_predicate_contract_as_validation():
    """Was `..._use_the_same_pack_contract_...`.

    It narrowed the Claim's `event_key` role to `allowed_binding_kinds: ["column"]` and
    asserted the compiler read the same list the validator did.  A derived Role declares
    no such list, so what the two now have to agree on is the DEFAULT for the role kind --
    which is the same `role_binding_kinds` call on both sides, and the same statement.
    """
    compiled = snapshot()

    roles = compiled.claims["moves_to@1"].roles
    assert roles["event_key"].kind == "attribute"
    assert roles["event_key"].allowed_binding_kinds == ("column", "constant")
    assert roles["subject"].allowed_binding_kinds == ("entity",)


def test_vocabulary_qualifier_contract_survives_compilation():
    """Was `test_vocabulary_and_symbolic_role_contracts_survive_compilation`.

    DELETED with the pack section: the symbolic half. A `symbolic` Role with an
    `allowed_values` roster could only be declared at `packs.*.claims.*.roles.*`, and
    `predicate_claim` derives no such kind -- see the deletion note in
    `test_ledger_setup_bundle.py`. The vocabulary half is the part that had a declaration
    of its own all along, so it keeps its assertions unchanged.
    """
    bundle = logical_bundle()
    bundle["vocabulary"]["moves_to@1"]["object"]["qualifiers"] = {
        "required": [], "optional": ["event_key", "movement_kind"]}
    source_profile(bundle)["mappings"]["main_transition"]["bind"]["movement_kind"] = {
        "kind": "constant", "value": "pick",
    }

    compiled = snapshot(bundle)
    predicate = compiled.vocabulary["moves_to@1"]

    assert predicate.required_qualifiers == ()
    assert predicate.optional_qualifiers == ("event_key", "movement_kind")
    role = compiled.claims["moves_to@1"].roles["movement_kind"]
    assert role.kind == "attribute"
    assert role.required is False
    assert role.allowed_values == ()


def test_registries_and_descriptors_are_recursively_immutable():
    compiled = snapshot()

    with pytest.raises(TypeError):
        compiled.entities._items["Other@1"] = compiled.entities["InputEntity@1"]
    with pytest.raises(TypeError):
        # `key_types` was retired 2026-09-09 (no reader, ever). `keys` is its
        # replacement HERE for the reason that matters to this test: it is a frozen
        # SEQUENCE on the same descriptor, so the recursive-immutability claim is still
        # scored one level below the entity rather than at it.
        compiled.entities["InputEntity@1"].identity_keys[0] = "integer"
    with pytest.raises(TypeError):
        compiled.profiles["input_rows"].mappings["main_transition"].bindings["new"] = {}
    with pytest.raises(FrozenInstanceError):
        compiled.claims["moves_to@1"].claim_id = "other@1"


def test_snapshot_hash_and_serialization_are_deterministic():
    first = snapshot(logical_bundle())
    second = snapshot(reverse_mappings(logical_bundle()))

    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.canonical_content_json == second.canonical_content_json
    assert first.serialize() == second.serialize()
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.readiness == "ready"


def test_snapshot_hash_binds_compiled_semantic_content():
    compiled = snapshot(logical_bundle())

    assert hashlib.sha256(
        compiled.canonical_content_json.encode("utf-8")
    ).hexdigest() == compiled.snapshot_sha256
    assert hashlib.sha256(
        compiled.bundle_canonical_json.encode("utf-8")
    ).hexdigest() == compiled.bundle_sha256
    assert json.loads(compiled.canonical_content_json)[
        "bundle_sha256"] == compiled.bundle_sha256
    assert compiled.snapshot_sha256 != compiled.bundle_sha256


def test_compiler_contract_version_changes_snapshot_hash(monkeypatch):
    first = snapshot()
    monkeypatch.setattr(
        setup_registry_module, "SNAPSHOT_COMPILER_VERSION",
        first.compiler_contract_version + 1)
    second = snapshot()

    assert first.bundle_sha256 == second.bundle_sha256
    assert first.snapshot_sha256 != second.snapshot_sha256
    assert second.compiler_contract_version == first.compiler_contract_version + 1


def test_virtual_join_change_changes_snapshot_hash():
    changed = logical_bundle()
    changed["virtual_joins"]["input_to_reference"]["fold"] = {
        "separator": True, "case": False}

    compiled = snapshot(changed)
    assert compiled.snapshot_sha256 != snapshot().snapshot_sha256


@pytest.mark.parametrize(
    ("fold", "code", "suffix", "message"),
    [
        ({"sql": "DROP"}, "unsafe_declaration", ".fold.sql",
         "field is not allowed"),
        ({"SQL": "DROP"}, "unsafe_declaration", ".fold.SQL",
         "field is not allowed"),
        ({"trim": True}, "invalid_join", ".fold.trim",
         "unknown notation rule 'trim'; known rules are ['case', 'separator', 'zero_pad']"),
        ({"separator": "yes"}, "invalid_type", ".fold.separator",
         'separator must be true or false, got "yes" - write true or false'),
        ({"zero_pad": True}, "invalid_join", ".fold.zero_pad",
         "notation rule 'zero_pad' is not implemented"),
    ],
)
def test_join_fold_uses_closed_notation_rule_grammar(fold, code, suffix, message):
    raw = logical_bundle()
    raw["virtual_joins"]["input_to_reference"]["fold"] = fold

    errors = snapshot_compile_errors(LedgerSetupBundle(raw), trusted_implementations())

    assert [issue.to_mapping() for issue in errors] == [{
        "code": code,
        "path": f"bundle.virtual_joins.input_to_reference{suffix}",
        "message": message,
    }]


def test_join_fold_contract_matches_operational_notation_vocabulary():
    # The on/off rules only - a value rule is stored by the write (notation_norm.VALUE_RULES).
    value_rules = frozenset(notation_norm.VALUE_RULES)
    assert setup_bundle_module._JOIN_FOLD_RULES == frozenset(
        notation_norm.KNOWN_RULES) - value_rules
    assert setup_bundle_module._IMPLEMENTED_JOIN_FOLD_RULES == frozenset(
        notation_norm.IMPLEMENTED_RULES) - value_rules


# RETIRED: test_dataflow_declaration_change_also_changes_snapshot_hash.
# It pinned that editing `chains`/`enrichments` moved the snapshot hash. THE MACHINERY IS
# GONE, and its removal was the point rather than a side effect: neither section could
# change one atom, so the hash they moved blocked the cursor with
# `cursor_snapshot_reset_required` over an approval-reference string. The surviving rule
# is the inverse and is covered by the registry hash tests that remain -- the hash now
# covers only what can change an atom. Retired because the sections no longer exist, not
# because it stopped passing.


def test_untrusted_mapper_errors_are_structured_and_deterministic():
    bundle = validate_bundle(logical_bundle())
    none_trusted = TrustedImplementationCatalog.build()

    first = snapshot_compile_errors(bundle, none_trusted)
    second = snapshot_compile_errors(
        validate_bundle(reverse_mappings(logical_bundle())), none_trusted)

    assert [issue.to_mapping() for issue in first] == [
        {
            "code": "untrusted_implementation",
            "path": f"{MAPPER_PATH}.implementation_id",
            "message": "mapper implementation 'map-transition-role' version 1 is not trusted",
        },
    ]
    assert [issue.to_mapping() for issue in first] == [
        issue.to_mapping() for issue in second
    ]
    with pytest.raises(LedgerSetupValidationError) as caught:
        compile_setup_snapshot(bundle, none_trusted)
    assert caught.value.to_mapping() == first[0].to_mapping()


# RETIRED: test_unused_config_implementations_are_also_checked.
# It pinned that a preparer or mapper NO SOURCE SELECTS is still trust-checked -- the
# checker walked the two sections rather than what was reachable from a source. THE SHAPE
# IS GONE: since 2026-08-20 both bodies live inside their source, so an unselected one
# cannot be written. What the test guarded (both clauses of every declared body are
# checked, in a deterministic order) is exactly what
# `test_untrusted_preparer_and_mapper_errors_are_structured_and_deterministic` above pins.
# Retired because the shape no longer exists, not because it stopped passing.


@pytest.mark.parametrize(
    ("section", "entry_id", "trusted", "path"),
    [
        (
            "mapper",
            "input_rows",
            TrustedImplementationCatalog.build(mappers=[("map-transition-role", 2)]),
            f"{MAPPER_PATH}.implementation_version",
        ),
    ],
)
def test_known_implementation_with_untrusted_version_has_exact_error_path(
        section, entry_id, trusted, path):
    raw = logical_bundle()
    errors = snapshot_compile_errors(
        validate_bundle(raw), trusted)

    assert [issue.code for issue in errors] == ["unsupported_implementation_version"]
    assert [issue.path for issue in errors] == [path]


# DELETED 2026-08-21 with the field it measured:
# `test_snapshot_compiler_requires_every_binding_to_be_approved` (two parameters). It
# asserted that the compiler runs `bundle_readiness_errors` before compiling, by driving a
# nested key binding's `approval_status` to a value nothing in the tree could produce.
# The field retired for holding one reachable value; the readiness STAGE is still called
# from `snapshot_compile_errors` and still returns its result, it simply has no rules left.


def test_directly_constructed_invalid_bundle_is_revalidated_fail_closed():
    # The undeclared predicate used to be planted at the pack's `emit.predicate`; since
    # 2026-08-21 the only place a predicate is NAMED is the mapping, so the same
    # `unknown_predicate` refusal is provoked there. Same code, same fail-closed
    # revalidation of a hand-built bundle that never went through `validate_bundle`.
    raw = logical_bundle()
    source_profile(raw)["mappings"]["main_transition"]["predicate"] = "missing@1"
    untrusted_input = LedgerSetupBundle(raw)

    errors = snapshot_compile_errors(untrusted_input, trusted_implementations())

    assert any(
        issue.code == "unknown_predicate"
        and issue.path == (
            f"{PROFILE_PATH}.mappings.main_transition.predicate")
        for issue in errors
    )


def test_new_config_entity_and_predicate_need_no_compiler_change():
    """Was `..._entity_predicate_and_pack_...`; the pack half was 17 lines of declaration.

    Adding a predicate is now the WHOLE act -- its Claim compiles with it, which is the
    point of the section going -- so the third assertion reads the derived Claim rather
    than a hand-written pack.
    """
    bundle = logical_bundle()
    bundle["entities"]["NewSubject@1"] = {"keys": ["new_subject_id"]}
    bundle["entities"]["NewTarget@1"] = {"keys": ["new_target_id"]}
    bundle["vocabulary"]["links_to@1"] = {
        "status": "active",
        "subjects": ["NewSubject@1"],
        "object": {
            "kind": "entity_ref", "types": ["NewTarget@1"],
            "qualifiers": {"required": [], "optional": []},
        },
    }

    compiled = snapshot(bundle)

    assert isinstance(compiled.entities, EntityTypeRegistry)
    assert compiled.entities["NewSubject@1"].config_path == (
        "bundle.entities.NewSubject@1")
    assert compiled.vocabulary["links_to@1"].config_path == (
        "bundle.vocabulary.links_to@1")
    assert compiled.claims["links_to@1"].config_path == "bundle.vocabulary.links_to@1"
    assert set(compiled.claims["links_to@1"].roles) == {
        "subject", "target", "occurred_at"}


def test_registry_keeps_multiple_versions_as_distinct_keys():
    bundle = logical_bundle()
    bundle["entities"]["VersionedEntity@1"] = {"keys": ["id"]}
    bundle["entities"]["VersionedEntity@2"] = {"keys": ["id"]}

    compiled = snapshot(bundle)

    assert compiled.entities["VersionedEntity@1"].version == 1
    assert compiled.entities["VersionedEntity@2"].version == 2
    assert list(key for key in compiled.entities if key.startswith("VersionedEntity@")) == [
        "VersionedEntity@1", "VersionedEntity@2"]


def test_registry_builder_refuses_add_after_seal():
    descriptor = EntityTypeDescriptor(
        entity_type_id="Example@1",
        version=1,
        identity_keys=("id",),
        allow_null=False,
        config_path="bundle.entities.Example@1",
    )
    builder = setup_registry_module._RegistryBuilder(EntityTypeRegistry)
    builder.add("Example@1", descriptor)
    sealed = builder.seal()

    assert sealed["Example@1"] is descriptor
    with pytest.raises(RuntimeError, match="sealed"):
        builder.add("Example@2", descriptor)
    with pytest.raises(RuntimeError, match="sealed"):
        builder.seal()


# RETIRED: test_trusted_unused_preparer_and_mapper_are_included_in_registries.
# Same reason as `test_unused_config_implementations_are_also_checked` above: a preparer
# or mapper no source selects can no longer be declared. The registries are now keyed by
# source id and are populated by walking `sources`, so "in the registry" and "declared"
# are the same statement -- see
# `test_registry_tree_compiles_predicate_claim_role_and_source_plan`.


def test_same_claims_compile_for_completely_renamed_source_and_columns():
    original = snapshot(logical_bundle())
    renamed = snapshot(logical_bundle(source_name="arbitrary_rows", prefix="renamed_"))

    assert original.claims.to_mapping() == renamed.claims.to_mapping()
    assert renamed.source_plans["arbitrary_rows"].relation == "arbitrary_rows"
    assert renamed.source_plans["arbitrary_rows"].driver.identity == (
        "renamed_event_key",)


def test_config_root_path_does_not_enter_snapshot_hash(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_tree(first_root)
    write_tree(second_root)

    first_bundle = load_setup_bundle(first_root)
    second_bundle = load_setup_bundle(second_root)
    first = compile_setup_snapshot(first_bundle, trusted_implementations())
    second = compile_setup_snapshot(second_bundle, trusted_implementations())

    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.serialize() == second.serialize()


def test_stage3_module_has_no_domain_branch_lookup_or_database_capability():
    source_path = Path(__file__).resolve().parents[1] / "ledger" / "setup_registry.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_domain_literals = {
        "dt_log", "bonding_log", "DT_LOT", "CORE_WAFER", "BOND_SLOT", "Core", "Bonding",
    }
    literal_strings = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert not (forbidden_domain_literals & literal_strings)
    assert "LookupRegistry" not in source
    assert "declared_lookup" not in source

    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert not ({"sqlalchemy", "database", "pandas"} & imported_roots)


def test_snapshot_has_no_source_row_or_write_methods():
    compiled = snapshot()

    for value in (
        compiled,
        compiled.source_plans["input_rows"],
        compiled.source_plans["input_rows"].driver,
    ):
        assert not hasattr(value, "execute")
        assert not hasattr(value, "read")
        assert not hasattr(value, "write")
        assert not hasattr(value, "commit")
        assert not hasattr(value, "advance_cursor")


def test_compiler_does_not_mutate_the_validated_bundle():
    before = validate_bundle(logical_bundle())
    expected = before.serialize()

    compile_setup_snapshot(before, trusted_implementations())

    assert before.serialize() == expected


def test_mapper_group_by_columns_are_compiled_into_snapshot():
    raw = logical_bundle()
    driver_mapper(raw)["unit"] = {
        "kind": "group_by", "columns": ["target_id"]}

    compiled = snapshot(raw)

    mapper = compiled.mappers["input_rows"]
    assert mapper.unit_kind == "group_by"
    assert mapper.unit_columns == ("target_id",)


def two_source_bundle():
    """One predicate shared by two sources, so a shared edit and a private edit separate.

    🔴 THE ISOLATION CLAIM NEEDS A BUNDLE WHERE THE TWO ANSWERS DIFFER.  A one-source
    fixture cannot tell "only my own material moves me" from "nothing ever moves me";
    both pass.  The second source reuses `input_rows` because a relation the fixture
    plant does not declare is refused, and the point here is the closure, not the table.
    """
    raw = copy.deepcopy(logical_bundle())
    second = copy.deepcopy(logical_bundle(source_name="other_rows")["sources"]["other_rows"])
    second["relation"] = "input_rows"
    raw["sources"]["other_rows"] = second
    return raw


def cursor_fingerprints(raw):
    compiled = snapshot(raw)
    return {
        source_id: setup_registry_module.source_cursor_fingerprint(compiled, source_id)
        for source_id in ("input_rows", "other_rows")
    }


def test_editing_one_sources_binding_leaves_the_other_sources_cursor_alone():
    """The whole reason the per-source fingerprint exists.

    Against the global `snapshot_sha256` this test cannot pass: that value covers every
    registry, so editing either source moved both and a cursor was refused
    (`cursor_snapshot_reset_required`) for a change that could not alter one of its atoms.
    """
    raw = two_source_bundle()
    before = cursor_fingerprints(raw)

    edited = copy.deepcopy(raw)
    source = edited["sources"]["other_rows"]
    source["bind"]["mappings"]["main_transition"]["bind"][
        "subject"]["keys"]["input_id"]["column"] = "join_id"
    after = cursor_fingerprints(edited)

    assert after["other_rows"] != before["other_rows"]
    assert after["input_rows"] == before["input_rows"]


def test_a_sources_own_edit_moves_its_own_cursor():
    """The discriminator for the test above.

    🔴 WITHOUT THIS ONE, "nothing ever moves" is indistinguishable from isolation --
    a fingerprint that ignored the sources entirely would pass the isolation test
    perfectly.  This is the sample on which the two candidate rules disagree.
    """
    raw = two_source_bundle()
    before = cursor_fingerprints(raw)

    edited = copy.deepcopy(raw)
    source = edited["sources"]["input_rows"]
    source["bind"]["mappings"]["main_transition"]["bind"][
        "subject"]["keys"]["input_id"]["column"] = "join_id"
    after = cursor_fingerprints(edited)

    assert after["input_rows"] != before["input_rows"]
    assert after["other_rows"] == before["other_rows"]


@pytest.mark.parametrize("written", [["record_id"], [], "anything"])
def test_writing_input_columns_leaves_the_cursor_where_it_is(written):
    """⚰️ `map.input_columns` is read and ignored (소유자 10-03, 총괄 2a8d9073c) - writing it, in
    any shape, moves no cursor.

    🔴 HALF OF A PAIR AND VACUOUS ALONE. "The fingerprint did not move" also passes for a
    function broken into returning a constant; `test_a_sources_own_edit_moves_its_own_cursor`
    above is the other half, and the positive control below carries part of it here.
    """
    raw = two_source_bundle()
    before = cursor_fingerprints(raw)
    assert before["input_rows"] != before["other_rows"], (
        "positive control: a fingerprint that returned a constant would pass every "
        "assertion below without hashing anything")

    edited = copy.deepcopy(raw)
    edited["sources"]["input_rows"]["map"]["input_columns"] = written
    after = cursor_fingerprints(edited)

    assert after["input_rows"] == before["input_rows"]
    assert after["other_rows"] == before["other_rows"]


def test_a_table_that_grows_a_column_is_read_whole_and_moves_no_fingerprint():
    """소유자 10-03 「그냥 다 읽으면 되잖아」 (총괄 2a8d9073c): the read brings every column of the
    relation, and the column list is not atom material - a column reaches an atom only
    through a binding (판정 201). So a new column arrives in the read, and neither the
    cursor fingerprint nor the snapshot moves."""
    from ledger.event_frame import base_select_columns, bound_select_columns

    grown = copy.deepcopy(DEFAULT_CATALOG)
    grown["input_rows"]["columns"]["added_later"] = "string"
    raw = logical_bundle()
    before = snapshot(raw, catalog=DEFAULT_CATALOG)
    after = snapshot(raw, catalog=grown)

    assert "added_later" not in base_select_columns(before.source_plans["input_rows"])
    assert "added_later" in base_select_columns(after.source_plans["input_rows"])
    assert set(base_select_columns(after.source_plans["input_rows"])) == {
        *grown["input_rows"]["columns"]}
    assert "added_later" not in bound_select_columns(after.source_plans["input_rows"])
    assert (setup_registry_module.source_cursor_fingerprint(after, "input_rows")
            == setup_registry_module.source_cursor_fingerprint(before, "input_rows"))
    assert after.snapshot_sha256 == before.snapshot_sha256


def test_editing_a_shared_predicate_moves_every_source_that_reaches_it():
    """The closure is transitive, and erring SMALL is the dangerous direction.

    A source that should have been refused and is not re-reads under a stale contract
    silently; a source refused too often merely annoys.  Both fixtures name `moves_to@1`
    in their own `bind.mappings`, so both must move -- and this is the assertion that
    fails first if someone later narrows the closure to a source's own declarations.
    (Until 2026-08-21 they reached it through a shared PACK, one hop further out; the
    closure lands directly on the predicate now, and the requirement is unchanged.)
    """
    raw = two_source_bundle()
    before = cursor_fingerprints(raw)

    edited = copy.deepcopy(raw)
    predicate = edited["vocabulary"]["moves_to@1"]
    predicate["object"]["qualifiers"]["optional"] = ["event_key", "reason"]
    after = cursor_fingerprints(edited)

    assert after["input_rows"] != before["input_rows"]
    assert after["other_rows"] != before["other_rows"]


# ------------------------------------------- S-103: retirement reaches the compiled plan

def test_a_sources_retirement_reaches_the_compiled_plan_and_the_live_reader():
    """🔴 A WORD WITH NO READER IS WORSE THAN AN ABSENT ONE (S-103, ruling 198), because
    the screen shows it taking effect. `sources.*.status` was accepted by the grammar and
    dropped by the compiler, so the one thing retiring a source must do - stop the
    translator reading it - did not happen.

    ⛔ RETIRING IS NOT DELETING. The atoms it already made are facts and a ledger appends,
    so what changes is only which sources a newly arrived row is offered to. That is
    `followup.sources_for_table`, asserted here rather than the flag alone: the flag
    reaching the dataclass and nothing consulting it is exactly the defect being closed.
    """
    from ledger import followup

    bundle = logical_bundle()
    compiled = snapshot(bundle)
    plan = compiled.source_plans["input_rows"]
    assert plan.status == "active", "an absent status means active"
    setup = type("S", (), {"snapshot": compiled})()
    assert followup.sources_for_table(setup, plan.relation) == ("input_rows",)

    bundle["sources"]["input_rows"]["status"] = "retired"
    retired = snapshot(bundle)
    assert retired.source_plans["input_rows"].status == "retired"
    setup = type("S", (), {"snapshot": retired})()
    assert followup.sources_for_table(setup, plan.relation) == (), (
        "a retired source must not be offered rows that arrive from now on")


def test_an_entity_types_retirement_reaches_the_compiled_plan():
    """The same word on the other declaration, compiled the same way. Its READER is the
    bundle contract (`inactive_entity_type`), which refuses before a snapshot exists - so
    what is asserted here is that the compiler does not silently drop the field on the
    path that runs when the contract has already passed."""
    bundle = logical_bundle()
    assert snapshot(bundle).entities["OutputEntity@1"].status == "active"
