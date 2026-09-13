# -*- coding: utf-8 -*-
"""S-98 (ruling 208). A walk can be asked for one interval, and says what it left out.

🔴 THE FILTER ALONE WOULD HAVE BEEN A DEFECT. Atoms outside the interval are simply not
fetched, so without a number beside it a narrowed walk and an empty one render identically -
the class this repository has already had to name in five other shapes ("a cut is not an
absence"). So the count is not decoration next to the filter; it is the half that keeps the
filter honest, and both land together.

⛔ AND THE KEY IS ABSENT, NOT ZERO, when no interval was asked for. A 0 says "the question
was put and nothing was excluded"; absence says "the question was not put". A reader cannot
recover that difference from a zero.
"""
from datetime import datetime, timedelta, timezone
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer                                               # noqa: E402
from ledger_api import ledger_subgraph                               # noqa: E402

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=30)
SEED = explorer.entity_id("Lot", {"lot": "A"})


def atom(number, subject, target, when):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type="Lot",
        subject_keys={"lot": subject}, predicate="derived_from",
        object_kind="entity_ref",
        object_payload={"type": "Lot", "keys": {"lot": target}, "qualifiers": {}},
        occurred_at=when, source_who="fixture", source_translator_ver="v1",
        source_raw_ref=f"row:{number}", supersedes=None,
        source_event_id=str(uuid.UUID(int=900 + number)),
        source_event_state="source_record")


def fixture():
    """One edge inside the window and two outside it, all reachable from the same seed."""
    return [atom(1, "A", "RECENT", NOW),
            atom(2, "A", "OLD_ONE", OLD),
            atom(3, "A", "OLD_TWO", OLD - timedelta(days=1))]


def walk(**interval):
    lookup = ledger_subgraph.InMemoryEvidenceLookup(fixture(), **interval)
    return ledger_subgraph.subgraph(SEED, lookup, hops=3, direction="both")


def labels(answer):
    return {node["label"] for node in answer["nodes"]}


def test_an_interval_keeps_the_edges_inside_it_and_drops_the_rest():
    """🔴 THE HEADLINE. `since` selects on the ATOM's instant, so the two old edges are
    never fetched and the nodes they would have carried never appear."""
    inside = walk(since=NOW - timedelta(hours=1))

    assert "RECENT" in labels(inside)
    assert "OLD_ONE" not in labels(inside) and "OLD_TWO" not in labels(inside)


def test_the_number_left_out_is_a_count_and_not_a_flag():
    """⛔ ruling 208 REFUSED A BOOLEAN. 「how many did I not see」 is the question an
    operator asks before deciding whether their window was too narrow, and a flag cannot
    answer it. Two edges are outside, so the answer says two."""
    answer = walk(since=NOW - timedelta(hours=1))

    assert answer["truncated"]["interval_excluded"] == 2


def test_a_walk_with_no_interval_has_no_such_key_at_all():
    """⛔ ABSENT, NOT ZERO. A 0 here would say 「asked, and nothing was excluded」 about a
    request that never asked - and every walk in the product before today is that request."""
    assert "interval_excluded" not in walk()["truncated"]


def test_the_seed_is_reached_whatever_the_interval_says():
    """⚠️ THE INTERVAL FILTERS EDGES, NOT THE SEED. A window that excludes everything
    must still answer with the node the caller asked about - otherwise a narrow window is
    indistinguishable from a bad id, and the operator debugs the wrong thing."""
    empty = walk(since=NOW + timedelta(days=1))

    assert empty["nodes"], "the seed must survive an interval that excludes every edge"
    assert labels(empty) == {"A"}
    assert empty["truncated"]["interval_excluded"] == 3


def test_until_is_exclusive_and_since_is_inclusive():
    """One spelling of a half-open interval, so two adjacent windows neither overlap nor
    leave a gap. `until=NOW` must therefore NOT carry the edge that happened at NOW."""
    before = walk(until=NOW)

    assert "RECENT" not in labels(before)
    assert {"OLD_ONE", "OLD_TWO"} <= labels(before)
    assert before["truncated"]["interval_excluded"] == 1

    at = walk(since=NOW)
    assert "RECENT" in labels(at)


# ------------------------------------------------------------------ the route's refusals

def test_a_bound_that_is_not_a_time_is_refused_by_name(monkeypatch):
    """⛔ REFUSED, NOT IGNORED. A dropped bound answers the WHOLE history to a caller who
    asked for a window, and they read that as 「there is nothing outside my window」 - the
    same silent-zero shape the scope refusal exists to stop."""
    from ledger import trace_router
    from fastapi import HTTPException
    import pytest

    monkeypatch.setattr(trace_router.trace, "relation_exists",
                        lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state",
                        lambda *a, **k: [])

    with pytest.raises(HTTPException) as raised:
        trace_router.evidence_subgraph(
            node_id=SEED, hops=4, direction="both", node_limit=100, edge_limit=200,
            since="yesterday", until=None, positive=None, negative=None,
            follow=None, backbone_hops=0, db=None)
    assert raised.value.status_code == 422
    assert raised.value.detail["reason"] == "interval_not_iso8601"
    assert raised.value.detail["argument"] == "since"


def test_a_window_that_cannot_contain_anything_is_refused(monkeypatch):
    """`since >= until` selects nothing at all, and answering it with an empty graph would
    look exactly like a seed with no evidence."""
    from ledger import trace_router
    from fastapi import HTTPException
    import pytest

    monkeypatch.setattr(trace_router.trace, "relation_exists",
                        lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state",
                        lambda *a, **k: [])

    with pytest.raises(HTTPException) as raised:
        trace_router.evidence_subgraph(
            node_id=SEED, hops=4, direction="both", node_limit=100, edge_limit=200,
            since="2026-09-09T12:00:00Z", until="2026-09-01T00:00:00Z",
            positive=None, negative=None, follow=None, backbone_hops=0, db=None)
    assert raised.value.detail["reason"] == "interval_empty"


def test_a_naive_bound_is_read_as_utc_rather_than_refused():
    """⚠️ `?since=2026-09-01` is the ordinary request. The ledger stores `timestamptz`, so a
    bound with no zone has to mean something, and every instant this module renders is UTC."""
    from ledger import trace_router

    assert trace_router._instant_arg("2026-09-01") == datetime(
        2026, 9, 1, tzinfo=timezone.utc)
    assert trace_router._instant_arg("2026-09-01T00:00:00Z") == datetime(
        2026, 9, 1, tzinfo=timezone.utc)


# ------------------------------------------------- the SQL half, which pg cannot score here

def sql_issued(**interval):
    """Every statement the SQL lookup WOULD send, without a database.

    ⚠️ THIS SCORES CONSTRUCTION, NOT EXECUTION. Every `pg_engine` test skips in this box, so
    the interval's SQL is otherwise measured by nothing at all - and "the clause was never
    added" is exactly the failure that would leave a narrowed walk answering the whole
    history while these in-memory cases stayed green.
    """
    lookup = ledger_subgraph.SqlEvidenceLookup(None, **interval)
    seen = []

    def _capture(sql, params):
        seen.append((" ".join(sql.split()), dict(params)))
        # Empty on purpose: this case is about WHICH statements are built, and rows here
        # would have to be whole atoms for the fetch and a bare count for the census.
        return []

    lookup._execute = _capture
    lookup.claims_for_entities([("Lot", {"lot": "A"})], "both", 10)
    return lookup, seen


def test_the_interval_reaches_the_statement_and_the_census_is_a_second_query():
    lookup, seen = sql_issued(since=OLD, until=NOW)

    assert len(seen) == 2, "one fetch and one census, per hop"
    fetch, census = seen
    assert "e.occurred_at >= %(since)s" in fetch[0]
    assert "e.occurred_at < %(until)s" in fetch[0]
    assert fetch[1]["since"] == OLD and fetch[1]["until"] == NOW

    # ⛔ THE COMPLEMENT, BUILT FROM THE SAME TWO BOUNDS. A census asking anything else would
    # report a number about a different set of rows than the walk actually skipped.
    assert "SELECT count(*)" in census[0]
    assert "(e.occurred_at < %(since)s OR e.occurred_at >= %(until)s)" in census[0]
    assert lookup.interval_excluded == 0


def test_without_an_interval_no_clause_and_no_second_query_are_issued():
    """⚠️ THE COST IS NOT PAID BY REQUESTS THAT DID NOT ASK. Ruling 208 accepted one extra
    query per hop BECAUSE it runs only for an interval; a census on every walk would be a
    price nobody asked for on the request path."""
    lookup, seen = sql_issued()

    assert len(seen) == 1, f"a walk with no interval must issue one query per hop: {seen}"
    assert "occurred_at >=" not in seen[0][0] and "occurred_at <" not in seen[0][0]
    assert lookup.interval_excluded is None
