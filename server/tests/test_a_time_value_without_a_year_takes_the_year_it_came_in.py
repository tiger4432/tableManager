# -*- coding: utf-8 -*-
"""A `time` format that reads no year («%m월 %d일») takes the year the value came in - `"year": "arrival"`
(lead 11-10, owner «value 노테이션만 먹으면 쉽잖아»). The write folds with now's year, the backfill with each
layer's `ingested_at`; a value in no declared format stays as it is; a year-less format without `year` is refused
by name instead of folding to 1900."""
import os
from datetime import datetime

import pytest

import notation_norm as nn
from chain import ingestion_worker as worker
from chain import replay
from database import models
from test_a_written_column_is_stored_folded import (DECLARED, PLAIN, TABLES, _declare, _rows, _stored,  # noqa: F401
                                                    _write, env, fixture_watcher)
from test_a_written_column_takes_the_declared_spelling import _refusals

KOREAN = {"time": {"from": ["%m월 %d일", "%m월%d일"], "year": "arrival"}}
ARRIVAL = dict(DECLARED, **{PLAIN: dict(DECLARED[PLAIN], seen={"write": True, "rules": KOREAN})})


def _this_year(month_day):
    return "%d-%s 00:00:00" % (datetime.now().year, month_day)


@pytest.fixture(name="arrival")
def fixture_arrival(env, tmp_path, monkeypatch):
    _declare(tmp_path, monkeypatch, ARRIVAL)
    return env


# --- the write: now's year, at every door -----------------------------------------------------------

def test_the_funnel_folds_a_month_and_day_into_this_year_and_leaves_other_values(arrival):
    report = {}
    _write(arrival, PLAIN, [{"k": "K-01", "seen": "3월 5일"}, {"k": "K-02", "seen": "11월9일"},
                            {"k": "K-03", "seen": "21"}, {"k": "K-04", "seen": "2026-01-02 00:00:00"}], report=report)
    assert sorted((r.k, r.seen) for r in _rows(arrival, PLAIN)) == [
        ("K-01", _this_year("03-05")), ("K-02", _this_year("11-09")), ("K-03", "21"),
        ("K-04", "2026-01-02 00:00:00")]
    assert report == {"unmatched": 1}


def test_a_chain_write_folds_a_month_and_day_into_this_year(arrival):
    ok, reason = worker.apply_chain_writes(
        arrival, "tx-chain", {"name": "r_probe", "target_table": PLAIN}, 0, {PLAIN: {"r_probe"}},
        {PLAIN: [{"business_key_val": "K-01", "updates": {"k": "K-01", "seen": "3월 5일"},
                 "source_name": "chain_ingestion"}]},
        [], [], {PLAIN: ["r_probe"]}, [])
    assert ok, reason
    assert [r.seen for r in _rows(arrival, PLAIN)] == [_this_year("03-05")]


def test_a_watched_file_folds_a_month_and_day_into_this_year(watcher, tmp_path, monkeypatch):
    import directory_watcher

    handler, workspace, factory = watcher
    _declare(tmp_path, monkeypatch, ARRIVAL)
    path = os.path.join(workspace, "raws", "dates.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("k,v,seen\nK-01,a,3월 5일\nK-02,b,21\n")
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 10 ** 9)
    handler._handle_event(path)
    handler.heavy_lane.run_all()
    assert _stored(factory) == [("K-01", "a", _this_year("03-05")), ("K-02", "b", "21")]


# --- the backfill: each layer's year ---------------------------------------------------------------

def _stored_in(db, tmp_path, monkeypatch, rows_by_source, years):
    """Rows written before the declaration, each source's layers dated in its year."""
    _declare(tmp_path, monkeypatch, {})
    for source, rows in rows_by_source:
        _write(db, PLAIN, rows, source=source)
    for source, year in years.items():
        db.query(models.CellSource).filter(models.CellSource.table_name == PLAIN,
                                           models.CellSource.source_name == source).update(
            {"ingested_at": datetime(year, 6, 1, 12, 0, 0)}, synchronize_session=False)
    db.commit()
    _declare(tmp_path, monkeypatch, ARRIVAL)


def _layers(db):
    return sorted((s.source_name, s.value) for s in db.query(models.CellSource)
                  .filter(models.CellSource.table_name == PLAIN, models.CellSource.column_name == "seen"))


def test_the_backfill_folds_each_layer_with_the_year_it_came_in(env, tmp_path, monkeypatch):
    _stored_in(env, tmp_path, monkeypatch,
               [("f24.csv", [{"k": "K-01", "seen": "3월 5일"}, {"k": "K-03", "seen": "2월 29일"}]),
                ("f25.csv", [{"k": "K-02", "seen": "3월 5일"}, {"k": "K-04", "seen": "2월 29일"},
                             {"k": "K-05", "seen": "21"}])],
               {"f24.csv": 2024, "f25.csv": 2025})
    stats = replay.fold_written_notation(env, PLAIN, apply=True)
    # one spelling, two years: each layer by its own (a fold by spelling gives both one year)
    assert sorted((r.k, r.seen) for r in _rows(env, PLAIN)) == [
        ("K-01", "2024-03-05 00:00:00"), ("K-02", "2025-03-05 00:00:00"),
        ("K-03", "2024-02-29 00:00:00"), ("K-04", "2월 29일"), ("K-05", "21")]
    assert _layers(env) == [("f24.csv", "2024-02-29 00:00:00"), ("f24.csv", "2024-03-05 00:00:00"),
                            ("f25.csv", "2025-03-05 00:00:00"), ("f25.csv", "21"), ("f25.csv", "2월 29일")]
    # counted as the cell and as the layer: 21's two, and 2025's 2월 29일 layer - its cell had no year to say
    assert stats["time_left"] == {"unmatched": 3}
    assert replay.fold_written_notation(env, PLAIN)["layers_folded"] == 0, "a second run moves nothing"


def test_a_shown_value_with_no_layer_is_left_and_counted(env, tmp_path, monkeypatch):
    _stored_in(env, tmp_path, monkeypatch, [("f24.csv", [{"k": "K-01", "seen": "3월 5일"}])], {"f24.csv": 2024})
    env.query(models.CellSource).filter(models.CellSource.table_name == PLAIN,
                                        models.CellSource.column_name == "seen").delete(synchronize_session=False)
    env.commit()
    stats = replay.fold_written_notation(env, PLAIN, apply=True)
    assert ([r.seen for r in _rows(env, PLAIN)], stats["time_left"]) == (["3월 5일"], {"no_arrival": 1})


# --- the declaration -------------------------------------------------------------------------------

@pytest.mark.parametrize("time, says", [
    ({"from": ["%m월 %d일"]}, "input format '%m월 %d일' reads no year - add \"year\": \"arrival\""),
    ({"from": ["%m/%d %H:%M"]}, "input format '%m/%d %H:%M' reads no year"),
    ({"from": ["%m월 %d일"], "year": "now"}, "\"year\" must be \"arrival\""),
])
def test_a_format_without_a_year_is_refused_unless_the_year_is_its_arrival(time, says):
    specs, rejections = _refusals({"seen_at": {"write": True, "rules": {"time": time}}})
    # the time rule is off; the column stands with its defaults (as for every refused value rule)
    assert not (specs.get("seen_at") or {}).get("rules", {}).get("time")
    assert any(says in r["detail"] for r in rejections), rejections


@pytest.mark.parametrize("formats", [["%m월 %d일", "%m월%d일"], ["%Y/%m/%d", "%m월 %d일"], ["%Y/%m/%d"]])
def test_korean_and_mixed_formats_stand_with_the_year_of_arrival(formats):
    specs, rejections = _refusals({"seen_at": {"write": True, "rules": {"time": {"from": formats, "year": "arrival"}}}})
    assert (rejections, specs["seen_at"]["rules"]["time"]["from"]) == ([], formats)


def test_february_29_needs_a_leap_year_of_arrival():
    spec = KOREAN["time"]
    assert nn.fold_time("2월 29일", spec, datetime(2024, 3, 1)) == ("2024-02-29 00:00:00", "folded")
    assert nn.fold_time("2월 29일", spec, datetime(2025, 3, 1)) == ("2월 29일", "unmatched")
    assert nn.fold_time("2월 29일", spec, nn.ARRIVAL_UNKNOWN) == ("2월 29일", "no_arrival")
