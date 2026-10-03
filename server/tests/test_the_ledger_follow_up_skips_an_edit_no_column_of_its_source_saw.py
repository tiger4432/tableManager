# -*- coding: utf-8 -*-
"""총괄 «소스가 안 읽는 칸» (소유자 10-03 「필요없는 더미 컬럼도 바꾸면 어찌되는지」): the ledger
follow-up does not re-translate an edit that says which columns it set when none of them is a
column the source reads. On PostgreSQL, in the hold world (`note` is read by nothing).

  an edit of `note` alone, said             the source is skipped, its atom stays
  `note` and `netdie` together              re-translated, the atom moves
  an edit that does not say its columns     re-translated (모른다)
  a CREATE, whatever it says                re-translated
  a mapper that reads the whole row         never skipped
"""
import contextlib
import os
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import event_constants                                              # noqa: E402
from database import crud, schemas                                  # noqa: E402
from database.context import channel, outbox_mode                   # noqa: E402
from database.database import stage_collapsed_event                 # noqa: E402
from ledger import backfill, followup                               # noqa: E402
from support import hold_world as hw                                 # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    for world in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
        hw.settle(world)
        assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]
        yield world


def _edit(world, updates, said_columns=True):
    """A person's edit of the official row - through the grid's door, which says its columns."""
    db = world["db"]
    row_id = hw.official(world).row_id
    mode = (outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED) if said_columns
            else contextlib.nullcontext())
    with channel(event_constants.CHANNEL_API), mode:
        crud.apply_batch_updates(db, hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name="user",
                                      updated_by="t")]))
        db.commit()


def _follow(world, monkeypatch):
    """The chain, then the follow-up: (sources re-translated, the follow records)."""
    asked, real = [], backfill.rescope
    monkeypatch.setattr(backfill, "rescope",
                        lambda engine, setup, source, *a, **k: asked.append(source)
                        or real(engine, setup, source, *a, **k))
    hw.run_chain(world)
    records = []
    while True:
        done = followup.drain_outbox_once(world["engine"], world["setup"])
        if done is None:
            return asked, [d for d in records if d.get("table") == hw.OFFICIAL]
        records.append(done)


def test_an_edit_of_a_column_no_source_reads_is_skipped_and_said(world, monkeypatch):
    _edit(world, {"note": "checked"})
    asked, records = _follow(world, monkeypatch)
    assert asked == []
    assert [(r["event_type"], r["sources"]) for r in records] == [
        ("EDIT", {hw.SOURCE: {"skipped": "columns"}})]
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]
    # 총괄 6e041f4cb ②: kept on the event's own ledger cell, and the CLI counts it per source
    with world["engine"].connect() as conn:
        state = conn.execute(text("SELECT ledger_state FROM database_outbox WHERE id = :i"),
                             {"i": records[0]["outbox_id"]}).scalar()
    assert state == followup.LEDGER_SKIPPED + hw.SOURCE
    assert followup.skipped_by_source(world["engine"]) == {hw.SOURCE: 1}


def test_a_read_column_among_them_is_re_translated(world, monkeypatch):
    _edit(world, {"note": "checked", "netdie": 8})
    asked, _ = _follow(world, monkeypatch)
    assert asked == [hw.SOURCE]
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 8.0)]


def test_an_edit_that_does_not_say_its_columns_is_re_translated(world, monkeypatch):
    _edit(world, {"note": "checked"}, said_columns=False)
    asked, _ = _follow(world, monkeypatch)
    assert asked == [hw.SOURCE]


def test_a_create_is_re_translated_whatever_it_says(world, monkeypatch):
    db = world["db"]
    stage_collapsed_event(db, "CREATE", hw.OFFICIAL, [hw.official(world).row_id], ["note"])
    db.commit()
    asked, _ = _follow(world, monkeypatch)
    assert asked == [hw.SOURCE]


def test_only_a_source_whose_declaration_is_all_it_reads_is_ever_skipped(world):
    plan = world["setup"].snapshot.source_plans[hw.SOURCE]
    assert followup.reads_none_of(plan, ["note"]) is True
    assert followup.reads_none_of(plan, ["note", "netdie"]) is False
    assert followup.reads_none_of(plan, None) is False
    python_mapper = SimpleNamespace(driver=SimpleNamespace(mapper=SimpleNamespace(
        implementation=SimpleNamespace(implementation_id="a_python_mapper"))))
    assert followup.reads_none_of(python_mapper, ["note"]) is False
