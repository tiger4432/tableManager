# -*- coding: utf-8 -*-
"""총괄 c24ba7d82 (소유자 10-02 「첫걸음은 열어」): a static seed's first step goes to dynamic nodes.
A static node met on the way is held as before. One seat, `ledger_subgraph._held_to_names`, asked by
the fetch split, `_step` (graph walk) and `_reach` (table rows, ranking).
"""
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

NOW = datetime(2026, 8, 15, 3, 0, tzinfo=timezone.utc)
EVENT = str(uuid.UUID("3101e12e-c814-58f4-87cf-c8e31084e923"))
STATIC = {"recipe", "defect_kind"}


def _atom(number, subject_type, subject, predicate, target_type, target):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type,
        subject_keys={subject_type: subject}, predicate=predicate, object_kind="entity_ref",
        object_payload={"type": target_type, "keys": {target_type: target}, "qualifiers": {}},
        occurred_at=NOW, source_who="fixture", source_translator_ver="v1",
        source_raw_ref=f"row:{number}", supersedes=None, source_event_id=EVENT,
        source_event_state="source_record")


ATOMS = (
    [_atom(300 + i, "wafer", w, "processed_with", "recipe", "R") for i, w in enumerate(("W1", "W2", "W3"))]
    + [_atom(310 + i, "defect", d, "of_kind", "defect_kind", "K") for i, d in enumerate(("D1", "D2", "D3"))]
    # W9 names R by ANOTHER predicate, so going on from R to W1..W3 is not a step back down
    # (`_goes_back_down`) - only the static rule can hold it
    + [_atom(320, "wafer", "W9", "qualified_with", "recipe", "R")]
)


def _id(kind, key):
    return explorer.entity_id(kind, {kind: key})


def _walk(seed, lookup=None, **kwargs):
    arguments = {"hops": 3, "direction": "both", "static_types": STATIC, "static_follow": set()}
    arguments.update(kwargs)
    return ledger_subgraph.subgraph(seed, lookup or ledger_subgraph.InMemoryEvidenceLookup(ATOMS),
                                    **arguments)


def _labels(body, kind):
    return sorted(node["label"] for node in body["nodes"] if node["type"] == kind)


class RecordingLookup:
    def __init__(self, atoms):
        self.inner = ledger_subgraph.InMemoryEvidenceLookup(atoms)
        self.calls = []

    def claims_for_entities(self, entities, direction, limit, *, follow=None):
        self.calls.append(({item[0] for item in entities}, None if follow is None else tuple(follow)))
        return self.inner.claims_for_entities(entities, direction, limit, follow=follow)


def test_a_static_seed_reaches_the_dynamic_nodes_that_name_it():
    body = _walk(_id("recipe", "R"), follow=["processed_with"])
    assert _labels(body, "wafer") == ["W1", "W2", "W3"]


def test_the_static_seed_is_fetched_with_the_callers_follow():
    """Narrowed to static-to-static predicates (none here) the seed would never be fetched."""
    lookup = RecordingLookup(ATOMS)
    _walk(_id("recipe", "R"), lookup, follow=["processed_with"])
    seed_calls = [follow for types, follow in lookup.calls if types == {"recipe"}]
    assert seed_calls and seed_calls[0] == ("processed_with",)


def test_a_static_node_met_on_the_way_is_held_as_before():
    body = _walk(_id("wafer", "W9"), follow=["qualified_with", "processed_with"])
    assert _labels(body, "recipe") == ["R"]
    assert _labels(body, "wafer") == ["W9"], "the walk left a name it met and came back into the world"


def test_a_static_seeds_fan_out_draws_its_first_n_and_bundles_the_rest():
    """총괄 11e5ea207: over the limit, the first `fanout_limit` are drawn - it drew none before."""
    body = _walk(_id("defect_kind", "K"), follow=["of_kind"], fanout_limit=2)
    assert len(_labels(body, "defect")) == 2
    assert [(b["far_type"], b["count"], b["drawn"]) for b in body["bundles"]] == [("defect", 3, 2)]


def test_the_table_rows_open_the_seed_the_same_way():
    """The rows are `_reach` over the walked graph - the same seat as the graph walk."""
    body = _walk(_id("recipe", "R"), follow=["processed_with"], rows=True)
    lines = [line.split("\t") for line in body["rows"].splitlines() if not line.startswith("#")]
    table = [dict(zip(lines[0], line)) for line in lines[1:]]
    reached = {row["id"] for row in table
               if row["type"] == "wafer" and row["seed"] == _id("recipe", "R") and row["via"] == "processed_with"}
    graph = {node["id"] for node in body["nodes"] if node["type"] == "wafer"}
    assert graph == reached == {_id("wafer", w) for w in ("W1", "W2", "W3")}


def test_reach_opens_only_the_seed_it_starts_from():
    """Two seeds: the static one steps out, the other meets it on the way and is held there."""
    nodes = {n: {"id": n, "type": t} for n, t in
             (("R", "recipe"), ("W9", "wafer"), ("W2", "wafer"), ("W3", "wafer"))}
    edges = ([{"source": w, "target": "R", "predicate": "processed_with"} for w in ("W2", "W3")]
             + [{"source": "W9", "target": "R", "predicate": "qualified_with"}])
    reach, _, _ = ledger_subgraph._reach(nodes, edges, {"R": 1, "W9": -1}, static_types={"recipe"})
    assert reach["W2"] == [1, 0] and reach["W3"] == [1, 0], "W9 went on through the name it met"
    assert reach["R"] == [0, 1], "a seed does not count itself; W9 reaches the name"
