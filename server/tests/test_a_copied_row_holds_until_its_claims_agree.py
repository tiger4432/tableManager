# -*- coding: utf-8 -*-
"""총괄 3211e9000 — 보류 포함 행 복사, end to end on PostgreSQL.

Source rows copy into the same-key official row (`copy_rows_with_hold`, the owner's
`copy_one_row` plus params and a count); the hold says whether the key's source rows agree, and a
ledger source reading the official table with `read.exclude_when` on the hold says nothing about a
held row. Every seat is the product's: crud writes, the chain's transaction-group body,
`followup.drain_once`.

  one source row                     agreed, the ledger says its value
  two rows, different values         blank, the ledger's atom is withdrawn
  two rows, the same values          agreed
  every commit                       a row whose values changed carries the hold of that moment
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from support import hold_world as hw                                 # noqa: E402
from utils.payload_helper import get_payload_dict                   # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world", params=[True, False], ids=["batch", "one_row"])
def fixture_world(request, pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=request.param)


def test_one_source_row_is_agreed_and_said(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]


def test_two_different_rows_hold_it_and_its_atom_is_withdrawn(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert len(hw.said(world)) == 1
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert hw.hold(world) in (None, "")
    assert hw.said(world) == []


def test_two_rows_with_the_same_values_stay_agreed(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]


@pytest.mark.parametrize("batches", [1, 2], ids=["one_batch", "two_batches"])
def test_no_commit_shows_new_values_without_their_hold(world, batches):
    """「원장이 보류 칸 없이 값만 본 횟수 0」, measured on every commit: values and hold travel in
    one item list, so they land together whether the clashing rows come in one batch or two."""
    rows = [{"log_id": "A", **hw.KEY, "netdie": 7}, {"log_id": "B", **hw.KEY, "netdie": 9}]
    for chunk in ([rows] if batches == 1 else [rows[:1], rows[1:]]):
        hw.push(world, chunk)
        hw.settle(world)
    assert hw.hold(world) in (None, "")
    assert world["stale"] == []
    assert hw.said(world) == []


# ------------------------------------------------------------------ the recount (3ba1d1dd4)

def test_deleting_the_clashing_row_recounts_the_hold_to_agreed(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
    hw.delete(world, "B")
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world)) == (7, "agreed")
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]


def test_deleting_the_row_whose_value_is_hidden_recounts_the_hold_too(world):
    """총괄 e11bb4de0 (나): withdrawing a layer that was not the shown one changes no cell, so only
    the delete path's own EDIT wakes the recount."""
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
    hw.delete(world, "A")
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world)) == (9, "agreed")
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 9.0)]
    assert len(hw.recount_writes(world)) == 1


def test_a_deleted_row_that_fed_nothing_stages_no_event(world):
    from database import models
    from chain import ingestion_worker as worker
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    before = world["db"].query(models.DatabaseOutbox).count()
    worker._retract_what_those_rows_fed(world["db"], hw.LOG, ["01890000-0000-7000-8000-000000000000"])
    world["db"].commit()
    assert world["db"].query(models.DatabaseOutbox).count() == before


def test_the_two_left_agreeing_are_agreed_and_the_recount_writes_once(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "C", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert (hw.official(world).netdie, hw.hold(world) or "") == (9, "")
    hw.delete(world, "B")
    hw.settle(world)
    assert hw.hold(world) == "agreed"
    assert len(hw.recount_writes(world)) == 1          # '' -> agreed, once; equal holds write nothing
    # 총괄 e11bb4de0 (나): the shown value moved, so the recount was woken TWICE - its own edit
    # and the delete path's - and the second wrote nothing, so it left no event either
    from chain import cell_layer
    from database import models
    woke = [e for e in world["db"].query(models.DatabaseOutbox).filter_by(table_name=hw.OFFICIAL)
            if get_payload_dict(e).get("updated_by") == cell_layer.R2_AUDIT_SOURCE]
    assert len(woke) == 2


# ------------------------------------------------------------------ one batch (32bab7896 · cb3d3c1bf)

def _netdie_layers(world):
    from database import models
    world["db"].expire_all()
    return sorted((s.source_name, s.origin_row_id) for s in world["db"].query(models.CellSource)
                  .filter_by(table_name=hw.OFFICIAL, column_name="netdie").all())


def _row_id(world, log_id):
    from sqlalchemy import text
    return world["db"].execute(text('SELECT row_id FROM "%s" WHERE log_id = :l' % hw.LOG),
                               {"l": log_id}).scalar()


def test_two_rows_of_one_key_in_one_batch_keep_a_layer_each(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}, {"log_id": "B", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    a, b = _row_id(world, "A"), _row_id(world, "B")
    assert _netdie_layers(world) == sorted([("chain_ingestion (%s)" % a, a),
                                            ("chain_ingestion (%s)" % b, b)])
    hw.delete(world, "B")
    hw.settle(world)
    assert _netdie_layers(world) == [("chain_ingestion (%s)" % a, a)]


def test_a_key_whose_source_rows_are_all_deleted_goes_and_is_unsaid(world):
    """The recount empties the hold and the row is left with only the chain's keys - it goes (총괄
    5eee501eb · 판정 ㄱ: it was held blank and stayed, a shell)."""
    from database import models

    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "C", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed" and len(hw.said(world)) == 1
    hw.delete(world, "A")
    hw.settle(world)
    hw.delete(world, "C")
    hw.settle(world)
    assert world["db"].query(models.DYNAMIC_TABLES[hw.OFFICIAL]).count() == 0
    assert hw.said(world) == []


def test_the_delete_paths_edit_names_what_lost_a_layer_and_wakes_only_opted_in_rules(world):
    """총괄 e11bb4de0 (나). A human layer carrying the deleted row's stamp is skipped, so its column
    is not named; the event rides the chain channel, so a rule that does not opt in stays asleep."""
    from chain import ingestion_worker as worker
    from database import models
    db = world["db"]
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    a, official_id = _row_id(world, "A"), hw.official(world).row_id
    named = sorted({c for (c,) in db.query(models.CellSource.column_name).filter_by(origin_row_id=a)})
    db.add(models.CellSource(table_name=hw.OFFICIAL, row_id=official_id, column_name="note",
                             source_name="user", value="x", origin_row_id=a, updated_by="t"))
    db.commit()
    last = db.query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()[0]
    worker._retract_what_those_rows_fed(db, hw.LOG, [a])
    new = db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > last).all()
    assert "note" not in named and named
    assert [(e.event_type, e.table_name) for e in new] == [("EDIT", hw.OFFICIAL)]
    payload = get_payload_dict(new[0])
    assert (payload["row_ids"], payload["columns"]) == ([official_id], named)
    # the channel, not only the source name: the guard reading `chain_ingestion` as the chain retires
    assert event_constants.channel_of(payload) == event_constants.CHANNEL_CHAIN
    assert worker.fire_refusal(hw.RECOUNT, new[0]) is None
    asleep = {**hw.RECOUNT, "allow_chain_trigger": False}
    assert worker.fire_refusal(asleep, new[0]) == worker.FIRE_REFUSED_CHAIN
