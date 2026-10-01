# -*- coding: utf-8 -*-
"""Walk control ㄱ = 가 (소유자 10-01 「가로해」, 총괄 739edd59c): `inverse_of` on a predicate,
and no step back down the same predicate or its declared inverse - ONE function,
`_goes_back_down`, asked by the walk's expansion and by the ranking's reach.

The box shape (walk control ①): `in_container` die -> wafer and `inspected` wafer -> die say
one link twice, so a die seed came down the wafer to every die by both.
"""
import json
import os
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import validation  # noqa: E402
from ledger import explorer, setup_bundle  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

QUALIFIERS = {"required": [], "optional": []}
IN_CONTAINER = {"status": "active", "subjects": ["die@1"],
                "object": {"kind": "entity_ref", "types": ["wafer@1"], "qualifiers": QUALIFIERS}}
INSPECTED = {"status": "active", "subjects": ["wafer@1"],
             "object": {"kind": "entity_ref", "types": ["die@1"], "qualifiers": QUALIFIERS}}
NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
SEED = explorer.entity_id("die", {"d": "D0"})
WAFER = explorer.entity_id("wafer", {"w": "W"})
DIES = 5


def _issues(section, predicate):
    problems = validation.Problems()
    setup_bundle._validate_vocabulary(section, problems)
    where = f"bundle.vocabulary.{predicate}.inverse_of"
    return [issue.to_mapping() for issue in problems.finish()
            if issue.to_mapping()["path"] == where]


# ---------------------------------------------------------------- the declaration cell

def test_one_side_declares_the_pair():
    assert _issues({"in_container@1": IN_CONTAINER,
                    "inspected@1": dict(INSPECTED, inverse_of="in_container@1")},
                   "inspected@1") == []


def test_both_sides_naming_each_other_is_one_pair():
    section = {"in_container@1": dict(IN_CONTAINER, inverse_of="inspected@1"),
               "inspected@1": dict(INSPECTED, inverse_of="in_container@1")}
    assert _issues(section, "inspected@1") == [] == _issues(section, "in_container@1")


def test_an_undeclared_inverse_is_refused_by_name():
    [issue] = _issues({"inspected@1": dict(INSPECTED, inverse_of="in_contaner@1")},
                      "inspected@1")
    assert issue["code"] == "unknown_id" and "in_contaner@1" in issue["message"]


def test_ends_that_do_not_flip_are_refused():
    bonded = dict(IN_CONTAINER, object=dict(IN_CONTAINER["object"], types=["die@1"]))
    [issue] = _issues({"bonded_from@1": bonded,
                       "inspected@1": dict(INSPECTED, inverse_of="bonded_from@1")},
                      "inspected@1")
    assert issue["code"] == "invalid_predicate" and "the other way" in issue["message"]


def test_a_predicate_has_one_inverse():
    section = {"in_container@1": IN_CONTAINER,
               "inspected@1": dict(INSPECTED, inverse_of="in_container@1"),
               "measured_on@1": dict(INSPECTED, inverse_of="in_container@1")}
    [issue] = _issues(section, "inspected@1")
    assert issue["code"] == "invalid_predicate" and "one inverse" in issue["message"]


def test_the_inverse_moves_no_source_fingerprint():
    """Walk-only: compiled nowhere, so no source re-reads and no atom moves."""
    from ledger.setup import load_setup
    from ledger.setup_registry import source_cursor_fingerprint

    here = os.path.dirname(os.path.abspath(__file__))
    sample = os.path.join(here, "..", "config", "sample")
    catalog = setup_bundle.load_physical_catalog(os.path.join(sample, "table_config.json.sample"))
    with open(os.path.join(sample, "ledger_config.json.sample"), encoding="utf-8") as fh:
        document = json.load(fh)

    def fingerprints(doc):
        root = tempfile.mkdtemp(prefix="inverse_")
        try:
            with open(os.path.join(root, "ledger_config.json"), "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            setup = load_setup(root, catalog=catalog)
            return {source: source_cursor_fingerprint(setup.snapshot, source)
                    for source, plan in setup.snapshot.source_plans.items()
                    if plan.planned and plan.status == "active"}
        finally:
            shutil.rmtree(root, ignore_errors=True)

    before = fingerprints(document)
    document["vocabulary"]["inspected@1"]["inverse_of"] = "in_container@1"
    assert "die_inspection" in before and fingerprints(document) == before


# ---------------------------------------------------------------- the walk and the reach

def _atom(number, subject_type, subject_keys, predicate, far_type, far_keys):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type, subject_keys=subject_keys,
        predicate=predicate, object_kind="entity_ref",
        object_payload={"type": far_type, "keys": far_keys}, occurred_at=NOW,
        source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10_000 + number)),
        source_event_state="source_molecule")


ATOMS = ([_atom(k + 1, "die", {"d": f"D{k}"}, "in_container", "wafer", {"w": "W"})
          for k in range(DIES)]
         + [_atom(100 + k, "wafer", {"w": "W"}, "inspected", "die", {"d": f"D{k}"})
            for k in range(DIES)]
         # the wafer's other facts
         + [_atom(200, "wafer", {"w": "W"}, "processed_with", "recipe", {"r": "R"}),
            _atom(201, "lot", {"l": "L"}, "has_wafer", "wafer", {"w": "W"})])


@pytest.fixture(params=[False, True], ids=["no pair", "pair"])
def declared(request, tmp_path):
    inspected = dict(INSPECTED, inverse_of="in_container@1") if request.param else INSPECTED
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps({"vocabulary": {"in_container@1": IN_CONTAINER,
                                               "inspected@1": inspected}}), encoding="utf-8")
    ledger_subgraph.reset_declaration_cache()
    yield request.param, str(path)
    ledger_subgraph.reset_declaration_cache()


def _walk(path):
    return ledger_subgraph.subgraph(SEED, ledger_subgraph.InMemoryEvidenceLookup(ATOMS),
                                    hops=2, declaration_path=path)


def test_a_declared_inverse_stops_the_siblings_and_nothing_else(declared):
    paired, path = declared
    body = _walk(path)
    types = sorted(n["type"] for n in body["nodes"])
    if paired:
        assert types == ["die", "lot", "recipe", "wafer"], types
    else:
        assert types.count("die") == DIES, "without the pair the wafer is entered two ways"


def test_the_reach_asks_the_same_function(declared):
    """Over the WHOLE graph - every atom an edge - the ranking reaches the dies the walk draws."""
    paired, path = declared
    nodes, edges = {}, []
    for a in ATOMS:
        near = explorer.entity_id(a.subject_type, a.subject_keys)
        far = explorer.entity_id(a.object_payload["type"], a.object_payload["keys"])
        nodes[near] = {"id": near, "type": a.subject_type}
        nodes[far] = {"id": far, "type": a.object_payload["type"]}
        edges.append({"source": near, "target": far, "predicate": a.predicate})
    token = ledger_subgraph._WALK_DECLARATION.set(path)
    try:
        reach, _, _ = ledger_subgraph._reach(nodes, edges, {SEED: 1})
    finally:
        ledger_subgraph._WALK_DECLARATION.reset(token)
    reached = {n for n in reach if nodes[n]["type"] == "die" and n != SEED}
    drawn = {n["id"] for n in _walk(path)["nodes"] if n["type"] == "die" and n["id"] != SEED}
    assert reached == drawn and (not reached) is paired


def test_a_step_back_to_another_type_is_walked_and_to_the_same_type_is_not(tmp_path):
    """소유자 「2로」 (총괄 f3fb29a44): `die -> seat <- wafer` reaches something else and is
    walked; `die -> seat <- die'` is a sibling and is not."""
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps({"vocabulary": {}}), encoding="utf-8")
    atoms = [_atom(1, "die", {"d": "D0"}, "slot_map", "seat", {"s": "S"}),
             _atom(2, "wafer", {"w": "W"}, "slot_map", "seat", {"s": "S"}),
             _atom(3, "die", {"d": "D1"}, "slot_map", "seat", {"s": "S"})]
    ledger_subgraph.reset_declaration_cache()
    try:
        body = ledger_subgraph.subgraph(SEED, ledger_subgraph.InMemoryEvidenceLookup(atoms),
                                        hops=2, declaration_path=str(path))
    finally:
        ledger_subgraph.reset_declaration_cache()
    assert sorted(n["type"] for n in body["nodes"]) == ["die", "seat", "wafer"]
