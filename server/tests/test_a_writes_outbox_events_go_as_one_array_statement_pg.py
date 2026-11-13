# -*- coding: utf-8 -*-
"""A write's per-row outbox events go into database_outbox as one statement of arrays on PostgreSQL
(write_lines._stage through crud.insert_by_arrays, lead 11-13): the ORM flush of 1,000 events was most of a 1k write's
commit (0.26-0.43 s, test DB). These rows are never in the session, so the NOTIFY the flush hook latches for an outbox
row is asked by _stage itself, once.

    a 1k write's events     one INSERT INTO database_outbox ... FROM unnest(, none by the ORM; one NOTIFY
    each event              the columns the ORM filled by default (status PENDING, retry_count 0, processed_chain
                            false) and its run / transaction / row count off the payload
    the arrays              <= 0.85 of an ORM add-and-flush of the same events, run alone"""
import statistics
import time

import pytest
from sqlalchemy import event, text

from database import crud, models, schemas
from database.database import row_event
from tests.support import line_tables

pytestmark = pytest.mark.pg

TABLE = "zz_outbox_arrays"
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
    line_tables.build(engine, TABLE)
    ob = models.DatabaseOutbox.__table__
    try:
        yield pg_session
    finally:
        pg_session.rollback()
        pg_session.execute(ob.delete().where(ob.c.table_name == TABLE))
        pg_session.commit()
        line_tables.drop(engine, TABLE)
        models.DYNAMIC_TABLES[TABLE].__table__.drop(bind=engine, checkfirst=True)


def test_a_writes_events_are_one_array_insert_and_one_notify(wide):
    db = wide
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
    ob = models.DatabaseOutbox.__table__
    rows = db.execute(ob.select().where(ob.c.table_name == TABLE).order_by(ob.c.id)).mappings().all()
    assert len(rows) == 1000 and rows[0]["event_type"] == "CREATE", "CANARY: the write staged an event a row"
    into = [s for s in said if "INSERT INTO" in s and "database_outbox" in s.split("(")[0]]
    assert len(into) == 1 and "FROM unnest(" in into[0], [s[:80] for s in into]
    assert sum(1 for s in said if s.startswith("NOTIFY")) == 1
    assert {(r["status"], r["retry_count"], r["processed_chain"]) for r in rows} == {("PENDING", 0, False)}
    assert [r["payload"]["business_key"] for r in rows] == ["K%04d" % i for i in range(1000)], "the rows' order"
    assert all(r["transaction_id"] == r["payload"]["transaction_id"] for r in rows)


def test_the_arrays_take_at_most_0_85_of_the_orms_time(wide):
    db = wide
    from types import SimpleNamespace

    shape = SimpleNamespace(columns=[SimpleNamespace(name=c) for c in ["k"] + COLS])

    def events(tag):
        return [{"retry_count": 0, "processed_chain": False, **row_event("CREATE", TABLE, SimpleNamespace(
            __table__=shape, row_id="%s-%04d" % (tag, i), business_key_val="%s-%04d" % (tag, i),
            **_values("%s-%04d" % (tag, i), i)))} for i in range(1000)]

    def orm(tag):
        for one in events(tag):
            db.add(models.DatabaseOutbox(**one))
        db.flush()

    def arrays(tag):
        said = events(tag)
        names = list(said[0])
        crud.insert_by_arrays(db, models.DatabaseOutbox.__table__, names, [[s[n] for n in names] for s in said],
                              key="id")

    took = {"orm": [], "arrays": []}
    for n in range(6):                                 # the first of each warms
        for name, form in (("orm", orm), ("arrays", arrays)):
            started = time.perf_counter()
            form("%s%d" % (name, n))
            db.commit()
            if n:
                took[name].append(time.perf_counter() - started)
    old, new = statistics.median(took["orm"]), statistics.median(took["arrays"])
    print("\n==== 1k events: ORM %.3f s, arrays %.3f s" % (old, new))
    assert db.execute(text("SELECT count(*) FROM database_outbox WHERE table_name = :t"), {"t": TABLE}).scalar() == 12000
    assert new <= old * 0.85, (old, new)
