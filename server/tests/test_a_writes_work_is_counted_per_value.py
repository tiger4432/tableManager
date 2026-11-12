# -*- coding: utf-8 -*-
"""A write's per-value work, counted (lead 11-12: «nothing pins the per-value cost, so each end-to-end board finds
the next one»). N rows x C written columns on a table of W > C columns, through the funnel; each count is a call
counter wrapped on the real module function. A same-value re-ingest asks, per value: one cast, one line text, and
the head's stored text equal to it (no conversion) - and per row one owner read; the head lines' bit masks are read
once a written column, not once a table column a head line. A changed-value write adds, per value, the head's text
read again (a number's - `_head_text`), the merge's and the outbox's «did the shown value move», and per row the
re-key's key part."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, models, schemas, write_lines
from database.database import Base

TABLE = "zz_per_value"
N = 20
WRITTEN = {"n0": "number", "s0": "string", "s1": "string"}                      # C = 3
COLUMNS = {"k": "string", **WRITTEN, **{"x%d" % i: "string" for i in range(8)}}   # W = 12
CONFIG = {TABLE: {"business_key": "k", "column_types": COLUMNS, "display_columns": list(COLUMNS)}}
C = len(WRITTEN)
COUNTED = [(crud, "cast_value_by_type"), (crud, "line_text"), (crud, "values_differ"), (crud, "layer_owner"),
           (write_lines, "_head_text"), (write_lines, "_bit")]


@pytest.fixture(name="db")
def fixture_db():
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    from tests.support import line_tables

    line_tables.build(engine, TABLE)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _write(db, tag, number):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="K%03d" % i, source_name="f1.csv", updated_by="probe",
                                  updates={"n0": number + i, "s0": "%s%d" % (tag, i), "s1": "t%s%d" % (tag, i)})
        for i in range(N)]))
    db.commit()


def _counted(monkeypatch):
    calls = {name: 0 for _module, name in COUNTED}
    for module, name in COUNTED:
        real = getattr(module, name)

        def counting(*args, _real=real, _name=name, **kwargs):
            calls[_name] += 1
            return _real(*args, **kwargs)
        monkeypatch.setattr(module, name, counting)
    return calls


def _lines(db):
    from sqlalchemy import text

    from database import lines
    return db.execute(text('SELECT count(*) FROM "%s"' % lines.lines_relation(TABLE))).scalar()


def test_a_same_value_reingest_costs_one_of_each_a_value(db, monkeypatch):
    _write(db, "a", 1)
    written = _lines(db)
    assert written == N, "CANARY: one line a row"
    calls = _counted(monkeypatch)
    _write(db, "a", 1.0)                           # the same values - the number re-spelled 1.0
    assert _lines(db) == written, "a repeat writes no line"
    assert calls == {"cast_value_by_type": N * C, "line_text": N * C, "values_differ": 0, "_head_text": 0,
                     "layer_owner": N, "_bit": C}, str(sorted(calls.items()))


def test_a_changed_value_write_adds_the_merges_compare_a_value(db, monkeypatch):
    _write(db, "a", 1)
    written = _lines(db)
    calls = _counted(monkeypatch)
    _write(db, "b", 100)                           # every written value moves
    assert _lines(db) == written + N, "one line a row"
    assert db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(business_key_val="K003").one().s0 == "b3"
    # per value: cast, line text, the head's text read again (a number head as its line text - one more line_text
    # a number value), the merge's «moved» and the outbox's (`_stage`); per row: the owner, the re-key's key part
    numbers = sum(1 for kind in WRITTEN.values() if kind == "number")
    assert calls == {"cast_value_by_type": N * C, "line_text": N * C + N * numbers, "values_differ": 2 * N * C + N,
                     "_head_text": N * C, "layer_owner": N, "_bit": C}, str(sorted(calls.items()))


def test_a_number_the_merge_respells_is_still_compared_and_a_kept_value_is_not(db, monkeypatch):
    """A write of s0 alone merges s0 (lead 11-12 b); n0, not merged, is re-spelled as its line reads it (2, not 2.0) -
    a new object of the same value, so «did it move» is asked of it and answers no; s1 and the unwritten columns are
    the very values read and are not asked."""
    _write(db, "a", 1)
    calls = _counted(monkeypatch)
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="K%03d" % i, source_name="f1.csv", updated_by="probe",
                                  updates={"s0": "z%d" % i}) for i in range(N)]))
    db.commit()
    row = db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(business_key_val="K003").one()
    assert (row.s0, float(row.n0), row.s1) == ("z3", 4.0, "ta3")
    # per row: the merge's s0 and n0, the outbox's s0 and n0, the re-key's key part
    assert calls["values_differ"] == 5 * N, str(sorted(calls.items()))
