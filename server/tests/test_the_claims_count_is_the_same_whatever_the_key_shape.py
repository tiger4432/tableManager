# -*- coding: utf-8 -*-
"""총괄 043915ab0 ② · 7a: the copy mapper's claims count (`hold_copy._claims`) joins the asked keys as a
VALUES list - `=` where every part has a value, NULL-safe by themselves where one holds a NULL - and the
answer is the one a plain reading of the rows gives, keyed by the key ASKED, on SQLite and PostgreSQL.

  a key with one value set · with two      1 · 2
  a key with a NULL part, its rows alike   1, NULL = NULL
  a key nothing holds                      absent from the answer
  a key asked in another type than its column holds (text '1' of an integer column, 7 of a text
  column, 2 of a double) - PostgreSQL raised integer = text on a VALUES list (19b975908)
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from mappers import hold_copy                                         # noqa: E402

TABLE = "claims_shape_log"
KEYS, COLUMNS = ["job", "x", "y"], ["netdie"]
ROWS = [("r1", "J1", 1, 2, 7), ("r2", "J1", 1, 2, 7),                 # one set
        ("r3", "J2", 1, 2, 7), ("r4", "J2", 1, 2, 8),                 # two sets
        ("r5", "J3", None, 2, 5), ("r6", "J3", None, 2, 5),           # a NULL part, one set
        ("r7", "J4", 1, None, 5), ("r8", "J4", 1, None, 6),           # a NULL part, two sets
        ("r9", "J1", 1, 3, 9)]                                        # a neighbour of J1
ASKED = [("J1", 1, 2), ("J2", 1, 2), ("J3", None, 2), ("J4", 1, None), ("J9", 1, 2)]

#: the types apart: `code` is text, `x` integer, `y` double - and the keys are asked in the other type
TYPED = "claims_type_log"
TYPED_ROWS = [("t1", "7", 1, 2.0, 5), ("t2", "7", 1, 2.0, 5),        # one set
              ("t3", "8", 1, 2.0, 5), ("t4", "8", 1, 2.0, 6),        # two sets
              ("t5", "9", None, 2.0, 4)]                             # a NULL part
TYPED_ASKED = [(7, "1", 2), (8, "1", 2), (9, None, 2), (7, "2", 2)]
TYPED_ANSWER = {(7, "1", 2): 1, (8, "1", 2): 2, (9, None, 2): 1}


def _plain(rows, asked):
    """What the rows say, read in Python: per asked key, its distinct value sets - NULL = NULL."""
    out = {}
    for key in asked:
        sets = {(netdie,) for _id, job, x, y, netdie in rows if (job, x, y) == key}
        if sets:
            out[key] = len(sets)
    return out


def _seed(db):
    db.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
    db.execute(text('CREATE TABLE "%s" (row_id varchar PRIMARY KEY, job varchar, x double precision, '
                    'y double precision, netdie double precision)' % TABLE))
    for row in ROWS:
        db.execute(text('INSERT INTO "%s" VALUES (:i, :j, :x, :y, :n)' % TABLE),
                   dict(zip(("i", "j", "x", "y", "n"), row)))
    db.execute(text('DROP TABLE IF EXISTS "%s"' % TYPED))
    db.execute(text('CREATE TABLE "%s" (row_id varchar PRIMARY KEY, code text, x integer, '
                    'y double precision, netdie double precision)' % TYPED))
    for row in TYPED_ROWS:
        db.execute(text('INSERT INTO "%s" VALUES (:i, :c, :x, :y, :n)' % TYPED),
                   dict(zip(("i", "c", "x", "y", "n"), row)))
    db.commit()


def _both(db):
    return (hold_copy._claims(db, TABLE, KEYS, COLUMNS, ASKED),
            hold_copy._claims(db, TYPED, ["code", "x", "y"], COLUMNS, TYPED_ASKED))


def test_the_claims_on_sqlite_are_what_the_rows_say():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    try:
        _seed(db)
        shape, typed = _both(db)
        assert shape == _plain(ROWS, ASKED) == {("J1", 1, 2): 1, ("J2", 1, 2): 2,
                                                ("J3", None, 2): 1, ("J4", 1, None): 2}
        assert typed == TYPED_ANSWER
    finally:
        db.close()


@pytest.mark.pg
def test_the_claims_on_postgresql_are_what_the_rows_say(pg_engine):
    db = sessionmaker(bind=pg_engine)()
    try:
        _seed(db)
        shape, typed = _both(db)
        assert shape == _plain(ROWS, ASKED)
        assert typed == TYPED_ANSWER
    finally:
        db.rollback()
        db.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
        db.execute(text('DROP TABLE IF EXISTS "%s"' % TYPED))
        db.commit()
        db.close()
