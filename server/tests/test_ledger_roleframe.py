"""Ledger v2 Stage 4 focused RoleFrame and Pack compiler contract tests."""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from ledger.envelope import Atom, source_event_identity
from ledger.roleframe import (
    BaseLedgerMapper,
    DeclarativeRoleMapper,
    EVENT_FRAME_REQUIRED_ATTRS,
    ROLE_FRAME_COLUMNS,
    RoleEmission,
    RoleFrameError,
    RoleMapperImplementationRegistry,
    compile_role_frame,
    dry_run_event_frame,
    map_event_frame,
    mapper_context,
)
from test_ledger_setup_bundle import logical_bundle
from test_ledger_setup_registry import snapshot


OCCURRED_AT = pd.Timestamp("2026-08-17T10:30:00+09:00")
MOLECULE_REF = "input_rows:event:E-1"
RAW_REF = "input_rows:record:R-1"


def event_frame(compiled, rows=None):
    rows = rows or [{
        "source_id": "IN-1",
        "target_id": "OUT-1",
        "event_at": OCCURRED_AT,
        "event_key": "E-1",
    }]
    frame = pd.DataFrame(rows)
    event_id, _ = source_event_identity(
        "input_rows", OCCURRED_AT.to_pydatetime(),
        molecule_ref=MOLECULE_REF, source_raw_ref=RAW_REF)
    frame.attrs.update({
        "source_id": "input_rows",
        "source_event_id": event_id,
        "molecule_ref": MOLECULE_REF,
        "source_raw_ref": RAW_REF,
        "setup_snapshot_hash": compiled.snapshot_sha256,
    })
    return frame


def implementations(mapper_type=DeclarativeRoleMapper):
    registry = RoleMapperImplementationRegistry()
    registry.register("map-transition-role", 1, mapper_type)
    return registry.seal()


def semantic_frame(frame):
    return [{column: frame.iloc[position][column]
             for column in frame.columns}
            for position in range(len(frame))]


def constant(value, *, status="approved", origin="user_declared"):
    return {
        "kind": "constant",
        "value": value,
        "binding_origin": origin,
        "approval_status": status,
    }


def test_declarative_column_constant_entity_bindings_make_role_frame():
    raw = logical_bundle()
    raw["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"] = (
        constant("fixed-event"))
    compiled = snapshot(raw)
    context = mapper_context(compiled, "input_rows")

    frame = map_event_frame(context, event_frame(compiled), implementations())

    assert tuple(frame.columns) == ROLE_FRAME_COLUMNS
    assert len(frame) == 1
    roles = frame.iloc[0]["roles"]
    assert roles["subject"] == {"type": "InputEntity@1", "keys": {"input_id": "IN-1"}}
    assert roles["target"] == {"type": "OutputEntity@1", "keys": {"output_id": "OUT-1"}}
    assert roles["occurred_at"] == OCCURRED_AT
    assert roles["event_key"] == "fixed-event"


class EquivalentPythonMapper(BaseLedgerMapper):
    def interpret_unit(self, context, unit, profile):
        mapping = profile.mappings[0]
        row = unit.iloc[0]
        return [RoleEmission(
            mapping_id=mapping.mapping_id,
            claim_ref=mapping.claim_ref,
            roles={
                "subject": {"type": "InputEntity@1",
                            "keys": {"input_id": row["source_id"]}},
                "target": {"type": "OutputEntity@1",
                           "keys": {"output_id": row["target_id"]}},
                "occurred_at": row["event_at"],
                "event_key": row["event_key"],
            },
            source_row_refs=(unit.attrs["source_raw_ref"],),
        )]


def test_registered_python_mapper_and_declarative_mapper_share_contract():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    source = event_frame(compiled)

    declarative = map_event_frame(context, source, implementations())
    custom = map_event_frame(context, source, implementations(EquivalentPythonMapper))

    assert tuple(declarative.columns) == tuple(custom.columns) == ROLE_FRAME_COLUMNS
    assert semantic_frame(declarative) == semantic_frame(custom)


def test_mapper_override_of_final_map_is_rejected():
    class UnsafeMapper(BaseLedgerMapper):
        def map(self, context, event_frame, descriptor, profile):
            return event_frame

        def interpret_unit(self, context, unit, profile):
            return []

    registry = RoleMapperImplementationRegistry()
    with pytest.raises(RoleFrameError) as caught:
        registry.register("unsafe", 1, UnsafeMapper)
    assert caught.value.to_mapping() == {
        "code": "unsupported_mapper_override",
        "path": "mapper_type.map",
        "message": "BaseLedgerMapper.map() is final and cannot be overridden",
    }


def test_unsealed_mapper_registry_cannot_execute():
    compiled = snapshot()
    registry = RoleMapperImplementationRegistry()
    registry.register("map-transition-role", 1, DeclarativeRoleMapper)
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled), registry)
    assert caught.value.code == "mapper_registry_not_sealed"
    assert caught.value.path == "mapper_registry"


def test_pack_compiler_is_the_only_entity_ref_payload_builder():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    role_frame = map_event_frame(context, event_frame(compiled), implementations())

    ledger_frame = compile_role_frame(context, role_frame)

    assert ledger_frame.iloc[0]["subject_type"] == "InputEntity@1"
    assert ledger_frame.iloc[0]["subject_keys"] == {"input_id": "IN-1"}
    assert ledger_frame.iloc[0]["predicate"] == "moves_to@1"
    assert ledger_frame.iloc[0]["object_kind"] == "entity_ref"
    assert ledger_frame.iloc[0]["object_payload"] == {
        "type": "OutputEntity@1",
        "keys": {"output_id": "OUT-1"},
        "qualifiers": {"event_key": "E-1"},
    }
    assert ledger_frame.iloc[0]["derivation"] == "main_transition"
    assert ledger_frame.iloc[0]["source_translator_ver"].endswith("#main_transition")


@pytest.mark.parametrize(
    ("object_kind", "role_kind", "value", "payload"),
    [
        ("value", "quantity", 12.5, {"value": 12.5}),
        ("event_ref", "identity", "EVENT-42", {"event": "EVENT-42"}),
    ],
)
def test_pack_compiler_supports_closed_scalar_object_kinds(
        object_kind, role_kind, value, payload):
    raw = logical_bundle()
    raw["vocabulary"]["moves_to@1"]["object"] = {
        "kind": object_kind,
        "qualifiers": {"required": [], "optional": []},
    }
    claim = raw["packs"]["movement@1"]["claims"]["transition"]
    claim["roles"].pop("target")
    claim["roles"].pop("event_key")
    claim["roles"]["result"] = {"kind": role_kind, "required": True}
    claim["emit"]["object"] = {"kind": object_kind, "value": "$result"}
    mapping = raw["profiles"]["input-transition@1"]["mappings"][0]
    mapping["bind"].pop("target")
    mapping["bind"].pop("event_key")
    mapping["bind"]["result"] = constant(value)
    raw["mappers"]["map-transition@1"]["emits"] = ["movement@1/transition"]
    compiled = snapshot(raw)

    result = dry_run_event_frame(
        mapper_context(compiled, "input_rows"), event_frame(compiled),
        implementations())

    assert result.ledger_frame.iloc[0]["object_kind"] == object_kind
    assert result.ledger_frame.iloc[0]["object_payload"] == payload


class InvalidEntityMapper(EquivalentPythonMapper):
    def interpret_unit(self, context, unit, profile):
        emission = super().interpret_unit(context, unit, profile)[0]
        roles = dict(emission.roles)
        roles["target"] = {"type": "OutputEntity@1", "keys": {"wrong": "OUT-1"}}
        return [RoleEmission(
            mapping_id=emission.mapping_id,
            claim_ref=emission.claim_ref,
            roles=roles,
            source_row_refs=emission.source_row_refs,
        )]


def test_invalid_stage_local_entity_shape_is_rejected_before_ledger_frame():
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(InvalidEntityMapper))
    assert caught.value.code == "invalid_entity_ref"
    assert caught.value.path == "role_frame.rows[0].roles.target.keys"
    assert caught.value.message


class WrongStageEntityMapper(EquivalentPythonMapper):
    def interpret_unit(self, context, unit, profile):
        emission = super().interpret_unit(context, unit, profile)[0]
        roles = dict(emission.roles)
        roles["subject"] = {
            "type": "OutputEntity@1", "keys": {"output_id": "OUT-1"}}
        return [RoleEmission(
            mapping_id=emission.mapping_id,
            claim_ref=emission.claim_ref,
            roles=roles,
            source_row_refs=emission.source_row_refs,
        )]


def test_python_mapper_cannot_substitute_another_registered_stage_entity():
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(WrongStageEntityMapper))
    assert caught.value.code == "invalid_entity_ref"
    assert caught.value.path == "role_frame.rows[0].roles.subject.type"
    assert "Profile binding" in caught.value.message


class RawDataFrameMapper(BaseLedgerMapper):
    def interpret_unit(self, context, unit, profile):
        return pd.DataFrame({"raw": ["ledger"]})


class RawAtomMapper(BaseLedgerMapper):
    def interpret_unit(self, context, unit, profile):
        return [Atom(
            subject_type="InputEntity@1", subject_keys={"input_id": "IN-1"},
            predicate="moves_to@1")]


@pytest.mark.parametrize("mapper_type", [RawDataFrameMapper, RawAtomMapper])
def test_raw_dataframe_or_atom_mapper_output_is_rejected(mapper_type):
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(mapper_type))
    assert caught.value.code == "unsupported_mapper_output"
    assert caught.value.path.startswith("mapper.units[0]")


def test_role_and_ledger_frames_are_deterministic_under_row_reordering():
    raw = logical_bundle()
    raw["mappers"]["map-transition@1"]["unit"] = {"kind": "row"}
    compiled = snapshot(raw)
    rows = [
        {"source_id": "IN-2", "target_id": "OUT-2",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
        {"source_id": "IN-1", "target_id": "OUT-1",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
    ]
    first_input = event_frame(compiled, rows)
    second_input = event_frame(compiled, list(reversed(rows)))
    context = mapper_context(compiled, "input_rows")

    first_roles = map_event_frame(context, first_input, implementations())
    second_roles = map_event_frame(context, second_input, implementations())
    first_ledger = compile_role_frame(context, first_roles)
    second_ledger = compile_role_frame(context, second_roles)

    assert semantic_frame(first_roles) == semantic_frame(second_roles)
    assert semantic_frame(first_ledger) == semantic_frame(second_ledger)
    refs = [value for values in first_roles["source_row_refs"].tolist()
            for value in values]
    assert len(refs) == len(set(refs)) == 2


def test_duplicate_derived_row_identity_requires_explicit_source_row_ref():
    raw = logical_bundle()
    raw["mappers"]["map-transition@1"]["unit"] = {"kind": "row"}
    compiled = snapshot(raw)
    row = {"source_id": "IN-1", "target_id": "OUT-1",
           "event_at": OCCURRED_AT, "event_key": "E-1"}
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"),
            event_frame(compiled, [row, dict(row)]), implementations())
    assert caught.value.code == "ambiguous_source_row_ref"
    assert caught.value.path == "event_frame.rows"


def test_group_by_mapper_units_are_internal_and_deterministic():
    raw = logical_bundle()
    raw["mappers"]["map-transition@1"]["unit"] = {
        "kind": "group_by", "columns": ["target_id"]}
    compiled = snapshot(raw)
    rows = [
        {"source_id": "IN-2", "target_id": "OUT-2",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
        {"source_id": "IN-1", "target_id": "OUT-1",
         "event_at": OCCURRED_AT, "event_key": "E-1"},
    ]
    context = mapper_context(compiled, "input_rows")

    first = map_event_frame(
        context, event_frame(compiled, rows), implementations(EquivalentPythonMapper))
    second = map_event_frame(
        context, event_frame(compiled, list(reversed(rows))),
        implementations(EquivalentPythonMapper))

    assert len(first) == 2
    assert semantic_frame(first) == semantic_frame(second)


def test_binding_approval_metadata_never_creates_claim_class():
    raw_a = logical_bundle()
    raw_b = logical_bundle()
    raw_b["profiles"]["input-transition@1"]["mappings"][0]["bind"]["event_key"][
        "binding_origin"] = "imported"
    compiled_a = snapshot(raw_a)
    compiled_b = snapshot(raw_b)
    result_a = dry_run_event_frame(
        mapper_context(compiled_a, "input_rows"), event_frame(compiled_a),
        implementations())
    result_b = dry_run_event_frame(
        mapper_context(compiled_b, "input_rows"), event_frame(compiled_b),
        implementations())

    semantic_columns = ("subject_type", "subject_keys", "predicate", "object_kind",
                        "object_payload", "occurred_at", "derivation")
    assert {name: result_a.ledger_frame.iloc[0][name] for name in semantic_columns} == {
        name: result_b.ledger_frame.iloc[0][name] for name in semantic_columns}
    assert all("claim_class" not in str(value)
               for value in result_a.ledger_frame.iloc[0].tolist())


@pytest.mark.parametrize("change", ["pack", "vocabulary", "entity"])
def test_registry_semantic_changes_reach_snapshot_and_provenance(change):
    baseline = snapshot()
    raw = logical_bundle()
    if change == "pack":
        raw["packs"]["movement@1"]["claims"]["transition"]["roles"]["note"] = {
            "kind": "attribute", "required": False}
    elif change == "vocabulary":
        raw["vocabulary"]["moves_to@1"]["layer"] = "source"
    else:
        raw["entities"]["InputEntity@1"]["key_types"] = {"input_id": "string"}
    changed = snapshot(raw)

    result = dry_run_event_frame(
        mapper_context(changed, "input_rows"), event_frame(changed), implementations())

    assert changed.snapshot_sha256 != baseline.snapshot_sha256
    assert result.snapshot_hash == changed.snapshot_sha256
    assert changed.snapshot_sha256 in result.ledger_frame.iloc[0]["source_translator_ver"]
    assert result.provenance["setup_snapshot_hash"] == changed.snapshot_sha256


def test_dry_run_returns_role_ledger_gate_preview_and_provenance_without_runtime():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    result = dry_run_event_frame(
        context, event_frame(compiled), implementations())

    assert len(result.role_frame) == len(result.ledger_frame) == 1
    assert result.gate_preview == {
        "status": "candidate",
        "atom_count": 1,
        "source_event_id": str(result.role_frame.iloc[0]["source_event_id"]),
        "declared_derivations": ("main_transition",),
        "declared_subject_types": ("InputEntity@1",),
    }
    assert result.provenance["mapping_ids"] == ("main_transition",)
    assert not hasattr(context, "db")
    assert not hasattr(context, "cursor")
    assert not hasattr(context, "store")


def test_event_frame_context_and_snapshot_hash_are_fail_closed():
    compiled = snapshot()
    context = mapper_context(compiled, "input_rows")
    frame = event_frame(compiled)
    del frame.attrs["molecule_ref"]
    with pytest.raises(RoleFrameError) as missing:
        map_event_frame(context, frame, implementations())
    assert missing.value.to_mapping() == {
        "code": "missing_event_context",
        "path": "event_frame.attrs.molecule_ref",
        "message": "attribute is required",
    }

    frame = event_frame(compiled)
    frame.attrs["setup_snapshot_hash"] = "0" * 64
    with pytest.raises(RoleFrameError) as mismatch:
        map_event_frame(context, frame, implementations())
    assert mismatch.value.code == "snapshot_mismatch"
    assert mismatch.value.path == "event_frame.attrs.setup_snapshot_hash"


class NaiveTimeMapper(EquivalentPythonMapper):
    def interpret_unit(self, context, unit, profile):
        emission = super().interpret_unit(context, unit, profile)[0]
        roles = dict(emission.roles)
        roles["occurred_at"] = datetime(2026, 8, 17, 10, 30)
        return [RoleEmission(
            mapping_id=emission.mapping_id,
            claim_ref=emission.claim_ref,
            roles=roles,
            source_row_refs=emission.source_row_refs,
        )]


def test_naive_time_role_is_rejected_with_exact_path():
    compiled = snapshot()
    with pytest.raises(RoleFrameError) as caught:
        map_event_frame(
            mapper_context(compiled, "input_rows"), event_frame(compiled),
            implementations(NaiveTimeMapper))
    assert caught.value.code == "invalid_time_role"
    assert caught.value.path == "role_frame.rows[0].roles.occurred_at"


def test_roleframe_module_has_no_runtime_or_database_imports():
    path = Path(__file__).parents[1] / "ledger" / "roleframe.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    assert not any(name in imports for name in {
        "sqlalchemy", "psycopg2", "database", "ledger.store", "ledger.gate",
        "ledger.cursor", "virtual_join_config",
    })


def test_all_eventframe_context_attributes_are_preserved_in_roleframe():
    compiled = snapshot()
    source = event_frame(compiled)
    result = map_event_frame(
        mapper_context(compiled, "input_rows"), source, implementations())
    for name in EVENT_FRAME_REQUIRED_ATTRS:
        assert result.attrs[name] == source.attrs[name]
