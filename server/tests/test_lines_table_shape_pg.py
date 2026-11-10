"""database.lines on PostgreSQL (scratch schema): the view refuses writes, PG refuses column DDL under the view
while alter_columns goes through, ensure is idempotent, and two connections claiming the same new key leave one
current line."""
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import lines

CFG = {"column_types": {"lot": "string", "qty": "number"}}


@pytest.fixture()
def db(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    yield session
    session.rollback()
    lines.drop_line_table(session, "lt")
    session.commit()
    session.close()


def test_the_view_refuses_writes(db):
    lines.ensure_line_table(db, "lt", CFG)
    db.execute(text("INSERT INTO lt__now (row_id, business_key_val) VALUES ('r0', 'k0')"))
    for stmt in ("INSERT INTO lt (row_id) VALUES ('r1')", "UPDATE lt SET lot = 'x'", "DELETE FROM lt"):
        db.execute(text("SAVEPOINT s"))
        with pytest.raises(Exception, match="write through database.lines"):
            db.execute(text(stmt))
        db.execute(text("ROLLBACK TO SAVEPOINT s"))


def test_pg_refuses_ddl_under_the_view_and_alter_columns_goes_through(db):
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    db.execute(text("SAVEPOINT s"))
    with pytest.raises(Exception) as refused:
        db.execute(text('ALTER TABLE lt__now DROP COLUMN "lot"'))
    assert refused.value.orig.pgcode == "2BP01"          # dependent_objects_still_exist - the box PG speaks Korean
    db.execute(text("ROLLBACK TO SAVEPOINT s"))
    lines.alter_columns(db, "lt", {"column_types": {"qty": "number"}}, drop=["lot"])
    db.commit()
    cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'lt' "
                           "AND table_schema = current_schema()")).scalars().all()
    assert "lot" not in cols and "qty" in cols


def test_ensure_twice_is_quiet(db):
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()


def test_two_connections_claiming_one_new_key_leave_one_line(db, pg_engine):
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    first = pg_engine.connect()
    tx = first.begin()
    first.execute(text("INSERT INTO lt__now (row_id, business_key_val) VALUES ('a', 'K') "
                       "ON CONFLICT (business_key_val) DO NOTHING"))
    done = {}

    def second():
        with pg_engine.begin() as conn:
            done["rows"] = conn.execute(text("INSERT INTO lt__now (row_id, business_key_val) VALUES ('b', 'K') "
                                             "ON CONFLICT (business_key_val) DO NOTHING")).rowcount

    worker = threading.Thread(target=second)
    worker.start()
    worker.join(1.0)
    assert worker.is_alive(), "the second claim did not wait for the first"
    tx.commit()
    first.close()
    worker.join(10)
    assert done["rows"] == 0
    assert db.execute(text("SELECT row_id FROM lt__now WHERE business_key_val = 'K'")).scalars().all() == ["a"]


def test_retype_changes_now_only(db):
    lines.ensure_line_table(db, "lt", CFG)
    db.commit()
    cfg = {"column_types": {"lot": "number", "qty": "number"}}
    lines.alter_columns(db, "lt", cfg, retype={"lot": '"lot"::double precision'})
    db.commit()
    kinds = dict(db.execute(text("SELECT table_name, data_type FROM information_schema.columns WHERE column_name = 'lot' "
                                 "AND table_schema = current_schema() AND table_name IN ('lt__now', 'lt__lines')")).all())
    assert kinds == {"lt__now": "double precision", "lt__lines": "character varying"}


def test_a_65th_column_rebuilds_the_head_index_on_pg(db):
    """A fresh name: slots outlive drop_line_table, so «lt» already holds slots from the tests above."""
    cfg = {"column_types": {f"c{i}": "string" for i in range(64)}}
    try:
        lines.ensure_line_table(db, "lt65", cfg)
        db.commit()
        wider = {"column_types": {**cfg["column_types"], "c64": "string"}}
        said = lines.alter_columns(db, "lt65", wider, add=["c64"])
        db.commit()
        assert any(x.startswith("CREATE INDEX") and "head_1" in x for x in said), said
        where = db.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'lt65__lines_h' "
                                "AND schemaname = current_schema()")).scalar()
        assert "head_1" in where
    finally:
        db.rollback()
        lines.drop_line_table(db, "lt65")
        db.commit()
