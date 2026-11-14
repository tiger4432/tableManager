# -*- coding: utf-8 -*-
"""14c (lead 11-14, owner «추천대로»): a table built before 08-31 keeps the retired graph columns (21e9df3d6), and an
install may hold other columns its declaration no longer names. 14b bound them as varchar and its array write failed
(«is_graph_synced is boolean but expression is character varying», the box copy's 500). Now: the retired ones are not
data (lines.NOT_DATA) and are never bound; any other leftover is bound with its stored type (lines.stored_columns).

    a person's new row · a person's moved value · a file batch (array INSERT and UPDATE)   no error
    the leftover cells of a row a write moves                                              unchanged
    t__lines' value cells                                     text; none for a retired column"""
import pytest
from sqlalchemy import event, text

from database import crud, models, schemas
from tests.support import line_tables

pytestmark = pytest.mark.pg

TABLE = "zz_pre0831"
CFG = {"business_key": "k", "column_types": {"k": "string", "v": "string", "n": "number"}}
#: as an 08-31-era install holds them: the retired three, and leftovers no declaration names any more
LEFTOVERS = (("is_graph_synced", "boolean"), ("needs_graph_rollback", "boolean"), ("graph_synced_at", "timestamptz"),
             ("old_json", "jsonb"), ("eventtime", "character varying"))
PLANTED = "true, false, '2026-08-01 10:00+00', '{\"a\": [1, 2]}'::jsonb, '2026-08-01 10:00'"


def _write(db, items, said=None):
    listen = (lambda conn, cursor, statement, *a: said.append(" ".join(statement.split()))) if said is not None else None
    if listen:
        event.listen(db.get_bind(), "before_cursor_execute", listen)
    try:
        crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            business_key_val=key, updates=values, source_name=source, updated_by="gate") for key, values, source in items]))
        db.commit()
    finally:
        if listen:
            event.remove(db.get_bind(), "before_cursor_execute", listen)


def _leftovers(db, key):
    return db.execute(text('SELECT %s FROM "%s" WHERE business_key_val = :k' % (
        ", ".join(name for name, _ in LEFTOVERS), TABLE)), {"k": key}).one()


@pytest.fixture(name="old")
def fixture_old(pg_session, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    models.init_dynamic_models({TABLE: CFG})
    engine = pg_session.get_bind()
    db = pg_session
    # the order an install meets: t holds the leftovers before the upgrade's boot builds its lines
    models.DYNAMIC_TABLES[TABLE].__table__.create(bind=engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE "%s" %s' % (TABLE, ", ".join("ADD COLUMN %s %s" % c for c in LEFTOVERS))))
    line_tables.build(engine, TABLE)
    try:
        _write(db, [("K0", {"k": "K0", "v": "a", "n": 1}, "user")] +
               [("F%03d" % i, {"k": "F%03d" % i, "v": "f", "n": i}, "old.csv") for i in range(300)])
        db.execute(text('UPDATE "%s" SET (%s) = (%s)' % (TABLE, ", ".join(n for n, _ in LEFTOVERS), PLANTED)))
        db.commit()
        yield db
    finally:
        db.rollback()
        line_tables.drop(engine, TABLE)
        models.DYNAMIC_TABLES[TABLE].__table__.drop(bind=engine, checkfirst=True)


def test_the_canary_the_table_holds_the_leftovers_with_their_old_types(old):
    got = dict(old.execute(text("SELECT column_name, data_type FROM information_schema.columns "
                                "WHERE table_schema = current_schema() AND table_name = :t"), {"t": TABLE}).all())
    for name, kind in LEFTOVERS:
        assert got[name].startswith(kind.split(" ")[0].replace("timestamptz", "timestamp")), (name, got[name])


def test_a_persons_new_row_goes_in(old):
    _write(old, [("K1", {"k": "K1", "v": "b", "n": 2}, "user")])
    assert old.execute(text('SELECT v FROM "%s" WHERE business_key_val = \'K1\'' % TABLE)).scalar() == "b"
    assert _leftovers(old, "K1") == (None,) * len(LEFTOVERS)


def test_a_persons_moved_value_keeps_the_leftover_cells(old):
    before = _leftovers(old, "K0")
    _write(old, [("K0", {"v": "moved"}, "user")])
    assert old.execute(text('SELECT v FROM "%s" WHERE business_key_val = \'K0\'' % TABLE)).scalar() == "moved"
    assert _leftovers(old, "K0") == before


def test_a_file_batch_goes_through_both_array_statements(old):
    before = _leftovers(old, "F007")
    said = []
    _write(old, [("F%03d" % i, {"k": "F%03d" % i, "v": "g", "n": i + 1}, "new.csv") for i in range(300)] +
           [("N%03d" % i, {"k": "N%03d" % i, "v": "n", "n": i}, "new.csv") for i in range(300)], said)
    insert = [s for s in said if s.startswith('INSERT INTO "%s" ' % TABLE)]
    update = [s for s in said if s.startswith('UPDATE "%s" ' % TABLE)]
    assert insert and all("unnest(" in s for s in insert), insert[:1]
    assert update and any("unnest(" in s for s in update), update[:1]
    assert old.execute(text('SELECT count(*) FROM "%s" WHERE v IN (\'g\', \'n\')' % TABLE)).scalar() == 600
    assert _leftovers(old, "F007") == before


def test_the_line_cells_stay_text_and_a_retired_column_has_none(old):
    _write(old, [("K0", {"v": "again"}, "user")])
    cells = dict(old.execute(text("SELECT column_name, data_type FROM information_schema.columns "
                                  "WHERE table_schema = current_schema() AND table_name = :t AND column_name LIKE 'v\\_%%'"),
                             {"t": TABLE + "__lines"}).all())
    assert cells and set(cells.values()) <= {"character varying", "text"}, cells
    from database import lines
    assert not {"v_" + name for name in lines.RETIRED} & set(cells), cells          # not data: no slot
    assert {"v_old_json", "v_eventtime"} <= set(cells), cells           # a leftover is data, text
