# -*- coding: utf-8 -*-
"""S-229. 쌍으로 신원이 정해지는 뷰가 «읽히지 않았습니다» — 전순서를 한 컬럼으로만 물어서.

🔴 MEASURED IN THE SHIPPED CATALOGUE, not on this box: of the eleven `kind: view` relations
in `table_config.json.sample`, FOUR declare neither `row_id` nor `business_key` and DO
declare `composite_key_source` — `bonding_core_lot` (base_id, core_wafer),
`bonding_core_die`, `lot_slot_move`, `bonding_die_from_core`. Every one of them was refused
under R7, so the operator opened a relation the catalogue fully describes and saw nothing.

🔴 THE COMPOSITE IS NOT A NEW CELL. `composite_key_source` is what composes
`business_key_val` for an ordinary table - the declaration already says 「these columns are
this row's identity」, and an identity is what a total order needs. A cell for the order
would be a second expression of the same fact, free to disagree with it.

⚠️ R7 IS UNCHANGED. A relation declaring none of the three is still refused by name rather
than paged arbitrarily: a `LIMIT` without a total order hands out a different page on every
refresh and raises nothing.
"""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                            # noqa: E402
from database import crud                                             # noqa: E402

PAIR_VIEW = "s229_pair_view"
LONE_VIEW = "s229_lone_view"
KEYLESS = "s229_keyless_view"


class _Model:
    """A relation with only the columns it declares - which is the point."""

    def __init__(self, **columns):
        for name, value in columns.items():
            setattr(self, name, value)


@pytest.fixture(autouse=True)
def _declared():
    crud.TABLE_CONFIG[PAIR_VIEW] = {
        "kind": "view", "composite_key_source": ["base_id", "core_wafer"],
        "column_types": {"base_id": "string", "core_wafer": "string", "note": "string"}}
    crud.TABLE_CONFIG[LONE_VIEW] = {
        "kind": "view", "business_key": "id", "composite_key_source": ["a", "b"],
        "column_types": {"id": "string", "a": "string", "b": "string"}}
    crud.TABLE_CONFIG[KEYLESS] = {
        "kind": "view", "column_types": {"note": "string"}}
    yield
    for name in (PAIR_VIEW, LONE_VIEW, KEYLESS):
        crud.TABLE_CONFIG.pop(name, None)


# ---------------------------------------------------------------------------
# 🔴 gate ⓐ — the key
# ---------------------------------------------------------------------------

def test_a_pair_keyed_view_orders_by_both_columns():
    """🔴 BOTH, IN THE DECLARED ORDER. One of them is not an identity, so paging on it hands
    out a different page whenever two rows share it."""
    model = _Model(base_id="BASE_COL", core_wafer="WAFER_COL", note="NOTE_COL")

    assert main.total_order_keys(model, PAIR_VIEW) == ("BASE_COL", "WAFER_COL")


def test_row_id_and_business_key_still_win_ahead_of_the_composite():
    """⚠️ THE ORDER OF THE THREE IS THE REGRESSION LINE. S-131 measured what moving the
    grid's total order costs, so `row_id` keeps it wherever it exists - and a view that
    declares BOTH a business key and a composite is answered by the business key."""
    with_row_id = _Model(row_id="ROWID_COL", a="A", b="B", id="ID")
    assert main.total_order_keys(with_row_id, LONE_VIEW) == ("ROWID_COL",)

    without = _Model(id="ID_COL", a="A_COL", b="B_COL")
    assert main.total_order_keys(without, LONE_VIEW) == ("ID_COL",)


def test_a_composite_naming_a_column_the_relation_lacks_is_refused():
    """🔴 A COMPOSITE MISSING A PART IS NOT A NARROWER KEY - it is a key that does not
    identify the row. Ordering by the rest is exactly the silent version of R7."""
    model = _Model(base_id="BASE_COL")           # `core_wafer` is not there

    with pytest.raises(HTTPException) as caught:
        main.total_order_keys(model, PAIR_VIEW)

    assert caught.value.status_code == 422
    assert "R7" in str(caught.value.detail)


def test_a_relation_declaring_none_of_the_three_is_still_refused():
    """⚠️ THE CONTROL. R7 did not get weaker; it got one more declaration it accepts."""
    with pytest.raises(HTTPException) as caught:
        main.total_order_keys(_Model(note="NOTE_COL"), KEYLESS)

    assert caught.value.status_code == 422
    assert "composite_key_source" in str(caught.value.detail), "the refusal names the way out"


# ---------------------------------------------------------------------------
# 🔴 gate ⓑ — the page, run against a real relation
# ---------------------------------------------------------------------------

ROWS = [
    {"base_id": "B2", "core_wafer": "W1", "note": "c"},
    {"base_id": "B1", "core_wafer": "W2", "note": "b"},
    {"base_id": "B1", "core_wafer": "W1", "note": "a"},
    {"base_id": "B2", "core_wafer": "W2", "note": "d"},
]


@pytest.fixture
def paged(monkeypatch):
    """A real table standing in for the view: the read path never asks whether the relation
    is physically a view, and a declared `kind: view` is what makes it read-only."""
    from sqlalchemy import Column, MetaData, String, Table, create_engine
    from sqlalchemy.orm import Session, registry

    # 🔴 NO PRIMARY KEY ON THE TABLE, ON PURPOSE. A view has none, and a composite PK would
    # make SQLite store the rows IN KEY ORDER - which silently repairs an ORDER BY that
    # names only the first part. Measured: with the PK, dropping the second key column from
    # the sort left every case green. The mapper still needs a key, so it is told one.
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = Table(PAIR_VIEW, metadata,
                  Column("base_id", String),
                  Column("core_wafer", String),
                  Column("note", String))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(table.insert(), ROWS)

    class Row:
        pass

    registry().map_imperatively(Row, table,
                               primary_key=[table.c.base_id, table.c.core_wafer])
    session = Session(engine)
    yield session, Row
    session.close()


def _page(session, model, skip, limit):
    keys = main.total_order_keys(model, PAIR_VIEW)
    order = main._order_by_clause(None, keys, False)
    picked = session.query(model).with_entities(*keys).order_by(*order).offset(skip).limit(limit).all()
    return [tuple(row) for row in picked]


def test_the_page_is_the_same_rows_every_time(paged):
    """🔴 WHAT R7 IS FOR. The same `skip` twice must be the same rows - that is the whole
    difference between a total order and a partial one."""
    session, model = paged

    assert _page(session, model, 0, 2) == _page(session, model, 0, 2)


def test_the_pages_partition_the_relation(paged):
    """🔴 AND NO ROW IS SEEN TWICE OR MISSED. Ordering by `base_id` alone would leave the two
    rows that share it free to swap between pages."""
    session, model = paged

    first, second = _page(session, model, 0, 2), _page(session, model, 2, 2)

    assert first == [("B1", "W1"), ("B1", "W2")]
    assert second == [("B2", "W1"), ("B2", "W2")]
    assert len(set(first + second)) == len(ROWS)


def test_the_rows_come_back_matched_on_the_whole_key(paged):
    """⚠️ THE RE-FETCH IS THE OTHER HALF OF THE TWO-PHASE PAGE. Matching on the first part
    alone would pull in every row that shares it - here, twice the page."""
    from sqlalchemy import tuple_

    session, model = paged
    keys = main.total_order_keys(model, PAIR_VIEW)
    wanted = _page(session, model, 0, 2)

    rows = session.query(model).filter(tuple_(*keys).in_(wanted)).all()

    assert {(row.base_id, row.core_wafer) for row in rows} == set(wanted)
