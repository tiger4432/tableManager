from datetime import datetime, timedelta, timezone
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.envelope import source_event_identity
import ledger_explorer
from ledger_api import ledger_subgraph
import ledger_trace_router
from ledger_api import mechanism_gate


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
    # The collection now carries the declared model target too, so the expected member
    # set is pinned against a KNOWN declaration rather than against whatever
    # mechanism_models.json happens to hold on this box.
    mechanism_gate.set_graph(MECHANISM_DECLARATION)
    try:
        reseeded = ledger_subgraph.subgraph(point["id"], lookup, hops=12)
    finally:
        mechanism_gate.set_graph(None)
    assert {node["node_kind"] for node in reseeded["nodes"]} == {
        "point", "entity", "collection", "quantity"}
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
    # 🔴 `node_limit` caps the nodes the CALLER ASKED FOR, and from 2026-08-25 claims are not
    # among them: they are provenance the trails read, capped separately by `claim_limit`.
    # Asserting on len(nodes) again would re-pin the old contract, in which 837 claims could
    # crowd out the 3-to-35 entities a walk exists to find.
    budgeted = [node for node in body["nodes"] if node["node_kind"] != "claim"]
    assert len(budgeted) == 10
    assert any(node["node_kind"] == "claim" for node in body["nodes"]), (
        "claims must still be emitted -- evidence.hops is built by reading them")
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


MECHANISM_DECLARATION = {
    "bindings": {"processed_with:params_actual.pressure_MPa": ["bond_pressure"]},
    "void_formation": {
        "role": "formation", "finding_kind": "void", "target": "void",
        "nodes": ["bond_pressure", "interface_unfill", "void"],
        "edges": [{"from": "bond_pressure", "to": "interface_unfill", "dir": "-"},
                  {"from": "interface_unfill", "to": "void", "dir": "+"}],
    },
    "delam_formation": {
        "role": "formation", "finding_kind": "delam", "target": "delam",
        "nodes": ["bond_pressure", "delam"],
        "edges": [{"from": "bond_pressure", "to": "delam", "dir": "+"}],
    },
}


def process_atom():
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=77)), subject_type="Wafer",
        subject_keys={"wafer": "WF-BOND"}, predicate="processed_with",
        object_kind="value",
        object_payload={"step": "BOND", "recipe": "R-6",
                        "params_actual": {"pressure_MPa": 3.2, "clamp_force_N": 12.5}},
        occurred_at=NOW, source_who="mes", source_translator_ver="v1",
        source_raw_ref="job:77", supersedes=None, source_event_id=EVENT,
        source_event_state="source_record")


def test_declared_mechanism_becomes_quantity_nodes_and_a_quantity_reseeds():
    lookup = ledger_subgraph.InMemoryEvidenceLookup([process_atom()])
    seed = ledger_explorer.entity_id("Wafer", {"wafer": "WF-BOND"})
    mechanism_gate.set_graph(MECHANISM_DECLARATION)
    try:
        graph = ledger_subgraph.subgraph(seed, lookup, hops=8)
        quantities = {node["label"]: node for node in graph["nodes"]
                      if node["node_kind"] == "quantity"}
        bindings = [edge for edge in graph["edges"] if edge["predicate"] == "binding"]
        mechanisms = [edge for edge in graph["edges"] if edge["predicate"] == "mechanism"]
        # The bound leaf grows edges; `clamp_force_N` is declared nowhere and stays silent.
        assert {edge["qualifiers"]["binding_key"] for edge in bindings} == {
            "processed_with:params_actual.pressure_MPa"}
        value_id = ledger_subgraph.value_node_id(process_atom().id, NOW)
        assert {edge["source"] for edge in bindings} == {value_id}
        # One quantity name declared by two models is two nodes, never one shared node:
        # merging them would splice two modellers' assertions into a third one.
        assert "bond_pressure · void_formation" in quantities
        assert "bond_pressure · delam_formation" in quantities
        assert len(bindings) == 2
        by_id = {node["id"]: node for node in graph["nodes"]}
        assert all(by_id[edge["source"]]["model"] == by_id[edge["target"]]["model"]
                   for edge in mechanisms)
        unfill = quantities["interface_unfill · void_formation"]["id"]
        pressure = quantities["bond_pressure · void_formation"]["id"]
        declared = next(edge for edge in mechanisms
                        if edge["source"] == pressure and edge["target"] == unfill)
        assert declared["qualifiers"] == {"dir": "-", "model": "void_formation"}
        assert declared["basis"] == mechanism_gate.CONFIG_FILENAME
        # A synthesized id is a seed like any other public node id.
        assert ledger_subgraph.decode_node_id(pressure) == {
            "kind": "quantity", "model": "void_formation",
            "quantity": "bond_pressure", "id": pressure}
        reseeded = ledger_subgraph.subgraph(pressure, lookup, hops=3)
        assert reseeded["state"] == "ready"
        assert reseeded["seed"]["id"] == pressure
        assert {node["label"] for node in reseeded["nodes"]} == {
            "bond_pressure · void_formation", "interface_unfill · void_formation",
            "void · void_formation"}
    finally:
        mechanism_gate.set_graph(None)


def signed_fixture():
    """Two subjects that share one factor and differ in how many claims they carry.

    The degree difference is the point: it is what makes the first-hop rule observable.
    """
    return [
        atom(11, "MARK", "measured", value={"metric": "cd", "value": 1.0}),
        atom(12, "MARK", "derived_from", target="ORIGIN"),
        atom(13, "CTRL", "derived_from", target="ORIGIN"),
        atom(14, "CTRL", "measured", value={"metric": "cd", "value": 2.0}),
        atom(15, "CTRL", "measured", value={"metric": "ov", "value": 3.0}),
        # One ancestor further out, so the fixture has a candidate that is NOT a seed and
        # NOT first -- which is the case the owner's question is about.
        atom(16, "ORIGIN", "derived_from", target="ROOT"),
    ]


def test_a_single_id_still_works_and_the_three_seed_states_stay_three():
    lookup = ledger_subgraph.InMemoryEvidenceLookup(signed_fixture())
    marked = ledger_explorer.entity_id("Lot", {"lot": "MARK"})
    control = ledger_explorer.entity_id("Lot", {"lot": "CTRL"})

    plain = ledger_subgraph.subgraph(marked, lookup, hops=4)
    assert plain["seed"]["id"] == marked
    assert plain["walk"]["start"] == {"positive": 1, "negative": 0}
    assert plain["propagation"]["state"] == "not_requested"

    # No control seed is NOT 「controls came back clean」 — the axis was never examined,
    # and an unlisted subject is never promoted into the negative list to fill it.
    solo = ledger_subgraph.subgraph({"positive": [marked]}, lookup, hops=4,
                                    collect="entity")
    assert solo["propagation"]["contrast"] == "unexamined"
    assert solo["walk"]["start"] == {"positive": 1, "negative": 0}

    contrasted = ledger_subgraph.subgraph(
        {"positive": [marked], "negative": [control]}, lookup, hops=4, collect="entity")
    assert contrasted["propagation"]["contrast"] == "contrasted"
    assert {item["sign"] for item in contrasted["seeds"]} == {"+", "-"}
    assert contrasted["walk"]["start"] == {"positive": 1, "negative": 1}

    try:
        ledger_subgraph.subgraph({"positive": [marked], "negative": [marked]}, lookup)
    except ValueError as exc:
        assert "both observed and a control" in str(exc)
    else:
        raise AssertionError("one subject was accepted as observed AND as a control")


def test_collect_switches_the_application_without_changing_the_walk():
    """Acceptance B: cause candidates and a common ancestor from ONE mechanism."""
    lookup = ledger_subgraph.InMemoryEvidenceLookup(
        signed_fixture() + [process_atom()])
    seeds = {"positive": [ledger_explorer.entity_id("Lot", {"lot": "MARK"}),
                          ledger_explorer.entity_id("Wafer", {"wafer": "WF-BOND"})]}
    mechanism_gate.set_graph(MECHANISM_DECLARATION)
    try:
        entities = ledger_subgraph.subgraph(seeds, lookup, hops=8, collect="entity")
        quantities = ledger_subgraph.subgraph(seeds, lookup, hops=8, collect="quantity")
    finally:
        mechanism_gate.set_graph(None)
    # `collect` picks the population and nothing else: the walked graph is identical.
    assert ([node["id"] for node in entities["nodes"]]
            == [node["id"] for node in quantities["nodes"]])
    assert len(entities["edges"]) == len(quantities["edges"])
    assert {row["type"] for row in entities["propagation"]["ranked"]} == {"Lot", "Wafer"}
    assert {row["type"] for row in quantities["propagation"]["ranked"]} == {"Quantity"}
    # The declared ancestor both marked subjects descend from is the lineage answer.
    origin = ledger_explorer.entity_id("Lot", {"lot": "ORIGIN"})
    assert origin in entities["propagation"]["top_set"]
    # Ranks, the top set and the trails travel; the reach that produced them does not.
    # A magnitude reads like a probability and is not one — what tells a reader that a
    # candidate was never reached from a control is the SIGN on its trails.
    assert '"reach"' not in json.dumps(entities["propagation"])
    for row in entities["propagation"]["ranked"]:
        assert set(row) == {"id", "type", "label", "rank", "top", "tied",
                            "incomparable", "evidence"}
    try:
        ledger_subgraph.subgraph(seeds, lookup, collect="Physics")
    except ValueError as exc:
        assert "collect must be one of" in str(exc)
    else:
        raise AssertionError("an unknown collect answered instead of refusing")


def uneven_fixture():
    """Two marked subjects carrying a DIFFERENT number of claims, one factor each.

    The two factors sit the same distance behind claims of the same degree, so the only
    thing that could separate them is the seeds' own degree — which is exactly what the
    first hop is forbidden to divide by.
    """
    events = [str(uuid.UUID(int=900 + n)) for n in range(5)]
    return [
        atom(21, "THIN", "derived_from", target="FACTOR-THIN", event=events[0]),
        atom(22, "THIN", "measured", value={"metric": "cd", "value": 1.0},
             event=events[1]),
        atom(23, "FAT", "derived_from", target="FACTOR-FAT", event=events[2]),
        atom(24, "FAT", "measured", value={"metric": "cd", "value": 2.0},
             event=events[3]),
        atom(25, "FAT", "measured", value={"metric": "ov", "value": 3.0},
             event=events[4]),
    ]


def test_the_first_hop_is_not_divided_by_the_seeds_own_degree():
    """The rule with a stated reason, on the fixture where the two rules disagree.

    `THIN` carries two claims and `FAT` three.  Their factors are otherwise identical, so
    under the rule they are reached with the same weight and come out TIED.  Divide the
    seed's own hop by its degree and the thinner subject's factor wins on nothing but its
    subject having had fewer claims recorded — the artefact the rule exists to prevent.
    """
    lookup = ledger_subgraph.InMemoryEvidenceLookup(uneven_fixture())
    body = ledger_subgraph.subgraph({"positive": [
        ledger_explorer.entity_id("Lot", {"lot": "THIN"}),
        ledger_explorer.entity_id("Lot", {"lot": "FAT"}),
    ]}, lookup, hops=4, collect="entity")
    ranked = {row["label"]: row for row in body["propagation"]["ranked"]}
    assert ranked["FACTOR-THIN"]["rank"] == ranked["FACTOR-FAT"]["rank"]
    assert ranked["FACTOR-THIN"]["tied"] and ranked["FACTOR-FAT"]["tied"]


def test_the_top_set_is_everything_not_dominated_and_carries_its_basis():
    lookup = ledger_subgraph.InMemoryEvidenceLookup(signed_fixture())
    marked = ledger_explorer.entity_id("Lot", {"lot": "MARK"})
    control = ledger_explorer.entity_id("Lot", {"lot": "CTRL"})
    # deep enough to reach the far ancestor, so `complete` still means something
    body = ledger_subgraph.subgraph(
        {"positive": [marked], "negative": [control]}, lookup, hops=8, collect="entity")
    prop = body["propagation"]
    prop_seeds = body["seeds"]
    ranked = {row["label"]: row for row in prop["ranked"]}
    assert prop["top_set"] == [row["id"] for row in prop["ranked"] if row["top"]]
    assert prop["complete"] is True
    # Every ranked entry that is NOT top is dominated by something in the top set, and
    # nothing in the top set dominates anything else there.
    assert all(row["rank"] > 1 for row in prop["ranked"] if not row["top"])
    # 「걸은 경로도 나와?」 — on EVERY rank, not only on the winner.  A reader has to be
    # able to say 「this one was never reached from a control」 about something that is
    # not first, and that judgement needs the trail and the sign, not the position.
    # Every ranked candidate the WALK reached carries its trail.  A seed may carry none
    # and that is not a hole: the caller named its sign, so there is no path to report --
    # measured on live data, where a control in another lineage branch is reached by no
    # other seed.  Asserting `all(...)` here would be a fixture-specific premise.
    seeded = {item["id"] for item in prop_seeds}
    assert all(row["evidence"] for row in prop["ranked"] if row["id"] not in seeded)
    assert any(row["rank"] > 1 for row in prop["ranked"]), "fixture must rank below 1"
    below = next(row for row in prop["ranked"]
                 if row["rank"] > 1 and row["id"] not in seeded)
    assert below["evidence"] and below["evidence"][0]["hops"]
    # The sign is what carries the judgement, and it is on every rank's trails.
    assert {trail["sign"] for row in prop["ranked"] for trail in row["evidence"]} == {
        "+", "-"}
    assert {trail["sign"] for trail in below["evidence"]} <= {"+", "-"}
    top = ranked["ORIGIN"]
    assert top["evidence"], "the top set carries its hop-by-hop basis"
    hops = top["evidence"][0]["hops"]
    assert hops[0]["id"] in (marked, control)
    assert hops[-1]["label"] == "ORIGIN"
    assert any(hop["node_kind"] == "claim" and hop["atom"] for hop in hops)
    # 「정도가 아니라 종류가 다르다」 has to be reachable or the mark is decoration:
    # more reach from the marked subjects AND more from the controls is a trade-off, so
    # neither dominates and both stay top.
    layers = ledger_subgraph._rank_layers([
        {"id": "trade", "reach": [0.5, 0.2]},
        {"id": "clean", "reach": [0.3, 0.0]},
        {"id": "twin", "reach": [0.3, 0.0]},
        {"id": "weak", "reach": [0.1, 0.9]}])
    assert [item["id"] for item in layers[0]] == ["trade", "clean", "twin"]
    assert all(item["incomparable"] for item in layers[0])
    assert [item["tied"] for item in layers[0]] == [False, True, True]
    assert [item["id"] for item in layers[1]] == ["weak"]


def test_the_summary_query_asks_for_a_literal_jsonb_path():
    """`#>>'{position,x}'` lives inside an f-string; unescaped it is a NameError.

    Every InMemory test uses the pure-Python twin and the PostgreSQL test is skipped
    without a server, so nothing here saw the SQL text itself until now.
    """
    lookup = ledger_subgraph.SqlEvidenceLookup.__new__(
        ledger_subgraph.SqlEvidenceLookup)
    lookup.relation = "ledger_events"
    captured = {}

    def capture(sql, params):
        captured["sql"] = sql
        return []

    lookup._execute = capture
    lookup.finding_summaries_for_entities([("Wafer", {"wafer": "W1"})], "both", 5)
    assert "'{position,x}'" in captured["sql"]
    assert "'{position,y}'" in captured["sql"]


def test_a_finding_reaches_every_model_declared_for_its_kind_without_merging_them():
    """The third declared edge: `finding_kind` names the model, the model names its target.

    A void reaches the formation model's `void` AND the observation-bias model's
    `void_observed`, and they stay two nodes.  Merging them would let a factor that only
    explains why a void was SEEN wear a formation path, which is the confusion the two
    models were split apart to prevent.
    """
    lookup = ledger_subgraph.InMemoryEvidenceLookup([observed_atom()])
    seed = ledger_explorer.entity_id("Wafer", {"wafer": "WF-VOID"})
    declaration = dict(MECHANISM_DECLARATION)
    declaration["void_observation_bias"] = {
        "role": "observation_bias", "finding_kind": "void", "target": "void_observed",
        "nodes": ["post_bond_queue_h", "void_observed"],
        "edges": [{"from": "post_bond_queue_h", "to": "void_observed", "dir": "u"}],
    }
    mechanism_gate.set_graph(declaration)
    try:
        graph = ledger_subgraph.subgraph(seed, lookup, hops=6)
        answer = ledger_subgraph.subgraph(
            next(node["id"] for node in graph["nodes"]
                 if node["node_kind"] == "collection"),
            lookup, hops=8, collect="quantity")
    finally:
        mechanism_gate.set_graph(None)
    findings = [edge for edge in graph["edges"] if edge["predicate"] == "finding"]
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    assert {labels[edge["target"]] for edge in findings} == {
        "void · void_formation", "void_observed · void_observation_bias"}
    assert {edge["qualifiers"]["role"] for edge in findings} == {
        "formation", "observation_bias"}
    assert all(edge["basis"] == mechanism_gate.CONFIG_FILENAME for edge in findings)
    # The delam model declares a different kind, so it is not drawn into a void's answer.
    assert not any("delam" in labels[edge["target"]] for edge in findings)
    # Seeding the finding is what makes the mechanism graph answerable from the finding
    # side at all; before this edge the same call reached no Quantity whatsoever.
    assert answer["propagation"]["state"] == "ranked"
    assert answer["propagation"]["top_set"]


def test_the_two_open_routes_take_the_signed_seeds_and_the_frozen_ones_do_not():
    routes = {route.path: route for route in ledger_trace_router.router.routes}
    def params(path):
        return {field.alias or field.name
                for field in routes[path].dependant.query_params}
    assert {"positive", "negative", "collect"} <= params("/api/ledger/subgraph")
    assert {"positive", "negative"} <= params("/api/ledger/subgraph/table")
    # `collect` produces a ranking that the three tables do not carry, so the table route
    # does not accept an argument it would echo and never consume.
    assert "collect" not in params("/api/ledger/subgraph/table")
    # `/api/ledger/explore_entity` was retired 2026-08-23; `/subgraph` answers it.
    # `/trace` and `/explore` were DELETED 2026-08-25 with the legacy screens, so the
    # assertion becomes the stronger one the line below already uses: they are not routes
    # at all. Asserting "they do not take signed seeds" would pass vacuously on a
    # KeyError-free dict lookup only because there is nothing left to ask.
    for retired in ("/api/ledger/explore_entity", "/api/ledger/trace",
                    "/api/ledger/explore", "/api/ledger/entities",
                    "/api/ledger/journey", "/api/ledger/lots", "/api/ledger/coverage"):
        assert retired not in routes, f"{retired} is still mounted"
    # `id` alone must reach subgraph() as the very same argument it always was.
    seed = ledger_explorer.entity_id("Lot", {"lot": "A"})
    assert ledger_trace_router._signed_start(seed, None, None) == seed
    assert ledger_trace_router._signed_start(seed, [], []) == seed
    assert ledger_trace_router._signed_start(seed, ["b"], ["c"]) == {
        "positive": [seed, "b"], "negative": ["c"]}
    assert ledger_trace_router._signed_start(seed, None, ["c"]) == {
        "positive": [seed], "negative": ["c"]}


def test_entity_label_takes_its_key_order_from_the_live_declaration():
    """A type declared after v1 has no entry in `ENTITY_TYPES`, so the label falls back
    to payload insertion order — which for `die` leads with x and y and pushes the only
    key that names the material out of a two-value label."""
    keys = {"x": 1.0, "y": 10.0, "mat_id": "SYN-XFER-CORE-W07", "mat_type": "Wafer"}
    saved = ledger_subgraph._entity_key_order
    try:
        # Declaration read, and this type is not in it: the label stays what it was.
        ledger_subgraph._entity_key_order = {}
        assert ledger_subgraph._entity_node("die", keys)["label"] == "1.0 / 10.0"
        # Declared: the order is the declaration's and the material name leads.
        ledger_subgraph._entity_key_order = {"die": ["mat_id", "x", "y", "mat_type"]}
        assert (ledger_subgraph._entity_node("die", keys)["label"]
                == "SYN-XFER-CORE-W07 / 1.0")
        # A type the declaration does not name is untouched, declared in v1 or not.
        assert ledger_subgraph._entity_node("Lot", {"lot": "A"})["label"] == "A"
        # Nothing else about the node moves.
        node = ledger_subgraph._entity_node("die", keys)
        assert node["node_kind"] == "entity" and node["keys"] == keys
        assert node["id"] == ledger_explorer.entity_id("die", keys)
    finally:
        ledger_subgraph._entity_key_order = saved


# The live ledger's own census, MEASURED 2026-08-23 against `ledger_events`.  Not a
# fixture's invention - all three hold atoms and no declaration carries them:
#     die       1,405 atoms   declared by v5, never by v1
#     DTJob       792 atoms   declared by v5, never by v1
#     WaferLeg     42 atoms   declared by NEITHER - v1 retired it, v5 never carried it
# 🔴 `WaferLeg` is why "fill the entity table from the live declaration" could not have
# been the fix: no edit to any declaration reaches a word both generations have dropped.
# A production ledger keeps atoms written before a declaration changed, so reading across
# a declaration edit is the ordinary case, not an exotic one.
MIXED_GENERATION_SEEDS = {
    "die": {"x": 1.0, "y": 8.0, "mat_id": "SYN-XFER-CORE-W04", "mat_type": "Wafer"},
    "DTJob": {"dt_job": "DT-EQP-01_20260511T0000_T01"},
    "WaferLeg": {"wafer": "SYN-CX-BW-001", "bonding_leg": "HBM-B_LOW-P"},
}
STILL_DECLARED_SEEDS = {"Wafer": {"wafer": "SYN-CX-BW-001"}, "Lot": {"lot": "SYN-CX-L1"}}


def test_each_undeclared_subject_type_seeds_on_its_own():
    """🔴 ASSERTED ONE AT A TIME ON PURPOSE.

    A single set-shaped assertion lets one member's success carry the others, and this
    repository has been bitten by exactly that.  Each of the three is named in its own
    failure message so a red says WHICH generation stopped reading.
    """
    for subject_type, keys in sorted(MIXED_GENERATION_SEEDS.items()):
        ref = ledger_subgraph.decode_node_id(
            ledger_explorer.entity_id(subject_type, keys))
        assert ref["kind"] == "entity", subject_type
        assert ref["type"] == subject_type, subject_type
        assert ref["keys"] == keys, subject_type


def test_both_generations_seed_together_in_one_request():
    """Mixed, resolved the way `subgraph()` itself resolves a seed set.

    Separately is not the same test as together: a per-seed refusal would fail the whole
    request, so the mixed set is what a screen actually sends when a user picks a die and
    a wafer in one investigation.
    """
    ids = {subject_type: ledger_explorer.entity_id(subject_type, keys)
           for subject_type, keys in
           list(MIXED_GENERATION_SEEDS.items()) + list(STILL_DECLARED_SEEDS.items())}
    collection = ledger_subgraph.finding_collection_node_id(
        "Wafer", STILL_DECLARED_SEEDS["Wafer"], "void", "CD-SEM", None)
    seed_signs = ledger_subgraph._signed_seeds(
        {"positive": list(ids.values()) + [collection], "negative": []})
    seed_refs = {item: ledger_subgraph.decode_node_id(item) for item in seed_signs}
    assert len(seed_refs) == len(ids) + 1
    for subject_type, node_id in ids.items():
        assert seed_refs[node_id]["type"] == subject_type, subject_type
    assert seed_refs[collection]["kind"] == "collection"


def test_restoring_the_write_gate_on_the_read_path_refuses_all_three():
    """🔴 THE MUTATION - without it the two tests above pass by not looking.

    Reinstates the pre-2026-08-23 ending of `decode_entity_id`, where the READ called
    `vocabulary.check_subject_keys` - the same function the write gate runs - and refused
    the id on any violation.  All three must go back to refusing, or the assertions above
    are not measuring the removal of that call.
    """
    from ledger import vocabulary
    original = ledger_explorer.decode_entity_id

    def gate_guarded(value):
        entity_type, keys = original(value)
        violations = vocabulary.check_subject_keys(entity_type, keys)
        if violations:
            raise ValueError("; ".join(violations))
        return entity_type, keys

    ledger_explorer.decode_entity_id = gate_guarded
    try:
        for subject_type, keys in sorted(MIXED_GENERATION_SEEDS.items()):
            try:
                ledger_subgraph.decode_node_id(
                    ledger_explorer.entity_id(subject_type, keys))
            except ValueError as exc:
                assert "is not a declared entity type" in str(exc), subject_type
            else:
                raise AssertionError(
                    f"{subject_type} was accepted with the write gate restored - the "
                    f"assertions above are not measuring the gate's removal")
        # The mutation is SPECIFIC, not a blanket break: what v1 declares was never the
        # part that stopped reading, so these two must survive it.
        for subject_type, keys in STILL_DECLARED_SEEDS.items():
            assert ledger_subgraph.decode_node_id(
                ledger_explorer.entity_id(subject_type, keys))["type"] == subject_type
    finally:
        ledger_explorer.decode_entity_id = original

    # 🔴 THE WRITE SIDE IS UNCHANGED, and this is where that is pinned.  The judgement
    # still exists and still says no; only the READ stopped asking it.  If this ever goes
    # empty, writing has been loosened and that is the wrong edit.
    assert vocabulary.check_subject_keys("WaferLeg", {"wafer": "W", "bonding_leg": "L"})
    assert vocabulary.check_subject_keys("die", MIXED_GENERATION_SEEDS["die"])


def test_the_carry_is_divided_where_the_walk_forks_and_nowhere_else():
    """The one pair of graphs the two candidate rules DISAGREE on, so this can only pass
    for the right reason.

    Nothing pinned this rule before 2026-08-23 and it had drifted into a length decay: the
    divisor was the undirected degree, which counts the neighbour a node was REACHED FROM,
    so a node in a pure chain divided by 2 at a place where nothing forks. That is the
    damping constant `_reach`'s own docstring forbids, arrived at without a constant, and it
    ranked a 3-hop process-history factor below a 1-hop one for its distance alone.

    Both halves are needed because each rule is right on one of them:
      * the CHAIN separates 「divide by degree」 from the correct rule — degree gives
        1.0, 0.5, 0.25 and the correct rule holds 1.0 all the way.
      * the FORK separates 「never divide」 from the correct rule — not dividing gives 1.0
        to each of three siblings, and it also catches dividing by the full degree, which
        splits a three-way fork into QUARTERS because it counts the way in.

    🔴 WAKE IT WITH THE MUTATIONS IT EXISTS FOR. Both go red, and they go red on different
    halves: restoring `carried / len(neighbours)` fails the chain, and dropping the division
    (`share = carried`) fails the fork.
    """
    chain = [{"source": "S", "target": "B"}, {"source": "B", "target": "C"},
             {"source": "C", "target": "D"}]
    reach, _ = ledger_subgraph._reach(["S", "B", "C", "D"], chain, {"S": 1})
    assert [round(reach[n][0], 6) for n in ("B", "C", "D")] == [1.0, 1.0, 1.0], (
        "a pure chain must not decay - nothing forks anywhere on it")

    fork = [{"source": "S", "target": "H"}, {"source": "H", "target": "X"},
            {"source": "H", "target": "Y"}, {"source": "H", "target": "Z"}]
    reach, _ = ledger_subgraph._reach(["S", "H", "X", "Y", "Z"], fork, {"S": 1})
    assert round(reach["H"][0], 6) == 1.0                      # first hop never divides
    third = round(1 / 3, 6)
    assert [round(reach[n][0], 6) for n in ("X", "Y", "Z")] == [third] * 3, (
        "a three-way fork splits three ways, not four - the way in is not an outgoing edge")


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
