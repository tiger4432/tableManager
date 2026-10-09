# -*- coding: utf-8 -*-
"""총괄 043915ab0 ②: the copy mapper's claims count (`hold_copy._claims`) joins the keys that have a
value in every part as a VALUES list and asks the keys holding a NULL by themselves - the answer is
the one a plain reading of the rows gives, on SQLite and on PostgreSQL.

  a key with one value set · with two      1 · 2
  a key with a NULL part, its rows alike   1, NULL = NULL
  a key nothing holds                      absent from the answer
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
    db.commit()


def _answer(db):
    return {tuple(None if v is None else (v if isinstance(v, str) else float(v)) for v in key): n
            for key, n in hold_copy._claims(db, TABLE, KEYS, COLUMNS, ASKED).items()}


def _expected():
    return {tuple(None if v is None else (v if isinstance(v, str) else float(v)) for v in key): n
            for key, n in _plain(ROWS, ASKED).items()}


def test_the_claims_on_sqlite_are_what_the_rows_say():
    engine = create_engine("sqlite://")
    db = sessionmaker(bind=engine)()
    try:
        _seed(db)
        assert _answer(db) == _expected() == {("J1", 1.0, 2.0): 1, ("J2", 1.0, 2.0): 2,
                                              ("J3", None, 2.0): 1, ("J4", 1.0, None): 2}
    finally:
        db.close()


@pytest.mark.pg
def test_the_claims_on_postgresql_are_what_the_rows_say(pg_engine):
    db = sessionmaker(bind=pg_engine)()
    try:
        _seed(db)
        assert _answer(db) == _expected()
    finally:
        db.rollback()
        db.execute(text('DROP TABLE IF EXISTS "%s"' % TABLE))
        db.commit()
        db.close()
