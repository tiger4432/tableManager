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
         supersedes=None, derivation=None):
    """One row of `ledger_events`. `derivation` stamps `source_translator_ver`'s
    `#<derivation>` suffix — the ONLY place an atom's basis lives, which is why a
    convention-backed fixture stamps it here and not in a column that does not
    exist."""
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
    # The class DECLARED this winner, so the word is `contested` (R-2026-08-13-B
    # week 2), not the `candidate` umbrella it sheltered under for slice 1.
    assert hop["state"] == lt.STATE_CONTESTED
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
# 🔴 The EXPANDED contract, on the wire — R-2026-08-13-B week 2 + R-2026-08-13-C
# ---------------------------------------------------------------------------

def _contested_by_convention(lots, slots, wafers):
    """A chain whose FIRST slot hop has a measurement and a convention that
    DISAGREE — the real shape, and the one the default resolver config produces.

    Deliberately not built out of a class-1 claim: the ROUTE loads the shipped
    resolver config, whose class 1 is `frame_confirmed`, and no translator emits
    that yet. Class 2 over class 3 is the contest that actually happens today —
    `slot_preserving` is an ASSUMPTION (class 3) and any uttered mapping outranks
    it, which is the ontology owner's ruling doing its job.
    """
    rows = straight_chain(lots, slots, wafers)
    rows.append(atom("sm-conv", lots[0], "slot_map",
                     # the assumption: "a split keeps its slot numbers"
                     {"lot": lots[1], "from": slots[0], "to": slots[0]},
                     derivation="slot_preserving"))
    return rows


def test_the_route_puts_contested_and_basis_on_the_wire(ledger_client, ledger):
    """🔴 THE EXPANDED CONTRACT, END TO END, THROUGH REAL POSTGRESQL AND HTTP.

    Both fields at once, because they shipped in one commit on purpose — the
    route contract is not shaken twice.

      `state: "contested"`  a winner was DECLARED by the class and a lower class
                            still disagrees. Distinct from `candidate`, which is
                            "k answers at one authority, no winner declared".
      `basis: {kind, name}` what the WINNER rests on, as a field. The losing
                            convention is named in the prose of the same
                            sentence, and a consumer reading the prose gets it
                            BACKWARDS — that read inverted once already.
    """
    with ledger.begin() as conn:
        insert(conn, _contested_by_convention(LOTS, SLOTS, WAFERS))

    body = ledger_client.get("/api/ledger/trace",
                             params={"lot": "L-D", "slot": "3"}).json()

    hop = [h for h in body["hops"] if h["predicate"] == "slot_map"][0]
    assert hop["state"] == "contested", (
        f"a declared winner with a live contradiction under it must not read "
        f"'{hop['state']}': {hop['reason']}")
    assert hop["n"] == 2
    # The measurement won. `slot_preserving` would have kept slot 3.
    assert hop["to"]["slot"] == SLOTS[1] != SLOTS[0]

    # 🔴 THE INVERSION, ON THE WIRE. `convention:` is in the sentence and belongs
    # to the LOSER; the winner uttered its mapping and carries no derivation.
    assert "convention:slot_preserving" in hop["reason"], hop["reason"]
    assert hop["basis"] is None, (
        f"the losing convention leaked into the winner's basis: {hop['basis']}")

    # And every hop on the wire carries the key set, `basis` included.
    for h in body["hops"]:
        assert "basis" in h, "a hop reached the client without the field"
        assert h["basis"] is None or set(h["basis"]) == {"kind", "name"}
        assert h["state"] in lt.HOP_STATES


def test_the_route_carries_a_convention_basis_when_the_convention_WINS(
        ledger_client, ledger):
    """The other side of the branch, and the one the enrich graft acts on.

    With no measurement to overrule it the assumption IS the answer, and the hop
    is `resolved` — a state that says nothing at all about how much was assumed.
    THAT is why `basis` cannot be inferred from `state`: this hop and a fully
    measured one are the same word, and only the field tells them apart.
    """
    rows = straight_chain(LOTS, SLOTS, WAFERS)
    rows = [r for r in rows if r["id"] != _uuid(f"sm-{LOTS[0]}")]
    rows.append(atom("sm-conv", LOTS[0], "slot_map",
                     {"lot": LOTS[1], "from": SLOTS[0], "to": SLOTS[1]},
                     derivation="slot_preserving"))
    with ledger.begin() as conn:
        insert(conn, rows)

    body = ledger_client.get("/api/ledger/trace",
                             params={"lot": "L-D", "slot": "3"}).json()
    hop = [h for h in body["hops"] if h["predicate"] == "slot_map"][0]

    assert hop["state"] == "resolved", "nothing disagreed with it"
    assert hop["basis"] == {"kind": "convention", "name": "slot_preserving"}, (
        "the hop the graft may NEVER pre-mark confirmed is indistinguishable "
        "from a measured one without this field")


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


def test_every_sampled_lot_is_one_the_trace_can_actually_walk(ledger):
    """🔴 THE SAMPLE IS SCORED BY ITS CONSUMER, NOT BY ITS OWN SQL.

    A "try one of these" affordance that offered a lot with no lineage would
    demonstrate the very emptiness this endpoint exists to explain. So every
    sampled `(lot, slot)` is fed to the walk and required to produce a RESOLVED
    lineage hop and a resolved `has_wafer` hop — i.e. the screen opens on
    something, for both of the questions a slot makes askable.
    """
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    with ledger.connect() as conn:
        sample = _coverage(conn)["sample"]
        assert sample, "a ready ledger with three lineage links sampled nothing"
        for entry in sample:
            assert set(entry) == {"lot", "slot"}
            assert isinstance(entry["slot"], str) and entry["slot"]
            answer = trace_on(conn, entry["lot"], entry["slot"])
            resolved = [h for h in answer["hops"]
                        if h["predicate"] == "derived_from"
                        and h["state"] == "resolved"]
            assert resolved, (
                f"sampled lot {entry['lot']!r} produced no resolved lineage hop: "
                f"{answer['terminal_reason']}")
            wafer_hops = [h for h in answer["hops"] if h["predicate"] == "has_wafer"]
            assert wafer_hops and wafer_hops[0]["state"] == "resolved", (
                f"sampled slot {entry['slot']!r} is not one lot "
                f"{entry['lot']!r} holds")


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
        insert(conn, [atom("reg-LONELY", "L-LONELY", "register", {})])
    with ledger.connect() as conn:
        answer = _coverage(conn)
        assert answer["state"] == "ready"
        assert answer["lots"] == 1
        assert answer["sample"] == []
        known = trace_on(conn, "L-LONELY")
        unknown = trace_on(conn, "L-NEVER-SEEN")

    # The two facts live in two places, and BOTH are anchored rather than free
    # prose — `[root]` / `[unknown_subject]` in `terminal_reason`, and the
    # register marker on the hop that could not be resolved. A client branches on
    # the anchors (L3's provisional canon under R-2026-08-13-C); the sentence
    # around them is for the operator.
    assert known["terminal_reason"].startswith("[root]")
    assert unknown["terminal_reason"].startswith("[unknown_subject]")
    assert "register 있음" in known["hops"][-1]["reason"], known["hops"][-1]["reason"]
    assert known["terminal_reason"] != unknown["terminal_reason"], (
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


# --- the same distinctions, over HTTP ---------------------------------------

def test_the_coverage_route_serves_the_pinned_shape(ledger_client, ledger):
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    resp = ledger_client.get("/api/ledger/coverage")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json"), (
        "the route was shadowed by the SPA catch-all - include_router must stay "
        "ABOVE it in main.py")
    body = resp.json()
    assert set(body) == COVERAGE_KEYS
    assert body["state"] == "ready"
    assert body["lots"] == len(LOTS)
    assert set(body["occurred_at"]) == {"from", "to"}
    # The status strip's three signals, over HTTP, in ONE request. Asserted here and
    # not only against the function because the ruling's requirement is that the SCREEN
    # can read them from the body it already fetches — a field that serialises to
    # something FastAPI cannot encode would pass every in-process test and 500 here.
    assert body["atoms"]["exact"] is False, "the atom count must declare itself an estimate"
    assert body["partitions"]["count"] > 0
    assert set(body["last_atom"]) == {"occurred_at", "recorded_at"}
    assert isinstance(body["cursors"], list)


def test_the_coverage_route_answers_200_when_the_ledger_is_not_deployed(
        ledger_client, monkeypatch):
    """An absent ledger is an ANSWER over HTTP too. A 500 here is what the
    product owner would read as "the screen itself is broken"."""
    import ledger_trace_router as router_module
    monkeypatch.setattr(router_module, "LEDGER_RELATION", "ledger_events_not_migrated")
    monkeypatch.setattr(router_module, "LEDGER_CURSOR_RELATION",
                        "ledger_cursor_not_migrated")
    resp = ledger_client.get("/api/ledger/coverage")
    assert resp.status_code == 200
    assert resp.json()["state"] == "absent"


def test_the_trace_route_names_an_absent_ledger_in_a_field_not_in_prose(
        ledger_client, monkeypatch):
    """🔴 THE ALARM THAT HAD NEVER BEEN RUNG.

    The 503-for-an-absent-relation branch shipped with NO test, so nothing had
    ever driven it — and it did not work on this box: it matched the English
    words "does not exist" in the driver's message, while this PostgreSQL emits
    Korean. The relation is now judged by the catalogue and the body is
    machine-readable. This is the test that fires it.
    """
    import ledger_trace_router as router_module
    monkeypatch.setattr(router_module, "LEDGER_RELATION", "ledger_events_not_migrated")

    resp = ledger_client.get("/api/ledger/trace", params={"lot": "L-D", "slot": "3"})
    assert resp.status_code == 503
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
    """SITUATION 3 vs SITUATION 1, over HTTP. One is a 200 carrying a reason, the
    other a 503 carrying a machine-readable one. They must never coincide."""
    with ledger.begin() as conn:
        insert(conn, straight_chain(LOTS, SLOTS, WAFERS))
    resp = ledger_client.get("/api/ledger/trace",
                             params={"lot": "L-NEVER-SEEN", "slot": "1"})
    assert resp.status_code == 200
    assert "unknown_subject" in resp.json()["terminal_reason"]
