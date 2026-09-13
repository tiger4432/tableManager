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


# ---------------------------------------------------------------------------
# 🔴 gate ⓒ (S-229-b) — the MODEL's identity, because the page is taken through it
#
# MEASURED ON THE OWNER'S BOX, after S-229 landed and before this: `bonding_core_lot` has
# 3,658 rows and 3,658 distinct `(base_id, core_wafer)` pairs - but only 160 distinct
# `base_id`. The model was mapped on `base_id` alone (the "nominated so the class can be
# built" column), so SQLAlchemy's identity map folded every row sharing one onto ONE object:
# a page of 1,000 came back as 41 rows, a 200 answering a twenty-fourth of what was asked
# for, with no error anywhere.
#
# ⚠️ WHY GATE ⓑ MISSED IT. Its fixture has one row per pair, so a fold is invisible - the
# collapsed set and the real set are the same set. The population below repeats the FIRST
# column on purpose, which is the only shape in which this defect exists.
# ---------------------------------------------------------------------------

MODEL_VIEW = "s229b_pair_model"

#: 🔴 ONE `base_id`, FOUR ROWS. Mapped on the first column alone this is one object.
FOLDING_ROWS = [
    {"base_id": "B1", "core_wafer": "W%d" % index, "note": "n%d" % index}
    for index in range(1, 5)
]


@pytest.fixture
def declared_model():
    from conftest import retire_dynamic_model
    from database import models

    catalogue = dict(crud.TABLE_CONFIG)
    entry = {"kind": "view", "composite_key_source": ["base_id", "core_wafer"],
             "column_types": {"base_id": "string", "core_wafer": "string", "note": "string"}}
    catalogue[MODEL_VIEW] = entry
    crud.TABLE_CONFIG[MODEL_VIEW] = entry
    models.init_dynamic_models(catalogue)
    try:
        yield models.DYNAMIC_TABLES[MODEL_VIEW]
    finally:
        crud.TABLE_CONFIG.pop(MODEL_VIEW, None)
        retire_dynamic_model(MODEL_VIEW)


def test_the_model_is_keyed_by_the_composite_the_catalogue_declares(declared_model):
    """🔴 THE MODEL AND THE SORT MUST AGREE ABOUT IDENTITY. `main.total_order_keys` answers
    row_id -> business_key -> composite; a model that nominates one column while the sort
    orders by two is the disagreement 판정 296 already paid for once."""
    assert [column.name for column in declared_model.__table__.primary_key] == [
        "base_id", "core_wafer"]


def test_a_page_of_n_is_n_rows_when_the_first_column_repeats(declared_model):
    """🔴 THE DEFECT ITSELF, RUN. Four rows share one `base_id`; asking for four must hand
    back four, not the one the identity map would have folded them into."""
    from sqlalchemy import create_engine, tuple_
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite://")
    declared_model.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(declared_model.__table__.insert(), FOLDING_ROWS)

    session = Session(engine)
    try:
        keys = main.total_order_keys(declared_model, MODEL_VIEW)
        order = main._order_by_clause(None, keys, False)
        picked = (session.query(declared_model).with_entities(*keys)
                  .order_by(*order).offset(0).limit(len(FOLDING_ROWS)).all())
        id_list = [tuple(row) for row in picked]
        rows = session.query(declared_model).filter(tuple_(*keys).in_(id_list)).all()

        assert len(id_list) == len(FOLDING_ROWS), "the key phase already lost rows"
        assert len(rows) == len(FOLDING_ROWS), "the identity map folded the page"
    finally:
        session.close()


BAD_COMPOSITE_VIEW = "s229b_bad_composite"


def test_a_composite_naming_a_column_the_view_lacks_does_not_become_the_mapped_key():
    """🔴 A PARTIAL KEY IS WORSE THAN THE NOMINATION. Using such a composite would map the
    class on whichever parts happen to exist - or on NOTHING, which SQLAlchemy cannot map at
    all - so the relation would stop being buildable rather than stop being pageable.

    ⚠️ The read path refuses it under R7 either way (gate ⓐ); what this pins is that the
    MODEL still comes up, because a catalogue typo must not take the whole registry down."""
    from conftest import retire_dynamic_model
    from database import models

    # ⚠️ THE MISSING NAME IS THE FIRST ONE, ON PURPOSE. With it last, a composite used
    # blindly still yields the same primary key as the nomination and the case decides
    # nothing - measured: that spelling let the mutation through.
    entry = {"kind": "view", "composite_key_source": ["not_a_column", "core_wafer"],
             "column_types": {"base_id": "string", "core_wafer": "string",
                              "note": "string"}}
    catalogue = dict(crud.TABLE_CONFIG)
    catalogue[BAD_COMPOSITE_VIEW] = entry
    crud.TABLE_CONFIG[BAD_COMPOSITE_VIEW] = entry
    try:
        models.init_dynamic_models(catalogue)
        model = models.DYNAMIC_TABLES[BAD_COMPOSITE_VIEW]

        assert [column.name for column in model.__table__.primary_key] == ["base_id"]
    finally:
        crud.TABLE_CONFIG.pop(BAD_COMPOSITE_VIEW, None)
        retire_dynamic_model(BAD_COMPOSITE_VIEW)
