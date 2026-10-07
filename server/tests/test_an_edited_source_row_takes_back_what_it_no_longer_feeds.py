# -*- coding: utf-8 -*-
"""총괄 e35500433 · 4c3417ccb · b13de0353 — an EDITED source row takes back what it no longer feeds.

A rule whose output carries `origin_row_id` withdraws, after its write, the layers its edited trigger
rows stamped in the columns that rule writes, off the rows the write did not just put them on. The
same withdrawal as a deletion's (`cell_layer.withdraw_by_origin`), narrowed; the rows that lost a
layer get one EDIT, stamped as the rule's own write.

  sqlite   two rules filling their own row, one re-runs: the other's column stays, events counted
           a rule that fills ANOTHER row moves it: the old row loses only that layer, the loop ends
  PG       the hold copy (`copy_rows_with_hold`): a moved key, a kept key, a sibling, a person's layer
"""
import json
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
import mapper_sdk                                                   # noqa: E402
from chain import cell_layer                                        # noqa: E402
from chain import ingestion_worker as worker                        # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.database import Base                                  # noqa: E402
from support import hold_world as hw                                # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

T = "er_self"
TABLES = {T: {"business_key": "k", "composite_key_source": ["k"],
              "column_types": {c: "string" for c in ("k", "a", "b", "p", "x", "y", "z")},
              "display_columns": ["k", "a", "b", "p", "x", "y", "z"]}}
RAN = []


def _fill(column, read, on="k"):
    """A rule body: each handed row writes `column` from `read` on the row its `on` names (itself
    for `k`) - with the row it read as the origin."""
    def body(db, payload, rule=None):
        RAN.append(rule["name"])
        out = []
        for one in (payload if isinstance(payload, list) else [payload]):
            data = {k: (v or {}).get("value") for k, v in (one.get("data") or {}).items()}
            where = data.get(on)
            if where:
                out.append({"updates": {"k": where, column: "%s!" % data.get(read)},
                            "origin_row_id": one["row_id"], "source_name": "chain_ingestion"})
        return {"updates": out}
    return body


RULES = [
    # two rules filling their own row, each woken by its own column (b13de0353 게이트 더)
    {"name": "er_x", "mapper": "er_x", "trigger_columns": ["a"], "body": _fill("x", "a")},
    {"name": "er_y", "mapper": "er_y", "trigger_columns": ["b"], "body": _fill("y", "b")},
    # a rule filling the row its `p` names: moving `p` leaves the old row behind
    {"name": "er_z", "mapper": "er_z", "trigger_columns": ["p"], "body": _fill("z", "k", on="p")},
    # a second rule filling that row, woken by another column (b13de0353: its cells stay)
    {"name": "er_v", "mapper": "er_v", "trigger_columns": ["b"], "body": _fill("y", "b", on="p")},
]


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    for rule in RULES:
        mapper_sdk.register(rule["mapper"], rule["body"])
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    RAN.clear()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.pop(T, None)
        for rule in RULES:
            mapper_sdk.MAPPER_REGISTRY.pop(rule["mapper"], None)
            mapper_sdk.MAPPER_PARAMS.pop(rule["mapper"], None)


def _rules(*names):
    return [{"enabled": True, "is_batch": True, "trigger_table": T, "target_table": T,
             "allow_chain_trigger": True, **{k: v for k, v in r.items() if k != "body"}}
            for r in RULES if r["name"] in names]


def _push(db, rows):
    """Collapsed, as a file load stages - so the event names the columns that changed."""
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, T, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name="user", updated_by="er")
            for r in rows]))
    db.commit()


def _drain(db, rules, rounds=6):
    for _ in range(rounds):
        pending = (db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.processed_chain.is_(False))
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
    raise AssertionError("the chain did not settle in %d rounds" % rounds)


def _events(db, since):
    return [(e.event_type, sorted(get_payload_dict(e).get("columns") or ()),
             event_constants.channel_of(get_payload_dict(e)))
            for e in db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > since)
            .order_by(models.DatabaseOutbox.id)]


def _mark(db):
    return db.query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).limit(1).scalar() or 0


def _row(db, k):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[T]).filter_by(business_key_val=k).one()


def _layers(db, k):
    return sorted((s.column_name, s.source_name, s.origin_row_id) for s in db.query(models.CellSource)
                  .filter_by(table_name=T, row_id=_row(db, k).row_id))


def test_one_of_two_rules_filling_their_own_row_reruns_and_the_other_column_stays(db):
    rules = _rules("er_x", "er_y")
    _push(db, [{"k": "R", "a": "1", "b": "1"}])
    _drain(db, rules)
    row = _row(db, "R").row_id
    assert (_row(db, "R").x, _row(db, "R").y) == ("1!", "1!")
    RAN.clear()
    since = _mark(db)

    _push(db, [{"k": "R", "a": "2"}])
    _drain(db, rules)

    assert (_row(db, "R").x, _row(db, "R").y) == ("2!", "1!")
    assert ("y", "chain_ingestion", row) in _layers(db, "R"), "the rule that did not run lost its cell"
    assert RAN == ["er_x"], RAN
    # the edit, then er_x's own write - nothing withdrawn, so no EDIT of the withdrawal's
    assert _events(db, since) == [("EDIT", ["a"], event_constants.CHANNEL_API),
                                  ("EDIT", ["x"], event_constants.CHANNEL_CHAIN)]


def test_a_row_filled_from_another_row_loses_only_that_layer_when_it_moves_away(db):
    rules = _rules("er_z")
    _push(db, [{"k": "P1"}, {"k": "P2"}, {"k": "C", "p": "P1"}])
    _drain(db, rules)
    child = _row(db, "C").row_id
    assert (_row(db, "P1").z, _row(db, "P2").z) == ("C!", None)
    RAN.clear()
    since = _mark(db)

    _push(db, [{"k": "C", "p": "P2"}])
    _drain(db, rules)

    assert (_row(db, "P1").z, _row(db, "P2").z) == (None, "C!")
    assert [l for l in _layers(db, "P1") if l[2] == child] == [], "the old row kept the moved row's layer"
    assert ("k", "user", None) in _layers(db, "P1"), "the old row's own key went with it"
    # 🔴 THE LOOP (b13de0353): what the withdrawal stages on P1 says er_z wrote it, so er_z is not
    #    woken by it - one run, for the edit - and nothing after it writes.
    assert RAN == ["er_z"], RAN
    assert _events(db, since) == [
        ("EDIT", ["p"], event_constants.CHANNEL_API),
        ("EDIT", ["z"], event_constants.CHANNEL_CHAIN),       # er_z writes P2
        ("EDIT", [], event_constants.CHANNEL_CHAIN),          # P1's z emptied (per row: no columns)
        ("EDIT", ["k", "z"], event_constants.CHANNEL_CHAIN),  # P1 lost a layer on k and z
    ]
    assert all(get_payload_dict(e).get(event_constants.WRITTEN_BY_KEY) == ["er_z"]
               for e in db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > since)
               if event_constants.channel_of(get_payload_dict(e)) == event_constants.CHANNEL_CHAIN)


def test_a_rule_that_now_writes_nothing_still_takes_back_what_it_wrote_before(db):
    """총괄 10-08: C points nowhere now, so er_z proposes nothing - and its cell on P1 still goes, by
    the columns er_z last wrote."""
    rules = _rules("er_z")
    _push(db, [{"k": "P1"}, {"k": "C", "p": "P1"}])
    _drain(db, rules)
    assert _row(db, "P1").z == "C!"

    _push(db, [{"k": "C", "p": ""}])
    _drain(db, rules)

    assert _row(db, "P1").z is None
    assert [l for l in _layers(db, "P1") if l[2] == _row(db, "C").row_id] == []


def test_a_rule_this_process_has_not_seen_write_says_so_and_takes_back_nothing(db, monkeypatch, caplog):
    import logging
    from chain import rule_run

    rules = _rules("er_z")
    _push(db, [{"k": "P1"}, {"k": "C", "p": "P1"}])
    _drain(db, rules)
    monkeypatch.setattr(rule_run, "_ORIGIN_SEEN", {})            # a restart: nothing seen yet
    monkeypatch.setattr(rule_run, "_COLUMNS_SEEN", {})

    with caplog.at_level(logging.WARNING):
        _push(db, [{"k": "C", "p": ""}])
        _drain(db, rules)

    assert _row(db, "P1").z == "C!"
    said = [r.getMessage() for r in caplog.records if "[ChainRetract]" in r.getMessage()]
    assert len(said) == 1 and "er_z" in said[0], said


def test_a_second_rule_filling_the_same_other_row_keeps_its_cell_when_only_the_first_reruns(db):
    """Same origin, same target row, two rules: only the rule that ran gives its columns back."""
    rules = _rules("er_z", "er_v")
    _push(db, [{"k": "P1"}, {"k": "P2"}, {"k": "C", "p": "P1", "b": "1"}])
    _drain(db, rules)
    assert (_row(db, "P1").z, _row(db, "P1").y) == ("C!", "1!")

    _push(db, [{"k": "C", "p": "P2"}])
    _drain(db, rules)

    assert (_row(db, "P1").z, _row(db, "P1").y) == (None, "1!"), "er_v's cell went with er_z's"
    assert ("y", "chain_ingestion", _row(db, "C").row_id) in _layers(db, "P1")


# ---------------------------------------------------------------------------------------------
# 총괄 4c3417ccb ③ — a decorated mapper's output says which input row it came from, by default
# ---------------------------------------------------------------------------------------------

def _decorated(transform):
    @mapper_sdk.mapper(name="er_sdk_probe")
    def body(df, db):
        return transform(df)
    return body


SHAPES = {
    # what the author returns: (the frame, the origins its items carry)
    "the frame itself": (lambda df: df.assign(x=df["a"]), ["r1", "r2", "r3"]),
    "columns picked by name": (lambda df: df[["k", "a"]], [None, None, None]),
    "filtered, then the index reset": (lambda df: df[df["a"] != "2"].reset_index(drop=True), ["r1", "r3"]),
    "sorted the other way": (lambda df: df.sort_values("a", ascending=False), ["r3", "r2", "r1"]),
    "an aggregate": (lambda df: df.groupby("k", as_index=False).agg(a=("a", "max")), [None, None]),
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_decorated_mapper_stamps_the_row_each_output_row_was_read_from(monkeypatch, shape):
    transform, origins = SHAPES[shape]
    monkeypatch.setitem(crud.TABLE_CONFIG, T, TABLES[T])
    payloads = [{"row_id": rid, "data": {"k": {"value": k}, "a": {"value": a}}}
                for rid, k, a in (("r1", "K1", "1"), ("r2", "K2", "2"), ("r3", "K2", "3"))]
    try:
        run = _decorated(transform)
        result = run(None, payloads, rule={"name": "er_sdk", "target_table": T})
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop("er_sdk_probe", None)
        mapper_sdk.MAPPER_PARAMS.pop("er_sdk_probe", None)

    assert [item.get("origin_row_id") for item in result["updates"]] == origins
    assert all(mapper_sdk.ORIGIN_MARK not in item["updates"] for item in result["updates"]), (
        "the mark reached the write")


# ---------------------------------------------------------------------------------------------
# PG - the hold copy, the shape the order was written about
# ---------------------------------------------------------------------------------------------

@pytest.fixture(name="world", params=[False, True], ids=["one_row", "batch"])
def fixture_world(request, pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=request.param)


def _official(world):
    """{(job, x, y): (row_id, hold, netdie)}"""
    with world["engine"].connect() as conn:
        return {(job, float(x), float(y)): (row_id, hold, netdie) for row_id, job, x, y, hold, netdie in conn.execute(
            text('SELECT row_id, dt_job, dt_x, dt_y, hold, netdie FROM "%s"' % hw.OFFICIAL))}


def _log_row(world, log_id):
    with world["engine"].connect() as conn:
        return conn.execute(text('SELECT row_id FROM "%s" WHERE log_id = :l' % hw.LOG), {"l": log_id}).scalar()


def _layers_of(world, row_id, origin=None):
    with world["engine"].connect() as conn:
        found = sorted((c, s, o) for c, s, o in conn.execute(text(
            "SELECT column_name, source_name, origin_row_id FROM cell_sources WHERE table_name = :t AND row_id = :r"),
            {"t": hw.OFFICIAL, "r": row_id}))
    return [layer for layer in found if origin is None or layer[2] == origin]


def _withdrawals_since(world, audit_from, outbox_from):
    with world["engine"].connect() as conn:
        audit = conn.execute(text("SELECT count(*) FROM audit_logs WHERE id > :a AND source_name = :s"),
                             {"a": audit_from, "s": cell_layer.R2_AUDIT_SOURCE}).scalar()
        events = [p for (p,) in conn.execute(text("SELECT payload FROM database_outbox WHERE id > :o"),
                                             {"o": outbox_from})]
    return audit + sum(1 for p in events if str(get_payload_dict(p).get("transaction_id") or "")
                       .startswith(cell_layer.R2_AUDIT_SOURCE))


def _marks(world):
    with world["engine"].connect() as conn:
        return (conn.execute(text("SELECT coalesce(max(id), 0) FROM audit_logs")).scalar(),
                conn.execute(text("SELECT coalesce(max(id), 0) FROM database_outbox")).scalar())


MOVED = {"log_id": "A", "dt_job": "J1", "dt_x": 5, "dt_y": 2, "netdie": 7}
OLD, NEW = ("J1", 1.0, 2.0), ("J1", 5.0, 2.0)


@pytest.mark.pg
def test_a_moved_source_row_leaves_its_old_key(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    a, old = _log_row(world, "A"), _official(world)[OLD][0]
    world["db"].add(models.CellSource(table_name=hw.OFFICIAL, row_id=old, column_name="note",
                                      source_name="user", value="typed", origin_row_id=a))
    world["db"].commit()

    hw.push(world, [MOVED])
    hw.settle(world)

    rows = _official(world)
    assert _layers_of(world, old, a) == [("note", "user", a)], "the old row kept A's layer, or lost a person's"
    assert _layers_of(world, old, None) != [], "the old row was emptied of layers that were not A's"
    assert not rows[OLD][1], "the old key was not recounted: %r" % (rows[OLD],)
    assert rows[NEW][1] == "agreed"
    assert hw.said(world) == [("J1", "7.0")], "the old key still speaks in the ledger"


@pytest.mark.pg
def test_an_edit_that_keeps_the_key_withdraws_nothing(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    audit_from, outbox_from = _marks(world)

    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 8}])
    hw.settle(world)

    assert _withdrawals_since(world, audit_from, outbox_from) == 0
    assert _official(world)[OLD][1:] == ("agreed", 8)
    assert hw.said(world) == [("J1", "8.0")]


@pytest.mark.pg
def test_a_job_split_into_two_batches_keeps_its_siblings(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", "dt_job": "J1", "dt_x": 3, "dt_y": 2, "netdie": 9}])
    hw.settle(world)
    b, sibling = _log_row(world, "B"), _official(world)[("J1", 3.0, 2.0)][0]
    before = _layers_of(world, sibling, b)

    hw.push(world, [MOVED])
    hw.settle(world)

    assert before and _layers_of(world, sibling, b) == before
    assert _official(world)[("J1", 3.0, 2.0)][1] == "agreed"
    assert hw.said(world) == [("J1", "7.0"), ("J1", "9.0")]


@pytest.mark.pg
def test_rows_left_behind_before_this_landing_are_cleaned_by_replaying_the_recount_then_the_copy(
        world, monkeypatch):
    """RUN.md's sentence, measured: an old key left by the code before - its A layer and its hold
    standing - goes when the recount is replayed (its hold) and then the copy rule (its layer). A
    script replay wakes no other rule, so both are run. 🔴 IN THAT ORDER: the copy first empties
    the old row's value while its hold still says agreed, and the ledger refuses that row."""
    from chain import replay

    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    real = worker.apply_chain_writes
    monkeypatch.setattr(worker, "apply_chain_writes",
                        lambda *a, **k: real(*a, **dict(k, edit_retractions=None)))
    hw.push(world, [MOVED])
    hw.settle(world)
    monkeypatch.setattr(worker, "apply_chain_writes", real)
    a, old = _log_row(world, "A"), _official(world)[OLD][0]
    assert _layers_of(world, old, a) and _official(world)[OLD][1] == "agreed", "nothing was left behind"
    copy, recount = (next(r for r in world["rules"] if r["name"] == name) for name in (hw.RULE["name"],
                                                                                        hw.RECOUNT["name"]))

    replay.replay_rule(world["db"], recount, apply=True)
    hw.settle(world)
    assert not _official(world)[OLD][1] and _layers_of(world, old, a)
    assert hw.said(world) == [("J1", "7.0")]

    replay.replay_rule(world["db"], copy, apply=True)
    hw.settle(world)
    assert _layers_of(world, old, a) == []
    assert _official(world)[NEW][1] == "agreed"
    assert hw.said(world) == [("J1", "7.0")]


# ---------------------------------------------------------------------------------------------
# PG - a join's fan-out: one value row fills many left rows, then its key moves (총괄 10-08)
# ---------------------------------------------------------------------------------------------

JL, JR = "er_join_left", "er_join_right"
JOIN_TABLES = {
    JL: {"business_key": "lk", "composite_key_source": ["lk"],
         "column_types": {"lk": "string", "dt_job": "string", "netdie": "number"},
         "display_columns": ["lk", "dt_job", "netdie"]},
    JR: {"business_key": "rk", "composite_key_source": ["rk"],
         "column_types": {"rk": "string", "dt_job": "string", "netdie": "number"},
         "display_columns": ["rk", "dt_job", "netdie"]},
}
JOIN = {"name": "er_join", "on": {"table": JR},
        "derive": {"kind": "join", "join": {"on": [{"left": "dt_job", "right": "dt_job"}],
                                            "take": [{"from": "netdie", "into": "netdie"}]}},
        "into": {"table": JL}}
JOIN_SOURCE = "er_join_left_src"
JOIN_LEFT_ROWS = 30


@pytest.fixture(name="join_world")
def fixture_join_world(pg_engine, monkeypatch, tmp_path):
    from pathlib import Path
    from sqlalchemy import MetaData
    from conftest import PG_TEST_SCHEMA, retire_dynamic_model
    from ledger import followup, schema
    from ledger.implementations import role_mapper_registry, trusted_implementations
    from ledger.setup import LedgerSetup
    from ledger.setup_bundle import load_physical_catalog, require_ready_bundle, validate_bundle
    from ledger.setup_registry import compile_setup_snapshot
    from datetime import datetime, timezone

    mapper_sdk.discover()
    saved = dict(crud.TABLE_CONFIG)
    for name in JOIN_TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(JOIN_TABLES)
    crud.TABLE_CONFIG.update(JOIN_TABLES)

    def clean():
        with pg_engine.begin() as conn:
            for name in JOIN_TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
            for table in ("cell_sources", "database_outbox"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name IN (:a, :b)' % (PG_TEST_SCHEMA, table)),
                             {"a": JL, "b": JR})
            for table in (schema.LEDGER_TABLE, schema.ROW_REF_TABLE):
                conn.execute(text('DELETE FROM "%s".%s WHERE source_who = :s' % (PG_TEST_SCHEMA, table)),
                             {"s": JOIN_SOURCE})
            conn.execute(text('DELETE FROM "%s".%s WHERE source = :s' % (PG_TEST_SCHEMA, schema.CURSOR_TABLE)),
                         {"s": JOIN_SOURCE})

    raw = pg_engine.raw_connection()
    try:
        schema.ensure_schema(raw)
        raw.commit()
        schema.ensure_partition(raw, datetime.now(timezone.utc))
    finally:
        raw.close()
    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in JOIN_TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    rules_path = tmp_path / "chain_rules.json"
    rules_path.write_text(json.dumps({"rules": [JOIN]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(rules_path))
    rules = [r for r in worker.load_chain_rules() if str(r.get("name", "")).startswith("er_join")]
    assert rules, "the join stood no rule"
    monkeypatch.setattr(worker, "loaded_chain_rules", lambda: rules)
    sample = hw.sample("table_config.json.sample")
    sample.update(JOIN_TABLES)
    catalog_path = tmp_path / "table_config.json"
    catalog_path.write_text(json.dumps(sample), encoding="utf-8")
    catalog = load_physical_catalog(catalog_path)
    doc = hw.sample("ledger_config.json.sample")
    doc["sources"] = {JOIN_SOURCE: {
        "relation": JL, "read": {"exclude_when": [{"column": "netdie", "blank": True}]},
        "map": {"implementation_id": "declarative-role", "implementation_version": 1},
        "bind": {"mappings": {"counted": {"predicate": "has_netdie@1", "bind": {
            "subject": {"kind": "entity", "entity_type": "dtjob@1",
                        "keys": {"dt_job": {"kind": "column", "column": "dt_job"}}},
            "value": {"kind": "column", "column": "netdie"}}}}}}}
    bundle = require_ready_bundle(validate_bundle(doc, catalog=catalog))
    setup = LedgerSetup(config_root=Path(hw.SAMPLE), bundle=bundle,
                        snapshot=compile_setup_snapshot(bundle, trusted_implementations(), catalog=catalog),
                        mappers=role_mapper_registry(), catalog=catalog)
    from support.isolated_pg import scratch_connect_args

    # pooled, as the product's engine is - on the test's NullPool every drain opens new connections
    pooled = create_engine(pg_engine.url, connect_args=scratch_connect_args(PG_TEST_SCHEMA), pool_size=5)
    session = sessionmaker(autocommit=False, autoflush=False, bind=pooled)()
    followup.reset()
    try:
        yield {"db": session, "engine": pooled, "setup": setup, "rules": rules}
    finally:
        session.close()
        pooled.dispose()
        followup.reset()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in JOIN_TABLES:
            retire_dynamic_model(name)


def _join_push(world, table, rows):
    from database.context import channel, outbox_mode

    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(world["db"], table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name="user", updated_by="er") for r in rows]))
    world["db"].commit()


def _join_settle(world):
    from ledger import followup

    db = world["db"]
    for _ in range(12):
        pending = (db.query(models.DatabaseOutbox)
                   .filter(models.DatabaseOutbox.processed_chain.is_(False),
                           models.DatabaseOutbox.table_name.in_([JL, JR]))
                   .order_by(models.DatabaseOutbox.id).all())
        if not pending:
            break
        by_tx = {}
        for item in pending:
            by_tx.setdefault(get_payload_dict(item).get("transaction_id"), []).append(item)
        for tx_id, events in by_tx.items():
            ok, error, _ = worker._process_chain_transaction_group_sync(tx_id, events, db, world["rules"])
            assert ok, error
            for item in events:
                event_constants.mark_processed(item, "SUCCESS")
            db.commit()
    while True:
        done = followup.drain_outbox_once(world["engine"], world["setup"])
        if done is None:
            return
        assert not any("error" in (s or {}) for s in (done.get("sources") or {}).values()), done


def _join_state(world):
    from ledger import schema

    with world["engine"].connect() as conn:
        filled = dict(conn.execute(text('SELECT dt_job, count(netdie) FROM "%s" GROUP BY dt_job' % JL)).fetchall())
        atoms = dict(conn.execute(text(
            "SELECT subject_keys->>'dt_job', count(*) FROM %s WHERE source_who = :s GROUP BY 1"
            % schema.LEDGER_TABLE), {"s": JOIN_SOURCE}).fetchall())
    return {"filled": filled, "atoms": atoms}


@pytest.mark.pg
def test_a_join_value_row_moved_to_a_key_no_left_row_carries_empties_what_it_filled(join_world, monkeypatch):
    from chain import rule_run

    _join_push(join_world, JL, [{"lk": "L%03d" % i, "dt_job": "J1" if i < JOIN_LEFT_ROWS else "J2"}
                                for i in range(2 * JOIN_LEFT_ROWS)])
    _join_push(join_world, JR, [{"rk": "r1", "dt_job": "J1", "netdie": 7}])
    _join_settle(join_world)
    assert _join_state(join_world) == {"filled": {"J1": JOIN_LEFT_ROWS, "J2": 0}, "atoms": {"J1": JOIN_LEFT_ROWS}}

    # the join writes the new key's rows: the old key's give their value back (as on 91da9c781)
    _join_push(join_world, JR, [{"rk": "r1", "dt_job": "J2"}])
    _join_settle(join_world)
    assert _join_state(join_world) == {"filled": {"J1": 0, "J2": JOIN_LEFT_ROWS}, "atoms": {"J2": JOIN_LEFT_ROWS}}

    # no left row carries J9: the join proposes nothing, and what it filled under J2 still goes - after
    # a restart too, when nothing of it was seen: the join's declaration says what it writes
    monkeypatch.setattr(rule_run, "_ORIGIN_SEEN", {})
    monkeypatch.setattr(rule_run, "_COLUMNS_SEEN", {})
    _join_push(join_world, JR, [{"rk": "r1", "dt_job": "J9"}])
    _join_settle(join_world)
    assert _join_state(join_world) == {"filled": {"J1": 0, "J2": 0}, "atoms": {}}
