"""총괄 5c0a86cec (owner 10-20 «키쪽같은거 리턴해도 새행 생성»): a key handed back in another shape names the row
that holds it - one row, the second write lands on it. The shapes that made a second row (or, under `uq_bk_`, a
refused write):

  ① a plain key only in the key column, no `business_key_val`
  ② a number key sent as 1.0 against a stored '1' (the prefetch asked '1.0' and «proved» it absent)
  ③ a number key sent as the text '1.0' (a plain key was not spelled as its column stores it)
  ④ a composite table's key column only, no parts

and beside them: a row stored under an old spelling is found by it and re-keyed (판정 191); a key sent beside a
different key column value still wins (총괄: unchanged).
"""
import os
import sys

import pytest
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import key_gate                                    # noqa: E402
from database.database import Base                            # noqa: E402
from database import crud, models, schemas                    # noqa: E402

PLAIN, NUMKEY, COMP = "zzsamekey_plain", "zzsamekey_numkey", "zzsamekey_comp"
CFG = {
    PLAIN: {"business_key": "unit_id", "column_types": {"unit_id": "string", "payload": "string"}},
    NUMKEY: {"business_key": "unit_no", "column_types": {"unit_no": "number", "payload": "string"}},
    COMP: {"business_key": "map_pk", "composite_key_source": ["map_id", "die_no"], "composite_key_separator": "_",
           "column_types": {"map_pk": "string", "map_id": "string", "die_no": "string", "payload": "string"}},
}
SHAPES = [
    ("1_key_column_only", PLAIN, dict(business_key_val="K1", updates={"unit_id": "K1", "payload": "a"}),
     dict(updates={"unit_id": "K1", "payload": "b"}), "K1"),
    ("2_number_as_float", NUMKEY, dict(business_key_val="1", updates={"unit_no": "1", "payload": "a"}),
     dict(business_key_val=1.0, updates={"unit_no": 1.0, "payload": "b"}), "1"),
    ("3_number_as_text", NUMKEY, dict(business_key_val="1", updates={"unit_no": "1", "payload": "a"}),
     dict(business_key_val="1.0", updates={"unit_no": "1.0", "payload": "b"}), "1"),
    ("4_composite_key_column_only", COMP, dict(updates={"map_id": "M1", "die_no": "3", "payload": "a"}),
     dict(updates={"map_pk": "M1_3", "payload": "b"}), "M1_3"),
]


def _push(db, table, **item):
    item.setdefault("source_name", "chain_ingestion")
    item.setdefault("updated_by", "rule_x")
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(**item)]))
    db.commit()


def _rows(db, table):
    return [(r.business_key_val, r.payload) for r in db.query(models.DYNAMIC_TABLES[table]).all()]


@pytest.fixture(name="db")
def fixture_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CFG)
    crud.TABLE_CONFIG.update(CFG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.parametrize("name,table,first,second,key", SHAPES, ids=[s[0] for s in SHAPES])
def test_the_second_write_lands_on_the_row(db, name, table, first, second, key):
    _push(db, table, **first)
    assert _rows(db, table) == [(key, "a")]                     # canary: the first write keyed the row
    _push(db, table, **second)
    assert _rows(db, table) == [(key, "b")], name


@pytest.mark.parametrize("old", ["1.0", "001"])
def test_a_row_under_an_old_spelling_is_found_by_it_and_re_keyed(db, old):
    """Found by the spelling it was stored under when that spelling arrives again (a file's text) - the
    arrived spelling moves aside (판정 191). A row whose old spelling never arrives again keeps it."""
    _push(db, NUMKEY, business_key_val="1", updates={"unit_no": "1", "payload": "a"})
    db.execute(text("UPDATE %s SET business_key_val = :k" % NUMKEY), {"k": old})
    db.commit()
    assert _rows(db, NUMKEY) == [(old, "a")]
    _push(db, NUMKEY, business_key_val=old, updates={"unit_no": old, "payload": "b"})
    assert _rows(db, NUMKEY) == [("1", "b")]


def test_a_key_sent_beside_another_key_column_value_still_wins(db):
    _push(db, PLAIN, business_key_val="K1", updates={"unit_id": "K1", "payload": "a"})
    _push(db, PLAIN, business_key_val="K1", updates={"unit_id": "K2", "payload": "b"})
    assert _rows(db, PLAIN) == [("K1", "b")]


def test_the_chain_key_gate_keeps_a_composite_key_column_only_item(db):
    item = schemas.GeneralUpdateItem(updates={"map_pk": "M1_3", "payload": "b"})
    kept, report = key_gate.screen(COMP, [item])
    assert (len(kept), report["refused_rows"]) == (1, 0)


@pytest.mark.pg
@pytest.mark.parametrize("index", ["no_index", "uq_bk"])
@pytest.mark.parametrize("name,table,first,second,key", SHAPES, ids=[s[0] for s in SHAPES])
def test_on_postgresql_with_and_without_the_unique_index(pg_engine, index, name, table, first, second, key):
    from conftest import PG_TEST_SCHEMA, retire_dynamic_model

    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == PG_TEST_SCHEMA
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(table)
    models.init_dynamic_models({table: CFG[table]})
    crud.TABLE_CONFIG.update({table: CFG[table]})

    def clean():
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, table)))
            for side in ("cell_sources", "cell_overwrites", "database_outbox", "audit_logs"):
                conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, side)), {"t": table})

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[table].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    if index == "uq_bk":
        with pg_engine.begin() as conn:
            conn.execute(text('CREATE UNIQUE INDEX "uq_bk_%s" ON "%s"."%s" (business_key_val)'
                              % (table, PG_TEST_SCHEMA, table)))
    db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        _push(db, table, **first)
        assert _rows(db, table) == [(key, "a")]
        _push(db, table, **second)
        assert _rows(db, table) == [(key, "b")], name
    finally:
        db.rollback()
        db.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(table)
