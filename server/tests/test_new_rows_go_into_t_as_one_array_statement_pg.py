# -*- coding: utf-8 -*-
"""A write's new rows go into t as one statement of arrays on PostgreSQL (crud.insert_by_arrays, lead 11-13): the
executemany VALUES form sent 1k rows x 33 columns in 0.47 s, the arrays in 0.35 s (box test DB, R4 _merge_now 0.72 s).

    the INSERT a write of new rows sends    INSERT ... SELECT ... FROM unnest(...) WITH ORDINALITY
    the arrays against the VALUES form      <= 0.85 of its time, the same rows, run alone"""
import datetime
import statistics
import time

import pytest
from sqlalchemy import event, text
from sqlalchemy.dialects.postgresql import insert as upsert

from database import crud, lines, models, schemas
from tests.support import line_tables

pytestmark = pytest.mark.pg

TABLE = "zz_new_arrays"
COLS = ["c%02d" % i for i in range(29)]
CFG = {"business_key": "k", "column_types": {"k": "string", **{c: ("number" if i % 3 == 0 else "string")
                                                                for i, c in enumerate(COLS)}}}


def _values(key, i):
    return {"k": key, **{c: (float(i + j) if j % 3 == 0 else "v%d-%d" % (i, j)) for j, c in enumerate(COLS)}}


@pytest.fixture(name="wide")
def fixture_wide(pg_session, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    models.init_dynamic_models({TABLE: CFG})
    engine = pg_session.get_bind()
    bits = line_tables.build(engine, TABLE)
    try:
        yield pg_session, bits
    finally:
        pg_session.rollback()
        line_tables.drop(engine, TABLE)
        models.DYNAMIC_TABLES[TABLE].__table__.drop(bind=engine, checkfirst=True)


def test_a_write_of_new_rows_sends_one_insert_of_arrays(wide):
    db, _bits = wide
    said = []
    listen = lambda conn, cursor, statement, *a: said.append(" ".join(statement.split()))   # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listen)
    try:
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            business_key_val="K%04d" % i, updates=_values("K%04d" % i, i), source_name="f1.csv", updated_by="probe")
            for i in range(1000)]))
        db.commit()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listen)
    assert db.execute(text('SELECT count(*) FROM "%s"' % TABLE)).scalar() == 1000, "CANARY: the rows went in"
    into = [s for s in said if s.startswith('INSERT INTO "%s" ' % TABLE)]
    assert len(into) == 1 and "FROM unnest(" in into[0] and "WITH ORDINALITY" in into[0], into[:1]


def test_the_arrays_take_at_most_0_85_of_the_values_forms_time(wide):
    db, bits = wide
    t = lines.current_table(db, TABLE, CFG)
    at = datetime.datetime.now(datetime.timezone.utc)
    won = lines.won_by_stored({c: 7 for c in ["k"] + COLS}, bits)

    def rows(tag):
        return [{"row_id": "%s-%04d" % (tag, i), "business_key_val": "%s-%04d" % (tag, i), "updated_at": at,
                 **_values("%s-%04d" % (tag, i), i), lines.WON_BY: won} for i in range(1000)]

    def values_form(tag):
        return db.execute(upsert(t).on_conflict_do_nothing(index_elements=["business_key_val"])
                          .returning(t.c.row_id), rows(tag)).scalars().all()

    def arrays(tag):
        data = rows(tag)
        names = list(data[0])
        return crud.insert_by_arrays(db, t, names, [[r[c] for c in names] for r in data], "business_key_val")

    took = {"values": [], "arrays": []}
    for n in range(6):                                 # the first of each warms
        for name, form in (("values", values_form), ("arrays", arrays)):
            started = time.perf_counter()
            assert len(form("%s%d" % (name, n))) == 1000
            db.commit()
            if n:
                took[name].append(time.perf_counter() - started)
    old, new = statistics.median(took["values"]), statistics.median(took["arrays"])
    print("\n==== 1k x 33 new rows: VALUES %.3f s, arrays %.3f s" % (old, new))
    assert new <= old * 0.85, (old, new)
