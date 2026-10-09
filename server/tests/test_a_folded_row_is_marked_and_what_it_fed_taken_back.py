# -*- coding: utf-8 -*-
"""총괄 016a766af · 83c05cfbb (소유자 10-09 「접는 거 아예 삭제하지 말고 공식 홀드에만 반영 못 해?」 -> ㄱ): the fold
marks instead of deleting, and a copy rule with `on.exclude` stops taking a marked row - what it fed
is taken back, the hold counts without it. On PostgreSQL, through the product's seats: the fold run
on the retroactive channel, the replay door, the chain's group body, the ledger follow-up.

  the mark                       the row that loses is marked «folded into <the row kept>» · nothing deleted
  the first group after a start  the rule's columns are known from its mapper's facts - its layers go
  the official row               the kept row's value · the hold agreed · the ledger says it
  the mark emptied               the row is back - two values, the hold blank again
  the fold again                 nothing to mark
  a rule without exclude         takes the marked row - nothing taken back
  a row that lost require        its layers go in a fresh process too (the census's 4 -> 4, now 0)
  the pair                       both halves carry `source_exclude`; copies that disagree refuse the recount
"""
import json
import logging
import os
import sys

import pytest
from sqlalchemy import text

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                # noqa: E402
import event_constants                                               # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402
from chain import cell_layer, replay, rule_run                       # noqa: E402
from database import crud, models, schemas                           # noqa: E402
from database.context import channel, retroactive_run                # noqa: E402
from support import hold_world as hw                                 # noqa: E402

pytestmark = pytest.mark.pg
MARK = "fold_mark"


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=True, exclude=[MARK])


@pytest.fixture(name="plain_world")
def fixture_plain_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path, batch=True)


def _two_claims(world):
    hw.push(world, [{"log_id": "A", **hw.KEY, "netdie": 7}])
    hw.settle(world)
    hw.push(world, [{"log_id": "B", **hw.KEY, "netdie": 9}])
    hw.settle(world)
    assert (float(hw.official(world).netdie), hw.hold(world) or "") == (9.0, ""), "canary: two claims, held"


def _fold(world, **cells):
    """The fold as a run makes it - on the retroactive channel, under its run."""
    with channel(event_constants.CHANNEL_RETROACTIVE), retroactive_run("fold-run"):
        return replay.fold_duplicate_rows(world["db"], hw.LOG, hw.KEYS, "log_id", apply=True,
                                          mark_column=MARK, **cells)


def _log(world):
    with world["engine"].connect() as conn:
        return {r[0]: (r[1], r[2]) for r in conn.execute(text(
            'SELECT log_id, row_id, fold_mark FROM "%s"' % hw.LOG))}


def _layers_of(world, log_id):
    row_id = _log(world)[log_id][0]
    return world["db"].query(models.CellSource).filter_by(table_name=hw.OFFICIAL, origin_row_id=row_id).count()


def test_the_first_group_after_a_start_takes_back_what_the_marked_row_fed(world, monkeypatch, caplog):
    _two_claims(world)
    before = _layers_of(world, "B")
    monkeypatch.setattr(rule_run, "_COLUMNS_SEEN", {})              # a process that has run nothing yet
    monkeypatch.setattr(rule_run, "_ORIGIN_SEEN", {})
    last = world["db"].query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()[0]
    out = _fold(world)
    staged = [(e.table_name, (e.payload or {}).get("only_rule"), len((e.payload or {}).get("row_ids") or ()))
              for e in world["db"].query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > last)
              .order_by(models.DatabaseOutbox.id) if (e.payload or {}).get("only_rule")]
    with caplog.at_level(logging.WARNING):
        hw.settle(world)
    log = _log(world)
    assert (out["rows_to_mark"], out["rows_marked"], out["rules_woken"], out["rules_recounting"]) == (
        1, 1, [hw.RULE["name"]], [hw.RECOUNT["name"]])
    # 총괄 10-09: the copy rule first, then its recount on the official row the marked row fed - one run line
    assert staged == [(hw.LOG, hw.RULE["name"], 1), (hw.OFFICIAL, hw.RECOUNT["name"], 1)]
    taken_back = [e for e in world["db"].query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > last)
                  if e.table_name == hw.OFFICIAL and (e.payload or {}).get("updated_by") == cell_layer.R2_AUDIT_SOURCE]
    assert taken_back and not [(r["name"], e.id) for e in taken_back for r in world["rules"]
                               if worker._rule_accepts_event(r, e)], "the withdrawal woke a rule"
    assert (sorted(log), log["A"][1], log["B"][1]) == (["A", "B"], None, replay.FOLD_MARK % log["A"][0])
    assert not [r for r in caplog.records if "아직 모릅니다" in r.getMessage()]
    assert (before > 0, _layers_of(world, "B")) == (True, 0)
    assert (float(hw.official(world).netdie), hw.hold(world)) == (7.0, "agreed")
    assert [(job, float(value)) for job, value in hw.said(world)] == [("J1", 7.0)]
    assert _fold(world)["rows_to_mark"] == 0, "a marked row ranks no more"


def test_emptying_the_mark_brings_the_row_back(world):
    _two_claims(world)
    _fold(world)
    hw.settle(world)
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(world["db"], hw.LOG, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(row_id=_log(world)["B"][0], updates={MARK: ""},
                                      source_name="user", updated_by="hc")]))
        world["db"].commit()
    hw.settle(world)
    assert (_log(world)["B"][1], hw.hold(world) or "") == (None, "")
    assert _layers_of(world, "B") > 0


def test_a_rule_without_exclude_still_takes_the_marked_row(plain_world):
    world = plain_world
    _two_claims(world)
    before = _layers_of(world, "B")
    out = _fold(world)
    hw.settle(world)
    assert (out["rows_marked"], out["rules_woken"], out["rules_recounting"]) == (1, [], [])
    assert (_layers_of(world, "B"), hw.hold(world) or "") == (before, "")


def test_a_row_that_lost_require_is_taken_back_in_a_fresh_process(world, monkeypatch):
    _two_claims(world)
    monkeypatch.setattr(rule_run, "_COLUMNS_SEEN", {})
    monkeypatch.setattr(rule_run, "_ORIGIN_SEEN", {})
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(world["db"], hw.LOG, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(row_id=_log(world)["B"][0], updates={"dt_job": ""},
                                      source_name="user", updated_by="hc")]))
        world["db"].commit()
    hw.settle(world)
    assert (_layers_of(world, "B"), float(hw.official(world).netdie), hw.hold(world)) == (0, 7.0, "agreed")


def test_both_halves_carry_the_copy_rules_exclude(world):
    by_name = {rule["name"]: rule for rule in world["rules"]}
    assert [by_name[name].get(chain_bindings.SOURCE_EXCLUDE_KEY) for name in (hw.RULE["name"], hw.RECOUNT["name"])] \
        == [[MARK], [MARK]]


def test_copies_that_exclude_by_different_columns_refuse_their_recount(world, tmp_path, monkeypatch, caplog):
    second = {**hw.RULE, "name": "hc_copy_2", "exclude": ["kind"], "is_batch": True}
    path = tmp_path / "chain_rules_pair.json"
    path.write_text(json.dumps({"rules": [{**hw.RULE, "is_batch": True, "exclude": [MARK]}, second,
                                          {**hw.RECOUNT, "is_batch": True}]}), encoding="utf-8")
    monkeypatch.setattr(worker, "RULES_PATH", str(path))
    with caplog.at_level(logging.ERROR):
        names = [rule.get("name") for rule in worker.load_chain_rules()]
    assert hw.RECOUNT["name"] not in names and {hw.RULE["name"], "hc_copy_2"} <= set(names)
    assert any("pair_mismatch" in r.getMessage() and hw.RECOUNT["name"] in r.getMessage() for r in caplog.records)
