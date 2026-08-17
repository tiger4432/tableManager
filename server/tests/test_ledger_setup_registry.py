"""Stage 3 tests for config-only registries and immutable setup snapshots."""
from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import notation_norm

from ledger import setup_bundle as setup_bundle_module
from ledger import setup_registry as setup_registry_module
from ledger.setup_bundle import (
    LedgerSetupBundle,
    LedgerSetupValidationError,
    validate_bundle,
)
from ledger.setup_registry import (
    EntityTypeDescriptor,
    EntityTypeRegistry,
    MapperDescriptor,
    PackDescriptor,
    PredicateDescriptor,
    RoleDescriptor,
    SourcePlan,
    TrustedImplementationCatalog,
    compile_setup_snapshot,
    snapshot_compile_errors,
)
from test_ledger_setup_bundle import logical_bundle, reverse_mappings, write_tree


def trusted_implementations():
    return TrustedImplementationCatalog.build(
        source_preparers=[("prepare-input", 1)],
        mappers=[("map-transition-role", 1)],
    )


def snapshot(bundle=None, trusted=None):
    return compile_setup_snapshot(
        validate_bundle(bundle or logical_bundle()),
        trusted or trusted_implementations(),
    )


def test_registry_tree_compiles_pack_claim_role_and_source_plan():
    compiled = snapshot()

    predicate = compiled.vocabulary["moves_to@1"]
    entity = compiled.entities["InputEntity@1"]
    pack = compiled.packs["movement@1"]
    role = pack.claims["transition"].roles["subject"]
    source = compiled.source_plans["input_rows"]

    assert isinstance(predicate, PredicateDescriptor)
    assert predicate.version == 1
    assert isinstance(entity, EntityTypeDescriptor)
    assert entity.identity_keys == ("input_id",)
    assert isinstance(pack, PackDescriptor)
    assert isinstance(role, RoleDescriptor)
    assert role.allowed_binding_kinds == ("entity",)
    assert isinstance(source, SourcePlan)
    assert source.driver.mapper is compiled.mappers["map-transition@1"]
    assert source.profile is compiled.profiles["input-transition@1"]


def test_role_binding_kinds_use_the_same_pack_contract_as_validation():
    bundle = logical_bundle()
    role = bundle["packs"]["movement@1"]["claims"]["transition"]["roles"]["event_key"]
    role["allowed_binding_kinds"] = ["column"]

    compiled = snapshot(bundle)

    assert compiled.packs["movement@1"].claims["transition"].roles[
        "event_key"].allowed_binding_kinds == ("column",)


def test_registries_and_descriptors_are_recursively_immutable():
    compiled = snapshot()

    with pytest.raises(TypeError):
        compiled.entities._items["Other@1"] = compiled.entities["InputEntity@1"]
    with pytest.raises(TypeError):
        compiled.entities["InputEntity@1"].key_types["input_id"] = "integer"
    with pytest.raises(TypeError):
        compiled.profiles["input-transition@1"].mappings[0].bindings["new"] = {}
    with pytest.raises(FrozenInstanceError):
        compiled.packs["movement@1"].version = 2


def test_source_plan_reuses_registry_join_descriptor_without_copying_it():
    compiled = snapshot()
    source_descriptor = (
        compiled.source_plans["input_rows"]
        .driver.preparation.verified_join_descriptors[0]
    )
    registry_descriptor = compiled.verified_joins["input_to_reference"]

    assert source_descriptor is registry_descriptor
    assert source_descriptor.verified is True
    assert source_descriptor.verification_basis == "catalog_declared_unique"
    assert source_descriptor.fold_verified is False
    assert source_descriptor.fold_verification_basis == "not_declared"
    assert source_descriptor.join_key == (("join_id", "join_id"),)


def test_snapshot_hash_and_serialization_are_deterministic():
    first = snapshot(logical_bundle())
    second = snapshot(reverse_mappings(logical_bundle()))

    assert first.sha256 == second.sha256
    assert first.canonical_json == second.canonical_json
    assert first.serialize() == second.serialize()
    assert first.sha256 == "b843cc9c3662d48a377a289818570d0ad66f951e574cf104cd3809654ffb090d"
    assert first.readiness == "ready"


def test_virtual_join_change_changes_snapshot_hash():
    changed = logical_bundle()
    changed["virtual_joins"]["input_to_reference"]["fold"] = {
        "separator": True, "case": False}

    compiled = snapshot(changed)
    assert compiled.sha256 != snapshot().sha256
    descriptor = compiled.verified_joins["input_to_reference"]
    assert descriptor.fold_verified is True
    assert descriptor.fold_verification_basis == "notation_rule_vocabulary"


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
         "notation rule toggle must be boolean"),
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
    assert setup_bundle_module._JOIN_FOLD_RULES == frozenset(
        notation_norm.KNOWN_RULES)
    assert setup_bundle_module._IMPLEMENTED_JOIN_FOLD_RULES == frozenset(
        notation_norm.IMPLEMENTED_RULES)


def test_dataflow_declaration_change_also_changes_snapshot_hash():
    changed = logical_bundle()
    changed["chains"]["safe-chain"] = {"steps": [{"kind": "declared"}]}

    assert snapshot(changed).sha256 != snapshot().sha256


def test_untrusted_preparer_and_mapper_errors_are_structured_and_deterministic():
    bundle = validate_bundle(logical_bundle())
    none_trusted = TrustedImplementationCatalog.build()

    first = snapshot_compile_errors(bundle, none_trusted)
    second = snapshot_compile_errors(
        validate_bundle(reverse_mappings(logical_bundle())), none_trusted)

    assert [issue.to_mapping() for issue in first] == [
        {
            "code": "untrusted_implementation",
            "path": "bundle.mappers.map-transition@1.implementation_id",
            "message": "mapper implementation 'map-transition-role' version 1 is not trusted",
        },
        {
            "code": "untrusted_implementation",
            "path": "bundle.source_preparers.prepare-input@1.implementation_id",
            "message": "source preparer implementation 'prepare-input' version 1 is not trusted",
        },
    ]
    assert [issue.to_mapping() for issue in first] == [
        issue.to_mapping() for issue in second
    ]
    with pytest.raises(LedgerSetupValidationError) as caught:
        compile_setup_snapshot(bundle, none_trusted)
    assert caught.value.to_mapping() == first[0].to_mapping()


def test_unused_config_implementations_are_also_checked():
    bundle = logical_bundle()
    bundle["source_preparers"]["unused-preparer@1"] = copy.deepcopy(
        bundle["source_preparers"]["prepare-input@1"])
    bundle["source_preparers"]["unused-preparer@1"]["implementation_id"] = (
        "unused-preparer")
    bundle["mappers"]["unused-mapper@1"] = copy.deepcopy(
        bundle["mappers"]["map-transition@1"])
    bundle["mappers"]["unused-mapper@1"]["implementation_id"] = "unused-mapper"

    errors = snapshot_compile_errors(validate_bundle(bundle), trusted_implementations())

    assert [(issue.code, issue.path) for issue in errors] == [
        ("untrusted_implementation", "bundle.mappers.unused-mapper@1.implementation_id"),
        (
            "untrusted_implementation",
            "bundle.source_preparers.unused-preparer@1.implementation_id",
        ),
    ]


@pytest.mark.parametrize(
    ("section", "entry_id", "trusted", "path"),
    [
        (
            "source_preparers",
            "prepare-input@1",
            TrustedImplementationCatalog.build(
                source_preparers=[("prepare-input", 2)],
                mappers=[("map-transition-role", 1)],
            ),
            "bundle.source_preparers.prepare-input@1.implementation_version",
        ),
        (
            "mappers",
            "map-transition@1",
            TrustedImplementationCatalog.build(
                source_preparers=[("prepare-input", 1)],
                mappers=[("map-transition-role", 2)],
            ),
            "bundle.mappers.map-transition@1.implementation_version",
        ),
    ],
)
def test_known_implementation_with_untrusted_version_has_exact_error_path(
        section, entry_id, trusted, path):
    errors = snapshot_compile_errors(validate_bundle(logical_bundle()), trusted)

    assert [issue.code for issue in errors] == ["unsupported_implementation_version"]
    assert [issue.path for issue in errors] == [path]


@pytest.mark.parametrize("approval", ["pending", "rejected"])
def test_snapshot_compiler_requires_every_binding_to_be_approved(approval):
    bundle = logical_bundle()
    binding = bundle["profiles"]["input-transition@1"]["mappings"][0]["bind"]
    binding["subject"]["keys"]["input_id"]["approval_status"] = approval

    errors = snapshot_compile_errors(validate_bundle(bundle), trusted_implementations())

    assert [issue.to_mapping() for issue in errors] == [{
        "code": "binding_not_approved",
        "path": (
            "bundle.profiles.input-transition@1.mappings[0].bind.subject.keys."
            "input_id.approval_status"
        ),
        "message": f"binding approval_status is {approval!r}, expected 'approved'",
    }]


def test_directly_constructed_invalid_bundle_is_revalidated_fail_closed():
    raw = logical_bundle()
    raw["packs"]["movement@1"]["claims"]["transition"]["emit"]["predicate"] = (
        "missing@1")
    untrusted_input = LedgerSetupBundle(raw)

    errors = snapshot_compile_errors(untrusted_input, trusted_implementations())

    assert any(
        issue.code == "unknown_predicate"
        and issue.path == "bundle.packs.movement@1.claims.transition.emit.predicate"
        for issue in errors
    )


@pytest.mark.parametrize(
    ("mutation", "code", "path"),
    [
        (
            "missing",
            "unknown_join_rule",
            (
                "bundle.sources.input_rows.driver.preparation."
                "inherit_virtual_join_rules[0]"
            ),
        ),
        (
            "disabled",
            "invalid_driver",
            (
                "bundle.sources.input_rows.driver.preparation."
                "inherit_virtual_join_rules[0]"
            ),
        ),
        (
            "left_mismatch",
            "invalid_driver",
            (
                "bundle.sources.input_rows.driver.preparation."
                "inherit_virtual_join_rules[0]"
            ),
        ),
        (
            "rejected_unique_proof",
            "invalid_join",
            "bundle.virtual_joins.input_to_reference.join_key",
        ),
    ],
)
def test_inherited_join_must_be_present_enabled_and_verified(mutation, code, path):
    raw = logical_bundle()
    if mutation == "missing":
        raw["sources"]["input_rows"]["driver"]["preparation"][
            "inherit_virtual_join_rules"] = ["missing-rule"]
    elif mutation == "disabled":
        raw["virtual_joins"]["input_to_reference"]["enabled"] = False
    elif mutation == "left_mismatch":
        raw["virtual_joins"]["input_to_reference"]["left_table"] = "reference_rows"
    else:
        raw["tables"]["reference_rows"].pop("business_key")
        raw["tables"]["reference_rows"]["indexes"][0]["unique"] = False

    errors = snapshot_compile_errors(LedgerSetupBundle(raw), trusted_implementations())

    assert errors
    assert all(issue.code and issue.path and issue.message for issue in errors)
    assert any(issue.code == code and issue.path == path for issue in errors)


def test_inherited_join_left_keys_must_be_preparer_inputs():
    raw = logical_bundle()
    raw["source_preparers"]["prepare-input@1"]["input_columns"] = []

    errors = snapshot_compile_errors(LedgerSetupBundle(raw), trusted_implementations())

    assert [issue.to_mapping() for issue in errors] == [{
        "code": "invalid_driver",
        "path": (
            "bundle.sources.input_rows.driver.preparation."
            "inherit_virtual_join_rules[0]"
        ),
        "message": (
            "join rule 'input_to_reference' left key column(s) ['join_id'] must be "
            "declared by preparer 'prepare-input@1' input_columns"
        ),
    }]


def test_source_preparation_cannot_redeclare_join_contract():
    raw = logical_bundle()
    raw["sources"]["input_rows"]["driver"]["preparation"]["join_key"] = [
        {"left": "join_id", "right": "join_id"}
    ]

    errors = snapshot_compile_errors(LedgerSetupBundle(raw), trusted_implementations())

    assert [issue.to_mapping() for issue in errors] == [{
        "code": "unknown_field",
        "path": "bundle.sources.input_rows.driver.preparation.join_key",
        "message": "field is not allowed",
    }]


def test_new_config_entity_predicate_and_pack_need_no_compiler_change():
    bundle = logical_bundle()
    bundle["entities"]["NewSubject@1"] = {"keys": ["new_subject_id"]}
    bundle["entities"]["NewTarget@1"] = {"keys": ["new_target_id"]}
    bundle["vocabulary"]["links_to@1"] = {
        "status": "active",
        "layer": "ontology",
        "subjects": ["NewSubject@1"],
        "object": {"kind": "entity_ref", "types": ["NewTarget@1"]},
    }
    bundle["packs"]["linkage@1"] = {
        "claims": {
            "link": {
                "roles": {
                    "subject": {"kind": "entity", "required": True},
                    "target": {"kind": "entity", "required": True},
                    "occurred_at": {"kind": "time", "required": True},
                },
                "emit": {
                    "predicate": "links_to@1",
                    "subject": "$subject",
                    "object": {"kind": "entity_ref", "entity": "$target"},
                    "occurred_at": "$occurred_at",
                },
            },
        },
    }

    compiled = snapshot(bundle)

    assert isinstance(compiled.entities, EntityTypeRegistry)
    assert compiled.entities["NewSubject@1"].config_path == (
        "bundle.entities.NewSubject@1")
    assert compiled.vocabulary["links_to@1"].config_path == (
        "bundle.vocabulary.links_to@1")
    assert compiled.packs["linkage@1"].config_path == "bundle.packs.linkage@1"


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
        key_types={},
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


def test_trusted_unused_preparer_and_mapper_are_included_in_registries():
    bundle = logical_bundle()
    bundle["source_preparers"]["unused-preparer@1"] = copy.deepcopy(
        bundle["source_preparers"]["prepare-input@1"])
    bundle["source_preparers"]["unused-preparer@1"]["implementation_id"] = (
        "unused-preparer")
    bundle["mappers"]["unused-mapper@1"] = copy.deepcopy(
        bundle["mappers"]["map-transition@1"])
    bundle["mappers"]["unused-mapper@1"]["implementation_id"] = "unused-mapper"
    trusted = TrustedImplementationCatalog.build(
        source_preparers=[("prepare-input", 1), ("unused-preparer", 1)],
        mappers=[("map-transition-role", 1), ("unused-mapper", 1)],
    )

    compiled = snapshot(bundle, trusted)

    assert compiled.source_preparers["unused-preparer@1"].implementation == (
        setup_registry_module.ImplementationKey("unused-preparer", 1))
    assert isinstance(compiled.mappers["unused-mapper@1"], MapperDescriptor)


def test_same_pack_compiles_for_completely_renamed_source_and_columns():
    original = snapshot(logical_bundle())
    renamed = snapshot(logical_bundle(source_name="arbitrary_rows", prefix="renamed_"))

    assert original.packs.to_mapping() == renamed.packs.to_mapping()
    assert renamed.source_plans["arbitrary_rows"].relation == "arbitrary_rows"
    assert renamed.source_plans["arbitrary_rows"].driver.identity == (
        "renamed_event_key",)


def test_config_root_path_does_not_enter_snapshot_hash(tmp_path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    write_tree(first_root)
    write_tree(second_root)

    from ledger.setup_bundle import load_setup_bundle

    first = compile_setup_snapshot(load_setup_bundle(first_root), trusted_implementations())
    second = compile_setup_snapshot(load_setup_bundle(second_root), trusted_implementations())

    assert first.sha256 == second.sha256
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
