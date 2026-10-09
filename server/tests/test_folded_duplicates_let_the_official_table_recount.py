# -*- coding: utf-8 -*-
"""총괄 d72dc0283: one chip's event went into the log twice with different values, so the official row
is held (two claims). Folding the log's duplicates per key - the earliest stays - goes through the
product's delete door, and the chain takes back what the deleted row fed: the recount rule finds one
claim and the hold reads agreed; the ledger says the kept value. Nothing else is done by hand.

PostgreSQL, on the hold-copy world (`support.hold_world`).
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import replay                                              # noqa: E402
from support import hold_world as hw                                  # noqa: E402

pytestmark = pytest.mark.pg


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    yield from hw.build(pg_engine, monkeypatch, tmp_path)


def test_folding_the_logs_duplicates_lets_the_hold_read_agreed(world):
    hw.push(world, [{"log_id": "A1", **hw.KEY, "netdie": 7},
                    {"log_id": "A2", **hw.KEY, "netdie": 8},
                    {"log_id": "B1", "dt_job": "J2", "dt_x": 3, "dt_y": 4, "netdie": 5}])
    hw.settle(world)
    held = {r.dt_job: (r.netdie, r.hold) for r in world["db"].query(
        hw.models.DYNAMIC_TABLES[hw.OFFICIAL]).all()}
    assert held["J1"][1] in (None, "") and held["J2"] == (5, "agreed"), held          # canary: J1 is held

    done = replay.fold_duplicate_rows(world["db"], hw.LOG, hw.KEYS, "log_id", keep="min", apply=True,
                                      log=lambda m: None)
    assert (done["keys_folded"], done["rows_deleted"]) == (1, 1)
    hw.settle(world)

    world["db"].expire_all()
    after = {r.dt_job: (r.netdie, r.hold) for r in world["db"].query(
        hw.models.DYNAMIC_TABLES[hw.OFFICIAL]).all()}
    assert after == {"J1": (7, "agreed"), "J2": (5, "agreed")}, after
    assert sorted(hw.said(world)) == [("J1", "7.0"), ("J2", "5.0")]                 # the ledger's spelling


def test_on_postgresql_the_preferred_text_matches_in_any_case_and_a_blank_key_row_stays(world):
    """총괄 1d2a7e0fd ④ · 9c8b9f919 where it runs: PostgreSQL's LIKE minds case, SQLite's does not."""
    hw.push(world, [{"log_id": "A1", **hw.KEY, "netdie": 7},
                    {"log_id": "X_AUTO_2", **hw.KEY, "netdie": 8},
                    {"log_id": "N1", "dt_job": "J3", "netdie": 1},
                    {"log_id": "N2", "dt_job": "J3", "netdie": 2}])
    done = replay.fold_duplicate_rows(world["db"], hw.LOG, hw.KEYS, "log_id", apply=True, log=lambda m: None,
                                      prefer_column="log_id", prefer_text="auto")
    assert (done["rows_deleted"], done["keys_preferred"], done["rows_blank_key"]) == (1, 1, 2)
    world["db"].expire_all()
    left = sorted(r.log_id for r in world["db"].query(hw.models.DYNAMIC_TABLES[hw.LOG]).all())
    assert left == ["N1", "N2", "X_AUTO_2"]


def _official(world):
    world["db"].expire_all()
    return {r.dt_job: (r.netdie, r.hold) for r in world["db"].query(hw.models.DYNAMIC_TABLES[hw.OFFICIAL]).all()}


def test_the_owners_three_steps_empty_the_official_fold_the_log_and_refill_by_the_copy_rule(world):
    """총괄 10-09 (소유자 「공식 표 다 지우고 다시 할게, 원자도 다 지워져야 해」): ① empty_table on the official
    table - its rows, layers and the atoms of the ledger source reading it; ② fold the log; ③ the copy
    rule's replay refills the official table and the ledger follows."""
    if os.path.join(SERVER_DIR, "scripts") not in sys.path:
        sys.path.append(os.path.join(SERVER_DIR, "scripts"))                     # after tests/: scripts has a support too
    import empty_table

    db = world["db"]
    hw.push(world, [{"log_id": "A1", **hw.KEY, "netdie": 7},
                    {"log_id": "A2", **hw.KEY, "netdie": 8},
                    {"log_id": "B1", "dt_job": "J2", "dt_x": 3, "dt_y": 4, "netdie": 5}])
    hw.settle(world)
    assert hw.said(world) == [("J2", "5.0")]                                      # canary: atoms to take

    found = empty_table.report(db, world["setup"], hw.OFFICIAL, world["rules"])     # ①
    empty_table.empty(db, world["engine"], world["setup"], hw.OFFICIAL, world["rules"],
                      confirm_rows=found["rows"], by="operator")
    assert _official(world) == {} and hw.said(world) == []                         # the source's atoms: 0

    folded = replay.fold_duplicate_rows(db, hw.LOG, hw.KEYS, "log_id", apply=True,   # ②
                                        log=lambda m: None)
    hw.settle(world)
    assert folded["rows_deleted"] == 1 and _official(world) == {} and hw.said(world) == []

    rule = next(r for r in world["rules"] if r["name"] == hw.RULE["name"])          # ③
    replay.replay_rule(db, rule, apply=True, log=lambda m: None)
    hw.settle(world)
    assert _official(world) == {"J1": (7, "agreed"), "J2": (5, "agreed")}
    assert sorted(hw.said(world)) == [("J1", "7.0"), ("J2", "5.0")]
