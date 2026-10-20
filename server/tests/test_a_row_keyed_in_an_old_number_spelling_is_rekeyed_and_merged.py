"""Owner 10-20 («체인 아직도 복제» · 1st priority, lead): a row stored under an old NUMBER spelling of its key («1.0» ·
«001») is re-keyed to the one spelling by the write fold (`replay.fold_written_notation`, the Admin op «Fold stored
values into the declared spelling»), and rows that meet on it are merged through the write door's merge
(`crud.merge_into_key_holders`). After it a chain handing the key back as 1 finds the row - no new row.

  '1.0' + '1'   one row '1'      '001' + '1'   one row '1'      '1.0' alone   re-keyed '1'
  a text key '001'   untouched (letters are the key)      a composite «M1_1.0» + «M1_1»   one row «M1_1»
  two rows storing one key as spelled («7» · «7», lead 10-20)   one row - in a number key and in a text key
SQLite takes the row path; PostgreSQL the by-value page. After a run that merged, the Admin op builds the table's
business-key unique index - only on PostgreSQL's public schema, where the builder reads.
"""
import os
import sys

import pytest
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import replay                                              # noqa: E402
from database.database import Base                                    # noqa: E402
from database import crud, models, schemas                            # noqa: E402

NUM, TXT, COMP = "zz_respell_num", "zz_respell_txt", "zz_respell_comp"
CFG = {
    NUM: {"business_key": "unit_no", "column_types": {"unit_no": "number", "payload": "string"}},
    TXT: {"business_key": "code", "column_types": {"code": "string", "payload": "string"}},
    COMP: {"composite_key_source": ["map_id", "die_no"], "composite_key_separator": "_",
           "column_types": {"map_id": "string", "die_no": "number", "payload": "string"}},
}


def _write(db, table, **updates):
    key = CFG[table].get("business_key")
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=updates.get(key) if key else None, updates=updates,
        source_name="chain_ingestion", updated_by="rule_x")]))
    db.commit()


def _twin(db, table, column, value, payload, key):
    """A second row storing a key another row stores - what a table without its unique index can hold."""
    db.execute(text("UPDATE %s SET %s = :v, business_key_val = :k WHERE payload = :p" % (table, column)),
               {"v": value, "k": key, "p": payload})
    db.commit()


def _old(db, table, payload, key):
    """What a row written before the one spelling carries: its key as the payload spelled it."""
    db.execute(text("UPDATE %s SET business_key_val = :k WHERE payload = :p" % table), {"k": key, "p": payload})
    db.commit()


def _rows(db, table):
    return sorted((r.business_key_val, r.payload) for r in db.query(models.DYNAMIC_TABLES[table]).all())


def _scenarios(db):
    # number key: '1.0' + '1' meet; '001' + '1' meet; '1.0' alone is only re-keyed
    _write(db, NUM, unit_no=1, payload="kept")
    _write(db, NUM, unit_no=2, payload="old_1.0")
    db.execute(text("UPDATE %s SET unit_no = 1 WHERE payload = 'old_1.0'" % NUM))
    _old(db, NUM, "old_1.0", "1.0")
    _write(db, NUM, unit_no=3, payload="old_003")
    _old(db, NUM, "old_003", "003")
    _write(db, NUM, unit_no=5, payload="alone")
    _old(db, NUM, "alone", "5.0")
    # same spelling twice: «7» · «7»
    _write(db, NUM, unit_no=7, payload="twin_a")
    _write(db, NUM, unit_no=8, payload="twin_b")
    _twin(db, NUM, "unit_no", 7, "twin_b", "7")
    # both: «9» · «9» · «9.0» - all three go to the key's first row
    _write(db, NUM, unit_no=9, payload="nine_a")
    _write(db, NUM, unit_no=10, payload="nine_b")
    _twin(db, NUM, "unit_no", 9, "nine_b", "9")
    _write(db, NUM, unit_no=11, payload="nine_old")
    _twin(db, NUM, "unit_no", 9, "nine_old", "9.0")
    first_nine = db.execute(text("SELECT row_id FROM %s WHERE payload = 'nine_a'" % NUM)).scalar()
    # text key: letters are the key; «A» twice
    _write(db, TXT, code="001", payload="text")
    _write(db, TXT, code="A", payload="text_a")
    _write(db, TXT, code="B", payload="text_b")
    _twin(db, TXT, "code", "A", "text_b", "A")
    # composite with a number part
    _write(db, COMP, map_id="M1", die_no=1, payload="comp_kept")
    _write(db, COMP, map_id="M1", die_no=2, payload="comp_old")
    db.execute(text("UPDATE %s SET die_no = 1 WHERE payload = 'comp_old'" % COMP))
    _old(db, COMP, "comp_old", "M1_1.0")
    assert _rows(db, NUM) == [("003", "old_003"), ("1", "kept"), ("1.0", "old_1.0"), ("5.0", "alone"),
                              ("7", "twin_a"), ("7", "twin_b"), ("9", "nine_a"), ("9", "nine_b"),
                              ("9.0", "nine_old")]                                                # canary
    assert [k for k, _p in _rows(db, TXT)] == ["001", "A", "A"]                                   # canary
    return first_nine


def _check(db, first_nine):
    plan = replay.fold_written_notation(db, NUM, apply=False)
    # 003 -> 3 · 5.0 -> 5; 1.0 meets 1 and 9.0 meets 9 (split spelling); the second «7» and «9» meet the first
    assert (plan["keys_changed"], plan["rows_merged"], plan["split_key_groups"], plan["same_key_groups"]) \
        == (2, 4, 2, 2), plan
    assert {(m["business_key_val"], m["folded_key"]) for m in plan["merged"]} == \
        {("1.0", "1"), ("7", "7"), ("9", "9"), ("9.0", "9")}
    assert {m["into"] for m in plan["merged"] if m["folded_key"] == "9"} == {first_nine}       # the key's first row
    plan = replay.fold_written_notation(db, TXT, apply=False)
    assert (plan["keys_changed"], plan["rows_merged"], plan["same_key_groups"]) == (0, 1, 1), plan
    for table in (NUM, TXT, COMP):
        replay.fold_written_notation(db, table, apply=True)
    assert [k for k, _p in _rows(db, NUM)] == ["1", "3", "5", "7", "9"], _rows(db, NUM)
    assert db.execute(text("SELECT row_id FROM %s WHERE business_key_val = '9'" % NUM)).scalar() == first_nine
    assert [k for k, _p in _rows(db, TXT)] == ["001", "A"], _rows(db, TXT)
    again = replay.fold_written_notation(db, NUM, apply=False)
    assert (again["keys_changed"], again["rows_merged"]) == (0, 0), again                     # a second run: nothing
    assert [k for k, _p in _rows(db, COMP)] == ["M1_1"], _rows(db, COMP)
    # the chain hands the key back as a number: it lands on the row
    _write(db, NUM, unit_no=1.0, payload="again")
    _write(db, NUM, unit_no=3, payload="again3")
    assert [k for k, _p in _rows(db, NUM)] == ["1", "3", "5", "7", "9"], _rows(db, NUM)


@pytest.fixture(name="sqlite_db")
def fixture_sqlite_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(CFG)
    crud.TABLE_CONFIG.update(CFG)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_old_number_spellings_are_rekeyed_and_merged_row_path(sqlite_db):
    _check(sqlite_db, _scenarios(sqlite_db))


def test_a_run_that_merged_calls_the_key_index_builder_on_postgresql_only(sqlite_db, monkeypatch):
    """The Admin op, after a merge: the start-up builder for this one table - on PostgreSQL; on SQLite a line."""
    from admin import retroactive
    from chain import ingestion_worker

    called = []
    monkeypatch.setattr(ingestion_worker, "_ensure_business_key_unique_indexes_sync",
                        lambda factory, only=None: called.append(only) or {"built": [], "refused": [], "invalid": []})
    _scenarios(sqlite_db)
    out = retroactive._run_fold_written_notation(sqlite_db, {"table": NUM}, log=lambda line: None)
    assert out["rows_merged"] == 4 and out["unique_index"] == {"skipped": "sqlite"} and called == []
    monkeypatch.setattr(sqlite_db.get_bind().dialect, "name", "postgresql")
    assert retroactive._build_key_index_after_merge(sqlite_db, NUM, lambda line: None) == \
        {"built": [], "refused": [], "invalid": []}
    assert called == [[NUM]]


@pytest.fixture(name="pg_db")
def fixture_pg_db(pg_engine):
    from conftest import PG_TEST_SCHEMA, retire_dynamic_model

    saved = dict(crud.TABLE_CONFIG)
    for name in CFG:
        retire_dynamic_model(name)
    models.init_dynamic_models(CFG)
    crud.TABLE_CONFIG.update(CFG)

    def clean():
        with pg_engine.begin() as conn:
            for name in CFG:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                for side in ("cell_sources", "cell_overwrites", "database_outbox", "audit_logs"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t' % (PG_TEST_SCHEMA, side)),
                                 {"t": name})

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in CFG:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)()
    try:
        assert db.execute(text("SELECT current_schema()")).scalar() == PG_TEST_SCHEMA
        yield db
    finally:
        db.rollback()
        db.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in CFG:
            retire_dynamic_model(name)


@pytest.mark.pg
def test_old_number_spellings_are_rekeyed_and_merged_by_value(pg_db):
    assert pg_db.get_bind().dialect.name in replay.FOLD_BY_VALUE_DIALECTS      # the by-value page
    _check(pg_db, _scenarios(pg_db))


@pytest.mark.pg
def test_the_key_index_is_built_after_the_merge_in_the_schema_the_run_reads(pg_db):
    """총괄 10-20 ③: the builder asks the connection's current schema (public in production). Here the scratch schema:
    refused while «7» · «9» are held twice, built on the scratch table after the Admin op's merge - and public's
    business-key unique indexes are the same before and after."""
    from admin import retroactive
    from chain import ingestion_worker
    from conftest import PG_TEST_SCHEMA

    count_uq = ("SELECT n.nspname, c.relname, x.indisvalid FROM pg_index x JOIN pg_class c ON c.oid = x.indexrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE x.indisunique AND c.relname LIKE 'uq_bk_%' "
                "AND n.nspname IN ('public', :s) ORDER BY 1, 2")
    public_before = [r for r in pg_db.execute(text(count_uq), {"s": PG_TEST_SCHEMA}).fetchall() if r[0] == "public"]
    _scenarios(pg_db)
    pg_db.commit()
    before = ingestion_worker._ensure_business_key_unique_indexes_sync(
        sessionmaker(bind=pg_db.get_bind()), only=[NUM])
    assert before["refused"] == [(NUM, 2)] and before["built"] == [], before     # a second «7» and «9»
    out = retroactive._run_fold_written_notation(pg_db, {"table": NUM}, log=lambda line: None)
    assert out["rows_merged"] == 4 and [entry[:2] for entry in out["unique_index"]["built"]] == [[NUM, "created"]], out
    after = pg_db.execute(text(count_uq), {"s": PG_TEST_SCHEMA}).fetchall()
    assert [r for r in after if r[0] == PG_TEST_SCHEMA and r[1] == "uq_bk_" + NUM] == \
        [(PG_TEST_SCHEMA, "uq_bk_" + NUM, True)], after
    assert [r for r in after if r[0] == "public"] == public_before
    again = ingestion_worker._ensure_business_key_unique_indexes_sync(sessionmaker(bind=pg_db.get_bind()), only=[NUM])
    assert again == {"built": [], "refused": [], "invalid": []}, again                  # it is seen as there
    with pytest.raises(Exception, match="uq_bk_" + NUM):                         # the index holds the key now
        pg_db.execute(text("INSERT INTO %s (row_id, business_key_val, unit_no, payload) VALUES ('x1', '1', 1, 'dup')"
                           % NUM))
    pg_db.rollback()
