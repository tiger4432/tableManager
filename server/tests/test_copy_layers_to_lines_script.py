"""The migration command (owner 11-11): a table copies to its end, a second run says «already copied», a page whose
copied lines do not give what t shows is rolled back and stops its table, naming the cell."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import lines
from database.models import CellOverwrite, CellSource, sql_type_of
from scripts import copy_layers_to_lines as script

CFG = {"column_types": {"lot": "string"}}
T1 = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)


def build(t_lot_r2):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource, CellOverwrite, CellSource):
        model.__table__.create(engine)
    with Session(bind=engine) as db:
        Table("t", MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(db.connection())
        db.execute(text("INSERT INTO t (row_id, business_key_val, lot) VALUES ('r1', 'k1', 'a'), ('r2', 'k2', :v)"),
                   {"v": t_lot_r2})
        for row_id, value in (("r1", "a"), ("r2", "b")):
            db.execute(CellSource.__table__.insert().values(table_name="t", row_id=row_id, column_name="lot",
                                                            source_name="fileA", value=value, ingested_at=T1,
                                                            updated_by="seed"))
        lines.ensure_line_table(db, "t", CFG)
        db.commit()
    return engine


def copied_rows(engine):
    with Session(bind=engine) as db:
        lt = lines.shape(db, "t", CFG)["lines"]
        return sorted(db.execute(select(lt.c.row_id).where(lt.c.batch == "copy_lines:t")).scalars().all())


def test_a_table_copies_to_its_end_and_a_second_run_says_already_copied():
    engine, said = build("b"), []
    first = script.copy_table(engine, "t", CFG, 1, say=said.append)
    assert (first["copied"], copied_rows(engine)) == (2, ["r1", "r2"])
    assert script.copy_table(engine, "t", CFG, 1, say=said.append) == {"table": "t", "already": True}
    assert said[-1].startswith("t: already copied")


def test_an_old_layer_table_without_the_owner_columns_is_refused_in_one_line():
    engine, said = build("b"), []
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE cell_sources DROP COLUMN owner_key"))
    out = script.copy_table(engine, "t", CFG, 1, say=said.append)
    assert out["stopped"] and copied_rows(engine) == []
    assert said == ["REFUSED - t: cell_sources has no owner_key - the copy reads them; this database cannot be copied"]


@pytest.mark.parametrize("page", [1, 2])
def test_a_page_whose_lines_do_not_give_t_is_rolled_back_and_stops_the_table(page):
    engine, said = build("not b"), []
    out = script.copy_table(engine, "t", CFG, page, say=said.append)
    assert out["stopped"] and [m[:2] for m in out["mismatched"]] == [("r2", "lot")]
    assert copied_rows(engine) == (["r1"] if page == 1 else [])      # the pages before it stay
    assert "STOPPED" in said[-1] and "r2.lot" in said[-1]
