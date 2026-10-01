# -*- coding: utf-8 -*-
"""걷기가 «지금 참인 것»을 그린다 - `cardinality: one` 의 지금 값은 가장 늦은 occurred_at
(총괄 22ebdd153, 판정 256 뒤집음).

⚰️ S-141's split by `supersedes` markers retired with the markers' one writer. Its symptom - a
replaced fact drawn beside its replacement - is the control here. The PG half (both SQL arms,
until, the same value again, ties, a cut fetch) is `test_ledger_trace_pg`; this is the in-memory
double, held to the same answers on the same fixture.
"""
from datetime import datetime, timedelta, timezone
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer                                          # noqa: E402
from ledger_api import ledger_subgraph                               # noqa: E402

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
T1, T2, T3 = (T0 + timedelta(hours=hours) for hours in (1, 2, 3))
#: t1 W1 · t2 W2 · t3 W3, and W9 at t1.5 arriving LAST.
HOLDS = [(1, T1, "W1"), (2, T2, "W2"), (3, T3, "W3"), (4, T0 + timedelta(minutes=90), "W9")]
LOT = explorer.entity_id("Lot", {"lot": "L-D"})


def _atoms(rows=HOLDS, qualifiers=None):
    return [ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="Lot", subject_keys={"lot": "L-D"},
        predicate="has_wafer", object_kind="entity_ref",
        object_payload={"type": "Wafer", "keys": {"wafer": wafer},
                        "qualifiers": (qualifiers or {}).get(number, {})},
        occurred_at=when, source_who="fixture", source_translator_ver="v1",
        source_raw_ref=f"row:{number}", supersedes=None,
        source_event_id=str(uuid.UUID(int=1000 + number)), source_event_state="source_record")
        for number, when, wafer in rows]


def _drawn(atoms=None, seed=LOT, direction="outgoing", **lookup):
    body = ledger_subgraph.subgraph(
        seed, ledger_subgraph.InMemoryEvidenceLookup(
            _atoms() if atoms is None else atoms, one=["has_wafer"], **lookup),
        hops=1, direction=direction, cardinalities={"has_wafer": "one"})
    label = {node["id"]: node["label"] for node in body["nodes"]}
    edges = sorted((label[e["target"]], bool(e.get("not_current")))
                   for e in body["edges"] if e["predicate"] == "has_wafer")
    return edges, body


def test_the_latest_fact_is_drawn_and_the_late_old_one_is_not():
    assert _drawn()[0] == [("W3", False)]


def test_as_of_a_time_and_with_history_the_double_answers_as_the_sql():
    assert _drawn(until=T2 + timedelta(minutes=30))[0] == [("W2", False)]
    assert _drawn(current_only=False)[0] == [
        ("W1", True), ("W2", True), ("W3", False), ("W9", True)]


def test_walked_from_an_old_object_the_replaced_fact_is_not_drawn():
    seed = explorer.entity_id("Wafer", {"wafer": "W1"})
    assert _drawn(seed=seed, direction="incoming")[0] == []


def test_a_tie_draws_both_and_the_subject_counts_it():
    edges, body = _drawn(_atoms(HOLDS + [(5, T3, "W4")]))
    lot, = [node for node in body["nodes"] if node["id"] == LOT]

    assert edges == [("W3", False), ("W4", False)]
    assert lot["current_conflicts"] == 1


def test_the_same_object_with_another_qualifier_at_that_instant_is_no_conflict():
    edges, body = _drawn(_atoms(HOLDS + [(6, T3, "W3")], qualifiers={6: {"slot": "2"}}))
    lot, = [node for node in body["nodes"] if node["id"] == LOT]

    assert edges == [("W3", False)]
    assert lot["current_conflicts"] == 0
