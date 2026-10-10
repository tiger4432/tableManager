# -*- coding: utf-8 -*-
"""총괄 eddf9e38e — a withdrawal's value changes go out as collapsed events, and the per-row ones it
queued before fold into collapsed ones per table (`cell_layer.fold_withdrawal_events`), on PostgreSQL.

  ① 1,000 source rows deleted     the withdrawal stages no per-row event; the follow-up drains none row by row
  ② 2,500 per-row events, 2 tx     3 collapsed events, the same rows; every other event as it was; again 0
     the envelope                  depth, channel, cascade, written_by and run carried; a run's own id not stamped
     the end state                 the chain on the folded events ends where it ends on the per-row ones -
                                   a person's edit after the fold included
"""
import contextlib
import os
import sys
import uuid

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                               # noqa: E402
from admin import retroactive                                        # noqa: E402
from chain import cell_layer                                         # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from database.context import (cascade, channel, outbox_mode,         # noqa: E402
                              request_chain_depth, retroactive_run, written_by)
from ledger import followup                                          # noqa: E402
from runtime import running                                          # noqa: E402
from support import hold_world as hw                                 # noqa: E402
from utils.payload_helper import get_payload_dict                    # noqa: E402

pytestmark = pytest.mark.pg
OUTBOX = models.DatabaseOutbox


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=True)


def _official_rows(world, n):
    db = world["db"]
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"dt_job": "J%d" % i, "dt_x": i, "dt_y": 1, "netdie": i},
                                      source_name="user", updated_by="hc") for i in range(n)]))
    db.commit()
    model = models.DYNAMIC_TABLES[hw.OFFICIAL]
    return db.query(model).order_by(model.dt_x).all()


def _per_row(world, rows, who=cell_layer.R2_AUDIT_SOURCE, source=cell_layer.R1_SOURCE_NAME,
             depth=None, doors=()):
    """One EDIT per row in one transaction, as a withdrawal staged them before eddf9e38e (or, with
    `who`/`source`, as anyone else's per-row write). -> the transaction id."""
    db = world["db"]
    tx = "%s_%s" % (who, uuid.uuid4().hex[:8])
    with contextlib.ExitStack() as stack:
        stack.enter_context(crud.transaction_context(who, tx, source))
        for door in doors:
            stack.enter_context(door)
        stack.callback(request_chain_depth.reset, request_chain_depth.set(depth))
        for row in rows:
            row.note = "n%s" % uuid.uuid4().hex[:6]
        db.commit()
    return tx


def _events(world):
    world["db"].expire_all()
    return {e.id: (e.table_name, e.event_type, e.status, e.processed_chain, get_payload_dict(e))
            for e in world["db"].query(OUTBOX).filter(OUTBOX.table_name.in_([hw.LOG, hw.OFFICIAL]))}


# ------------------------------------------------------------------ ① the withdrawal writes collapsed

def test_a_withdrawal_of_a_thousand_rows_stages_no_event_row_by_row(world, monkeypatch):
    calls = []
    real = followup.drain_outbox_once

    def recorded(*a, **k):
        done = real(*a, **k)
        if done is not None:
            calls.append((done.get("table"), done.get("event_type"), done.get("rows")))
        return done
    monkeypatch.setattr(followup, "drain_outbox_once", recorded)
    db = world["db"]
    rows = [{"log_id": "R%04d" % i, "dt_job": "J%d" % (i % 7), "dt_x": i, "dt_y": 1, "netdie": i}
            for i in range(1000)]
    with channel(event_constants.CHANNEL_API), outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED):
        crud.apply_batch_updates(db, hw.LOG, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(r), source_name="user", updated_by="hc") for r in rows]))
    db.commit()
    hw.settle(world)
    last = db.query(OUTBOX.id).order_by(OUTBOX.id.desc()).first()[0]
    ids = [r[0] for r in db.execute(text('SELECT row_id FROM "%s"' % hw.LOG))]
    crud.delete_rows_batch(db, hw.LOG, ids, "hc")
    db.commit()
    hw.run_chain(world)
    calls.clear()
    while not any(kind == "DELETE" for _t, kind, _r in calls):
        assert followup.drain_outbox_once(world["engine"], world["setup"]) is not None
    deleted = next(n for _t, kind, n in calls if kind == "DELETE")
    worker._retract_what_those_rows_fed(db, hw.LOG, [r for r in ids])
    db.commit()
    staged = [p for _i, (table, _k, _s, _d, p) in sorted(_events(world).items())
              if _i > last and table == hw.OFFICIAL and p.get("updated_by") == cell_layer.R2_AUDIT_SOURCE]
    # the values revealed (one event per 1,000 rows) and the rows that lost a layer (`_withdraw_and_tell`)
    assert (deleted, [len(p.get("row_ids") or ()) for p in staged]) == (1000, [1000, 1000])
    calls.clear()
    hw.settle(world)
    # the two above and the recount's write; with the DELETE, 4 - ca0d23b08 measured 1,003, 1,000 one row each.
    # And the rows the recount left with only the chain's keys go, one collapsed DELETE (총괄 5eee501eb)
    assert calls == [(hw.OFFICIAL, "EDIT", 1000)] * 3 + [(hw.OFFICIAL, "DELETE", 1000)], calls


# ------------------------------------------------------------------ ② the queued ones fold

def test_queued_withdrawal_events_fold_per_table_and_nothing_else_moves(world, monkeypatch):
    db = world["db"]
    rows = _official_rows(world, 2600)
    tx1 = _per_row(world, rows[:1500])
    tx2 = _per_row(world, rows[1500:2500])
    _per_row(world, rows[2500:2505], who="hc", source="user")                  # a person's edits, row by row
    _per_row(world, rows[2505:2506])                                           # one the chain already ran
    ran = max(_events(world))
    db.query(OUTBOX).filter(OUTBOX.id == ran).update({"processed_chain": True, "status": "SUCCESS"})
    _per_row(world, rows[2506:2507])                                           # one the chain tried
    tried = max(_events(world))
    db.query(OUTBOX).filter(OUTBOX.id == tried).update({"status": "RETRYING", "retry_count": 1})
    held = _per_row(world, rows[2507:2514])                                    # a line the chain runs now
    db.commit()
    with channel(event_constants.CHANNEL_API):                                 # another table, row by row
        crud.apply_batch_updates(db, hw.LOG, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"log_id": "L%d" % i, "dt_job": "J1", "dt_x": i, "dt_y": 1},
                                      source_name="user", updated_by="hc") for i in range(3)]))
    db.commit()
    monkeypatch.setattr(running, "chain_lines_running", lambda beats=None: {held: {"stage": "mapper"}})
    before = _events(world)
    folding = {i for i, (_t, _k, _s, _d, p) in before.items() if p.get("transaction_id") in (tx1, tx2)}
    assert len(folding) == 2500

    preview = cell_layer.fold_withdrawal_events(db)
    detail = retroactive.count(db, "fold_withdrawal_events", {})["detail"]
    done = cell_layer.fold_withdrawal_events(db, apply=True)
    after = _events(world)

    assert {i: e for i, e in before.items() if i not in folding} == {i: e for i, e in after.items() if i in before}
    assert done == dict(preview, pages=done["pages"]) and done["by_table"] == {hw.OFFICIAL: [2500, 3]}
    assert (done["rows"], done["retrying"], done["running"]) == (2500, 1, 7)
    assert detail.startswith("'hc_official' 2500 event(s) -> 3 - 2500 row(s). Left as they are: 1 event(s) "
                             "the chain already tried (RETRYING), 7 on a line the chain runs now."), detail
    made = [e for i, e in sorted(after.items()) if i not in before]
    assert [(t, k, s, d, len(p["row_ids"])) for t, k, s, d, p in made] == [
        (hw.OFFICIAL, "EDIT", "PENDING", False, 1000)] * 2 + [(hw.OFFICIAL, "EDIT", "PENDING", False, 500)]
    # 총괄: every row the per-row events named is named again - one missing is a withdrawal lost
    assert sorted((t, r) for t, _k, _s, _d, p in made for r in p["row_ids"]) == sorted(
        (before[i][0], before[i][4]["row_id"]) for i in folding)
    assert {(p["updated_by"], p["source_name"], p["transaction_id"].startswith(cell_layer.R2_AUDIT_SOURCE + "_"),
             p["transaction_id"] in (tx1, tx2), tuple(sorted(set(p) & {"columns", "chain_depth", "run_id"})))
            for _t, _k, _s, _d, p in made} == {(cell_layer.R2_AUDIT_SOURCE, cell_layer.R1_SOURCE_NAME, True, False, ())}
    assert cell_layer.fold_withdrawal_events(db, apply=True)["by_table"] == {}


def test_a_fold_carries_each_group_s_envelope_and_not_its_own_run(world):
    db = world["db"]
    rows = _official_rows(world, 9)
    _per_row(world, rows[:4], depth=2, doors=(channel(event_constants.CHANNEL_CHAIN), cascade(True),
                                              written_by([hw.RECOUNT["name"]])))
    _per_row(world, rows[4:9], doors=(retroactive_run("RUN-OLD"),))
    before = set(_events(world))
    with retroactive_run("RUN-FOLD"):                                         # where `_run_to_the_end` runs it
        out = retroactive._run_fold_withdrawal_events(db, {}, log=lambda m: None)
    made = sorted(((len(p["row_ids"]), {k: p.get(k) for k in ("chain_depth", "channel", "cascade",
                                                               "written_by", "run_id")})
                   for i, (_t, _k, _s, _d, p) in _events(world).items() if i not in before), key=lambda m: m[0])
    assert (out["events_folded"], out["events_made"]) == (9, 2)
    assert made == [
        (4, {"chain_depth": 2, "channel": event_constants.CHANNEL_CHAIN, "cascade": True,
             "written_by": [hw.RECOUNT["name"]], "run_id": None}),
        (5, {"chain_depth": None, "channel": None, "cascade": None, "written_by": None, "run_id": "RUN-OLD"})]


# ------------------------------------------------------------------ the end state

def _ends_where(pg_engine, monkeypatch, tmp_path, fold):
    """Two source rows a key, one deleted; its withdrawal queued row by row, as before eddf9e38e;
    [the fold]; then a person edits one of those rows; the chain and the follow-up to the end."""
    tmp_path.mkdir()
    with contextlib.closing(hw.build(pg_engine, monkeypatch, tmp_path, batch=True)) as built:
        world = next(built)
        db = world["db"]
        keys = [{"dt_job": "J%d" % i, "dt_x": i, "dt_y": 1} for i in range(20)]
        hw.push(world, [{"log_id": "A%d" % i, **k, "netdie": 7} for i, k in enumerate(keys)])
        hw.settle(world)
        hw.push(world, [{"log_id": "B%d" % i, **k, "netdie": 9} for i, k in enumerate(keys)])
        hw.settle(world)
        ids = [r[0] for r in db.execute(text('SELECT row_id FROM "%s" WHERE log_id LIKE \'B%%\'' % hw.LOG))]
        crud.delete_rows_batch(db, hw.LOG, ids, "hc")
        db.commit()
        hw.run_chain(world)
        while followup.drain_outbox_once(world["engine"], world["setup"]) is not None:
            pass
        with monkeypatch.context() as before_the_fix:
            before_the_fix.setattr("database.context.outbox_mode", lambda mode: contextlib.nullcontext())
            worker._retract_what_those_rows_fed(db, hw.LOG, ids)
            db.commit()
        queued = [p for _t, _k, _s, d, p in _events(world).values()
                  if not d and p.get("row_id") and p.get("updated_by") == cell_layer.R2_AUDIT_SOURCE]
        if fold:
            cell_layer.fold_withdrawal_events(db, apply=True)
        left = [p for _t, _k, _s, d, p in _events(world).values()
                if not d and p.get("row_id") and p.get("updated_by") == cell_layer.R2_AUDIT_SOURCE]
        with channel(event_constants.CHANNEL_API):
            crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates={**keys[0], "netdie": 42}, source_name="user",
                                          updated_by="hc")]))
            db.commit()
        hw.settle(world)
        with world["engine"].connect() as conn:
            official = sorted(tuple(r) for r in conn.execute(text(
                'SELECT dt_job, dt_x, netdie, hold FROM "%s"' % hw.OFFICIAL)))
        return len(queued), len(left), official, sorted((j, float(v)) for j, v in hw.said(world))


def test_the_chain_ends_where_it_ended_on_the_per_row_events(pg_engine, monkeypatch, tmp_path):
    queued, left, official, said = _ends_where(pg_engine, monkeypatch, tmp_path / "per_row", fold=False)
    queued_f, left_f, official_f, said_f = _ends_where(pg_engine, monkeypatch, tmp_path / "folded", fold=True)
    assert (queued, left, queued_f, left_f) == (20, 20, 20, 0)
    assert official_f == official and said_f == said
    assert (official[0], said[0]) == (("J0", 0, 42, "agreed"), ("J0", 42.0))
