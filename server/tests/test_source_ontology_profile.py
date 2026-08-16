"""Phase 2 contract tests for the pure Source Ontology Profile schema."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ledger import config as ledger_config
from ledger.source_profile import (
    MAPPING_STATUS_HUMAN_APPROVED,
    MAPPING_STATUS_INFERRED,
    PROFILE_CONFIG_SECTION,
    PROFILE_SCHEMA_VERSION,
    ProfileValidationError,
    public_profile_schema,
    serialize_profile,
    validate_profile,
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


def test_version_one_registers_only_the_two_requested_templates():
    registries = default_profile_registries()
    assert registries.templates.names() == ("lot_lineage", "transfer")
    assert public_profile_schema(registries)["schema_version"] == 1


def test_same_profile_has_the_same_serialization_regardless_of_mapping_order():
    first = lineage_profile()
    second = {
        "containers": {},
        "roles": dict(reversed(list(first["roles"].items()))),
        "event": dict(reversed(list(first["event"].items()))),
        "entity": dict(reversed(list(first["entity"].items()))),
        "source": dict(reversed(list(first["source"].items()))),
        "schema_version": 1,
    }
    assert serialize_profile(first) == serialize_profile(first)
    assert serialize_profile(first) == serialize_profile(second)
    assert json.loads(serialize_profile(first)) == validate_profile(first).to_mapping()


def test_missing_required_role_is_rejected_at_its_exact_profile_path():
    profile = lineage_profile()
    profile["roles"].pop("event_type")
    with pytest.raises(ProfileValidationError) as caught:
        validate_profile(profile, path="profiles.history")
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
        validate_profile(profile, path="profiles.sample")
    assert caught.value.path == path
    assert caught.value.code == code


def test_blank_entity_key_role_is_rejected_at_the_key_path():
    profile = lineage_profile()
    profile["entity"]["keys"]["lot"] = ""
    with pytest.raises(ProfileValidationError) as caught:
        validate_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.entity.keys.lot"
    assert caught.value.code == "blank_value"


def test_blank_column_used_by_an_identity_key_is_rejected_before_it_can_compile():
    profile = lineage_profile()
    profile["roles"]["lot"]["column"] = "  "
    with pytest.raises(ProfileValidationError) as caught:
        validate_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.roles.lot.column"
    assert caught.value.code == "blank_value"


def test_timezone_has_no_implicit_default():
    profile = lineage_profile()
    profile["event"].pop("timezone")
    with pytest.raises(ProfileValidationError) as caught:
        validate_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.event.timezone"
    assert caught.value.code == "missing_field"


def test_invalid_timezone_is_rejected_instead_of_using_machine_local_time():
    profile = lineage_profile()
    profile["event"]["timezone"] = "Factory/Local"
    with pytest.raises(ProfileValidationError) as caught:
        validate_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.event.timezone"
    assert caught.value.code == "invalid_timezone"


@pytest.mark.parametrize("factory", [lineage_profile, transfer_profile])
def test_one_template_accepts_renamed_source_and_physical_columns(factory):
    original = validate_profile(factory())
    renamed = validate_profile(factory(source="renamed_relation", prefix="site_"))
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
    validated = validate_profile(profile)
    assert validated.roles["row_identity"].status == MAPPING_STATUS_INFERRED
    assert validated.roles["lot"].status == MAPPING_STATUS_HUMAN_APPROVED


def test_inferred_mapping_without_a_reason_is_rejected():
    profile = lineage_profile()
    profile["roles"]["row_identity"] = {
        "column": "record_id", "status": MAPPING_STATUS_INFERRED}
    with pytest.raises(ProfileValidationError) as caught:
        validate_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.roles.row_identity.reason"
    assert caught.value.code == "missing_inference_reason"


def test_unknown_fields_are_rejected_instead_of_being_silently_ignored():
    profile = lineage_profile()
    profile["event"]["translator"] = "something"
    with pytest.raises(ProfileValidationError) as caught:
        validate_profile(profile, path="profiles.history")
    assert caught.value.path == "profiles.history.event.translator"
    assert caught.value.code == "unknown_field"


def test_public_contract_does_not_expose_runtime_implementation_details():
    public_text = json.dumps(public_profile_schema(), ensure_ascii=False).lower()
    for hidden in (
            "predicate", "atom", "claim_class", "translator_version", "derivation",
            "canonical_key", "provenance"):
        assert hidden not in public_text


def test_profiles_coexist_beside_legacy_sources_without_changing_legacy_loader(tmp_path):
    config = legacy_lineage_config()
    config[PROFILE_CONFIG_SECTION] = {"future_history": lineage_profile()}
    profiles = validate_profile_section(config)
    assert list(profiles) == ["future_history"]

    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    loaded = ledger_config.load(str(path))
    assert list(loaded["sources"]) == ["legacy_rows"]
    assert loaded[PROFILE_CONFIG_SECTION] == config[PROFILE_CONFIG_SECTION]
    assert "__origin__" not in config


def test_profile_validation_is_pure_and_does_not_mutate_its_input():
    profile = transfer_profile()
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

