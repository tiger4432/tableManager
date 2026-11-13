# -*- coding: utf-8 -*-
"""A merge re-decides only the cells its write touched (lead 11-12; main re-decided those alone): a pin its pinned
cells, a merge-again mark its blanks, a mark that names cells (a notation fold's re-merge) those cells, a key merge's
holder the columns the shell's lines spoke and the merge's own. A cell whose t value disagrees with its lines (as a
migrated one may) keeps its value through each - it flips only when that column is written."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from conftest import retire_dynamic_model
from database import crud, models, schemas, write_lines
from database.database import Base

TABLE = "zz_touched_only"
COLUMNS = {"k": "string", "job": "string", "a": "string", "b": "string"}
CONFIG = {TABLE: {"business_key": "k", "composite_key_source": ["job"], "column_types": COLUMNS,
                  "display_columns": list(COLUMNS)}}


@pytest.fixture(name="db")
def fixture_db():
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(TABLE)
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CONFIG)
    crud.TABLE_CONFIG.update(CONFIG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    from tests.support import line_tables

    line_tables.build(engine, TABLE)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(TABLE)


def _write(db, updates, source, row_id=None):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source, updated_by="probe")]))
    db.commit()


def _row(db, job):
    db.expire_all()
    return db.query(models.DYNAMIC_TABLES[TABLE]).filter_by(job=job).one()


def _off_its_lines(db, job, column, value):
    """t says `value` in `column` where its lines say otherwise - a cell a migration copied out of step."""
    db.execute(text('UPDATE "%s" SET "%s" = :v WHERE job = :j' % (TABLE, column)), {"v": value, "j": job})
    db.commit()
    assert getattr(_row(db, job), column) == value, "CANARY: t disagrees with its lines"


def test_a_pin_re_decides_its_cell_alone(db):
    _write(db, {"job": "J1", "a": "1", "b": "1"}, "f1.csv")
    _write(db, {"job": "J1", "a": "2"}, "f2.csv")
    row_id = _row(db, "J1").row_id
    _off_its_lines(db, "J1", "b", "X")
    crud.set_cell_manual_priority_batch(db, TABLE, [{"row_id": row_id, "column_name": "a"}], "f1.csv", "op")
    db.commit()
    row = _row(db, "J1")
    assert (row.a, row.b) == ("1", "X")


def test_a_merge_again_mark_re_decides_its_blanks_and_a_naming_mark_its_cells(db):
    _write(db, {"job": "J1", "a": "1", "b": "1"}, "f1.csv")
    row_id = _row(db, "J1").row_id
    _off_its_lines(db, "J1", "a", "Y")
    _off_its_lines(db, "J1", "b", "X")
    write_lines.write_lines(db, TABLE, [{"row_id": row_id, "line_kind": "mark", "columns": []}], kind="mark",
                            transaction_id="again")
    db.commit()
    assert (_row(db, "J1").a, _row(db, "J1").b) == ("Y", "X"), "a merge-again mark that names nothing moves nothing"
    write_lines.write_lines(db, TABLE, [{"row_id": row_id, "line_kind": "mark", "columns": [], "scope": ["a"],
                                         "source_name": "notation_backfill", "written_by": "notation_backfill"}],
                            kind="mark", transaction_id="named")
    db.commit()
    assert (_row(db, "J1").a, _row(db, "J1").b) == ("1", "X"), "a re-merge scoped to a re-decides a alone"


def test_a_re_merge_where_nothing_moves_writes_no_line_and_no_audit_row(db, monkeypatch):
    """A notation fold's re-merge is a merge-again mark with a scope (lead 11-12): no line, an audit row only when a
    shown value moves - over 1,000 rows where none does, nothing - and the merge decides its scope alone."""
    from database import lines

    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"job": "J%d" % i, "a": "1", "b": "1"}, source_name="f1.csv",
                                  updated_by="probe") for i in range(1000)]))
    db.commit()
    rows = [r for (r,) in db.query(models.DYNAMIC_TABLES[TABLE].row_id)]
    count = lambda sql: db.execute(text(sql)).scalar()                    # noqa: E731
    before = (count('SELECT count(*) FROM "%s"' % lines.lines_relation(TABLE)), count("SELECT count(*) FROM audit_batches"))
    asked, merge = [], lines.merge
    monkeypatch.setattr(lines, "merge", lambda *a, **k: asked.append(k.get("columns")) or merge(*a, **k))
    write_lines.write_lines(db, TABLE, [{"row_id": r, "line_kind": "mark", "columns": [], "scope": ["a"],
                                         "source_name": "notation_backfill", "written_by": "notation_backfill"}
                                        for r in rows], kind="mark", transaction_id="re-merge")
    db.commit()
    assert len(rows) == 1000 and before[0] == 1000, "CANARY: a line a row"
    assert (count('SELECT count(*) FROM "%s"' % lines.lines_relation(TABLE)), count("SELECT count(*) FROM audit_batches"),
            asked) == (before[0], before[1], [{"a"}])


def test_a_key_merge_re_decides_what_the_shell_brought_alone(db):
    _write(db, {"job": "J1", "a": "1", "b": "1"}, "f1.csv")
    _write(db, {"job": "J2", "a": "2"}, "f2.csv")
    _off_its_lines(db, "J1", "b", "X")
    shell = _row(db, "J2").row_id
    _write(db, {"job": "J1"}, crud.USER_SOURCE, row_id=shell)        # the shell lands on the holder's key: merged
    holder = _row(db, "J1")
    assert db.query(models.DYNAMIC_TABLES[TABLE]).count() == 1, "CANARY: the rows merged"
    assert holder.b == "X", "b - the shell never spoke it - keeps the holder's value"
