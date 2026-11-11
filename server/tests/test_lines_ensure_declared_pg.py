"""lines.ensure_declared on PostgreSQL (scratch schema): a table without the business key index keeps lines all the
same (owner 11-11); a lock held by a long read refuses within the lock wait and the next call builds (lead
11-11 - boot and the config watcher never hang on a 70M-row table)."""
import pytest
from sqlalchemy import MetaData, Table, inspect, text

from database import crud, lines, models
from database.models import sql_type_of

CFG = {"column_types": {"lot": "string"}}
NAME = "ed_t"


@pytest.fixture()
def engine(pg_engine, monkeypatch):
    import parsers.directory_watcher as watcher

    Table(NAME, MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(pg_engine)
    monkeypatch.setattr(crud, "TABLE_CONFIG", {NAME: CFG})
    monkeypatch.setattr(models, "DYNAMIC_TABLES", {NAME: type("StandIn", (), {})})
    monkeypatch.setattr(watcher, "ddl_lock_wait", lambda: (0.2, 0.3))
    yield pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{NAME}__lines"'))
        conn.execute(text(f'DROP TABLE IF EXISTS "{NAME}"'))
        conn.execute(text(f"DELETE FROM line_columns WHERE table_name = '{NAME}'"))


def test_a_table_without_the_key_index_keeps_lines(engine):
    with engine.connect() as conn:
        assert not lines.key_index_standing(conn, NAME)                          # canary: no index stands
    assert lines.ensure_declared(engine) == {}
    assert inspect(engine).has_table(f"{NAME}__lines")


def test_a_held_lock_refuses_then_the_next_call_builds(engine):
    with engine.begin() as conn:
        conn.execute(text(f'CREATE UNIQUE INDEX "uq_bk_{NAME}" ON "{NAME}" (business_key_val)'))
    reader = engine.connect()
    tx = reader.begin()
    reader.execute(text(f'SELECT * FROM "{NAME}"'))                              # a long read holds ACCESS SHARE
    try:
        said = lines.ensure_declared(engine)
        assert NAME in said and "held by" in said[NAME]
    finally:
        tx.rollback()
        reader.close()
    assert not inspect(engine).has_table(f"{NAME}__lines")
    assert lines.ensure_declared(engine) == {}
    assert inspect(engine).has_table(f"{NAME}__lines")


def test_the_one_key_index_builder_builds_the_lines_on_the_fold_path(engine):
    """A fold's merge calls the key index builder for its table (retroactive._build_key_index_after_merge); the lines
    stand right after it, not at the next boot."""
    from sqlalchemy.orm import sessionmaker

    from chain.ingestion_worker import _ensure_business_key_unique_indexes_sync

    out = _ensure_business_key_unique_indexes_sync(sessionmaker(bind=engine), only=[NAME])
    assert [t for t, *_ in out["built"]] == [NAME]                                # canary: the index was built here
    assert inspect(engine).has_table(f"{NAME}__lines")
