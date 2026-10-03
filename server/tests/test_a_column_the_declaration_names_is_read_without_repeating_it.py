# -*- coding: utf-8 -*-
"""총괄 c38eae7cf + 33c930e98 (소유자 「바인드 컬럼 다 채웠는데 자꾸 안채웠다고 에러남」): a column a
binding, `bind.entities.<type>.attributes`, a mapper's group or a `when` names is in the named set
(`bound_select_columns`, what the row print covers).

⚰️ `map.input_columns` retired (소유자 10-03, 총괄 2a8d9073c): the read brings every column of the
relation, so a file that writes the list - even an empty one - gets the atoms one that does not.
The form rows this file measured (locked chips, the everything-default) retired with it.

The frame a preview gets is the rows laid out as the cursor SELECTs them (`base_select_columns`),
a column the fixture row does not carry arriving as NULL.
"""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from support.read_frame import as_read                                  # noqa: E402
from ledger.config_authoring import authoring_plan                      # noqa: E402
from ledger.event_frame import base_select_columns, bound_select_columns  # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.runtime_v2 import last_cursor, preview_cursor_batch          # noqa: E402
from ledger.setup_bundle import (                                        # noqa: E402
    load_physical_catalog, require_ready_bundle, validate_bundle, validate_bundle_errors)
from ledger.setup_registry import compile_setup_snapshot                 # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
CATALOG = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))

#: The box's group source over `dt_log`, read by the code mapper `dt-job-role`.
DT_JOB_GROUP = {
    "relation": "dt_log",
    "read": {"unit": "group", "identity": ["dt_job"], "group_by": ["dt_job"],
             "order_by": ["dt_job", "dt_cell_key"], "cursor": {"columns": ["dt_job", "dt_cell_key"]},
             "occurred_at": {"basis": "ingested", "timezone": "Asia/Seoul"}},
    "map": {"implementation_id": "dt-job-role", "implementation_version": 1,
            "unit": {"kind": "group_by", "columns": ["dt_job"]},
            "input_columns": ["dt_eqp", "dt_index", "dt_job", "event_time"]},
    "bind": {"entities": {"dtjob@1": {"attributes": {"dt_eqp": {"kind": "column", "column": "dt_eqp"}}}},
             "mappings": {
                 "counted": {"predicate": "has_netdie@1", "bind": {
                     "occurred_at": {"kind": "column", "column": "event_time"},
                     "subject": {"kind": "entity", "entity_type": "dtjob@1",
                                 "keys": {"dt_job": {"kind": "column", "column": "dt_job"}}},
                     "value": {"kind": "column", "column": "dt_index"}}},
                 "register": {"predicate": "register@1", "bind": {
                     "occurred_at": {"kind": "column", "column": "event_time"},
                     "subject": {"kind": "entity", "entity_type": "dtjob@1",
                                 "keys": {"dt_job": {"kind": "column", "column": "dt_job"}}}}}}},
}

ROWS = {
    "transfer_event": [{"row_id": "T1", "dt_cell_key": "K1", "core_wafer_id": "W7", "c_wx": 1.0,
                        "c_wy": 2.0, "dt_job_id": "J1", "b_wx": 3.0, "b_wy": 4.0, "dt_job": "J1",
                        "dt_x": 3.0, "dt_y": 4.0, "event_time": "2026-09-30 11:00:00", "product": None}],
    "dt_job": [{"row_id": "D1", "dt_job": "J1", "netdie_count": 7, "dt_eqp": "EQ1",
                "event_time": "2026-09-30 11:00:00", "created_at": "2026-09-30 11:05:00"}],
    "wafer_process_recipe": [{"row_id": "P%d" % i, "wafer_id": "W%d" % i, "recipe_id": "R1",
                              "step": "S1", "eventtime": "2026-09-30 12:00:00", "mat_type": kind}
                             for i, kind in ((1, ""), (2, "DT"))],
    "dt_job_group": [{"row_id": "L%d" % i, "dt_job": "J1", "dt_cell_key": "K%d" % i, "dt_eqp": "EQ1",
                      "dt_index": i, "event_time": "2026-09-30 13:00:00", "core_wafer_id": "W1",
                      "created_at": "2026-09-30 13:05:00",
                      "product": None} for i in (1, 2, 3)],
}


def _document(with_group=False):
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    if with_group:
        document["sources"]["dt_job_group"] = copy.deepcopy(DT_JOB_GROUP)
    return document


def _stripped(document):
    """No source writes `input_columns`."""
    out = copy.deepcopy(document)
    for source in out["sources"].values():
        source["map"].pop("input_columns", None)
    return out


def _written(document):
    """Every source writes `input_columns: []` - what read only the named columns before."""
    out = copy.deepcopy(document)
    for source in out["sources"].values():
        source["map"]["input_columns"] = []
    return out


def _snapshot(document):
    bundle = require_ready_bundle(validate_bundle(document, catalog=CATALOG))
    return compile_setup_snapshot(bundle, trusted_implementations(), catalog=CATALOG)


def _named(source):
    """What the declaration names outside `input_columns` - the test's own count."""
    named = set()

    def walk(binding):
        if isinstance(binding, dict) and binding.get("kind") == "column":
            named.add(binding["column"])
        elif isinstance(binding, dict) and binding.get("kind") == "entity":
            for group in ("keys", "attributes"):
                for inner in (binding.get(group) or {}).values():
                    walk(inner)

    for mapping in source["bind"].get("mappings", {}).values():
        named.update((mapping.get("when") or {}).keys())
        for role in mapping["bind"].values():
            walk(role)
    for item in (source["bind"].get("entities") or {}).values():
        for inner in (item.get("attributes") or {}).values():
            walk(inner)
    named.update((source["map"].get("unit") or {}).get("columns") or ())
    return named


def _semantics(snapshot, source):
    plan = snapshot.source_plans[source]
    frame = as_read(plan, ROWS[source])
    preview = preview_cursor_batch(snapshot, source, frame, last_cursor(plan, frame),
                                   role_mapper_registry(), known_registrations=())
    fields = ("predicate", "subject_type", "subject_keys", "object_kind", "object_payload",
              "occurred_at", "occurred_at_basis", "derivation", "source_event_id")
    return sorted(json.dumps({f: a.get(f) for f in fields}, sort_keys=True, default=str)
                  for a in preview.candidate_semantics), len(preview.refusals)


SOURCES = ("transfer_event", "dt_job", "wafer_process_recipe", "dt_job_group")


@pytest.fixture(scope="module", name="declared")
def fixture_declared():
    return _snapshot(_written(_document(with_group=True)))


@pytest.fixture(scope="module", name="stripped")
def fixture_stripped():
    return _snapshot(_stripped(_document(with_group=True)))


def test_a_declaration_with_or_without_input_columns_is_accepted():
    """The owner's case: a key column bound (transfer_event's b_wx), an entity attribute
    (dt_job's dt_eqp), a group read by a code mapper, a `when` column."""
    assert validate_bundle_errors(_stripped(_document(with_group=True)), catalog=CATALOG) == ()
    assert validate_bundle_errors(_written(_document(with_group=True)), catalog=CATALOG) == ()


@pytest.mark.parametrize("source", SOURCES)
def test_every_column_the_declaration_names_is_selected(stripped, source):
    named = _named(_document(with_group=True)["sources"][source])
    assert named, "canary: the source names columns"
    plan = stripped.source_plans[source]
    assert named <= set(bound_select_columns(plan))
    assert set(CATALOG[plan.relation]["columns"]) <= set(base_select_columns(plan))


@pytest.mark.parametrize("source", SOURCES)
def test_the_atoms_are_the_ones_the_repeating_declaration_writes(declared, stripped, source):
    """A written `input_columns: []` narrows nothing: the same atoms, the same refusals."""
    before, before_refused = _semantics(declared, source)
    after, after_refused = _semantics(stripped, source)
    assert before, "canary: the source writes atoms"
    assert (after, after_refused) == (before, before_refused)


def test_a_column_only_the_mappers_group_names_is_selected_and_must_exist():
    """`dt_lot` is named by `map.unit.columns` alone - no read term, no binding."""
    document = _stripped(_document(with_group=True))
    document["sources"]["dt_job_group"]["map"]["unit"]["columns"] = ["dt_job", "dt_lot"]
    plan = _snapshot(document).source_plans["dt_job_group"]
    assert "dt_lot" in bound_select_columns(plan)
    document["sources"]["dt_job_group"]["map"]["unit"]["columns"] = ["dt_job", "no_such_column"]
    assert [(e.code, e.path) for e in validate_bundle_errors(document, catalog=CATALOG)] == [
        ("unknown_column", "bundle.sources.dt_job_group.map.unit.columns")]


@pytest.mark.parametrize("profile", [{}, {"mappings": {"s": {}}}, {"mappings": {"s": {"bind": None}}},
                                     {"entities": {"dtjob@1": None}}])
def test_a_half_built_profile_does_not_blank_the_form(profile):
    """S-196: a half-built `bind` raised inside the form plan and blanked it."""
    document = _document()
    document["sources"]["dt_job"]["bind"] = profile
    paths = [row["path"] for row in authoring_plan(document, CATALOG)["fields"]]
    assert any(path.startswith("bundle.sources.dt_job.map.") for path in paths)
