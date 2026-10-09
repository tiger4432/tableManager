# -*- coding: utf-8 -*-
"""총괄 5eee501eb · 판정 ㄱ (소유자 10-09 「체인한 거 회수할 때 왜 소스 하나도 안 남은 거 행 안 지움? 키값만 남아 있네」 ·
「공식표에 껍데기 행 잔뜩 쌓여 있음」): a row the chain's write empties, left with only the chain's key layers, is
deleted through the grid's door; the shells already there go by one retroactive operation on the same judgement
(`cell_layer.shells`). On PostgreSQL, through the product's seats - the chain's group body, the ledger follow-up,
the worker's withdrawal after a drained deletion.

  ① every source row gone       the recount empties the hold -> the official row goes · a history line · the ledger
                                 says nothing · its DELETE wakes no rule
  ② a person's layer            even one that emptied a cell -> the row stays
  ③ another source still claims -> the row stays, agreed
  ④ the fold marked the only row of a key -> that official row goes, the other stays
  ⑤ the sweep                   its preview is what it deletes, and then nothing
  ⑥ key layers                  a person's or a file's keys -> the row stays
"""
import logging
import os
import sys

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                               # noqa: E402
from admin import retroactive                                        # noqa: E402
from chain import cell_layer, replay                                 # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from database.context import channel, retroactive_run                # noqa: E402
from support import hold_world as hw                                 # noqa: E402

pytestmark = pytest.mark.pg
MARK = "fold_mark"


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=True)


@pytest.fixture(name="marking_world")
def fixture_marking_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=True, exclude=[MARK])


def _official(world):
    with world["engine"].connect() as conn:
        return {(job, int(x), int(y)): (row_id, None if netdie is None else float(netdie), hold or "")
                for row_id, job, x, y, netdie, hold in conn.execute(text(
                    'SELECT row_id, dt_job, dt_x, dt_y, netdie, hold FROM "%s"' % hw.OFFICIAL))}


def _write_official(world, source, cells, on=event_constants.CHANNEL_API):
    db = world["db"]
    with channel(on):
        crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates=dict(cells), source_name=source, updated_by="shell_test")]))
        db.commit()


def _edit_note(world, row_id, value):
    """A person's edit of `note` alone, by row id - the keys keep only the chain's layers."""
    db = world["db"]
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            row_id=row_id, updates={"note": value}, source_name="user", updated_by="shell_test")]))
        db.commit()


def _person_layers(world, row_id):
    return sorted((s.column_name, s.value or "") for s in world["db"].query(models.CellSource).filter_by(
        table_name=hw.OFFICIAL, row_id=row_id, source_name="user"))


def test_1_every_source_gone_the_official_row_goes(world, caplog):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    [(row_id, netdie, hold)] = _official(world).values()
    assert (netdie, hold) == (7.0, "agreed"), "canary: one claim, agreed"
    last = world["db"].query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()[0]
    with caplog.at_level(logging.INFO):
        hw.delete(world, "A")
        hw.settle(world)
    assert _official(world) == {}
    assert "[ChainShell] table=%s rows_deleted=1 - only the chain's keys were left" % hw.OFFICIAL in [
        r.getMessage() for r in caplog.records]
    history = world["db"].query(models.AuditLog).filter_by(table_name=hw.OFFICIAL, row_id=row_id,
                                                           column_name="DELETE").all()
    assert [h.updated_by for h in history] == [cell_layer.SHELL_DELETER]
    assert hw.said(world) == []
    deletions = [e for e in world["db"].query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > last)
                 if e.table_name == hw.OFFICIAL and e.event_type == "DELETE"]
    assert deletions and not [(r["name"], e.id) for e in deletions for r in world["rules"]
                              if worker._is_trigger_event(e) and worker.fires(r, e)], "the deletion wakes a rule"
    said = [r.getMessage() for r in caplog.records]
    shell_at = said.index("[ChainShell] table=%s rows_deleted=1 - only the chain's keys were left" % hw.OFFICIAL)
    assert not [line for line in said[shell_at:] if "[ChainRule] rule=" in line], "a rule ran after the deletion"


def test_2_a_persons_layer_even_one_that_emptied_a_cell_keeps_the_row(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    [(row_id, _netdie, _hold)] = _official(world).values()
    _edit_note(world, row_id, "seen")
    _edit_note(world, row_id, "")
    hw.settle(world)
    assert _person_layers(world, row_id) == [("note", "")], "canary: the person's only layer is an emptied cell"
    hw.delete(world, "A")
    hw.settle(world)
    [(_row_id, netdie, hold)] = _official(world).values()
    assert (netdie, hold) == (None, "")


def test_3_another_source_still_claiming_keeps_the_row(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}, {"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    hw.delete(world, "A")
    hw.settle(world)
    [(_row_id, netdie, hold)] = _official(world).values()
    assert (netdie, hold) == (9.0, "agreed")


def test_4_the_fold_marked_the_only_row_of_a_key_and_that_official_row_goes(marking_world):
    world = marking_world
    hw.push(world, [{"log_id": "A", "dt_job": "J1", "dt_x": 1, "dt_y": 2, "netdie": 7},
                    {"log_id": "B", "dt_job": "J1", "dt_x": 3, "dt_y": 4, "netdie": 9}])
    hw.settle(world)
    assert sorted(_official(world)) == [("J1", 1, 2), ("J1", 3, 4)], "canary: two keys"
    with channel(event_constants.CHANNEL_RETROACTIVE), retroactive_run("fold-run"):
        out = replay.fold_duplicate_rows(world["db"], hw.LOG, ["dt_job"], "log_id", apply=True, mark_column=MARK)
    hw.settle(world)
    assert out["rows_marked"] == 1
    assert {key: rest[1:] for key, rest in _official(world).items()} == {("J1", 1, 2): (7.0, "agreed")}


def test_5_and_6_the_sweep_takes_the_shells_already_there_and_nothing_a_person_or_a_file_keyed(world):
    def shell(job, x, y, keys_by=crud.CHAIN_SOURCE):
        key = {"dt_job": job, "dt_x": x, "dt_y": y}
        _write_official(world, keys_by, key, on=event_constants.CHANNEL_RETROACTIVE)
        _write_official(world, crud.CHAIN_SOURCE, {**key, "hold": ""}, on=event_constants.CHANNEL_RETROACTIVE)
    shell("J1", 1, 1)
    shell("J1", 1, 2)
    shell("J1", 2, 1, keys_by="user")                              # ⑥ a person keyed it
    shell("J1", 2, 2, keys_by="official_rows.csv")                 # a file keyed it
    shell("J1", 3, 1)
    _write_official(world, crud.CHAIN_SOURCE, {"dt_job": "J1", "dt_x": 3, "dt_y": 1, "netdie": 5},
                    on=event_constants.CHANNEL_RETROACTIVE)        # a value
    shell("J1", 3, 2)
    emptied = _official(world)[("J1", 3, 2)][0]
    _edit_note(world, emptied, "seen")
    _edit_note(world, emptied, "")                                 # ② a person emptied it
    assert _person_layers(world, emptied) == [("note", "")], "canary: the keys are the chain's alone"
    db = world["db"]
    said = retroactive.count(db, "remove_shell_rows", {"table": hw.OFFICIAL})
    preview = replay.remove_shell_rows(db, hw.OFFICIAL)
    done = replay.remove_shell_rows(db, hw.OFFICIAL, apply=True)
    again = replay.remove_shell_rows(db, hw.OFFICIAL)
    assert (said["affected"], preview["rows_to_delete"], done["rows_deleted"], again["rows_to_delete"]) == (2, 2, 2, 0)
    assert sorted((one["dt_job"], int(one["dt_x"]), int(one["dt_y"])) for one in preview["sample"]) == [
        ("J1", 1, 1), ("J1", 1, 2)]
    assert sorted(_official(world)) == [("J1", 2, 1), ("J1", 2, 2), ("J1", 3, 1), ("J1", 3, 2)]
