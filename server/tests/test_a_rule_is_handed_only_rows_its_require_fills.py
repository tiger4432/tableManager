# -*- coding: utf-8 -*-
"""A rule's `require`: only trigger rows whose listed columns are all filled reach the rule
(소유자 09-28 「특정 칼럼 집합이 다 찬 행만 복사」 · 「맵퍼 에러 방지도 되니」, 총괄 49052cbdd).

  where      `rule_run.run_rule` - the seat every kind and every replay hands its rows through,
             and the enrichment backfill calls; a join's answer read asks the SQL twin, so
             neither half takes a value from such a row (총괄 2276e38cf)
  none left  a group `require` emptied does not call the mapper
  empty      `crud.is_blank_value`, the product's one judgement
  later      filling a required column wakes the rule (it counts as the rule's column changing)
  declared   flat `require` = unified `on.require`; every rule the declaration stands on
             `on.table` carries it, a rule on another table does not
  refused    a name the trigger table does not have
  not undone  a target row written before a required column went empty stays
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

import chain_bindings                                               # noqa: E402
import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from chain import join_into, replay, rule_run, rule_shape           # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import outbox_mode                            # noqa: E402
from database.database import Base                                  # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

SRC, DST = "rq_log", "rq_answer_map"
TABLES = {
    SRC: {"business_key": "k", "composite_key_source": ["k"],
          "column_types": {"k": "string", "job": "string", "slot": "string", "v": "string"},
          "display_columns": ["k", "job", "slot", "v"]},
    DST: {"business_key": "k", "composite_key_source": ["k"],
          "column_types": {"k": "string", "v": "string"},
          "display_columns": ["k", "v"]},
}
#: The owner's shape: copy a log row to the answer map only once its keys are filled.
COPY = {"name": "rq_copy", "enabled": True, "is_batch": True, "trigger_table": SRC,
        "target_table": DST, "trigger_columns": ["v"], "require": ["job", "slot"],
        "mapper_module": "rq_copy", "mapper_function": "copy"}
MAPPER = """
SEEN = []

def copy(db, payload, rule=None):
    handed = payload if isinstance(payload, list) else [payload]
    out = []
    for p in handed:
        data = p.get("data") or {}
        k = (data.get("k") or {}).get("value")
        SEEN.append(k)
        out.append({"business_key_val": k,
                    "updates": {"k": k, "v": (data.get("v") or {}).get("value")}})
    return {"updates": out}
"""


def _payload(row_id, **values):
    return {"row_id": row_id, "data": {c: {"value": v} for c, v in values.items()}}


# ------------------------------------------------------------------------------ the judge

@pytest.mark.parametrize("value,handed", [("J1", True), (0, True), (None, False), ("", False),
                                          ("   ", False)])
def test_empty_is_the_products_one_judgement(value, handed):
    kept, empty = rule_run.held_back(COPY, [_payload("r", job=value, slot="S")])
    assert (kept != []) is handed
    assert empty == ({} if handed else {"job": 1})


def test_a_rule_without_require_is_handed_everything():
    rule = dict(COPY)
    rule.pop("require")
    rows = [_payload("r", job=None, slot=None)]
    assert rule_run.held_back(rule, rows) == (rows, {})


# ----------------------------------------------------- the seat, for every kind of rule

SPIED = []
CALLS = []


@pytest.fixture(name="spy")
def fixture_spy(monkeypatch):
    SPIED.clear()
    CALLS.clear()

    def call(db, payload, rule=None):
        rows = payload if isinstance(payload, list) else [payload]
        CALLS.append(len(rows))
        SPIED.extend(p["row_id"] for p in rows)
        return {"updates": []}

    monkeypatch.setattr(rule_run, "resolve",
                        lambda rule: rule_run.Resolved(call, "spy", True))
    return SPIED


JOIN = {"name": "rq_join", "on": {"table": SRC, "require": ["job", "slot"]},
        "derive": {"kind": "join", "join": {"on": [{"left": "k", "right": "k"}],
                                            "take": [{"from": "v", "into": "v"}]}},
        "into": {"table": DST}}
DECIDE = {"name": "rq_decide", "on": {"table": SRC, "require": ["job", "slot"]},
          "derive": {"kind": "decide", "decide": {"key": ["k"], "fields": ["v"]}},
          "into": {"table": DST}}
MAPPER_DECL = {"name": "rq_mapper", "on": {"table": SRC, "require": ["job", "slot"]},
               "derive": {"kind": "mapper", "mapper": {"mapper_module": "m",
                                                        "mapper_function": "f"}},
               "into": {"table": DST}}


@pytest.fixture(name="catalogue")
def fixture_catalogue():
    crud.TABLE_CONFIG.update(TABLES)
    try:
        yield crud.TABLE_CONFIG
    finally:
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


@pytest.mark.parametrize("declaration", [JOIN, DECIDE, MAPPER_DECL],
                         ids=["join", "decide", "mapper"])
def test_each_kind_carries_require_on_its_trigger_table_and_the_seat_holds_rows_back(
        catalogue, spy, caplog, declaration):
    stood, refusal, _notes = rule_shape.expand_declaration(declaration, catalogue)
    assert refusal is None and stood
    on_src = [r for r in stood if r.get("trigger_table") == SRC]
    elsewhere = [r for r in stood if r.get("trigger_table") != SRC]
    assert on_src and all(r[chain_bindings.REQUIRE_KEY] == ["job", "slot"] for r in on_src)
    assert all(chain_bindings.REQUIRE_KEY not in r for r in elsewhere), \
        "a rule on another table never receives the rows require is about"
    rows = [_payload("full", k="1", job="J", slot="S", v="x"),
            _payload("no_slot", k="2", job="J", slot="", v="x")]
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, dict(on_src[0], is_batch=True), payloads=rows)
    assert spy == ["full"]
    assert any("1 row(s) not handed over - required column(s) empty: slot=1" in r.getMessage()
               for r in caplog.records)


def test_a_group_require_emptied_does_not_call_the_mapper(catalogue, spy, caplog):
    """총괄 2276e38cf ② (소유자 「맵퍼 에러 방지」): rows were offered and all held back ->
    no call. A group that offered nothing is still told so - today's contract."""
    rows = [_payload("a", k="1", job="", slot="S"), _payload("b", k="2", job="J", slot=None)]
    with caplog.at_level(logging.INFO):
        rule_run.run_rule(None, COPY, payloads=rows)
    assert CALLS == []
    assert any("2 row(s) not handed over" in r.getMessage() for r in caplog.records)
    rule_run.run_rule(None, COPY, payloads=[])
    assert CALLS == [0]


def test_the_loader_refuses_a_name_the_trigger_table_does_not_have(catalogue, tmp_path,
                                                                   monkeypatch, caplog):
    """Refused through the real loader - the flat cell and the unified cell, one judge. The
    save gate calls the same `rule_refusals` on the same stood rules."""
    rules = [dict(COPY, name="rq_ok"),
             dict(COPY, name="rq_flat_typo", require=["job", "nope"]),
             dict(COPY, name="rq_not_a_list", require="job"),
             dict(JOIN, name="rq_join_typo", on={"table": SRC, "require": ["nope"]})]
    path = tmp_path / "chain_rules.json"
    path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    with caplog.at_level(logging.ERROR):
        loaded = {r.get("name") for r in worker.load_chain_rules()}
    assert "rq_ok" in loaded
    assert not loaded & {"rq_flat_typo", "rq_not_a_list", "rq_join_typo"}
    # ⚠️ Only the rule that carries the cell is refused, so a join keeps its `:target` half;
    #   that half refuses by name when it runs (`join_into._missing`, measured below).
    assert "rq_join_typo:target" in loaded
    said = " ".join(r.getMessage() for r in caplog.records)
    assert all(pair in said for pair in ("rq_flat_typo(unknown_require_column)",
                                         "rq_not_a_list(bad_require)",
                                         "rq_join_typo(unknown_require_column)"))


def test_the_flat_cell_and_the_unified_cell_are_one(catalogue):
    internal = rule_shape.from_chain_rule(COPY)
    assert internal["on"][chain_bindings.REQUIRE_KEY] == ["job", "slot"]
    assert rule_shape.as_chain_rule(internal)[chain_bindings.REQUIRE_KEY] == ["job", "slot"]
    on = next(f["node"] for f in chain_bindings.skeleton()["unified_root"]["fields"]
              if f["key"] == "on")
    assert chain_bindings.REQUIRE_KEY in [f["key"] for f in on["fields"]], \
        "the chain tab's form draws what the skeleton says"


# ---------------------------------------------------------------------------- end to end

@pytest.fixture(name="db")
def fixture_db(tmp_path, monkeypatch):
    mapper_sdk.discover()
    (tmp_path / "rq_copy.py").write_text(textwrap.dedent(MAPPER), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("rq_copy", None)
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
        sys.modules.pop("rq_copy", None)


def _push(db, table, rows):
    # Collapsed, the shape ingestion stages: only that event names its `columns`. A per-row
    # event names none, reads as 「모른다」 and wakes every rule, so it cannot tell whether a
    # filled `require` column wakes the rule on its own.
    with outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name="seed", updated_by="rq")
            for r in rows]))
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


def _copied(db):
    return sorted(r.k for r in db.query(models.DYNAMIC_TABLES[DST]).all())


def test_a_row_waits_until_its_keys_are_filled_then_it_is_copied(db, caplog):
    mapper = sys.modules.get("rq_copy") or __import__("rq_copy")
    _push(db, SRC, [{"k": "A", "job": "J1", "slot": "S1", "v": "a"},
                    {"k": "B", "job": "J2", "slot": "", "v": "b"}])
    _drain(db, [COPY])
    assert mapper.SEEN == ["A"], "the mapper was handed the row whose slot is empty"
    assert _copied(db) == ["A"]

    # The key arrives later, in a write that does not touch `v` - it still wakes the rule.
    _push(db, SRC, [{"k": "B", "slot": "S2"}])
    staged = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.processed_chain.is_(False)).all()
    # `updated_at` joins the names when the fill lands in a later clock second than the insert.
    named = [set(get_payload_dict(e).get("columns") or ()) - {"updated_at"} for e in staged]
    assert named == [{"slot"}], \
        "the fill must name its column, or this cell is not asking the wake judgement"
    # ⚠️ `trigger_columns` does not gate a run today (`fires` does not ask it - measured
    #   09-25, `rule_shape.join_trigger_columns`), so the copy below happens either way. What
    #   the wake judgement decides is the recorded outcome: without `require` in it, this
    #   fill logs 「skipped」 for a rule that then runs.
    caplog.clear()
    with caplog.at_level(logging.INFO):
        _drain(db, [COPY])
    assert not [r for r in caplog.records if "rule rq_copy skipped" in r.getMessage()]
    assert mapper.SEEN[1:] == ["B"]
    assert _copied(db) == ["A", "B"]

    # Not undone: emptying a required column later leaves the copied row where it is.
    _push(db, SRC, [{"k": "A", "slot": ""}])
    _drain(db, [COPY])
    assert _copied(db) == ["A", "B"]


def test_a_replay_is_held_back_at_the_same_seat(db, monkeypatch):
    mapper = sys.modules.get("rq_copy") or __import__("rq_copy")
    _push(db, SRC, [{"k": "A", "job": "J1", "slot": "S1", "v": "a"},
                    {"k": "B", "job": "", "slot": "S2", "v": "b"}])
    for event in db.query(models.DatabaseOutbox).all():
        event_constants.mark_processed(event, "SUCCESS")
    db.commit()
    monkeypatch.setattr(replay, "load_rules", lambda: [COPY])
    ids = [r.row_id for r in db.query(models.DYNAMIC_TABLES[SRC]).all()]
    replay.replay_rule(db, COPY, apply=True, row_ids=ids, log=lambda *a, **k: None)
    _drain(db, [COPY])
    assert mapper.SEEN == ["A"]
    assert _copied(db) == ["A"]


# --------------------------------------------- the join, from both sides (총괄 2276e38cf)

def _values(db):
    return {r.k: r.v for r in db.query(models.DYNAMIC_TABLES[DST]).all()}


def test_a_join_takes_no_value_from_a_row_whose_require_is_empty_whichever_side_woke(db):
    stood, refusal, _notes = rule_shape.expand_declaration(JOIN, crud.TABLE_CONFIG)
    assert refusal is None
    _push(db, SRC, [{"k": "B", "job": "J", "slot": "", "v": "b"}])
    _drain(db, stood)
    # The filled table gains B: the `:target` half wakes and looks the value table up.
    _push(db, DST, [{"k": "B"}])
    _drain(db, stood)
    assert _values(db) == {"B": None}
    # The key is filled: the value side wakes and the answer is there now.
    _push(db, SRC, [{"k": "B", "slot": "S"}])
    _drain(db, stood)
    assert _values(db) == {"B": "b"}


def test_a_join_half_whose_require_names_a_missing_column_refuses_by_name(db):
    stood, _refusal, _notes = rule_shape.expand_declaration(
        dict(JOIN, on={"table": SRC, "require": ["nope"]}), crud.TABLE_CONFIG)
    target = next(r for r in stood if r["trigger_table"] == DST)
    assert "require column 'nope'" in join_into.propose(db, target, ["x"])["refusal"]


# ----------------------------------------------- the enrichment backfill (총괄 2276e38cf ③)

BF_TABLES = {
    "rq_bf_src": {"business_key": "log_key",
                  "composite_key_source": ["equipment", "event_time", "chip_id"],
                  "composite_key_separator": "_",
                  "column_types": {"log_key": "string", "equipment": "string",
                                   "event_time": "string", "chip_id": "string",
                                   "lot_hint": "string"}},
    "rq_bf_derived": {"business_key": "job_id",
                      "composite_key_source": ["equipment", "event_time"],
                      "composite_key_separator": "_",
                      "column_types": {"job_id": "string", "equipment": "string",
                                       "event_time": "string", "wafer_id": "string"}},
}
BF_DECIDE = {"name": "rq_bf", "on": {"table": "rq_bf_src", "require": ["lot_hint"]},
             "into": {"table": "rq_bf_derived"},
             "derive": {"kind": "decide", "decide": {"key": ["equipment", "event_time"],
                                                     "fields": ["wafer_id"]}}}


def test_the_backfill_holds_back_what_the_live_chain_holds_back(db, tmp_path, monkeypatch):
    from chain.enrichment import backfill

    models.init_dynamic_models(BF_TABLES)
    crud.TABLE_CONFIG.update(BF_TABLES)
    Base.metadata.create_all(bind=db.get_bind())
    try:
        path = tmp_path / "chain_rules.json"
        path.write_text(json.dumps({"rules": [BF_DECIDE]}), encoding="utf-8")
        monkeypatch.setattr(worker, "RULES_PATH", str(path))
        _push(db, "rq_bf_src", [
            {"equipment": "EQP1", "event_time": "T1", "chip_id": "C1", "lot_hint": "L1"},
            {"equipment": "EQP2", "event_time": "T2", "chip_id": "C2", "lot_hint": ""}])
        rule = backfill.load_rule("rq_bf", crud.TABLE_CONFIG)
        assert rule[chain_bindings.REQUIRE_KEY] == ["lot_hint"]
        backfill.run_backfill(db, rule, apply=True, log=lambda *_: None)
        derived = models.DYNAMIC_TABLES["rq_bf_derived"]
        assert sorted(r.equipment for r in db.query(derived).all()) == ["EQP1"]
    finally:
        for name in BF_TABLES:
            crud.TABLE_CONFIG.pop(name, None)
