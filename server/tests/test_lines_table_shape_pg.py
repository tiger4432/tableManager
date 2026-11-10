"""database.lines on PostgreSQL (scratch schema): t stays a table with won_by + t__lines; ensure refuses a table
without a unique business key, is idempotent; column DDL lands on both; two connections claiming one new key leave
one row."""
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import lines

CFG = {"column_types": {"lot": "string", "qty": "number"}}


def make_table(db, name, cfg, unique_key=True):
    from sqlalchemy import MetaData, Table

    from database.models import sql_type_of

    Table(name, MetaData(), *lines._data_columns(cfg, sql_type_of, row_id_key=True)).create(db.connection())
    if unique_key:
        db.execute(text(f'CREATE UNIQUE INDEX "uq_bk_{name}" ON "{name}" (business_key_val)'))


@pytest.fixture()
def db(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    yield session
    session.rollback()
    for name in ("lt", "lt65", "lt_nokey"):
        lines.drop_line_table(session, name)
        session.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    session.commit()
    session.close()


def test_ensure_refuses_a_table_without_a_unique_business_key(db):
    make_table(db, "lt_nokey", CFG, unique_key=False)
    with pytest.raises(ValueError, match="add_business_key_unique_index"):
        lines.ensure_line_table(db, "lt_nokey", CFG)


def test_alter_columns_changes_t_and_its_lines(db):
    make_table(db, "lt", CFG)
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    lines.alter_columns(db, "lt", {"column_types": {"qty": "number"}}, drop=["lot"])
    db.commit()
    for rel in ("lt", "lt__lines"):
        cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = :t "
                               "AND table_schema = current_schema()"), {"t": rel}).scalars().all()
        assert "lot" not in cols and "qty" in cols, rel


def test_ensure_twice_is_quiet(db):
    make_table(db, "lt", CFG)
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()


def test_two_connections_claiming_one_new_key_leave_one_row(db, pg_engine):
    make_table(db, "lt", CFG)
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    first = pg_engine.connect()
    tx = first.begin()
    first.execute(text("INSERT INTO lt (row_id, business_key_val) VALUES ('a', 'K') "
                       "ON CONFLICT (business_key_val) DO NOTHING"))
    done = {}

    def second():
        with pg_engine.begin() as conn:
            done["rows"] = conn.execute(text("INSERT INTO lt (row_id, business_key_val) VALUES ('b', 'K') "
                                             "ON CONFLICT (business_key_val) DO NOTHING")).rowcount

    worker = threading.Thread(target=second)
    worker.start()
    worker.join(1.0)
    assert worker.is_alive(), "the second claim did not wait for the first"
    tx.commit()
    first.close()
    worker.join(10)
    assert done["rows"] == 0
    assert db.execute(text("SELECT row_id FROM lt WHERE business_key_val = 'K'")).scalars().all() == ["a"]


def test_retype_changes_t_only(db):
    make_table(db, "lt", CFG)
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    cfg = {"column_types": {"lot": "number", "qty": "number"}}
    lines.alter_columns(db, "lt", cfg, retype={"lot": '"lot"::double precision'})
    db.commit()
    kinds = dict(db.execute(text("SELECT table_name, data_type FROM information_schema.columns WHERE column_name = 'lot' "
                                 "AND table_schema = current_schema() AND table_name IN ('lt', 'lt__lines')")).all())
    assert kinds == {"lt": "double precision", "lt__lines": "character varying"}


def test_a_65th_column_rebuilds_the_head_index_on_pg(db):
    """A fresh name: slots outlive drop_line_table, so «lt» already holds slots from the tests above."""
    cfg = {"column_types": {f"c{i}": "string" for i in range(64)}}
    make_table(db, "lt65", cfg)
    lines.ensure_line_table(db, "lt65", cfg)
    db.commit()
    wider = {"column_types": {**cfg["column_types"], "c64": "string"}}
    said = lines.alter_columns(db, "lt65", wider, add=["c64"])
    db.commit()
    assert any(x.startswith("CREATE INDEX") and "head_1" in x for x in said), said
    where = db.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'lt65__lines_h' "
                            "AND schemaname = current_schema()")).scalar()
    assert "head_1" in where


def test_two_writers_noting_one_new_source_leave_one_row(pg_engine):
    seen = {}

    def note(tag):
        session = sessionmaker(bind=pg_engine)()
        try:
            lines.note_sources(session, ["pg_race_source"])
            session.commit()
            seen[tag] = "ok"
        finally:
            session.close()

    first = sessionmaker(bind=pg_engine)()
    lines.note_sources(first, ["pg_race_source"])          # holds the row's insert open
    worker = threading.Thread(target=note, args=("second",))
    worker.start()
    worker.join(1.0)
    assert worker.is_alive(), "the second insert did not wait for the first"
    first.commit()
    first.close()
    worker.join(10)
    with pg_engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM line_sources WHERE source_name = 'pg_race_source'")).scalar() == 1
        conn.execute(text("DELETE FROM line_sources WHERE source_name = 'pg_race_source'"))
    assert seen == {"second": "ok"}
