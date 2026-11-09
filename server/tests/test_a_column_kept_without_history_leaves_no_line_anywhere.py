"""A column its table keeps no history for (`no_history_columns`, owner 11-09 ㄴ) leaves no history line, whoever
writes it (lead 11-09 ㅁ''') - not stored, not in the recent changes' cache (`GET /audit_logs/recent`), not in the lines
the write hands back. The two seats ask one judgement, `crud.keeps_history`: `create_audit_log` (a cell's line) and
`crud.row_update_line` (the columns a row's line names). A plain column beside it is the control: every writer leaves
its line there.

    writer × column        stored · cached · handed back
    a machine's write      state: none         plain: the row's line naming it alone
    a person's write       state: none         plain: the cell's line
    a priority pin         state: none         plain: the cell's line
    a layer deleted        state: none         plain: the cell's line
    a collision merge      state: none         plain: the cell's line
    a state cell blanked   test_the_system_catalogue_keeps_each_parts_state_pg (the queue draining, PostgreSQL)
    the replay's lines     test_fold_units_leaves_what_the_chain_leaves_pg"""
import uuid

import pytest

from admin.audit_cache import audit_cache
from database import crud, models, schemas
from database.database import Base

TABLE = "gauges"
CONFIG = {"business_key": "gauge_id", "no_history_columns": ["reading"],
          "column_types": {"gauge_id": "string", "reading": "string", "note": "string"}}
MERGED = "xscope_safe_map"                    # conftest's: its composite key lets one edit land on another row's key


@pytest.fixture
def db(db_session, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CONFIG)
    models.init_dynamic_models({TABLE: CONFIG})
    Base.metadata.create_all(bind=db_session.get_bind(), tables=[models.DYNAMIC_TABLES[TABLE].__table__])
    _write(db_session, {"gauge_id": "G1", "note": "a", "reading": "1"}, "a.csv")
    _write(db_session, {"gauge_id": "G1", "note": "b", "reading": "2"}, "b.csv")
    monkeypatch.setattr(audit_cache, "is_loaded", True)
    return db_session


def _write(db, updates, source, table=TABLE, row_id=None):
    _results, _cells, handed, _gone = crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(row_id=row_id, updates=updates, source_name=source, updated_by="t")]))
    db.commit()
    return handed


def _row(db):
    return db.query(models.DYNAMIC_TABLES[TABLE]).one()


def machine(db, column):
    return _write(db, {"gauge_id": "G1", column: "9"}, "c.csv")


def person(db, column):
    return _write(db, {"gauge_id": "G1", column: "9"}, "user")


def pin(db, column):
    _changed, handed, _gone = crud.set_cell_manual_priority_batch(
        db, TABLE, [{"row_id": _row(db).row_id, "column_name": column}], "a.csv", "op")
    return handed


def delete(db, column):
    _changed, handed = crud.delete_cell_source_batch(db, TABLE, [{"row_id": _row(db).row_id, "column_name": column}],
                                                     "b.csv")
    return handed


def merge(db, column):
    """Two rows one composite-key edit apart; the edit lands the shell on the other's key and the merge writes `bn`."""
    model = models.DYNAMIC_TABLES[MERGED]

    def add(cx, bn):
        key = crud.compose_business_key(MERGED, ["L1", 1, cx, 1], ["lot", "slot", "cx", "cy"])
        row = model(row_id=str(uuid.uuid4()), business_key_val=key, cell_key=key, lot="L1", slot=1, cx=cx, cy=1, bn=bn)
        db.add(row)
        return row

    add(1, "OLD")
    shell = add(2, "NEW")
    db.commit()
    return _write(db, {"cx": 1}, "user", table=MERGED, row_id=shell.row_id)


WRITERS = {"a machine's write": machine, "a person's write": person, "a priority pin": pin, "a layer deleted": delete,
           "a collision merge": merge}


def _lines(db, writer, column, monkeypatch):
    """(stored, cached, handed back) - the lines the writer left, each as (column, new value)."""
    table = MERGED if writer is merge else TABLE
    if writer is merge and column == "reading":                           # the merge writes `bn`: kept or not
        monkeypatch.setitem(crud.TABLE_CONFIG[MERGED], "no_history_columns", ["bn"])
    before = db.query(models.AuditLog.id).order_by(models.AuditLog.id.desc()).limit(1).scalar() or 0
    given = []                                     # every line handed to the cache - a group shows its newest alone
    many, one = audit_cache.add_logs_batch, audit_cache.add_log
    monkeypatch.setattr(audit_cache, "add_logs_batch", lambda logs, *a, **k: (given.extend(logs), many(logs, *a, **k)))
    monkeypatch.setattr(audit_cache, "add_log", lambda log: (given.append(log), one(log)))
    handed = writer(db, column)
    db.expire_all()
    stored = [(line.column_name, line.new_value) for line in db.query(models.AuditLog).filter(
        models.AuditLog.table_name == table, models.AuditLog.id > before).order_by(models.AuditLog.id)]
    cached = [(line["column_name"], line["new_value"]) for line in given]
    handed = [(line["column_name"], line["new_value"]) for line in handed]
    if writer is merge:                                                  # the edit's own `cx` line is a plain one
        return tuple([line for line in lines if line[0] == "bn"] for lines in (stored, cached, handed))
    return stored, cached, handed


@pytest.mark.parametrize("name", WRITERS)
def test_a_column_kept_without_history_leaves_no_line_whoever_writes_it(db, name, monkeypatch):
    shown = _row(db).reading
    assert _lines(db, WRITERS[name], "reading", monkeypatch) == ([], [], [])
    if WRITERS[name] is not merge:
        assert _row(db).reading != shown, "CANARY: the writer moved the cell"


@pytest.mark.parametrize("name", WRITERS)
def test_a_plain_column_keeps_its_line_whoever_writes_it(db, name, monkeypatch):
    stored, cached, handed = _lines(db, WRITERS[name], "note", monkeypatch)
    assert stored and cached and handed, (name, stored, cached, handed)
    named = {column for column, _value in stored + cached + handed}
    assert named <= {"note", "bn", "ROW_UPDATE"}, named
    assert not [value for _c, value in stored + cached + handed if "reading" in str(value)]
