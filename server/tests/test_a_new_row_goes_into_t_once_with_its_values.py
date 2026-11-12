# -*- coding: utf-8 -*-
"""A new row goes into t once, with its values (lead 11-13 ㄱ; main's unit of work inserted it once): step 1 names its
row_id and puts nothing, step 5 inserts it with its merged values, won_by and updated_at - before, step 1 put a bare
row and step 5 updated it, one dead t row a new row (the 11-13 marathon's t bloat). A key another writer put meanwhile
(PostgreSQL) is that writer's row: this write's lines go there, nothing orphaned, one head a (row, source, column) -
the largest line_id - and t shows the merge of those heads, whichever writer committed first.

    case                                    sqlite              PostgreSQL
    1,000 new rows                          t INSERT 1 · UPDATE 0
    two writers of one new key              -                   both commit orders: one row, no orphan, one head"""
import threading
import time

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, lines, models, schemas, write_lines
from database.database import Base

TABLE = "zz_new_once"
COLUMNS = {"k": "string", "a": "string", "b": "number"}
CONFIG = {TABLE: {"business_key": "k", "column_types": COLUMNS, "display_columns": list(COLUMNS)}}
N = 1000


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


def _statements(db, run):
    seen = []
    listen = lambda conn, cursor, statement, *a: seen.append(" ".join(statement.split()[:3]))   # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listen)
    try:
        run()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listen)
    return seen


def test_new_rows_go_into_t_once_with_their_values(db):
    said = _statements(db, lambda: (crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="K%04d" % i, updates={"k": "K%04d" % i, "a": "x%d" % i, "b": i},
                                  source_name="f1.csv", updated_by="probe") for i in range(N)])), db.commit()))
    rows = {r.k: (r.a, r.b) for r in db.query(models.DYNAMIC_TABLES[TABLE]).all()}
    assert len(rows) == N and rows["K0007"] == ("x7", 7), "CANARY: the write made its rows with their values"
    on_t = [s.split() for s in said]
    into_t = [w for w in on_t if w[:2] == ["INSERT", "INTO"] and w[2].strip('"') == TABLE]
    updates = [w for w in on_t if w[0] == "UPDATE" and w[1].strip('"') == TABLE]
    assert (len(into_t), len(updates)) == (1, 0), said


# --- PostgreSQL: two writers of one new key ---------------------------------------------------------------------

PG_TABLE = "pgqa_bk_table"


def _pg_write(db, qty, source):
    crud.apply_batch_updates(db, PG_TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val="PN-RACE", updates={"part_no": "PN-RACE", "qty": qty}, source_name=source,
        updated_by="probe")]))
    db.commit()


def _heads_one_each(db):
    """[(source, column, the head line ids, the largest line_id naming it)] where they differ, and t's qty against the
    merge of the heads, and the lines no t row holds."""
    rel = lines.lines_relation(PG_TABLE)
    bits = lines.bit_map(db, PG_TABLE)
    found = db.execute(text('SELECT line_id, row_id, source_name, line_kind, written_0, head_0 FROM "%s"' % rel)).all()
    rows = db.execute(text('SELECT row_id, qty FROM "%s" WHERE business_key_val = :k' % PG_TABLE),
                      {"k": "PN-RACE"}).all()
    orphans = db.execute(text('SELECT count(*) FROM "%s" l WHERE NOT EXISTS (SELECT 1 FROM "%s" t WHERE t.row_id = '
                              'l.row_id)' % (rel, PG_TABLE))).scalar()
    wrong = []
    for c, bit in bits.items():
        m = 1 << bit
        for source in {line[2] for line in found}:
            naming = [line for line in found if line[2] == source and line[3] in ("write", "withdraw")
                      and (line[4] & ((1 << 64) - 1)) & m]
            if not naming:
                continue
            heads = sorted(line[0] for line in naming if (line[5] & ((1 << 64) - 1)) & m)
            if heads != [max(line[0] for line in naming)]:
                wrong.append((source, c, heads, max(line[0] for line in naming)))
    merged = lines.merge(db, PG_TABLE, crud.TABLE_CONFIG[PG_TABLE], [r[0] for r in rows])
    return rows, orphans, wrong, merged


@pytest.mark.pg
@pytest.mark.parametrize("first", ["the second writer", "the first writer"])
def test_two_writers_of_one_new_key_end_on_one_row_with_one_head_each(pg_session, monkeypatch, first):
    """Writer 1 starts first and stops at step 5: before its INSERT («the second writer» commits the key first - writer
    1's lines, the older ones, move onto writer 2's row) or after it, uncommitted («the first writer» commits first -
    writer 2's INSERT waits on it and loses, its newer lines move onto writer 1's row)."""
    from tests.support import line_tables

    engine = pg_session.get_bind()
    line_tables.build(engine, PG_TABLE)
    Maker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    one, two = Maker(), Maker()
    real = write_lines._merge_now
    reached, go, errors = threading.Event(), threading.Event(), []

    def held(*a, **k):
        if threading.current_thread().name != "writer 1":
            return real(*a, **k)
        if first == "the second writer":
            reached.set()
            go.wait(30)
            return real(*a, **k)
        answer = real(*a, **k)
        reached.set()
        go.wait(30)
        return answer

    monkeypatch.setattr(write_lines, "_merge_now", held)

    def run(db, qty, source, name):
        try:
            _pg_write(db, qty, source)
        except Exception as exc:                   # noqa: BLE001 - asserted below
            errors.append((name, exc))

    try:
        w1 = threading.Thread(target=run, args=(one, 1, "f1.csv", "writer 1"), name="writer 1")
        w1.start()
        assert reached.wait(30), "CANARY: writer 1 reached step 5"
        w2 = threading.Thread(target=run, args=(two, 2, "f1.csv", "writer 2"), name="writer 2")
        w2.start()
        if first == "the second writer":
            w2.join(60)
            go.set()
        else:
            time.sleep(1.0)                        # writer 2 at its INSERT, waiting on writer 1's row
            go.set()
            w2.join(60)
        w1.join(60)
        assert not errors, errors
        pg_session.expire_all()
        rows, orphans, wrong, merged = _heads_one_each(pg_session)
        assert len(rows) == 1, rows
        assert (orphans, wrong) == (0, []), (orphans, wrong)
        assert rows[0][1] == merged[rows[0][0]]["qty"][0] == 2, (rows, merged)   # the newer line of f1 shows
    finally:
        for s in (one, two, pg_session):
            s.rollback()
            s.close()
        line_tables.drop(engine, PG_TABLE)
