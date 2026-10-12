# -*- coding: utf-8 -*-
"""총괄 41194be5d (소유자 「메인 노드로 걷고 걸은 것들 중에서 보조 노드로 경로가 있는지 판정만 - 정적 동적 제한 없이
최단경로」): `aux` judges each walked node - found (hops to the nearest aux) · none · unknown - by the same walk from the
aux nodes with the guards that drop a step off; the answer's nodes and edges stay as walked. Seed: wafer W, its dies
D0 · D1 · D2; each cell an aux node of its own:
  A1  reaches D0 only through a static name (quantity Q, a hub of 50 more dies)   found
  A2  reaches D1 only by a predicate the walk does not follow   found
  A3  reaches D2 directly and through two steps                 found, the shorter
  A4  joined to nothing the walk holds                          none
  A5  a fan-out past the atom cap (the answer's node cap does not bind it)       unknown, never none
  A6  reaches D0 only by a step back down (die -> W -> die)     found"""
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
QUALIFIERS = {"required": [], "optional": []}


def _predicate(subject, far):
    return {"status": "active", "subjects": [subject + "@1"],
            "object": {"kind": "entity_ref", "types": [far + "@1"], "qualifiers": QUALIFIERS}}


VOCABULARY = {"in_container@1": _predicate("die", "wafer"), "measures@1": _predicate("die", "quantity"),
              "observed@1": _predicate("die", "defect"), "bonded_from@1": _predicate("die", "die"),
              "linked@1": _predicate("die", "die")}
COUNTER = iter(range(1, 10 ** 6))
DEFAULT_EDGES = ledger_subgraph.DEFAULT_EDGE_LIMIT


def _atom(subject_type, subject_keys, predicate, far_type, far_keys):
    number = next(COUNTER)
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type, subject_keys=subject_keys,
        predicate=predicate, object_kind="entity_ref", object_payload={"type": far_type, "keys": far_keys},
        occurred_at=NOW, source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10 ** 6 + number)), source_event_state="source_molecule")


def die(name):
    return {"d": name}


ATOMS = ([_atom("die", die("D%d" % k), "in_container", "wafer", {"w": "W"}) for k in range(3)]
         + [_atom("die", die("D0"), "measures", "quantity", {"q": "Q"}),
            _atom("die", die("A1"), "measures", "quantity", {"q": "Q"})]               # A1 -> Q -> D0
         + [_atom("die", die("H%d" % k), "measures", "quantity", {"q": "Q"}) for k in range(50)]
         + [
            _atom("die", die("D1"), "observed", "defect", {"f": "F"}),
            _atom("die", die("A2"), "observed", "defect", {"f": "F"}),                 # A2 -> F -> D1, not followed
            _atom("die", die("A3"), "bonded_from", "die", die("D2")),                  # A3 -> D2
            _atom("die", die("A3"), "linked", "die", die("X")),
            _atom("die", die("X"), "linked", "die", die("D2")),                        # A3 -> X -> D2
            _atom("die", die("A4"), "linked", "die", die("Z"))]                        # nothing the walk holds
         + [_atom("die", die("A5"), "linked", "die", die("N%d" % k)) for k in range(300)]
         + [_atom("die", die("A6"), "in_container", "wafer", {"w": "W"})])           # A6 -> W -> D0: back down
SEED = explorer.entity_id("wafer", {"w": "W"})
AUX = {name: explorer.entity_id("die", die(name)) for name in ("A1", "A2", "A3", "A4", "A5", "A6")}
D = {name: explorer.entity_id("die", die(name)) for name in ("D0", "D1", "D2")}


@pytest.fixture
def declared(tmp_path):
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps({"vocabulary": VOCABULARY}), encoding="utf-8")
    ledger_subgraph.reset_declaration_cache()
    yield (str(path),)
    ledger_subgraph.reset_declaration_cache()


def walk(declared, aux=None, edge_limit=DEFAULT_EDGES):
    return ledger_subgraph.subgraph(
        SEED, ledger_subgraph.InMemoryEvidenceLookup(ATOMS), declaration_paths=declared, hops=2,
        edge_limit=edge_limit, follow=["in_container", "measures", "bonded_from", "linked"],
        static_types={"quantity"}, aux=aux)


def judged(body):
    return {node["id"]: node["aux"] for node in body["nodes"]}


def test_a_node_reached_only_through_a_static_name_is_found(declared):
    assert judged(walk(declared, [AUX["A1"]]))[D["D0"]] == {"state": "found", "hops": 2, "via": AUX["A1"]}


def test_a_node_reached_only_by_a_predicate_the_walk_does_not_follow_is_found(declared):
    assert judged(walk(declared, [AUX["A2"]]))[D["D1"]] == {"state": "found", "hops": 2, "via": AUX["A2"]}


def test_two_ways_answer_the_shorter(declared):
    assert judged(walk(declared, [AUX["A3"]]))[D["D2"]] == {"state": "found", "hops": 1, "via": AUX["A3"]}


def test_a_node_joined_to_nothing_is_none(declared):
    body = walk(declared, [AUX["A4"]])
    assert body["aux"]["complete"] and set(s["state"] for s in judged(body).values()) == {"none"}, body["aux"]


def test_a_walk_cut_by_its_caps_says_unknown_never_none(declared):
    body = walk(declared, [AUX["A5"]], edge_limit=20)       # atom cap 200
    assert not body["aux"]["complete"] and set(s["state"] for s in judged(body).values()) == {"unknown"}, body["aux"]


def test_a_node_reached_only_by_a_step_back_down_is_found(declared):
    assert judged(walk(declared, [AUX["A6"]]))[D["D0"]] == {"state": "found", "hops": 2, "via": AUX["A6"]}


def test_several_aux_name_the_nearest_and_the_answer_is_the_walk_without_them(declared):
    plain, body = walk(declared), walk(declared, [AUX["A3"], AUX["A1"]])
    assert ({n["id"] for n in plain["nodes"]}, len(plain["edges"])) == ({n["id"] for n in body["nodes"]},
                                                                        len(body["edges"]))
    assert "aux" not in plain and all("aux" not in n for n in plain["nodes"])
    assert judged(body)[D["D2"]] == {"state": "found", "hops": 1, "via": AUX["A3"]}
