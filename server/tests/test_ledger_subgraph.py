from datetime import datetime, timedelta, timezone
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.envelope import source_event_identity
import ledger_explorer
import ledger_subgraph
import ledger_trace_router


NOW = datetime(2026, 8, 15, 3, 0, tzinfo=timezone.utc)
EVENT = str(uuid.UUID("3101e12e-c814-58f4-87cf-c8e31084e923"))


def atom(number, subject, predicate, *, target=None, value=None,
         event=EVENT, event_state="source_molecule"):
    payload = {}
    kind = None
    if target:
        kind = "entity_ref"
        payload = {"type": "Lot", "keys": {"lot": target}, "qualifiers": {}}
    elif value is not None:
        kind = "value"
        payload = value
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="Lot",
        subject_keys={"lot": subject}, predicate=predicate, object_kind=kind,
        object_payload=payload, occurred_at=NOW, source_who="fixture",
        source_translator_ver="v1", source_raw_ref=f"row:{number}",
        supersedes=None, source_event_id=event,
        source_event_state=event_state)


def fixture():
    return [
        atom(1, "A", "derived_from", target="B"),
        atom(2, "A", "measured", value={"metric": "cd", "value": 48.8, "unit": "um"}),
        atom(3, "C", "derived_from", target="A",
             event=str(uuid.UUID("4bb344d4-97a6-514d-a392-8d77b2d50775"))),
    ]


def observed_atom():
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=44)), subject_type="Wafer",
        subject_keys={"wafer": "WF-VOID"}, predicate="observed",
        object_kind="value",
        object_payload={"finding_kind": "void", "method": "sat",
                        "run_uid": "SAT:44", "position": {"x": 7, "y": 9}},
        occurred_at=NOW, source_who="sat", source_translator_ver="v1",
        source_raw_ref="void:44", supersedes=None, source_event_id=EVENT,
        source_event_state="source_record")


def test_source_event_identity_groups_one_utterance_but_not_sources_or_times():
    a = source_event_identity("source-A", NOW, molecule_ref="m-1")
    b = source_event_identity("source-A", NOW, molecule_ref="m-1")
    other_source = source_event_identity("source-B", NOW, molecule_ref="m-1")
    other_time = source_event_identity(
        "source-A", NOW + timedelta(seconds=1), molecule_ref="m-1")
    record = source_event_identity("source-A", NOW, source_raw_ref="row-7")
    assert a == b
    assert a[1] == "source_molecule"
    assert a[0] != other_source[0] != other_time[0]
    assert record[1] == "source_record"


def test_entity_event_and_claim_are_all_valid_subgraph_seeds():
    lookup = ledger_subgraph.InMemoryEvidenceLookup(fixture())
    entity_id = ledger_explorer.entity_id("Lot", {"lot": "A"})
    entity_graph = ledger_subgraph.subgraph(entity_id, lookup, hops=3)
    kinds = {node["node_kind"] for node in entity_graph["nodes"]}
    assert {"entity", "event", "claim", "value"} <= kinds
    assert {node["label"] for node in entity_graph["nodes"] if node["node_kind"] == "entity"} >= {"A", "B", "C"}
    assert sum(node["node_kind"] == "event" for node in entity_graph["nodes"]) == 2
    assert sum(node["node_kind"] == "claim" for node in entity_graph["nodes"]) == 3

    event_id = next(node["id"] for node in entity_graph["nodes"]
                    if node["node_kind"] == "event" and node["keys"]["source_event_id"] == EVENT)
    event_graph = ledger_subgraph.subgraph(event_id, lookup, hops=2)
    assert sum(node["node_kind"] == "claim" for node in event_graph["nodes"]) == 2

    claim_id = next(node["id"] for node in entity_graph["nodes"]
                    if node["node_kind"] == "claim" and node["predicate"] == "measured")
    claim_graph = ledger_subgraph.subgraph(claim_id, lookup, hops=1)
    assert {node["node_kind"] for node in claim_graph["nodes"]} == {
        "claim", "entity", "event", "value"}

    for node in entity_graph["nodes"]:
        assert ledger_subgraph.decode_node_id(node["id"])["kind"] == node["node_kind"]


def test_direction_and_value_projection_are_explicit_parameters():
    lookup = ledger_subgraph.InMemoryEvidenceLookup(fixture())
    entity_id = ledger_explorer.entity_id("Lot", {"lot": "A"})
    outgoing = ledger_subgraph.subgraph(
        entity_id, lookup, hops=3, direction="outgoing", include_values=False)
    labels = {node["label"] for node in outgoing["nodes"]}
    assert "C" not in labels
    assert not any(node["node_kind"] == "value" for node in outgoing["nodes"])
    assert outgoing["walk"]["direction"] == "outgoing"
    assert outgoing["walk"]["resolver_applied"] is False


def test_raw_observed_claim_points_to_a_directional_map_point_not_a_value():
    observed = observed_atom()
    lookup = ledger_subgraph.InMemoryEvidenceLookup([observed])
    seed = ledger_explorer.entity_id("Wafer", {"wafer": "WF-VOID"})
    graph = ledger_subgraph.subgraph(
        seed, lookup, hops=2, include_values=False, observation_mode="claims")
    point = next(node for node in graph["nodes"]
                 if node["node_kind"] == "point")
    assert point["type"] == "Finding Point"
    assert point["finding_kind"] == "void"
    assert point["keys"]["position"] == {"x": 7, "y": 9}
    assert point["expansion"] == "explicit_seed_to_wafer_only"
    assert not any(node["node_kind"] == "value" for node in graph["nodes"])
    assert any(edge["predicate"] == "observed" and
               edge["target"] == point["id"] for edge in graph["edges"])
    reseeded = ledger_subgraph.subgraph(point["id"], lookup, hops=12)
    assert {node["node_kind"] for node in reseeded["nodes"]} == {
        "point", "entity", "collection"}
    assert any(edge["predicate"] == "on_subject" for edge in reseeded["edges"])
    assert any(edge["predicate"] == "has_findings" for edge in reseeded["edges"])
    assert not any(node["node_kind"] in {"claim", "event", "value"}
                   for node in reseeded["nodes"])


def test_entity_folds_defects_into_collection_and_collection_reseeds_details():
    observed = observed_atom()
    lookup = ledger_subgraph.InMemoryEvidenceLookup([observed])
    seed = ledger_explorer.entity_id("Wafer", {"wafer": "WF-VOID"})
    graph = ledger_subgraph.subgraph(seed, lookup, hops=12, include_values=False)
    collections = [node for node in graph["nodes"]
                   if node["node_kind"] == "collection"]
    assert len(collections) == 1
    collection = collections[0]
    assert collection["type"] == "Finding Collection"
    assert collection["occurrence_count"] == 1
    assert collection["finding_kind"] == "void"
    assert collection["aggregates"]["count"] == 1
    assert collection["spatial"]["bbox"] == {
        "min_x": 7.0, "max_x": 7.0, "min_y": 9.0, "max_y": 9.0}
    assert not any(node["node_kind"] in {"claim", "point"}
                   for node in graph["nodes"])
    assert graph["walk"]["observation_mode"] == "summary"
    assert any(edge["predicate"] == "has_findings" and edge["witnesses"] == 1
               for edge in graph["edges"])

    unfolded = ledger_subgraph.subgraph(
        collection["id"], lookup, hops=2, include_values=False)
    assert not any(node["node_kind"] == "claim" for node in unfolded["nodes"])
    assert any(node["node_kind"] == "point" for node in unfolded["nodes"])
    assert any(edge["predicate"] == "contains" for edge in unfolded["edges"])


def test_legacy_atom_is_one_honest_event_and_can_be_reseeded():
    legacy = atom(9, "OLD", "register", event=None, event_state=None)
    lookup = ledger_subgraph.InMemoryEvidenceLookup([legacy])
    entity_id = ledger_explorer.entity_id("Lot", {"lot": "OLD"})
    body = ledger_subgraph.subgraph(entity_id, lookup, hops=2)
    event = next(node for node in body["nodes"] if node["node_kind"] == "event")
    assert event["source_event_state"] == "legacy_atom"
    reseeded = ledger_subgraph.subgraph(event["id"], lookup, hops=1)
    assert any(node["node_kind"] == "claim" for node in reseeded["nodes"])


def test_caps_are_reported_instead_of_looking_complete():
    many = [atom(index + 100, "FAN", "measured", value={"value": index},
                 event=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"event-{index}")))
            for index in range(30)]
    seed = ledger_explorer.entity_id("Lot", {"lot": "FAN"})
    body = ledger_subgraph.subgraph(
        seed, ledger_subgraph.InMemoryEvidenceLookup(many),
        hops=4, node_limit=10, edge_limit=20)
    assert len(body["nodes"]) == 10
    assert body["truncated"]["nodes"] is True
    assert body["truncated"]["reason"]


def test_tabular_projection_is_stable_and_dynamic_fields_stay_typed():
    seed = ledger_explorer.entity_id("Lot", {"lot": "A"})
    graph = ledger_subgraph.subgraph(
        seed, ledger_subgraph.InMemoryEvidenceLookup(fixture()), hops=3)
    export = ledger_subgraph.tabular_projection(graph)
    assert tuple(export["tables"]["nodes"]["columns"]) == ledger_subgraph.NODE_TABLE_COLUMNS
    assert tuple(export["tables"]["edges"]["columns"]) == ledger_subgraph.EDGE_TABLE_COLUMNS
    properties = export["tables"]["properties"]["rows"]
    value = next(row for row in properties
                 if row["property_scope"] == "object_payload"
                 and row["property_path"] == "value")
    assert value["value_type"] == "number"
    assert value["value_number"] == 48.8
    assert value["value_text"] is None
    # Stable IDs are the join keys Spotfire/Excel use across the three sheets.
    node_ids = {row["node_id"] for row in export["tables"]["nodes"]["rows"]}
    assert all(row["source_id"] in node_ids and row["target_id"] in node_ids
               for row in export["tables"]["edges"]["rows"])
    assert export["provenance"]["source"] == "ledger_events"


def test_property_table_cap_is_named():
    seed = ledger_explorer.entity_id("Lot", {"lot": "A"})
    graph = ledger_subgraph.subgraph(
        seed, ledger_subgraph.InMemoryEvidenceLookup(fixture()), hops=3)
    export = ledger_subgraph.tabular_projection(graph, property_limit=100)
    assert len(export["tables"]["properties"]["rows"]) <= 100
    # This small fixture may fit; force a graph with enough dynamic paths to hit it.
    graph["nodes"][0]["object_payload"] = {f"metric_{i}": i for i in range(160)}
    export = ledger_subgraph.tabular_projection(graph, property_limit=100)
    assert export["truncated"]["properties"] is True
    assert "properties" in export["truncated"]["reason"]
    assert len(export["tables"]["nodes"]["rows"]) == len(graph["nodes"])
    node_ids = {row["node_id"] for row in export["tables"]["nodes"]["rows"]}
    assert all(row["source_id"] in node_ids and row["target_id"] in node_ids
               for row in export["tables"]["edges"]["rows"])


def test_node_ids_reject_noncanonical_or_forged_shapes():
    event_id = ledger_subgraph.event_node_id(EVENT, NOW, "source_molecule")
    assert ledger_subgraph.decode_node_id(event_id)["event_id"] == EVENT
    try:
        ledger_subgraph.decode_node_id(event_id + "=")
    except ValueError as exc:
        assert "canonical" in str(exc) or "JSON" in str(exc)
    else:
        raise AssertionError("noncanonical event id was accepted")


def test_graph_and_table_routes_are_both_declared_and_csv_is_safe():
    paths = {route.path for route in ledger_trace_router.router.routes}
    assert "/api/ledger/subgraph" in paths
    assert "/api/ledger/subgraph/table" in paths
    assert ledger_trace_router._csv_safe("=HYPERLINK('x')") == "'=HYPERLINK('x')"
    assert ledger_trace_router._csv_safe("  @SUM(A1)") == "'  @SUM(A1)"
    assert ledger_trace_router._csv_safe(-1.25) == -1.25


def test_sql_lookup_round_trip_uses_persisted_event_identity(pg_engine):
    from ledger.envelope import Atom
    from ledger.store import LedgerStore

    store = LedgerStore(pg_engine)
    store.ensure_schema()
    atoms = [
        Atom(subject_type="Lot", subject_keys={"lot": "SQL-A"},
             predicate="derived_from", object_kind="entity_ref",
             object_payload={"type": "Lot", "keys": {"lot": "SQL-B"}},
             occurred_at=NOW, source_who="sql-fixture",
             source_translator_ver="v1", source_raw_ref="row:1",
             molecule_ref="event:one"),
        Atom(subject_type="Lot", subject_keys={"lot": "SQL-A"},
             predicate="measured", object_kind="value",
             object_payload={"metric": "cd", "value": 48.8, "unit": "um"},
             occurred_at=NOW, source_who="sql-fixture",
             source_translator_ver="v1", source_raw_ref="row:2",
             molecule_ref="event:one"),
    ]
    connection = pg_engine.raw_connection()
    try:
        store.ensure_partitions(connection, [NOW])
        attempted, inserted = store.insert_atoms(connection, atoms)
        connection.commit()
        assert (attempted, inserted) == (2, 2)
        assert atoms[0].source_event_id == atoms[1].source_event_id
        seed = ledger_explorer.entity_id("Lot", {"lot": "SQL-A"})
        body = ledger_subgraph.subgraph(
            seed, ledger_subgraph.SqlEvidenceLookup(connection), hops=3)
    finally:
        connection.close()
    assert sum(node["node_kind"] == "claim" for node in body["nodes"]) == 2
    events = [node for node in body["nodes"] if node["node_kind"] == "event"]
    assert len(events) == 1
    assert events[0]["source_event_state"] == "source_molecule"
