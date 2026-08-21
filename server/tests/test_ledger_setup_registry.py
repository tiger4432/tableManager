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
import virtual_join_config as virtual_join_config_module

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
    PREPARATION_PATH,
    PROFILE_PATH,
    driver_mapper,
    driver_preparation,
    load_setup_bundle,
    logical_bundle,
    objectless_register_bundle,
    reverse_mappings,
    source_profile,
    validate_bundle,
    write_tree,
)
from verified_join_contract import (
    VerifiedJoinDescriptor,
    _bind_physical_verifier_issuer,
    is_physically_verified_descriptor,
)


def compile_setup_snapshot(bundle, trusted, verified_joins=(), *, catalog=None):
    """Fixture-defaulting wrapper. Production callers resolve the catalog once in
    `ledger.setup`; here the fixture plant's catalog stands in for `table_config.json`."""
    return setup_registry_module.compile_setup_snapshot(
        bundle, trusted, verified_joins,
        catalog=DEFAULT_CATALOG if catalog is None else catalog)


def snapshot_compile_errors(bundle, trusted, verified_joins=(), *, catalog=None):
    return setup_registry_module.snapshot_compile_errors(
        bundle, trusted, verified_joins,
        catalog=DEFAULT_CATALOG if catalog is None else catalog)


def trusted_implementations():
    return TrustedImplementationCatalog.build(
        source_preparers=[("prepare-input", 1)],
        mappers=[("map-transition-role", 1)],
    )


def physically_verified_joins(bundle=None, *, unique_index="uq_reference_join_id"):
    """Obtain test descriptors through the production physical-verifier boundary."""
    raw = bundle or logical_bundle()
    normalized_rules = []
    for rule_id, rule in sorted(raw["virtual_joins"].items()):
        if not rule.get("enabled"):
            continue
        fold = rule.get("fold") or None
        normalized_rules.append({
            "name": rule_id,
            "left_table": rule["left_table"],
            "right_table": rule["right_table"],
            "join_key": [
                {"left": pair["left"], "right": pair["right"], "fold": fold}
                for pair in rule["join_key"]
            ],
            "expose": list(rule["expose"]),
            "join_cardinality": rule["join_cardinality"],
        })
    # The loader is the production issuance path.  Only its physical DB probe is
    # replaced: Stage 3 registry tests do not own a PostgreSQL session.
    with (
        patch.object(
            virtual_join_config_module,
            "load_virtual_join_rules",
            return_value=normalized_rules,
        ),
        patch.object(
            virtual_join_config_module,
            "verify_uniqueness",
            return_value={
                "unique_index": unique_index,
                "refused": False,
                "code": None,
            },
        ),
    ):
        return tuple(virtual_join_config_module.load_verified_rules(object()))


def snapshot(bundle=None, trusted=None, *, catalog=None):
    """`catalog` names the physical plant the bundle is judged against; omitting it uses
    the fixture plant.  A bundle describing a DIFFERENT plant (see the DT chain fixture in
    `test_ledger_source_preparation`) passes its own, exactly as a different deployment
    would ship its own `table_config.json`."""
    raw = bundle or logical_bundle()
    return compile_setup_snapshot(
        validate_bundle(raw, catalog=catalog),
        trusted or trusted_implementations(),
        physically_verified_joins(raw),
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
        "binding_origin": "user_declared", "approval_status": "approved",
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
        compiled.entities["InputEntity@1"].key_types["input_id"] = "integer"
    with pytest.raises(TypeError):
        compiled.profiles["input_rows"].mappings["main_transition"].bindings["new"] = {}
    with pytest.raises(FrozenInstanceError):
        compiled.claims["moves_to@1"].claim_id = "other@1"


def test_source_plan_reuses_registry_join_descriptor_without_copying_it():
    compiled = snapshot()
    source_descriptor = (
        compiled.source_plans["input_rows"]
        .driver.preparation.verified_join_descriptors[0]
    )
    registry_descriptor = compiled.verified_joins["input_to_reference"]

    assert source_descriptor is registry_descriptor
    assert source_descriptor["verified"] is True
    assert source_descriptor.verification_basis == "physical_unique_index"
    assert source_descriptor.join_key_pairs == (("join_id", "join_id"),)


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


def test_snapshot_compile_refuses_join_without_physical_verification():
    errors = snapshot_compile_errors(
        validate_bundle(logical_bundle()), trusted_implementations())

    assert [error.to_mapping() for error in errors] == [{
        "code": "unverified_join",
        "path": "bundle.virtual_joins.input_to_reference",
        "message": (
            "join rule 'input_to_reference' requires a physical UNIQUE "
            "verification descriptor"
        ),
    }]


def test_catalog_mapping_cannot_construct_a_verified_descriptor_directly():
    with pytest.raises(TypeError):
        VerifiedJoinDescriptor({"name": "catalog_only"})
    with pytest.raises(TypeError):
        VerifiedJoinDescriptor()
    assert not hasattr(VerifiedJoinDescriptor, "from_verified_rule")
    with pytest.raises(
            TypeError,
            match="only available to virtual_join_config"):
        _bind_physical_verifier_issuer()
    with pytest.raises(
            TypeError,
            match="only be issued inside virtual_join_config.load_verified_rules"):
        virtual_join_config_module._VERIFIED_JOIN_ISSUER.issue({"name": "raw"})


def test_former_internal_issue_cannot_use_the_bound_capability_directly():
    with pytest.raises(
            TypeError,
            match="direct VerifiedJoinDescriptor issuance is not allowed"):
        VerifiedJoinDescriptor._issue(
            {
                "name": "input_to_reference",
                "left_table": "input_rows",
                "right_table": "reference_rows",
                "join_key": [
                    {"left": "join_id", "right": "join_id", "fold": None}
                ],
                "expose": ["target_id"],
                "join_cardinality": "one",
                "unique_index": "NOT_PROBED_FAKE_INDEX",
            },
            issuer=virtual_join_config_module._VERIFIED_JOIN_ISSUER,
        )


def test_unissued_instance_is_not_accepted_as_physical_proof():
    forged = object.__new__(VerifiedJoinDescriptor)
    object.__setattr__(forged, "_data", {"name": "input_to_reference"})

    assert is_physically_verified_descriptor(forged) is False
    errors = snapshot_compile_errors(
        validate_bundle(logical_bundle()),
        trusted_implementations(),
        (forged,),
    )
    assert errors[0].to_mapping() == {
        "code": "unverified_join",
        "path": "bundle.virtual_joins.input_to_reference",
        "message": (
            "join rule 'input_to_reference' requires a physical UNIQUE "
            "verification descriptor"
        ),
    }
    assert errors[1].to_mapping() == {
        "code": "invalid_verified_join",
        "path": "verified_joins[0]",
        "message": (
            "must be a VerifiedJoinDescriptor produced by physical verification"
        ),
    }


def test_issuer_registry_has_no_module_level_mutation_handle():
    import verified_join_contract as contract

    assert not hasattr(contract, "_ISSUED_DESCRIPTORS")
    assert not hasattr(contract, "_PhysicalVerifierIssuer")
    assert not hasattr(contract, "_ISSUER_BIND_TOKEN")


def test_fake_index_name_cannot_bypass_the_physical_verifier():
    raw = logical_bundle()
    fake_catalog_rule = {
        "name": "input_to_reference",
        "left_table": "input_rows",
        "right_table": "reference_rows",
        "join_key": [{"left": "join_id", "right": "join_id", "fold": None}],
        "expose": ["target_id"],
        "join_cardinality": "one",
        "unique_index": "NOT_PROBED_FAKE_INDEX",
    }

    # The former public promotion API is absent.  Passing the same raw declaration to
    # the compiler is also rejected as a non-physical descriptor.
    assert not hasattr(VerifiedJoinDescriptor, "from_verified_rule")
    errors = snapshot_compile_errors(
        validate_bundle(raw), trusted_implementations(), (fake_catalog_rule,))

    assert [error.to_mapping() for error in errors] == [
        {
            "code": "unverified_join",
            "path": "bundle.virtual_joins.input_to_reference",
            "message": (
                "join rule 'input_to_reference' requires a physical UNIQUE "
                "verification descriptor"
            ),
        },
        {
            "code": "invalid_verified_join",
            "path": "verified_joins[0]",
            "message": (
                "must be a VerifiedJoinDescriptor produced by physical verification"
            ),
        },
    ]


def test_snapshot_compile_rejects_mismatched_physical_descriptor_exactly():
    raw = logical_bundle()
    descriptor_source = logical_bundle()
    descriptor_source["virtual_joins"]["input_to_reference"][
        "left_table"] = "different_rows"
    descriptor = physically_verified_joins(descriptor_source)[0]

    errors = snapshot_compile_errors(
        validate_bundle(raw), trusted_implementations(), (descriptor,))

    assert [error.to_mapping() for error in errors] == [{
        "code": "verified_join_mismatch",
        "path": "bundle.virtual_joins.input_to_reference",
        "message": (
            "physical verification descriptor does not match join rule "
            "'input_to_reference'"
        ),
    }]


def test_physical_verification_result_changes_snapshot_not_bundle_hash():
    raw = logical_bundle()
    validated = validate_bundle(raw)
    first = compile_setup_snapshot(
        validated, trusted_implementations(),
        physically_verified_joins(raw, unique_index="uq_reference_a"))
    second = compile_setup_snapshot(
        validated, trusted_implementations(),
        physically_verified_joins(raw, unique_index="uq_reference_b"))

    assert first.bundle_sha256 == second.bundle_sha256
    assert first.snapshot_sha256 != second.snapshot_sha256
    assert first.canonical_content_json != second.canonical_content_json


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
    descriptor = compiled.verified_joins["input_to_reference"]
    assert descriptor.pair_folds == ({"case": False, "separator": True},)


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


# RETIRED: test_dataflow_declaration_change_also_changes_snapshot_hash.
# It pinned that editing `chains`/`enrichments` moved the snapshot hash. THE MACHINERY IS
# GONE, and its removal was the point rather than a side effect: neither section could
# change one atom, so the hash they moved blocked the cursor with
# `cursor_snapshot_reset_required` over an approval-reference string. The surviving rule
# is the inverse and is covered by the registry hash tests that remain -- the hash now
# covers only what can change an atom. Retired because the sections no longer exist, not
# because it stopped passing.


def test_untrusted_preparer_and_mapper_errors_are_structured_and_deterministic():
    bundle = validate_bundle(logical_bundle())
    none_trusted = TrustedImplementationCatalog.build()

    verified = physically_verified_joins(bundle.to_mapping())
    first = snapshot_compile_errors(bundle, none_trusted, verified)
    second = snapshot_compile_errors(
        validate_bundle(reverse_mappings(logical_bundle())), none_trusted, verified)

    assert [issue.to_mapping() for issue in first] == [
        {
            "code": "untrusted_implementation",
            "path": f"{MAPPER_PATH}.implementation_id",
            "message": "mapper implementation 'map-transition-role' version 1 is not trusted",
        },
        {
            "code": "untrusted_implementation",
            "path": f"{PREPARATION_PATH}.implementation_id",
            "message": "source preparer implementation 'prepare-input' version 1 is not trusted",
        },
    ]
    assert [issue.to_mapping() for issue in first] == [
        issue.to_mapping() for issue in second
    ]
    with pytest.raises(LedgerSetupValidationError) as caught:
        compile_setup_snapshot(bundle, none_trusted, verified)
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
            "preparation",
            "input_rows",
            TrustedImplementationCatalog.build(
                source_preparers=[("prepare-input", 2)],
                mappers=[("map-transition-role", 1)],
            ),
            f"{PREPARATION_PATH}.implementation_version",
        ),
        (
            "mapper",
            "input_rows",
            TrustedImplementationCatalog.build(
                source_preparers=[("prepare-input", 1)],
                mappers=[("map-transition-role", 2)],
            ),
            f"{MAPPER_PATH}.implementation_version",
        ),
    ],
)
def test_known_implementation_with_untrusted_version_has_exact_error_path(
        section, entry_id, trusted, path):
    raw = logical_bundle()
    errors = snapshot_compile_errors(
        validate_bundle(raw), trusted, physically_verified_joins(raw))

    assert [issue.code for issue in errors] == ["unsupported_implementation_version"]
    assert [issue.path for issue in errors] == [path]


@pytest.mark.parametrize("approval", ["pending", "rejected"])
def test_snapshot_compiler_requires_every_binding_to_be_approved(approval):
    bundle = logical_bundle()
    binding = source_profile(bundle)["mappings"]["main_transition"]["bind"]
    binding["subject"]["keys"]["input_id"]["approval_status"] = approval

    errors = snapshot_compile_errors(validate_bundle(bundle), trusted_implementations())

    assert [issue.to_mapping() for issue in errors] == [{
        "code": "binding_not_approved",
        "path": (
            f"{PROFILE_PATH}.mappings.main_transition.bind.subject.keys."
            "input_id.approval_status"
        ),
        "message": f"binding approval_status is {approval!r}, expected 'approved'",
    }]


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


@pytest.mark.parametrize(
    ("mutation", "code", "path"),
    [
        (
            "missing",
            "unknown_join_rule",
            (
                "bundle.sources.input_rows.prepare."
                "inherit_virtual_join_rules[0]"
            ),
        ),
        (
            "disabled",
            "invalid_driver",
            (
                "bundle.sources.input_rows.prepare."
                "inherit_virtual_join_rules[0]"
            ),
        ),
        (
            "left_mismatch",
            "invalid_driver",
            (
                "bundle.sources.input_rows.prepare."
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
    catalog = copy.deepcopy(DEFAULT_CATALOG)
    if mutation == "missing":
        raw["sources"]["input_rows"]["prepare"][
            "inherit_virtual_join_rules"] = ["missing-rule"]
    elif mutation == "disabled":
        raw["virtual_joins"]["input_to_reference"]["enabled"] = False
    elif mutation == "left_mismatch":
        raw["virtual_joins"]["input_to_reference"]["left_table"] = "reference_rows"
    else:
        # The physical half moved out of the bundle: "the join's right side cannot be
        # proven unique" is now stated by mutating the CATALOG, which is where relation
        # keys and unique indexes are declared.  Mutating a copy, so the shared
        # `DEFAULT_CATALOG` stays intact for the other parameter cases.
        catalog["reference_rows"].pop("business_key")
        catalog["reference_rows"]["indexes"][0]["unique"] = False

    errors = snapshot_compile_errors(
        LedgerSetupBundle(raw), trusted_implementations(), catalog=catalog)

    assert errors
    assert all(issue.code and issue.path and issue.message for issue in errors)
    assert any(issue.code == code and issue.path == path for issue in errors)


def test_inherited_join_left_keys_must_be_preparer_inputs():
    raw = logical_bundle()
    driver_preparation(raw)["input_columns"] = []

    errors = snapshot_compile_errors(LedgerSetupBundle(raw), trusted_implementations())

    assert [issue.to_mapping() for issue in errors] == [{
        "code": "invalid_driver",
        "path": (
            "bundle.sources.input_rows.prepare."
            "inherit_virtual_join_rules[0]"
        ),
        "message": (
            "join rule 'input_to_reference' left key column(s) ['join_id'] must be "
            "declared by bundle.sources.input_rows.prepare.input_columns"
        ),
    }]


def test_source_preparation_cannot_redeclare_join_contract():
    raw = logical_bundle()
    raw["sources"]["input_rows"]["prepare"]["join_key"] = [
        {"left": "join_id", "right": "join_id"}
    ]

    errors = snapshot_compile_errors(LedgerSetupBundle(raw), trusted_implementations())

    # The preparer's fields are the driver clause's fields now, so the refusal lists
    # them -- which is the `_Problems.exact` behaviour, not a new message.
    assert [issue.to_mapping() for issue in errors] == [{
        "code": "unknown_field",
        "path": "bundle.sources.input_rows.prepare.join_key",
        "message": (
            "field is not allowed; allowed here: implementation_id (required), "
            "implementation_version (required), input_columns (required), "
            "output_columns (required), accepts_verified_join_rules (required), "
            "inherit_virtual_join_rules (required)"
        ),
    }]


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
    first = compile_setup_snapshot(
        first_bundle, trusted_implementations(),
        physically_verified_joins(first_bundle.to_mapping()))
    second = compile_setup_snapshot(
        second_bundle, trusted_implementations(),
        physically_verified_joins(second_bundle.to_mapping()))

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

    compile_setup_snapshot(
        before, trusted_implementations(),
        physically_verified_joins(before.to_mapping()))

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
    source["map"]["input_columns"] = sorted(
        {*source["map"]["input_columns"], "join_id"})
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
    source["map"]["input_columns"] = sorted(
        {*source["map"]["input_columns"], "join_id"})
    after = cursor_fingerprints(edited)

    assert after["input_rows"] != before["input_rows"]
    assert after["other_rows"] == before["other_rows"]


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
