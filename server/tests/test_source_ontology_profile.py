"""Phase 2 contract tests for the pure Source Ontology Profile schema."""
from __future__ import annotations

import copy
from dataclasses import replace
import ast
import json
from pathlib import Path

import pytest

from ledger import config as ledger_config
from ledger.source_profile import (
    MAPPING_STATUS_HUMAN_APPROVED,
    MAPPING_STATUS_INFERRED,
    BindingKindDescriptor,
    BindingKindRegistry,
    ClaimDescriptor,
    PackDescriptor,
    PackRegistry,
    PROFILE_CONFIG_SECTION,
    PROFILE_SCHEMA_VERSION,
    ProfileValidationError,
    RoleDescriptor,
    default_binding_kind_registry,
    profile_readiness_errors,
    public_profile_schema,
    require_executable_profile,
    serialize_profile,
    validate_legacy_profile,
    validate_profile,
    validate_profile_errors,
    validate_profile_section,
)
from ledger.source_profile_builtins import default_profile_registries


def approved(column, *, relation=None):
    out = {"column": column, "status": MAPPING_STATUS_HUMAN_APPROVED}
    if relation is not None:
        out["relation"] = relation
    return out


def lineage_profile(source="lineage_rows", prefix=""):
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "source": {"relation": source},
        "entity": {"type": "Lot", "keys": {"lot": "lot"}},
        "event": {"template": "lot_lineage", "timezone": "Asia/Seoul"},
        "roles": {
            "row_identity": approved(prefix + "record_id"),
            "occurred_at": approved(prefix + "event_at"),
            "event_type": approved(prefix + "kind"),
            "lot": approved(prefix + "lot_id"),
            "parent_lot": approved(prefix + "parent_id"),
            "child_lot": approved(prefix + "child_id"),
            "slots": approved(prefix + "slot_values"),
            "wafers": approved(prefix + "wafer_values"),
        },
        "containers": {},
    }


def transfer_profile(source="movement_rows", inventory="inventory_rows", prefix=""):
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "source": {"relation": source, "related": {"destination": inventory}},
        "entity": {"type": "Wafer", "keys": {"wafer": "wafer"}},
        "event": {"template": "transfer", "timezone": "UTC"},
        "roles": {
            "row_identity": approved(prefix + "record_id"),
            "occurred_at": approved(prefix + "event_at"),
            "event_key": approved(prefix + "movement_id"),
            "row_order": approved(prefix + "record_id"),
            "wafer": approved(prefix + "material_id"),
            "destination_lookup_key": approved(
                prefix + "movement_id", relation="destination"),
            "destination_lot": approved(prefix + "lot_id", relation="destination"),
            "destination_slot": approved(prefix + "slot_id", relation="destination"),
        },
        "containers": {
            "from": {"type": "wafer_grid", "keys": {"wafer": "wafer"}},
            "to": {
                "type": "dt_slot",
                "keys": {"lot": "destination_lot", "slot": "destination_slot"},
                "lookup": {
                    "event_role": "event_key",
                    "container_role": "destination_lookup_key",
                },
            },
        },
    }


def legacy_lineage_config():
    return {
        "version": 1,
        "sources": {
            "legacy_rows": {
                "kind": "lineage",
                "occurred_at_column": "event_at",
                "occurred_at_timezone": "Asia/Seoul",
                "subject_types": ["Lot", "Wafer"],
                "register_entity_types": ["Lot", "Wafer"],
                "columns": {
                    "row_identity": "record_id",
                    "lot": "lot_id",
                    "event_type": "kind",
                    "parent_lot": "parent_id",
                    "child_lot": "child_id",
                    "slots": "slot_values",
                    "wafers": "wafer_values",
                },
                "vocabulary": {
                    "split": {
                        "lineage": "parent_child",
                        "slot_pairing": "slot_preserving",
                    },
                },
            },
        },
    }


def movement_profile(source="movement_rows", subject_column="ITEM_ID"):
    return {
        "profile_version": PROFILE_SCHEMA_VERSION,
        "source": source,
        "packs": ["transfer@1"],
        "mappings": [{
            "mapping_id": "primary_movement",
            "use": "transfer/movement",
            "bind": {
                "subject": {
                    "kind": "column",
                    "column": subject_column,
                },
                "from": {"kind": "constant", "value": "source_position"},
                "to": {
                    "kind": "declared_lookup",
                    "lookup_id": "destination_inventory",
                    "key": "column:MOVE_ID",
                    "select": "container",
                },
                "occurred_at": "column:EVENT_TIME",
            },
        }],
    }


def executable_movement_profile():
    profile = movement_profile()
    bind = profile["mappings"][0]["bind"]
    bind["from"].update({
    })
    bind["occurred_at"] = {
        "kind": "column",
        "column": "EVENT_TIME",
    }
    bind["to"].update({
        "key": {
            "kind": "column",
            "column": "MOVE_ID",
        },
    })
    return profile


def one_error(profile):
    errors = validate_profile_errors(profile)
    assert len(errors) == 1, [error.to_mapping() for error in errors]
    return errors[0].to_mapping()


def one_error_with_registries(profile, registries):
    errors = validate_profile_errors(profile, registries=registries)
    assert len(errors) == 1, [error.to_mapping() for error in errors]
    return errors[0].to_mapping()


def serialize_legacy_profile(profile):
    return validate_legacy_profile(profile).serialize()


def test_public_canonical_schema_exposes_packs_but_not_legacy_templates():
    registries = default_profile_registries()
    assert registries.templates.names() == ("lot_lineage", "transfer")
    public = public_profile_schema(registries)
    assert public["profile_version"] == 1
    assert "schema_version" not in public
    assert "mapping_statuses" not in public
    assert "templates" not in public
    assert "entity_types" not in public
    assert "container_types" not in public


def test_explicit_legacy_validator_is_deterministic_but_not_canonical():
    first = lineage_profile()
    second = {
        "containers": {},
        "roles": dict(reversed(list(first["roles"].items()))),
        "event": dict(reversed(list(first["event"].items()))),
        "entity": dict(reversed(list(first["entity"].items()))),
        "source": dict(reversed(list(first["source"].items()))),
        "schema_version": 1,
    }
    assert serialize_legacy_profile(first) == serialize_legacy_profile(first)
    assert serialize_legacy_profile(first) == serialize_legacy_profile(second)
    assert json.loads(serialize_legacy_profile(first)) == (
        validate_legacy_profile(first).to_mapping())


def test_missing_required_role_is_rejected_at_its_exact_profile_path():
    profile = lineage_profile()
    profile["roles"].pop("event_type")
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.history")
    assert caught.value.code == "missing_required_role"
    assert caught.value.path == "profiles.history.roles.event_type"


@pytest.mark.parametrize(("mutation", "path", "code"), [
    (lambda profile: profile["entity"].update(type="UnknownMaterial"),
     "profiles.sample.entity.type", "unregistered_entity_type"),
    (lambda profile: profile["event"].update(template="unknown_event"),
     "profiles.sample.event.template", "unregistered_template"),
    (lambda profile: profile["containers"]["to"].update(type="unknown_place"),
     "profiles.sample.containers.to.type", "unregistered_container_type"),
])
def test_unregistered_entity_template_and_container_are_rejected(mutation, path, code):
    profile = transfer_profile()
    mutation(profile)
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.sample")
    assert caught.value.path == path
    assert caught.value.code == code


def test_blank_entity_key_role_is_rejected_at_the_key_path():
    profile = lineage_profile()
    profile["entity"]["keys"]["lot"] = ""
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.entity.keys.lot"
    assert caught.value.code == "blank_value"


def test_blank_column_used_by_an_identity_key_is_rejected_before_it_can_compile():
    profile = lineage_profile()
    profile["roles"]["lot"]["column"] = "  "
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.roles.lot.column"
    assert caught.value.code == "blank_value"


def test_timezone_has_no_implicit_default():
    profile = lineage_profile()
    profile["event"].pop("timezone")
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.event.timezone"
    assert caught.value.code == "missing_field"


def test_invalid_timezone_is_rejected_instead_of_using_machine_local_time():
    profile = lineage_profile()
    profile["event"]["timezone"] = "Factory/Local"
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.event.timezone"
    assert caught.value.code == "invalid_timezone"


@pytest.mark.parametrize("factory", [lineage_profile, transfer_profile])
def test_one_template_accepts_renamed_source_and_physical_columns(factory):
    original = validate_legacy_profile(factory())
    renamed = validate_legacy_profile(
        factory(source="renamed_relation", prefix="site_"))
    assert renamed.event.template == original.event.template
    assert set(renamed.roles) == set(original.roles)
    assert all(role.column.startswith("site_") for role in renamed.roles.values())


def test_inferred_and_human_approved_column_mappings_are_distinct():
    profile = lineage_profile()
    profile["roles"]["row_identity"] = {
        "column": "record_id",
        "status": MAPPING_STATUS_INFERRED,
        "reason": "the declared source key has one column",
    }
    validated = validate_legacy_profile(profile)
    assert validated.roles["row_identity"].status == MAPPING_STATUS_INFERRED
    assert validated.roles["lot"].status == MAPPING_STATUS_HUMAN_APPROVED


def test_inferred_mapping_without_a_reason_is_rejected():
    profile = lineage_profile()
    profile["roles"]["row_identity"] = {
        "column": "record_id", "status": MAPPING_STATUS_INFERRED}
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.roles.row_identity.reason"
    assert caught.value.code == "missing_inference_reason"


def test_unknown_fields_are_rejected_instead_of_being_silently_ignored():
    profile = lineage_profile()
    profile["event"]["translator"] = "something"
    with pytest.raises(ProfileValidationError) as caught:
        validate_legacy_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.event.translator"
    assert caught.value.code == "unknown_field"


def test_public_contract_does_not_expose_runtime_implementation_details():
    public_text = json.dumps(public_profile_schema(), ensure_ascii=False).lower()
    for hidden in (
            "predicate", "atom", "claim_class", "translator_version", "derivation",
            "canonical_key", "provenance"):
        assert hidden not in public_text


def test_legacy_six_field_profile_is_rejected_by_every_canonical_entry_point():
    legacy = lineage_profile()
    errors = validate_profile_errors(legacy)
    assert errors
    with pytest.raises(ProfileValidationError):
        validate_profile(legacy)
    with pytest.raises(ProfileValidationError):
        serialize_profile(legacy)
    with pytest.raises(ProfileValidationError):
        validate_profile_section({PROFILE_CONFIG_SECTION: {"legacy": legacy}})

    explicit = validate_legacy_profile(legacy)
    with pytest.raises(ProfileValidationError):
        serialize_profile(explicit)


@pytest.mark.parametrize("profile", [lineage_profile(), movement_profile()])
def test_validate_profile_and_error_collection_have_the_same_verdict(profile):
    errors = validate_profile_errors(profile)
    if errors:
        with pytest.raises(ProfileValidationError) as caught:
            validate_profile(profile)
        assert caught.value.to_mapping() == errors[0].to_mapping()
    else:
        assert validate_profile(profile).to_mapping()


def test_profiles_coexist_beside_legacy_sources_without_changing_legacy_loader(tmp_path):
    config = legacy_lineage_config()
    config[PROFILE_CONFIG_SECTION] = {"future_history": movement_profile()}
    profiles = validate_profile_section(config)
    assert list(profiles) == ["future_history"]

    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    loaded = ledger_config.load(str(path))
    assert list(loaded["sources"]) == ["legacy_rows"]
    assert loaded[PROFILE_CONFIG_SECTION] == config[PROFILE_CONFIG_SECTION]
    assert "__origin__" not in config


def test_profile_validation_is_pure_and_does_not_mutate_its_input():
    profile = movement_profile()
    before = copy.deepcopy(profile)
    validate_profile(profile)
    serialize_profile(profile)
    assert profile == before


def test_generic_profile_engine_contains_no_first_fixture_source_or_step_names():
    common_module = (Path(__file__).parents[1] / "ledger" / "source_profile.py")
    source = common_module.read_text(encoding="utf-8").lower()
    assert "bonding" not in source
    assert "dt_log" not in source
    assert "core" not in source


def test_pack_claim_role_registry_lookup_is_explicit():
    registries = default_profile_registries()
    pack = registries.packs.get("transfer", 1)
    assert pack is not None
    claim = pack.claim("movement")
    assert claim is not None
    role = claim.role("occurred_at")
    assert role == RoleDescriptor(
        role_id="occurred_at",
        kind="time",
        required=True,
        allowed_binding_kinds=("column", "declared_lookup"),
        allow_null=False,
    )


def test_unknown_pack_has_dedicated_error_contract():
    profile = movement_profile()
    profile["packs"] = ["missing@1"]
    profile["mappings"][0]["use"] = "missing/movement"
    assert one_error(profile) == {
        "code": "unknown_pack",
        "path": "packs[0]",
        "message": "pack 'missing' is not registered",
    }


def test_unsupported_pack_version_has_dedicated_error_contract():
    profile = movement_profile()
    profile["packs"] = ["transfer@99"]
    assert one_error(profile) == {
        "code": "unsupported_pack_version",
        "path": "packs[0]",
        "message": "pack 'transfer' does not support version 99; supported versions: 1",
    }


def test_unknown_claim_has_dedicated_error_contract():
    profile = movement_profile()
    profile["mappings"][0]["use"] = "transfer/missing"
    assert one_error(profile) == {
        "code": "unknown_claim",
        "path": "mappings[0].use",
        "message": "claim 'missing' is not registered in pack 'transfer'",
    }


def test_missing_required_role_has_dedicated_error_contract():
    profile = movement_profile()
    profile["mappings"][0]["bind"].pop("occurred_at")
    assert one_error(profile) == {
        "code": "missing_required_role",
        "path": "mappings[0].bind.occurred_at",
        "message": "transfer/movement requires occurred_at",
    }


def test_unknown_role_has_dedicated_error_contract():
    profile = movement_profile()
    profile["mappings"][0]["bind"]["mystery"] = "column:MYSTERY"
    assert one_error(profile) == {
        "code": "unknown_role",
        "path": "mappings[0].bind.mystery",
        "message": "role 'mystery' is not registered for transfer/movement",
    }


def test_invalid_binding_kind_has_dedicated_error_contract():
    profile = movement_profile()
    profile["mappings"][0]["bind"]["subject"] = {
        "kind": "constant", "value": "not_an_entity_binding"}
    assert one_error(profile) == {
        "code": "invalid_binding",
        "path": "mappings[0].bind.subject.kind",
        "message": "binding kind 'constant' is not allowed for role 'subject'",
    }


def test_duplicate_mapping_id_has_dedicated_error_contract():
    profile = movement_profile()
    duplicate = copy.deepcopy(profile["mappings"][0])
    profile["mappings"].append(duplicate)
    assert one_error(profile) == {
        "code": "duplicate_mapping_id",
        "path": "mappings[1].mapping_id",
        "message": "mapping_id 'primary_movement' is duplicated",
    }


def test_unsupported_profile_version_has_dedicated_error_contract():
    profile = movement_profile()
    profile["profile_version"] = 2
    assert one_error(profile) == {
        "code": "unsupported_profile_version",
        "path": "profile_version",
        "message": "version 2 is not supported; expected 1",
    }


@pytest.mark.parametrize("mapping_id", [None, "", "two words", "tab\tid"])
def test_mapping_id_is_required_and_cannot_contain_whitespace(mapping_id):
    profile = movement_profile()
    if mapping_id is None:
        profile["mappings"][0].pop("mapping_id")
    else:
        profile["mappings"][0]["mapping_id"] = mapping_id
    assert one_error(profile)["code"] == "invalid_mapping_id"


def test_canonical_profile_normalization_and_serialization_are_deterministic():
    profile = movement_profile()
    reordered = {
        "mappings": [{
            "bind": dict(reversed(list(profile["mappings"][0]["bind"].items()))),
            "use": "transfer/movement",
            "mapping_id": "primary_movement",
        }],
        "packs": ["transfer@1"],
        "source": "movement_rows",
        "profile_version": 1,
    }
    first = serialize_profile(profile)
    assert first == serialize_profile(profile)
    assert first == serialize_profile(reordered)
    assert json.loads(first) == validate_profile(profile).to_mapping()


def test_error_list_order_is_deterministic_and_independent_of_bind_order():
    profile = movement_profile()
    bind = profile["mappings"][0]["bind"]
    bind.pop("occurred_at")
    bind["subject"] = {"kind": "constant", "value": "x"}
    bind["zeta"] = "column:Z"
    reversed_profile = copy.deepcopy(profile)
    reversed_profile["mappings"][0]["bind"] = dict(
        reversed(list(bind.items())))
    first = [error.to_mapping() for error in validate_profile_errors(profile)]
    second = [error.to_mapping()
              for error in validate_profile_errors(reversed_profile)]
    assert first == second
    assert [item["path"] for item in first] == sorted(
        item["path"] for item in first)


def test_same_pack_claim_accepts_unrelated_source_and_column_names():
    first = validate_profile(movement_profile(
        source="dt_log", subject_column="CORE_WAFER"))
    second = validate_profile(movement_profile(
        source="arbitrary_table", subject_column="ITEM_ID"))
    assert first.mappings[0].use == second.mappings[0].use == "transfer/movement"
    assert first.source == "dt_log"
    assert second.source == "arbitrary_table"
    assert first.mappings[0].bind["subject"].values["column"] == "CORE_WAFER"
    assert second.mappings[0].bind["subject"].values["column"] == "ITEM_ID"


def test_registering_a_new_pack_does_not_change_profile_schema():
    custom_pack = PackDescriptor(
        pack_id="example",
        version=1,
        claims=(ClaimDescriptor(
            claim_id="observation",
            roles=(RoleDescriptor("item", "entity"),),
        ),),
    )
    registries = replace(
        default_profile_registries(),
        packs=PackRegistry((custom_pack,)).seal(),
    )
    profile = {
        "profile_version": 1,
        "source": "unrelated_source",
        "packs": ["example@1"],
        "mappings": [{
            "mapping_id": "example_mapping",
            "use": "example/observation",
            "bind": {"item": "column:ANY_COLUMN"},
        }],
    }
    assert validate_profile(profile, registries=registries).mappings[0].use == (
        "example/observation")


def test_registering_a_new_binding_kind_needs_no_validator_branch():
    def normalize_alias(payload, path, role, registry):
        del path, role, registry
        return {"alias": payload["alias"]}, ()

    pack = PackDescriptor(
        pack_id="extension",
        version=1,
        claims=(ClaimDescriptor(
            claim_id="reference",
            roles=(RoleDescriptor(
                "item", "entity", allowed_binding_kinds=("declared_alias",)),),
        ),),
    )
    base_bindings = default_binding_kind_registry()
    binding_kinds = BindingKindRegistry((
        *base_bindings.descriptors(),
        BindingKindDescriptor("declared_alias", normalize_alias),
    )).seal()
    registries = replace(
        default_profile_registries(),
        packs=PackRegistry((pack,)).seal(),
        binding_kinds=binding_kinds,
    )
    profile = {
        "profile_version": 1,
        "source": "any_source",
        "packs": ["extension@1"],
        "mappings": [{
            "mapping_id": "extension_reference",
            "use": "extension/reference",
            "bind": {"item": {"kind": "declared_alias", "alias": "primary"}},
        }],
    }
    validated = validate_profile(profile, registries=registries)
    assert validated.mappings[0].bind["item"].kind == "declared_alias"


def test_binding_registry_validates_column_constant_and_declared_lookup():
    validated = validate_profile(movement_profile())
    binding_kinds = {
        role_id: binding.kind
        for role_id, binding in validated.mappings[0].bind.items()
    }
    assert binding_kinds == {
        "from": "constant",
        "occurred_at": "column",
        "subject": "column",
        "to": "declared_lookup",
    }
    lookup = validated.mappings[0].bind["to"].to_mapping()
    assert lookup["key"] == {"kind": "column", "column": "MOVE_ID"}


def test_declared_lookup_phase_two_only_normalizes_declared_structure():
    lookup = validate_profile(movement_profile()).mappings[0].bind["to"]
    assert set(lookup.values) == {"lookup_id", "key", "select"}
    assert lookup.values["lookup_id"] == "destination_inventory"
    assert lookup.values["select"] == "container"
    assert "result" not in lookup.values
    assert "resolved" not in lookup.values


def test_constant_null_permission_comes_from_the_role_contract():
    profile = movement_profile()
    profile["mappings"][0]["bind"]["from"] = {
        "kind": "constant", "value": None}
    error = one_error(profile)
    assert error["code"] == "invalid_binding"
    assert error["path"] == "mappings[0].bind.from.value"


def test_a_retired_v1_binding_field_is_swallowed():
    """A v1 Profile written before 2026-08-21 must still validate, unchanged.

    `binding_origin`, `approval_status` and `suggestion_reason` retired that day for
    holding one reachable value each. This reader is the LEGACY v1 door, and every v1
    Profile ever written carries all three, so the names are read and dropped rather
    than refused -- without that they would fall into the kind payload and
    `descriptor.normalize` would refuse the whole file for a word that means nothing.

    Replaces `test_binding_origin_and_approval_status_are_independent_and_preserved`
    and `test_system_suggested_binding_requires_a_suggestion_reason`, which asserted
    that the values survived normalization and that one implied the other.
    """
    profile = movement_profile()
    profile["mappings"][0]["bind"]["occurred_at"] = {
        "kind": "column",
        "column": "EVENT_TIME",
        "binding_origin": "imported",
        "approval_status": "rejected",
        "suggestion_reason": "header similarity",
    }
    validated = validate_profile(profile)
    assert validated.mappings[0].bind["occurred_at"].to_mapping() == {
        "kind": "column", "column": "EVENT_TIME"}
    # ...and `rejected` no longer withholds execution, because nothing reads it.
    assert profile_readiness_errors(validated) == ()


def test_a_binding_does_not_create_or_raise_a_claim_epistemic_class():
    """Was `test_approved_binding_does_not_...`; the approval half retired 2026-08-21.

    It compared an `approved` Profile against a `pending` one and asserted both kept their
    own value. There is one value now, so what is left is the property that never needed
    two: a binding says WHERE a value comes from and never how much it is believed.
    """
    normalized = validate_profile(movement_profile()).to_mapping()
    assert normalized["mappings"][0]["use"] == "transfer/movement"
    mapping_text = json.dumps(normalized, sort_keys=True)
    for forbidden in ("claim_class", '"pin"', '"confirmed"',
                      "approval_status", "binding_origin", "suggestion_reason"):
        assert forbidden not in mapping_text


# DELETED 2026-08-21 with the field they measured:
# `test_pending_binding_is_structurally_valid_but_not_executable`,
# `test_rejected_binding_is_structurally_valid_but_not_executable` and
# `test_nested_lookup_key_pending_blocks_execution_at_its_exact_path`.
# All three drove `approval_status` to a value no file in the tree ever held, and the
# field is gone, so the state they refused is underivable rather than merely
# unchecked. `profile_readiness_errors` keeps its TYPE gate (below) and its position
# between "this parsed" and "this runs"; it holds no rules today.


def test_a_validated_profile_is_executable():
    validated = validate_profile(executable_movement_profile())
    assert profile_readiness_errors(validated) == ()
    assert require_executable_profile(validated) is validated


def test_readiness_gate_requires_structural_validation_first():
    with pytest.raises(TypeError, match="validated SourceOntologyProfile"):
        profile_readiness_errors(executable_movement_profile())


def test_role_kind_and_allowed_binding_kinds_both_gate_validation():
    profile = movement_profile()
    profile["mappings"][0]["bind"]["subject"] = {
        "kind": "constant", "value": "source_position"}
    assert one_error(profile) == {
        "code": "invalid_binding",
        "path": "mappings[0].bind.subject.kind",
        "message": "binding kind 'constant' is not allowed for role 'subject'",
    }

    custom_pack = PackDescriptor(
        pack_id="role-kind-check",
        version=1,
        claims=(ClaimDescriptor(
            claim_id="observation",
            roles=(RoleDescriptor(
                "subject", "entity",
                allowed_binding_kinds=("constant",),
                symbolic_constants=("source_position",),
            ),),
        ),),
    )
    registries = replace(
        default_profile_registries(),
        packs=PackRegistry((custom_pack,)).seal(),
    )
    wrong_kind_profile = {
        "profile_version": 1,
        "source": "any_source",
        "packs": ["role-kind-check@1"],
        "mappings": [{
            "mapping_id": "role_kind_check",
            "use": "role-kind-check/observation",
            "bind": {"subject": {
                "kind": "constant", "value": "source_position"}},
        }],
    }
    assert one_error_with_registries(wrong_kind_profile, registries) == {
        "code": "invalid_binding",
        "path": "mappings[0].bind.subject.kind",
        "message": "binding kind 'constant' does not support role kind 'entity'",
    }


def test_from_position_uses_a_registered_symbolic_constant_fail_closed():
    validated = validate_profile(movement_profile())
    from_role = (default_profile_registries().packs.get("transfer", 1)
                 .claim("movement").role("from"))
    assert from_role.kind == "position"
    assert from_role.symbolic_constants == ("source_position",)
    assert validated.mappings[0].bind["from"].values["value"] == (
        "source_position")

    profile = movement_profile()
    profile["mappings"][0]["bind"]["from"]["value"] = "arbitrary_position"
    error = one_error(profile)
    assert error["code"] == "invalid_binding"
    assert error["path"] == "mappings[0].bind.from.value"
    assert "allowed values or types: source_position" in error["message"]


def test_common_validator_has_no_domain_case_literals():
    common_module = Path(__file__).parents[1] / "ledger" / "source_profile.py"
    tree = ast.parse(common_module.read_text(encoding="utf-8"))
    literals = {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    forbidden = {
        "dt_log", "bonding_log", "DT_LOT", "CORE_WAFER", "BOND_SLOT",
        "Core", "Bonding",
    }
    assert literals.isdisjoint(forbidden)


def test_phase_two_adds_no_database_migration():
    root = Path(__file__).parents[2]
    migration_names = {
        path.name.lower() for path in (root / "server" / "migrations").glob("*")
    } if (root / "server" / "migrations").exists() else set()
    assert not any("source_profile" in name or "claim_mapping" in name
                   for name in migration_names)


def test_profile_modules_have_no_database_write_capability():
    ledger_dir = Path(__file__).parents[1] / "ledger"
    trees = [ast.parse((ledger_dir / name).read_text(encoding="utf-8"))
             for name in ("source_profile.py", "source_profile_builtins.py")]
    imported = set()
    called = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
            elif isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    called.add(function.id)
                elif isinstance(function, ast.Attribute):
                    called.add(function.attr)
    assert not any(name == "sqlalchemy" or name.startswith("database")
                   for name in imported)
    assert called.isdisjoint({
        "commit", "execute", "flush", "bulk_insert_mappings",
        "write_text", "write_bytes",
    })
