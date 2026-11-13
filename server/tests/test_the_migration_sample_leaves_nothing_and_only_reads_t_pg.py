"""copy_layers_to_lines --sample (lead 11-12 ㄹ): copy_page as it is, on a throwaway schema inside one transaction -
pages copied and timed, then rolled back: schemas, tables, rows and indexes as before, and t held by nothing stronger
than ACCESS SHARE while it ran. Refused where the lines are built already."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import MetaData, Table, create_engine, text

from database import lines
from database.models import CellOverwrite, CellSource, sql_type_of
from scripts import copy_layers_to_lines as script

pytestmark = pytest.mark.pg

HOME = "c_sample_home"
CFG = {"column_types": {"lot": "string", "qty": "number"}}


@pytest.fixture()
def home(pg_engine):
    with pg_engine.begin() as c:
        c.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % HOME))
        c.execute(text('CREATE SCHEMA "%s"' % HOME))
    engine = create_engine(pg_engine.url, connect_args={"options": "-csearch_path=%s" % HOME})
    with engine.begin() as c:
        Table("smp", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(c)
        CellSource.__table__.create(c)
        CellOverwrite.__table__.create(c)              # the pins - every database before the window has them
        c.execute(text("INSERT INTO smp (row_id, business_key_val, lot, qty) "
                       "SELECT 'r' || lpad(g::text, 5, '0'), 'k' || g, 'a' || g, g FROM generate_series(1, 2500) g"))
        for col in ("lot", "qty"):
            c.execute(text("INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value, "
                           "ingested_at, updated_by) SELECT 'smp', 'r' || lpad(g::text, 5, '0'), :c, 'f.csv', "
                           "CASE WHEN :c = 'lot' THEN to_json('a' || g) ELSE to_json(g) END, :at, 'seed' "
                           "FROM generate_series(1, 2500) g"), {"c": col, "at": datetime(2026, 11, 1, tzinfo=timezone.utc)})
    yield engine
    engine.dispose()
    with pg_engine.begin() as c:
        c.execute(text('DROP SCHEMA IF EXISTS "%s" CASCADE' % HOME))


def census(engine):
    with engine.connect() as c:
        return {"schemas": c.execute(text("SELECT count(*) FROM pg_namespace")).scalar(),
                "tables": c.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname = :s"), {"s": HOME}).scalar(),
                "indexes": c.execute(text("SELECT count(*) FROM pg_indexes WHERE schemaname = :s"), {"s": HOME}).scalar(),
                "t": c.execute(text("SELECT count(*), max(lot) FROM smp")).one()._tuple(),
                "layers": c.execute(text("SELECT count(*) FROM cell_sources")).scalar(),
                "sample schema": c.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :n"),
                                           {"n": script.SAMPLE_SCHEMA}).scalar()}


def test_the_sample_copies_pages_rolls_everything_back_and_only_reads_t(home):
    held = []
    before = census(home)
    got = script.sample(home, "smp", CFG, seconds=60, page=500, during=lambda conn: held.extend(conn.execute(text(
        "SELECT mode FROM pg_locks WHERE pid = pg_backend_pid() AND relation = CAST(:r AS regclass)"),
        {"r": '"%s"."smp"' % HOME}).scalars()))
    assert (got["pages"], got["layers"]) == (5, 5000) and got["rate"] > 0
    assert held and set(held) == {"AccessShareLock"}, held
    assert census(home) == before and before["sample schema"] == 0


def test_the_sample_is_refused_where_the_lines_are_built(home):
    from sqlalchemy.orm import Session

    with Session(bind=home) as db:
        lines.LineColumn.__table__.create(db.connection())
        db.commit()
    with pytest.raises(ValueError, match="built here already"):
        script.sample(home, "smp", CFG, seconds=1)
