from datetime import datetime, timedelta, timezone
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger.envelope import source_event_identity
import ledger_explorer
from ledger_api import ledger_subgraph
import pytest
from fastapi import HTTPException
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


def test_legacy_atom_is_one_honest_event_and_can_be_reseeded():
    legacy = atom(9, "OLD", "register", event=None, event_state=None)
    lookup = ledger_subgraph.InMemoryEvidenceLookup([legacy])
    entity_id = ledger_explorer.entity_id("Lot", {"lot": "OLD"})
    body = ledger_subgraph.subgraph(entity_id, lookup, hops=2)
    # 🔴 a legacy atom no longer becomes an event NODE -- it is still one honest fact, now
    # carried as an edge. `register` has no object, so what it leaves is the subject itself.
    assert not any(node["node_kind"] in ledger_subgraph.RETIRED_NODE_KINDS
                   for node in body["nodes"])
    assert any(node["label"] == "OLD" for node in body["nodes"])
    reseeded = ledger_subgraph.subgraph(entity_id, lookup, hops=1)
    assert any(node["label"] == "OLD" for node in reseeded["nodes"])


def test_caps_are_reported_instead_of_looking_complete():
    """A cap that bites must be SAID, never silently shrink the answer.

    🔴 The fixture reaches 30 DISTINCT lots on purpose. From 2026-08-25 `node_limit` counts
    things in the world and not the parts one assertion is made of, so a fixture of 30
    measurements on ONE lot -- which is what this used to be -- yields a single world node and
    stops testing the cap at all. Thirty targets make the cap bite for the reason it exists.
    """
    many = [atom(index + 100, "FAN", "derived_from", target=f"LOT-{index:02d}")
            for index in range(30)]
    seed = ledger_explorer.entity_id("Lot", {"lot": "FAN"})
    body = ledger_subgraph.subgraph(
        seed, ledger_subgraph.InMemoryEvidenceLookup(many),
        hops=4, node_limit=10, edge_limit=20)
    # measurement nodes still ride free; everything else shares node_limit
    world = [node for node in body["nodes"] if node["node_kind"] != "value"]
    assert len(world) == 10
    assert body["truncated"]["nodes"] is True
    assert body["truncated"]["reason"]
    # and the facts are still carried -- as edges, which is where they live now
    assert any(edge.get("claim_id") for edge in body["edges"])


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
    # 🔴 a trail no longer STEPS THROUGH a claim -- it steps between things in the world and
    # the assertion is the edge it crosses. Asserting a claim hop would pin the old shape.
    assert all(hop["node_kind"] not in ledger_subgraph.RETIRED_NODE_KINDS for hop in hops)
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


def test_the_two_open_routes_take_the_signed_seeds_and_the_frozen_ones_do_not():
    routes = {route.path: route for route in ledger_trace_router.router.routes}
    def params(path):
        return {field.alias or field.name
                for field in routes[path].dependant.query_params}
    assert {"positive", "negative", "collect"} <= params("/api/ledger/subgraph")
    # `/api/ledger/explore_entity` was retired 2026-08-23; `/subgraph` answers it.
    # `/trace` and `/explore` were DELETED 2026-08-25 with the legacy screens, so the
    # assertion becomes the stronger one the line below already uses: they are not routes
    # at all. Asserting "they do not take signed seeds" would pass vacuously on a
    # KeyError-free dict lookup only because there is nothing left to ask.
    # 🔴 RETIRED 2026-08-28: the router keeps `/subgraph` and `/declaration` and
    #    nothing else. Asserted as absence rather than by counting, so a route added back
    #    by name fails here even if the count happens to match.
    for retired in ("/api/ledger/explore_entity", "/api/ledger/trace",
                    "/api/ledger/explore", "/api/ledger/entities",
                    "/api/ledger/journey", "/api/ledger/lots", "/api/ledger/coverage",
                    "/api/ledger/subgraph/table", "/api/ledger/siblings",
                    "/api/ledger/trends", "/api/ledger/composition",
                    "/api/ledger/selection/resolve", "/api/ledger/kinds",
                    "/api/ledger/structure", "/api/ledger/lot_map"):
        assert retired not in routes, f"{retired} is still mounted"
    assert set(routes) == {"/api/ledger/subgraph", "/api/ledger/declaration"}
    # `id` alone must reach subgraph() as the very same argument it always was.
    seed = ledger_explorer.entity_id("Lot", {"lot": "A"})
    assert ledger_trace_router._signed_start(seed, None, None) == seed
    assert ledger_trace_router._signed_start(seed, [], []) == seed
    assert ledger_trace_router._signed_start(seed, ["b"], ["c"]) == {
        "positive": [seed, "b"], "negative": ["c"]}
    assert ledger_trace_router._signed_start(seed, None, ["c"]) == {
        "positive": [seed], "negative": ["c"]}


def test_an_undeclared_follow_predicate_is_refused_by_walking_the_refusal():
    """🔴 THE REFUSAL PATH IS EXECUTED HERE, not merely described.

    It shipped broken on 2026-08-25: the check was rewritten to use
    `_followable_predicates()` while the error body still read a `declared` variable that no
    longer existed, so a typo answered 500 instead of 422. Nothing caught it because every
    test called `subgraph()` directly and the route's own guard had never once been run --
    a guard goes wrong on the day it becomes reachable, and that day was the day it was
    written.

    Calling the route function is the point of this test. Asserting the message without
    executing the branch would reproduce exactly the hole it closes.
    """
    followable = ledger_trace_router._followable_predicates()
    assert "processed_with" in followable, "a real predicate must be followable"

    with pytest.raises(HTTPException) as raised:
        ledger_trace_router.evidence_subgraph(
            node_id=ledger_explorer.entity_id("Lot", {"lot": "A"}),
            hops=4, direction="both", include_values=True,
            include_actions=False, node_limit=100, edge_limit=200, shape="graph",
            property_limit=1000, positive=None, negative=None, collect=None,
            follow=["definitely_not_a_predicate"], db=None)
    assert raised.value.status_code == 422
    detail = raised.value.detail
    assert detail["reason"] == "predicate_not_declared"
    assert detail["unknown"] == ["definitely_not_a_predicate"]
    # the body must be able to say what WAS allowed -- that is the field that was undefined
    assert "processed_with" in detail["declared"]


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


def test_restoring_the_write_gate_on_the_read_path_refuses_all_three():
    """🔴 THE MUTATION - without it the two tests above pass by not looking.

    Reinstates the pre-2026-08-23 ending of `decode_entity_id`, where the READ ran the
    write gate's judgement and refused the id on any violation.  All three must go back to
    refusing, or the assertions above are not measuring the removal of that call.

    🔴 THE GUARD IS RESTATED FROM THE DECLARATION, not imported.  It used to call
    `vocabulary.check_subject_keys`, and that module was the v1 word list this repository
    retired on 2026-08-27.  A mutation may restate the rule it reinstates -- that is what
    makes it a mutation -- but it must not restate it from a source the product no longer
    reads, or the control would go on passing after the rule itself changed.
    """
    from ledger import config as ledger_config
    declared_entities = {
        str(key).split("@", 1)[0]: set((value or {}).get("keys") or ())
        for key, value in ((ledger_config.load() or {}).get("entities") or {}).items()
    }
    original = ledger_explorer.decode_entity_id

    def gate_guarded(value):
        entity_type, keys = original(value)
        if entity_type not in declared_entities:
            raise ValueError(f"{entity_type} is not a declared entity type")
        missing = declared_entities[entity_type] - set(keys or {})
        if missing:
            raise ValueError(
                f"{entity_type} is not a declared entity type with these keys "
                f"(missing {sorted(missing)})")
        return entity_type, keys

    # 🔴 `die` IS DECLARED NOW and so it is not part of the mutation's refusing set.
    #    The 2026-08-27 rebuild moved the ledger's subject onto `die@1`, so the spelling
    #    that v1 refused is the spelling v5 emits.  Asserting it still refuses would be
    #    asserting the old rule, and the mutation would then be measuring history rather
    #    than the gate.  What remains undeclared is the CAPITALISED v1 generation, and
    #    that is what the read had to stop asking about.
    refused = {name: keys for name, keys in MIXED_GENERATION_SEEDS.items()
               if name not in declared_entities}
    assert refused, ("every mixed-generation seed is declared now - this mutation no "
                     "longer restores anything and should be retired, not adjusted")
    ledger_explorer.decode_entity_id = gate_guarded
    try:
        for subject_type, keys in sorted(refused.items()):
            try:
                ledger_subgraph.decode_node_id(
                    ledger_explorer.entity_id(subject_type, keys))
            except ValueError as exc:
                assert "is not a declared entity type" in str(exc), subject_type
            else:
                raise AssertionError(
                    f"{subject_type} was accepted with the write gate restored - the "
                    f"assertions above are not measuring the gate's removal")
        # The mutation is SPECIFIC, not a blanket break: what the DECLARATION declares was
        # never the part that stopped reading, so a declared spelling must survive it.
        # 🔴 READ, NOT RESTATED.  `STILL_DECLARED_SEEDS` spells its types the v1 way
        # (`Wafer`, `Lot`), and those capitals stopped being declared at the lowercase
        # migration -- a hand-kept second copy of the vocabulary going stale is the exact
        # failure this whole retirement is about, so the survivor is taken from the
        # declaration instead of from the fixture.
        for subject_type, keys in STILL_DECLARED_SEEDS.items():
            declared_spelling = subject_type.lower()
            if declared_spelling not in declared_entities:
                continue
            assert ledger_subgraph.decode_node_id(
                ledger_explorer.entity_id(declared_spelling, keys))["type"]                 == declared_spelling
    finally:
        ledger_explorer.decode_entity_id = original

    # 🔴 THE JUDGEMENT ITSELF IS UNCHANGED, and this is where that is pinned.  The
    # declaration still refuses these two spellings; only the READ stopped asking.  If
    # this ever goes empty, the declaration has been loosened and that is the wrong edit.
    assert "WaferLeg" not in declared_entities
    assert "DTJob" not in declared_entities
    assert "die" in declared_entities      # the rebuild's subject, declared and emitted


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


#: 🔴 NINE TESTS RETIRED HERE 2026-08-28, WITH THE NODE KINDS THEY MEASURED. They
#: asserted finding points, finding collections, quantity nodes, value nodes, claim nodes,
#: source-event nodes, the `collect` switch and the retired id prefixes -- every one of them
#: a place the walk no longer has. What survives is the walk's own contract: declared
#: entities, the edges between them, the budget and `truncated`.
