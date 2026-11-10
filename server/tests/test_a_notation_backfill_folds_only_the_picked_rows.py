# -*- coding: utf-8 -*-
"""The notation backfill folds only the rows a screen picked - `row_ids`, the cell chain_replay takes (lead 11-10,
owner «노테이션 소급 ㄱ»). Without it the whole table, as before; an id the table does not hold is named, not
counted as «0 rows»; an empty pick is refused, not read as «everything»."""
import pytest

from admin import retroactive
from chain import replay
from test_a_written_column_is_stored_folded import DECLARED, PLAIN, _declare, _rows, _write, env  # noqa: F401


def _stored(db, tmp_path, monkeypatch):
    _declare(tmp_path, monkeypatch, {})
    _write(db, PLAIN, [{"k": "K-01", "v": "wafer.1"}, {"k": "K-02", "v": "wafer.2"}])
    _declare(tmp_path, monkeypatch, DECLARED)
    return {row.k: row.row_id for row in _rows(db, PLAIN)}


def _shown(db):
    db.expire_all()
    return sorted((row.k, row.v) for row in _rows(db, PLAIN))


def test_only_the_picked_row_is_folded_and_an_id_the_table_does_not_hold_is_named(env, tmp_path, monkeypatch):
    ids = _stored(env, tmp_path, monkeypatch)
    count = retroactive.count(env, "fold_written_notation", {"table": PLAIN, "row_ids": [ids["K-01"], "no-such-row"]})
    assert (count["affected"], count["scanned"]) == (1, 1)
    assert "'%s' holds no row no-such-row. " % PLAIN in count["detail"], count["detail"]
    stats = replay.fold_written_notation(env, PLAIN, apply=True, row_ids=[ids["K-01"], "no-such-row"])
    assert stats["row_ids_not_found"] == ["no-such-row"]
    assert _shown(env) == [("K-01", "wafer-01"), ("K-02", "wafer.2")]
    replay.fold_written_notation(env, PLAIN, apply=True)                # no pick: the whole table, as before
    assert _shown(env) == [("K-01", "wafer-01"), ("K-02", "wafer-02")]


def test_a_pick_of_rows_the_table_does_not_hold_is_not_none(env, tmp_path, monkeypatch):
    _stored(env, tmp_path, monkeypatch)
    count = retroactive.count(env, "fold_written_notation", {"table": PLAIN, "row_ids": ["gone-1", "gone-2"]})
    assert (count["affected"], count["absence"]) == (0, retroactive.ABSENCE_CANNOT_POINT)
    assert "holds no row gone-1, gone-2" in count["detail"]


def test_an_empty_pick_is_refused_not_read_as_the_whole_table(env, tmp_path, monkeypatch):
    _stored(env, tmp_path, monkeypatch)
    with pytest.raises(replay.ReplayRefused, match="row_ids was given but empty; an empty selection would fold the "
                                                   "whole table instead of nothing"):
        replay.fold_written_notation(env, PLAIN, apply=True, row_ids=[" "])
    assert _shown(env) == [("K-01", "wafer.1"), ("K-02", "wafer.2")]
