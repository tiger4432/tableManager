# -*- coding: utf-8 -*-
"""A deleted row's lines stay - its history (owner «메인 표가 곧 이력») - so the cells a source row fed still name it
(`cells_stamped_by` reads lines, no join to t: settle is on the write path, lead 11-11). What the withdrawal says it
took (`lost_a_layer`, the rows the delete path tells the rules with an EDIT) is what write_lines took back - a deleted
row's withdraw it leaves out, so the deleted row is not told. sqlite."""
import pytest

from chain import cell_layer
from database import crud, lines, models
from database.database import Base
from database.write_lines import write_lines
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE = "dr_told"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.commit()
    ticking_clock(monkeypatch)
    return db_session


def test_a_deleted_rows_cells_are_asked_but_not_told(db):
    fed = write_lines(db, TABLE, [{"key": {"k": key}, "values": {"k": key, "a": "x"}, "source_name": crud.CHAIN_SOURCE,
                                   "written_by": "rule1", "input_row": "o1"} for key in ("K1", "K2")],
                      kind="chain", transaction_id="tx1")
    gone, kept = [item["row_id"] for item in fed["items"]]
    write_lines(db, TABLE, [{"row_id": gone, "line_kind": "deleted", "source_name": "user", "written_by": "kim"}],
                kind="funnel", transaction_id="tx2")
    asked = cell_layer.cells_stamped_by(db, TABLE, ["o1"])
    assert {row for _t, row, *_ in asked} == {gone, kept}, "canary: the deleted row's lines still name its cells"
    stats = cell_layer.withdraw_layers(db, asked, apply=True)
    assert stats["lost_a_layer"][TABLE][1] == {kept}
    assert stats["cells_withdrawn"] == 2
