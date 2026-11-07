# -*- coding: utf-8 -*-
"""총괄 2d6a0fd58 ㄱ (소유자 「걷기 뒤에 붙여」), widened 10-14 to every declared type: the walk answer says the type of the
column the ledger read a value from - the value's source, the column that source binds the name to, that column's
table_config type as written (`ledger.setup.declared_value_type`) - never the value's shape.

  a node name    its records and per-world values carry `column_type` ("image", "datetime", "TEXT" ... as declared)
  an edge        its records and the edge carry `column_types: {<qualifier>: <type>}`
  two sources    one name, two sources binding it to columns of two types - each record says its own source's
  no one type    a name bound to two columns of two types in one source: no cell (unknown)
  a reload       the type changed in table_config reaches the next walk, no restart (the singleton is read live)

On the shipped sample's `lot_slot_wafer` (lot_slot --has_wafer--> wafer), compiled from a declaration in tmp_path."""
import copy
import json
import os
import sys
import uuid
from dataclasses import replace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from test_a_test_run_shows_the_atoms_its_rows_became import SOURCE, _document  # noqa: E402
from test_an_attribute_bound_on_a_source_becomes_its_entitys_registration import _atoms  # noqa: E402
from test_the_test_run_reads_until_it_has_a_molecule import _row  # noqa: E402
from chain import ingestion_worker as worker  # noqa: E402
from database import crud  # noqa: E402
from ledger import explorer, setup_bundle  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

OTHER = "lot_slot_wafer_by_lot"
COLUMN = {"kind": "column", "column": "event_type"}


from ledger import worker as ledger_worker  # noqa: E402


def _declared(*, as_qualifier=False, other_source=False):
    """`event_type` bound for the wafer on the source; as the qualifier `shot` of has_wafer (its own role, no attribute of that name); and a second
    source over the same table binding the name to the `lot` column."""
    document = _document()
    document["entities"]["wafer@1"]["attributes"] = ["event_type"]
    source = document["sources"][SOURCE]
    source["bind"]["entities"] = {"wafer@1": {"attributes": {"event_type": dict(COLUMN)}}}
    if as_qualifier:
        document["vocabulary"]["has_wafer@1"]["object"]["qualifiers"]["optional"] = ["shot"]
        source["bind"]["mappings"]["seat-holds-wafer"]["bind"]["shot"] = dict(COLUMN)
    if other_source:
        other = copy.deepcopy(source)
        other["bind"]["entities"] = {"wafer@1": {"attributes": {"event_type": {"kind": "column", "column": "lot"}}}}
        document["sources"][OTHER] = other
    return document


def _walk(atoms, seed_type="wafer", keys=None):
    seed = explorer.entity_id(seed_type, keys or {"wafer": "W000"})
    return ledger_subgraph.subgraph(seed, ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=1,
                                    registration_follow={setup_bundle.REGISTER_PREDICATE})


@pytest.fixture(name="declared")
def fixture_declared(tmp_path, monkeypatch):
    """`declared(document, **types)` -> the atoms of two rows; the walk compiles that declaration, and the table's
    column types are `types` (the live singleton, as a reload leaves it)."""
    def declare(document, **types):
        setup, atoms = _atoms(tmp_path, document, [_row(i) for i in range(2)])
        monkeypatch.setattr(ledger_worker, "_compiled_setup", lambda world: setup)
        monkeypatch.setitem(crud.TABLE_CONFIG, SOURCE, {"column_types": dict(types)})
        # as the walk reads them back from the store
        return [ledger_subgraph.EvidenceAtom(
            id=str(uuid.uuid4()), subject_type=a.subject_type, subject_keys=a.subject_keys, predicate=a.predicate,
            object_kind=a.object_kind, object_payload=a.object_payload or {}, occurred_at=a.occurred_at,
            source_who=a.source_who, source_translator_ver="v", source_raw_ref=a.source_raw_ref, supersedes=None,
            source_event_id=str(a.source_event_id), source_event_state=a.source_event_state,
            occurred_at_basis=a.occurred_at_basis) for a in atoms]
    return declare


def _wafer(body):
    return next(n for n in body["nodes"] if n["id"] == explorer.entity_id("wafer", {"wafer": "W000"}))


@pytest.mark.parametrize("kind", ["image", "datetime", "number", "TEXT"])
def test_a_name_says_the_type_of_its_column_on_its_records(declared, kind):
    atoms = declared(_declared(), event_type=kind, lot="TEXT")
    node = _wafer(_walk(atoms))
    assert node["records"]["event_type"], "CANARY: the wafer's registration was walked"
    assert {r.get("column_type") for r in node["records"]["event_type"]} == {kind}
    assert {v.get("column_type") for v in node["attributes_by_world"]["event_type"]} == {kind}


def test_a_reload_reaches_the_next_walk(declared):
    """The type changed in the live table_config reaches the next walk, nothing restarted."""
    atoms = declared(_declared(), event_type="TEXT", lot="TEXT")
    assert {r.get("column_type") for r in _wafer(_walk(atoms))["records"]["event_type"]} == {"TEXT"}
    atoms = declared(_declared(), event_type="image", lot="TEXT")
    assert {r.get("column_type") for r in _wafer(_walk(atoms))["records"]["event_type"]} == {"image"}


def test_each_record_says_its_own_sources_column(declared):
    """One name, two sources: one reads it from the image column, the other from `lot` (text)."""
    atoms = declared(_declared(other_source=True), event_type="image", lot="TEXT")
    registrations = [a for a in atoms if a.predicate == setup_bundle.REGISTER_PREDICATE]
    copied = [replace(a, id=a.id + "-b", source_who=OTHER, occurred_at=a.occurred_at.replace(year=2027))
              for a in registrations]
    records = _wafer(_walk(atoms + copied))["records"]["event_type"]
    assert sorted({(r["source_who"], r.get("column_type")) for r in records}) == [
        (SOURCE, "image"), (OTHER, "TEXT")], records


def test_one_name_bound_to_two_columns_of_two_types_in_one_source_says_none(declared):
    """The source reads `event_type` from the image column in one sentence (inherited) and from `lot` (text) in
    another (the role says its own) - one name, two types: no type, so no mark. Asked of the seat too, since a seat
    that picked one of the two would mark half the time."""
    from ledger.setup import declared_value_type

    document = _declared()
    document_registered = _document(registered_wafer=True)
    document_registered["entities"] = document["entities"]
    document_registered["sources"][SOURCE]["bind"]["entities"] = document["sources"][SOURCE]["bind"]["entities"]
    document_registered["sources"][SOURCE]["bind"]["mappings"]["wafer-registered"]["bind"]["subject"]["attributes"] = {
        "event_type": {"kind": "column", "column": "lot"}}
    atoms = declared(document_registered, event_type="image", lot="TEXT")
    setup = ledger_worker._compiled_setup(None)
    bound = {sentence: mapping.bindings for sentence, mapping in setup.snapshot.source_plans[SOURCE].profile.mappings.items()}
    assert (bound["seat-holds-wafer"]["target"]["attributes"]["event_type"]["column"],
            bound["wafer-registered"]["subject"]["attributes"]["event_type"]["column"]) == ("event_type", "lot"), \
        "CANARY: the one source binds the name to two columns"
    assert declared_value_type(setup, SOURCE, "event_type") is None
    records = _wafer(_walk(atoms))["records"]["event_type"]
    assert records and {r.get("column_type") for r in records} == {None}, records


def test_an_edge_qualifier_read_from_an_image_column_says_so_on_the_edge_and_its_records(declared):
    atoms = declared(_declared(as_qualifier=True), event_type="datetime", lot="TEXT")
    body = _walk(atoms)
    (edge,) = [e for e in body["edges"] if "shot" in (e.get("qualifiers") or {})]
    assert edge.get("column_types") == {"shot": "datetime"}
    assert edge["records"] and {json.dumps(r.get("column_types")) for r in edge["records"]} == {
        json.dumps({"shot": "datetime"})}
