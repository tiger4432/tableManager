# -*- coding: utf-8 -*-
"""A declaration is not woken by its own writes (소유자 09-28 「ㄱ으로 해」, 총괄 ebefd20e8).

Production, 09-28: a join declared `allow_chain_trigger: true`; its `:target` half inherited the
cell and the join's writes into the target re-woke it - the queue grew until the owner paused
the chain. `allow_chain_trigger` keeps its meaning, 「take what OTHER rules wrote」: the chain's
two write seats stamp which declarations wrote (`written_by`), and `_rule_accepts_event` - where
the opt-in is read - drops an event only its own declaration wrote.

  own declaration wrote it           not woken - even when the key column changed
  another declaration wrote it       woken, as the opt-in says
  its own AND another wrote it       woken - the other's change rides the same event
  an event with no stamp (older)     as before
"""
import json
import os
import sys
import textwrap
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import rule_shape                                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

LEFT, RIGHT = "sw_left_log", "sw_right_attr"
TABLES = {
    LEFT: {"business_key": "log_key", "composite_key_source": ["log_key"],
           "column_types": {"log_key": "string", "job": "string", "lot_confirmed": "string"},
           "display_columns": ["log_key", "job", "lot_confirmed"]},
    RIGHT: {"business_key": "job", "composite_key_source": ["job"],
            "column_types": {"job": "string", "lot": "string"},
            "display_columns": ["job", "lot"]},
}
#: The production shape: a join that opted into chain writes.
JOIN = {"name": "sw_lot_join", "allow_chain_trigger": True,
        "on": {"table": RIGHT},
        "derive": {"kind": "join", "join": {"on": [{"left": "job", "right": "job"}],
                                            "take": [{"from": "lot", "into": "lot_confirmed"}]}},
        "into": {"table": LEFT}}
BUMP = """
def bump(db, payload, rule=None):
    out = []
    for p in (payload if isinstance(payload, list) else [payload]):
        data = p.get("data") or {}
        k = (data.get("log_key") or {}).get("value")
        n = int((data.get("lot_confirmed") or {}).get("value") or 0)
        out.append({"business_key_val": k, "updates": {"log_key": k, "lot_confirmed": str(n + 1)}})
    return {"updates": out}


def bump_itself(db, payload, rule=None):
    from database import crud, schemas
    items = [schemas.GeneralUpdateItem(updates=u["updates"], source_name="chain_ingestion",
                                       updated_by="sw")
             for u in bump(db, payload, rule)["updates"]]
    crud.apply_batch_updates(db, "sw_left_log", schemas.GeneralUpdateBatch(updates=items))
    return {"updates": []}
"""


def _event(table, **payload):
    return types.SimpleNamespace(id=None, table_name=table, event_type="EDIT",
                                 payload=dict(payload), _parsed_payload=dict(payload))


def _halves():
    stood = {r["name"]: r for r in rule_shape.expand_declaration(JOIN, TABLES)[0]}
    return stood[JOIN["name"]], stood[JOIN["name"] + rule_shape.COMPANION_SUFFIX]


# ------------------------------------------------------------------------------ the judge

@pytest.mark.parametrize("wrote,woken", [
    (["sw_lot_join"], False),                 # its own write, key column changed or not
    (["someone_else"], True),                 # another declaration's write: the opt-in
    (["sw_lot_join", "someone_else"], True),  # shared: the other's change is on it too
    (None, True),                             # no stamp: an event queued before the key
])
def test_the_target_half_is_not_woken_by_its_own_declaration(wrote, woken):
    _source, target = _halves()
    payload = {"channel": event_constants.CHANNEL_CHAIN, "columns": ["job", "lot_confirmed"]}
    if wrote is not None:
        payload[event_constants.WRITTEN_BY_KEY] = wrote
    event = _event(LEFT, **payload)
    # The key column is on it, so the column filter lets it through - only the stamp decides.
    assert worker.rule_watches_changed_columns(target, event) is True
    assert worker.fires(target, event) is woken


def test_both_halves_are_one_declaration_and_a_decide_is_two():
    source, target = _halves()
    assert rule_shape.declaration_of(source) == rule_shape.declaration_of(target) == JOIN["name"]
    # ⚠️ decide's confirm half is woken by its dedup half's write - two rules on purpose.
    assert rule_shape.declaration_of({"name": "enrichment_dedup:x", "origin": "synthesized:x"}) \
        != rule_shape.declaration_of({"name": "enrichment_confirm:x", "origin": "synthesized:x"})


def test_a_write_from_outside_the_chain_is_untouched():
    _source, target = _halves()
    event = _event(LEFT, channel=event_constants.CHANNEL_API, written_by=["sw_lot_join"],
                   columns=["job"])
    assert worker.fires(target, event) is True


# ---------------------------------------------------------------------------- end to end

@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    mapper_sdk.discover()
    (tmp_path / "sw_bump.py").write_text(textwrap.dedent(BUMP), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("sw_bump", None)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [JOIN]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        sys.modules.pop("sw_bump", None)


def _push(db, table, rows):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name="seed", updated_by="sw")
        for r in rows]))
    db.commit()


def _drain(db, rules, rounds=6):
    """-> the chain-written events each round woke, per rule name. Raises if it never settles."""
    woke = {}
    for _ in range(rounds):
        pending = (db.query(models.DatabaseOutbox)
                   .filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return woke
        for e in pending:
            if event_constants.channel_of(get_payload_dict(e)) == event_constants.CHANNEL_CHAIN:
                for r in rules:
                    if worker.fires(r, e) and worker.rule_watches_changed_columns(r, e):
                        woke[r["name"]] = woke.get(r["name"], 0) + 1
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, rules)
            assert ok, error
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle in %d rounds: %s" % (rounds, woke))


def _chain_events(db, table):
    return [get_payload_dict(e) for e in db.query(models.DatabaseOutbox).all()
            if e.table_name == table
            and event_constants.channel_of(get_payload_dict(e)) == event_constants.CHANNEL_CHAIN]


def test_the_join_stamps_its_write_with_its_declaration(db):
    rules = [r for r in worker.load_chain_rules() if str(r.get("name", "")).startswith("sw_")]
    _push(db, LEFT, [{"log_key": "K1", "job": "J1"}])
    _push(db, RIGHT, [{"job": "J1", "lot": "L1"}])
    _drain(db, rules)
    wrote = _chain_events(db, LEFT)
    assert wrote and all(p[event_constants.WRITTEN_BY_KEY] == [JOIN["name"]] for p in wrote)
    assert [r.lot_confirmed for r in db.query(models.DYNAMIC_TABLES[LEFT]).all()] == ["L1"]


def test_a_same_value_write_stages_no_event(db):
    """② (총괄 ebefd20e8): a write that changes nothing stages nothing, so a loop stops by
    itself once its values stop moving - this repair closes the case where they keep moving."""
    rules = [r for r in worker.load_chain_rules() if str(r.get("name", "")).startswith("sw_")]
    _push(db, RIGHT, [{"job": "J1", "lot": "L1"}])
    _drain(db, rules)
    before = len(_chain_events(db, LEFT))
    _push(db, LEFT, [{"log_key": "K4", "job": "J1", "lot_confirmed": "L1"}])
    _drain(db, rules)
    assert len(_chain_events(db, LEFT)) == before, "the join rewrote L1 over L1 and said so"


def test_a_rule_that_writes_its_own_trigger_table_runs_once(db):
    """The mapper shape of the same loop: it writes the table it watches, opted in, with no
    column filter - and its value moves every time, so nothing but this repair stops it."""
    rule = {"name": "sw_self", "enabled": True, "is_batch": True, "trigger_table": LEFT,
            "target_table": LEFT, "mapper_module": "sw_bump", "mapper_function": "bump",
            "allow_chain_trigger": True}
    other = dict(rule, name="sw_other", trigger_table=RIGHT)
    _push(db, LEFT, [{"log_key": "K1", "job": "J1", "lot_confirmed": "0"}])
    woke = _drain(db, [rule, other])
    assert woke.get("sw_self", 0) == 0, woke
    assert [r.lot_confirmed for r in db.query(models.DYNAMIC_TABLES[LEFT]).all()] == ["1"]
    assert all(p[event_constants.WRITTEN_BY_KEY] == ["sw_self"] for p in _chain_events(db, LEFT))


def test_a_rule_that_writes_inside_its_own_call_is_stamped_too(db):
    """The other seat: a mapper handed `db` may write during its call, inside
    `rule_run.chain_envelope` - that write is the rule's declaration's as well."""
    rule = {"name": "sw_itself", "enabled": True, "is_batch": True, "trigger_table": LEFT,
            "target_table": LEFT, "mapper_module": "sw_bump", "mapper_function": "bump_itself",
            "allow_chain_trigger": True}
    _push(db, LEFT, [{"log_key": "K1", "job": "J1", "lot_confirmed": "0"}])
    woke = _drain(db, [rule])
    assert woke.get("sw_itself", 0) == 0, woke
    wrote = _chain_events(db, LEFT)
    assert wrote and all(p[event_constants.WRITTEN_BY_KEY] == ["sw_itself"] for p in wrote)
