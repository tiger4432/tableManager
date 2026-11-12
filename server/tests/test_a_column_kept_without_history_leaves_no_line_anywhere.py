"""A column its table keeps no history for (`no_history_columns`, owner 11-09 ㄴ) leaves no history line, whoever
writes it (lead 11-09 ㅁ''') - not stored, not in the lines the write hands back. The two seats ask one judgement, `crud.keeps_history`: `create_audit_log` (a cell's line) and
`crud._said_logs` (the columns a row's line names). A plain column beside it is the control: every writer leaves
its line there.

    writer × column        stored · handed back
    a machine's write      state: none         plain: the row's line naming it alone
    a person's write       state: none         plain: the cell's line
    a priority pin         state: refused      plain: the cell's line
    a layer deleted        state: refused      plain: the cell's line
    a collision merge      state: none         plain: the cell's line
    a file's blank         state: t blank      plain: dropped, as any machine's blank
    a state cell blanked   test_the_system_catalogue_keeps_each_parts_state_pg (the queue draining, PostgreSQL)
    the replay's lines     test_fold_units_leaves_what_the_chain_leaves_pg

A no-history column keeps no layers: its value is t's, the last write's, a blank included; a pin or a layer removal
on it is refused by name (lead 11-12 안 1)."""
import uuid

import pytest

from sqlalchemy import text

from database import crud, lines, models, schemas
from database.database import Base
from tests.support import line_tables

TABLE = "gauges"
CONFIG = {"business_key": "gauge_id", "no_history_columns": ["reading"],
          "column_types": {"gauge_id": "string", "reading": "string", "note": "string"}}
MERGED = "xscope_safe_map"                    # conftest's: its composite key lets one edit land on another row's key


@pytest.fixture
def db(db_session, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CONFIG)
    models.init_dynamic_models({TABLE: CONFIG})
    Base.metadata.create_all(bind=db_session.get_bind(), tables=[models.DYNAMIC_TABLES[TABLE].__table__])
    line_tables.build(db_session.get_bind(), TABLE)                      # the product's shape: a table keeps lines
    _write(db_session, {"gauge_id": "G1", "note": "a", "reading": "1"}, "a.csv")
    _write(db_session, {"gauge_id": "G1", "note": "b", "reading": "2"}, "b.csv")
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
    line_tables.build(db.get_bind(), MERGED)

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


def _stored(db, table, after):
    """The cells of `table`'s lines after line `after`, each as (column, value text) - the overhaul's record (t__lines;
    audit_logs takes no write - lead 11-11)."""
    if db.get_bind().dialect.name != "sqlite" and not lines.has_lines(db, table):
        return []
    bits = lines.bit_map(db, table)
    found = db.execute(text('SELECT * FROM "%s" WHERE line_id > :after ORDER BY line_id' % lines.lines_relation(table)),
                       {"after": after}).mappings().all()
    return [(c, line[lines.value_column(c)]) for line in found for c, bit in sorted(bits.items(), key=lambda cb: cb[1])
            if (line["written_%d" % (bit // 64)] & ((1 << 64) - 1)) >> (bit % 64) & 1]


def _lines(db, writer, column, monkeypatch):
    """(stored, handed back) of the writer's cells in `column` (the merge's: `bn`) - each as (column, new value); a
    handed row line (ROW_UPDATE) as it is."""
    table = MERGED if writer is merge else TABLE
    if writer is merge and column == "reading":                           # the merge writes `bn`: kept or not
        monkeypatch.setitem(crud.TABLE_CONFIG[MERGED], "no_history_columns", ["bn"])
    after = db.execute(text('SELECT coalesce(max(line_id), 0) FROM "%s"' % lines.lines_relation(table))).scalar()         if writer is not merge else 0                                     # the merge builds its table's lines afresh
    handed = writer(db, column)
    db.expire_all()
    asked = "bn" if writer is merge else column
    stored = [cell for cell in _stored(db, table, after) if cell[0] == asked]
    handed = [(line["column_name"], line["new_value"]) for line in handed]
    if writer is merge:                                                  # the edit's own `cx` line is a plain one
        return stored, [line for line in handed if line[0] == "bn"]
    return stored, handed


@pytest.mark.parametrize("name", [name for name, writer in WRITERS.items() if writer not in (pin, delete)])
def test_a_column_kept_without_history_leaves_no_line_whoever_writes_it(db, name, monkeypatch):
    shown = _row(db).reading
    assert _lines(db, WRITERS[name], "reading", monkeypatch) == ([], [])
    if WRITERS[name] is not merge:
        assert _row(db).reading != shown, "CANARY: the writer moved the cell"


@pytest.mark.parametrize("name", WRITERS)
def test_a_plain_column_keeps_its_line_whoever_writes_it(db, name, monkeypatch):
    stored, handed = _lines(db, WRITERS[name], "note", monkeypatch)
    if WRITERS[name] is pin:
        # a pin says no value: its line is a mark that names no cell (lead 11-12 ㄱ - written bits mean «this line says a
        # value»); the pin itself is cell_overwrites', the carried line names the cell
        marks = db.execute(text('SELECT count(*) FROM "%s" WHERE line_kind = :k' % lines.lines_relation(TABLE)),
                           {"k": "mark"}).scalar()
        assert (stored, bool(handed), marks) == ([], True, 1), (stored, handed, marks)
        return
    assert stored and handed, (name, stored, handed)
    named = {column for column, _value in stored + handed}
    assert named <= {"note", "bn", "ROW_UPDATE"}, named
    assert not [value for _c, value in stored + handed if "reading" in str(value)]


@pytest.mark.parametrize("name, said", [("a priority pin", "no layers to pin"),
                                        ("a layer deleted", "no layers to take a source off")])
def test_a_pin_or_a_layer_removal_on_a_column_of_no_history_is_refused_by_name(db, name, said):
    table = lines.lines_relation(TABLE)
    before = (_row(db).reading, db.execute(text('SELECT count(*) FROM "%s"' % table)).scalar())
    with pytest.raises(crud.ReadOnlyRelation) as refused:                # the route answers it 422 with its reason
        WRITERS[name](db, "reading")
    db.rollback()
    assert "'reading' of 'gauges' keeps no history - " + said in str(refused.value), str(refused.value)
    assert (_row(db).reading, db.execute(text('SELECT count(*) FROM "%s"' % table)).scalar()) == before == ("2", 2)


@pytest.mark.parametrize("column, shown", [("reading", None), ("note", "b")])
def test_a_files_blank_clears_a_column_of_no_history_and_is_dropped_on_one_that_keeps_it(db, column, shown):
    assert getattr(_row(db), column) == ("2" if column == "reading" else "b"), "CANARY: the fixture wrote the cell"
    _write(db, {"gauge_id": "G1", column: ""}, "c.csv")
    db.expire_all()
    assert getattr(_row(db), column) == shown
