# -*- coding: utf-8 -*-
"""S-226 (판정 391). 평키 표의 «정체성»을 아무도 안 올려서, 두 번째 쓰기가 못 찾았다.

🔴 THE AXIS HAD ONE HALF. A row's identity is ONE axis, and `assemble_composite_business_key`
has resolved the COMPOSITE half of it since 판정 190. The PLAIN half - a table that declares
`business_key` and no `composite_key_source` - was resolved NOWHERE: nothing lifted
`updates[business_key]` into `business_key_val`, and `_get_or_create_row` reads only
`row_id`/`business_key_val`. So the row landed, the upsert could never find it again, and
EVERY run inserted another copy. Not only a retry - every run.

🔴 WHAT HELD IT UP WAS THE MAPPER AUTHOR, counted before this was built: of the 10 chain
rules in the shipped catalogue 3 target a plain-keyed table, and of the 7 shipped mapper
samples SIX write `business_key_val` by hand while ZERO go through `mapper_sdk.df_to_updates`.
「재시도가 안전한 이유는 business key 이지 맵퍼의 성질이 아니다」 - and on this shape it was
the mapper's property, which is the thing a declaration is supposed to take over.

⚠️ AND THE LIFT ONLY FILLS. A supplied `business_key_val` is what the prefetch filtered on
and what `_get_or_create_row` matched, so re-deriving over it stores the row under a handle
the batch never resolved on. The composite half overwrites by design (판정 190); the plain
half has no assembly to switch off, so the two are deliberately not symmetric.

⚠️ 818c9c0 IS UNTOUCHED, AND THAT IS GATE ⓑ BELOW. The lift fires only when the key column
HAS a value, so a blank key column still writes nothing, still lands NULL, and is still a
legitimate row from manual grid work. A ruling about rows WITH a key cannot reach rows
without one, and this file asserts that rather than asserting it in prose.
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from database.database import Base                                     # noqa: E402
from database import crud, models, schemas                             # noqa: E402

PLAIN = "s226_plain_keyed"
COMPOSITE = "s226_composite_keyed"

TABLES = {
    PLAIN: {
        "business_key": "part_no",
        "column_types": {"part_no": "string", "qty": "number", "note": "string"},
        "display_columns": ["part_no", "qty", "note"],
    },
    COMPOSITE: {
        "business_key": "cell_key",
        "composite_key_source": ["wafer", "x", "y"],
        "composite_key_separator": "_",
        "column_types": {"cell_key": "string", "wafer": "string", "x": "number",
                         "y": "number", "grade": "string"},
        "display_columns": ["cell_key", "wafer", "x", "y", "grade"],
    },
}


@pytest.fixture(name="db")
def fixture_db():
    """⚠️ THE DECLARATIONS ARE REMOVED AGAIN. `crud.TABLE_CONFIG` is process-wide, so a
    fixture that only adds leaves every later file running against a catalogue this one
    invented."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)

    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        for name in TABLES:
            crud.TABLE_CONFIG.pop(name, None)


def _push(db, table, rows):
    """One write door call, exactly as a chain mapper's batch reaches it.

    ⛔ NO `business_key_val` ANYWHERE IN HERE. That is the whole subject: a mapper that
    emits columns and leaves identity to the declaration. Spelling the key in the fixture
    would make the fixture do the product's job and every assertion below would pass on a
    tree with the lift removed."""
    batch = schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(row), source_name="chain",
                                  updated_by="s226") for row in rows])
    return crud.apply_batch_updates(db, table, batch)


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


# ---------------------------------------------------------------------------
# 🔴 ⓐ — the same key twice is one row
# ---------------------------------------------------------------------------

def test_two_writes_of_one_plain_key_land_one_row(db):
    """🔴 THE DEFECT, AND IT NEEDS THE SECOND PUSH TO SHOW. One push is indistinguishable
    between the two trees - the row lands either way. The second is where an identity is
    either found or minted again."""
    _push(db, PLAIN, [{"part_no": "PN-1", "qty": 3}])
    _push(db, PLAIN, [{"part_no": "PN-1", "qty": 7}])

    rows = _rows(db, PLAIN)
    assert len(rows) == 1, [r.business_key_val for r in rows]
    assert rows[0].business_key_val == "PN-1"
    assert rows[0].qty == 7, "the second write updated the row it found"


def test_different_plain_keys_are_different_rows(db):
    """⚠️ THE OTHER HALF OF 'ONE ROW'. A lift that returned a CONSTANT would pass the case
    above and fold the whole table onto one row."""
    _push(db, PLAIN, [{"part_no": "PN-1", "qty": 1}, {"part_no": "PN-2", "qty": 2}])
    _push(db, PLAIN, [{"part_no": "PN-1", "qty": 10}, {"part_no": "PN-2", "qty": 20}])

    rows = sorted(_rows(db, PLAIN), key=lambda r: r.business_key_val)
    assert [r.business_key_val for r in rows] == ["PN-1", "PN-2"]
    assert [r.qty for r in rows] == [10, 20]


# ---------------------------------------------------------------------------
# ⚠️ ⓑ — a blank key column is what it was yesterday (818c9c0 untouched)
# ---------------------------------------------------------------------------

def test_a_blank_key_column_is_still_refused_by_name_at_the_chain_gate(db):
    """⚠️ THE REFUSAL IS THE CHAIN'S, AND IT DID NOT MOVE. `unfilled_key_columns` names the
    column, `chain/key_gate.py` declines the row and counts it. The lift has nothing to
    lift here, so this verdict has to be one character identical."""
    blank = schemas.GeneralUpdateItem(updates={"part_no": "   ", "qty": 1})
    absent = schemas.GeneralUpdateItem(updates={"qty": 1})
    filled = schemas.GeneralUpdateItem(updates={"part_no": "PN-1", "qty": 1})

    assert crud.unfilled_key_columns(PLAIN, blank) == ["part_no"]
    assert crud.unfilled_key_columns(PLAIN, absent) == ["part_no"]
    assert crud.unfilled_key_columns(PLAIN, filled) == []


def test_a_blank_key_column_still_lands_null_rather_than_an_identity(db):
    """🔴 818c9c0 IS A DIFFERENT SUBJECT AND MUST STAY ONE. A keyless row is a legitimate
    shape from manual grid work and NULL is its accepted spelling. Widening the lift to
    fire on a blank value would give every keyless row in a table the SAME identity - the
    `''` that collides under `uq_bk_<table>` and stops the table's ingestion outright.

    🔴 THE LIFT IS ASKED DIRECTLY, BECAUSE THE ROW ALONE CANNOT SEE THIS. Measured while
    scoring the mutations: with the blank check removed the item got `business_key_val =
    ''`, and the row STILL landed NULL - `''` is falsy at every seat downstream, so
    `_get_or_create_row` ignored it and `_update_row_business_key` wrote nothing. The
    stored row is identical and the ITEM is not, so a gate that only reads the row is
    green on the defect it was written for."""
    blank = schemas.GeneralUpdateItem(updates={"part_no": "  ", "qty": 1})

    assert crud.assemble_composite_business_key(PLAIN, blank) is False
    assert blank.business_key_val is None, "never '' - that is a shared identity"

    _push(db, PLAIN, [{"part_no": "  ", "qty": 1}])
    rows = _rows(db, PLAIN)
    assert len(rows) == 1
    assert rows[0].business_key_val is None, "blank writes nothing, it does not write ''"


def test_the_lift_does_not_fire_when_the_caller_names_a_row_by_id(db):
    """⚠️ A CALLER NAMING A ROW BY ID IS NOT ASKING ABOUT IDENTITY - the same early return
    the composite half has had since 판정 190."""
    item = schemas.GeneralUpdateItem(row_id="r-1", updates={"part_no": "PN-9"})

    assert crud.assemble_composite_business_key(PLAIN, item) is False
    assert item.business_key_val is None


def test_the_lift_fills_an_absent_identity_and_never_overwrites_a_supplied_one(db):
    """🔴 THE TWO HALVES ARE NOT SYMMETRIC, AND THE FIRST CUT OF THIS ROUND GOT IT WRONG.
    The composite half OVERWRITES a supplied key on purpose (판정 190: a supplied key
    switching assembly off is how two payloads with the same columns became two rows under
    one identity). The plain half must not - there is no assembly to switch off, and a
    supplied `business_key_val` is what the prefetch filtered on and what
    `_get_or_create_row` matched.

    ⚠️ MEASURED, NOT REASONED: the first cut re-derived here, and
    `test_set_based_write_path.py::test_the_items_own_key_wins_over_any_re_derivation_from_the_payload`
    went red - a payload spelling `'1234.0'` re-keyed a row the batch had resolved as
    `'1234'`, storing it under a handle nothing looks it up by. That file owns the live
    assertion; this one records why the lift stops where it does."""
    supplied = schemas.GeneralUpdateItem(business_key_val="1234",
                                         updates={"part_no": "1234.0", "qty": 1})
    absent = schemas.GeneralUpdateItem(updates={"part_no": "1234.0", "qty": 1})

    assert crud.assemble_composite_business_key(PLAIN, supplied) is False
    assert supplied.business_key_val == "1234", "the key the batch resolved on survives"
    assert crud.assemble_composite_business_key(PLAIN, absent) is True
    assert absent.business_key_val == "1234.0"


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the composite half is one character unchanged
# ---------------------------------------------------------------------------

def test_the_composite_half_still_composes_and_writes_its_column_back(db):
    """⚠️ ONE SEAT, TWO SHAPES, AND THE OLDER SHAPE DOES NOT MOVE. The composite half also
    writes the assembled key back into `updates[key_col]`; the plain half must NOT, because
    that is where its value came from."""
    item = schemas.GeneralUpdateItem(updates={"wafer": "W1", "x": 3, "y": 7})

    assert crud.assemble_composite_business_key(COMPOSITE, item) is True
    assert item.business_key_val == "W1_3_7"
    assert item.updates["cell_key"] == "W1_3_7", "the composite half's write-back"


def test_two_writes_of_one_composite_key_still_land_one_row(db):
    _push(db, COMPOSITE, [{"wafer": "W1", "x": 3, "y": 7, "grade": "A"}])
    _push(db, COMPOSITE, [{"wafer": "W1", "x": 3, "y": 7, "grade": "B"}])

    rows = _rows(db, COMPOSITE)
    assert len(rows) == 1, [r.business_key_val for r in rows]
    assert rows[0].business_key_val == "W1_3_7"
    assert rows[0].grade == "B"


def test_a_composite_with_a_blank_part_is_still_refused(db):
    """⚠️ THE PLAIN BRANCH MUST NOT SWALLOW THE COMPOSITE ONE. A table declaring BOTH cells
    is composite, and a missing part is still no identity - reading `business_key` first
    would quietly make every composite table plain."""
    item = schemas.GeneralUpdateItem(updates={"wafer": "W1", "x": 3})

    assert crud.assemble_composite_business_key(COMPOSITE, item) is False
    assert crud.unfilled_key_columns(COMPOSITE, item) == ["y"]
