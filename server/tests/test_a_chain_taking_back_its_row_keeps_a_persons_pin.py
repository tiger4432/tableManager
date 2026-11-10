# -*- coding: utf-8 -*-
"""A chain taking back a row it made takes only its own part (owner 11-10 «체인이 낸 행 부분만 없애면 됨»): a person's
part - a layer they wrote, or a pin they set on a cell - keeps the row. One function says it (`cell_layer.person_rows`)
and both seats that delete a chain row ask it: `cell_layer.shells` (after a withdrawal) and `ingestion_worker._settle`
(a key no source row holds any more). Before, `_settle` read layers only and deleted a row a person had pinned."""
import pytest

from chain import cell_layer
from chain import ingestion_worker as worker
from database import crud, models
from test_a_written_column_is_stored_folded import PLAIN, _rows, env  # noqa: F401


def _chain_row(db, updates):
    ok, reason = worker.apply_chain_writes(
        db, "tx-chain", {"name": "r_made", "target_table": PLAIN}, 0, {PLAIN: {"r_made"}},
        {PLAIN: [{"business_key_val": "K-01", "updates": dict(updates, k="K-01"), "source_name": "chain_ingestion",
                  "updated_by": "r_made"}]},
        [], [], {PLAIN: ["r_made"]}, [])
    assert ok, reason
    db.commit()
    (row,) = _rows(db, PLAIN)
    return row.row_id


def _pin(db, row_id, column, source):
    db.add(models.CellOverwrite(table_name=PLAIN, row_id=row_id, column_name=column, is_overwrite=True,
                                updated_by="op", manual_priority_source=source))
    db.commit()


def _layer(db, row_id, column):
    return db.query(models.CellSource.source_name).filter(
        models.CellSource.table_name == PLAIN, models.CellSource.row_id == row_id,
        models.CellSource.column_name == column).scalar()


@pytest.mark.parametrize("pinned, left", [(False, 0), (True, 1)])
def test_a_key_no_source_row_holds_keeps_a_row_a_person_pinned(env, pinned, left):
    row_id = _chain_row(env, {"v": "V1"})
    if pinned:
        _pin(env, row_id, "v", _layer(env, row_id, "v"))
    cover = {"covers": {"where": [{"k": "K-01"}], "rules": ["r_made"]}, "updated_by": "r_made"}
    worker._settle(env, PLAIN, [], [], [cover])
    env.commit()
    assert len(_rows(env, PLAIN)) == left


@pytest.mark.parametrize("pinned, left", [(False, 0), (True, 1)])
def test_a_withdrawal_keeps_a_row_a_person_pinned(env, pinned, left):
    row_id = _chain_row(env, {"v": "V1"})
    if pinned:
        _pin(env, row_id, "v", _layer(env, row_id, "v"))
    stats = cell_layer.withdraw_source(env, PLAIN, _layer(env, row_id, "v"), apply=True)
    env.commit()
    assert (len(_rows(env, PLAIN)), stats["rows_deleted"]) == (left, 1 - left)


def test_a_pin_alone_is_a_persons_part_to_the_shell_question(env):
    """Only the chain's key, nothing shown: a shell - unless a person pinned a cell of it."""
    row_id = _chain_row(env, {})
    assert cell_layer.shells(env, PLAIN, [row_id]) == [row_id]
    _pin(env, row_id, "v", "f01.csv")
    assert (cell_layer.shells(env, PLAIN, [row_id]), cell_layer.person_rows(env, PLAIN, [row_id])) == ([], {row_id: [crud.USER_SOURCE]})
