# -*- coding: utf-8 -*-
"""총괄 7255b4918 ④ — an entity binding's `entity_type` takes the binding shape: a string is the
type (today), `{kind: column, column}` reads it from each row. Checked per row against what the
predicate admits in that role; the keys are every admitted type's keys together, a row using its
own type's.

  row                                     answer
  admitted type, its key filled           an atom of that type, its keys
  type the role does not admit            that molecule refused (type_not_admitted), others land
  type cell empty                         no_identity
  confirm cell empty (exclude_when)       no atom - not this source's row
  load: a type's key unbound · a key no type has · attributes · a code mapper · register
        without a probe                   refused by name

The SHIPPED sample (entities, `leads_to`) and catalog, plus one candidates relation - the
physical half written here, the way a deployment's own table_config would carry it.
"""
import copy
import json
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.backfill import prepare_v2_cursor_batch                          # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.roleframe import dry_run_event_frame, mapper_context              # noqa: E402
from ledger.setup_bundle import (load_physical_catalog,                      # noqa: E402
                                 require_ready_bundle, validate_bundle,
                                 validate_bundle_errors)
from ledger.setup_registry import compile_setup_snapshot                     # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
CANDIDATES = "cause_candidates"
COLUMNS = ("row_id", "cand_id", "cause_type", "cause_key", "phenomenon_type",
           "phenomenon_key", "certainty", "confirmed", "dt_eqp")


def column(name):
    return {"kind": "column", "column": name}


def typed(type_column, keys):
    return {"kind": "entity", "entity_type": column(type_column), "keys": keys}


SOURCE = {
    "relation": CANDIDATES,
    "read": {"unit": "row", "identity": ["cand_id"], "order_by": ["cand_id"],
             "occurred_at": {"basis": "ingested", "timezone": "Asia/Seoul"},
             "exclude_when": [{"column": "confirmed", "blank": True}]},
    "map": {"implementation_id": "declarative-role", "implementation_version": 1,
            "unit": {"kind": "row"}},
    "bind": {"mappings": {"leads": {"predicate": "leads_to@1", "bind": {
        "subject": typed("cause_type", {"quantity": column("cause_key")}),
        "target": typed("phenomenon_type", {"quantity": column("phenomenon_key"),
                                            "defect_kind": column("phenomenon_key")}),
        "certainty": column("certainty"),
    }}}},
}


@pytest.fixture(scope="module", name="catalog")
def fixture_catalog():
    shipped = dict(load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample")))
    shipped[CANDIDATES] = {"columns": {**{name: "string" for name in COLUMNS},
                                       "created_at": "datetime"},
                           "business_key": "cand_id"}
    return shipped


@pytest.fixture(scope="module", name="shipped")
def fixture_shipped():
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        return json.load(fh)


def document(shipped, source=None):
    out = copy.deepcopy(shipped)
    out["vocabulary"]["leads_to@1"]["object"]["qualifiers"]["optional"].append("certainty")
    out["sources"][CANDIDATES] = copy.deepcopy(source or SOURCE)
    return out


def translate(shipped, catalog, rows):
    snapshot = compile_setup_snapshot(
        require_ready_bundle(validate_bundle(document(shipped), catalog=catalog)),
        trusted_implementations(), catalog=catalog)
    frame = pd.DataFrame([{**{name: row.get(name) for name in COLUMNS},
                           "created_at": pd.Timestamp("2026-10-06T01:00:00+00:00")}
                          for row in rows])
    refusals = []
    frames = prepare_v2_cursor_batch(snapshot, CANDIDATES, frame, refusals=refusals)
    atoms = [atom for event in frames
             for atom in dry_run_event_frame(mapper_context(snapshot, CANDIDATES), event,
                                             role_mapper_registry()).ledger_frame.to_dict("records")]
    return atoms, refusals


def row(index, cause_type, cause_key, phenomenon_type, phenomenon_key, confirmed="yes",
        certainty="suspected"):
    return {"row_id": f"RID-{index}", "cand_id": f"C-{index}", "cause_type": cause_type,
            "cause_key": cause_key, "phenomenon_type": phenomenon_type,
            "phenomenon_key": phenomenon_key, "certainty": certainty, "confirmed": confirmed}


def test_each_row_names_its_own_type_and_only_admitted_ones_land(shipped, catalog):
    atoms, refusals = translate(shipped, catalog, [
        row(1, "quantity", "q-temp", "defect_kind", "d-void"),
        row(2, "quantity@1", "q-a", "quantity", "q-b", certainty="confirmed"),
        row(3, "defect_kind", "d-x", "quantity", "q-c"),          # not an admitted subject
        row(4, "quantity", "q-d", "defect_kind", "d-y", confirmed=""),   # not confirmed
        row(5, "", "q-e", "defect_kind", "d-z"),                  # no type
        row(6, "quantity", "", "defect_kind", "d-w"),             # its own type's key empty
    ])
    leads = sorted(((atom["subject_type"], atom["subject_keys"], atom["object_payload"])
                    for atom in atoms if atom["predicate"] == "leads_to"), key=str)
    assert leads == sorted([
        ("quantity", {"quantity": "q-temp"},
         {"type": "defect_kind", "keys": {"defect_kind": "d-void"},
          "qualifiers": {"certainty": "suspected"}}),
        ("quantity", {"quantity": "q-a"},
         {"type": "quantity", "keys": {"quantity": "q-b"},
          "qualifiers": {"certainty": "confirmed"}}),
    ], key=str), "each row's own type, and only that type's keys"
    assert sorted(refusal.reason for refusal in refusals) == [
        "no_identity", "no_identity", "type_not_admitted"]
    (not_admitted,) = [r for r in refusals if r.reason == "type_not_admitted"]
    assert "'defect_kind'" in not_admitted.detail and "subject" in not_admitted.detail


def test_a_named_type_reads_as_it_did(shipped, catalog):
    """A string `entity_type` is today's: the shipped sample validates exactly as before."""
    assert [(issue.code, issue.path) for issue in validate_bundle_errors(
        shipped, catalog=catalog)] == []


@pytest.mark.parametrize("change,code,where", [
    (lambda s: s["bind"]["mappings"]["leads"]["bind"]["target"]["keys"].pop("defect_kind"),
     "invalid_entity_ref", "bind.target.keys"),
    (lambda s: s["bind"]["mappings"]["leads"]["bind"]["subject"]["keys"].update(
        nosuch=column("cause_key")), "invalid_entity_ref", "bind.subject.keys.nosuch"),
    (lambda s: s["bind"]["mappings"]["leads"]["bind"]["subject"].update(
        attributes={"dt_eqp": column("dt_eqp")}), "invalid_binding", "bind.subject.attributes"),
    (lambda s: s["map"].update(implementation_id="map-transition-role"),
     "invalid_binding", "bind.subject.entity_type"),
    (lambda s: s["bind"]["mappings"]["leads"]["bind"]["subject"].update(
        entity_type={"kind": "constant", "value": "quantity"}),
     "invalid_binding", "bind.subject.entity_type"),
], ids=["a type's key unbound", "a key no type has", "attributes", "a code mapper",
        "not a column"])
def test_a_shape_that_cannot_be_read_per_row_is_refused_at_load(shipped, catalog, change,
                                                                  code, where):
    source = copy.deepcopy(SOURCE)
    change(source)
    found = {(issue.code, issue.path) for issue in validate_bundle_errors(
        document(shipped, source), catalog=catalog)}
    assert any(found_code == code and where in path for found_code, path in found), found


def test_an_admitted_type_with_source_attributes_is_refused(shipped, catalog):
    """A type read per row cannot inherit `bind.entities.<type>.attributes` - which type's?"""
    doc = document(shipped)
    doc["vocabulary"]["leads_to@1"]["subjects"].append("dtjob@1")
    source = doc["sources"][CANDIDATES]
    source["bind"]["mappings"]["leads"]["bind"]["subject"]["keys"]["dt_job"] = column(
        "cause_key")
    source["bind"]["entities"] = {"dtjob@1": {"attributes": {"dt_eqp": column("dt_eqp")}}}
    found = {(issue.code, issue.path) for issue in validate_bundle_errors(doc, catalog=catalog)}
    assert ("invalid_binding", f"bundle.sources.{CANDIDATES}.bind.mappings.leads.bind.subject"
            ".entity_type") in found, found
