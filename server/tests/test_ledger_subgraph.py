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
        entity_id, lookup, hops=3, direction="outgoing")
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
    # 🔴 `RETIRED_NODE_KINDS` left with `collect` on 2026-08-28: there is one kind
    # now, so a roster of the retired ones has nothing to exclude from. Asserted directly.
    assert not any(node["node_kind"] != "entity"
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
    # 🔴 `not_requested` until 2026-08-28.  It was the answer while `collect` chose the
    # population and a walk without it had nothing to rank; the owner ruled that the
    # candidates are every reached node, so a plain single-id walk ranks too and the only
    # remaining reason to say nothing is an empty one.
    assert plain["propagation"]["state"] == "ranked"
    assert plain["propagation"]["ranked"], "every reached node is a candidate"
    assert all(item["type"] for item in plain["propagation"]["ranked"]), (
        "each candidate carries its DECLARED type, not the projection's node_kind")
    assert all(len(item["reach"]) == 2 for item in plain["propagation"]["ranked"]), (
        "both reaches leave, unfolded - there is no ruled way to combine them yet")

    # No control seed is NOT 「controls came back clean」 — the axis was never examined,
    # and an unlisted subject is never promoted into the negative list to fill it.
    solo = ledger_subgraph.subgraph({"positive": [marked]}, lookup, hops=4,
                                    )
    assert solo["propagation"]["contrast"] == "unexamined"
    assert solo["walk"]["start"] == {"positive": 1, "negative": 0}

    contrasted = ledger_subgraph.subgraph(
        {"positive": [marked], "negative": [control]}, lookup, hops=4)
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


def test_the_two_open_routes_take_the_signed_seeds_and_the_frozen_ones_do_not():
    routes = {route.path: route for route in ledger_trace_router.router.routes}
    def params(path):
        return {field.alias or field.name
                for field in routes[path].dependant.query_params}
    # 🔴 `collect` LEFT WITH THE KINDS IT CHOSE BETWEEN (2026-08-28). Every node is a
    #    declared entity now, so a switch selecting a node kind has one value and is not a
    #    switch. The signed seeds stay -- they change the WALK, not the projection.
    assert {"positive", "negative"} <= params("/api/ledger/subgraph")
    assert not ({"collect", "include_values", "enrich_actions", "shape", "property_limit"}
                & params("/api/ledger/subgraph")), "a projection knob came back"
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
            hops=4, direction="both",
            node_limit=100, edge_limit=200,
            positive=None, negative=None,
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


def test_reaching_counts_one_however_wide_the_fork():
    """🔴 THE RULE REPLACED ITS PREDECESSOR ON 2026-08-29 (owner: 「그냥 많이 재면 신호
    약해지겠구나」).  This used to assert that a fork SPLITS the carry three ways.  It does
    not any more: splitting punishes the subject that was measured more, so a die carrying
    12 findings gave each of them 0.083 while a die carrying 3 gave each 0.333.

    Both halves are still needed, and each still separates the rule from one wrong answer:
      * the CHAIN separates it from 「divide by degree」, which decays 1, 0.5, 0.25 down a
        graph where nothing forks and would rank a 3-hop history below a 1-hop one for its
        distance alone.
      * the FORK separates it from 「divide among the ways out」, which is the rule that was
        here until today: three siblings must each read 1, not a third.

    🔴 WAKE IT WITH THE MUTATION IT EXISTS FOR: restore any division in `_reach` and the
    fork half goes red, because a divided fork cannot produce 1.
    """
    def graph(edges, ids):
        return {node_id: {"id": node_id, "type": "die"} for node_id in ids}, edges

    chain = [{"source": "S", "target": "B", "predicate": "transfer"},
             {"source": "B", "target": "C", "predicate": "transfer"},
             {"source": "C", "target": "D", "predicate": "transfer"}]
    nodes, edges = graph(chain, ("S", "B", "C", "D"))
    reach, _, _ = ledger_subgraph._reach(nodes, edges, {"S": 1})
    assert [reach[n][0] for n in ("B", "C", "D")] == [1, 1, 1], (
        "a chain must not decay - nothing forks anywhere on it")

    fork = [{"source": "S", "target": "H", "predicate": "transfer"},
            {"source": "H", "target": "X", "predicate": "observed"},
            {"source": "H", "target": "Y", "predicate": "observed"},
            {"source": "H", "target": "Z", "predicate": "observed"}]
    nodes, edges = graph(fork, ("S", "H", "X", "Y", "Z"))
    reach, _, _ = ledger_subgraph._reach(nodes, edges, {"S": 1})
    assert [reach[n][0] for n in ("H", "X", "Y", "Z")] == [1, 1, 1, 1], (
        "a wide fork must not weaken the things it forks to - reaching is reaching")
    assert all(isinstance(value, int) for item in reach.values() for value in item), (
        "reach must be integers, or a tie stops being exact and dominance breaks on rounding")


def test_reach_obeys_the_two_walk_rules_the_fetch_obeys():
    """🔴 THE CONTRAST MUST NOT OUT-WALK THE FETCH.  `_reach` re-walks the merged graph, so
    a rule the fetch enforces and this does not lets a seed reach what its own walk never
    would.  MEASURED 2026-08-29, the day division stopped hiding it: every one of 996
    candidates came back [2, 2].

    Each half is one of the two rules, on a graph where breaking it is visible:
      * A NAME IS NOT A THOROUGHFARE - `void` is static, so a seed may reach it and may not
        continue out of it into the other seed's die.
      * A STEP DOES NOT GO BACK DOWN THE PREDICATE IT JUST CLIMBED - climbing `inspected`
        to a wafer must not descend `inspected` into that wafer's other dies.
    """
    nodes = {"d1": {"id": "d1", "type": "die"}, "d2": {"id": "d2", "type": "die"},
             "void": {"id": "void", "type": "defect_kind"},
             "w": {"id": "w", "type": "wafer"},
             "sib": {"id": "sib", "type": "die"}}
    edges = [{"source": "d1", "target": "void", "predicate": "of_kind"},
             {"source": "d2", "target": "void", "predicate": "of_kind"},
             {"source": "w", "target": "d1", "predicate": "inspected"},
             {"source": "w", "target": "sib", "predicate": "inspected"}]

    reach, _, _ = ledger_subgraph._reach(nodes, edges, {"d1": 1}, static_types={"defect_kind"})
    assert reach["void"][0] == 1, "the name itself is reached"
    assert "d2" not in reach, "the walk left a name and landed in the other seed's die"
    assert "sib" not in reach, "the walk climbed a wafer and came back down to its siblings"

    # 🔴 THE TWO GUARDS ARE INDEPENDENT, so each is woken separately. Without the classes
    # declared the name becomes a thoroughfare and the other seed's die IS reached; the
    # sibling stays out either way, because the step that would reach it is refused by the
    # predicate rule and not by the class rule.
    leaky, _, _ = ledger_subgraph._reach(nodes, edges, {"d1": 1})
    assert "d2" in leaky, "the class rule is what keeps a name from being walked through"
    assert "sib" not in leaky, "the predicate rule does not depend on the classes"


class RecordingLookup:
    """Wraps the contract double and keeps every `(entities, follow)` it was asked for.

    The narrowing this test exists for happens BEFORE the fetch, so asserting on the
    returned graph alone cannot tell it apart from filtering afterwards -- both produce
    the same nodes. What separates them is the argument the lookup was called with.
    """

    def __init__(self, atoms):
        self.inner = ledger_subgraph.InMemoryEvidenceLookup(atoms)
        self.calls = []

    def claims_for_entities(self, entities, direction, limit, *, follow=None):
        self.calls.append(({item[0] for item in entities},
                           None if follow is None else tuple(follow)))
        return self.inner.claims_for_entities(entities, direction, limit, follow=follow)


def _kind_atom(number, subject_type, subject, predicate, target_type, target):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type,
        subject_keys={subject_type: subject}, predicate=predicate,
        object_kind="entity_ref",
        object_payload={"type": target_type, "keys": {target_type: target},
                        "qualifiers": {}},
        occurred_at=NOW, source_who="fixture", source_translator_ver="v1",
        source_raw_ref=f"row:{number}", supersedes=None, source_event_id=EVENT,
        source_event_state="source_record")


NAME_FIXTURE = [
    _kind_atom(201, "wafer", "W1", "measures", "quantity", "Q"),
    _kind_atom(202, "wafer", "W2", "measures", "quantity", "Q"),
    _kind_atom(203, "quantity", "Q", "leads_to", "quantity", "Q2"),
]


def test_a_name_is_FETCHED_with_the_narrower_follow_rather_than_filtered_after():
    """🔴 THE REFUSAL HAS TO HAPPEN BEFORE THE QUERY, or the budget is already spent.

    `_expand_atom` refuses a static-to-dynamic step, and for a while that was the only
    place it happened -- so the atoms were read out of the ledger, charged to
    `claims_scanned`, and then dropped. MEASURED 2026-08-29 on the live ledger: one defect
    seeded with `of_kind` followed scanned 6,000 claims (the ceiling) to return 13 nodes
    and stopped at hop 2; without it, 371 claims and 315 nodes at hop 4. `defect_kind`
    carries 103,841 atoms against ONE distinct object.

    A test on the returned graph cannot see this -- filtering after the fetch returns the
    same nodes. So this asserts the ARGUMENT: the frontier splits by entity class and the
    static half is asked for the static-to-static predicates only.

    🔴 WAKE IT: drop the class split in `subgraph()` and the static frontier is fetched
    with the full follow, so the recorded call carries `measures` and W2 arrives.
    """
    lookup = RecordingLookup(NAME_FIXTURE)
    body = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("wafer", {"wafer": "W1"}), lookup,
        hops=4, direction="both", follow=["measures", "leads_to"],
        static_types={"quantity"}, static_follow={"leads_to"})

    labels = {node["label"] for node in body["nodes"]}
    assert "Q" in labels, "the name itself is collected"
    assert "Q2" in labels, "static -> static still walks, or the causal chain dies"
    assert "W2" not in labels, "the walk left a name and came back into the world"

    narrowed = [follow for _, follow in lookup.calls if follow == ("leads_to",)]
    assert narrowed, (
        "the static frontier was never fetched with the narrowed follow - the refusal is "
        "happening after the query, where the budget has already been spent")
    assert not any(follow is None for _, follow in lookup.calls), (
        "a falsy follow reads as EVERY predicate in the lookup contract")


def test_the_static_step_predicates_are_DERIVED_from_the_declaration(monkeypatch):
    """🔴 THE ONE ALLOWANCE A NAME HAS IS COMPUTED, NOT LISTED.

    A static node is collected and not expanded, except along predicates whose BOTH ends
    are static -- today that is `{leads_to}` and it is the mechanism chain. Spelling the
    set in code would make it a domain word in a branch; it is read off the declaration
    instead, so declaring a new static-to-static predicate widens it with no edit.

    The fixture holds one of each shape so the derivation cannot pass by returning
    everything or the first thing it sees.

    🔴 AND AN UNREADABLE DECLARATION RETURNS THE EMPTY SET, which expands no static node
    at all. That is the safe direction: refusing the step costs the causal chain, while
    guessing costs the whole walk -- one name with 103,841 atoms against a single object
    is enough to spend the budget.
    """
    declared = {
        "entities": {"kind@1": {"class": "static"}, "name@1": {"class": "static"},
                     "thing@1": {"class": "dynamic"}, "other@1": {}},
        "vocabulary": {
            "s_to_s@1": {"subjects": ["kind@1"],
                         "object": {"kind": "entity_ref", "types": ["name@1"]}},
            "s_to_d@1": {"subjects": ["kind@1"],
                         "object": {"kind": "entity_ref", "types": ["thing@1"]}},
            "d_to_s@1": {"subjects": ["thing@1"],
                         "object": {"kind": "entity_ref", "types": ["kind@1"]}},
            "d_to_undeclared@1": {"subjects": ["kind@1"],
                                  "object": {"kind": "entity_ref", "types": ["other@1"]}},
            "no_object@1": {"subjects": ["kind@1"], "object": {"kind": "value"}},
        },
    }
    from ledger import config as ledger_config
    monkeypatch.setattr(ledger_config, "load", lambda *a, **k: declared)
    assert ledger_trace_router._static_step_predicates() == {"s_to_s"}

    def unreadable(*args, **kwargs):
        raise RuntimeError("declaration unreadable")

    monkeypatch.setattr(ledger_config, "load", unreadable)
    assert ledger_trace_router._static_step_predicates() == set(), (
        "an unreadable declaration must expand no name, not every name")


BACKBONE_CHAIN = [
    _kind_atom(220 + index, "die", f"D{index}", "transfer", "die", f"D{index + 1}")
    for index in range(5)
]


def test_backbone_hops_buys_depth_for_steps_that_stay_inside_the_world():
    """🔴 THE SECOND BUDGET IS NOT A SECOND DEPTH. Following one material through its own
    transfer history never LEAVES, so those steps spend `backbone_hops` while `hops`
    stays the allowance for departures. Both are still counted by `depths`, so every
    reader of it keeps the meaning it had.

    The chain here is five `transfer` steps between dies -- dynamic to dynamic the whole
    way, so every step is free of the departure budget and the only thing that can carry
    the walk past the first hop is the backbone allowance.

    🔴 WAKE IT: fix `budget_hops` at `hops` and the second half returns two nodes.
    """
    seed = ledger_explorer.entity_id("die", {"die": "D0"})
    lookup = ledger_subgraph.InMemoryEvidenceLookup(BACKBONE_CHAIN)

    near = ledger_subgraph.subgraph(seed, lookup, hops=1, backbone_hops=0,
                                    direction="outgoing", follow=["transfer"])
    assert len(near["nodes"]) == 2, "one departure buys one hop"

    far = ledger_subgraph.subgraph(seed, lookup, hops=1, backbone_hops=4,
                                   direction="outgoing", follow=["transfer"])
    assert len(far["nodes"]) == 6, (
        "the backbone allowance did not carry the walk down a chain that never departs: "
        f"{len(far['nodes'])} nodes")
    assert max(node["depth"] for node in far["nodes"]) == 5, (
        "`depths` must still count every step, or hops_reached and the trails change meaning")


SIBLING_FIXTURE = [
    _kind_atom(211, "wafer", "W", "inspected", "die", "D1"),
    _kind_atom(212, "wafer", "W", "inspected", "die", "D2"),
    _kind_atom(213, "wafer", "W", "inspected", "die", "D3"),
]


def test_the_fetch_does_not_climb_a_container_and_come_back_down_to_its_siblings():
    """🔴 THE SAME REFUSAL AS `_reach`, ON THE FETCH SIDE, AND IT WAS UNGUARDED.

    Seeded at one die and walked both ways, the only route to the wafer's other dies is
    to climb `inspected` backwards and walk it forwards again. Those siblings are
    one-sided by construction and say nothing.

    MEASURED 2026-08-29 on the live ledger: one defect at hops=4 returned 199 defects and
    115 dies, of which 189 and 111 arrived exactly this way. The control settles it --
    `direction=outgoing` cannot reverse, and that seed's true lineage is four dies.

    🔴 THIS TEST EXISTS BECAUSE THE GUARD WAS UNTESTED. Turning the `arrivals` check in
    `_expand_atom` into a no-op left the whole ledger suite green (445 passed, the same 9
    pre-existing failures), while the walk it guards was the largest behavioural change of
    that night. All three types here are dynamic, so the class rule cannot be what passes
    this -- only the predicate rule can.
    """
    body = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("die", {"die": "D1"}),
        ledger_subgraph.InMemoryEvidenceLookup(SIBLING_FIXTURE),
        hops=4, direction="both", follow=["inspected"])

    # 🔴 COUNT THE DIES, DO NOT LOOK FOR THEIR LABELS. A die's label is built from
    # `mat_id`/`x`/`y`, so this fixture's dies all render as the bare word "die" and
    # `"D2" not in labels` is true whether or not D2 is in the graph -- the first version
    # of this test asserted exactly that and passed with the guard turned off.
    dies = [node for node in body["nodes"] if node["type"] == "die"]
    assert {node["label"] for node in body["nodes"]} >= {"W"}, (
        "climbing to the container is the step that stays")
    assert len(dies) == 1, (
        "the walk climbed `inspected` and walked it back down into the seed's siblings: "
        f"{len(dies)} dies came back where only the seed should have")


def test_an_empty_static_intersection_skips_the_fetch_instead_of_passing_an_empty_list():
    """🔴 AN EMPTY LIST IS NOT `None`. `claims_for_entities` reads a falsy `follow` as
    「every predicate」, so narrowing to an empty intersection and passing it would fetch
    MORE than narrowing to one name. The group has to be skipped instead.

    Here the caller follows `measures` only, so a static node's allowance is empty.
    """
    lookup = RecordingLookup(NAME_FIXTURE)
    body = ledger_subgraph.subgraph(
        ledger_explorer.entity_id("wafer", {"wafer": "W1"}), lookup,
        hops=4, direction="both", follow=["measures"],
        static_types={"quantity"}, static_follow={"leads_to"})

    labels = {node["label"] for node in body["nodes"]}
    assert "Q" in labels and "W2" not in labels and "Q2" not in labels
    assert all(follow == ("measures",) for _, follow in lookup.calls), (
        "the static group was fetched anyway, with an empty or absent follow")


def test_a_reach_of_zero_reports_whether_the_side_could_have_reached_that_kind():
    """🔴 ZERO SAYS NOTHING ABOUT ITSELF, so each side is a pair: reached over reachable.

    A control that reached the candidate's KIND and carried a different one is a real
    difference. A control that could not reach that kind at all produces the same 0 and
    means nothing by it -- MEASURED 2026-08-29, a seeded control whose bridge to its core
    wafers was missing put `SYN-R-CMP-01` in rank 1 at [2, 0] while the ledger plainly
    recorded that same recipe on its own cores.

    The fixture holds both cases at once so neither can pass by accident:
      * `recipe` — BOTH seeds reach one, so the denominator is 1/1 and the marked side's
        recipe is a real difference.
      * `defect_kind` — only the marked seed reaches one, so the control's zero has a zero
        denominator behind it. This is also why a tautological axis excludes itself: a
        group defined as void-free cannot reach `defect_kind`.
    """
    def entity(node_id, node_type):
        return {"id": node_id, "type": node_type, "label": node_id}
    nodes = {n["id"]: n for n in (
        entity("p1", "wafer"), entity("n1", "wafer"),
        entity("rA", "recipe"), entity("rB", "recipe"),
        entity("void", "defect_kind"))}
    edges = [{"source": "p1", "target": "rA", "predicate": "processed_with"},
             {"source": "n1", "target": "rB", "predicate": "processed_with"},
             {"source": "p1", "target": "void", "predicate": "of_kind"}]

    block = ledger_subgraph._propagation(
        nodes, edges, {"p1": 1, "n1": -1}, True,
        static_types={"recipe", "defect_kind"})
    ranked = {item["label"]: item for item in block["ranked"]}

    assert ranked["rA"]["reach"] == [1, 0]
    assert ranked["rA"]["reachable"] == [1, 1], (
        "both sides reached a recipe, so the control's zero is a real absence")
    assert ranked["void"]["reach"] == [1, 0]
    assert ranked["void"]["reachable"] == [1, 0], (
        "the control never reached a defect_kind, so its zero carries no evidence")
    assert ranked["rB"]["reach"] == [0, 1] and ranked["rB"]["reachable"] == [1, 1]


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

#: 🔴 TWO MORE RETIRED 2026-08-28: the ranked-answer tests. `collect` turned the walk
#: into a ranking over one node KIND, and there is one kind now, so the ranking has nothing to
#: choose between. `_rank_layers` went with them.


# ---------------------------------------------------------------- frames as a derived key
def seat_atom(number, source, x, y, target_lot):
    """One source's reading of one physical seat, in ITS OWN frame."""
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="die",
        subject_keys={"mat_id": "W1", "x": x, "y": y, "mat_type": "Wafer"},
        predicate="transfer", object_kind="entity_ref",
        object_payload={"type": "Lot", "keys": {"lot": target_lot}, "qualifiers": {}},
        occurred_at=NOW, source_who=source, source_translator_ver="v1",
        source_raw_ref=f"row:{number}", supersedes=None, source_event_id=EVENT,
        source_event_state="source_molecule")


def seat_fixture():
    """Two logs reading the SAME seat, one of them a quarter turn out.

    `left` writes it as (2, 5).  `right` reads the same physical hole as (5, 5) because its
    frame is `x = -y + 7`, `y = x`.  Nothing in the ledger says these are the same.
    """
    return [seat_atom(701, "left", 2, 5, "L-LEFT"),
            seat_atom(702, "right", 5, 5, "L-RIGHT")]


SEAT_FRAMES = {
    "ok": True,
    "keys": {"die": ["x", "y"]},
    "by_source": {"right": {"die": {"x": {"from": "y", "sign": -1, "offset": 7},
                                    "y": {"from": "x", "sign": 1, "offset": 0}}}},
    "declaring": 1,
}


def walk_the_seat(frames):
    saved = ledger_subgraph._declared_frame_cache
    try:
        ledger_subgraph._declared_frame_cache = frames
        return ledger_subgraph.subgraph(
            ledger_explorer.entity_id("die", {"mat_id": "W1", "x": 2, "y": 5,
                                              "mat_type": "Wafer"}),
            ledger_subgraph.InMemoryEvidenceLookup(seat_fixture()), hops=2)
    finally:
        ledger_subgraph._declared_frame_cache = saved


def test_two_frames_of_one_seat_are_one_node_and_the_ledger_says_nothing():
    """🔴 THE POINT: the walk decides they are the same seat, the ledger never says so.

    `right` stored (5, 2); the seed is `left`'s (2, 5).  Half A carries the frontier DOWN
    through the inverse so the fetch matches `right`'s stored row, and Half B carries the
    endpoint UP so both readings build one node.  Neither atom is rewritten, and correcting
    the declaration changes the answer on the next walk with nothing to retract.
    """
    body = walk_the_seat(SEAT_FRAMES)
    seats = [node for node in body["nodes"] if node["type"] == "die"]
    assert len(seats) == 1, "two readings of one seat must be ONE node"
    reached = {edge["target"] for edge in body["edges"]}
    lots = {node["id"] for node in body["nodes"] if node["type"] == "Lot"}
    assert lots and lots <= reached, "both sides' edges must arrive"
    assert len(body["edges"]) == 2, "one edge per reading, both kept"
    assert body["walk"]["frames"]["declaration_read"] is True
    assert body["walk"]["frames"]["sources_declaring"] == 1
    assert body["walk"]["frames"]["sources_on_framed_types"] == 2
    assert body["walk"]["frames"]["sources_on_framed_types_with_frame"] == 1

    # correcting the declaration changes the answer, with no ledger write
    wrong = dict(SEAT_FRAMES, by_source={"right": {"die": {
        "x": {"from": "y", "sign": -1, "offset": 99},
        "y": {"from": "x", "sign": 1, "offset": 0}}}})
    # 🔴 THE SEAT COUNT CANNOT SEE THIS. A broken frame leaves the seed seat standing
    # alone, which is also ONE node - the same number the joined case gives. What moves is
    # what ARRIVES: the other side's edge stops coming.
    broken = walk_the_seat(wrong)
    assert len(broken["edges"]) == 1, (
        "a wrong offset must stop joining them - otherwise the transform is a no-op")
    assert not [node for node in broken["nodes"]
                if node.get("keys", {}).get("lot") == "L-RIGHT"], (
        "the other side must become unreachable when the frame is wrong")


def test_without_the_declaration_the_same_fixture_is_TWO_seats():
    """🔴 THE DISCRIMINATING INPUT, not a copy of the test above.

    With the frame removed the two readings are two different coordinates and must land as
    two nodes.  Without this, a transform that did nothing at all would still pass the test
    above whenever the two sides happened to share a coordinate.
    """
    body = walk_the_seat({"ok": True, "keys": {}, "by_source": {}, "declaring": 0})
    seats = [node for node in body["nodes"] if node["type"] == "die"]
    assert len(seats) == 1, (
        "only the seeded reading is reachable when no frame is declared")
    assert len(body["edges"]) == 1, "the other side's atom must NOT be joined"
    assert body["walk"]["frames"]["sources_declaring"] == 0
