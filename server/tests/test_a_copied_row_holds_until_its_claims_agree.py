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

from support import hold_world as hw                                 # noqa: E402

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
# ⚠️ The deleted row is the one whose value shows: withdrawing a hidden value changes no shown
#    cell and leaves no event today - the delete path's own event lands next (총괄 e11bb4de0 (나)).

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


def test_a_key_whose_source_rows_are_all_deleted_is_held_and_unsaid(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "C", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    assert hw.hold(world) == "agreed" and len(hw.said(world)) == 1
    hw.delete(world, "A")
    hw.settle(world)
    hw.delete(world, "C")
    hw.settle(world)
    assert hw.hold(world) in (None, "")
    assert hw.said(world) == []
