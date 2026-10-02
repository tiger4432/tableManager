# -*- coding: utf-8 -*-
"""총괄 0c9b6e3c0 — 시각은 사건 엣지에만 · read 칸마다 제품 기본값 하나 (소유자 10-02).

A mapping that binds `occurred_at` is an EVENT EDGE; one that binds none is not, and its atom keeps
the molecule's stored time with the not-an-event basis (the references mechanism). A source that
writes no `read.occurred_at` reads its event edges' column, or with none the row's stored time.
Every read cell a source leaves out is filled by `setup_bundle.source_defaults` BEFORE the bundle is
normalized and hashed, so leaving a cell out and writing the same value are one bundle.
"""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.backfill import _v2_frame                                   # noqa: E402
from ledger.implementations import role_mapper_registry, trusted_implementations  # noqa: E402
from ledger.runtime_v2 import execute_scoped_batch, last_cursor, preview_cursor_batch  # noqa: E402
from ledger.schema import NOT_AN_EVENT_BASIS                            # noqa: E402
from ledger.setup_bundle import (                                       # noqa: E402
    DEFAULT_TIME_ORIGIN, declared_unique_keys, load_physical_catalog, require_ready_bundle,
    validate_bundle, validate_bundle_errors)
from ledger.setup_registry import compile_setup_snapshot                # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample")
CATALOG = load_physical_catalog(os.path.join(SAMPLE, "table_config.json.sample"))
ZONE = "Asia/Seoul"


def _document():
    with open(os.path.join(SAMPLE, "ledger_config.json.sample"), encoding="utf-8") as fh:
        return json.load(fh)


def _snapshot(document):
    bundle = require_ready_bundle(validate_bundle(document, catalog=CATALOG))
    return compile_setup_snapshot(bundle, trusted_implementations(), catalog=CATALOG)


def _rows():
    return [{"row_id": "R%d" % i, "run_uid": "U%d" % i, "method": "aoi", "base_wafer_id": "W1",
             "base_x": float(i), "base_y": 0.0, "stack_gate": None, "recipe_id": None, "eqp_id": None,
             "observed_at": "2026-09-30 10:00:00", "work_id": None} for i in (1, 2)]


def _written(document, source="die_inspection"):
    class _Store:
        def __init__(self):
            self.written = []

        def write_batch(self, source, version, atoms, cursor, molecules, *args, **kwargs):
            self.written.extend(atoms)
            return {"attempted": len(atoms), "inserted": len(atoms), "deduped": 0, "withdrawn": 0}

    snapshot = _snapshot(document)
    frame = _v2_frame(_rows())
    store = _Store()
    execute_scoped_batch(snapshot, source, frame, ("row_id", tuple(frame["row_id"])),
                         role_mapper_registry(), store, known_registrations=())
    return store.written


def _semantics(document, source="die_inspection"):
    snapshot = _snapshot(document)
    frame = _v2_frame(_rows())
    preview = preview_cursor_batch(snapshot, source, frame, last_cursor(snapshot.source_plans[source], frame),
                                   role_mapper_registry(), known_registrations=())
    return sorted(json.dumps({k: v for k, v in atom.items() if k != "source_translator_ver"},
                             sort_keys=True, default=str) for atom in preview.candidate_semantics)


def _die_inspection(document):
    return document["sources"]["die_inspection"]


def _with_a_not_an_event_mapping(document):
    """die_inspection says a second sentence of each row - the die sits in the wafer - binding no time."""
    _die_inspection(document)["bind"]["mappings"]["die-in-wafer"] = {
        "predicate": "in_container@1",
        "bind": {"subject": copy.deepcopy(_die_inspection(document)["bind"]["mappings"]
                                          ["die-inspected"]["bind"]["target"]),
                 "target": {"kind": "entity", "entity_type": "wafer@1",
                            "keys": {"wafer": {"kind": "column", "column": "base_wafer_id"}}}}}


# ------------------------------------------------------------------ read defaults

def test_a_source_that_leaves_its_defaulted_cells_out_is_the_bundle_that_writes_them():
    """The shipped sample, every active source, with each cell removed that equals what the
    product would answer - unit by group_by, identity/order_by by the catalog's shortest key,
    map.unit by read.group_by. Same bundle, same snapshot hash."""
    full = _document()
    slim = copy.deepcopy(full)
    removed = 0
    for source_id, source in slim["sources"].items():
        if source.get("status", "active") != "active":
            continue
        read, mapper = source["read"], source["map"]
        group_by = read.get("group_by") or []
        if read.get("unit") == ("group" if group_by else "row"):
            del read["unit"]
            removed += 1
        keys = declared_unique_keys(CATALOG[source["relation"]])
        shortest = list(min(keys, key=len)) if keys else None
        for cell in ("identity", "order_by"):
            if shortest is not None and read.get(cell) == shortest:
                del read[cell]
                removed += 1
        if mapper.get("unit") == ({"kind": "group_by", "columns": group_by} if group_by
                                  else {"kind": "row"}):
            del mapper["unit"]
            removed += 1
    assert removed >= 10, "canary: the sample leaves cells out to compare - %d" % removed
    assert validate_bundle(slim, catalog=CATALOG).to_mapping() == (
        validate_bundle(full, catalog=CATALOG).to_mapping())
    assert _snapshot(slim).snapshot_sha256 == _snapshot(full).snapshot_sha256


def test_a_cell_left_out_with_no_answer_is_still_refused_by_name():
    """identity has a default only where the catalog declares a key - no key, no guess."""
    document = _document()
    source = _die_inspection(document)
    del source["read"]["identity"]
    catalog = copy.deepcopy(CATALOG)
    for field in ("business_key", "composite_key", "indexes"):
        catalog[source["relation"]].pop(field, None)
    issues = validate_bundle_errors(document, catalog=catalog)
    assert any(issue.path == "bundle.sources.die_inspection.read.identity" for issue in issues), [
        (issue.code, issue.path) for issue in issues]


# ------------------------------------------------------------------ the time is the event edges'

def test_a_source_with_no_time_reads_its_event_edges_column_and_writes_the_same_atoms():
    before = _semantics(_document())
    document = _document()
    source = _die_inspection(document)
    del source["read"]["occurred_at"]
    source["bind"]["mappings"]["die-inspected"]["bind"]["occurred_at"]["timezone"] = ZONE
    filled = validate_bundle(document, catalog=CATALOG).to_mapping()
    assert filled["sources"]["die_inspection"]["read"]["occurred_at"] == {
        "column": "observed_at", "timezone": ZONE}
    assert before and _semantics(document) == before, "same atoms, event ids and times"


def test_a_source_with_no_event_edge_reads_the_rows_stored_time():
    document = _document()
    source = _die_inspection(document)
    del source["read"]["occurred_at"]
    del source["bind"]["mappings"]["die-inspected"]["bind"]["occurred_at"]
    filled = validate_bundle(document, catalog=CATALOG).to_mapping()
    assert filled["sources"]["die_inspection"]["read"]["occurred_at"] == DEFAULT_TIME_ORIGIN


@pytest.mark.parametrize("second", [{"kind": "column", "column": "base_x", "timezone": ZONE},
                                    {"kind": "column", "column": "observed_at"}])
def test_event_edges_that_do_not_name_one_time_are_refused_by_name(second):
    """Two columns, or one with no timezone: the time is not guessed."""
    document = _document()
    _with_a_not_an_event_mapping(document)
    source = _die_inspection(document)
    del source["read"]["occurred_at"]
    source["bind"]["mappings"]["die-inspected"]["bind"]["occurred_at"]["timezone"] = ZONE
    source["bind"]["mappings"]["die-in-wafer"]["bind"]["occurred_at"] = second
    issues = validate_bundle_errors(document, catalog=CATALOG)
    assert [(issue.code, issue.path) for issue in issues if issue.code == "missing_time"] == [
        ("missing_time", "bundle.sources.die_inspection.read.occurred_at")]


# ------------------------------------------------------------------ a mapping with no event time

def test_a_mapping_that_binds_no_event_time_writes_atoms_that_are_not_events():
    document = _document()
    _with_a_not_an_event_mapping(document)
    written = _written(document)
    basis = sorted((atom.predicate, atom.occurred_at_basis) for atom in written)
    assert basis == [("in_container", NOT_AN_EVENT_BASIS)] * 2 + [("inspected", None)] * 2
    # one molecule, one stored time, one event id - the references mechanism
    for event in (atom for atom in written if atom.predicate == "inspected"):
        partner = [atom for atom in written if atom.predicate == "in_container"
                   and atom.source_raw_ref == event.source_raw_ref]
        assert [(atom.occurred_at, atom.source_event_id) for atom in partner] == [
            (event.occurred_at, event.source_event_id)]


def test_the_event_edges_atoms_do_not_move_when_a_not_an_event_mapping_joins():
    before = [atom for atom in _semantics(_document())]
    document = _document()
    _with_a_not_an_event_mapping(document)
    after = _semantics(document)
    assert before and set(before) <= set(after)


def test_the_same_rows_translated_twice_are_the_same_atoms():
    document = _document()
    _with_a_not_an_event_mapping(document)
    assert _semantics(document) == _semantics(document)


# ------------------------------------------------------------------ the migration (--report / --apply --source)

def test_moving_a_source_time_onto_its_event_edges_keeps_its_atoms_and_runs_once():
    from scripts import migrate_ledger_slim_sources as slim

    before = _semantics(_document())
    document = _document()
    old = copy.deepcopy(_die_inspection(document)["read"]["occurred_at"])
    assert slim.time_of(_die_inspection(document))["verdict"] == "movable - atoms unchanged"
    changes = slim.move_time(document, "die_inspection")
    assert "die_inspection.read.occurred_at removed" in changes
    filled = validate_bundle(document, catalog=CATALOG).to_mapping()
    assert filled["sources"]["die_inspection"]["read"]["occurred_at"] == old
    assert _semantics(document) == before
    assert slim.move_time(document, "die_inspection") == [], "a moved source has nothing left to move"


def test_a_source_whose_edges_name_another_time_moves_only_when_chosen():
    from scripts import migrate_ledger_slim_sources as slim

    document = _document()
    assert slim.time_of(document["sources"]["dt_job"])["verdict"] == "movable - atoms change"
    with pytest.raises(slim.MigrationRefusal):
        slim.move_time(document, "dt_job")
    assert "occurred_at" in document["sources"]["dt_job"]["read"], "refused means untouched"
    slim.move_time(document, "dt_job", change_atoms=True)
    assert "occurred_at" not in document["sources"]["dt_job"]["read"]


def test_retired_binding_cells_go_only_when_asked():
    from scripts import migrate_ledger_slim_sources as slim

    document = _document()
    lines = slim.report(copy.deepcopy(document), CATALOG)
    assert any(line.startswith("retired binding cells:") for line in lines), "canary: the sample has some"
    assert slim.drop_retired(document) and "approval_status" not in json.dumps(document)


# ------------------------------------------------------------------ the form (lead 5c3e49954)

def test_a_source_with_no_read_opens_its_form_with_no_read_cell_owed():
    """The RELEASE_LOG example: die_inspection writes no `read`, its event edge binds the time and
    its zone. The authoring plan used to refuse to build (the zone row was derived with no ground),
    so the whole form failed; no read cell is owed now."""
    from ledger.config_authoring import authoring_plan

    document = _document()
    source = _die_inspection(document)
    del source["read"]
    source["bind"]["mappings"]["die-inspected"]["bind"]["occurred_at"]["timezone"] = ZONE
    plan = authoring_plan(document, CATALOG, selection_prefix="bundle.sources.die_inspection")
    rows = {f["path"]: f for f in plan["fields"]}
    zone = rows["bundle.sources.die_inspection.read.occurred_at.timezone"]
    assert (zone["state"], zone["disposition"], zone["ground"]["rule"], zone["ground"]["text"], zone["value"]) == (
        "derived", "default_overridable", "read_default", "Default: " + ZONE, ZONE)
    read = [f for p, f in rows.items() if p.startswith("bundle.sources.die_inspection.read.")]
    assert read and not [f["path"] for f in read if f.get("remaining")], [f["path"] for f in read]


def test_an_unbound_event_time_says_not_an_event_and_no_other_unbound_role_does():
    """Lead 04cecc30f 2: the mapping's time role left blank is a not-an-event edge, and the form
    says so through `is_event_time_role`; another unbound role in the same branch stays ungrounded."""
    from ledger.config_authoring import authoring_plan

    document = _document()
    _with_a_not_an_event_mapping(document)
    del _die_inspection(document)["bind"]["mappings"]["die-in-wafer"]["bind"]["target"]
    plan = authoring_plan(document, CATALOG, selection_prefix="bundle.sources.die_inspection")
    rows = {f["path"]: f for f in plan["fields"]}
    at = "bundle.sources.die_inspection.bind.mappings.die-in-wafer.bind."
    time, target = rows[at + "occurred_at"], rows[at + "target"]
    assert (time["state"], time["ground"]["rule"], time["ground"]["text"]) == (
        "unanswered", "not_an_event", "Not an event")
    assert (target["state"], target["ground"]) == ("missing", None)


def test_exclude_when_is_one_row_whose_candidates_are_clauses_the_validator_takes():
    """Lead 04cecc30f 3: one row over the relation's columns; a candidate is the whole clause,
    so writing one as it is validates and the screen owns no shape."""
    from ledger.config_authoring import authoring_plan, relation_columns

    document = _document()
    source = _die_inspection(document)
    source["read"].pop("exclude_when", None)
    path = "bundle.sources.die_inspection.read.exclude_when"
    row = {f["path"]: f for f in authoring_plan(
        document, CATALOG, selection_prefix="bundle.sources.die_inspection")["fields"]}[path]
    columns = relation_columns(CATALOG, source["relation"])
    assert columns
    assert (row["state"], row["value"], row["universe"]) == ("unanswered", None, "RELATION")
    assert row["candidates"] == [{"column": name, "blank": True} for name in columns]
    source["read"]["exclude_when"] = [row["candidates"][0]]
    assert validate_bundle_errors(document, catalog=CATALOG) == ()
    held = {f["path"]: f for f in authoring_plan(
        document, CATALOG, selection_prefix="bundle.sources.die_inspection")["fields"]}[path]
    assert (held["state"], held["value"]) == ("answered", [row["candidates"][0]])


def test_a_mapper_unit_left_out_is_the_loaders_default_not_a_red_square():
    """The loader fills `map.unit` a source leaves out (`source_defaults`); the form drew the row
    missing, so a slim source opened with one remaining square nobody had to fill."""
    from ledger.config_authoring import authoring_plan

    document = _document()
    del _die_inspection(document)["map"]["unit"]
    path = "bundle.sources.die_inspection.map.unit.kind"
    row = {f["path"]: f for f in authoring_plan(
        document, CATALOG, selection_prefix="bundle.sources.die_inspection")["fields"]}[path]
    assert (row["state"], row["disposition"], row["ground"]["rule"], row["value"]) == (
        "derived", "default_overridable", "read_default", "row")
    _die_inspection(document)["map"]["unit"] = {}
    row = {f["path"]: f for f in authoring_plan(
        document, CATALOG, selection_prefix="bundle.sources.die_inspection")["fields"]}[path]
    assert row["state"] == "missing"            # a unit written without its kind is still owed
