"""lines.stamped_by on PostgreSQL (scratch schema): the cells these source rows feed, each origin asked through
t__lines_i on its own (LATERAL, OFFSET 0 - 총괄 d28171060), a withdrawn column left out."""
import pytest
from sqlalchemy import MetaData, Table, event, text
from sqlalchemy.orm import sessionmaker

from database import lines
from database.models import sql_type_of

CFG = {"column_types": {"lot": "string", "qty": "number"}}
NAME = "sb_t"


@pytest.fixture()
def db(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    Table(NAME, MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(session.connection())
    session.execute(text(f'CREATE UNIQUE INDEX "uq_bk_{NAME}" ON "{NAME}" (business_key_val)'))
    s = lines.ensure_line_table(session, NAME, CFG)
    lot, qty = lines._mask(s["bits"]["lot"]), lines._mask(s["bits"]["qty"])
    session.execute(s["lines"].insert(), [
        {"line_kind": "write", "source_name": "chain_ingestion", "row_id": "r1", "input_row": "o1",
         "written_0": lot | qty, "head_0": lot | qty, "withdrawn_0": 0},
        {"line_kind": "write", "source_name": "chain_ingestion", "row_id": "r2", "input_row": "o2",
         "written_0": lot | qty, "head_0": lot | qty, "withdrawn_0": qty},
        {"line_kind": "write", "source_name": "user", "row_id": "r1", "input_row": None,
         "written_0": lot, "head_0": lot, "withdrawn_0": 0}])
    yield session
    session.rollback()
    lines.drop_line_table(session, NAME)
    session.execute(text(f'DROP TABLE IF EXISTS "{NAME}"'))
    session.execute(text(f"DELETE FROM line_columns WHERE table_name = '{NAME}'"))
    session.commit()
    session.close()


def test_each_origin_is_asked_through_the_input_row_index(db):
    sent = []
    listener = lambda conn, cursor, statement, *a: sent.append(statement)       # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        got = [cell[1:] for cell in lines.stamped_by(db, [NAME], ["o1", "o2", "o1"])]
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert sorted(got) == [("r1", "lot", "chain_ingestion", "o1"), ("r1", "qty", "chain_ingestion", "o1"),
                           ("r2", "lot", "chain_ingestion", "o2")]
    assert any("CROSS JOIN LATERAL" in s and "OFFSET 0" in s for s in sent)
    index = db.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = :n AND schemaname = current_schema()"),
                       {"n": f"{NAME}__lines_i"}).scalar()
    assert "input_row IS NOT NULL" in index
