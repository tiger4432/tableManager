# -*- coding: utf-8 -*-
"""R2's preview (`replay.count_withdrawable`) says what the run (`withdraw_source`) withdraws - same fixture, per cell
(lead 11-11). A line says several columns, and past 64 columns its bits sit in a later chunk: a count of lines, or a
row judgement that reads chunk 0 only, answered another number than the run.

    one source on a row          3 cells, the row is a shell and goes
    another source beside it     3 cells, the row stays
    a cell pinned to the source  skipped, counted pinned
    a pin on a cell it never said  nothing
"""
import pytest

from chain import replay
from database import crud, lines, models, schemas
from database.database import Base
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE, SOURCE, OTHER = "wd_preview", "s.csv", "f.csv"
PAD = {f"p{i:02d}": "string" for i in range(64)}     # first, so k · a · b · c take bits 64.. (chunk 1)


@pytest.fixture(name="db", params=["small", "wide"])
def fixture_db(request, db_session, monkeypatch):
    types = {**(PAD if request.param == "wide" else {}), "k": "string", "a": "string", "b": "string", "c": "string"}
    cfg = {"composite_key_source": ["k"], "column_types": types}
    models.init_dynamic_models({TABLE: cfg})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, cfg)
    Base.metadata.create_all(bind=db_session.get_bind())
    bits = lines.ensure_line_table(db_session, TABLE, cfg)["bits"]
    assert (min(bits[c] for c in "kabc") >= 64) == (request.param == "wide"), "canary: the columns' chunk"
    db_session.commit()
    ticking_clock(monkeypatch)

    def put(source, key, **values):
        crud.apply_batch_updates(db_session, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            business_key_val=key, updates={"k": key, **values}, source_name=source, updated_by="loader")]))

    put(SOURCE, "K1", a="1", b="1")                     # only the source - a shell after
    put(SOURCE, "K2", a="2", b="2")
    put(OTHER, "K2", a="x", c="x")
    put(SOURCE, "K3", a="3")
    put(OTHER, "K3", a="y")
    put(OTHER, "K4", a="z")
    rows = {r.business_key_val: r.row_id for r in db_session.query(models.DYNAMIC_TABLES[TABLE])}
    for key, col in (("K3", "a"), ("K2", "c")):          # a pin on a claimed cell · on a cell the source never said
        db_session.add(models.CellOverwrite(table_name=TABLE, row_id=rows[key], column_name=col, is_overwrite=False,
                                            updated_by="kim", manual_priority_source=SOURCE))
    db_session.commit()
    return db_session


def test_the_preview_counts_what_the_run_withdraws(db):
    preview = replay.count_withdrawable(db, TABLE, SOURCE)
    run = replay.withdraw_source(db, TABLE, SOURCE, apply=True, log=lambda m: None)

    assert preview["cells_claimed"] == run["cells_matched"], (preview, run)
    assert preview["pinned"] == run["pinned_skipped"], (preview, run)
    assert preview["cells_claimed"] - preview["pinned"] == run["cells_withdrawn"], (preview, run)
    assert preview["rows_emptied"] == run["rows_deleted"], (preview, run)
    assert (run["cells_matched"], run["pinned_skipped"], run["rows_deleted"]) == (8, 1, 1), "canary: the fixture"
