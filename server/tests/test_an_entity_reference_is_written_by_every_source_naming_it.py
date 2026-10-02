# -*- coding: utf-8 -*-
"""총괄 29047aedc (소유자 「다이 웨이퍼 잇기 지어」): `entities.<type>.references` is written by the
translator as an atom for every source that names the entity - one seat, `roleframe.compile_role_rows`
(`_reference_rows`) - and its time is not an event time (`schema.REFERENCE_BASIS`).

The shipped sample with one reference added to die@1: a die whose mat_type is Wafer sits in the wafer
its mat_id names.
"""
import copy
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import roleframe                                            # noqa: E402
from ledger.backfill import _v2_frame                                   # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.runtime_v2 import execute_scoped_batch, last_cursor, preview_cursor_batch  # noqa: E402
from ledger.schema import REFERENCE_BASIS                                 # noqa: E402
from ledger.setup_bundle import load_physical_catalog, require_ready_bundle, validate_bundle  # noqa: E402
from ledger.setup_registry import compile_setup_snapshot, source_cursor_fingerprint  # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
REFERENCE = {"edge": "in_container@1", "to": {"entity": "wafer@1", "keys": {"wafer": "mat_id"}},
             "from": {"when": {"mat_type": "Wafer"}}}


def _snapshot(change=None):
    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    if change:
        change(document)
    bundle = require_ready_bundle(validate_bundle(document, catalog=catalog))
    return compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog)


def _with_reference(document):
    document["entities"]["die@1"]["references"] = copy.deepcopy(REFERENCE)


@pytest.fixture(scope="module", name="snapshot")
def fixture_snapshot():
    return _snapshot(_with_reference)


def _inspection_rows():
    return [{"row_id": "R%d" % i, "run_uid": "U%d" % i, "method": "aoi", "base_wafer_id": "W1",
             "base_x": float(i), "base_y": 0.0, "stack_gate": None, "recipe_id": None, "eqp_id": None,
             "observed_at": "2026-09-30 10:00:00", "work_id": None} for i in (1, 2)]


def _transfer_rows():
    return [{"row_id": "T1", "dt_cell_key": "K1", "core_wafer_id": "W7", "c_wx": 1.0, "c_wy": 2.0,
             "dt_job_id": "J1", "b_wx": 3.0, "b_wy": 4.0, "dt_job": "J1", "dt_x": 3.0, "dt_y": 4.0,
             "event_time": "2026-09-30 11:00:00", "product": None}]


def _preview(snapshot, source, rows):
    frame = _v2_frame(rows)
    return preview_cursor_batch(snapshot, source, frame, last_cursor(snapshot.source_plans[source], frame),
                                role_mapper_registry(), known_registrations=())


def _edges(preview):
    """(die keys, wafer) of every reference atom, keys in the product's own spelling."""
    return sorted((json.dumps(a["subject_keys"], sort_keys=True), a["object_payload"]["keys"]["wafer"])
                  for a in preview.candidate_semantics if a["predicate"] == "in_container")


def _dies(preview, mat_type):
    """The die keys the source's own atoms carried, either side."""
    found = set()
    for a in preview.candidate_semantics:
        for kind, keys in ((a["subject_type"], a["subject_keys"]),
                           ((a["object_payload"] or {}).get("type"), (a["object_payload"] or {}).get("keys"))):
            if kind == "die" and keys.get("mat_type") == mat_type and a["predicate"] != "in_container":
                found.add(json.dumps(keys, sort_keys=True))
    return found


def test_a_source_that_names_the_entity_writes_its_reference(snapshot):
    """die_inspection names each die as its object - one edge per die, to the wafer its mat_id names."""
    preview = _preview(snapshot, "die_inspection", _inspection_rows())
    dies = _dies(preview, "Wafer")
    assert len(dies) == 2
    assert _edges(preview) == sorted((die, "W1") for die in dies)


def test_only_where_when_holds(snapshot):
    """transfer_event names a Wafer die (subject) and a DT die (object): only the first sits in a wafer."""
    preview = _preview(snapshot, "transfer_event", _transfer_rows())
    assert len(_dies(preview, "DT")) == 1, "canary: the DT die is named"
    assert _edges(preview) == [(die, "W7") for die in _dies(preview, "Wafer")]


def test_no_reference_declared_writes_nothing():
    assert _edges(_preview(_snapshot(), "die_inspection", _inspection_rows())) == []


def test_the_reference_atom_is_not_event_timed_and_the_event_atoms_keep_their_time(snapshot):
    class _Store:
        def __init__(self):
            self.written = []

        def write_batch(self, source, version, atoms, cursor, molecules, *args, **kwargs):
            self.written.extend(atoms)
            return {"attempted": len(atoms), "inserted": len(atoms), "deduped": 0, "withdrawn": 0}

    frame = _v2_frame(_inspection_rows())
    store = _Store()
    execute_scoped_batch(snapshot, "die_inspection", frame, ("row_id", tuple(frame["row_id"])),
                         role_mapper_registry(), store, known_registrations=())
    basis = sorted((a.predicate, a.occurred_at_basis) for a in store.written)
    assert basis == [("in_container", REFERENCE_BASIS)] * 2 + [("inspected", None)] * 2
    reference = [a for a in store.written if a.predicate == "in_container"][0]
    event = [a for a in store.written if a.predicate == "inspected" and a.source_raw_ref == reference.source_raw_ref][0]
    assert (reference.occurred_at, reference.source_event_id) == (event.occurred_at, event.source_event_id)


def test_a_fact_the_molecule_states_is_not_said_twice():
    def change(document):
        _with_reference(document)
        mappings = document["sources"]["die_inspection"]["bind"]["mappings"]
        inspected = mappings["die-inspected"]["bind"]
        mappings["die-in-wafer"] = {"predicate": "in_container@1", "bind": {
            "occurred_at": inspected["occurred_at"], "subject": inspected["target"],
            "target": inspected["subject"]}}
    preview = _preview(_snapshot(change), "die_inspection", _inspection_rows())
    stated = [a for a in preview.candidate_semantics if a["predicate"] == "in_container"]
    assert len(stated) == 2, "the mapped edge and the reference made the same fact twice"


def test_one_entity_named_twice_is_one_atom_backed_by_every_row_that_named_it(snapshot):
    """The seat itself, with a molecule whose two rows name the same die."""
    die = {"mat_id": "W1", "mat_type": "Wafer", "x": 1.0, "y": 0.0}
    base = {"source_event_id": "e", "source_event_state": "source_molecule", "subject_type": "wafer",
            "subject_keys": {"wafer": "W1"}, "predicate": "inspected", "object_kind": "entity_ref",
            "object_payload": {"type": "die", "keys": die}, "occurred_at": "t", "source_who": "s",
            "source_translator_ver": "v", "source_raw_ref": "r", "supersedes": None, "molecule_ref": "m",
            "derivation": "die-inspected"}
    named = [("die@1", die, base, ("row-1",)), ("die@1", dict(die), dict(base), ("row-2",))]
    made = roleframe._reference_rows(SimpleNamespace(snapshot=snapshot), named, [base], "event-ref", "p#")
    assert len(made) == 1
    assert json.loads(made[0]["source_raw_ref"])["rows"] == ["row-1", "row-2"]
    assert made[0]["derivation"].startswith("entity-reference:die@1")


def test_the_reference_moves_only_the_cursors_of_sources_that_name_the_entity(snapshot):
    before = _snapshot()
    moved = {source for source, plan in snapshot.source_plans.items() if plan.planned and plan.status == "active"
             if source_cursor_fingerprint(snapshot, source) != source_cursor_fingerprint(before, source)}
    assert {"die_inspection", "transfer_event"} <= moved
    assert "dt_job" not in moved and "lot_event" not in moved


def test_the_declaration_says_a_source_naming_the_entity_writes_the_edge():
    from ledger.setup_bundle import emitted_predicates

    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    _with_reference(document)
    entities = document["entities"]
    assert "in_container@1" in emitted_predicates(document["sources"]["die_inspection"], entities)
    assert "in_container@1" in emitted_predicates(document["sources"]["transfer_event"], entities)
    assert "in_container@1" not in emitted_predicates(document["sources"]["dt_job"], entities)


@pytest.mark.parametrize("change, path, code", [
    ({"edge": "sits_in@1"}, "references[0].edge", "unknown_predicate"),
    ({"to": {"entity": "lot@1", "keys": {"lot": "mat_id"}}}, "references[0].to.entity", "invalid_entity_ref"),
    ({"to": {"entity": "wafer@1", "keys": {"wafer": "lot_id"}}}, "references[0].to.keys.wafer.key", "invalid_entity_ref"),
    ({"from": {"when": {"kind": "Wafer"}}}, "references[0].from.when.kind", "invalid_entity_ref"),
], ids=["predicate_not_declared", "object_type_not_taken", "key_map_names_no_key", "when_names_no_key"])
def test_a_wrong_reference_is_refused_by_name(change, path, code):
    from ledger.setup_bundle import validate_bundle_errors

    catalog = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)
    document["entities"]["die@1"]["references"] = dict(REFERENCE, **change)
    errors = validate_bundle_errors(document, catalog=catalog)
    assert ("bundle.entities.die@1." + path, code) in {(e.path, e.code) for e in errors}, errors
