# -*- coding: utf-8 -*-
"""S-243, 판정 405. 「부재는 층을 만들지 않는다 — 고의로 비운 것만 NULL 층이다」.

> 소유자 2026-09-15: 「빈 층 고의 입력은 **진짜 빈 것**, 그냥 없던 것은 **아직 입력하지
> 않은 것**」

🔴 THE TWO ARE DIFFERENT FACTS AND THE WRITE PATH TOLD THEM APART NOWHERE. A file's empty
cell was cast to NULL and STORED as that source's layer, exactly like a person clearing the
cell by hand. And because `pipeline_parser` OUTRANKS the chain (2 against 4), that NULL then
hid a value the join had correctly written - for good, on every subsequent read, with the
join still running and still right.

⛔ THE VIRTUAL JOIN'S `COALESCE` FILLS; THIS PATH DOES NOT. That difference is the whole of
S-243: the two ways a value reaches a cell disagreed about what an empty cell means, and
only one of them had said so out loud.

⚠️ WHAT RULING 405 COSTS, STATED SO NOBODY IS SURPRISED: a file that gave a value yesterday
and a blank today leaves YESTERDAY'S VALUE STANDING. That is what 「아직 입력하지 않은 것」
means. Erasing is the business of a person, of `withdraw_source` (R2), or of `replace_map`.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from database import crud, models, schemas                          # noqa: E402

TABLE = "inventory_master"
COLUMN = "category"
KEY = "PART-243"

#: 🔴 THE FILE SOURCE HAS TO OUTRANK THE CHAIN OR THE FIXTURE CANNOT HOLD THE DEFECT.
#: Measured at `parsers/directory_watcher.py:2977`: the pipeline path writes under this
#: exact name (rank 2), and the watcher path writes under a filename-derived name (rank
#: 99). Only the first can hide a chain layer, so only the first shows what was broken.
FILE_SOURCE = "pipeline_parser"


def _write(db, value, source, drop_report=None, column=COLUMN):
    batch = schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(
            business_key_val=KEY, updates={column: value},
            source_name=source, updated_by="tester")],
        transaction_id="tx-243", silent=True)
    kwargs = {"drop_report": drop_report} if drop_report is not None else {}
    crud.apply_batch_updates(db, TABLE, batch, **kwargs)
    db.commit()


def _shown(db, column=COLUMN):
    """The value a reader sees - the row's own column, which layering resolves into."""
    model = models.DYNAMIC_TABLES[TABLE]
    row = db.query(model).filter(model.business_key_val == KEY).one_or_none()
    return None if row is None else getattr(row, column)


def _layers(db, column=COLUMN):
    return {s.source_name: s.value for s in db.query(models.CellSource).filter(
        models.CellSource.table_name == TABLE,
        models.CellSource.column_name == column).all()}


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the ruling, both halves
# ---------------------------------------------------------------------------

def test_a_files_blank_cell_does_not_hide_what_the_chain_wrote(db_session):
    """🔴 GATE ① OF THIS ROUND, AND THE OWNER'S CASE. The join wrote 'W'; the file then
    delivered an empty cell for the same column. Before this ruling the file's NULL layer
    outranked the chain's and the cell read empty forever - the chain still running, still
    correct, and invisible."""
    _write(db_session, "W", crud.CHAIN_SOURCE)
    _write(db_session, "", FILE_SOURCE)

    assert _shown(db_session) == "W"
    assert crud.CHAIN_SOURCE in _layers(db_session)
    assert FILE_SOURCE not in _layers(db_session), "absence made a layer"


def test_a_person_clearing_the_cell_still_wins(db_session):
    """🔴 THE OTHER HALF, AND WITHOUT IT THIS ROUND WOULD BE 「blanks are ignored」. A human
    emptying a cell MEANS it - rank 0 - and ruling 405 is about telling that apart from a
    file that simply had nothing to say."""
    _write(db_session, "W", crud.CHAIN_SOURCE)
    _write(db_session, "", crud.USER_SOURCE)

    assert _shown(db_session) is None
    assert crud.USER_SOURCE in _layers(db_session)


def test_the_chains_own_blank_is_an_assertion_and_still_makes_a_layer(db_session):
    """⚠️ 판정 f3c04dee. A matched right row that IS empty is an ANSWER - the join looked
    and there is nothing there - which is not the same as a file that never spoke."""
    _write(db_session, "A", FILE_SOURCE)
    _write(db_session, "", crud.CHAIN_SOURCE)

    assert crud.CHAIN_SOURCE in _layers(db_session)
    assert _layers(db_session)[crud.CHAIN_SOURCE] in (None, "")


def test_yesterdays_value_stays_when_todays_file_says_nothing(db_session):
    """🔴 GATE ③, AND THIS IS THE PRICE OF THE RULING. 「Not entered」 is not 「withdraw
    what you said before」, so the earlier value stands. An operator who wants it gone has
    three ways, and none of them is an empty cell in a file."""
    _write(db_session, "A", FILE_SOURCE)
    report = {}
    _write(db_session, "", FILE_SOURCE, drop_report=report)

    assert _shown(db_session) == "A"
    assert _layers(db_session)[FILE_SOURCE] == "A", "the existing layer was touched"
    assert report["by_reason"].get(crud.DROP_ABSENT_NOT_WRITTEN) == 1


# ---------------------------------------------------------------------------
# ⚠️ ⓑ — what a blank is, and what it is not
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blank", ["", "   ", None])
def test_every_spelling_of_empty_is_the_same_absence(db_session, blank):
    """⚠️ ONE PREDICATE, `is_blank_value` - the same one the key seats fold with (S-181).
    A second spelling here would make 「빈칸」 mean one thing in the key gate and another
    in the layer."""
    _write(db_session, "A", crud.CHAIN_SOURCE)
    _write(db_session, blank, FILE_SOURCE)

    assert FILE_SOURCE not in _layers(db_session)
    assert _shown(db_session) == "A"


def test_a_numeric_zero_is_a_value_and_makes_its_layer(db_session):
    """⛔ THE DEFECT THIS ROUND MUST NOT CREATE, AND MY FIRST FIXTURE COULD NOT SEE IT.
    `0` and `False` are ANSWERS; a predicate spelled `not value` would call them blank and
    silently drop real data - the exact trap `is_blank_value`'s own docstring exists to
    stop. Scored on a NUMBER column, because the string "0" is truthy and a mutation
    swapping the predicate passes straight through it."""
    _write(db_session, 5, crud.CHAIN_SOURCE, column="stock_qty")
    _write(db_session, 0, FILE_SOURCE, column="stock_qty")

    assert FILE_SOURCE in _layers(db_session, "stock_qty")
    assert _shown(db_session, "stock_qty") == 0


def test_the_writer_is_chosen_positively_never_by_blacklist():
    """🔴 BECAUSE THE SET OF AUTOMATIC SOURCE NAMES IS OPEN-ENDED. File parsers write under
    the INGESTED FILENAME - 10,750 distinct values on the live DB per `USER_SOURCE`'s own
    note - so 「is this a file」 cannot be asked, and 「is this one of the two writers that
    can MEAN empty」 can."""
    assert crud.can_mean_emptied(crud.USER_SOURCE)
    assert crud.can_mean_emptied(crud.CHAIN_SOURCE)
    assert not crud.can_mean_emptied("some_file_2026_09_15.csv")
    assert not crud.can_mean_emptied("pipeline_parser")
    assert not crud.can_mean_emptied("collision_merge")
    assert crud.get_source_priority(crud.USER_SOURCE) == 0
    assert crud.get_source_priority("some_file_2026_09_15.csv") == 99


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the seat, and what this round did NOT move
# ---------------------------------------------------------------------------

def test_the_reading_side_is_untouched(db_session):
    """⚠️ 「해석은 그대로 두고 쓰기 경계 하나만 바뀐다」. `compute_priority_value` still
    answers with the top layer even when that layer is NULL - a deliberate blank has to be
    able to win, and moving the ruling into the READER would have broken that."""
    assert crud.compute_priority_value({crud.USER_SOURCE: None, FILE_SOURCE: "A"},
                                       table_name=TABLE)[0] is None
    assert crud.compute_priority_value({FILE_SOURCE: "A"}, table_name=TABLE)[0] == "A"


def test_the_count_says_absent_rather_than_dropped_for_a_reason(db_session):
    """⚠️ IT IS NOT AN ERROR AND MUST NOT READ AS ONE. A file whose column went blank and
    a file that never named the column at all were indistinguishable; this names the first
    without calling it a failure, which is why it is a COUNT and not a warning."""
    report = {}
    _write(db_session, "", FILE_SOURCE, drop_report=report)

    assert report["by_reason"] == {crud.DROP_ABSENT_NOT_WRITTEN: 1}
    assert report["by_column"] == {COLUMN: 1}
