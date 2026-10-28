"""The PostgreSQL half of test_a_table_made_at_runtime_asks_its_key_index (lead 10-28, a data guard): a table the runtime
makes asks, the scheduler's index line's next poll builds `uq_bk_<table>` for it, and two writers putting one new key at
the same moment leave one row (`crud.apply_batch_updates`' recovery has the index to stand on). A table already holding
a key twice is named and left without one, as at the start. The test schema's tables; public is not touched."""
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import crud, models, schemas
from conftest import PG_TEST_SCHEMA, retire_dynamic_model

pytestmark = pytest.mark.pg
NEW, DUP = "kx_made_pg", "kx_made_dup_pg"
VALID = ("SELECT x.indisvalid FROM pg_index x JOIN pg_class c ON c.oid = x.indexrelid JOIN pg_namespace n ON "
         "n.oid = c.relnamespace WHERE x.indisunique AND n.nspname = :s AND c.relname = :n")


@pytest.fixture
def made(pg_db, monkeypatch):
    from runtime import index_wants

    engine = pg_db.get_bind()
    asked = []
    monkeypatch.setattr(index_wants, "want", lambda *args: asked.append(args))   # its thread's job, run here
    entry = {"business_key": "k", "column_types": {"k": "string", "v": "string"}}
    for name in (NEW, DUP):
        crud.TABLE_CONFIG[name] = entry
    models.init_dynamic_models({name: crud.TABLE_CONFIG[name] for name in crud.TABLE_CONFIG})
    with engine.begin() as conn:
        for name in (NEW, DUP):
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
    yield pg_db, engine, asked
    pg_db.rollback()
    with engine.begin() as conn:
        for name in (NEW, DUP):
            conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
    for name in (NEW, DUP):
        crud.TABLE_CONFIG.pop(name, None)
        retire_dynamic_model(name)


def _poll(engine):
    from runtime import maintenance_line, system_reload

    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        mark = system_reload.latest_reload_id(db)
    finally:
        db.close()
    return maintenance_line.poll_once(factory, mark)


def _put(engine, key, value):
    db = sessionmaker(bind=engine)()
    try:
        crud.apply_batch_updates(db, NEW, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
            updates={"k": key, "v": value}, source_name="user")]))
        db.commit()
    finally:
        db.close()


def test_a_table_made_at_runtime_gets_its_key_index_on_the_next_poll(made):
    pg_db, engine, asked = made
    created = models.create_missing_dynamic_tables(engine)
    assert {NEW, DUP} <= set(created)
    with engine.begin() as conn:                         # DUP holds a key twice before the poll
        conn.execute(text('INSERT INTO "%s"."%s" (row_id, business_key_val, k) VALUES (\'a\', \'1\', \'1\'), '
                          '(\'b\', \'1\', \'1\')' % (PG_TEST_SCHEMA, DUP)))
    from runtime import index_wants

    for args in [a for a in asked if a[0] in (NEW, DUP)]:
        assert index_wants.ask(*args), args              # one INDEX_WANTED row each
    _poll(engine)
    with engine.connect() as conn:
        assert conn.execute(text(VALID), {"s": PG_TEST_SCHEMA, "n": "uq_bk_" + NEW}).scalar() is True
        assert conn.execute(text(VALID), {"s": PG_TEST_SCHEMA, "n": "uq_bk_" + DUP}).scalar() is None, \
            "a table holding a key twice is named and left, as at the start"

    barrier = threading.Barrier(2)
    errors = []

    def put(value):
        try:
            barrier.wait()
            _put(engine, "K", value)
        except Exception as exc:                          # noqa: BLE001 - said below
            errors.append(exc)

    threads = [threading.Thread(target=put, args=(v,)) for v in ("x", "y")]
    [t.start() for t in threads]
    [t.join(60) for t in threads]
    with engine.connect() as conn:
        rows = conn.execute(text('SELECT count(*) FROM "%s"."%s" WHERE business_key_val = \'K\''
                                 % (PG_TEST_SCHEMA, NEW))).scalar()
    assert (rows, errors) == (1, []), (rows, errors)
