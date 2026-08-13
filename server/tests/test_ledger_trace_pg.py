"""The ledger trace against a real PostgreSQL — the recursive CTE and the seam.

Everything here needs an isolated PostgreSQL, declared as
`ASSY_PG_TEST_DATABASE_URL`, and skips loudly without one. It has to be
PostgreSQL and not the suite's SQLite: the query is `jsonb` operators and a
`CYCLE` clause, and a green SQLite run would be evidence about a database this
code never touches (this project has paid for that three times).

`ledger_events` is created HERE, inside the scratch schema `pg_engine` already
drops on teardown. The table itself is another lane's to build; this file only
needs the CONTRACT shape to exist somewhere isolated so the query can be scored
against real `jsonb`, real `timestamptz` and real partitions.
"""

import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_trace as lt


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
#: single spelling — and inherits every constraint, including the two CHECKs that
#: make `register` the ONLY predicate allowed a NULL `object_kind`. When that
#: schema changes, these tests change with it instead of drifting away from it.
#:
#: The one index this lane cares about, `idx_ledger_subject_lot`, is in there and
#: is named after this consumer in `schema.py`'s own comment. It is NOT re-spelled
#: here.

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
    """A DETERMINISTIC uuid per logical atom name.

    Deterministic because level 3 of the resolver is the event id, so a test
    about ordering that minted random ids would pass or fail by luck.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"ledger-l2/{seed}"))


def insert(conn, atoms):
    conn.execute(text(
        "INSERT INTO ledger_events (id, subject_type, subject_keys, predicate, "
        "object_kind, object_payload, occurred_at, source_who, "
        "source_translator_ver, source_raw_ref, supersedes) VALUES "
        "(CAST(:id AS uuid), :st, CAST(:sk AS jsonb), :p, :ok, "
        " CAST(:op AS jsonb), :oa, :who, :ver, :raw, CAST(:sup AS uuid))"),
        atoms)


#: 🔴 A resolver config whose class 1 is decided by `source_who`, NOT by a flag in
#: the payload. That is not a preference: `ledger.vocabulary` REFUSES any
#: qualifier a predicate did not declare, and `slot_map`/`has_wafer` declare
#: exactly {from,to,wafer} and {slot}. So an atom carrying `"confirmed": true`
#: cannot get past the translator's gate, and a resolver that could only be
#: driven that way could never be driven at all.
CONFIRMED_CFG = dict(lt.DEFAULT_RESOLVER_CONFIG,
                     confirmed_sources=["chain_confirm"])


def _object(predicate, payload):
    """`(object_kind, object_payload)` in the translator's OWN shape.

    🔴 These fixtures used to be flat (`{"lot": "L-A"}`) and every test passed,
    while the real payload is `envelope.entity_ref` — `{"type", "keys",
    "qualifiers"}` — and the SQL that reads it (`object_payload->'keys'->>'lot'`)
    was therefore never once executed against the shape it exists for. Fixtures
    written by the lane under test agree with the lane under test.
    """
    p = dict(payload)
    if predicate == "register":
        # 🔴 NULL, not the string "none" and not `{}`. `register`'s object is ∅
        # (§4.1) and the shipped table enforces it BOTH ways:
        #   (predicate = 'register') = (object_kind IS NULL)
        # so a `register` with a non-null kind is refused, and so is any other
        # predicate with a null one. The trace must therefore tolerate a NULL
        # `object_kind` on exactly this predicate and never read it as malformed.
        return None, None
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
         supersedes=None):
    import json
    kind, ref = _object(predicate, payload)
    ref = None if ref is None else json.dumps(ref)
    return {"id": _uuid(name), "st": "Lot",
            "sk": json.dumps({"lot": lot}), "p": predicate, "ok": kind,
            "op": ref, "oa": occurred_at, "who": who,
            "ver": "lot_event/1", "raw": f"lot_event:{name}",
            "sup": _uuid(supersedes) if supersedes else None}


def straight_chain(lots, slots, wafers, who="lot_event"):
    import itertools
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


def trace_on(conn, lot, slot=None, config=None, **kw):
    return lt.trace(lot, slot,
                    lookup=lt.SqlClaimLookup(conn, relation="ledger_events"),
                    config=config or lt.DEFAULT_RESOLVER_CONFIG, **kw)


def raw_atom(id, lot, predicate, payload, occurred_at=T0, who="lot_event"):
    """An atom with a CHOSEN id — for the ordering tests, where the id is the
    thing under test. Payload still goes through `_object`, so these exercise the
    real shape too."""
    import json
    kind, ref = _object(predicate, payload)
    ref = None if ref is None else json.dumps(ref)
    return {"id": id, "st": "Lot", "sk": json.dumps({"lot": lot}),
            "p": predicate, "ok": kind, "op": ref,
            "oa": occurred_at, "who": who, "ver": "lot_event/1",
            "raw": "r", "sup": None}


LOTS = ["L-D", "L-C", "L-B", "L-A"]
SLOTS = ["3", "7", "11", "22"]
WAFERS = ["W-D", "W-C", "W-B", "W-A"]


# ---------------------------------------------------------------------------
# End to end on real SQL
# ---------------------------------------------------------------------------

def test_a_real_chain_walks_end_to_end(ledger):
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        answer = trace_on(conn, "L-D", "3")

    assert [(h["predicate"], h["state"]) for h in answer["hops"]] == [
        ("has_wafer", "resolved"), ("derived_from", "resolved"), ("slot_map", "resolved"),
        ("has_wafer", "resolved"), ("derived_from", "resolved"), ("slot_map", "resolved"),
        ("has_wafer", "resolved"), ("derived_from", "resolved"), ("slot_map", "resolved"),
        ("has_wafer", "resolved"), ("derived_from", "unresolvable"),
    ]
    lineage = [h["to"]["keys"]["lot"] for h in answer["hops"]
               if h["predicate"] == "derived_from" and h["to"]]
    assert lineage == ["L-C", "L-B", "L-A"]
    wafers = [h["to"]["keys"]["wafer"] for h in answer["hops"]
              if h["predicate"] == "has_wafer" and h["to"]]
    assert wafers == WAFERS
    slots = [h["to"]["slot"] for h in answer["hops"] if h["predicate"] == "slot_map"]
    assert slots == ["7", "11", "22"]
    assert "root" in answer["terminal_reason"] and "L-A" in answer["terminal_reason"]
    # every hop cites the atom it was decided by
    for hop in answer["hops"]:
        if hop["state"] != "unresolvable":
            assert hop["event_id"] and hop["occurred_at"]


def test_deleting_a_has_wafer_atom_names_the_hop_on_real_sql(ledger):
    """🔴 The acceptance criterion, run against PostgreSQL rather than a list."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        before = trace_on(conn, "L-D", "3")
        conn.execute(text("DELETE FROM ledger_events WHERE id = CAST(:i AS uuid)"),
                     {"i": _uuid("hw-L-B")})
        after = trace_on(conn, "L-D", "3")

    assert all(h["state"] == "resolved" for h in before["hops"]
               if h["predicate"] == "has_wafer")

    wafer_hops = [h for h in after["hops"] if h["predicate"] == "has_wafer"]
    assert [h["state"] for h in wafer_hops] == \
        ["resolved", "resolved", "unresolvable", "resolved"]
    broken = wafer_hops[2]
    assert broken["from"] == {"type": "Lot", "keys": {"lot": "L-B"}, "slot": "11"}
    assert broken["to"] is None
    assert "no_claim" in broken["reason"] and "has_wafer" in broken["reason"]
    assert "lot=L-B" in broken["reason"] and "slot=11" in broken["reason"]
    # and the answer is not shorter - the lineage is untouched
    assert len(after["hops"]) == len(before["hops"])


def test_a_candidate_hop_on_real_sql_reports_rank_and_n(ledger):
    rows = straight_chain(LOTS, SLOTS, WAFERS)
    rows += [
        atom("df-L-D-alt1", "L-D", "derived_from", {"lot": "L-ALT1"},
             occurred_at=T0 + timedelta(days=1)),
        atom("df-L-D-alt2", "L-D", "derived_from", {"lot": "L-ALT2"},
             occurred_at=T0 + timedelta(days=1)),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        answer = trace_on(conn, "L-D", "3")
    hop = [h for h in answer["hops"] if h["predicate"] == "derived_from"][0]
    assert hop["state"] == "candidate"
    assert (hop["rank"], hop["n"]) == (1, 3)
    for name in ("L-C", "L-ALT1", "L-ALT2"):
        assert name in hop["reason"]


def test_a_confirmed_claim_beats_a_newer_observation_on_real_sql(ledger):
    """§6's class boundary, with `timestamptz` doing the comparing rather than
    a Python datetime — the level a naive/aware mix would have broken."""
    rows = [
        atom("reg", "L-D", "register", {}),
        atom("conf", "L-D", "derived_from", {"lot": "L-TRUE"},
             occurred_at=T0 - timedelta(days=300), who="chain_confirm"),
        atom("obs", "L-D", "derived_from", {"lot": "L-WRONG"},
             occurred_at=T0 + timedelta(days=300), who="user"),
        atom("reg-t", "L-TRUE", "register", {}),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        answer = trace_on(conn, "L-D", config=CONFIRMED_CFG)
    hop = [h for h in answer["hops"] if h["predicate"] == "derived_from"][0]
    assert hop["to"]["keys"]["lot"] == "L-TRUE"
    # The observation named a DIFFERENT parent, so the hop reports the contest —
    # but the ranking is not in doubt and the confirmed claim is what is followed.
    assert hop["state"] == "candidate"
    assert hop["n"] == 2
    assert "하위 계급 반대" in hop["reason"] and "L-WRONG" in hop["reason"]


def test_totality_survives_a_round_trip_through_postgres(ledger):
    """Two atoms equal on class, source and `occurred_at`, differing only in id.

    Run repeatedly with the rows physically reordered between runs, because the
    defect this level exists to stop was PHYSICAL ORDER deciding the answer.
    """
    a, b = sorted([_uuid("tie-a"), _uuid("tie-b")])
    rows = [
        atom("reg", "L-D", "register", {}),
        raw_atom(a, "L-D", "derived_from", {"lot": "P-FIRST-ID"}),
        raw_atom(b, "L-D", "derived_from", {"lot": "P-SECOND-ID"}),
    ]
    answers = set()
    for i in range(6):
        with ledger.begin() as conn:
            conn.execute(text("TRUNCATE ledger_events"))
            insert(conn, rows if i % 2 == 0 else list(reversed(rows)))
            hop = [h for h in trace_on(conn, "L-D")["hops"]
                   if h["predicate"] == "derived_from"][0]
            answers.add((hop["to"]["keys"]["lot"], hop["event_id"], hop["n"]))
    assert answers == {("P-FIRST-ID", a, 2)}, f"the answer moved: {answers}"


def test_the_partition_key_forbids_a_pk_on_id_alone(ledger):
    """🔴 A contract fact L1 and the resolver both depend on, asked of the engine.

    "`id` is a unique primary key so the last tiebreak always decides" is the
    obvious totality argument and it is not available: a table partitioned on
    `occurred_at` cannot have a unique constraint that omits `occurred_at`. The
    resolver's totality therefore rests on levels 2b+3 being JOINTLY the primary
    key, which is a different claim, and this test is what stops it from being
    quietly assumed back.
    """
    import sqlalchemy.exc
    with ledger.begin() as conn:
        with pytest.raises(sqlalchemy.exc.DatabaseError):
            conn.execute(text(
                "CREATE TABLE l2_pk_probe (id uuid NOT NULL, "
                "occurred_at timestamptz NOT NULL, PRIMARY KEY (id)) "
                "PARTITION BY RANGE (occurred_at)"))
    with ledger.begin() as conn:
        conn.execute(text(
            "CREATE TABLE l2_pk_probe (id uuid NOT NULL, "
            "occurred_at timestamptz NOT NULL, PRIMARY KEY (id, occurred_at)) "
            "PARTITION BY RANGE (occurred_at)"))
        conn.execute(text("DROP TABLE l2_pk_probe"))


def test_a_repeated_id_at_a_different_time_is_still_ordered(ledger):
    """The row the primary key above CANNOT forbid, resolved deterministically.

    Seen for real: a demo translation of `assy_qa`'s `lot_event` minted the same
    logical atom from two source rows with different `event_time`, and both rows
    landed. Level 2b separates them, so the answer does not move.
    """
    dup = _uuid("dup-id")
    rows = [
        atom("reg", "L-D", "register", {}),
        raw_atom(dup, "L-D", "derived_from", {"lot": "P-OLD"}, occurred_at=T0),
        raw_atom(dup, "L-D", "derived_from", {"lot": "P-NEW"},
                 occurred_at=T0 + timedelta(days=1)),
    ]
    seen = set()
    for i in range(4):
        with ledger.begin() as conn:
            conn.execute(text("TRUNCATE ledger_events"))
            insert(conn, rows if i % 2 == 0 else list(reversed(rows)))
            hop = [h for h in trace_on(conn, "L-D")["hops"]
                   if h["predicate"] == "derived_from"][0]
            seen.add((hop["to"]["keys"]["lot"], hop["n"]))
    assert seen == {("P-NEW", 2)}, f"a repeated id made the answer move: {seen}"


#: 🔴 The acceptance datum, end to end. Source text `2026-05-03 02:17:00` is a
#: local Asia/Seoul wall clock; it stores as `2026-05-02T17:17:00+00:00`; the
#: screen must show `2026-05-03 02:17`, matching the source exactly.
ACCEPTANCE_SOURCE_TEXT = "2026-05-03 02:17:00"
ACCEPTANCE_INSTANT = datetime(2026, 5, 2, 17, 17, 0, tzinfo=timezone.utc)
ACCEPTANCE_RENDERED = "2026-05-03T02:17:00+09:00"


def test_the_rendered_time_matches_the_source_document(ledger):
    with ledger.begin() as conn:
        insert(conn, [
            atom("reg", "L-D", "register", {}, occurred_at=ACCEPTANCE_INSTANT),
            atom("hw", "L-D", "has_wafer", {"slot": "3", "wafer": "WF.01"},
                 occurred_at=ACCEPTANCE_INSTANT),
        ])
        answer = trace_on(conn, "L-D", "3")
    hop = [h for h in answer["hops"] if h["predicate"] == "has_wafer"][0]
    assert hop["occurred_at"] == ACCEPTANCE_RENDERED
    assert hop["occurred_at"][:19].replace("T", " ") == ACCEPTANCE_SOURCE_TEXT


def test_the_rendered_time_does_not_depend_on_the_postgres_session_timezone(ledger):
    """🔴 THE TEST THAT WOULD HAVE CAUGHT THE ACCIDENT.

    Before the display zone was declared, `_iso` emitted an aware value verbatim,
    so the offset came from the PostgreSQL SESSION's TimeZone. `assy_qa`'s default
    is `Asia/Seoul`, so the acceptance condition passed while nothing the ledger
    declares was doing the work — and on a box whose PostgreSQL `TimeZone` is UTC
    the same atom would have rendered nine hours off, from a completely different
    cause than the bug that had just been fixed.

    So the session is FORCED to three different zones, including UTC, and the
    rendered string must not move. Setting `TimeZone` here is the whole point:
    a test that only ever ran under the box's default could not tell a declared
    zone from an inherited one.
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
            answer = trace_on(conn, "L-D", "3")
        hop = [h for h in answer["hops"] if h["predicate"] == "has_wafer"][0]
        rendered[session_zone] = (hop["occurred_at"], probe.isoformat())

    # The driver really did hand back three different offsets - otherwise this
    # test proves nothing about the code.
    driver_offsets = {v[1] for v in rendered.values()}
    assert len(driver_offsets) == 3, (
        f"the session TimeZone did not change what psycopg2 returned, so this "
        f"scenario does not discriminate: {driver_offsets}")

    assert {v[0] for v in rendered.values()} == {ACCEPTANCE_RENDERED}, (
        f"the rendered time follows the PostgreSQL session TimeZone: {rendered}")


def test_an_unusable_display_timezone_is_refused_rather_than_defaulted(ledger):
    """A display zone that silently became UTC is the failure being designed out,
    and a screen rendering a fab record in the wrong zone looks entirely normal."""
    broken = dict(lt.DEFAULT_RESOLVER_CONFIG, display_timezone="Mars/Olympus")
    with ledger.begin() as conn:
        insert(conn, [atom("reg", "L-D", "register", {})])
        with pytest.raises(lt.ResolverConfigError):
            trace_on(conn, "L-D", "3", config=broken)


def test_supersedes_is_honoured_against_real_uuid_columns(ledger):
    rows = [
        atom("reg", "L-D", "register", {}),
        atom("wrong", "L-D", "derived_from", {"lot": "L-WRONG"},
             occurred_at=T0 + timedelta(days=10), who="user"),
        atom("fix", "L-D", "derived_from", {"lot": "L-RIGHT"},
             occurred_at=T0, who="zz_file.csv", supersedes="wrong"),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        answer = trace_on(conn, "L-D")
    hop = [h for h in answer["hops"] if h["predicate"] == "derived_from"][0]
    assert hop["to"]["keys"]["lot"] == "L-RIGHT" and hop["n"] == 1


def test_a_cycle_in_the_ledger_does_not_spin_the_cte(ledger):
    """Without the `CYCLE` clause this recursion has no floor but the depth cap,
    and a genuine loop would be reported as `depth_cap` — the screen would say
    "the chain continues" about a chain that eats itself."""
    rows = [
        atom("r1", "L-A", "register", {}), atom("r2", "L-B", "register", {}),
        atom("d1", "L-A", "derived_from", {"lot": "L-B"}),
        atom("d2", "L-B", "derived_from", {"lot": "L-A"}),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        t0 = time.perf_counter()
        answer = trace_on(conn, "L-A")
        elapsed = time.perf_counter() - t0
    assert "cycle" in answer["terminal_reason"]
    assert elapsed < 2.0, "the CTE did not stop at the cycle"


def test_an_empty_ledger_table_still_answers(ledger):
    with ledger.begin() as conn:
        answer = trace_on(conn, "L-NOTHING", "3")
    assert len(answer["hops"]) == 1
    assert answer["hops"][0]["state"] == "unresolvable"
    assert "unknown_subject" in answer["terminal_reason"]


# ---------------------------------------------------------------------------
# 🔴 THE SEAM — the lookup is replaceable, demonstrated rather than asserted
# ---------------------------------------------------------------------------

def test_the_sql_lookup_and_an_in_memory_lookup_give_the_identical_answer(ledger):
    """The swappability of the lookup, as a CHECKED property.

    `SqlClaimLookup` overrides `neighbourhood` with one recursive CTE;
    `InMemoryClaimLookup` implements only the two primitives and inherits the
    default `neighbourhood`. Both feed the same resolver, and the two answers
    must be byte-identical apart from `generated_at`. A materialised lookup for
    week 2's slot-level lineage (452 ms inline vs 0.58 ms materialised, measured)
    slots into exactly this hole: implement the two primitives, change nothing
    else.
    """
    rows = straight_chain(LOTS, SLOTS, WAFERS)
    rows += [
        atom("df-L-D-alt", "L-D", "derived_from", {"lot": "L-ALT"},
             occurred_at=T0 + timedelta(days=1)),
        atom("conf-L-C", "L-C", "has_wafer",
             {"slot": "7", "wafer": "W-C-CONFIRMED"},
             occurred_at=T0 - timedelta(days=90), who="chain_confirm"),
    ]
    with ledger.begin() as conn:
        insert(conn, rows)
        sql_answer = trace_on(conn, "L-D", "3", config=CONFIRMED_CFG)
        # the SAME claims, pulled out flat, served from memory
        flat = lt.SqlClaimLookup(conn, "ledger_events").claims_for_lots(
            LOTS + ["L-ALT"])
    mem_answer = lt.trace("L-D", "3", lookup=lt.InMemoryClaimLookup(flat),
                          config=CONFIRMED_CFG)

    assert sql_answer["hops"] == mem_answer["hops"]
    assert sql_answer["terminal_reason"] == mem_answer["terminal_reason"]
    # and the interesting hops really were exercised
    kinds = {(h["predicate"], h["state"]) for h in sql_answer["hops"]}
    assert ("derived_from", "candidate") in kinds
    assert ("has_wafer", "resolved") in kinds


def test_the_one_shot_cte_and_the_two_primitives_ask_the_same_question(ledger):
    """`OneShotSqlClaimLookup` is an optimisation of the two primitives — a
    rejected one (see its docstring), but it must still be the SAME question.

    Kept as a test because it is what makes the default path's answer checkable
    against an independently written query rather than against itself.
    """
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        default = lt.SqlClaimLookup(conn, "ledger_events")
        one_shot = lt.OneShotSqlClaimLookup(conn, "ledger_events")
        nb_default = default.neighbourhood("L-D", max_depth=lt.DEFAULT_MAX_DEPTH)
        nb_one_shot = one_shot.neighbourhood("L-D", max_depth=lt.DEFAULT_MAX_DEPTH)
        answer_default = trace_on(conn, "L-D", "3")
        answer_one_shot = lt.trace("L-D", "3", lookup=one_shot,
                                   config=lt.DEFAULT_RESOLVER_CONFIG)

    assert sorted(nb_default.lots) == sorted(nb_one_shot.lots)
    assert sorted(c.id for c in nb_default.claims) == \
        sorted(c.id for c in nb_one_shot.claims)
    assert nb_default.truncated is False and nb_one_shot.truncated is False
    assert answer_default["hops"] == answer_one_shot["hops"]


def test_a_diamond_genealogy_does_not_duplicate_claims(ledger):
    """A lot reached by TWO paths must be fetched once, not once per path.

    A MERGE gives exactly this shape, so it is not a corner case — it is half of
    what `lot_event` contains. Duplicated claims would not change the winner
    (they carry the same answer), which is what makes this quiet: the hop would
    stay `resolved` and only the witness count in the reason would inflate. That
    is a number a human reads off this screen, so it has to be true.

    Added after mutation scoring: removing the `GROUP BY lot` from the CTE left
    the whole suite GREEN, because every fixture until this one was a straight
    chain.
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
        default_nb = lt.SqlClaimLookup(conn, "ledger_events").neighbourhood("L-D")
        one_shot_nb = lt.OneShotSqlClaimLookup(
            conn, "ledger_events").neighbourhood("L-D")
        answer = trace_on(conn, "L-D", "1")

    for label, nb in (("default", default_nb), ("one-shot", one_shot_nb)):
        ids = [c.id for c in nb.claims]
        assert len(ids) == len(set(ids)), (
            f"{label} lookup returned L-A's claims once per path: "
            f"{len(ids)} rows, {len(set(ids))} distinct")
        assert sorted(nb.lots) == ["L-A", "L-B1", "L-B2", "L-D"]

    # L-A is the lot reached twice; its wafer is stated by exactly ONE atom and
    # the answer must say so.
    a_hop = [h for h in answer["hops"]
             if h["predicate"] == "has_wafer" and h["from"]["keys"]["lot"] == "L-A"]
    assert len(a_hop) == 1
    assert a_hop[0]["state"] == "resolved"
    assert "[single]" in a_hop[0]["reason"], (
        f"one atom reported as several: {a_hop[0]['reason']!r}")


def test_the_relation_name_is_the_only_thing_that_moves(ledger):
    """Pointing the walk at a different relation is one constructor argument.
    Here that relation is a VIEW, which is the crudest possible stand-in for the
    materialised table week 2 will need."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        conn.execute(text(
            "CREATE OR REPLACE VIEW ledger_projection AS "
            "SELECT * FROM ledger_events"))
        try:
            direct = lt.trace("L-D", "3",
                              lookup=lt.SqlClaimLookup(conn, "ledger_events"),
                              config=lt.DEFAULT_RESOLVER_CONFIG)
            swapped = lt.trace("L-D", "3",
                               lookup=lt.SqlClaimLookup(conn, "ledger_projection"),
                               config=lt.DEFAULT_RESOLVER_CONFIG)
        finally:
            conn.execute(text("DROP VIEW IF EXISTS ledger_projection"))
    assert direct["hops"] == swapped["hops"]


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


def test_the_route_serves_the_pinned_shape(ledger_client, ledger):
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))

    resp = ledger_client.get("/api/ledger/trace", params={"lot": "L-D", "slot": "3"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json"), (
        "the route was shadowed by the SPA catch-all and served index.html - "
        "include_router must stay ABOVE it in main.py")
    body = resp.json()
    assert set(body) == {"hops", "terminal_reason", "generated_at"}
    assert len(body["hops"]) == 11
    assert [h["to"]["keys"]["lot"] for h in body["hops"]
            if h["predicate"] == "derived_from" and h["to"]] == ["L-C", "L-B", "L-A"]
    assert "root" in body["terminal_reason"]


def test_the_route_reports_a_break_rather_than_an_empty_answer(ledger_client, ledger):
    """🔴 A broken chain is a 200 that SAYS where it broke. Not a 404, not `[]`."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
        conn.execute(text("DELETE FROM ledger_events WHERE id = CAST(:i AS uuid)"),
                     {"i": _uuid("hw-L-B")})

    resp = ledger_client.get("/api/ledger/trace", params={"lot": "L-D", "slot": "3"})
    assert resp.status_code == 200
    body = resp.json()
    broken = [h for h in body["hops"] if h["state"] == "unresolvable"]
    assert broken, "the break was not reported at all"
    named = [h for h in broken if h["predicate"] == "has_wafer"]
    assert len(named) == 1
    assert "lot=L-B" in named[0]["reason"] and "slot=11" in named[0]["reason"]


def test_the_route_answers_for_a_lot_the_ledger_never_heard_of(ledger_client, ledger):
    resp = ledger_client.get("/api/ledger/trace", params={"lot": "L-GHOST", "slot": "1"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["hops"]) == 1
    assert body["hops"][0]["state"] == "unresolvable"
    assert "unknown_subject" in body["terminal_reason"]


def test_the_route_works_without_a_slot(ledger_client, ledger):
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    body = ledger_client.get("/api/ledger/trace", params={"lot": "L-D"}).json()
    assert {h["predicate"] for h in body["hops"]} == {"derived_from"}
    assert len(body["hops"]) == 4


def test_the_route_refuses_a_request_with_no_lot(ledger_client):
    assert ledger_client.get("/api/ledger/trace").status_code == 422
    assert ledger_client.get("/api/ledger/trace",
                             params={"lot": "  "}).status_code == 422


# ---------------------------------------------------------------------------
# Cost — interleaved arms
# ---------------------------------------------------------------------------

def _build_synthetic_ledger(conn, relation, n_chains, chain_len=5,
                            span_days=None, start=None):
    """`n_chains` independent chains of `chain_len` lots each, one wafer per lot.

    Atoms per chain: chain_len register + chain_len has_wafer +
    (chain_len-1) derived_from + (chain_len-1) slot_map.

    The lot names do NOT carry the size, so arm A and arm B ask the IDENTICAL
    question of two differently sized ledgers. If the name encoded the arm, the
    two arms would be two different questions and the ratio would be noise.
    """
    rows = []
    for i in range(n_chains):
        lots = [f"C{i}-{d}" for d in range(chain_len)]
        for d, lot in enumerate(lots):
            offset = i * chain_len + d
            if span_days is not None:   # keep every atom in one month
                offset %= 60 * 24 * span_days
            when = (T0 if start is None else start) + timedelta(minutes=offset)
            # Through `raw_atom`, so the COST is measured on the real payload
            # shape. A cost measured on flat payloads would be measuring a
            # jsonb path one operator shorter than the one that ships.
            rows.append(raw_atom(_uuid(f"{relation}/{lot}/reg"), lot,
                                 "register", {}, occurred_at=when))
            rows.append(raw_atom(_uuid(f"{relation}/{lot}/hw"), lot, "has_wafer",
                                 {"slot": str(d + 1), "wafer": f"W-{lot}"},
                                 occurred_at=when))
            if d + 1 < chain_len:
                parent = lots[d + 1]
                rows.append(raw_atom(_uuid(f"{relation}/{lot}/df"), lot,
                                     "derived_from", {"lot": parent},
                                     occurred_at=when))
                rows.append(raw_atom(_uuid(f"{relation}/{lot}/sm"), lot,
                                     "slot_map",
                                     {"lot": parent, "from": str(d + 1),
                                      "to": str(d + 2), "wafer": f"W-{lot}"},
                                     occurred_at=when))
    sql_rel = relation
    for start in range(0, len(rows), 2000):
        conn.execute(text(
            f"INSERT INTO {sql_rel} (id, subject_type, subject_keys, predicate, "
            f"object_kind, object_payload, occurred_at, source_who, "
            f"source_translator_ver, source_raw_ref, supersedes) VALUES "
            f"(CAST(:id AS uuid), :st, CAST(:sk AS jsonb), :p, :ok, "
            f" CAST(:op AS jsonb), :oa, :who, :ver, :raw, CAST(:sup AS uuid))"),
            rows[start:start + 2000])
    return len(rows)


def _create_ledger_like(conn, relation, months=None):
    """A second relation with the SHIPPED shape under a different name.

    Derived from `ledger.schema`'s own statements by renaming the relation and
    its indexes, rather than by keeping a second copy of the DDL here. The cost
    numbers are then measured against the constraints, index set and partition
    grain that actually ship — a probe against a leaner table would report a
    write and read cost nobody will ever see.
    """
    conn.execute(text(f"DROP TABLE IF EXISTS {relation} CASCADE"))

    def rename(sql):
        return (sql.replace(ledger_schema.LEDGER_TABLE, relation)
                   .replace("idx_ledger_", f"idx_{relation}_")
                   .replace("uq_ledger_", f"uq_{relation}_")
                   .replace("ck_ledger_", f"ck_{relation}_"))

    conn.execute(text(rename(ledger_schema.CREATE_LEDGER)))
    for stmt in ledger_schema.INDEXES:
        conn.execute(text(rename(stmt)))
    for when in (FIXTURE_MONTHS if months is None else months):
        conn.execute(text(rename(ledger_schema.create_partition_sql(when))))


@pytest.mark.skipif(
    not os.environ.get("ASSY_LEDGER_COST_PROBE"),
    reason="cost probe; set ASSY_LEDGER_COST_PROBE=1")
def test_trace_cost_tracks_partition_count_not_ledger_size(ledger, capsys):
    """🔴 What this walk actually costs is PARTITIONS, not atoms.

    The walk carries no `occurred_at` predicate — "everything about this lot" has
    no time bound — so partition pruning can never fire and EVERY partition is
    visited on every hop. `ledger.schema` says exactly this in its own comment
    about `idx_ledger_subject_lot`; this measures the price.

    Two relations, IDENTICAL atoms (18,000, all inside one month), differing only
    in how many monthly partitions exist. If cost tracked data, the two would be
    equal.

    🔴 Synthetic, on this box. NOT production evidence. It does not argue against
    the monthly grain — pruning and detaching are decided by other queries and by
    storage — it prices this one query under it, so the number is on the table
    when week 2 decides whether the slot-level chain gets materialised.
    """
    # The single partition and the data must be the SAME month, or the
    # insert fails on the partition key instead of measuring anything.
    one_month_start = datetime(2026, 6, 2, tzinfo=timezone.utc)
    same_month = [one_month_start]
    five_years = [datetime(y, m, 15, tzinfo=timezone.utc)
                  for y in range(2023, 2028) for m in range(1, 13)]
    try:
        with ledger.begin() as conn:
            _create_ledger_like(conn, "ledger_1part", months=same_month)
            _create_ledger_like(conn, "ledger_60part", months=five_years)
            for rel in ("ledger_1part", "ledger_60part"):
                _build_synthetic_ledger(conn, rel, 1000, span_days=20,
                                        start=one_month_start)
                conn.execute(text(f"ANALYZE {rel}"))

        arms = [("1 partition ", "ledger_1part"), ("60 partitions", "ledger_60part")]
        per = {a[0]: [] for a in arms}
        rounds = 40
        with ledger.connect() as conn:
            for name, rel in arms:
                lt.trace("C0-0", "1", lookup=lt.SqlClaimLookup(conn, rel),
                         config=lt.DEFAULT_RESOLVER_CONFIG)
            for r in range(rounds):
                for name, rel in (arms if r % 2 == 0 else list(reversed(arms))):
                    t0 = time.perf_counter()
                    answer = lt.trace(f"C{(r * 37) % 1000}-0", "1",
                                      lookup=lt.SqlClaimLookup(conn, rel),
                                      config=lt.DEFAULT_RESOLVER_CONFIG)
                    per[name].append((time.perf_counter() - t0) * 1000.0)
                    assert len(answer["hops"]) == 14

        lines = ["[partition cost] identical 18,000 atoms, 14 hops/trace, "
                 f"{rounds} rounds, order alternated"]
        for name, _ in arms:
            s = sorted(per[name])
            lines.append(f"  {name}: {statistics.median(s):6.2f} ms/trace  "
                         f"{statistics.median(s) / 14:6.3f} ms/hop")
        a = statistics.median(per[arms[0][0]])
        b = statistics.median(per[arms[1][0]])
        lines.append(f"  60x partitions -> {b / a:.2f}x per trace "
                     f"(+{(b - a) / 59:.3f} ms per extra partition)")
        with capsys.disabled():
            print("\n" + "\n".join(lines))

        assert b > a * 2, (
            "the partition count stopped mattering - either pruning started "
            "firing (it cannot, there is no time predicate) or this probe broke")
    finally:
        with ledger.begin() as conn:
            for rel in ("ledger_1part", "ledger_60part"):
                conn.execute(text(f"DROP TABLE IF EXISTS {rel} CASCADE"))


@pytest.mark.skipif(
    not os.environ.get("ASSY_LEDGER_COST_PROBE"),
    reason="cost probe builds a ~400k-atom ledger; set ASSY_LEDGER_COST_PROBE=1")
def test_cost_per_hop_at_two_ledger_sizes_interleaved(ledger, capsys):
    """Per-hop cost at two ledger sizes, measured with the arms INTERLEAVED.

    🔴 Sequential arms are how a lane reported 24.9% today where the real figure
    was 7-15%: the box drifts (cache warmth, other lanes, the OS) and a
    sequential A-then-B assigns all of that drift to B. Arms here alternate
    A,B,A,B within one loop and the reported figure is the per-arm MEDIAN, so
    drift lands on both arms.

    The two arms are two SEPARATE RELATIONS of the same shape - which is only
    possible because the relation is the lookup's seam. Two sizes sharing one
    table would not be two ledger sizes at all: both traces would scan the same
    heap and the ratio would measure nothing.

    Four arms, because the interesting comparison turned out to be TWO
    comparisons at once: ledger size AND which lookup. The default
    `SqlClaimLookup` (two round trips) against `OneShotSqlClaimLookup` (one),
    each at 18k and 360k atoms.

    🔴 Synthetic, on this box, one process. NOT production evidence.
    """
    small, big = 1000, 20000              # 20x, the ratio §7-bis reported on
    try:
        with ledger.begin() as conn:
            _create_ledger_like(conn, "ledger_small")
            _create_ledger_like(conn, "ledger_big")
            n_small = _build_synthetic_ledger(conn, "ledger_small", small)
            n_big = _build_synthetic_ledger(conn, "ledger_big", big)
            # 🔴 ANALYZE, explicitly. A table with no statistics makes the
            # planner invent a seq scan and a fake "scale is non-linear" with
            # it - the instrument fault caught on 2026-08-12.
            conn.execute(text("ANALYZE ledger_small"))
            conn.execute(text("ANALYZE ledger_big"))

        sizes = {"ledger_small": n_small, "ledger_big": n_big}
        with ledger.connect() as conn:
            arms = []
            for relation, n in (("ledger_small", small), ("ledger_big", big)):
                arms.append((f"2step/{relation}", lt.SqlClaimLookup(conn, relation), n))
                arms.append((f"1shot/{relation}",
                             lt.OneShotSqlClaimLookup(conn, relation), n))
            per_trace = {name: [] for name, _, _ in arms}

            for name, lookup, n in arms:        # warm-up, discarded
                lt.trace("C0-0", "1", lookup=lookup,
                         config=lt.DEFAULT_RESOLVER_CONFIG)

            rounds = 40
            for r in range(rounds):
                # 🔴 The order within the round ROTATES. Interleaving in a FIXED
                # order still hands arm 1 every first-in-round cost there is -
                # a position bias wearing an interleaving costume, and it is
                # what the first run of this probe was reporting.
                k = r % len(arms)
                for name, lookup, n in arms[k:] + arms[:k]:
                    lot = f"C{(r * 37) % n}-0"
                    t0 = time.perf_counter()
                    answer = lt.trace(lot, "1", lookup=lookup,
                                      config=lt.DEFAULT_RESOLVER_CONFIG)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    assert len(answer["hops"]) == 14, \
                        f"{name}: {len(answer['hops'])} hops, expected 14"
                    per_trace[name].append(elapsed_ms)

        lines = [f"[ledger trace cost] {rounds} rounds, order ROTATED each round, "
                 f"5-lot chain = 14 hops/trace",
                 f"  ledger sizes: {sizes}"]
        for name, _, _ in arms:
            t = sorted(per_trace[name])
            lines.append(
                f"  {name:22s} {statistics.median(t):6.2f} ms/trace  "
                f"{statistics.median(t)/14:6.3f} ms/hop  "
                f"(p10 {t[len(t)//10]:6.2f} / p90 {t[(len(t)*9)//10]:6.2f})")
        for tag in ("2step", "1shot"):
            a = statistics.median(per_trace[f"{tag}/ledger_small"])
            b = statistics.median(per_trace[f"{tag}/ledger_big"])
            lines.append(f"  {tag}: 20x ledger -> {b / a:.2f}x")

        # 🔴 The number is not reported without the PLAN behind it. A per-hop
        # cost that goes DOWN as the ledger grows 20x is not a scaling result,
        # it is two different plans, and saying which is the difference between
        # a measurement and a rumour.
        with ledger.connect() as conn:
            for relation in ("ledger_small", "ledger_big"):
                plan = conn.exec_driver_sql(
                    "EXPLAIN (ANALYZE) "
                    + lt._TRACE_CTE.format(relation=relation),
                    {"start_lot": "C7-0", "max_depth": 20,
                     "predicates": list(lt.LINEAGE_PREDICATES)}).fetchall()
                joins = [ln[0].strip() for ln in plan
                         if ln[0].strip().startswith(("Hash Join", "Nested Loop",
                                                      "Merge Join"))]
                lines.append(f"  1shot/{relation} outer join: "
                             f"{joins[0].split('(')[0].strip() if joins else '?'}")
        with capsys.disabled():
            print("\n" + "\n".join(lines))

        # 🔴 The gate that matters is FLATNESS of the default path, not an
        # absolute threshold invented to be passed. A 20x ledger that costs more
        # than 2x per trace means the walk is reading the ledger rather than
        # indexing into it, and that is the failure this design has to avoid.
        ratio = (statistics.median(per_trace["2step/ledger_big"])
                 / statistics.median(per_trace["2step/ledger_small"]))
        assert ratio < 2.0, (
            f"the default lookup is not flat across a 20x ledger: {ratio:.2f}x")
        assert statistics.median(per_trace["2step/ledger_big"]) / 14 < 50.0
    finally:
        with ledger.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS ledger_small CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS ledger_big CASCADE"))
