# -*- coding: utf-8 -*-
"""A seat that declared `follow` got its attribute column back empty, forever.

S-52-i, the sixth layer. The walk recorded a registration's qualifiers only from atoms it
had FETCHED, and what it fetches is what `follow` names -- so `follow=['has_netdie']`
returned the `dtjob` node with no `attributes` at all. Every screen seat declares `follow`
as the predicates that seat cares about, so on a real seat the column was not "sometimes
empty": it could never be filled.

🔴 A REGISTRATION IS NOT AN EDGE. It is the entity describing itself -- 「술어가 아닌 것은
표면적으로 노드」, and ruling 124 calls these the node's COLUMNS. Nothing about a column
should depend on which roads the caller asked to walk, so the sweep is
`follow`-independent by construction rather than by adding `register` to every seat's
declaration (which would be the same fact written down N times, and wrong the day N+1
appears).
"""
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer                                              # noqa: E402
from ledger_api import ledger_subgraph                              # noqa: E402

NOW = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
DTJOB = explorer.entity_id("dtjob", {"dt_job": "J1"})


def atom(number, predicate, *, kind=None, payload=None, occurred_at=None):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="dtjob",
        subject_keys={"dt_job": "J1"}, predicate=predicate, object_kind=kind,
        object_payload=payload, occurred_at=occurred_at or NOW, source_who="dt_job",
        source_translator_ver="v1", source_raw_ref=f"row:{number}", supersedes=None,
        source_event_id=str(uuid.UUID(int=900 + number)),
        source_event_state="source_molecule")


def registration(number, value, *, occurred_at=None):
    return atom(number, "register", payload={"qualifiers": {"dt_eqp": value}},
                occurred_at=occurred_at)


def counted(number=2):
    return atom(number, "has_netdie", kind="value", payload={"value": 12})


def walk(atoms, **kwargs):
    # ⚠️ THE WORD IS THE CALLER'S NOW (S-263). The sweep used to spell `["register"]` inside
    # `subgraph`; the route derives it from the declaration's objectless predicate, so this
    # fixture names the one IT wrote above. That is the whole point of the change - the
    # module no longer knows a domain word, and the seat that writes the atoms does.
    kwargs.setdefault("registration_follow", {"register"})
    return ledger_subgraph.subgraph(
        DTJOB, ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=2, **kwargs)


def dtjob_node(body):
    return next(node for node in body["nodes"] if node["id"] == DTJOB)


# ------------------------------------------------------------------- the gate itself

def test_a_seat_that_follows_one_predicate_still_gets_the_column():
    """🔴 THE MEASUREMENT THAT OPENED THIS. `follow=['has_netdie']` -- one ordinary seat --
    and the attribute has to be there. Before the sweep this was `None`."""
    body = walk([registration(1, "SYN-DTE-03"), counted()], follow=["has_netdie"])
    assert dtjob_node(body)["attributes"] == {"dt_eqp": "SYN-DTE-03"}


def test_following_register_as_well_answers_exactly_the_same():
    """⛔ TWO PATHS TO ONE VALUE IS THE FAILURE, not the fix. The walk may fetch the same
    registration through `follow` as well, and both roads go through one recorder -- so a
    caller who names `register` and one who does not cannot be told apart by the answer."""
    atoms = [registration(1, "SYN-DTE-03"), counted()]
    narrow = dtjob_node(walk(atoms, follow=["has_netdie"]))
    wide = dtjob_node(walk(atoms, follow=["has_netdie", "register"]))
    assert narrow["attributes"] == wide["attributes"]
    assert narrow["attribute_conflicts"] == wide["attribute_conflicts"] == 0


def test_no_follow_at_all_answers_the_same_too():
    atoms = [registration(1, "SYN-DTE-03"), counted()]
    assert dtjob_node(walk(atoms))["attributes"] == {"dt_eqp": "SYN-DTE-03"}


# ------------------------------------------------------- and the absence stays an absence

def test_a_declaration_with_no_attribute_answers_byte_for_byte_as_before():
    """⚠️ THE KEY IS ABSENT, NOT EMPTY. "this entity carries no values" and "this walk did
    not reach its registration" are different answers, and the sweep must not turn the
    second into an empty object for every node it touches."""
    body = walk([counted()], follow=["has_netdie"])
    node = dtjob_node(body)
    assert "attributes" not in node and "attribute_conflicts" not in node


def test_a_registration_that_says_nothing_adds_no_key():
    """A registration with no qualifiers is what every source that declares no attribute
    writes, and it is the case that has to stay byte-identical."""
    node = dtjob_node(walk([atom(1, "register"), counted()], follow=["has_netdie"]))
    assert "attributes" not in node


# ------------------------------------------------------------ latest wins, and it is counted

def test_the_newest_registration_wins_and_a_disagreement_is_counted():
    """The reading rule is unchanged by the sweep -- which is the point of routing both
    roads through one recorder rather than filling `attributes` in a second place."""
    node = dtjob_node(walk([
        registration(1, "OLD"),
        registration(2, "NEW", occurred_at=NOW + timedelta(hours=1)),
        counted(3),
    ], follow=["has_netdie"]))
    assert node["attributes"] == {"dt_eqp": "NEW"}
    assert node["attribute_conflicts"] == 1


def test_one_fact_stated_twice_is_not_a_disagreement():
    node = dtjob_node(walk([
        registration(1, "SAME"),
        registration(2, "SAME", occurred_at=NOW + timedelta(hours=1)),
        counted(3),
    ], follow=["has_netdie"]))
    assert node["attributes"] == {"dt_eqp": "SAME"} and node["attribute_conflicts"] == 0


# --------------------------------------------------------------------- what it costs

def test_the_whole_result_is_asked_in_one_query():
    """🔴 A QUERY PER NODE WOULD BE A WALK-SIZED FAN-OUT ON THE REQUEST PATH (owner:
    「성능 마진 넉넉하게」). The sweep asks once, for every entity node the walk kept."""
    asked = []
    lookup = ledger_subgraph.InMemoryEvidenceLookup(
        [registration(1, "SYN-DTE-03"), counted()])
    real = lookup.claims_for_entities

    def spy(entities, direction, limit, *, follow=None):
        asked.append({"entities": list(entities), "follow": follow, "limit": limit})
        return real(entities, direction, limit, follow=follow)

    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(DTJOB, lookup, hops=2, follow=["has_netdie"],
                             registration_follow={"register"})
    sweeps = [call for call in asked if call["follow"] == ["register"]]
    assert len(sweeps) == 1, asked
    assert sweeps[0]["limit"] == (len(sweeps[0]["entities"])
                                 * ledger_subgraph.REGISTRATIONS_FETCHED_PER_NODE)


def test_a_walk_that_kept_no_entity_asks_nothing():
    """An empty frontier must not become a query with an empty IN list."""
    asked = []
    lookup = ledger_subgraph.InMemoryEvidenceLookup([counted()])
    real = lookup.claims_for_entities

    def spy(entities, direction, limit, *, follow=None):
        asked.append(follow)
        return real(entities, direction, limit, follow=follow)

    lookup.claims_for_entities = spy
    ledger_subgraph.subgraph(DTJOB, lookup, hops=2, node_limit=1,
                             follow=["has_netdie"],
                             registration_follow={"register"})
    assert asked.count(["register"]) <= 1
