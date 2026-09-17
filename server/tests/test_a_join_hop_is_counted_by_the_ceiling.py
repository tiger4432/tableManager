# -*- coding: utf-8 -*-
"""S-279 · 판정 423. A write a `builtin:` kind makes for itself carries its hop number.

🔴 WHY THIS IS THE ROUND'S ONLY EVIDENCE. 판정 402 removed the load-time refusal of cycles in
the chain graph, and it said WHY: 「고리는 오류가 아니라 모양이다 — 막는 것은 max_chain_depth
다」. That sentence is the whole licence for a declared loop, and it is only true while every
hop in the loop carries a depth the ceiling can read.

A builtin does not. S-278 moved the join off the paced follow-up lap and onto the group path,
where it writes at the top of the rule loop - ABOVE the block that stamped the envelope. Worse
than 「too early」: a builtin writes for ITSELF and proposes nothing, so a group whose rules are
all builtins leaves `table_updates` empty and never ENTERS that block at all. Every lap of a
cycle through a join therefore started counting from zero, and the ceiling could not end it.

⚠️ THE THIRD ASSERTION IS THE ONE THAT WOULD HAVE BEEN MISSED. A fixture with a mapper in the
group passes on a build where the stamp merely happens too late, because the mapper's own write
opens the scope; only a join-ONLY group tells 「stamped late」 from 「not stamped at all」.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                                # noqa: E402
from chain import ingestion_worker as worker                          # noqa: E402
from chain import rule_shape, rule_run                                # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

LEFT = "s423_log"
RIGHT = "s423_attribution"

TABLES = {
    LEFT: {
        "business_key": "log_key",
        "composite_key_source": ["log_key"],
        "column_types": {"log_key": "string", "job": "string", "lot_confirmed": "string"},
        "display_columns": ["log_key", "job", "lot_confirmed"],
    },
    RIGHT: {
        "business_key": "job",
        "composite_key_source": ["job"],
        "column_types": {"job": "string", "lot": "string"},
        "display_columns": ["job", "lot"],
    },
}

DECLARATION = {
    "name": "s423_lot_from_attribution",
    "on": {"table": LEFT},
    "derive": {"kind": "join",
               "join": {"right_table": RIGHT,
                        "on": [{"left": "job", "right": "job"}],
                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
    "into": {"table": LEFT},
}


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _seed(db):
    crud.apply_batch_updates(db, RIGHT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"job": "J", "lot": "LOT"},
                                  source_name="seed", updated_by="s423")]))
    crud.apply_batch_updates(db, LEFT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"log_key": "L1", "job": "J"},
                                  source_name="seed", updated_by="s423")]))
    db.commit()


def _events(db, table):
    return db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == table).all()


def _depths(events):
    """The hop each event carries, read the way the drain's ceiling reads it."""
    return [event_constants.chain_depth_of(worker.get_payload_dict(e)) for e in events]


def _join_only():
    """The rule set with NO file mapper in it - a group that proposes nothing.

    `expand_declaration` returns `(rules, refusal, warnings)`; the rules are the target-side
    rule and its `:reference` companion, both `builtin:join_into`.
    """
    return rule_shape.expand_declaration(DECLARATION, crud.TABLE_CONFIG)[0]


# ---------------------------------------------------------------------------
# ① the hop exists at all
# ---------------------------------------------------------------------------

def test_the_join_stamps_its_own_write_with_a_hop(db):
    """🔴 TODAY'S DEFECT, IN ONE NUMBER. The join writes and the event it produces must be able
    to answer 「how deep am I」 - the ceiling has nothing else to read."""
    _seed(db)
    before = set(e.id for e in _events(db, LEFT))

    worker._process_chain_transaction_group_sync(
        "tx-s423-a", _events(db, LEFT), db, _join_only())

    made = [e for e in _events(db, LEFT) if e.id not in before]
    assert made, "the join wrote no event, so this proves nothing"
    assert _depths(made) == [1], (
        "the join's write carries %r instead of hop 1, so `max_chain_depth` cannot count a "
        "cycle that goes through it - and 판정 402 made that ceiling the ONLY thing standing "
        "between a declared loop and an endless one" % (_depths(made),))


# ---------------------------------------------------------------------------
# ③ and it is stamped when NOTHING in the group proposes - the quieter half
# ---------------------------------------------------------------------------

def test_the_hop_is_stamped_even_though_no_rule_in_the_group_proposed_anything(db):
    """⛔ THE DISCRIMINANT. `_join_only()` has no file mapper, so `table_updates` stays empty
    and the block that used to hold the stamp is never entered. A fixture with a mapper beside
    the join would pass on a build where the stamp merely happens LATE - 「두 규칙이 같은 답을
    내는 표본은 판별식이 아니다」."""
    _seed(db)
    rules = _join_only()
    # ⚰️ [판정 562] `builtin_kind` WAS AN ADDRESS QUESTION and is deleted. What this
    #   fixture needs is the PROPERTY it stood in for: every rule here writes its own rows,
    #   so `table_updates` stays empty and the stamp cannot arrive by the other path.
    assert all(rule_run.writes_itself(r) for r in rules), (
        "this fixture only decides anything while every rule in it writes for itself")

    before = set(e.id for e in _events(db, LEFT))
    worker._process_chain_transaction_group_sync("tx-s423-c", _events(db, LEFT), db, rules)

    made = [e for e in _events(db, LEFT) if e.id not in before]
    assert _depths(made) == [1], _depths(made)


# ---------------------------------------------------------------------------
# ② the number GROWS lap over lap, which is what the ceiling compares
# ---------------------------------------------------------------------------

def test_a_hop_already_in_flight_is_carried_forward_rather_than_restarted(db):
    """🔴 THE PROPERTY THE CEILING NEEDS, AND THE ONE THAT WAS BROKEN. The ceiling itself lives
    in the drain (`depth > max_depth`) and its arithmetic never changed; what was wrong is the
    INPUT. A join that always stamped its write at 1 makes `depth > max_depth` false forever, so
    the loop 판정 402 declared finite was not - and that ruling is the entire reason the
    load-time cycle refusal was removed.

    ⚠️ DRIVEN BY A TRIGGER THAT ALREADY CARRIES A HOP, not by walking a real cycle twice. Two
    measured reasons the obvious fixture decides nothing: a chain-written event does not
    re-trigger the chain without `allow_chain_trigger` (「체인이 쓴 행은 체인을 다시 깨우지
    않는다」), and a second lap writing the SAME value produces no event at all. Either would
    make this green while the counter still restarted.
    """
    import json

    _seed(db)
    rules = [dict(r, allow_chain_trigger=True) for r in _join_only()]

    # The trigger arrives at hop 3 - as it would three laps into a declared cycle.
    trigger = _events(db, LEFT)[0]
    payload = worker.get_payload_dict(trigger)
    payload[event_constants.CHAIN_DEPTH_KEY] = 3
    trigger.payload = json.dumps(payload)
    if hasattr(trigger, "_parsed_payload"):
        trigger._parsed_payload = payload
    db.commit()
    assert event_constants.chain_depth_of(worker.get_payload_dict(trigger)) == 3, (
        "the fixture did not manage to hand the group a hop, so it decides nothing")

    before = set(e.id for e in _events(db, LEFT))
    worker._process_chain_transaction_group_sync("tx-s423-deep", [trigger], db, rules)
    made = [e for e in _events(db, LEFT) if e.id not in before]

    assert _depths(made) == [4], (
        "a trigger at hop 3 produced %r; a counter that restarts at 1 is a ceiling that never "
        "fires" % (_depths(made),))
