# -*- coding: utf-8 -*-
"""S-243-b. 어제까지 쌓인 «파일의 NULL 층»을 «센다» — 지우기 전에.

🔴 판정 405 는 «앞으로의 쓰기»를 고쳤다. 이미 저장된 층은 그대로 남아 오늘도 가린다: 파일
소스가 체인을 앞서므로(2 또는 99 대 4) 조인이 올바르게 쓴 값이 안 보인다.

⛔ 지우는 것은 «데이터 변경»이고 이 도구는 그것을 하지 않는다. 소유자 승인을 받으려면 수가
먼저이고, 그것이 이 파일이 채점하는 전부다 — 「세기 먼저」는 이 저장소가 소급마다 쓰는 자세다
(`retroactive` 의 사전 세기 · `unique_key.duplicate_keys` · `fold_plan`).

⚠️ 두 수는 «다른 사실»이다. 아래에 다른 층이 없는 NULL 층은 지워도 화면이 안 바뀐다. 한 수로
합치면 운영자가 「수천 건」을 보고 «아무것도 안 바뀌는» 일에 착수한다.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

SCRIPTS = os.path.join(SERVER_DIR, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import count_absent_null_layers as counter                         # noqa: E402
from database import crud, models                                  # noqa: E402

TABLE = "inventory_master"
COLUMN = "category"
FILE_SOURCE = "some_file_2026_09_15.csv"


def _layer(db, row_id, source, value, column=COLUMN):
    db.add(models.CellSource(table_name=TABLE, row_id=row_id, column_name=column,
                             source_name=source, value=value, updated_by="test"))


@pytest.fixture(name="stored")
def fixture_stored(db_session):
    """🔴 THE FIXTURE THE ORDER SPECIFIED, and every row in it is there to be TOLD APART.

    Two file NULL layers - one with a value beneath it and one alone - and a person's NULL
    layer, which is an ANSWER and must not be counted as debris."""
    _layer(db_session, "r1", FILE_SOURCE, None)
    _layer(db_session, "r1", crud.CHAIN_SOURCE, "W")      # r1's NULL HIDES this
    _layer(db_session, "r2", FILE_SOURCE, None)           # r2's NULL hides nothing
    _layer(db_session, "r3", crud.USER_SOURCE, None)      # deliberate - never counted
    db_session.commit()
    return db_session


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the two numbers, told apart
# ---------------------------------------------------------------------------

def test_the_file_layers_are_counted_and_the_hiding_ones_counted_separately(stored):
    """🔴 THE GATE OF THIS ROUND. Two file NULL layers, of which ONE actually hides a
    value - and the count says both numbers rather than one."""
    assert counter.count(stored) == [(TABLE, COLUMN, FILE_SOURCE, 2, 1)]


def test_a_persons_cleared_cell_is_an_answer_and_is_never_counted(stored):
    """⛔ IT IS NOT DEBRIS. 판정 405 keeps that layer on purpose - counting it here would
    put a deliberate blank on a list headed 「지울 후보」."""
    assert all(entry[2] != crud.USER_SOURCE for entry in counter.count(stored))


def test_the_chains_asserted_blank_is_not_counted_either(db_session):
    """⚠️ 판정 f3c04dee. 「the matched right row IS empty」 is an answer the join gave, not
    a layer nobody meant to write."""
    _layer(db_session, "r9", crud.CHAIN_SOURCE, None)
    db_session.commit()

    assert counter.count(db_session) == []


def test_another_empty_layer_underneath_is_not_something_being_hidden(db_session):
    """🔴 「가린다」 MEANS A VALUE IS UNDERNEATH, AND A SECOND `null` IS NOT A VALUE.
    Two file sources that both delivered a blank for one cell hide nothing from each other -
    counting them as hiding would put a number on the operator's desk that says work exists
    where none does, which is the exact reason this report splits its two counts."""
    _layer(db_session, "z1", FILE_SOURCE, None)
    _layer(db_session, "z1", "other_file.csv", None)
    db_session.commit()

    found = counter.count(db_session)

    assert sorted((entry[2], entry[3], entry[4]) for entry in found) == [
        ("other_file.csv", 1, 0), (FILE_SOURCE, 1, 0)]


def test_the_predicate_is_imported_not_respelled():
    """🔴 ONE SPELLING OF 「WHO MAY EMPTY A CELL」. If the counting side answered that
    question for itself, the number it produced would be a number about something else -
    and nobody reading the report could tell.

    ⚠️ ASKED OF THE CODE OBJECT, NOT THE SOURCE TEXT. My first cut grepped the source and
    went red on its own explanatory COMMENT, which names both writers - a test that scores
    prose is a test whose easiest repair is deleting the explanation."""
    assert "can_mean_emptied" in counter.count.__code__.co_names
    literals = counter.count.__code__.co_consts
    assert crud.USER_SOURCE not in literals
    assert crud.CHAIN_SOURCE not in literals


# ---------------------------------------------------------------------------
# ⛔ ⓑ — it counts, and that is all it does
# ---------------------------------------------------------------------------

def test_nothing_is_written_and_there_is_no_way_to_ask_for_it(stored):
    """⛔ NO `--apply`, AND NOT BY POLICY - BY ABSENCE. A flag that exists can be typed,
    and 「the script refuses it」 is a promise; 「the script has no such flag」 is a fact."""
    before = stored.query(models.CellSource).count()

    counter.count(stored)

    assert stored.query(models.CellSource).count() == before
    with pytest.raises(SystemExit):
        counter.main(["--apply"])


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the sentence an operator acts on
# ---------------------------------------------------------------------------

def test_zero_hiding_layers_says_there_is_nothing_to_do():
    """⚠️ 「몇 건 있음」 WITHOUT 「그게 아무것도 안 가림」 SENDS SOMEBODY TO WORK FOR NOTHING."""
    said = counter.render([(TABLE, COLUMN, FILE_SOURCE, 5, 0)])

    assert "→ 다음: " in said
    assert "없음" in said.split("→ 다음: ")[1]


def test_a_hiding_count_names_the_number_and_the_next_step():
    said = counter.render([(TABLE, COLUMN, FILE_SOURCE, 5, 3)])

    action = said.split("→ 다음: ")[1]
    assert "3" in action and "S-243-c" in action
    assert "내보" in action, "erasing without an export first is not reversible"


def test_an_empty_installation_says_so_rather_than_printing_a_blank_table():
    """⚠️ AN EMPTY TABLE AND 「나는 아무것도 못 찾았다」 LOOK THE SAME ON A TERMINAL."""
    said = counter.render([])

    assert "없음" in said and "→ 다음: " in said


def test_the_biggest_hider_is_reported_first(db_session):
    """⚠️ THE OPERATOR READS THE TOP OF THE LIST, and the listing is capped - so the
    order has to be by the count that MATTERS, not by the bigger raw number. Scored on
    `count` itself rather than on a hand-sorted list, because the sort is what is claimed."""
    _layer(db_session, "x1", FILE_SOURCE, None, column="category")
    _layer(db_session, "x2", FILE_SOURCE, None, column="category")
    _layer(db_session, "y1", FILE_SOURCE, None, column="part_no")
    _layer(db_session, "y1", crud.CHAIN_SOURCE, "P", column="part_no")
    db_session.commit()

    found = counter.count(db_session)

    assert [entry[1] for entry in found] == ["part_no", "category"]
    assert (found[0][4], found[1][4]) == (1, 0)
