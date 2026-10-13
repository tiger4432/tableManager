"""A source that attaches a table's rows under nodes (총괄 10-13 행 붙이기, 14a486e8c): the walk reads its sentence - from a
parent node, the declared predicate to a row node, whose values are the row's columns - as it reads the ledger's, in the
same read, and nothing is written. Folding, counting and expanding are the hub's own."""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger import explorer  # noqa: E402
from ledger.setup_registry import AttachPlan  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
ATTACHED = ("test:walk-attached-rows",)
DEFECTS = AttachPlan(predicate="has_defect", subject_type="die", subject_keys=(("die", "die", False),),
                     target_type="defect_row", target_keys=(("defect_id", "defect_id", False),),
                     columns=("size", "kind"))
#: D0 three rows, D1 one, D2 none - and a row with no key, which names no node
ROWS = [{"row_id": 1, "die": "D0", "defect_id": "F1", "size": 1.5, "kind": "void"},
        {"row_id": 2, "die": "D0", "defect_id": "F2", "size": 2.0, "kind": "crack"},
        {"row_id": 3, "die": "D0", "defect_id": "F3", "size": None, "kind": " void "},
        {"row_id": 4, "die": "D1", "defect_id": "F4", "size": 7, "kind": "void"},
        {"row_id": 5, "die": "D1", "defect_id": " ", "size": 1, "kind": "void"}]


@pytest.fixture(autouse=True)
def declared():
    ledger_subgraph._declaration_facts[ATTACHED] = (
        {"defect_row": ["defect_id"]}, {}, {}, {}, {}, {}, frozenset({"has_defect"}),
        {"defect_row": {"keys": ["defect_id"]}})
    yield
    ledger_subgraph._declaration_facts.pop(ATTACHED, None)


def node(kind, name):
    return explorer.entity_id(kind, {kind: name})


def row_node(name):
    return explorer.entity_id("defect_row", {"defect_id": name})


WAFER_DIES = [ledger_subgraph.EvidenceAtom(
    id=str(uuid.UUID(int=number + 1)), subject_type="wafer", subject_keys={"wafer": "W"}, predicate="has_die",
    object_kind="entity_ref", object_payload={"type": "die", "keys": {"die": die}}, occurred_at=NOW,
    source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number, supersedes=None,
    source_event_id=str(uuid.UUID(int=10_000 + number)), source_event_state="source_molecule")
    for number, die in enumerate(("D0", "D1", "D2"))]


def _walk(rows=ROWS, **kwargs):
    lookup = ledger_subgraph.InMemoryEvidenceLookup(WAFER_DIES, attached=[("defects", DEFECTS, rows)])
    kwargs.setdefault("hops", 2)
    return ledger_subgraph.subgraph(node("wafer", "W"), lookup, declaration_paths=ATTACHED, backbone_hops=0,
                                    registration_follow={"register"}, **kwargs)


def _hubs(body):
    return {item["hub"]["near"]: item for item in body["nodes"] if item.get("hub", {}).get("predicate") == "has_defect"}


def test_each_die_s_rows_are_one_hub_counted_as_the_table_holds_them():
    """The declared step folds (hub: true), ×1 too: D0's three rows, D1's one - its row with a blank key names no
    node - and D2 none."""
    body = _walk()
    hubs = _hubs(body)
    assert {near: hub["count"] for near, hub in hubs.items()} == {node("die", "D0"): 3, node("die", "D1"): 1}
    assert {hub["type"] for hub in hubs.values()} == {"defect_row"}


def test_a_hub_s_table_rows_carry_the_row_s_columns_as_its_node_s_values():
    """The row node's values are its row's columns - said as the translator says a node's bound attributes (register),
    a number as its text, a blank left out, text trimmed - and the table draws them though the row type declares no
    attribute: the table declaration names them (lead 10-13, a row comes whole)."""
    body = _walk()
    table = body["tables"][_hubs(body)[node("die", "D0")]["id"]]
    rows = {row[table["columns"].index("id")]: dict(zip(table["columns"], row)) for row in table["rows"]}
    assert {key: (row["size"], row["kind"]) for key, row in rows.items()} == {
        row_node("F1"): ("1.5", "void"), row_node("F2"): ("2", "crack"),
        row_node("F3"): (None, "void")}


def test_an_opened_hub_s_rows_stand_as_nodes_with_their_values():
    """expand is the hub's own door: the step does not fold, its rows come as nodes."""
    folded = _walk()
    opened = _walk(expand=[_hubs(folded)[node("die", "D0")]["id"]])
    rows = {item["id"]: item for item in opened["nodes"] if item["type"] == "defect_row"}
    assert set(rows) >= {row_node("F%d" % i) for i in (1, 2, 3)}
    assert rows[row_node("F2")]["attributes"] == {"size": "2", "kind": "crack"}


def test_a_walk_from_a_row_node_reads_back_to_its_parent():
    """The sentence reads both ways - a row node walks back to its die (incoming), as any edge: the declared step folds
    that way too, so the die is its hub's row."""
    lookup = ledger_subgraph.InMemoryEvidenceLookup(WAFER_DIES, attached=[("defects", DEFECTS, ROWS)])
    body = ledger_subgraph.subgraph(row_node("F4"), lookup, declaration_paths=ATTACHED, hops=1,
                                    backbone_hops=0, registration_follow={"register"})
    (hub,) = [item for item in body["nodes"] if item.get("hub")]
    assert (hub["hub"]["direction"], hub["type"], hub["count"]) == ("incoming", "die", 1)
    table = body["tables"][hub["id"]]
    assert [row[table["columns"].index("id")] for row in table["rows"]] == [node("die", "D1")]


def test_an_attached_atom_is_never_of_version_seven_so_a_continued_walk_keeps_it():
    """A continued walk reads as of its first page by the atom id's time (uuid7) - an attached row has none: the rows are
    the table's now, so «as of» never leaves one out."""
    atoms = ledger_subgraph.attach_atoms("defects", DEFECTS, ROWS)
    assert len(atoms) == 8, "canary: four rows with keys, two atoms each"
    assert all(uuid.UUID(atom.id).version != 7 for atom in atoms)
    lookup = ledger_subgraph.InMemoryEvidenceLookup(atoms)
    lookup.recorded_before = ledger_subgraph._as_of_bound(NOW)
    assert len(lookup.claims_for_entities([("die", {"die": "D0"})], "outgoing", 100)[0]) == 3


def test_without_attached_rows_the_answer_is_the_bytes_it_was():
    """A walk whose lookup attaches nothing answers byte for byte as the same walk always did, and says nothing of rows."""
    plain = ledger_subgraph.subgraph(node("wafer", "W"), ledger_subgraph.InMemoryEvidenceLookup(WAFER_DIES),
                                     declaration_paths=ATTACHED, hops=2, backbone_hops=0,
                                     registration_follow={"register"})
    empty = _walk(rows=[])
    drop = lambda body: {k: v for k, v in body.items() if k != "generated_at"}  # noqa: E731
    assert drop(plain) == drop(empty)
    assert "rows_withheld" not in plain["truncated"]


def test_a_walk_that_reads_no_rows_says_why_and_only_then():
    """since/until or another world: the lookup carries no attach sentence and the reason rides the answer."""
    lookup = ledger_subgraph.InMemoryEvidenceLookup(WAFER_DIES, rows_withheld="rows are attached as their tables are now")
    body = ledger_subgraph.subgraph(node("wafer", "W"), lookup, declaration_paths=ATTACHED, hops=2, backbone_hops=0)
    assert body["truncated"]["rows_withheld"] == "rows are attached as their tables are now"
    assert "rows_withheld" not in _walk()["truncated"]


@pytest.mark.parametrize("asked,reason", [({"since": NOW}, "since or until"), ({"until": NOW}, "since or until"),
                                          ({"world": "other"}, "other worlds"), ({}, None)])
def test_the_route_attaches_the_operating_world_s_rows_only_to_a_walk_of_now(asked, reason, monkeypatch):
    """The route reads the attach sentences of the operating world's declaration (compiled once per change) - and none
    for a walk with since or until or of other worlds, saying why."""
    from types import SimpleNamespace

    from chain import ingestion_worker
    from ledger import trace_router

    plan = SimpleNamespace(relation="dt_defect", attach=DEFECTS, status="active")
    setup = SimpleNamespace(snapshot=SimpleNamespace(source_plans={"defects": plan, "other": SimpleNamespace(
        relation="t", attach=None, status="active")}))
    monkeypatch.setattr(ingestion_worker, "_compiled_setup", lambda world: setup)
    names = (SimpleNamespace(name=asked.get("world", "default")),)
    attached, withheld = trace_router._attached_rows(names, asked.get("since"), asked.get("until"))
    if reason is None:
        assert attached == (("defects", "dt_defect", DEFECTS),) and withheld is None
    else:
        assert attached == () and reason in withheld
