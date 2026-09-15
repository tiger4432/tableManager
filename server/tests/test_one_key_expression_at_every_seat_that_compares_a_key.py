# -*- coding: utf-8 -*-
"""S-245. 키 식의 저자는 «하나»다 — 접기·타입·NULL 셋이 한 함수에서 나온다.

🔴 THE FOLD WAS NEVER THE WHOLE KEY. What a join compares, what a unique index is built
on, and what a duplicate probe groups by is `coalesce(fold(col), '')` - and the type
question inside it was answered separately at four seats. `chain.join_into` learned to
cast a non-text column on 2026-09-15; `virtual_join.executor.join_onclause` and
`virtual_join.config.index_key_expression` did not. So a `number` join key answered the
owner with 「invalid input syntax for type double precision: ""」 at three of the four,
including on the READ path, where the failed statement aborted the read's own transaction.

> 소유자 2026-09-15: 「더블 프리시전 자료형 오류 — 내가 이런거 뜨게하지 말랬지 **알아서
> 접어서 하라고**」

⛔ AND A DISAGREEMENT HERE DOES NOT FAIL, IT GOES QUIET. PostgreSQL uses an expression
index only when the query's expression MATCHES it (S-181), so a second spelling is a
sequential scan on a 10-million-row table with every test green. That is why this file
scores the four renderings against ONE fixture rather than each seat against itself.

⚠️ WHAT THIS FILE CANNOT PROVE. SQLite is the suite, and it has neither `::text` nor the
fold's `regexp_replace`. Every assertion here compiles in the **PostgreSQL dialect** without
a PostgreSQL - which scores the SPELLING and not the execution. That a cast key actually
builds an index is `contracts/` work and a restart.
"""
import os
import sys

import pytest
from sqlalchemy import Column, Float, MetaData, String, Table
from sqlalchemy.dialects import postgresql

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import notation_norm                                              # noqa: E402
import virtual_join.config as vjc                                 # noqa: E402
from chain import join_into                                       # noqa: E402
from virtual_join import executor as vje                          # noqa: E402

FOLD = {"separator": True, "case": True}


@pytest.fixture(name="tables")
def fixture_tables():
    """A numeric key and a text key, side by side - the discriminating pair."""
    metadata = MetaData()
    left = Table("s245_left", metadata,
                 Column("num", Float), Column("txt", String))
    right = Table("s245_right", metadata,
                  Column("num", Float), Column("txt", String))
    return left, right


def _pg(element) -> str:
    return str(element.compile(dialect=postgresql.dialect(),
                               compile_kwargs={"literal_binds": True}))


@pytest.fixture(name="known")
def fixture_known(monkeypatch):
    """The type lookup reads the live model registry, so the fixture registers a MODEL.

    ⚠️ NOT A `Table`. `DYNAMIC_TABLES` holds mapped classes, and `getattr(cls, column)`
    gives an `InstrumentedAttribute` rather than a `Column` - a fixture registering the
    column collection would ask a different object for its type than production does, and
    would go green whether or not the real path can answer at all."""
    from sqlalchemy import Integer
    from sqlalchemy.orm import declarative_base

    from database import models

    base = declarative_base()

    class _Left(base):
        __tablename__ = "s245_left"
        row_id = Column(Integer, primary_key=True)
        num = Column(Float)
        txt = Column(String)

    monkeypatch.setitem(models.DYNAMIC_TABLES, "s245_left", _Left)
    return _Left


# ---------------------------------------------------------------------------
# 🔴 ⓐ — one author, two renderings, and they agree
# ---------------------------------------------------------------------------

def test_the_two_renderings_of_a_numeric_key_are_the_same_expression(tables):
    """🔴 THE GATE OF THIS ROUND. The ON clause compiles through SQLAlchemy and the index
    DDL is text an operator pastes into psql; if those two differ the index exists and the
    join does not use it."""
    left, _right = tables

    compiled = _pg(notation_norm.key_expression_sql(left.c.num))
    ddl = notation_norm.key_expression_text("s245_left.num", None, text_column=False)

    assert compiled == ddl == "coalesce(s245_left.num::text, '')"


def test_the_two_renderings_of_a_text_key_are_byte_identical_to_yesterday(tables):
    """⚠️ NO CAST, BECAUSE EVERY INDEX BUILT YESTERDAY IS THAT SHAPE. An unconditional cast
    would change the required expression for every text join at once, and PostgreSQL would
    stop recognising the indexes that already cover them - every join unapproved."""
    left, _right = tables

    compiled = _pg(notation_norm.key_expression_sql(left.c.txt))
    ddl = notation_norm.key_expression_text('"txt"', None, text_column=True)

    assert compiled == "coalesce(s245_left.txt, '')"
    assert ddl == "coalesce(\"txt\", '')"


def test_a_folded_text_key_still_comes_out_of_the_one_fold(tables):
    """⚠️ THE FOLD IS UNCHANGED BY THIS ROUND — it was already one author. What moved is the
    two pieces AROUND it, which had three."""
    left, _right = tables

    compiled = _pg(notation_norm.key_expression_sql(left.c.txt, FOLD))
    ddl = notation_norm.key_expression_text("s245_left.txt", FOLD, text_column=True)

    assert compiled == ddl
    assert compiled.startswith("coalesce(translate(regexp_replace(")


def test_the_cast_asks_the_column_not_whatever_the_fold_returned(tables):
    """🔴 THE ORDER IS A CLAIM, SO IT IS SCORED HERE AND NOWHERE ELSE. The fold construct
    declares a String type, so a cast decided AFTER folding can only ever answer 「already
    text」 - it would silently stop casting the moment a fold appeared.

    ⚠️ AND THE PRODUCT CANNOT BUILD THIS PAIR TODAY: the declaration validator refuses a
    fold on a non-string column, which is why a mutation swapping the two orders passes
    every other test in this suite. That is an argument for pinning it, not against - the
    day that validator loosens, this is the line that keeps the expression right."""
    left, _right = tables

    assert "::text" in _pg(notation_norm.key_expression_sql(left.c.num, FOLD))


# ---------------------------------------------------------------------------
# 🔴 ⓑ — the four seats, one fixture
# ---------------------------------------------------------------------------

def test_the_read_time_on_clause_casts_a_numeric_key(tables):
    """🔴 THIS IS THE SEAT THE OWNER MET. `coalesce(col, '')` against a `number` column is
    the statement PostgreSQL refused, and it refused it on the READ path."""
    left, right = tables
    rule = {"join_key": [{"left": "num", "right": "num", "fold": None}]}

    clause = _pg(vje.join_onclause(left.c, right.c, rule))

    assert clause == "coalesce(s245_left.num::text, '') = coalesce(s245_right.num::text, '')"


def test_the_read_time_on_clause_leaves_a_text_key_alone(tables):
    left, right = tables
    rule = {"join_key": [{"left": "txt", "right": "txt", "fold": None}]}

    clause = _pg(vje.join_onclause(left.c, right.c, rule))

    assert clause == "coalesce(s245_left.txt, '') = coalesce(s245_right.txt, '')"


def test_the_write_time_join_folds_the_same_key_the_same_way(tables):
    """⚠️ AND THIS SEAT ALREADY CAST - it is the one that taught the others. What it did
    NOT do is ask the question of the COLUMN: it asked whatever the fold returned, and the
    fold construct declares a String type, so the answer was always 「already text」."""
    left, _right = tables

    assert (_pg(join_into._folded(left.c.num, None))
            == _pg(notation_norm.key_expression_sql(left.c.num)))
    assert (_pg(join_into._folded(left.c.txt, FOLD))
            == _pg(notation_norm.key_expression_sql(left.c.txt, FOLD)))


def test_the_index_ddl_casts_a_numeric_key_and_only_when_it_knows(known):
    """🔴 [S-245] THE DDL IS WHERE THE TYPE IS HARDEST TO KNOW, and the answer when it
    cannot is 「text」 - the expression this product emitted yesterday. Guessing 「not text」
    for an unresolvable column would put a cast into an index expression the existing
    indexes do not have, and every join on that table would go unapproved."""
    assert (vjc.index_key_expression("num", None, "s245_left")
            == "coalesce(\"num\"::text, '')")
    assert (vjc.index_key_expression("txt", None, "s245_left")
            == "coalesce(\"txt\", '')")
    assert (vjc.index_key_expression("num", None, "a_table_nobody_declared")
            == "coalesce(\"num\", '')")
    assert vjc.index_key_expression("num", None) == "coalesce(\"num\", '')"


def test_the_duplicate_probe_groups_by_the_expression_the_index_is_built_on(known):
    """⛔ THIS ONE TOOK THE READ PATH DOWN. `GROUP BY coalesce(number_col, '')` raised
    inside the auto-index probe, and a raised statement aborts the transaction the read was
    already in - so the switch an operator reached for did not stop the flood (S-248's
    sibling). The probe could not ask the type because it was never handed the table."""
    from virtual_join import unique_key

    assert (unique_key._expressions("s245_left", ["num", "txt"], None)
            == ["coalesce(\"num\"::text, '')", "coalesce(\"txt\", '')"])


def test_the_index_name_does_not_move_when_the_cast_appears(known):
    """⚠️ THE NAME CARRIES THE FOLD, NOT THE TYPE. If a cast changed the name, the index a
    numeric join needs would be asked for under a new name every time this product learned
    something about types - and the old one would be retracted (S-248) and rebuilt."""
    assert (vjc.required_index_name("s245_left", ["num"])
            == vjc.required_index_name("s245_left", ["num"], [None]))
    assert vjc.required_index_name("s245_left", ["num"]).endswith("_ns")


# ---------------------------------------------------------------------------
# ⚠️ ⓒ — the comparator that decides whether an index counts
# ---------------------------------------------------------------------------

def test_the_cast_is_invisible_to_the_index_comparator(known):
    """🔴 WHY THE SPELLING IS `::text` AND NOT `CAST(... AS TEXT)`.
    `normalize_index_expression` strips `::text` as noise PostgreSQL adds when it renders an
    index definition - so an index built either way is still recognised as covering the key.
    `CAST(... AS TEXT)` is NOT stripped there, and rendering it that way on PostgreSQL would
    make every join on a cast key unapproved even though its index exists."""
    with_cast = vjc.normalize_index_expression(
        vjc.index_key_expression("num", None, "s245_left"))
    without = vjc.normalize_index_expression(
        vjc.index_key_expression("num", None, None))

    assert with_cast == without == "coalesce(num,'')"
