"""database.lines on PostgreSQL (scratch schema): t stays a table with won_by + t__lines; ensure builds a table's
lines with or without a unique business key (owner 11-11: lines are bound to row_id), is idempotent; column DDL lands on both; two connections claiming one new key leave
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
    for name in ("lt", "lt65", "lt_nokey", "lt_dups", "lt_ix"):
        lines.drop_line_table(session, name)
        session.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    session.commit()
    session.close()


def test_a_table_without_the_key_index_or_with_keys_held_twice_keeps_lines(db):
    """Lines are bound to row_id - the key index is the write's upsert's alone (owner 11-11)."""
    from sqlalchemy import inspect

    make_table(db, "lt_nokey", CFG, unique_key=False)
    make_table(db, "lt_dups", CFG, unique_key=False)
    db.execute(text("INSERT INTO lt_dups (row_id, business_key_val) VALUES ('a', 'K'), ('b', 'K')"))
    assert not lines.key_index_standing(db.connection(), "lt_nokey")              # canary: no index stands
    for name in ("lt_nokey", "lt_dups"):
        lines.ensure_line_table(db, name, CFG)
        assert inspect(db.connection()).has_table(f"{name}__lines") and lines.has_lines(db, name)


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


def test_a_65th_column_builds_the_head_index_concurrently_on_pg(db, pg_engine):
    """A fresh name: slots outlive drop_line_table, so «lt» already holds slots from the tests above. The column DDL
    leaves the head index alone; head_index builds the new chunk's one CONCURRENTLY and takes the old away."""
    from database import models

    cfg = {"column_types": {f"c{i}": "string" for i in range(64)}}
    make_table(db, "lt65", cfg)
    lines.ensure_line_table(db, "lt65", cfg)
    db.commit()
    wider = {"column_types": {**cfg["column_types"], "c64": "string"}}
    said = lines.alter_columns(db, "lt65", wider, add=["c64"])
    db.commit()
    assert not any("INDEX" in x for x in said), said                     # nothing in the column DDL's transaction
    assert lines.head_index(pg_engine, "lt65", wider) == models.INDEX_BUILT
    names = dict(db.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'lt65__lines' "
                                 "AND schemaname = current_schema()")).all())
    assert "head_1" in names["lt65__lines_h2"] and "lt65__lines_h" not in names
    assert lines.head_index(pg_engine, "lt65", wider) == models.INDEX_PRESENT


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


def line_index_names(db, name):
    """{index: valid} of t__lines in this schema."""
    return dict(db.execute(text(
        "SELECT c.relname, i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
        "JOIN pg_class t ON t.oid = i.indrelid WHERE t.relname = :t AND t.relnamespace = "
        "(SELECT oid FROM pg_namespace WHERE nspname = current_schema())"), {"t": lines.lines_relation(name)}).all())


@pytest.fixture()
def lt_ix(db, monkeypatch):
    from database import crud

    make_table(db, "lt_ix", CFG)
    lines.ensure_line_table(db, "lt_ix", CFG)
    db.commit()
    monkeypatch.setitem(crud.TABLE_CONFIG, "lt_ix", CFG)
    return {i.name for i in lines.shape(db, "lt_ix", CFG)["lines"].indexes}


def test_every_declared_line_index_dropped_is_built_again_valid_by_the_start(db, pg_engine, lt_ix, caplog):
    """Lead 11-12: ra, b, p, h and i each dropped on a built line table - the start's ensure builds it back, valid,
    and says the line the operator reads (RUN.md [11-12c])."""
    import logging

    caplog.set_level(logging.INFO, logger=lines.__name__)
    assert len(lt_ix) == 5 and set(line_index_names(db, "lt_ix")) >= lt_ix
    for name in sorted(lt_ix):
        db.execute(text(f'DROP INDEX "{name}"'))
        db.commit()
        assert name not in line_index_names(db, "lt_ix")
        caplog.clear()
        assert lines.ensure_declared(pg_engine, tables=["lt_ix"]) == {}
        assert line_index_names(db, "lt_ix").get(name) is True, name
        assert [r.getMessage().split(" built in ")[0] for r in caplog.records if " built in " in r.getMessage()] \
            == [f"[Indexes] line index '{name}'"]


def test_a_line_index_not_built_refuses_the_start_naming_it(db, pg_engine, lt_ix, monkeypatch):
    from database import models

    name = sorted(lt_ix)[0]
    db.execute(text(f'DROP INDEX "{name}"'))
    db.commit()
    builder = models._ensure_one_index_once
    monkeypatch.setattr(models, "_ensure_one_index_once", lambda engine, n, *a, **k: (
        models.INDEX_DEFERRED if n == name else builder(engine, n, *a, **k)))
    refused = lines.ensure_declared(pg_engine, tables=["lt_ix"])
    assert list(refused) == ["lt_ix"] and f"index {name} not built (deferred)" in refused["lt_ix"]
