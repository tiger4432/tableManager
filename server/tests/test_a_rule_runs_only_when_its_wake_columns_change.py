# -*- coding: utf-8 -*-
"""`trigger_columns` gates a run (소유자 09-29 「ㄱ」, 총괄 2a1be19e9).

  seat       `fire_refusal` - `fires` is its yes/no, the pre-run outcome reads its reason
  wakes      trigger_columns, then `require`; an event without a column list runs (「모른다」)
  join       the value side wakes on its key AND its take columns (derived), the `:target`
             half on its own key - its own take write does not wake it
  said       「skipped: none of [..] changed」 once per group, only when the rule did not run;
             「<rule> wakes only on: [..]」 once per column-scoped rule at load
"""
import json
import logging
import os
import sys
import textwrap

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
from database.context import outbox_mode                            # noqa: E402
from database.database import Base                                  # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

WT, WOUT, VAL, FILL = "wc_t", "wc_out", "wc_val", "wc_fill"
TABLES = {
    WT: {"business_key": "k", "composite_key_source": ["k"],
         "column_types": {"k": "string", "a": "string", "b": "string", "r": "string"},
         "display_columns": ["k", "a", "b", "r"]},
    WOUT: {"business_key": "k", "composite_key_source": ["k"],
           "column_types": {"k": "string", "a": "string"}, "display_columns": ["k", "a"]},
    VAL: {"business_key": "vid", "composite_key_source": ["vid"],
          "column_types": {"vid": "string", "k": "string", "v": "string", "other": "string"},
          "display_columns": ["vid", "k", "v", "other"]},
    FILL: {"business_key": "fid", "composite_key_source": ["fid"],
           "column_types": {"fid": "string", "k": "string", "v": "string", "note": "string"},
           "display_columns": ["fid", "k", "v", "note"]},
}
RULE_A = {"name": "wc_a", "enabled": True, "is_batch": True, "trigger_table": WT,
          "target_table": WOUT, "trigger_columns": ["a"], "require": ["r"],
          "mapper_module": "wc_seen", "mapper_function": "seen"}
JOIN = {"name": "wc_join", "on": {"table": VAL},
        "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}],
                                            "take": [{"from": "v", "into": "v"}]}},
        "into": {"table": FILL}}
MAPPER = """
SEEN = []

def seen(db, payload, rule=None):
    for p in (payload if isinstance(payload, list) else [payload]):
        SEEN.append(((p.get("data") or {}).get("k") or {}).get("value"))
    return {"updates": []}
"""


@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    mapper_sdk.discover()
    (tmp_path / "wc_seen.py").write_text(textwrap.dedent(MAPPER), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("wc_seen", None)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)
        sys.modules.pop("wc_seen", None)


def _push(db, table, rows, collapsed=True):
    """Collapsed is the shape ingestion and the chain stage - the one that names its columns."""
    batch = schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name="seed", updated_by="wc")
        for r in rows])
    if collapsed:
        with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
            crud.apply_batch_updates(db, table, batch)
            db.commit()
    else:
        crud.apply_batch_updates(db, table, batch)
        db.commit()


def _drain(db, rules, rounds=6):
    for _ in range(rounds):
        pending = (db.query(models.DatabaseOutbox)
                   .filter(models.DatabaseOutbox.processed_chain.is_(False))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            return
        groups = {}
        for e in pending:
            groups.setdefault(get_payload_dict(e).get("transaction_id"), []).append(e)
        for tx_id, events in groups.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, rules)
            assert ok, error
            for e in events:
                event_constants.mark_processed(e, "SUCCESS")
            db.commit()
    raise AssertionError("the chain did not settle")


def _skipped(caplog, name):
    return [r for r in caplog.records
            if r.getMessage().startswith("[Chain] rule %s skipped: none of" % name)]


# ------------------------------------------------------------------ a column-scoped rule

def test_a_rule_runs_on_its_columns_and_on_nothing_else(db, caplog):
    seen = __import__("wc_seen").SEEN
    _push(db, WT, [{"k": "1", "a": "x", "b": "y", "r": "z"}])
    _drain(db, [RULE_A])
    assert seen == ["1"]

    caplog.clear()
    with caplog.at_level(logging.INFO):
        _push(db, WT, [{"k": "1", "b": "y2"}])
        _drain(db, [RULE_A])
    assert seen == ["1"], "a change to b ran a rule that wakes on a"
    assert len(_skipped(caplog, "wc_a")) == 1
    assert "['a', 'r']" in _skipped(caplog, "wc_a")[0].getMessage()

    _push(db, WT, [{"k": "1", "a": "x2"}])
    _drain(db, [RULE_A])
    assert seen == ["1", "1"]

    # `require` counts as the rule's column (총괄 49052cbdd).
    _push(db, WT, [{"k": "1", "r": "z2"}])
    _drain(db, [RULE_A])
    assert seen == ["1", "1", "1"]

    # No column list on the event is 「모른다」, and 「모른다」 runs.
    _push(db, WT, [{"k": "1", "b": "y3"}], collapsed=False)
    staged = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.processed_chain.is_(False)).all()
    assert staged and all(get_payload_dict(e).get("columns") is None for e in staged)
    _drain(db, [RULE_A])
    assert seen == ["1", "1", "1", "1"]


# ---------------------------------------------------------------------------- the join

def _values(db):
    fill = models.DYNAMIC_TABLES[FILL]
    return {r.fid: r.v for r in db.query(fill).order_by(fill.fid).all()}


def test_the_join_wakes_on_its_key_and_its_take_columns_on_both_sides(db, caplog):
    stood, refusal, _notes = rule_shape.expand_declaration(JOIN, crud.TABLE_CONFIG)
    assert refusal is None
    target = next(r for r in stood if r["trigger_table"] == FILL)
    _push(db, FILL, [{"fid": "f1", "k": "B"}, {"fid": "f2", "k": "D"}])
    _drain(db, stood)
    _push(db, VAL, [{"vid": "v1", "k": "B", "v": "1", "other": "o"}])
    _drain(db, stood)
    assert _values(db) == {"f1": "1", "f2": None}

    # value side - a take column changes
    _push(db, VAL, [{"vid": "v1", "v": "2"}])
    _drain(db, stood)
    assert _values(db) == {"f1": "2", "f2": None}

    # value side - a column the join does not read
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _push(db, VAL, [{"vid": "v1", "other": "o2"}])
        _drain(db, stood)
    assert len(_skipped(caplog, "wc_join")) == 1

    # value side - the key changes: f2 takes v1's value, and f1 gives back the one v1 no longer
    # feeds (총괄 b13de0353 - an edited source row's stamped layer is withdrawn)
    _push(db, VAL, [{"vid": "v1", "k": "D"}])
    _drain(db, stood)
    assert _values(db) == {"f1": None, "f2": "2"}

    # `:target` side - a new row, then its key changes
    _push(db, VAL, [{"vid": "v2", "k": "E", "v": "9"}])
    _drain(db, stood)
    _push(db, FILL, [{"fid": "f3", "k": "D"}])
    _drain(db, stood)
    assert _values(db)["f3"] == "2"
    _push(db, FILL, [{"fid": "f3", "k": "E"}])
    _drain(db, stood)
    assert _values(db)["f3"] == "9"

    # `:target` side - a column it does not read
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _push(db, FILL, [{"fid": "f3", "note": "n"}])
        _drain(db, stood)
    assert len(_skipped(caplog, target["name"])) == 1

    # `:target` side - the join's own take write names only what it wrote
    from chain import cell_layer

    wrote = [e for e in db.query(models.DatabaseOutbox).filter(
                 models.DatabaseOutbox.table_name == FILL).all()
             if event_constants.channel_of(get_payload_dict(e)) == event_constants.CHANNEL_CHAIN
             and not str(get_payload_dict(e).get("transaction_id") or "").startswith(
                 cell_layer.R2_AUDIT_SOURCE)]    # the withdrawal above writes too, not as the take
    assert wrote
    assert {worker.fire_refusal(target, e) for e in wrote} == {worker.FIRE_REFUSED_COLUMNS}


# ------------------------------------------------------------------------- said at load

def test_the_loader_names_what_each_column_scoped_rule_wakes_on(db, tmp_path, monkeypatch,
                                                                caplog):
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": [RULE_A, JOIN]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    with caplog.at_level(logging.INFO):
        worker.load_chain_rules()
    said = [r.getMessage() for r in caplog.records if "wakes only on:" in r.getMessage()]
    assert "[ChainRules] wc_a wakes only on: ['a', 'r']" in said
    assert "[ChainRules] wc_join wakes only on: ['k', 'v']" in said
    assert "[ChainRules] wc_join:target wakes only on: ['k']" in said
