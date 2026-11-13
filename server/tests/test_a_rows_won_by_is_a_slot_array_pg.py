# -*- coding: utf-8 -*-
"""t.won_by is a bigint array by bit slot (lead 11-13 안 1): the R0 marathon read t as 2.4x main's width (avg row
1,177 vs 494 B on one seed) - won_by spelled every winning column's name in JSONB. A 30-column row's won_by is now
the slots' line_ids; the same winners in the old spelling are measured beside it."""
import json

import pytest
from sqlalchemy import text

from database import crud, lines, models, schemas
from tests.support import line_tables

pytestmark = pytest.mark.pg

TABLE = "zz_won_wide"
COLS = ["c%02d" % i for i in range(29)]
CFG = {"business_key": "k", "column_types": {"k": "string", **{c: ("number" if i % 3 == 0 else "string")
                                                                for i, c in enumerate(COLS)}}}
#: bytes of a 30-column row's won_by as slots - measured on PG 11-13 (264 B; the same winners as JSONB names 576 B
#: here, 684 B a row on the R3 marathon's names)
MEASURED = 264


def test_a_30_column_rows_won_by_is_its_slots(pg_session, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    models.init_dynamic_models({TABLE: CFG})
    engine = pg_session.get_bind()
    line_tables.build(engine, TABLE)
    try:
        crud.apply_batch_updates(pg_session, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            business_key_val="K1", updates={"k": "K1", **{c: (n if n % 3 == 0 else "v%d" % n) for n, c in enumerate(COLS)}},
            source_name="f1.csv", updated_by="probe")]))
        pg_session.commit()
        row_id, size = pg_session.execute(text('SELECT row_id, pg_column_size(won_by) FROM "%s"' % TABLE)).one()
        won = lines.won_by_of(pg_session, TABLE, [row_id])[row_id]
        assert sorted(won) == sorted(["k"] + COLS), "CANARY: the row names a winner a column"
        named = pg_session.execute(text("SELECT pg_column_size(CAST(:j AS jsonb))"), {"j": json.dumps(won)}).scalar()
        print("\n==== won_by %d B as slots, %d B as JSONB names" % (size, named))
        assert size <= MEASURED and size * 2 < named, (size, named)
    finally:
        pg_session.rollback()
        line_tables.drop(engine, TABLE)
        models.DYNAMIC_TABLES[TABLE].__table__.drop(bind=engine, checkfirst=True)
