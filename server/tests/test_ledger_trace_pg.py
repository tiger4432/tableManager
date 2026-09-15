"""The ledger walk against a real PostgreSQL — the SQL lookup, the seam, the route.

Everything here needs an isolated PostgreSQL, declared as
`ASSY_PG_TEST_DATABASE_URL`, and skips loudly without one. It has to be
PostgreSQL and not the suite's SQLite: the lookup is `jsonb` operators over real
`timestamptz` and real partitions, and a green SQLite run would be evidence about
a database this code never touches (this project has paid for that three times).

`ledger_events` is created HERE, inside the scratch schema `pg_engine` already
drops on teardown. The table itself is another lane's to build; this file only
needs the CONTRACT shape to exist somewhere isolated so the query can be scored
against real `jsonb`, real `timestamptz` and real partitions.

🔴 THE SUBJECT MOVED (S-259, 2026-09-16). This file used to drive `ledger.trace.trace`
— the recursive CTE, the per-hop resolver and `GET /api/ledger/trace`. That walk came out
whole in `95940d45` (2026-08-27) and its routes in `67cc2e8a` (2026-08-25); the one data
route is `GET /api/ledger/subgraph`, served by `ledger_api.ledger_subgraph.subgraph` over
`SqlEvidenceLookup`. Every test whose QUESTION survived that revision now asks it of the
walk; every test whose question was the resolver's (hop states, rank/n, class order,
basis, the declared display zone) went with the resolver, as the unit file's did in the
same commit. What is left here is what only PostgreSQL can answer: the jsonb frontier
join, uuid `supersedes`, the session-timezone independence of `occurred_at`, the
relation seam, the catalogue-judged 503, and the route over HTTP against a real table.
"""

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

# Every test here drives `ledger` / `ledger_client`, both of which sit on `pg_engine` and
# skip without a declared PostgreSQL (S-256).
pytestmark = pytest.mark.pg

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer
from ledger import trace as lt
from ledger_api import ledger_subgraph


#: Fixtures carry a REAL +09:00 offset, not UTC (see the unit-test file).
KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=KST)

ledger_schema = pytest.importorskip(
    "ledger.schema", reason="the ledger package (L1) is not present")

#: 🔴 **THE DDL IS NOT WRITTEN HERE.** It used to be — a hand copy with YEARLY
#: partitions and NULLABLE provenance columns — and it was wrong on both counts
#: against the table that actually ships: the grain is MONTHLY (at 673 B/atom a
#: yearly partition carries the whole year and defeats pruning and detaching),
#: and `source_who` / `source_translator_ver` / `source_raw_ref` are NOT NULL
#: (an atom that cannot say who asserted it, by which translator, from which raw
#: row is not evidence). A fixture that disagrees with the shipped schema tests
#: a table nobody has.
#:
#: So this file calls `ledger.schema.ensure_schema` — the translator lane's own
#: single spelling — and inherits every constraint. When that schema changes,
#: these tests change with it instead of drifting away from it.

#: Months the fixtures write into. `occurred_at` is the partition key, so a month
#: with no partition is an insert that fails outright rather than a slow one.
FIXTURE_MONTHS = [datetime(y, m, 15, tzinfo=timezone.utc)
                  for y in (2024, 2025, 2026, 2027)
                  for m in range(1, 13)]


@pytest.fixture(scope="session")
def ledger_engine(pg_engine):
    """`pg_engine` plus the SHIPPED `ledger_events` schema in its scratch schema."""
    raw = pg_engine.raw_connection()
    try:
        # `search_path` came from the engine's connect_args, so every unqualified
        # relation this DDL creates lands in the scratch schema and goes with it.
        ledger_schema.ensure_schema(raw.driver_connection)
        for when in FIXTURE_MONTHS:
            ledger_schema.ensure_partition(raw.driver_connection, when)
    finally:
        raw.close()
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS ledger_events CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS ledger_translator_cursor CASCADE"))


@pytest.fixture(scope="function")
def ledger(ledger_engine):
    with ledger_engine.begin() as conn:
        conn.execute(text("TRUNCATE ledger_events"))
    yield ledger_engine
    with ledger_engine.begin() as conn:
        conn.execute(text("TRUNCATE ledger_events"))


def _uuid(seed):
    """A DETERMINISTIC uuid per logical atom name, so an edge's `claim_id` can be
    asserted by the atom's name rather than read back and compared to itself."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ledger-l2/{seed}"))


def insert(conn, atoms):
    conn.execute(text(
        "INSERT INTO ledger_events (id, subject_type, subject_keys, predicate, "
        "object_kind, object_payload, occurred_at, source_who, "
        "source_translator_ver, source_raw_ref, supersedes, source_event_id, "
        "source_event_state) VALUES "
        "(CAST(:id AS uuid), :st, CAST(:sk AS jsonb), :p, :ok, "
        " CAST(:op AS jsonb), :oa, :who, :ver, :raw, CAST(:sup AS uuid), "
        " CAST(:id AS uuid), 'source_record')"),
        atoms)


def _object(predicate, payload):
    """`(object_kind, object_payload)` in the translator's OWN shape.

    🔴 These fixtures used to be flat (`{"lot": "L-A"}`) and every test passed,
    while the real payload is `envelope.entity_ref` — `{"type", "keys",
    "qualifiers"}` — and the SQL that reads it (`object_payload->'keys'`) was
    therefore never once executed against the shape it exists for. Fixtures
    written by the lane under test agree with the lane under test.
    """
    p = dict(payload)
    if predicate == "register":
        # 🔴 NULL kind, not the string "none". `register`'s object is ∅ (§4.1); what it
        # may carry is the subject's OWN values, as `{"qualifiers": {...}}` (S-52) —
        # the shipped CHECK refuses anything else there. The walk turns those into the
        # node's `attributes` rather than into an edge, and must never read a bare
        # registration (NULL payload) as malformed.
        return None, ({"qualifiers": p} if p else None)
    if predicate == "has_wafer":
        ref = {"type": "Wafer", "keys": {"wafer": p.pop("wafer")}}
        ref["qualifiers"] = {"slot": p.pop("slot")}
        assert not p, f"unconsumed has_wafer payload: {p}"
        return "entity_ref", ref
    ref = {"type": "Lot", "keys": {"lot": p.pop("lot")}}
    if p:
        ref["qualifiers"] = p
    return "entity_ref", ref


def atom(name, lot, predicate, payload, occurred_at=T0, who="lot_event",
         supersedes=None, derivation=None):
    """One row of `ledger_events`. `derivation` stamps `source_translator_ver`'s
    `#<derivation>` suffix, the only place an atom's basis lives."""
    import json
    kind, ref = _object(predicate, payload)
    ref = None if ref is None else json.dumps(ref)
    return {"id": _uuid(name), "st": "Lot",
            "sk": json.dumps({"lot": lot}), "p": predicate, "ok": kind,
            "op": ref, "oa": occurred_at, "who": who,
            "ver": "lot_event/1" + (f"#{derivation}" if derivation else ""),
            "raw": f"lot_event:{name}",
            "sup": _uuid(supersedes) if supersedes else None}


def straight_chain(lots, slots, wafers, who="lot_event"):
    rows = []
    for i, lot in enumerate(lots):
        rows.append(atom(f"reg-{lot}", lot, "register", {},
                         occurred_at=T0 + timedelta(hours=i), who=who))
        rows.append(atom(f"hw-{lot}", lot, "has_wafer",
                         {"slot": slots[i], "wafer": wafers[i]},
                         occurred_at=T0 + timedelta(hours=i), who=who))
        if i + 1 < len(lots):
            parent = lots[i + 1]
            rows.append(atom(f"df-{lot}", lot, "derived_from", {"lot": parent},
                             occurred_at=T0 + timedelta(hours=i), who=who))
            rows.append(atom(f"sm-{lot}", lot, "slot_map",
                             {"lot": parent, "from": slots[i], "to": slots[i + 1]},
                             occurred_at=T0 + timedelta(hours=i), who=who))
    return rows


def raw_atom(id, lot, predicate, payload, occurred_at=T0, who="lot_event"):
    """An atom with a CHOSEN id. Payload still goes through `_object`, so these
    exercise the real shape too."""
    import json
    kind, ref = _object(predicate, payload)
    ref = None if ref is None else json.dumps(ref)
    return {"id": id, "st": "Lot", "sk": json.dumps({"lot": lot}),
            "p": predicate, "ok": kind, "op": ref,
            "oa": occurred_at, "who": who, "ver": "lot_event/1",
            "raw": "r", "sup": None}


def lot_seed(lot):
    return explorer.entity_id("Lot", {"lot": lot})


def walk_on(conn, lot, relation="ledger_events", **kw):
    """The live seat, in process: the walk over the ledger through the SQL lookup —
    exactly what `GET /api/ledger/subgraph` hands `subgraph` (minus the declaration
    lookups the route adds, which are not what PostgreSQL is asked here)."""
    return ledger_subgraph.subgraph(
        lot_seed(lot),
        ledger_subgraph.SqlEvidenceLookup(conn, relation=relation), **kw)


def lots_of(body):
    return sorted(node["keys"]["lot"] for node in body["nodes"]
                  if node["keys"].get("lot") is not None)


def edges_of(body, predicate):
    """`(source label, target label, edge)` for every edge of one predicate."""
    label = {node["id"]: node["label"] for node in body["nodes"]}
    return [(label[e["source"]], label[e["target"]], e)
            for e in body["edges"] if e["predicate"] == predicate]


LOTS = ["L-D", "L-C", "L-B", "L-A"]
SLOTS = ["3", "7", "11", "22"]
WAFERS = ["W-D", "W-C", "W-B", "W-A"]


# ---------------------------------------------------------------------------
# End to end on real SQL
# ---------------------------------------------------------------------------

def test_a_real_chain_walks_end_to_end(ledger):
    """The whole chain, over the jsonb frontier join, edges citing their atoms."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        body = walk_on(conn, "L-D", hops=12, direction="outgoing")

    assert body["state"] == "ready"
    assert lots_of(body) == sorted(LOTS)
    assert sorted(n["keys"]["wafer"] for n in body["nodes"]
                  if n["keys"].get("wafer")) == sorted(WAFERS)
    assert [(s, t) for s, t, _ in edges_of(body, "derived_from")] == [
        ("L-D", "L-C"), ("L-C", "L-B"), ("L-B", "L-A")]
    assert [e["qualifiers"] for _, _, e in edges_of(body, "slot_map")] == [
        {"from": "3", "to": "7"}, {"from": "7", "to": "11"}, {"from": "11", "to": "22"}]
    assert [(s, t, e["qualifiers"]["slot"]) for s, t, e in edges_of(body, "has_wafer")] == \
        list(zip(LOTS, WAFERS, SLOTS))
    # every edge cites the atom it was read from, by that atom's id
    for lot, (_, _, edge) in zip(LOTS, edges_of(body, "derived_from")):
        assert edge["claim_id"] == _uuid(f"df-{lot}")
    assert not any(body["truncated"][k] for k in ("depth", "nodes", "edges", "claims"))


#: 🔴 The acceptance datum, end to end. Source text `2026-05-03 02:17:00` is a
#: local Asia/Seoul wall clock; it stores as `2026-05-02T17:17:00+00:00`. The walk
#: puts the INSTANT on the wire (`_instant`: UTC, ISO 8601) and the screen renders
#: the wall clock — so what must not move here is the instant.
ACCEPTANCE_INSTANT = datetime(2026, 5, 2, 17, 17, 0, tzinfo=timezone.utc)
ACCEPTANCE_ON_THE_WIRE = "2026-05-02T17:17:00+00:00"


def test_the_rendered_time_does_not_depend_on_the_postgres_session_timezone(ledger):
    """🔴 THE TEST THAT WOULD HAVE CAUGHT THE ACCIDENT.

    psycopg2 hands back an aware datetime in the SESSION's TimeZone. `assy_qa`'s
    default is `Asia/Seoul`; on a box whose PostgreSQL `TimeZone` is UTC the same
    atom would come back with a different offset, and a renderer that emitted the
    value verbatim would put a different string on the wire for the same instant.

    So the session is FORCED to three different zones, including UTC, and the
    rendered string must not move. Setting `TimeZone` here is the whole point:
    a test that only ever ran under the box's default could not tell a
    normalised instant from an inherited one.
    """
    with ledger.begin() as conn:
        insert(conn, [
            atom("reg", "L-D", "register", {}, occurred_at=ACCEPTANCE_INSTANT),
            atom("hw", "L-D", "has_wafer", {"slot": "3", "wafer": "WF.01"},
                 occurred_at=ACCEPTANCE_INSTANT),
        ])

    rendered = {}
    for session_zone in ("UTC", "America/Los_Angeles", "Asia/Seoul"):
        with ledger.connect() as conn:
            conn.exec_driver_sql(f"SET TimeZone = '{session_zone}'")
            probe = conn.exec_driver_sql(
                "SELECT occurred_at FROM ledger_events LIMIT 1").scalar()
            body = walk_on(conn, "L-D", hops=1, direction="outgoing")
        (_, _, edge), = edges_of(body, "has_wafer")
        rendered[session_zone] = (edge["occurred_at"], probe.isoformat())

    # The driver really did hand back three different offsets - otherwise this
    # test proves nothing about the code.
    driver_offsets = {v[1] for v in rendered.values()}
    assert len(driver_offsets) == 3, (
        f"the session TimeZone did not change what psycopg2 returned, so this "
        f"scenario does not discriminate: {driver_offsets}")

    assert {v[0] for v in rendered.values()} == {ACCEPTANCE_ON_THE_WIRE}, (
        f"the rendered time follows the PostgreSQL session TimeZone: {rendered}")


def test_supersedes_is_honoured_against_real_uuid_columns(ledger):
    """A later atom that names an earlier one in `supersedes` (a uuid column read back
    as text) retires it: the walk draws the correction only, and says how many it
    dropped (`walk.superseded_dropped`, S-141)."""
    rows = [
        atom("reg", "L-D", "register", {}),
        atom("wrong", "L-D", "derived_from", {"lot": "L-WRONG"},
             occurred_at=T0 + timedelta(days=10), who="user"),
        atom("fix", "L-D", "derived_from", {"lot": "L-RIGHT"},
             occurred_at=T0, who="zz_file.csv", supersedes="wrong"),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        body = walk_on(conn, "L-D", hops=1, direction="outgoing")
    assert [(s, t) for s, t, _ in edges_of(body, "derived_from")] == [("L-D", "L-RIGHT")]
    assert body["walk"]["superseded_dropped"] == 1


def test_a_cycle_in_the_ledger_does_not_spin_the_walk(ledger):
    """A genuine loop must terminate on its own and must NOT be reported as the depth
    budget running out — the screen exists to say WHY a walk stopped, and "the chain
    continues" about a chain that eats itself is the wrong why."""
    rows = [
        atom("r1", "L-A", "register", {}), atom("r2", "L-B", "register", {}),
        atom("d1", "L-A", "derived_from", {"lot": "L-B"}),
        atom("d2", "L-B", "derived_from", {"lot": "L-A"}),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        t0 = time.perf_counter()
        body = walk_on(conn, "L-A", hops=40, direction="outgoing")
        elapsed = time.perf_counter() - t0
    assert lots_of(body) == ["L-A", "L-B"]
    assert sorted((s, t) for s, t, _ in edges_of(body, "derived_from")) == [
        ("L-A", "L-B"), ("L-B", "L-A")]
    assert body["truncated"]["depth"] is False, "a loop was reported as a depth cut"
    assert elapsed < 2.0, "the walk did not stop at the cycle"


def test_an_empty_ledger_table_still_answers(ledger):
    with ledger.begin() as conn:
        body = walk_on(conn, "L-NOTHING", hops=3)
    assert body["state"] == "empty"
    assert [n["id"] for n in body["nodes"]] == [lot_seed("L-NOTHING")]
    assert body["edges"] == []


# ---------------------------------------------------------------------------
# 🔴 THE SEAM — the lookup is replaceable, demonstrated rather than asserted
# ---------------------------------------------------------------------------

def test_a_diamond_genealogy_does_not_duplicate_claims(ledger):
    """A lot reached by TWO paths must be fetched once, not once per path.

    A MERGE gives exactly this shape, so it is not a corner case — it is half of
    what `lot_event` contains. A duplicated fetch would be quiet: the same edge id
    twice, or one witness counted as two in `claim_count`. Those are numbers a
    human reads off this screen, so they have to be true.
    """
    rows = [
        atom("reg-D", "L-D", "register", {}),
        atom("hw-D", "L-D", "has_wafer", {"slot": "1", "wafer": "W-D"}),
        atom("df-D-1", "L-D", "derived_from", {"lot": "L-B1"}),
        atom("df-D-2", "L-D", "derived_from", {"lot": "L-B2"}),
        atom("sm-D-1", "L-D", "slot_map", {"lot": "L-B1", "from": "1", "to": "1"}),
        atom("sm-D-2", "L-D", "slot_map", {"lot": "L-B2", "from": "1", "to": "1"}),
        atom("reg-B1", "L-B1", "register", {}),
        atom("reg-B2", "L-B2", "register", {}),
        atom("df-B1", "L-B1", "derived_from", {"lot": "L-A"}),
        atom("df-B2", "L-B2", "derived_from", {"lot": "L-A"}),
        atom("sm-B1", "L-B1", "slot_map", {"lot": "L-A", "from": "1", "to": "1"}),
        atom("sm-B2", "L-B2", "slot_map", {"lot": "L-A", "from": "1", "to": "1"}),
        atom("reg-A", "L-A", "register", {}),
        atom("hw-A", "L-A", "has_wafer", {"slot": "1", "wafer": "W-A"}),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        body = walk_on(conn, "L-D", hops=12, direction="outgoing")

    assert lots_of(body) == ["L-A", "L-B1", "L-B2", "L-D"]
    claim_ids = [e["claim_id"] for e in body["edges"]]
    assert len(claim_ids) == len(set(claim_ids)) == 10, (
        f"L-A's atoms came back once per path: {len(claim_ids)} edges, "
        f"{len(set(claim_ids))} distinct")
    # L-A is the lot reached twice; its wafer is stated by exactly ONE atom and
    # the answer must say so.
    a_hop = [e for s, _, e in edges_of(body, "has_wafer") if s == "L-A"]
    assert len(a_hop) == 1 and a_hop[0]["claim_id"] == _uuid("hw-A")
    (a_node,) = [n for n in body["nodes"] if n["keys"].get("lot") == "L-A"]
    # df-B1, df-B2, sm-B1, sm-B2 arrive and hw-A leaves: five atoms, counted once each
    assert a_node["claim_count"] == 5


def test_the_relation_name_is_the_only_thing_that_moves(ledger):
    """Pointing the walk at a different relation is one constructor argument.
    Here that relation is a VIEW, which is the crudest possible stand-in for a
    materialised projection."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        conn.execute(text(
            "CREATE OR REPLACE VIEW ledger_projection AS "
            "SELECT * FROM ledger_events"))
        try:
            direct = walk_on(conn, "L-D", hops=12, direction="outgoing")
            swapped = walk_on(conn, "L-D", relation="ledger_projection",
                              hops=12, direction="outgoing")
        finally:
            conn.execute(text("DROP VIEW IF EXISTS ledger_projection"))
    for key in ("nodes", "edges", "state", "walk", "truncated"):
        assert direct[key] == swapped[key], key


# ---------------------------------------------------------------------------
# The route — over HTTP, against the same PostgreSQL
# ---------------------------------------------------------------------------

@pytest.fixture
def ledger_client(ledger):
    """A `TestClient` whose `get_db` yields a Session on the scratch schema."""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from main import app
    from database.database import get_db

    Maker = sessionmaker(autocommit=False, autoflush=False, bind=ledger)
    db = Maker()

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.rollback()
        db.close()


WALK_ROUTE = "/api/ledger/subgraph"


def test_the_route_serves_the_walk_over_real_postgres(ledger_client, ledger):
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))

    resp = ledger_client.get(WALK_ROUTE, params={
        "id": lot_seed("L-D"), "hops": 12, "direction": "outgoing"})
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/json"), (
        "the route was shadowed by the SPA catch-all and served index.html - "
        "include_router must stay ABOVE it in main.py")
    body = resp.json()
    assert {"state", "nodes", "edges", "seeds", "propagation", "walk", "limits",
            "truncated", "generated_at"} <= set(body)
    assert body["state"] == "ready"
    assert lots_of(body) == sorted(LOTS)
    assert [(s, t) for s, t, _ in edges_of(body, "derived_from")] == [
        ("L-D", "L-C"), ("L-C", "L-B"), ("L-B", "L-A")]


def test_the_route_answers_for_a_lot_the_ledger_never_heard_of(ledger_client, ledger):
    resp = ledger_client.get(WALK_ROUTE, params={"id": lot_seed("L-GHOST"), "hops": 1})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "empty"
    assert [n["id"] for n in body["nodes"]] == [lot_seed("L-GHOST")]


def test_the_route_names_an_absent_ledger_in_a_field_not_in_prose(
        ledger_client, monkeypatch):
    """🔴 THE ALARM THAT HAD NEVER BEEN RUNG.

    The 503-for-an-absent-relation branch once matched the English words "does not
    exist" in the driver's message, while this PostgreSQL emits Korean. The relation
    is judged by the catalogue and the body is machine-readable. This is the test
    that fires it, against a real catalogue.
    """
    from ledger import trace_router as router_module
    monkeypatch.setattr(router_module, "LEDGER_RELATION", "ledger_events_not_migrated")

    resp = ledger_client.get(WALK_ROUTE, params={"id": lot_seed("L-D"), "hops": 3})
    assert resp.status_code == 503, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, dict), (
        "the client would have to parse Korean prose to tell a deployment "
        "problem from a data boundary")
    # 🔴 THE LITERAL, NOT THE CONSTANT. `detail["reason"] == lt.REASON_RELATION_
    # ABSENT` compares the code to itself and stays green while the token the
    # client lane branches on changes underneath it — a mutant renaming the
    # constant passed that version of this assertion. The wire value is the
    # contract, so the wire value is what is written out here.
    assert detail["reason"] == "ledger_relation_absent"
    assert lt.REASON_RELATION_ABSENT == "ledger_relation_absent"
    assert detail["state"] == "absent"
    assert detail["relation"] == "ledger_events_not_migrated"
    assert detail["message"]


def test_an_unknown_lot_and_an_undeployed_ledger_are_different_responses(
        ledger_client, ledger):
    """SITUATION 3 vs SITUATION 1, over HTTP. One is a 200 carrying `state: empty`,
    the other (the test above) a 503 carrying a machine-readable reason. They must
    never coincide, and a populated ledger must not change the 200."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    resp = ledger_client.get(WALK_ROUTE, params={"id": lot_seed("L-NEVER-SEEN"), "hops": 3})
    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "empty"


# ---------------------------------------------------------------------------
# COVERAGE — the four "nothings" have to become four different answers
# ---------------------------------------------------------------------------
#
# The defect these tests exist for was found on a real box, not imagined: the
# product owner opened the trace screen on `assy_manager` and got nothing,
# because that database had no `ledger_events` table at all. A deployment
# problem and a data boundary rendered identically and the screen said neither.
# Each test below pins ONE of the four situations apart from the others.
#
#     1 relation absent    deployment — the migration has not been run
#     2 present, no atoms  the backfill has not been run
#     3 unknown lot        a data boundary
#     4 known, no lineage  registered, nothing claimed about its parentage

def _coverage(conn, **kw):
    return lt.coverage(conn, config=lt.DEFAULT_RESOLVER_CONFIG, **kw)


#: 🔴 THE PINNED SHAPE, IN ONE PLACE. A client lane renders this body and the status
#: strip added by ruling R-2026-08-13-F reads the SAME response rather than fetching its
#: own — so a key appearing or vanishing here is a contract change, not an edit, and the
#: set is asserted rather than sampled so a field cannot quietly disappear.
#:
#: `atoms`, `partitions`, `cursors` and `last_atom` are the ruling's four additions.
#: There is deliberately no verification-run key: no such log exists and the ruling
#: declined to build one, so the screen renders its own 「검산 기록 없음」 rather than
#: reading an empty field that would imply the log exists and is empty.
COVERAGE_KEYS = {"state", "lots", "sources", "occurred_at", "sample",
                 "atoms", "partitions", "cursors", "last_atom"}


def test_coverage_says_absent_when_the_relation_is_not_there(ledger):
    """SITUATION 1. Asked of a relation the catalogue does not know — exactly
    what `to_regclass` sees on a database whose migration never ran.

    It must be an ANSWER, not an exception: an operator in front of a blank
    screen needs the word `absent`, not a stack trace.
    """
    with ledger.connect() as conn:
        answer = _coverage(conn, relation="ledger_events_not_migrated",
                           cursor_relation="ledger_cursor_not_migrated")
    assert answer["state"] == "absent"
    assert answer["lots"] == 0
    assert answer["sources"] == []
    assert answer["occurred_at"] == {"from": None, "to": None}
    assert answer["sample"] == []


def test_coverage_says_empty_when_the_table_is_there_and_holds_nothing(ledger):
    """SITUATION 2.

    🔴 This is the one the trace screen CANNOT tell from situation 3 on its own:
    against an empty ledger every lot comes back `[unknown_subject]`, exactly as
    an unknown lot does against a full one. The difference is a property of the
    box, so it is answered here rather than guessed there.
    """
    with ledger.connect() as conn:
        answer = _coverage(conn)
    assert answer["state"] == "empty"
    assert answer["lots"] == 0
    assert answer["occurred_at"] == {"from": None, "to": None}
    assert answer["sample"] == []


def test_coverage_reports_a_ready_ledger_in_the_pinned_shape(ledger):
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    with ledger.connect() as conn:
        answer = _coverage(conn)

    assert set(answer) == COVERAGE_KEYS
    assert answer["state"] == "ready"
    # The `register` atoms ARE the catalog — four lots, four registers.
    assert answer["lots"] == len(LOTS)
    assert answer["sources"] == []          # nothing wrote a cursor row here
    assert answer["occurred_at"]["from"] is not None
    assert answer["occurred_at"]["from"] <= answer["occurred_at"]["to"]


def test_coverage_renders_times_in_the_declared_zone(ledger):
    """The same rule `_iso` follows everywhere else, so the response does not
    depend on the PostgreSQL session's TimeZone or on the machine's."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    seoul = dict(lt.DEFAULT_RESOLVER_CONFIG, display_timezone="Asia/Seoul")
    utc = dict(lt.DEFAULT_RESOLVER_CONFIG, display_timezone="UTC")
    with ledger.connect() as conn:
        in_seoul = lt.coverage(conn, config=seoul)["occurred_at"]["from"]
        in_utc = lt.coverage(conn, config=utc)["occurred_at"]["from"]

    assert in_seoul.endswith("+09:00"), in_seoul
    assert in_utc.endswith("+00:00"), in_utc
    # The SAME instant said twice. If these differed, the zone would be being
    # applied to the VALUE rather than to its rendering — the defect `bee1aeb`
    # closed, which nothing complains about because a wrong instant is still a
    # well-formed one.
    assert datetime.fromisoformat(in_seoul) == datetime.fromisoformat(in_utc)


def test_the_sample_leads_with_the_lot_that_has_the_most_lineage(ledger):
    """Rule 2 of `_coverage_sample`, and it is what puts a CONTENDED lot first.

    The most informative thing the screen can open on is a lot whose lineage is
    disputed, because that is where the state vocabulary earns its keep. On
    `assy_manager` this rule surfaces `CL-2601-005-A5` — three `derived_from`
    atoms, two of which disagree — ahead of lots carrying one.
    """
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        # L-B gains a SECOND, contending parent claim. Nothing else changes.
        insert(conn, [atom("df-L-B-alt", "L-B", "derived_from", {"lot": "L-A"},
                           occurred_at=T0 + timedelta(hours=9))])
    with ledger.connect() as conn:
        sample = _coverage(conn)["sample"]
    assert sample[0]["lot"] == "L-B", (
        f"the contended lot is not first: {[e['lot'] for e in sample]}")


def test_a_lot_nothing_is_derived_from_is_never_sampled(ledger):
    """SITUATION 4, and the junk filter in one test.

    `assy_manager`'s ledger legitimately registers a lot called `adsfas` —
    somebody typed it into `lot_event`. The ledger MUST keep counting it: the
    translator records what the source uttered and does not judge it, and `lots`
    is a fact about the source. But it must not be the first thing an operator
    reads, and rule 1 excludes it by a PROPERTY OF THE DATA (nothing is derived
    from it) rather than by a blocklist somebody would have to maintain.
    """
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        insert(conn, [atom("reg-junk", "adsfas", "register", {}),
                      atom("hw-junk", "adsfas", "has_wafer",
                           {"slot": "1", "wafer": "W-JUNK"})])
    with ledger.connect() as conn:
        answer = _coverage(conn)
    assert answer["lots"] == len(LOTS) + 1, "the junk lot was dropped from the count"
    assert "adsfas" not in [e["lot"] for e in answer["sample"]]


def test_a_lot_with_only_a_register_is_told_apart_from_a_lot_nobody_knows(ledger):
    """SITUATION 4 vs SITUATION 3 — the two that are both "the ledger says
    nothing about this lot" and are NOT the same fact."""
    with ledger.begin() as conn:
        insert(conn, [atom("reg-LONELY", "L-LONELY", "register", {"owner": "fab-2"})])
    with ledger.connect() as conn:
        answer = _coverage(conn)
        assert answer["state"] == "ready"
        assert answer["lots"] == 1
        assert answer["sample"] == []
        known = walk_on(conn, "L-LONELY", hops=3)
        unknown = walk_on(conn, "L-NEVER-SEEN", hops=3)

    # Neither walk finds a neighbour, so both say `empty` — the WALK is the same. What
    # tells them apart is the node: a registration this walk reached puts the entity's
    # own values on it as `attributes`, and a node no registration was reached for gets
    # NO such key (not `{}`, not `null` — `_apply_registrations`, WALK.md §4). A client
    # branches on the key; nothing here is prose.
    assert known["state"] == unknown["state"] == "empty"
    (known_node,) = known["nodes"]
    (unknown_node,) = unknown["nodes"]
    assert known_node["attributes"] == {"owner": "fab-2"}
    assert "attributes" not in unknown_node, (
        "situations 3 and 4 render identically — the operator cannot tell a data "
        "boundary from a lot with no lineage claim")


def test_coverage_names_the_sources_that_have_written_to_the_ledger(ledger):
    """`sources` comes from the cursor table, so it still answers when the ledger
    is EMPTY — "a translator ran and produced nothing" is a different fact from
    "no translator has ever run", and both render as zero atoms."""
    with ledger.begin() as conn:
        conn.execute(text(
            "INSERT INTO ledger_translator_cursor "
            "(source, translator_ver, cursor_value) "
            "VALUES ('lot_event', 'lot_event/1', '{}'::jsonb)"))
    try:
        with ledger.connect() as conn:
            answer = _coverage(conn)
        assert answer["state"] == "empty"
        assert answer["sources"] == ["lot_event"]
    finally:
        with ledger.begin() as conn:
            conn.execute(text("DELETE FROM ledger_translator_cursor"))


# ---------------------------------------------------------------------------
# THE STATUS STRIP'S THREE SIGNALS (ruling R-2026-08-13-F)
# ---------------------------------------------------------------------------
#
# Before this, `occurred_at.to` was the ONLY one of them any route carried. Atom
# count, partition state and cursor state lived in `store`/`schema` functions the
# backfill CLI called and nothing served, and named refusal reasons could not be
# read out of the database at all. Each test below pins one of them, and the two
# that could lie quietly — an estimate that has never been analysed, and a
# recorded time decoded out of an id that has none — are pinned on BOTH arms.

def test_the_atom_count_is_an_estimate_and_the_response_says_so(ledger):
    """🔴 APPROXIMATED ON PURPOSE, AND HONEST ABOUT IT.

    `store.atom_count()` is `count(*)` across every partition — the cost this
    endpoint may not pay at ten million atoms. The catalogue answers instead, and
    the field carries `exact: false` so the screen can render an approximation
    rather than a number that will be quoted back as a discrepancy.
    """
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        actual = conn.execute(text("SELECT count(*) FROM ledger_events")).scalar()
        # 🔴 ANALYZE FIRST, AND SAY WHY. `reltuples` is maintained by VACUUM and
        # ANALYZE, so a table nobody has analysed reports -1 or 0 — and this project
        # has already lost a round to a measurement taken on a relation with no
        # statistics (lessons file, 2026-08-12). The un-analysed arm is the test
        # below; this one is the analysed one.
        conn.execute(text("ANALYZE ledger_events"))
    with ledger.connect() as conn:
        answer = _coverage(conn)

    atoms = answer["atoms"]
    assert atoms["exact"] is False
    assert atoms["method"] == "pg_class.reltuples"
    assert atoms["estimate"] == actual, (
        f"the estimate is {atoms['estimate']} against {actual} real atoms — on a "
        f"freshly analysed table these agree, so a difference here means the sum is "
        f"reading the wrong relations (the partitioned PARENT holds no rows of its own)")


def test_an_unanalysed_partition_is_counted_and_named_rather_than_read_as_empty(ledger):
    """The estimate's blind spot, reported instead of smoothed over.

    A partition PostgreSQL has never analysed carries `reltuples = -1`. Treating that
    as zero would let a freshly restored database report an empty ledger that is full
    — the estimate would be confidently wrong with nothing on the screen to hint at
    it. So those partitions are counted, and the response says how many of its inputs
    it could not see.
    """
    # Put the catalogue into the state a never-analysed database is in. Written
    # directly rather than by finding a partition PostgreSQL happens not to have
    # analysed yet, because that would make the test depend on autovacuum's timing —
    # and a guard that fires only when the scheduler cooperates is not a guard.
    # 🔴 `pg_stat_reset()` is deliberately NOT used: it would throw away this
    # database's whole statistics ledger to test one field, and reading a reset
    # counter as a fact is a defect this project has already paid a round for.
    with ledger.begin() as conn:
        conn.execute(text("UPDATE pg_class SET reltuples = -1, relpages = 0 "
                          "WHERE oid IN (SELECT inhrelid FROM pg_inherits "
                          "WHERE inhparent = to_regclass('ledger_events'))"))
    try:
        with ledger.connect() as conn:
            answer = _coverage(conn)
        assert answer["atoms"]["unanalyzed_partitions"] == len(FIXTURE_MONTHS), (
            "a partition with no statistics is being reported as a partition with "
            "zero atoms")
        assert answer["atoms"]["estimate"] == 0
    finally:
        with ledger.begin() as conn:
            conn.execute(text("ANALYZE ledger_events"))


def test_the_partitions_are_reported_exactly_from_the_catalogue(ledger):
    """Exact and free — `pg_inherits` is a catalogue join, no heap is touched.

    The bound is carried VERBATIM as PostgreSQL renders it. Re-parsing
    `FOR VALUES FROM (…) TO (…)` into a pair of instants here would be a second
    spelling of the partition grammar, and the operator needs to see what the
    database says rather than this module's re-reading of it.
    """
    with ledger.connect() as conn:
        answer = _coverage(conn)
    partitions = answer["partitions"]
    assert partitions["count"] == len(FIXTURE_MONTHS)
    assert len(partitions["list"]) == partitions["count"]
    names = [p["name"] for p in partitions["list"]]
    assert "ledger_events_2026_01" in names, names[:3]
    assert names == sorted(names), "the partition list must not shuffle between calls"
    for entry in partitions["list"]:
        assert entry["bound"].startswith("FOR VALUES FROM"), entry


def test_the_partitions_answer_for_a_deployed_but_EMPTY_ledger(ledger):
    """An empty ledger is deployed, partitioned and covering months — and saying
    nothing about that would leave "the table is there and holds nothing" and "the
    table is there and I cannot tell you anything" rendering identically, which is
    the exact conflation `state` exists to end."""
    with ledger.connect() as conn:
        answer = _coverage(conn)
    assert answer["state"] == "empty"
    assert answer["partitions"]["count"] == len(FIXTURE_MONTHS)
    assert answer["last_atom"] == {"occurred_at": None, "recorded_at": None}


def test_the_last_atom_carries_the_time_it_HAPPENED_and_the_time_it_was_RECORDED(ledger):
    """🔴 THE SAME DECODE AS `ledger.uuid7.timestamp_ms`, PROVEN EQUAL.

    There is no `recorded_at` column and ruling R-2026-08-13-F refused to add one —
    a second home for one fact. The write time lives in the UUIDv7 `id`, and the web
    server decodes it in SQL because it does not import the translator package
    (`server/ledger/__init__.py`'s stated safety property: nothing in `server/`
    imports it).

    That leaves TWO spellings of one decode, in two languages, and two spellings of
    one key is how this project's schema notes say a writer and a reader silently
    stop agreeing. So the test drives BOTH and requires the same instant.
    """
    uuid7 = pytest.importorskip("ledger.uuid7")
    minted = uuid7.uuid7()
    when = T0 + timedelta(days=3)
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        insert(conn, [dict(raw_atom(str(minted), "L-NEWEST", "register", {},
                                    occurred_at=when))])
    with ledger.connect() as conn:
        answer = _coverage(conn)

    assert answer["last_atom"]["occurred_at"] == lt._iso(
        when, lt.resolve_display_zone(lt.DEFAULT_RESOLVER_CONFIG))
    recorded = datetime.fromisoformat(answer["last_atom"]["recorded_at"])
    expected_ms = uuid7.timestamp_ms(minted)
    assert round(recorded.timestamp() * 1000) == expected_ms, (
        f"the SQL decode says {recorded.isoformat()} and `uuid7.timestamp_ms` says "
        f"{expected_ms} — the two spellings of the UUIDv7 stamp have drifted")


def test_an_id_that_is_not_a_v7_reports_NO_recorded_time_rather_than_inventing_one(
        ledger):
    """The other arm, and it is not hypothetical: every fixture in this file mints
    `uuid5`. Decoding a v5's first 48 bits would yield a perfectly well-formed
    instant made of hash bits — a confident wrong answer, which is the failure mode
    this project keeps paying for. NULL is the honest report."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    with ledger.connect() as conn:
        answer = _coverage(conn)
    assert answer["last_atom"]["occurred_at"] is not None, (
        "the fixture did not land, so this test would prove nothing")
    assert answer["last_atom"]["recorded_at"] is None


def test_an_index_can_serve_the_newest_atom_without_scanning_the_ledger(ledger):
    """The newest-atom lookup is the ONLY one of the ruling's four additions that
    touches the ledger heap, so it is the only one that could turn the page load into
    a scan. Two claims, and the FIRST one is the load-bearing one:

    1. **Structural, and size-independent**: an index on the parent leads with
       `occurred_at`. That is the property the docstring claims (`uq_ledger_atom`'s
       leading column, `schema.DEDUPE_COLUMNS`) and the one that survives a schema
       edit — if somebody reorders those columns for a different reason, this goes
       red and the endpoint's cost argument is re-decided rather than lost.
    2. **The plan, with `enable_seqscan` off**: an index scan is AVAILABLE. Disabling
       the switch does not force one — PostgreSQL still falls back to a penalised
       sequential scan when no usable index exists — so this stays a real assertion.

    🔴 WHAT THIS DOES **NOT** CLAIM, said out loud: that the planner CHOOSES the index
    here. This fixture is 48 partitions holding a handful of rows, and on it the
    planner correctly prefers a sort over 61 rows — a plan assertion at that size
    would be measuring the degenerate case. On `assy_manager` (909 atoms, one
    partition, analysed) the very same statement plans as
    `Index Scan Backward using …occurred_at…` with the switch ON, which is the real
    behaviour this test can only bracket.
    """
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        conn.execute(text("ANALYZE ledger_events"))

    with ledger.connect() as conn:
        leading = dict(conn.execute(text("""
            SELECT i.relname, a.attname
            FROM pg_index x
            JOIN pg_class i ON i.oid = x.indexrelid
            JOIN pg_attribute a ON a.attrelid = i.oid AND a.attnum = 1
            WHERE x.indrelid = to_regclass('ledger_events')
        """)).fetchall())
        conn.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(r[0] for r in conn.execute(text(
            "EXPLAIN SELECT occurred_at, id FROM ledger_events "
            "ORDER BY occurred_at DESC LIMIT 1")).fetchall())

    assert leading.get("uq_ledger_atom") == "occurred_at", (
        f"no index on the ledger leads with occurred_at, so the newest-atom lookup "
        f"has nothing to ride: {leading}")
    assert "Seq Scan" not in plan, (
        f"even with sequential scans disabled the newest-atom lookup will not use an "
        f"index — there is none it can use:\n{plan}")


def test_the_cursor_report_names_what_was_refused_and_what_it_cannot_explain(ledger):
    """🔴 THE ONLY READ OF NAMED REFUSALS THAT EXISTS.

    `gate._refusals` is process-local to the backfill, the web server never imports
    that package, and the heartbeat note is not served — so this column is the whole
    of the answer to "what was refused, by name" for anybody who is not the backfill
    process itself.

    Both row shapes are here in one test because they are told apart by a field:

      * a row the current writer owns  -> a breakdown, `refusals_unaccounted == 0`
      * a row that PREDATES the column -> NULL, and its aggregate is unaccounted for

    The second is not hypothetical: both development databases carried exactly that
    (`molecules_refused = 1`, no breakdown) when the migration ran. A screen that
    rendered "1 refused" beside an empty list would be reporting a bookkeeping fault
    that is not there, and a status strip that cries wolf about its own bookkeeping
    is worse than no status strip.
    """
    with ledger.begin() as conn:
        conn.execute(text("""
            INSERT INTO ledger_translator_cursor
                (source, translator_ver, cursor_value, molecules_refused,
                 refusal_reasons)
            VALUES ('written_by_the_new_writer', 'v/1', '{}'::jsonb, 3,
                    '{"no_identity": {"count": 2,
                                      "last_at": "2026-08-13T01:02:03+00:00"},
                      "atomicity_violation": {"count": 1,
                                              "last_at": "2026-08-13T04:05:06+00:00"}}')
        """))
        conn.execute(text("""
            INSERT INTO ledger_translator_cursor
                (source, translator_ver, cursor_value, molecules_refused)
            VALUES ('predates_the_column', 'v/1', '{}'::jsonb, 1)
        """))
    try:
        with ledger.connect() as conn:
            answer = _coverage(conn)
        rows = {c["source"]: c for c in answer["cursors"]}
        assert set(rows) == {"written_by_the_new_writer", "predates_the_column"}
        assert answer["sources"] == sorted(rows), (
            "`sources` must keep naming exactly the cursor rows it always did")

        owned = rows["written_by_the_new_writer"]
        assert owned["molecules_refused"] == 3
        assert set(owned["refusal_reasons"]) == {"no_identity", "atomicity_violation"}
        assert owned["refusal_reasons"]["no_identity"]["count"] == 2
        assert owned["refusals_unaccounted"] == 0, (
            "the breakdown does not add up to the aggregate it explains")
        # Rendered in the DECLARED display zone, like every other instant in this
        # response. The stored value is UTC; +09:00 here is the same instant said
        # in the zone the operator reads.
        assert owned["refusal_reasons"]["no_identity"]["last_at"].endswith("+09:00")

        legacy = rows["predates_the_column"]
        assert legacy["refusal_reasons"] is None, (
            "NULL became {} somewhere — 'this predates the breakdown' and 'nothing "
            "was refused' are now indistinguishable")
        assert legacy["refusals_unaccounted"] == 1
    finally:
        with ledger.begin() as conn:
            conn.execute(text("DELETE FROM ledger_translator_cursor"))


def test_coverage_answers_when_the_cursor_table_predates_the_refusal_column(ledger):
    """The migration-ordering arm, from the READER's side.

    `add_frame_confirmation.py` documents the hazard: a column added to an existing
    table is a 500 in every process that reads it before the migration runs. A status
    endpoint that answers 500 is the screen reporting itself broken, which is exactly
    the blank-screen incident this endpoint was built for. So the reader asks the
    catalogue which columns exist and selects only those.
    """
    with ledger.begin() as conn:
        conn.execute(text(
            "INSERT INTO ledger_translator_cursor "
            "(source, translator_ver, cursor_value, molecules_refused) "
            "VALUES ('lot_event', 'v/1', '{}'::jsonb, 4)"))
        conn.execute(text("ALTER TABLE ledger_translator_cursor "
                          "DROP COLUMN refusal_reasons"))
    try:
        with ledger.connect() as conn:
            answer = _coverage(conn)
        row = answer["cursors"][0]
        assert row["source"] == "lot_event"
        assert row["molecules_refused"] == 4
        assert "refusal_reasons" not in row, (
            "a column the database does not have was reported as present")
        assert row["refusals_unaccounted"] == 4
    finally:
        with ledger.begin() as conn:
            conn.execute(text("DELETE FROM ledger_translator_cursor"))
            conn.execute(text("ALTER TABLE ledger_translator_cursor "
                              "ADD COLUMN refusal_reasons JSONB"))

