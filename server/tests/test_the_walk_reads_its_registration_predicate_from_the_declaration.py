# -*- coding: utf-8 -*-
"""S-263. The walk asks the declaration which predicate a registration is written with.

🔴 IT SPELLED THE WORD ITSELF: `follow=["register"]`. 「코드에 도메인 낱말이 없다」 - an
installation whose registration predicate is named anything else got every node's
`attributes` permanently empty, and NOTHING said so, which is the same silence S-52-i
removed one layer up (「this entity carries no values」 and 「this walk never asked」
rendering the same).

⚠️ THE DECLARATION ALREADY ANSWERED IT. A sentence the vocabulary gives NO OBJECT says
nothing about an object and everything about its SUBJECT - `roleframe` says exactly that
where it compiles one - and an entity's values ride in those atoms' qualifiers. So the
predicate is DERIVED, the way `_static_types` and `_predicate_cardinalities` are, and
every fixture below names it something OTHER than 「register」: a test that used the real
word could not tell the derivation from the literal it replaced.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from ledger import explorer, trace_router                                        # noqa: E402
from ledger_api import ledger_subgraph                                           # noqa: E402

NOW = datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc)
EVENT = str(uuid.UUID(int=900))

#: The declaration of an installation that does NOT use the word this code used to hold.
DECLARED = {
    "entities": {"wafer@1": {}, "quantity@1": {}},
    "vocabulary": {
        # 🔴 THE ONE WITH NO OBJECT. Named `enrolled`, so the derivation cannot pass by
        # returning the literal it replaced.
        "enrolled@1": {"subjects": ["wafer@1"], "object": {"kind": "none"}},
        "measures@1": {"subjects": ["wafer@1"],
                       "object": {"kind": "entity_ref", "types": ["quantity@1"]}},
        "counted@1": {"subjects": ["wafer@1"], "object": {"kind": "value"}},
    },
}


def _edge_atom():
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=901)), subject_type="wafer", subject_keys={"wafer": "W1"},
        predicate="measures", object_kind="entity_ref",
        object_payload={"type": "quantity", "keys": {"quantity": "Q"}, "qualifiers": {}},
        occurred_at=NOW, source_who="fixture", source_translator_ver="v1",
        source_raw_ref="row:901", supersedes=None, source_event_id=EVENT,
        source_event_state="source_record")


def _registration_atom(predicate):
    """An objectless atom carrying the subject's own value, under whatever word."""
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=902)), subject_type="wafer", subject_keys={"wafer": "W1"},
        predicate=predicate, object_kind=None,
        object_payload={"qualifiers": {"product": "P7"}},
        occurred_at=NOW, source_who="fixture", source_translator_ver="v1",
        source_raw_ref="row:902", supersedes=None, source_event_id=EVENT,
        source_event_state="source_record")


class RecordingLookup:
    """Keeps the `follow` of every sweep, because the WORD ASKED FOR is the subject here.

    Asserting on the returned graph alone cannot tell 「asked for the right predicate」 from
    「asked for everything and kept the right rows」 - the nodes come back the same either
    way. The argument is what separates them.
    """

    def __init__(self, atoms):
        self.inner = ledger_subgraph.InMemoryEvidenceLookup(atoms)
        self.follows = []

    def claims_for_entities(self, entities, direction, limit, *, follow=None):
        self.follows.append(None if follow is None else tuple(follow))
        return self.inner.claims_for_entities(entities, direction, limit, follow=follow)

    def __getattr__(self, name):
        return getattr(self.inner, name)


# ---------------------------------------------------------------------------
# 🔴 ⓐ - the word comes out of the declaration
# ---------------------------------------------------------------------------

def test_the_registration_predicate_is_the_one_the_declaration_gives_no_object(monkeypatch):
    """🔴 THE GATE. One vocabulary entry of each object kind, so the derivation cannot
    pass by returning everything or the first thing it sees."""
    from ledger import config as ledger_config
    monkeypatch.setattr(ledger_config, "load", lambda *a, **k: DECLARED)

    assert trace_router._self_describing_predicates() == {"enrolled"}


def test_an_unreadable_declaration_names_no_predicate_rather_than_guessing_one(monkeypatch):
    """⚠️ AND IT DOES NOT FALL BACK TO A WORD. A guess would be the literal coming back in
    through the error path - correct on the box it was written for and silently wrong
    everywhere else, which is the defect, not the repair."""
    from ledger import config as ledger_config

    def unreadable(*args, **kwargs):
        raise RuntimeError("declaration unreadable")

    monkeypatch.setattr(ledger_config, "load", unreadable)
    assert trace_router._self_describing_predicates() == set()


# ---------------------------------------------------------------------------
# 🔴 ⓑ - the walk asks for what it was handed, and the route hands it over
# ---------------------------------------------------------------------------

def test_the_sweep_asks_for_the_predicate_it_was_handed():
    """🔴 「착지는 배선이 아니다」의 반대쪽 절반: the derivation is worth nothing unless the
    query carries it. The subject registers under `enrolled`, and its value arrives."""
    lookup = RecordingLookup([_edge_atom(), _registration_atom("enrolled")])
    seed = explorer.entity_id("wafer", {"wafer": "W1"})

    body = ledger_subgraph.subgraph(seed, lookup, hops=1,
                                    registration_follow={"enrolled"})

    assert ("enrolled",) in lookup.follows, lookup.follows
    assert not any(call == ("register",) for call in lookup.follows), lookup.follows
    node = next(n for n in body["nodes"] if n["id"] == seed)
    assert node.get("attributes") == {"product": "P7"}


def test_a_walk_handed_no_predicate_sweeps_nothing_rather_than_a_word_of_its_own():
    """⛔ THE REGRESSION LINE FOR THE LITERAL. If the module kept a word of its own, a
    caller that named none would still fetch registrations - and this box, whose word IS
    「register」, would never notice the difference."""
    lookup = RecordingLookup([_edge_atom(), _registration_atom("register")])
    seed = explorer.entity_id("wafer", {"wafer": "W1"})

    body = ledger_subgraph.subgraph(seed, lookup, hops=1)

    assert not any(call == ("register",) for call in lookup.follows), lookup.follows
    node = next(n for n in body["nodes"] if n["id"] == seed)
    assert "attributes" not in node, node


def test_the_route_hands_the_walk_what_it_derived(monkeypatch):
    """⚠️ MEASURED AT THE SEAM, NOT AT EITHER END. `_evidence_graph` is the ONE caller of
    `subgraph`, so a derivation that never reaches it is the 「배선 0」 shape - and the two
    halves can only disagree here."""
    from ledger import config as ledger_config
    from ledger import trace as ledger_trace

    monkeypatch.setattr(ledger_config, "load", lambda *a, **k: DECLARED)
    monkeypatch.setattr(ledger_trace, "relation_exists", lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state", lambda *a, **k: [])
    handed = {}
    monkeypatch.setattr(ledger_subgraph, "subgraph",
                        lambda *args, **kwargs: handed.update(kwargs) or {})

    trace_router._evidence_graph(
        object(), node_id=explorer.entity_id("wafer", {"wafer": "W1"}), hops=1,
        direction="both", node_limit=10, edge_limit=10)

    assert handed["registration_follow"] == {"enrolled"}
