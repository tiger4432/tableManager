# -*- coding: utf-8 -*-
"""총괄 e5e0a87e2 · 10-11 ㄱ — the walk answer carries every value record beside the current value (소유자 「노드 속성을
잘 쓰는 게 중요」 · 「프로세스 이벤트 하나에 계측 포인트별로 측정 원자가 주렁주렁」).

  an edge     its relation's atoms were folded into one edge (the latest) - each is now a record of it: time,
              qualifiers (a point too), world, source, claim; an atom reached from both ends is one record
  a node      each name's registrations were read down to one value - each is now a record: value, time, world,
              source, claim, newest first; a `many` name and a `one` name alike
  the cap     `RECORDS_PER_FACT` records, the rest counted in `records_more`
  unchanged   the current value - an edge's own fields, a node's `attributes` - is what it was
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer                                       # noqa: E402
from ledger_api import ledger_subgraph                            # noqa: E402

T0 = datetime(2026, 10, 1, 1, 0, tzinfo=timezone.utc)
WAFER = {"wid": "TRD-W-001"}
POINT = {"q": "TRD-P"}
SEED = explorer.entity_id("wafer", WAFER)


def _atom(number, predicate, payload, hour, kind=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="wafer", subject_keys=dict(WAFER),
        predicate=predicate, object_kind=kind, object_payload=payload, occurred_at=T0 + timedelta(hours=hour),
        source_who="trd_src", source_translator_ver="v1", source_raw_ref=f"row:{number}", supersedes=None,
        source_event_id=str(uuid.UUID(int=900 + number)), source_event_state="source_molecule")


def _measures(number, hour, point):
    return _atom(number, "measures", {"type": "quantity", "keys": dict(POINT),
                                      "qualifiers": {"point": point, "value": float(number)}}, hour, "entity_ref")


def _registration(number, hour, **values):
    return _atom(number, "register", {"qualifiers": values}, hour)


ATOMS = ([_measures(n, n, "P%d" % n) for n in (1, 2, 3, 4)]
         + [_registration(10 + n, n, product=p, tag=p.lower()) for n, p in ((1, "A"), (2, "B"), (3, "C"))])


def _walk():
    return ledger_subgraph.subgraph(SEED, ledger_subgraph.InMemoryEvidenceLookup(ATOMS), hops=1,
                                    registration_follow={"register"})


def _edge(body):
    (edge,) = [e for e in body["edges"] if e["predicate"] == "measures"]
    return edge


def _node(body):
    return next(n for n in body["nodes"] if n["id"] == SEED)


def test_an_edge_carries_every_atom_of_its_relation_as_a_record():
    """The application's 18766 repro: TRD-W-001 -measures-> TRD-P, four atoms, one edge, one point drawn."""
    edge = _edge(_walk())
    assert edge["claim_id"] == ATOMS[3].id and edge["qualifiers"]["point"] == "P4", "CANARY: the current edge is the latest"
    assert [(r["occurred_at"], r["qualifiers"]["point"], r["claim_id"]) for r in edge["records"]] == [
        (ledger_subgraph._instant(a.occurred_at), a.object_payload["qualifiers"]["point"], a.id)
        for a in reversed(ATOMS[:4])]
    assert {r["world"] for r in edge["records"]} == {None} and {r["source_who"] for r in edge["records"]} == {"trd_src"}
    assert edge["records_more"] == 0


def test_an_atom_reached_from_both_ends_is_one_record():
    """Between two static types a step may go back the way it came (`_goes_back_down` lets it), so the walk reads
    the cause's atom again from the effect - one atom, one record."""
    cause = ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=77)), subject_type="cause", subject_keys={"c": "C1"}, predicate="leads_to",
        object_kind="entity_ref", object_payload={"type": "effect", "keys": {"e": "E1"}}, occurred_at=T0,
        source_who="mech", source_translator_ver="v1", source_raw_ref="row:77", supersedes=None,
        source_event_id=str(uuid.UUID(int=977)), source_event_state="source_molecule")
    body = ledger_subgraph.subgraph(explorer.entity_id("cause", {"c": "C1"}),
                                    ledger_subgraph.InMemoryEvidenceLookup([cause]), hops=3,
                                    static_types={"cause", "effect"}, static_follow={"leads_to"})
    (edge,) = body["edges"]
    assert body["walk"]["claims_scanned"] >= 2, "CANARY: the atom was read from both ends"
    assert ([r["claim_id"] for r in edge["records"]], edge["records_more"]) == ([cause.id], 0)


@pytest.mark.parametrize("plural", [False, True])
def test_a_nodes_name_carries_every_registration_as_a_record(plural, monkeypatch):
    monkeypatch.setattr(ledger_subgraph, "_declared_plural_attributes",
                        lambda node_type: {"product"} if plural else set())
    node = _node(_walk())
    assert node["attributes"]["product"] == (["A", "B", "C"] if plural else "C"), "CANARY: today's value"
    for name, said in (("product", ["C", "B", "A"]), ("tag", ["c", "b", "a"])):
        assert [r["value"] for r in node["records"][name]] == said, name
        assert [r["claim_id"] for r in node["records"][name]] == [ATOMS[6].id, ATOMS[5].id, ATOMS[4].id]
    assert node["records_more"] == {"product": 0, "tag": 0}


def test_past_the_cap_the_rest_are_counted(monkeypatch):
    monkeypatch.setattr(ledger_subgraph, "RECORDS_PER_FACT", 2)
    body = _walk()
    edge, node = _edge(body), _node(body)
    assert (len(edge["records"]), edge["records_more"]) == (2, 2)
    assert ([r["value"] for r in node["records"]["product"]], node["records_more"]["product"]) == (["C", "B"], 1)


class _OldestFirst(ledger_subgraph.InMemoryEvidenceLookup):
    """The same atoms handed oldest first - the order a fetch hands them in is not the answer's."""
    handed = ()

    def claims_for_entities(self, *args, **kwargs):
        rows, more = super().claims_for_entities(*args, **kwargs)
        self.handed = tuple(self.handed) + tuple(atom.id for atom in reversed(rows))
        return rows[::-1], more


def test_the_newest_records_stay_whatever_order_they_were_fetched_in(monkeypatch):
    """총괄 10-11: an edge's records were kept in the order fetched and cut there, a node name's were sorted - one list
    read two ways. One rule now: the atom's time, then its claim id, newest first; past the cap the newest stay."""
    monkeypatch.setattr(ledger_subgraph, "RECORDS_PER_FACT", 2)
    tied = ATOMS + [_measures(5, 4, "P5"), _registration(14, 3, product="D", tag="d")]
    lookup = _OldestFirst(tied)
    body = ledger_subgraph.subgraph(SEED, lookup, hops=1, registration_follow={"register"})
    measured = [a.id for a in tied if a.predicate == "measures"]
    assert [i for i in lookup.handed if i in measured][:2] == measured[:2], "CANARY: handed oldest first"
    edge, node = _edge(body), _node(body)
    assert ([r["claim_id"] for r in edge["records"]], edge["records_more"]) == ([tied[-2].id, ATOMS[3].id], 3)
    assert ([r["value"] for r in node["records"]["product"]], node["records_more"]["product"]) == (["D", "C"], 2)
