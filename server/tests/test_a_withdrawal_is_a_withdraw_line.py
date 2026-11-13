# -*- coding: utf-8 -*-
"""Taking a source's claim back is a withdraw line (cell-source overhaul, lead 11-11: the write of a withdrawal is
write_lines' withdraw; the claims are read by C's layer reader). The layers here are handed to the withdrawal's write
(`_withdraw_cells`), as `withdraw_layers` and `withdraw_source` hand them.

    reveal    the cell shows the next source's value; counted revealed, one withdraw line
    empty     the only source taken back leaves the cell empty; counted emptied
    pinned    a cell a person pinned to that source is skipped and counted, its value stays
    dry run   the same counts, nothing written - no line, the value as it was
"""
import pytest
from sqlalchemy import select

from chain import cell_layer
from database import crud, lines, models, schemas
from database.database import Base
from test_write_lines_writes_a_line_a_change_and_its_current_line import ticking_clock

TABLE = "wd_line"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.commit()
    ticking_clock(monkeypatch)
    for source, value in (("f1.csv", "one"), ("f2.csv", "two")):
        crud.apply_batch_updates(db_session, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            business_key_val="K1", updates={"k": "K1", "a": value}, source_name=source, updated_by="loader")]))
    return db_session


def _row(db):
    model = models.DYNAMIC_TABLES[TABLE]
    return db.query(model).filter(model.business_key_val == "K1").one()


def _withdraw_lines(db):
    ln = lines.shape(db, TABLE, CFG)["lines"]
    return db.execute(select(ln.c.source_name).where(ln.c.line_kind == "withdraw")).scalars().all()


def _take(db, source, apply=True):
    """The withdrawal's write over claims in hand - what `withdraw_layers` and `withdraw_source` hand it."""
    claims = {(_row(db).row_id, "a"): [source]}
    return cell_layer._withdraw_cells(db, TABLE, cell_layer.resolve_target(TABLE, ["a"]), cell_layer._pages_of(claims),
                                      apply=apply)


def test_taking_back_the_shown_source_reveals_the_next(db):
    assert _row(db).a == "two", "canary: the newer file shows"
    stats = _take(db, "f2.csv")
    db.expire_all()
    assert (_row(db).a, stats["cells_withdrawn"], stats["revealed"], stats["emptied"]) == ("one", 1, 1, 0), stats
    assert _withdraw_lines(db) == ["f2.csv"]


def test_taking_back_every_source_leaves_the_cell_empty(db):
    _take(db, "f2.csv")
    stats = _take(db, "f1.csv")
    db.expire_all()
    assert (_row(db).a, stats["emptied"]) == (None, 1), stats


def test_a_cell_pinned_to_the_source_is_skipped(db):
    db.add(models.CellOverwrite(table_name=TABLE, row_id=_row(db).row_id, column_name="a", is_overwrite=False,
                                updated_by="kim", manual_priority_source="f2.csv"))     # a person's pin, as stored
    db.commit()
    stats = _take(db, "f2.csv")
    db.expire_all()
    assert (_row(db).a, stats["pinned_skipped"], stats["cells_withdrawn"], _withdraw_lines(db)) == ("two", 1, 0, []), \
        stats


def test_a_dry_run_counts_the_same_and_writes_nothing(db):
    stats = _take(db, "f2.csv", apply=False)
    db.expire_all()
    assert (stats["cells_withdrawn"], stats["revealed"], _row(db).a, _withdraw_lines(db)) == (1, 1, "two", []), stats
