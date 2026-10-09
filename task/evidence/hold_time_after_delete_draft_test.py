# -*- coding: utf-8 -*-
"""DRAFT (application lane, lead message 10-09): a key's two source rows differ only in time; one is deleted
from the grid; the hold recounts to agreed - and the official time cell?

For the implementer to move into server/tests/. The world is support.hold_world with a datetime column
copied too; every seat is the product's (crud writes, the chain's group body, followup.drain_once, the
worker's withdrawal after a drained deletion). PostgreSQL scratch schema (pg_engine).

Today: the copy layers alone go back to the survivor (green). With one more layer on the official cell
under a REGISTERED name - plain `chain_ingestion` (rank 4) - that layer is shown before, after and
throughout, older or newer: the per-row copy layer `chain_ingestion (<row_id>)` is unregistered (99) and
never outranks it. That cell is red. A person's value (rank 0) staying is pinned as green.
"""
import os
import sys

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from support import hold_world as hw                                 # noqa: E402

pytestmark = pytest.mark.pg

EARLY, LATE, OTHER = "2026-10-09T10:00:00+09:00", "2026-10-09T10:05:00+09:00", "2026-10-09T09:00:00+09:00"


@pytest.fixture(name="world", params=[True, False], ids=["batch", "one_row"])
def fixture_world(request, pg_engine, monkeypatch, tmp_path):
    tables = {name: {**spec, "column_types": {**spec["column_types"], "evt_time": "datetime"},
                     "display_columns": spec["display_columns"] + ["evt_time"]}
              for name, spec in hw.TABLES.items()}
    params = {**hw.RULE["params"], "columns": ["netdie", "evt_time"]}
    monkeypatch.setattr(hw, "TABLES", tables)
    monkeypatch.setattr(hw, "RULE", {**hw.RULE, "params": params})
    monkeypatch.setattr(hw, "RECOUNT", {**hw.RECOUNT, "params": {**params, "source_table": hw.LOG}})
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=request.param)


def _same_instant(a, b):
    from database import crud
    return crud.value_key(a, "datetime") == crud.value_key(b, "datetime")


def _delete_from_the_grid(world, log_id):
    """The grid's delete routes' body: crud.delete_rows_batch, under the API channel."""
    from database import crud
    from database.context import channel
    db = world["db"]
    row_id = db.execute(text('SELECT row_id FROM "%s" WHERE log_id = :l' % hw.LOG), {"l": log_id}).scalar()
    with channel(event_constants.CHANNEL_API):
        crud.delete_rows_batch(db, hw.LOG, [row_id], "owner")
        db.commit()


def _write_official(world, source_name, value):
    from database import crud, schemas
    from database.context import channel
    db = world["db"]
    with channel(event_constants.CHANNEL_API if source_name == "user" else event_constants.CHANNEL_CHAIN):
        crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={**hw.KEY, "evt_time": value}, source_name=source_name,
                                      updated_by="other")]))
        db.commit()


@pytest.mark.parametrize("batches", [1, 2], ids=["one_batch", "two_batches"])
@pytest.mark.parametrize("drop, survivor", [("B", EARLY), ("A", LATE)], ids=["late_shown", "early_hidden"])
def test_the_time_cell_comes_back_to_the_survivor(world, batches, drop, survivor):
    rows = [{"log_id": "A", **hw.KEY, "netdie": 7, "evt_time": EARLY},
            {"log_id": "B", **hw.KEY, "netdie": 7, "evt_time": LATE}]
    for chunk in ([rows] if batches == 1 else [rows[:1], rows[1:]]):
        hw.push(world, chunk)
        hw.settle(world)
    assert hw.hold(world) in (None, "")                          # canary: the two times clash
    _delete_from_the_grid(world, drop)
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert _same_instant(hw.official(world).evt_time, survivor)


def test_an_older_plain_chain_layer_does_not_outrank_the_surviving_copy(world):
    """RED today: a plain `chain_ingestion` layer (another rule, an earlier one) written BEFORE both copies
    is shown before and after the delete - the copies' per-row layers are unregistered (99), it is 4."""
    from database import crud
    _write_official(world, crud.CHAIN_SOURCE, OTHER)
    hw.settle(world)
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7, "evt_time": EARLY}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 7, "evt_time": LATE}])
    hw.settle(world)
    _delete_from_the_grid(world, "B")
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert _same_instant(hw.official(world).evt_time, EARLY)    # <- red today: shows OTHER


def test_a_persons_value_on_the_cell_stays(world):
    """A person's edit (rank 0) outranks every machine layer, before and after - by design."""
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7, "evt_time": EARLY}])
    hw.settle(world)
    _write_official(world, "user", OTHER)
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 7, "evt_time": LATE}])
    hw.settle(world)
    _delete_from_the_grid(world, "B")
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert _same_instant(hw.official(world).evt_time, OTHER)
