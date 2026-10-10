# -*- coding: utf-8 -*-
"""The time page (총괄 10-10 B): `/subgraph` with one of around / earlier / later answers ONE node's
atoms along ONE predicate on ONE side, in time order, a page at a time - the walk widened to time.
Each point is the walk's own edge (`_claim_edge`); the envelope is the walk's names plus `page`.
Through the route, against the product's own `ensure_schema` in a scratch schema.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer, schema, trace_router  # noqa: E402
from ledger.envelope import ROW_COLUMNS  # noqa: E402

pytestmark = pytest.mark.pg

T = datetime(2026, 5, 3, 2, 0, tzinfo=timezone.utc)
Q = ("quantity", {"quantity": "p"})
TOOL = ("tool", {"tool": "T1"})
ENTITIES = {"quantity@1": {"keys": ["quantity"]}, "wafer@1": {"keys": ["wafer"]},
            "tool@1": {"keys": ["tool"]}, "recipe@1": {"keys": ["recipe"]}}
VOCABULARY = {"measures@1": {}, "set_to@1": {"cardinality": "one"}}


def _atom(subject, predicate, obj, at, basis=None, value=None):
    """`obj`: (type, keys) for an entity_ref, or None for a value atom carrying `value`."""
    payload = ({"type": obj[0], "keys": obj[1], "qualifiers": {"value": value}} if obj
               else {"value": value})
    return {"id": str(uuid.uuid4()), "subject_type": subject[0], "subject_keys": json.dumps(subject[1]),
            "predicate": predicate, "object_kind": "entity_ref" if obj else "value",
            "object_payload": json.dumps(payload), "occurred_at": at, "source_who": "src",
            "source_translator_ver": "v1", "source_raw_ref": str(uuid.uuid4()), "supersedes": None,
            "source_event_id": str(uuid.uuid4()), "source_event_state": "source_molecule",
            "occurred_at_basis": basis}


#: ten wafers measure Q at hours 0..8 - two of them at the SAME instant (5 h); one more whose time
#: is not an event time; the tool's `one` predicate set twice, and once to a value
HOURS = [0, 1, 2, 3, 4, 5, 5, 6, 7, 8]
POINTS = [_atom(("wafer", {"wafer": "W%02d" % n}), "measures", Q, T + timedelta(hours=h), value=float(n))
          for n, h in enumerate(HOURS)]
INGESTED = _atom(("wafer", {"wafer": "W99"}), "measures", Q, T + timedelta(hours=4, minutes=30),
                 basis=schema.NOT_AN_EVENT_BASIS, value=99.0)
OLD = _atom(TOOL, "set_to", ("recipe", {"recipe": "R1"}), T)
NEW = _atom(TOOL, "set_to", ("recipe", {"recipe": "R2"}), T + timedelta(hours=1))
VALUE = _atom(TOOL, "set_to", None, T + timedelta(minutes=30), value=3)
ATOMS = POINTS + [INGESTED, OLD, NEW, VALUE]
IN_ORDER = [row["id"] for row in sorted(POINTS, key=lambda row: (row["occurred_at"], uuid.UUID(row["id"])))]


@pytest.fixture(scope="module")
def engine():
    from conftest import _declared_as_test_database, _resolve_pg_test_url
    from tests.support.isolated_pg import scratch_connect_args, scratch_schema
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool
    from ledger import store as ledger_store

    url, reason = _resolve_pg_test_url()
    if url is None:
        pytest.skip(reason)
    scratch = scratch_schema("assy_pytest_time_page")
    with _declared_as_test_database(url):
        built = create_engine(url, poolclass=NullPool, connect_args=scratch_connect_args(scratch))
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
                conn.execute(text('CREATE SCHEMA "%s"' % scratch))
        except OperationalError as exc:
            pytest.skip("PostgreSQL is not reachable: %s" % str(exc).strip().splitlines()[0])
        try:
            store = ledger_store.LedgerStore(built)
            store.ensure_schema()
            raw = built.raw_connection()
            try:
                store.ensure_partitions(raw, [T])
                with raw.cursor() as cursor:
                    for atom in ATOMS:
                        cursor.execute(
                            f"INSERT INTO {schema.LEDGER_TABLE} ({', '.join(ROW_COLUMNS)}) "
                            f"VALUES ({', '.join(['%s'] * len(ROW_COLUMNS))})",
                            [atom[c] for c in ROW_COLUMNS])
                raw.commit()
            finally:
                raw.close()
            yield built
        finally:
            with admin.begin() as conn:
                conn.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % scratch))
            built.dispose()
            admin.dispose()


@pytest.fixture
def get(engine, monkeypatch):
    """GET /api/ledger/subgraph through FastAPI - its own Query parsing, defaults and bounds."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from database.database import get_db
    from ledger import config as _config

    monkeypatch.setattr(_config, "load", lambda *_a, **_k: {"entities": ENTITIES, "vocabulary": VOCABULARY})
    app = FastAPI()
    app.include_router(trace_router.router)

    def db():
        session = Session(bind=engine)
        try:
            yield session
        finally:
            session.close()
    app.dependency_overrides[get_db] = db
    client = TestClient(app)

    def call(node=Q, **params):
        params.setdefault("id", explorer.entity_id(*node))
        response = client.get("/api/ledger/subgraph",
                              params={name: value for name, value in params.items() if value is not None})
        return response.status_code, response.json()
    return call


def _page(get, **params):
    params = {"follow": "measures", "direction": "incoming", "hops": 1, **params}
    status, body = get(**params)
    assert status == 200, body
    return body


def _claims(body):
    return [edge["claim_id"] for edge in body["edges"]]


def _iso(at):
    return at.isoformat()


def test_a_walk_that_asks_no_page_is_the_walk(get):
    """First cell (총괄): no around / earlier / later - the walk, no `page` key. The direct call
    leaves FastAPI's `Query` sentinels in the three slots; they must not read as asked."""
    status, body = get(follow="measures", direction="incoming", hops=1)
    assert status == 200 and "page" not in body and body["walk"]["mode"] == "evidence_graph"
    assert trace_router._time_page_asked(
        {"around": trace_router.Query(None), "earlier": trace_router.Query(None),
         "later": trace_router.Query(None)}, trace_router.Query(1000),
        follow=None, follow_keys={}, direction="both", hops=12, given=[]) is None


def test_around_is_the_nearest_points_on_both_sides_in_time_order(get):
    body = _page(get, around=_iso(T + timedelta(hours=4, minutes=40)), page=4)
    at = [edge["occurred_at"] for edge in body["edges"]]
    hours = [T + timedelta(hours=h) for h in (4, 5, 5, 6)]
    assert at == [_iso(h) for h in hours], "nearest 4 to 4:40 are 4, 5, 5, 6 h - in time order"
    page = body["page"]
    assert (page["mode"], page["size"], page["rows"]) == ("around", 4, 4)
    assert page["window"] == {"from": _iso(hours[0]), "to": _iso(hours[-1])}
    assert page["has_earlier"] is True and page["has_later"] is True
    assert page["earlier"] and page["later"]
    assert body["walk"]["mode"] == "time_page" and body["seed"]["id"] == explorer.entity_id(*Q)
    assert {node["depth"] for node in body["nodes"]} == {0, 1}
    assert not any("claim_count" in node or "attributes" in node for node in body["nodes"])


def test_later_pages_of_one_visit_every_point_once_across_a_same_instant_tie(get):
    body = _page(get, around=_iso(T), page=1)
    assert body["page"]["has_earlier"] is False and body["page"]["earlier"] is None
    seen = _claims(body)
    while body["page"]["has_later"]:
        body = _page(get, later=body["page"]["later"], page=1)
        assert body["page"]["mode"] == "later" and body["page"]["has_earlier"] is None
        seen += _claims(body)
    assert body["page"]["later"] is None
    assert seen == IN_ORDER, "every point once, in (time, id) order - the 5 h pair split by a page"


def test_earlier_pages_walk_back_to_the_first_point(get):
    body = _page(get, around=_iso(T + timedelta(hours=9)), page=3)
    assert body["page"]["has_later"] is False
    seen = _claims(body)
    while body["page"]["has_earlier"]:
        body = _page(get, earlier=body["page"]["earlier"], page=3)
        assert body["page"]["mode"] == "earlier" and body["page"]["has_later"] is None
        seen = _claims(body) + seen
    assert seen == IN_ORDER


def test_an_atom_whose_time_is_not_an_event_is_counted_not_drawn(get):
    body = _page(get, around=_iso(T), page=100)
    assert INGESTED["id"] not in _claims(body) and len(body["edges"]) == len(POINTS)
    assert body["page"]["not_event_time"] == 1


def test_an_old_fact_is_a_point_marked_not_current_and_a_value_is_no_point(get):
    """A page of TWO holds both facts - the value atom between them takes no place on it."""
    body = _page(get, node=TOOL, follow="set_to", direction="outgoing", around=_iso(T), page=2)
    marked = {edge["claim_id"]: edge.get("not_current") for edge in body["edges"]}
    assert marked == {OLD["id"]: True, NEW["id"]: None}
    assert body["edges"][0]["by_world"][0]["not_current"] is True
    assert body["page"]["rows"] == 2 and body["page"]["has_later"] is False
    assert body["page"]["not_event_time"] == 0


def test_a_point_is_the_walks_own_edge(get):
    page = _page(get, around=_iso(T), page=100)
    status, walked = get(follow="measures", direction="incoming", hops=1)
    assert status == 200
    by_claim = {edge["claim_id"]: edge for edge in walked["edges"]}
    assert len(by_claim) == len(POINTS) + 1, "the walk draws the ingested one too, with no time"
    assert len(page["edges"]) == len(POINTS)
    for edge in page["edges"]:
        assert edge == by_claim[edge["claim_id"]]


@pytest.mark.parametrize("params, argument", [
    ({"around": "2026-05-03T02:00:00Z", "later": "x"}, "around, later"),
    ({"around": "2026-05-03T02:00:00Z", "follow": None}, "follow"),
    ({"around": "2026-05-03T02:00:00Z", "follow": ["measures", "set_to"]}, "follow"),
    ({"around": "2026-05-03T02:00:00Z", "follow": "measures:quantity"}, "follow"),
    ({"around": "2026-05-03T02:00:00Z", "direction": "both"}, "direction"),
    ({"around": "2026-05-03T02:00:00Z", "hops": 2}, "hops"),
    ({"around": "not a time"}, "around"),
    ({"later": "not-a-cursor"}, "later"),
    ({"earlier": "A CURSOR WHOSE ID IS NOT A UUID"}, "earlier"),
])
def test_a_page_asked_wrongly_is_refused_by_argument(get, params, argument):
    from ledger_api import ledger_subgraph

    if params.get("earlier") == "A CURSOR WHOSE ID IS NOT A UUID":
        params = {"earlier": ledger_subgraph._token([_iso(T), "not-a-uuid"])}
    status, body = get(**{"follow": "measures", "direction": "incoming", "hops": 1, **params})
    assert status == 422 and body["detail"]["reason"] == "time_page_invalid", body
    assert body["detail"]["argument"] == argument


@pytest.mark.parametrize("name, value", [
    ("positive", explorer.entity_id("wafer", {"wafer": "W01"})),
    ("negative", explorer.entity_id("wafer", {"wafer": "W01"})),
    ("collect", "wafer"), ("group_by", "type"), ("measure", "count"),
    ("expand", explorer.entity_id(*Q) + "|measures|incoming"),
    ("since", "2026-05-01T00:00:00Z"), ("until", "2026-06-01T00:00:00Z"),
    ("fanout_limit", 5), ("format", "rows"),
])
def test_a_page_asked_with_a_walk_argument_is_refused_naming_it(get, name, value):
    status, body = get(follow="measures", direction="incoming", hops=1, around=_iso(T), **{name: value})
    assert status == 422 and body["detail"]["reason"] == "time_page_conflicts", body
    assert body["detail"]["arguments"] == [name]


def test_seed_type_with_a_page_is_refused_naming_it(get):
    status, body = get(node=Q, follow="measures", direction="incoming", hops=1, around=_iso(T),
                       seed_type="wafer")
    assert status == 422 and body["detail"]["arguments"] == ["seed_type"], body


@pytest.mark.parametrize("size", [0, 5001])
def test_the_page_size_is_bounded(get, size):
    status, _ = get(follow="measures", direction="incoming", hops=1, around=_iso(T), page=size)
    assert status == 422
