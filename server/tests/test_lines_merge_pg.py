"""database.lines.merge / winners_sql on PostgreSQL (scratch schema): the same cells as test_lines_merge give
compute_priority_value's winner - bigint masks (bit 63 is the sign), the CASE terms and row_number run on PG."""
from datetime import timedelta

import pytest
from sqlalchemy import MetaData, Table, text
from sqlalchemy.orm import sessionmaker

from database import crud, lines
from database.models import sql_type_of
from tests.test_lines_merge import CELLS, CFG, T0, pin, put


@pytest.fixture()
def db(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(session.connection())
    session.execute(text('CREATE UNIQUE INDEX "uq_bk_t" ON "t" (business_key_val)'))
    lines.ensure_line_table(session, "t", CFG)
    yield session
    session.rollback()
    lines.drop_line_table(session, "t")
    session.execute(text('DROP TABLE IF EXISTS "t"'))
    session.execute(text("DELETE FROM cell_overwrites WHERE table_name = 't'"))
    session.execute(text("DELETE FROM line_columns WHERE table_name = 't'"))
    session.commit()
    session.close()


def test_the_sql_winner_is_compute_priority_values_winner_on_pg(db):
    for row, (layers, pinned) in CELLS.items():
        for source, minutes, value, withdrawn in layers:
            put(db, row, source, None if minutes is None else T0 + timedelta(minutes=minutes), value, withdrawn)
        if pinned:
            pin(db, row, pinned)
    got = lines.merge(db, "t", CFG, list(CELLS))
    for row, (layers, pinned) in CELLS.items():
        sources = {source: {"value": value, "ingested_at": None if minutes is None else T0 + timedelta(minutes=minutes)}
                   for source, minutes, value, withdrawn in layers if not withdrawn}
        assert got[row]["lot"][0] == crud.compute_priority_value(sources, pinned, "t")[0], row


def test_the_sign_bit_column_merges_on_pg(db):
    wide = {"column_types": {**CFG["column_types"], **{f"c{i}": "string" for i in range(63)}}}
    lines.alter_columns(db, "t", wide, add=[f"c{i}" for i in range(63)])
    sign = next(c for c, b in lines.bit_map(db, "t").items() if b == 63)
    put(db, "r1", "fileA", T0, "x", column=sign)
    assert lines.merge(db, "t", wide, ["r1"])["r1"][sign][0] == "x"
