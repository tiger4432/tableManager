# -*- coding: utf-8 -*-
"""S-174. Two rows claiming one virtual join's key are refused BY NAME; the group SUCCEEDS.

Owner, 2026-09-11: 「중복된 키 값이 uq_vjoin_… 위반」 stopped a whole table's chain, and
「뭐가 문제인지 안 보인다, 너무 복잡하고 막는 게 많다」.

WHAT WAS WRONG WAS THE SHAPE OF THE REFUSAL, NOT THE DETECTION
--------------------------------------------------------------
A virtual join is approved only against a UNIQUE index on its right-side key, so that
table owes that uniqueness.  When a mapper emitted two rows sharing one such key, the
upsert failed on `uq_vjoin_<table>_<columns>` — a constraint that is NOT the statement's
`ON CONFLICT` target, so there is no `DO UPDATE` arm for it and the whole STATEMENT dies.
From there: the group failed, its events were quarantined, the quarantine re-expanded
them into a thousand per-row events, and the HOL guard held every other group behind that
table.  One row of data stopped one table, and the operator saw a driver error in Korean.

THE BEFORE-STATE IS RUN, NOT ASSERTED FROM A DOCSTRING
------------------------------------------------------
The fixture installs the real UNIQUE index, so `test_without_the_refusal_...` reproduces
the failure through the real worker funnel.  A test that only shows the fixed behaviour
cannot tell a working guard from one that never fires.

⚠️ WITHIN ONE BATCH.  A row colliding with one ALREADY STORED breaks the same index and
is not caught here; `test_a_collision_with_a_stored_row_is_not_caught_yet` pins that
boundary so it is a stated limit rather than a silent one.
"""
import asyncio
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from chain import ingestion_worker as worker                            # noqa: E402
from chain import mapper_call                                 # noqa: E402
import mapper_sdk                                                  # noqa: E402
from chain import legacy_join_declaration as vjc                                  # noqa: E402
from chain import legacy_materialized_join as vje                                # noqa: E402
from database.database import Base                                 # noqa: E402
from database import crud, models, schemas                         # noqa: E402
from database.models import DatabaseOutbox                         # noqa: E402


#: Prefixes that cannot exist in the user's own (gitignored) `table_config.json`.  A
#: collision lets `init_dynamic_models` win the race for the shared in-memory sqlite
#: schema and the suite fails with `no such column` — the `bonding_log` incident.
TRIGGER = "vjuq_test_trigger"
#: The RIGHT side of the join: the table that owes the uniqueness.
DERIVED = "vjuq_test_derived"
JOIN_COLUMN = "job_uid"
RULE_NAME = "vjuq_test_rule"
#: The name the migration would give the index.  Spelled through the product's own helper
#: rather than typed, so a change to that naming does not leave this fixture asserting a
#: constraint the product no longer builds.
INDEX_NAME = vjc.required_index_name(DERIVED, [JOIN_COLUMN])

TEST_TABLE_CONFIG = {
    TRIGGER: {
        "business_key": "src_key",
        "column_types": {"src_key": "string", "job": "string"},
    },
    DERIVED: {
        "business_key": "unit_key",
        "column_types": {"unit_key": "string", JOIN_COLUMN: "string",
                         "grade": "string"},
    },
}


@pytest.fixture(name="db")
def fixture_db():
    # StaticPool for the reason `test_chain_key_gate` states: 판정 193 moved this funnel's
    # work into `asyncio.to_thread`, and every connection to ":memory:" is its own empty
    # database, so without it the worker thread reads back "no such table".
    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.init_dynamic_models(TEST_TABLE_CONFIG)
    crud.TABLE_CONFIG.update(TEST_TABLE_CONFIG)

    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    # 🔴 THE INDEX IS REAL, AND THAT IS WHAT MAKES THE BEFORE-STATE RUNNABLE. Without it
    # the duplicate simply writes and every test here would be scoring an assertion about
    # a database that never refuses anything.
    with engine.begin() as conn:
        conn.execute(text('CREATE UNIQUE INDEX "%s" ON "%s" ("%s")'
                          % (INDEX_NAME, DERIVED, JOIN_COLUMN)))

    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(name="declared_join", autouse=True)
def fixture_declared_join(monkeypatch):
    """This table is the RIGHT side of an APPROVED join.

    🔴 SUPPLIED AT THE APPROVAL SEAM, AND IT HAS TO BE. Approval asks `pg_index` whether a
    UNIQUE index covers the join key, and `unique_index_covering` answers `None` on any
    dialect that is not PostgreSQL — 「모르면 거부」. So on sqlite no declaration is ever
    approved, and a fixture that only wrote the rules file would exercise nothing. The
    index above is real; this says what the catalogue would have said about it.
    """
    rule = {
        "name": RULE_NAME,
        "left_table": TRIGGER,
        "right_table": DERIVED,
        "join_key": [{"left": "job", "right": JOIN_COLUMN, "fold": None}],
        "left_columns": ["job"],
        "right_columns": [JOIN_COLUMN],
        "right_folds": [None],
        "folded": False,
        "expose": ["grade"],
        "join_cardinality": "one",
        "enabled": True,
    }
    monkeypatch.setattr(vjc, "load_virtual_join_rules", lambda *a, **kw: [rule])
    monkeypatch.setattr(vje, "rules_for_right",
                        lambda _db, right_table: [rule] if right_table == DERIVED else [])
    assert vje.rules_for_right(None, DERIVED) == [rule]
    assert vje.rules_for_right(None, TRIGGER) == []
    return rule


def _item(unit_key, job_uid, grade="A"):
    return schemas.GeneralUpdateItem(
        business_key_val=unit_key,
        updates={"unit_key": unit_key, JOIN_COLUMN: job_uid, "grade": grade},
        source_name="chain_ingestion", updated_by="chain_worker")


def _rows(db):
    return db.query(models.DYNAMIC_TABLES[DERIVED]).all()


def _push(db, items, report=None):
    batch = schemas.GeneralUpdateBatch(updates=items)
    return crud.apply_batch_updates(db, DERIVED, batch, drop_report=report)


# ---------------------------------------------------------------------------
# Driving the REAL worker funnel
# ---------------------------------------------------------------------------

#: The name this file's rules give their mapper. Registered per test, so the seat
#: resolves it the way it resolves any `@mapper` a file declares.
FAKE_MAPPER = "vjuq_fake_mapper"

def _run_chain(db, monkeypatch, mapper_result, tx="vjuq-tx"):
    event = DatabaseOutbox(event_uuid="vjuq-event", event_type="CREATE",
                           table_name=TRIGGER,
                           payload={"source_name": "user", "data": {}})
    rules = [{"name": RULE_NAME, "trigger_table": TRIGGER, "target_table": DERIVED,
              "mapper": FAKE_MAPPER, "is_batch": True, "enabled": True}]
    monkeypatch.setattr(worker.outbox_expand, "expand_events",
                        lambda _db, events: {worker.outbox_expand.event_key(e): [{"data": {}}]
                                             for e in events})
    # ⚰️ [판정 498] REGISTERED AS A MAPPER, NOT PATCHED OVER THE EXECUTOR. There is no
    #    `execute_custom_mapper` to replace any more - the seat resolves a rule's name itself -
    #    so the fake is put where the product LOOKS for a mapper. That is closer to the
    #    subject than the old patch was: the funnel now resolves this rule the same way it
    #    resolves a shipped one.
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, FAKE_MAPPER,
                        lambda _db, _payload, rule=None: mapper_result)
    return asyncio.run(worker.process_chain_transaction_group(tx, [event], db, rules))


def _mapper_output(items):
    return {"updates": [
        {"business_key_val": i.business_key_val, "updates": dict(i.updates),
         "source_name": "chain_ingestion"} for i in items]}


#: One batch: eight rows that are fine and two that both claim `J-DUP`.
def _batch_with_one_duplicate_pair():
    items = [_item("U%d" % n, "J-%d" % n) for n in range(8)]
    items.append(_item("U-A", "J-DUP", grade="A"))
    items.append(_item("U-B", "J-DUP", grade="B"))
    return items


# ---------------------------------------------------------------------------
# 1. The before-state: without the refusal the whole batch dies
# ---------------------------------------------------------------------------

def test_without_the_refusal_the_duplicate_pair_kills_the_whole_batch(db, monkeypatch):
    """KILLS: the claim that the constraint was survivable without this guard.

    Neutralised through `import`, and the substitution is asserted — a mutation that does
    not apply reports a hole as a catch.
    """
    monkeypatch.setattr(crud, "refuse_virtual_join_duplicates",
                        lambda db, table_name, batch: [])
    assert crud.refuse_virtual_join_duplicates(None, DERIVED, None) == []

    with pytest.raises(Exception):
        _push(db, _batch_with_one_duplicate_pair())
    # ⛔ AND THE EIGHT GOOD ROWS ARE GONE TOO. That is the defect: one row of data, and
    # the table's whole batch is on the floor. The rollback is the harness catching up
    # with the database, not part of the claim: the flush failed, so the session refuses
    # to read until it is told so.
    db.rollback()
    assert _rows(db) == []


# ---------------------------------------------------------------------------
# 2. With it: both are skipped by name and the rest are written
# ---------------------------------------------------------------------------

def test_the_pair_is_refused_and_the_other_eight_are_written(db):
    report = {}
    _push(db, _batch_with_one_duplicate_pair(), report=report)

    written = sorted(r.business_key_val for r in _rows(db))
    assert written == ["U%d" % n for n in range(8)], written
    assert report["rows_refused"][crud.DROP_UNIQUE_VIOLATED] == 2, report["rows_refused"]


def test_each_refused_row_is_told_which_other_row_claims_its_key(db):
    """⛔ A COUNT IS NOT FIXABLE. The operator has to open two rows, so the refusal names
    both — the one skipped and the one it collided with."""
    report = {}
    _push(db, _batch_with_one_duplicate_pair(), report=report)

    refusals = report["refusals"]
    assert sorted(r["row"] for r in refusals) == ["U-A", "U-B"]
    assert {r["rule"] for r in refusals} == {RULE_NAME}
    assert {r["reason"] for r in refusals} == {crud.DROP_UNIQUE_VIOLATED}
    by_row = {r["row"]: r for r in refusals}
    assert by_row["U-A"]["others"] == ["U-B"]
    assert by_row["U-B"]["others"] == ["U-A"]
    assert by_row["U-A"]["key"] == ["J-DUP"]
    assert JOIN_COLUMN in by_row["U-A"]["message"]
    assert "U-B" in by_row["U-A"]["message"]


def test_a_healthy_batch_refuses_nothing_and_reports_nothing(db):
    """A guard exercised only on the case that already fails proves nothing about the
    case that must stay untouched."""
    report = {}
    _push(db, [_item("U%d" % n, "J-%d" % n) for n in range(8)], report=report)

    assert len(_rows(db)) == 8
    assert report["refusals"] == []
    assert crud.DROP_UNIQUE_VIOLATED not in report["rows_refused"]


# ---------------------------------------------------------------------------
# 3. The discriminator: two ITEMS are not two ROWS
# ---------------------------------------------------------------------------

def test_one_row_named_twice_is_not_a_violation(db):
    """KILLS: refusing on payload equality rather than on row identity.

    Two items carrying the same business key land on ONE row — `unique_results` merges
    them before any statement is built — so nothing can violate anything, and refusing
    them would throw away a write the database would have accepted."""
    report = {}
    _push(db, [_item("U-SAME", "J-ONE", grade="A"),
               _item("U-SAME", "J-ONE", grade="B")], report=report)

    assert len(_rows(db)) == 1
    assert report["refusals"] == []
    assert _rows(db)[0].grade == "B", "the last writer is the value"


def test_a_payload_that_does_not_carry_the_join_key_is_not_judged(db):
    """⛔ NOT A VERDICT. A partial update may leave the key to the stored row, and
    refusing it would refuse a write that cannot break anything."""
    _push(db, [_item("U-KEYED", "J-ONE")])
    report = {}
    _push(db, [schemas.GeneralUpdateItem(
        business_key_val="U-KEYED", updates={"grade": "Z"},
        source_name="chain_ingestion", updated_by="chain_worker")], report=report)

    assert report["refusals"] == []
    assert _rows(db)[0].grade == "Z"


def test_a_collision_with_a_stored_row_is_refused_by_name_too(db):
    """⚰️ THIS TEST ASSERTED THE OPPOSITE UNTIL 2026-09-14, and the boundary it pinned
    (S-174 ①) is what a production outage was made of: a new row taking a key an EARLIER
    batch stored died on the index, and since `uq_vjoin_*` is not the statement's
    `ON CONFLICT` target it took the WHOLE push with it. Pinning the limit was right;
    living with it was not. Both halves now refuse by name, so the boundary is gone rather
    than documented."""
    _push(db, [_item("U-FIRST", "J-DUP")])
    report = {}
    _push(db, [_item("U-SECOND", "J-DUP")], report=report)

    assert sorted(r.business_key_val for r in _rows(db)) == ["U-FIRST"]
    assert report["rows_refused"][crud.DROP_UNIQUE_VIOLATED] == 1
    assert report["refusals"][0]["others"] == ["U-FIRST"]


# ---------------------------------------------------------------------------
# 4. The group SUCCEEDS — which is what keeps the table's chain moving
# ---------------------------------------------------------------------------

def test_the_chain_group_succeeds_and_names_the_refusal(db, monkeypatch, caplog):
    """🔴 THE WHOLE POINT OF ②. A failed group is quarantined, re-expanded per row, and
    held by the HOL guard; a SUCCESS group is none of those. So the one assertion that
    matters is that the group comes back SUCCESS with the bad pair skipped."""
    caplog.set_level("WARNING")
    ok, error, _messages = _run_chain(
        db, monkeypatch, _mapper_output(_batch_with_one_duplicate_pair()))

    assert ok is True and error is None
    assert sorted(r.business_key_val for r in _rows(db)) == ["U%d" % n for n in range(8)]
    line = [r.getMessage() for r in caplog.records
            if "[Chain Write Refusal]" in r.getMessage()]
    assert len(line) == 1, [r.getMessage() for r in caplog.records]
    assert "vjoin_refused=2" in line[0]
    assert "written=8" in line[0]
    assert RULE_NAME in line[0]


def test_without_the_refusal_the_same_group_fails(db, monkeypatch):
    """The other half of the same measurement: with the guard neutralised the group comes
    back False, which is the state that quarantines and then blocks the table."""
    monkeypatch.setattr(crud, "refuse_virtual_join_duplicates",
                        lambda db, table_name, batch: [])
    assert crud.refuse_virtual_join_duplicates(None, DERIVED, None) == []

    ok, error, _messages = _run_chain(
        db, monkeypatch, _mapper_output(_batch_with_one_duplicate_pair()))
    assert ok is False and error


# ---------------------------------------------------------------------------
# 5. The source of the keys: approved rules, indexed both ways, loaded once
# ---------------------------------------------------------------------------

def test_the_right_side_index_is_built_from_the_same_single_load(monkeypatch):
    """⛔ NOT A SECOND READ OF THE DECLARATION FILE. This runs on the write path once per
    batch; re-loading and re-validating the declaration file there is the inline work
    the standing performance rule forbids. Both directions come out of ONE pass, and this
    counts the passes rather than trusting the arrangement."""
    # The autouse fixture above substitutes `rules_for_right` for every other test here;
    # this one is about the real body, so its substitution is lifted first.
    monkeypatch.undo()
    assert vje.rules_for_right.__module__ == "chain.legacy_materialized_join"

    calls = []
    rule = {"name": "vjuq_shared", "left_table": TRIGGER, "right_table": DERIVED,
            "join_key": [{"left": "job", "right": JOIN_COLUMN, "fold": None}],
            "left_columns": ["job"], "right_columns": [JOIN_COLUMN],
            "right_folds": [None], "expose": ["grade"], "enabled": True}

    def _one_load(_db, known_tables=None):
        calls.append(1)
        return [rule]

    monkeypatch.setattr(vjc, "load_verified_rules", _one_load)
    vje.reset_cache()
    try:
        assert vje.rules_for(None, TRIGGER) == [rule]
        assert vje.rules_for_right(None, DERIVED) == [rule]
        assert len(calls) == 1, calls
        # And a table that is nobody's right side gets an empty answer rather than the
        # whole list - the filter is real, not a pass-through.
        assert vje.rules_for_right(None, TRIGGER) == []
    finally:
        vje.reset_cache()


def test_a_declaration_that_is_not_approved_refuses_nothing(db, monkeypatch):
    """🔴 THE DIRECTION THAT MATTERS. Approval means the UNIQUE index EXISTS; where it does
    not, a duplicate breaks nothing and refusing would be the guard throwing away rows the
    database would have written."""
    monkeypatch.setattr(vje, "rules_for_right", lambda _db, _t: [])
    report = {}
    # The index is still installed by the fixture, so this asks the narrow question -
    # does the REFUSAL follow the approval - rather than whether sqlite complains.
    with pytest.raises(Exception):
        _push(db, _batch_with_one_duplicate_pair(), report=report)
    db.rollback()
    assert report.get("refusals") in (None, [])


def test_a_replace_map_push_whose_every_row_is_refused_does_not_empty_the_map(db):
    """⛔ THE ONE PLACE THIS REFUSAL COULD DESTROY DATA. The purge runs BEFORE the refusal,
    so a `replace_map` push that ends with nothing to write would leave the scope deleted
    and unreplaced. Same ruling the key gate made for its own whole-batch refusal."""
    _push(db, [_item("U-KEEP", "J-KEEP")])
    assert len(_rows(db)) == 1

    batch = schemas.GeneralUpdateBatch(
        updates=[_item("U-A", "J-DUP"), _item("U-B", "J-DUP")],
        replace_map=True, scope={"unit_key": "U-KEEP"})
    with pytest.raises(ValueError) as caught:
        crud.apply_batch_updates(db, DERIVED, batch)
    assert "가상 조인" in str(caught.value)

    db.rollback()
    assert [r.business_key_val for r in _rows(db)] == ["U-KEEP"], (
        "the purge must have been unwound with the refusal")


# ---------------------------------------------------------------------------
# The STORED half (2026-09-14 outage)
# ---------------------------------------------------------------------------

def test_a_row_colliding_with_a_stored_key_is_skipped_and_the_rest_are_written(db):
    """🔴 THE HALF THIS FILE'S SUBJECT SAID IT DID NOT COVER, and the one that cost a
    production day. Everything above is a pair inside ONE batch. Here the key is already
    in the TABLE, which breaks the same index - and because `uq_vjoin_*` is not the
    statement's `ON CONFLICT` target there is no DO UPDATE arm for it, so the whole
    statement used to die: the entire push, not the offending row. No chain rule has to be
    involved, which is why disabling every chain rule did not stop it."""
    _push(db, [_item("U-FIRST", "J-HELD")])
    assert sorted(r.business_key_val for r in _rows(db)) == ["U-FIRST"]

    report = {}
    _push(db, [_item("U-CLASH", "J-HELD"), _item("U-OK", "J-FREE")], report=report)

    written = sorted(r.business_key_val for r in _rows(db))
    assert written == ["U-FIRST", "U-OK"], written
    assert report["rows_refused"][crud.DROP_UNIQUE_VIOLATED] == 1, report["rows_refused"]

    refusal = [r for r in report["refusals"] if r["row"] == "U-CLASH"][0]
    assert refusal["others"] == ["U-FIRST"], refusal["others"]
    assert refusal["key"] == ["J-HELD"]
    assert "U-FIRST" in refusal["message"]


def test_updating_the_row_that_already_holds_the_key_is_not_a_collision(db):
    """⚠️ AN UPSERT IS NOT A CLASH. The row holding the key re-pushing its own key must
    still be written, or every second push of an unchanged file would refuse itself."""
    _push(db, [_item("U-SAME", "J-OWN", grade="A")])
    report = {}
    _push(db, [_item("U-SAME", "J-OWN", grade="B")], report=report)

    assert sorted(r.business_key_val for r in _rows(db)) == ["U-SAME"]
    assert not report.get("refusals"), report.get("refusals")
