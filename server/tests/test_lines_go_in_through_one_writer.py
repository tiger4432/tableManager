"""lines.insert_lines, the one writer of t__lines rows (lead 11-12 ㄴ): on PostgreSQL its execute_values rows read back
character for character as SQLAlchemy's insert wrote them - a bit column with bit 63 set, a time at a non-UTC offset,
text with a quote, None - and its returned line_ids pair with their own rows across statements; sqlite pairs the same."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import MetaData, Table, create_engine, insert, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import lines
from database.models import sql_type_of

CFG = {"column_types": {"lot": "string", "qty": "number"}}
SEOUL = timezone(timedelta(hours=9))
MANY = lines.INSERT_PAGE * 2 + 500                       # three statements on PostgreSQL


def build(db, name):
    Table(name, MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(db.connection())
    lines.ensure_line_table(db, name, CFG)
    db.commit()
    return lines.shape(db, name, CFG)["lines"]


def row(i, batch, **cells):
    return {"line_kind": "write", "source_name": "f'%d.csv" % i, "at": datetime(2026, 11, 12, 9, i % 60, tzinfo=SEOUL),
            "written_by": "seed", "batch": batch, "input_row": None, "owner_rule": None, "owner_key": None,
            "confirmed": None, "row_id": "r%05d" % i, "business_key_val": "k%d" % i, "written_0": 1 << (i % 63),
            "head_0": 1 << (i % 63), "withdrawn_0": 0, lines.value_column("lot"): "lot-%d" % i,
            lines.value_column("qty"): None, **cells}


@pytest.fixture()
def pg(pg_engine):
    db = sessionmaker(bind=pg_engine)()
    yield db
    db.rollback()
    lines.drop_line_table(db, "lt_one")
    db.execute(text('DROP TABLE IF EXISTS "lt_one"'))
    db.commit()
    db.close()


def as_text(db, ln, batch):
    """Every cell but line_id and batch, as PostgreSQL spells it, in row order."""
    cols = [c.name for c in ln.columns if c.name not in ("line_id", "batch")]
    return db.execute(text('SELECT %s FROM "%s" WHERE batch = :b ORDER BY row_id' % (
        ", ".join('"%s"::text' % c for c in cols), ln.name)), {"b": batch}).all()


def test_the_new_insert_reads_back_as_the_old_one_wrote(pg):
    ln = build(pg, "lt_one")
    edge = {"written_0": -(1 << 63), "head_0": -1, "at": datetime(2026, 11, 12, 23, 59, 59, 123456, tzinfo=SEOUL),
            lines.value_column("lot"): "it's 한글 \\ %s"}
    for batch in ("old", "new"):
        rows = [row(i, batch) for i in range(5)] + [row(5, batch, **edge)]
        if batch == "old":
            pg.execute(insert(ln), rows)
        else:
            assert lines.insert_lines(pg, ln, rows) == []
    old, new = as_text(pg, ln, "old"), as_text(pg, ln, "new")
    assert len(old) == 6 and new == old
    assert old[5][[c.name for c in ln.columns if c.name not in ("line_id", "batch")].index("written_0")] \
        == str(-(1 << 63))


def plant_and_read(db, ln):
    rows = [row(i, "ids") for i in range(MANY)]
    got = lines.insert_lines(db, ln, rows, ids=True)
    told = dict(db.execute(select(ln.c.line_id, ln.c[lines.value_column("lot")])).all())
    return [told[i] for i in got]


def test_returned_ids_pair_with_their_own_rows_on_pg(pg):
    ln = build(pg, "lt_one")
    assert plant_and_read(pg, ln) == ["lot-%d" % i for i in range(MANY)]


def test_returned_ids_pair_with_their_own_rows_on_sqlite():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource):
        model.__table__.create(engine)
    with Session(bind=engine) as db:
        ln = build(db, "lt_one")
        assert plant_and_read(db, ln) == ["lot-%d" % i for i in range(MANY)]
