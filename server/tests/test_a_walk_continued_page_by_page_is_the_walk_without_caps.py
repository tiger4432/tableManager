# -*- coding: utf-8 -*-
"""총괄 ad3c03e71 · df746abf6 (소유자 「원하는 걸 다 얻었는지 파악하고 계속 추가 걷기」 · 「상한은 그대로」): a walk its caps
stopped hands back `more.resume`; handed back, the next page walks on within the same caps. One BFS paused and continued:

  every cap a page can meet (atoms · nodes · edges), every page merged   = the same walk with no cap
  a page that says «complete» for a type                                 has nothing of that type left to find
  each page                                                              within its caps
  an atom written after the first page                                   not in any page after it; the answer says as of when

The seeds W (wafer) and Q0 (quantity, a static seed: its first step goes down to dies). Dies D0..D5 in W, E0..E2 measure
Q0 - so a die is reached for no departure (D) or one (E). S (quantity) is measured by E0 then D0, the newer first: a page
cut between the two has S at its boundary (2 departures) and the next lowers it to 1, so S leads on to the recipe R. D1 and
D2 are linked (a step between two nodes of one depth); D3's links are opened (`expand`), so its group reads three times.
The operator O1 calibrates Q0 - reached only by the static seed's own step, which is not held to names."""
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
from ledger.uuid7 import uuid7  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
QUALIFIERS = {"required": [], "optional": []}


def _predicate(subject, far):
    return {"status": "active", "subjects": [subject + "@1"],
            "object": {"kind": "entity_ref", "types": [far + "@1"], "qualifiers": QUALIFIERS}}


VOCABULARY = {"in_container@1": _predicate("die", "wafer"), "measures@1": _predicate("die", "quantity"),
              "linked@1": _predicate("die", "die"), "leads_to@1": _predicate("quantity", "recipe"),
              "calibrates@1": _predicate("operator", "quantity"), "twin@1": _predicate("die", "die")}
COUNTER = iter(range(1, 10 ** 6))


def _atom(subject_type, subject_keys, predicate, far_type, far_keys, atom_id=None):
    number = next(COUNTER)
    return ledger_subgraph.EvidenceAtom(
        id=atom_id or str(uuid.UUID(int=number)), subject_type=subject_type, subject_keys=subject_keys,
        predicate=predicate, object_kind="entity_ref", object_payload={"type": far_type, "keys": far_keys},
        occurred_at=NOW + timedelta(seconds=number), source_who="t", source_translator_ver="v1",
        source_raw_ref="row:%d" % number, supersedes=None, source_event_id=str(uuid.UUID(int=10 ** 6 + number)),
        source_event_state="source_molecule")


def die(name):
    return {"d": name}


ATOMS = ([_atom("operator", {"o": "O1"}, "calibrates", "quantity", {"q": "Q0"})]     # the oldest: read last
         + [_atom("die", die("D%d" % k), "in_container", "wafer", {"w": "W"}) for k in range(6)]
         + [_atom("die", die("E%d" % k), "measures", "quantity", {"q": "Q0"}) for k in range(3)]
         + [_atom("die", die("D0"), "measures", "quantity", {"q": "S"}),
            _atom("die", die("E0"), "measures", "quantity", {"q": "S"}),               # newer: read first
            _atom("die", die("D1"), "linked", "die", die("D2"))]
         + [_atom("die", die("D3"), "linked", "die", die("F%d" % k)) for k in range(4)]
         + [_atom("die", die("D3"), "measures", "quantity", {"q": "T"}),
            _atom("quantity", {"q": "S"}, "leads_to", "recipe", {"r": "R"}),
            _atom("die", die("F0"), "linked", "die", die("G0")),
            _atom("die", die("D5"), "linked", "die", die("H0")),
            _atom("die", die("F1"), "twin", "die", die("D4"))])                         # back to a die read whole
# W marked, Q0 a control - the ranking's two sides (응용 18766: a page after the first ranked nothing)
SEEDS = {"positive": [explorer.entity_id("wafer", {"w": "W"})],
         "negative": [explorer.entity_id("quantity", {"q": "Q0"})]}
EXPAND = ["%s|linked|outgoing" % explorer.entity_id("die", die("D3"))]


@pytest.fixture
def declared(tmp_path):
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps({"vocabulary": VOCABULARY}), encoding="utf-8")
    ledger_subgraph.reset_declaration_cache()
    yield (str(path),)
    ledger_subgraph.reset_declaration_cache()


CURSORS = {}                    # id(page) -> the kept walk's cursor after it
TOKEN_BYTES = 100               # a page's more.resume as sent: {"walk": "<server start>.<pid>.<walk>.<page>"}


def walk(declared, atoms, resume=None, nodes=ledger_subgraph.DEFAULT_NODE_LIMIT,
         edges=ledger_subgraph.DEFAULT_EDGE_LIMIT, follow=None):
    return ledger_subgraph.subgraph(
        SEEDS, ledger_subgraph.InMemoryEvidenceLookup(atoms), declaration_paths=declared, hops=2,
        backbone_hops=2, static_types=["quantity", "recipe"], static_follow=["leads_to"], node_limit=nodes,
        edge_limit=edges, expand=EXPAND, resume=resume, follow=follow, resumable=True)


def _kind(node):
    return str(node["type"]).split("@")[0]


def _ranked(answer):
    """{node: (reach, per seed its trail's hop count)} and {(node, seed): (hop ids, hop predicates)} of one answer's
    ranking. A trail is the first shortest path, so two of one length may differ in which - the count may not."""
    ranked, hops = {}, {}
    for row in answer["propagation"]["ranked"]:
        ranked[row["id"]] = (row["reach"], sorted((trail["seed"], len(trail["hops"])) for trail in row["evidence"]))
        for trail in row["evidence"]:
            hops[(row["id"], trail["seed"])] = (tuple(hop["id"] for hop in trail["hops"]),
                                                tuple(tuple(hop.get("predicates") or ()) for hop in trail["hops"]))
    return ranked, hops


def pages(declared, atoms, nodes, edges, first=None, follow=None):
    """Every page until none is left: [(answer, nodes so far)] - from `first`, a page already walked, when given. The
    paused walk stays in this process (총괄 54f7edfdb): its cursor is read from where it is kept, beside each page."""
    out, held = [], set()
    answer = first or walk(declared, atoms, None, nodes, edges, follow)
    for _ in range(200):
        held |= {node["id"] for node in answer["nodes"]}
        out.append((answer, set(held)))
        if answer["more"]["resume"] is None:
            return out
        CURSORS[id(answer)] = ledger_subgraph._KEPT[answer["more"]["resume"]["walk"]]["state"]["cursor"]
        # what a client hands back is what went over the wire
        answer = walk(declared, atoms, json.loads(json.dumps(answer["more"]["resume"])), nodes, edges, follow)
    raise AssertionError("still more after 200 pages")


# the route hands [] when no follow was asked (응용 10-12: every type said complete on a cut page)
@pytest.mark.parametrize("follow", [None, []], ids=["no follow", "the route's empty follow"])
def test_every_cap_paged_and_merged_is_the_walk_without_caps(declared, monkeypatch, follow):
    whole = walk(declared, ATOMS, follow=follow)
    assert whole["more"]["resume"] is None and not whole["truncated"]["reason"], whole["truncated"]
    every = {node["id"]: _kind(node) for node in whole["nodes"]}
    joined = {edge["id"] for edge in whole["edges"]}
    ranked, trails = _ranked(whole)
    assert any(r[0] for r, _e in ranked.values()) and any(r[1] for r, _e in ranked.values()), "canary: both sides reach"
    assert all(all(p) for _ids, preds in trails.values() for p in preds[1:]), "canary: the one walk's hops are named"
    assert explorer.entity_id("recipe", {"r": "R"}) in every, "canary: R is reached only through S at one departure"
    assert explorer.entity_id("operator", {"o": "O1"}) in every, "canary: O1 is reached only by the static seed's step"

    wrong, said_whole_early, over_caps, deepest_read, most, ranked_wrong, spent_again = [], [], [], 0, 0, [], []
    big_token = []
    rank_wrong = []
    for claims in range(1, 13):
        monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", claims)
        for nodes in (10, 13, 400):                              # the walk's own floors: 10 nodes, 20 edges
            for edges in (20, 6000):
                run = pages(declared, ATOMS, nodes, edges, follow=follow)
                most = max(most, len(run))
                got = {node["id"] for answer, _held in run for node in answer["nodes"]}
                drawn = {edge["id"] for answer, _held in run for edge in answer["edges"]}
                if got != set(every) or drawn != joined:
                    wrong.append((claims, nodes, edges, sorted(set(every) - got), sorted(got - set(every)),
                                  len(joined - drawn), len(drawn - joined)))
                # an atom cap alone: no node read whole is read again, so the pages read what the one walk read
                spent = sum(answer["walk"]["claims_scanned"] for answer, _held in run)
                if (nodes, edges) == (400, 6000) and spent != whole["walk"]["claims_scanned"]:
                    spent_again.append((claims, spent, whole["walk"]["claims_scanned"]))
                # the screen merges the pages' ranked rows by id, a later page's over an earlier one's
                merged, merged_trails = {}, {}
                for answer, _held in run:
                    one, its = _ranked(answer)
                    merged.update(one)
                    merged_trails.update(its)
                # every hop after the seed names what joins it (응용 18766: [] on a hop an earlier page drew), and a
                # trail that took the one walk's path says the one walk's predicates on it
                unnamed = [key for key, (_ids, preds) in merged_trails.items() if not all(preds[1:])]
                differ = [key for key, (ids, preds) in merged_trails.items()
                          if key in trails and trails[key][0] == ids and trails[key][1] != preds]
                if unnamed or differ:
                    ranked_wrong.append((claims, nodes, edges, "hops", len(unnamed), len(differ)))
                # 총괄 10-12: a page's rank · top · tied · incomparable and its top_set are among every node reached so
                # far - its own rows and the pages' before - not among its own rows alone
                # 총괄 54f7edfdb: a page is a delta - top_set came in, top_set_left went out; read in turn, the top set
                so_far, top_now = {}, set()
                for answer, _held in run:
                    rows = answer["propagation"]["ranked"]
                    so_far.update({row["id"]: row["reach"] for row in rows})
                    top_now = ((top_now - set(answer["propagation"].get("top_set_left") or ()))
                               | set(answer["propagation"]["top_set"]))
                    if not rows:
                        continue
                    layers = ledger_subgraph._rank_layers([{"id": n, "reach": r} for n, r in so_far.items()])
                    expect = {it["id"]: (it["rank"], it["rank"] == 1, it["tied"], it["incomparable"])
                              for layer in layers for it in layer}
                    if (any((row["rank"], row["top"], row["tied"], row["incomparable"]) != expect[row["id"]]
                            for row in rows)
                            or sorted(top_now) != sorted(it["id"] for it in layers[0])):
                        rank_wrong.append((claims, nodes, edges))
                        break
                if merged != ranked:
                    ranked_wrong.append((claims, nodes, edges, len(set(ranked) - set(merged)),
                                         sum(1 for n in merged if n in ranked and merged[n] != ranked[n])))
                for answer, held in run:
                    deepest_read = max(deepest_read, int((CURSORS.get(id(answer)) or {}).get("read") or 0))
                    # the token is a key, whatever the walk has reached (총괄 54f7edfdb: 10 MB at page 47 before)
                    if len(json.dumps(answer["more"]["resume"])) > TOKEN_BYTES:
                        big_token.append((claims, nodes, edges, len(json.dumps(answer["more"]["resume"]))))
                    for kind, said in answer["more"]["reach"].items():
                        missing = {n for n, k in every.items() if k == kind} - held
                        if said["complete"] and missing:
                            said_whole_early.append((claims, nodes, edges, kind, len(missing)))
                    limits = answer["limits"]
                    if (answer["walk"]["claims_scanned"] > limits["claims"] or len(answer["nodes"]) > limits["nodes"]
                            or len(answer["edges"]) > limits["edges"]):
                        over_caps.append((claims, nodes, edges))
    assert most >= 3 and deepest_read >= 1, "canary: pages were cut, and one stopped past a group's first read"
    assert wrong == [], wrong
    assert said_whole_early == [], said_whole_early
    assert over_caps == [], over_caps
    assert big_token == [], big_token
    assert ranked_wrong == [], ranked_wrong
    assert spent_again == [], spent_again
    assert rank_wrong == [], rank_wrong


def test_an_atom_written_after_the_first_page_is_in_no_page_after_it(declared, monkeypatch):
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 3)
    first = walk(declared, ATOMS, nodes=400)
    assert first["more"]["resume"] is not None, "canary: the first page was cut"
    time.sleep(0.01)                                            # the new atom's uuid7 falls after the first page
    later = ATOMS + [_atom("die", die("D4"), "linked", "die", die("NEW"), atom_id=str(uuid7()))]
    new = explorer.entity_id("die", die("NEW"))
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 6000)
    assert new in {node["id"] for node in walk(declared, later)["nodes"]}, "canary: a walk now reaches it"
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 3)
    first_as_of = ledger_subgraph._KEPT[first["more"]["resume"]["walk"]]["state"]["as_of"]    # kept with the walk
    run = pages(declared, later, 400, 6000, first=first)
    assert len(run) >= 2
    assert {answer["more"]["as_of"] for answer, _held in run[1:]} == {first_as_of}
    assert new not in run[-1][1]


def test_a_seed_whose_newest_twenty_thousand_atoms_lead_elsewhere_reaches_the_collected_type_on_page_four(tmp_path):
    """총괄 10-12 (소유자 「원자 수만 개 묶여 있는 노드를 시작으로 걸으면 아무것도 안 나오는데」): the static seed HUB holds
    20,000 newer atoms to dies and 5 older ones to recipes; collect recipe. The first page's read is cut on the dies and
    says recipe is not complete; the fourth page reaches the five recipes."""
    path = tmp_path / "ledger_config.json"
    path.write_text(json.dumps({"vocabulary": {"measures@1": _predicate("die", "quantity"),
                                               "uses@1": _predicate("recipe", "quantity")}}), encoding="utf-8")
    ledger_subgraph.reset_declaration_cache()
    atoms = ([_atom("recipe", {"r": "R%d" % k}, "uses", "quantity", {"q": "HUB"}) for k in range(5)]
             + [_atom("die", die("H%d" % k), "measures", "quantity", {"q": "HUB"}) for k in range(20000)])
    lookup, answers, resume = ledger_subgraph.InMemoryEvidenceLookup(atoms), [], None
    while len(answers) < 10:
        answers.append(ledger_subgraph.subgraph(
            explorer.entity_id("quantity", {"q": "HUB"}), lookup, declaration_paths=(str(path),), hops=2,
            static_types=["quantity", "recipe"], collect=["recipe"], resume=resume, resumable=True))
        resume = answers[-1]["more"]["resume"]
        if resume is None:
            break
    ledger_subgraph.reset_declaration_cache()
    assert [len(a["nodes"]) for a in answers] == [0, 0, 0, 5]
    assert [a["more"]["reach"]["recipe"]["complete"] for a in answers] == [False, False, False, True]


def test_a_continued_pages_rows_take_their_paths_from_the_seeds(declared, monkeypatch):
    """총괄 10-12: the rows a continued page answers (`format=rows`) read their path from the seed that reached each
    node, as its ranking does - the pages' (node, seed) rows merged = the one walk's, every path starting at its seed."""
    def rows(answer):
        lines = answer["rows"].splitlines()
        header = lines[1].split("\t")
        return [dict(zip(header, line.split("\t"))) for line in lines[2:]]

    def walk_rows(atoms, resume=None):
        return ledger_subgraph.subgraph(
            SEEDS, ledger_subgraph.InMemoryEvidenceLookup(atoms), declaration_paths=declared, hops=2, backbone_hops=2,
            static_types=["quantity", "recipe"], static_follow=["leads_to"], expand=EXPAND, resume=resume, resumable=True, rows=True,
            entities={})

    whole = {(row["id"], row["seed"]) for row in rows(walk_rows(ATOMS)) if row["seed"]}
    monkeypatch.setattr(ledger_subgraph, "MAX_CLAIM_SCAN", 3)
    merged, answer, pages_walked = set(), walk_rows(ATOMS), 1
    while True:
        for row in rows(answer):
            if row["seed"]:
                assert row["path_ids"].split(ledger_subgraph.PATH_SEPARATOR)[0] == row["seed"], row
                merged.add((row["id"], row["seed"]))
        if answer["more"]["resume"] is None:
            break
        answer, pages_walked = walk_rows(ATOMS, json.loads(json.dumps(answer["more"]["resume"]))), pages_walked + 1
    assert pages_walked >= 3, "canary: the walk was paged"
    assert merged == whole, (sorted(whole - merged)[:5], sorted(merged - whole)[:5])

