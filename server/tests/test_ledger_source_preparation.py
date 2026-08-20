"""Stage 5 tests for the existing-cursor -> pandas SourcePreparer boundary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import ast
import copy
from types import MappingProxyType

import pandas as pd
import pytest

from ledger.backfill import prepare_v2_cursor_batch, v2_base_select_columns
from ledger.roleframe import (
    DeclarativeRoleMapper,
    MapperContext,
    RoleMapperImplementationRegistry,
    dry_run_event_frame,
)
from ledger.source_preparation import (
    BaseSourcePreparer,
    DEFAULT_JOIN_CHUNK_SIZE,
    DirectJoinSourcePreparer,
    JoinRightRow,
    PREPARATION_METRICS_ATTR,
    PREPARATION_PROVENANCE_ATTR,
    SQLAlchemyVerifiedJoinBatchReader,
    SourcePreparationError,
    SourcePreparerImplementationRegistry,
    VerifiedJoinBatchReader,
    dependency_replay_worklist,
    preparation_action_candidate,
    right_value_fingerprint,
)
from ledger.setup_bundle import LedgerSetupValidationError
from test_ledger_setup_bundle import (
    binding, driver_mapper, driver_preparation, logical_bundle, source_profile)
from test_ledger_setup_registry import snapshot


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def base_rows(count=1):
    return pd.DataFrame([{
        "record_id": f"R-{index:04d}",
        "join_id": f"J-{index:04d}",
        "source_id": f"IN-{index:04d}",
        "event_at": NOW + timedelta(seconds=index),
        "event_key": f"E-{index:04d}",
    } for index in range(count)])


def right_row(key, target=None, *, row_id=None, updated_at=NOW):
    return JoinRightRow(
        key=(key,),
        identity={"row_id": row_id or f"RIGHT-{key}"},
        values={"target_id": target or f"OUT-{key}"},
        updated_at=updated_at,
    )


def entity_binding(entity_type, columns):
    return {
        "kind": "entity",
        "entity_type": entity_type,
        "keys": {key: binding(column) for key, column in columns.items()},
        "binding_origin": "user_declared",
        "approval_status": "approved",
    }


#: The DT chain fixture describes a plant of its own, so it gets a `table_config.json` of
#: its own rather than a `tables` section back inside the bundle.  Written out here, apart
#: from `dt_chain_bundle()` and never derived from it: the point of the physical half
#: living elsewhere is that the two sides CAN disagree, and a catalog computed from the
#: bundle would agree by construction.  See `logical_catalog` in `test_ledger_setup_bundle`.
DT_CHAIN_CATALOG = {
    "dt_log": {
        "columns": {
            "record_id": "string", "dt_job_id": "string",
            "event_at": "datetime", "core_wafer": "string",
            "core_x": "number", "core_y": "number",
            "recorded_dt_lot": "string",
        },
        "business_key": "record_id",
    },
    "dt_inventory": {
        "columns": {
            "dt_job_id": "string", "dt_lot": "string", "dt_slot": "number",
            "dt_offset_x": "number", "dt_offset_y": "number",
            "bond_wafer": "string", "bond_offset_x": "number",
            "bond_offset_y": "number", "bond_layer": "number",
            "final_chip": "string",
        },
        "business_key": "dt_job_id",
        "indexes": [{"name": "uq_dt_inventory_job", "columns": ["dt_job_id"],
                     "unique": True}],
    },
}


def dt_chain_bundle():
    raw = logical_bundle(source_name="dt_log")
    raw["virtual_joins"] = {
        "dt_job_to_inventory": {
            "left_table": "dt_log", "right_table": "dt_inventory",
            "join_key": [{"left": "dt_job_id", "right": "dt_job_id"}],
            "expose": [
                "dt_lot", "dt_slot", "dt_offset_x", "dt_offset_y",
                "bond_wafer", "bond_offset_x", "bond_offset_y", "bond_layer",
                "final_chip",
            ],
            "join_cardinality": "one", "enabled": True,
        },
    }
    raw["vocabulary"] = {
        "transferred_to@1": {
            "status": "active", "layer": "ontology",
            "subjects": ["CoreDie@1", "DTDie@1"],
            "object": {
                "kind": "entity_ref", "types": ["DTDie@1", "BondComponent@1"],
                "qualifiers": {"required": ["job"], "optional": []},
            },
        },
        "component_of@1": {
            "status": "active", "layer": "ontology",
            "subjects": ["CoreDie@1"],
            "object": {
                "kind": "entity_ref", "types": ["FinalChip@1"],
                "qualifiers": {"required": [], "optional": []},
            },
        },
    }
    raw["entities"] = {
        "CoreDie@1": {"keys": ["core_wafer", "core_x", "core_y"]},
        "DTDie@1": {"keys": ["dt_lot", "dt_slot", "dt_x", "dt_y"]},
        "BondComponent@1": {
            "keys": ["bond_wafer", "bond_x", "bond_y", "layer"]},
        "FinalChip@1": {"keys": ["chip_id"]},
    }
    preparation = {
        "implementation_id": "prepare-input", "implementation_version": 1,
        "input_columns": ["dt_job_id", "core_x", "core_y"],
        "output_columns": {
                "inventory_dt_lot": "string", "inventory_dt_slot": "number",
                "resolved_dt_x": "number", "resolved_dt_y": "number",
            "inventory_bond_wafer": "string", "resolved_bond_x": "number",
            "resolved_bond_y": "number", "inventory_bond_layer": "number",
            "inventory_final_chip": "string",
        },
        "accepts_verified_join_rules": True,
        "inherit_virtual_join_rules": ["dt_job_to_inventory"],
    }
    mapper = {
        "implementation_id": "map-transition-role", "implementation_version": 1,
        "unit": {"kind": "row"},
        "input_columns": [
            "core_wafer", "core_x", "core_y", "dt_job_id", "event_at",
            "inventory_dt_lot", "inventory_dt_slot", "resolved_dt_x",
            "resolved_dt_y", "inventory_bond_wafer", "resolved_bond_x",
            "resolved_bond_y", "inventory_bond_layer", "inventory_final_chip",
        ],
        "emits": [
            "assembly@1/core_to_dt", "assembly@1/dt_to_bond",
            "assembly@1/core_component"],
    }
    entity_role = {"kind": "entity", "required": True}
    time_role = {"kind": "time", "required": True}
    job_role = {"kind": "identity", "required": True}
    raw["packs"] = {
        "assembly@1": {"claims": {
            "core_to_dt": {
                "roles": {"subject": entity_role, "target": entity_role,
                          "occurred_at": time_role, "job": job_role},
                "emit": {
                    "predicate": "transferred_to@1", "subject": "$subject",
                    "object": {"kind": "entity_ref", "entity": "$target",
                               "qualifiers": {"job": "$job"}},
                    "occurred_at": "$occurred_at",
                },
            },
            "dt_to_bond": {
                "roles": {"subject": entity_role, "target": entity_role,
                          "occurred_at": time_role, "job": job_role},
                "emit": {
                    "predicate": "transferred_to@1", "subject": "$subject",
                    "object": {"kind": "entity_ref", "entity": "$target",
                               "qualifiers": {"job": "$job"}},
                    "occurred_at": "$occurred_at",
                },
            },
            "core_component": {
                "roles": {"subject": entity_role, "target": entity_role,
                          "occurred_at": time_role},
                "emit": {
                    "predicate": "component_of@1", "subject": "$subject",
                    "object": {"kind": "entity_ref", "entity": "$target",
                               "qualifiers": {}},
                    "occurred_at": "$occurred_at",
                },
            },
        }},
    }
    core = entity_binding("CoreDie@1", {
        "core_wafer": "core_wafer", "core_x": "core_x", "core_y": "core_y"})
    dt = entity_binding("DTDie@1", {
        "dt_lot": "inventory_dt_lot", "dt_slot": "inventory_dt_slot",
        "dt_x": "resolved_dt_x", "dt_y": "resolved_dt_y"})
    bond = entity_binding("BondComponent@1", {
        "bond_wafer": "inventory_bond_wafer", "bond_x": "resolved_bond_x",
        "bond_y": "resolved_bond_y", "layer": "inventory_bond_layer"})
    final_chip = entity_binding("FinalChip@1", {
        "chip_id": "inventory_final_chip"})
    raw["sources"] = {
        "dt_log": {
            "relation": "dt_log",
            "profile": {
                "packs": ["assembly@1"],
                "mappings": [
                    {"mapping_id": "core_to_dt", "use": "assembly@1/core_to_dt",
                     "bind": {"subject": core, "target": dt,
                              "occurred_at": binding("event_at"),
                              "job": binding("dt_job_id")}},
                    {"mapping_id": "dt_to_bond", "use": "assembly@1/dt_to_bond",
                     "bind": {"subject": dt, "target": bond,
                              "occurred_at": binding("event_at"),
                              "job": binding("dt_job_id")}},
                    {"mapping_id": "core_component", "use": "assembly@1/core_component",
                     "bind": {"subject": core, "target": final_chip,
                              "occurred_at": binding("event_at")}},
                ],
            },
            "driver": {
                "unit": "group", "identity": ["dt_job_id"],
                "group_by": ["dt_job_id"], "order_by": ["record_id"],
                "occurred_at": {"column": "event_at", "timezone": "Asia/Seoul"},
                "cursor": {"columns": ["event_at", "record_id"]},
                "preparation": preparation,
                "mapper": mapper,
            },
        },
    }
    return raw


class FakeJoinReader(VerifiedJoinBatchReader):
    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.calls = []

    def read_chunk(self, descriptor, keys):
        self.calls.append((descriptor, keys))
        return MappingProxyType({
            key: tuple(self.rows.get(key, ()))
            for key in keys if key in self.rows
        })


def reader_for(frame):
    return FakeJoinReader({
        (row.join_id,): (right_row(row.join_id),)
        for row in frame.itertuples(index=False)
    })


def preparers(preparer_type=DirectJoinSourcePreparer):
    registry = SourcePreparerImplementationRegistry()
    registry.register("prepare-input", 1, preparer_type)
    return registry.seal()


def mappers():
    registry = RoleMapperImplementationRegistry()
    registry.register("map-transition-role", 1, DeclarativeRoleMapper)
    return registry.seal()


def issue(exc):
    assert isinstance(exc.value, SourcePreparationError)
    value = exc.value.to_mapping()
    assert value["code"] and value["path"] and value["message"]
    return value


def test_existing_cursor_selects_only_base_physical_columns():
    compiled = snapshot()

    columns = v2_base_select_columns(compiled, "input_rows")

    assert columns == ("event_at", "event_key", "join_id", "record_id", "source_id")
    assert "target_id" not in columns


def test_preparer_output_can_own_event_identity_without_entering_cursor_select():
    raw = logical_bundle()
    driver_preparation(raw)["output_columns"][
        "prepared_event_key"] = "string"
    raw["sources"]["input_rows"]["driver"]["identity"] = [
        "prepared_event_key"]
    raw["sources"]["input_rows"]["driver"]["group_by"] = [
        "prepared_event_key"]
    compiled = snapshot(raw)

    class DerivedEventPreparer(BaseSourcePreparer):
        def prepare_outputs(self, context, base_frame, joins):
            joined = joins["input_to_reference"]
            return {
                "target_id": tuple(
                    joined.value(index, "target_id")
                    for index in range(len(base_frame))),
                "prepared_event_key": tuple("PAIR-1" for _ in range(len(base_frame))),
            }

    base = base_rows(2)
    base["event_at"] = [NOW, NOW]
    assert "prepared_event_key" not in v2_base_select_columns(
        compiled, "input_rows")

    event, = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader_for(base),
        preparers(DerivedEventPreparer))

    assert len(event) == 2
    assert event["prepared_event_key"].tolist() == ["PAIR-1", "PAIR-1"]
    assert '"prepared_event_key":"PAIR-1"' in event.attrs["molecule_ref"]


def test_missing_prepared_event_identity_is_structured_and_fail_closed():
    raw = logical_bundle()
    driver_preparation(raw)["output_columns"][
        "prepared_event_key"] = "string"
    raw["sources"]["input_rows"]["driver"]["identity"] = [
        "prepared_event_key"]
    raw["sources"]["input_rows"]["driver"]["group_by"] = [
        "prepared_event_key"]
    compiled = snapshot(raw)

    class MissingEventPreparer(BaseSourcePreparer):
        def prepare_outputs(self, context, base_frame, joins):
            joined = joins["input_to_reference"]
            return {
                "target_id": tuple(
                    joined.value(index, "target_id")
                    for index in range(len(base_frame))),
                "prepared_event_key": tuple(None for _ in range(len(base_frame))),
            }

    with pytest.raises(SourcePreparationError) as exc:
        prepare_v2_cursor_batch(
            compiled, "input_rows", base_rows(), reader_for(base_rows()),
            preparers(MissingEventPreparer))

    assert issue(exc) == {
        "code": "source_preparation_incomplete",
        "path": "event_frame.rows[0].prepared_event_key",
        "message": "prepared event group identity is missing",
    }


def test_direct_preparer_builds_eventframe_then_the_stage4_compiler_path():
    compiled = snapshot()
    base = base_rows()
    reader = reader_for(base)

    events = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader, preparers())

    assert len(events) == 1
    event = events[0]
    assert event["target_id"].tolist() == ["OUT-J-0000"]
    assert event["source_id"].tolist() == ["IN-0000"]
    assert len(reader.calls) == 1
    assert reader.calls[0][0] is compiled.verified_joins["input_to_reference"]
    assert event.attrs[PREPARATION_METRICS_ATTR] == {
        "join_queries": 1, "source_rows": 1, "unique_join_keys": 1}
    proof = event.attrs[PREPARATION_PROVENANCE_ATTR][0]
    assert proof["rule_id"] == "input_to_reference"
    assert proof["right_relation"] == "reference_rows"
    assert proof["join_key"] == ["J-0000"]
    assert proof["right_identity"] == {"row_id": "RIGHT-J-0000"}
    assert proof["right_updated_at"] == NOW.isoformat()
    assert len(proof["right_value_fingerprint"]) == 64
    assert "verified_joins" in event.attrs["source_raw_ref"]
    assert proof["right_value_fingerprint"] in event.attrs["source_raw_ref"]

    result = dry_run_event_frame(
        MapperContext(compiled, compiled.source_plans["input_rows"]), event, mappers())
    assert len(result.role_frame) == 1
    assert result.ledger_frame.iloc[0]["predicate"] == "moves_to"
    assert result.ledger_frame.iloc[0]["object_payload"] == {
        "type": "OutputEntity",
        "keys": {"output_id": "OUT-J-0000"},
        "qualifiers": {"event_key": "E-0000"},
    }


def test_1001_unique_keys_are_two_batch_reads_not_n_plus_one():
    compiled = snapshot()
    base = base_rows(1001)
    reader = reader_for(base)

    events = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader, preparers())

    assert len(events) == 1001
    assert [len(call[1]) for call in reader.calls] == [DEFAULT_JOIN_CHUNK_SIZE, 1]
    assert all(call[0] is compiled.verified_joins["input_to_reference"]
               for call in reader.calls)


def test_sqlalchemy_reader_is_one_read_only_query_per_supplied_chunk(monkeypatch):
    from sqlalchemy import column
    from database import models

    compiled = snapshot()
    descriptor = compiled.verified_joins["input_to_reference"]

    class RightModel:
        join_id = column("join_id")
        row_id = column("row_id")
        updated_at = column("updated_at")
        target_id = column("target_id")

    class Query:
        def __init__(self):
            self.filters = []
            self.order = ()

        def filter(self, expression):
            self.filters.append(expression)
            return self

        def order_by(self, *expressions):
            self.order = expressions
            return self

        def all(self):
            return [("J-0000", "RIGHT-J-0000", NOW, "OUT-J-0000")]

    class Session:
        def __init__(self):
            self.queries = []

        def query(self, *columns):
            query = Query()
            self.queries.append((columns, query))
            return query

    monkeypatch.setitem(models.DYNAMIC_TABLES, "reference_rows", RightModel)
    session = Session()
    reader = SQLAlchemyVerifiedJoinBatchReader(session)

    result = reader.read_chunk(descriptor, (("J-0000",),))

    assert reader.query_count == 1
    assert len(session.queries) == 1
    assert result[("J-0000",)][0].values == {"target_id": "OUT-J-0000"}
    assert not hasattr(reader, "commit")
    assert not hasattr(reader, "rollback")


@pytest.mark.parametrize(
    ("rows", "code", "action"),
    [
        ({}, "source_preparation_missing", "target_mapping_missing"),
        ({("J-0000",): (
            right_row("J-0000", row_id="A"),
            right_row("J-0000", row_id="B"),
        )}, "source_preparation_ambiguous", "target_mapping_ambiguous"),
    ],
)
def test_zero_or_multiple_right_rows_refuse_before_mapper_and_cursor(rows, code, action):
    compiled = snapshot()
    reader = FakeJoinReader(rows)
    cursor = {"event_at": "BEFORE"}
    mapper_calls = 0

    with pytest.raises(SourcePreparationError) as exc:
        prepare_v2_cursor_batch(
            compiled, "input_rows", base_rows(), reader, preparers())
        mapper_calls += 1
        cursor["event_at"] = "AFTER"

    error = issue(exc)
    assert error["code"] == code
    assert error["path"].startswith(
        "source_preparation.join_rules.input_to_reference.keys.")
    assert mapper_calls == 0
    assert cursor == {"event_at": "BEFORE"}
    candidate = preparation_action_candidate(exc.value, source_id="input_rows")
    assert candidate["action"] == action


def test_missing_join_key_refuses_without_any_right_query():
    compiled = snapshot()
    base = base_rows()
    base.loc[0, "join_id"] = None
    reader = FakeJoinReader()

    with pytest.raises(SourcePreparationError) as exc:
        prepare_v2_cursor_batch(compiled, "input_rows", base, reader, preparers())

    error = issue(exc)
    assert error == {
        "code": "source_preparation_incomplete",
        "path": "source_batch.rows[0].join_id",
        "message": "join key value is missing",
        "details": {"join_key_index": 0, "rule_id": "input_to_reference"},
    }
    assert reader.calls == []


def test_prepared_output_never_overwrites_a_recorded_left_value():
    compiled = snapshot()
    base = base_rows()
    base["target_id"] = ["WRONG-LEFT"]
    reader = reader_for(base)

    with pytest.raises(SourcePreparationError) as exc:
        prepare_v2_cursor_batch(compiled, "input_rows", base, reader, preparers())

    error = issue(exc)
    assert error["code"] == "source_preparation_output_collision"
    assert "target_id" in error["message"]
    assert reader.calls == []


def test_missing_right_row_retries_same_event_after_late_arrival():
    compiled = snapshot()
    base = base_rows()
    reader = FakeJoinReader()
    cursor = "BEFORE"

    with pytest.raises(SourcePreparationError):
        prepare_v2_cursor_batch(compiled, "input_rows", base, reader, preparers())
    assert cursor == "BEFORE"

    reader.rows[("J-0000",)] = (right_row("J-0000"),)
    event, = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader, preparers())
    cursor = event.attrs["source_event_id"]

    assert event["target_id"].tolist() == ["OUT-J-0000"]
    assert cursor != "BEFORE"


def test_successful_right_row_change_yields_dependency_replay_worklist():
    compiled = snapshot()
    base = base_rows()
    event, = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader_for(base), preparers())
    previous = event.attrs[PREPARATION_PROVENANCE_ATTR]
    descriptor = compiled.verified_joins["input_to_reference"]
    changed = right_row("J-0000", target="OUT-CORRECTED",
                        updated_at=NOW + timedelta(minutes=1))
    new_fingerprint = right_value_fingerprint(descriptor, changed)

    worklist = dependency_replay_worklist(previous, ({
        "rule_id": descriptor.rule_id,
        "right_identity": changed.identity,
        "right_value_fingerprint": new_fingerprint,
    },))

    assert len(worklist) == 1
    assert worklist[0]["action"] == "dependency_replay"
    assert worklist[0]["source_event_id"] == str(event.attrs["source_event_id"])
    assert worklist[0]["previous_fingerprint"] != new_fingerprint
    assert worklist[0]["current_fingerprint"] == new_fingerprint


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_unapproved_nested_entity_binding_stops_before_preparer_call(status):
    raw = logical_bundle()
    source_profile(raw)["mappings"][0]["bind"]["subject"][
        "keys"]["input_id"]["approval_status"] = status
    reader = FakeJoinReader()

    with pytest.raises(LedgerSetupValidationError) as exc:
        snapshot(raw)

    assert exc.value.code == "binding_not_approved"
    assert exc.value.path.endswith("bind.subject.keys.input_id.approval_status")
    assert reader.calls == []


def test_missing_prepared_entity_identity_refuses_before_role_mapper():
    compiled = snapshot()
    base = base_rows()
    reader = FakeJoinReader({
        ("J-0000",): (right_row("J-0000", target=None),),
    })
    # The helper's default target would replace None, so preserve an explicit null row.
    reader.rows[("J-0000",)] = (JoinRightRow(
        key=("J-0000",), identity={"row_id": "RIGHT-J-0000"},
        values={"target_id": None}, updated_at=NOW),)
    cursor = "BEFORE"

    with pytest.raises(SourcePreparationError) as exc:
        prepare_v2_cursor_batch(compiled, "input_rows", base, reader, preparers())

    error = issue(exc)
    assert error["code"] == "source_preparation_incomplete"
    assert error["path"] == "event_frame.rows[0].target_id"
    assert cursor == "BEFORE"


def test_multi_core_dt_inventory_builds_stage_local_identity_and_direction_claims():
    compiled = snapshot(dt_chain_bundle(), catalog=DT_CHAIN_CATALOG)

    class AssemblyPreparer(BaseSourcePreparer):
        def prepare_outputs(self, context, base_frame, joins):
            join = joins["dt_job_to_inventory"]
            values = [join.rows[index].values for index in range(len(base_frame))]
            dt_x = [base_frame.iloc[index]["core_x"] + values[index]["dt_offset_x"]
                    for index in range(len(base_frame))]
            dt_y = [base_frame.iloc[index]["core_y"] + values[index]["dt_offset_y"]
                    for index in range(len(base_frame))]
            return {
                "inventory_dt_lot": tuple(value["dt_lot"] for value in values),
                "inventory_dt_slot": tuple(value["dt_slot"] for value in values),
                "resolved_dt_x": tuple(dt_x), "resolved_dt_y": tuple(dt_y),
                "inventory_bond_wafer": tuple(
                    value["bond_wafer"] for value in values),
                "resolved_bond_x": tuple(
                    dt_x[index] + values[index]["bond_offset_x"]
                    for index in range(len(base_frame))),
                "resolved_bond_y": tuple(
                    dt_y[index] + values[index]["bond_offset_y"]
                    for index in range(len(base_frame))),
                "inventory_bond_layer": tuple(
                    value["bond_layer"] for value in values),
                "inventory_final_chip": tuple(
                    value["final_chip"] for value in values),
            }

    base = pd.DataFrame([{
        "record_id": f"DT-R-{index}", "dt_job_id": "DT-JOB-1",
        "event_at": NOW, "core_wafer": "CORE-WF-1",
        "core_x": index, "core_y": index + 10,
        "recorded_dt_lot": "WRONG-LEFT-LOT",
    } for index in range(3)])
    right = JoinRightRow(
        key=("DT-JOB-1",), identity={"row_id": "INV-1"}, updated_at=NOW,
        values={
            "dt_lot": "DT-CONFIRMED", "dt_slot": 7,
            "dt_offset_x": 100, "dt_offset_y": 200,
            "bond_wafer": "BOND-WF-1", "bond_offset_x": 1000,
            "bond_offset_y": 2000, "bond_layer": 12,
            "final_chip": "FINAL-CHIP-1",
        },
    )
    reader = FakeJoinReader({("DT-JOB-1",): (right,)})

    event, = prepare_v2_cursor_batch(
        compiled, "dt_log", base, reader, preparers(AssemblyPreparer))
    result = dry_run_event_frame(
        MapperContext(compiled, compiled.source_plans["dt_log"]), event, mappers())
    ledger = result.ledger_frame

    assert len(event) == 3
    assert event["recorded_dt_lot"].tolist() == ["WRONG-LEFT-LOT"] * 3
    assert event["inventory_dt_lot"].tolist() == ["DT-CONFIRMED"] * 3
    assert len(event.attrs[PREPARATION_PROVENANCE_ATTR]) == 1
    assert len(ledger) == 9
    assert set(ledger["predicate"]) == {"transferred_to", "component_of"}
    assert "same_as" not in set(ledger["predicate"])

    transfers = ledger[ledger["predicate"] == "transferred_to"]
    assert set(transfers["subject_type"]) == {"CoreDie", "DTDie"}
    assert {payload["type"] for payload in transfers["object_payload"]} == {
        "DTDie", "BondComponent"}
    core_to_dt = transfers[transfers["subject_type"] == "CoreDie"]
    assert {payload["keys"]["dt_lot"]
            for payload in core_to_dt["object_payload"]} == {"DT-CONFIRMED"}
    assert {payload["keys"]["dt_x"]
            for payload in core_to_dt["object_payload"]} == {100, 101, 102}

    components = ledger[ledger["predicate"] == "component_of"]
    assert len(components) == 3
    assert set(components["subject_type"]) == {"CoreDie"}
    assert {payload["type"] for payload in components["object_payload"]} == {
        "FinalChip"}
    assert {payload["keys"]["chip_id"]
            for payload in components["object_payload"]} == {"FINAL-CHIP-1"}


def test_custom_preparer_free_hook_can_rename_and_calculate_only_declared_outputs():
    raw = logical_bundle()
    driver_preparation(raw)["output_columns"] = {
        "resolved_target": "string"}
    driver_mapper(raw)["input_columns"] = [
        "source_id", "resolved_target", "event_at", "event_key"]
    source_profile(raw)["mappings"][0]["bind"]["target"][
        "keys"]["output_id"]["column"] = "resolved_target"
    compiled = snapshot(raw)

    class RenamingPreparer(BaseSourcePreparer):
        def prepare_outputs(self, context, base_frame, joins):
            join = joins["input_to_reference"]
            return {"resolved_target": tuple(
                "RESOLVED:" + str(join.value(index, "target_id"))
                for index in range(len(base_frame)))}

    base = base_rows()
    event, = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader_for(base), preparers(RenamingPreparer))

    assert event["resolved_target"].tolist() == ["RESOLVED:OUT-J-0000"]
    assert "target_id" not in event.columns


def test_direct_and_custom_preparer_share_the_same_role_and_pack_compiler():
    compiled = snapshot()
    base = base_rows()

    class EchoPreparer(BaseSourcePreparer):
        def prepare_outputs(self, context, base_frame, joins):
            # Attempting to alter the hook input cannot alter the caller's base frame.
            base_frame.loc[0, "source_id"] = "MUTATED-HOOK-COPY"
            join = joins["input_to_reference"]
            return {"target_id": tuple(
                join.value(index, "target_id") for index in range(len(base_frame)))}

    direct_event, = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader_for(base), preparers())
    custom_event, = prepare_v2_cursor_batch(
        compiled, "input_rows", base, reader_for(base), preparers(EchoPreparer))
    context = MapperContext(compiled, compiled.source_plans["input_rows"])
    direct = dry_run_event_frame(context, direct_event, mappers()).ledger_frame
    custom = dry_run_event_frame(context, custom_event, mappers()).ledger_frame

    assert custom_event["source_id"].tolist() == ["IN-0000"]
    assert direct.to_dict(orient="records") == custom.to_dict(orient="records")


def test_registry_is_sealed_and_common_preparation_pipeline_cannot_be_overridden():
    class BadPreparer(BaseSourcePreparer):
        def prepare_batch(self, context, base_frame, reader):
            return ()

        def prepare_outputs(self, context, base_frame, joins):
            return {}

    registry = SourcePreparerImplementationRegistry()
    with pytest.raises(SourcePreparationError) as exc:
        registry.register("bad", 1, BadPreparer)
    assert issue(exc)["code"] == "unsupported_source_preparer_override"

    registry.register("prepare-input", 1, DirectJoinSourcePreparer)
    registry.seal()
    with pytest.raises(RuntimeError):
        registry.register("another", 1, DirectJoinSourcePreparer)


def test_runtime_module_has_no_cursor_store_gate_atom_or_transaction_capability():
    tree = ast.parse(open(
        "server/ledger/source_preparation.py", encoding="utf-8").read())
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    text = open("server/ledger/source_preparation.py", encoding="utf-8").read()

    assert not any(name.endswith((".store", ".gate")) for name in imports)
    assert "write_batch(" not in text
    assert ".commit(" not in text
    assert ".rollback(" not in text
    assert "atoms_from_ledger_frame" not in text
    assert not hasattr(SQLAlchemyVerifiedJoinBatchReader, "commit")
    assert not hasattr(SQLAlchemyVerifiedJoinBatchReader, "rollback")
