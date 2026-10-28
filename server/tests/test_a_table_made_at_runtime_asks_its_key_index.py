"""A table made after the scheduler started asks its business-key unique index (lead 10-28, a data guard): the seats
that make a table - the runtime «create missing» and the API's boot - queue an INDEX_WANTED of `models.KEY_UNIQUE`,
and the scheduler's index line builds it with the start builder for that table alone, on its next poll. Without it a
new table took no unique index until the scheduler restarted, and two inserts of one key made two rows.
In process on sqlite; the PostgreSQL half is test_a_table_made_at_runtime_gets_its_key_index_pg."""
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from database import crud, models
from conftest import retire_dynamic_model

NEW = "kx_made_now"


def test_the_ask_is_queued_on_postgres_alone(monkeypatch):
    from runtime import index_wants

    queued = []
    monkeypatch.setattr(index_wants, "want", lambda *args: queued.append(args))
    models.ask_key_unique(NEW, SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    assert queued == []
    pg = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    models.ask_key_unique(NEW, pg)
    assert queued == [(NEW, ["business_key_val"], models.KEY_UNIQUE, 0.0, pg)]
    assert models.auto_index_serves({"columns": ["business_key_val"], "using": "btree", "where": None},
                                    ["business_key_val"], models.KEY_UNIQUE) is False, \
        "a plain index on the column does not serve - only the builder knows uniqueness"


@pytest.fixture
def made(monkeypatch):
    asked = []
    monkeypatch.setattr(models, "ask_key_unique", lambda table, bind: asked.append(table))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    entry = {"business_key": "k", "column_types": {"k": "string"}}
    crud.TABLE_CONFIG[NEW] = entry
    models.init_dynamic_models({**{name: crud.TABLE_CONFIG[name] for name in models.DYNAMIC_TABLES
                                   if name in crud.TABLE_CONFIG}, NEW: entry})
    models.DYNAMIC_TABLES[NEW].__table__.drop(bind=engine, checkfirst=True)
    yield engine, asked
    crud.TABLE_CONFIG.pop(NEW, None)
    retire_dynamic_model(NEW)


def test_a_table_made_by_create_missing_asks_and_one_already_there_does_not(made):
    engine, asked = made
    assert not inspect(engine).has_table(NEW)
    created = models.create_missing_dynamic_tables(engine)
    assert NEW in created and asked == [n for n in created], "every table made asks, once"
    asked.clear()
    assert models.create_missing_dynamic_tables(engine) == [] and asked == []


def test_the_api_boot_asks_for_the_tables_it_made_alone(made, monkeypatch):
    import main

    engine, asked = made
    held = set(inspect(engine).get_table_names())
    assert NEW not in held and held                                   # canary: the boot finds tables already there
    main.bootstrap_database_schema(engine)
    assert asked == [NEW], "the table the boot made - not the ones it found"


def test_the_line_builds_a_key_ask_with_the_start_builder_for_that_table(monkeypatch):
    import event_constants
    from chain import ingestion_worker
    from runtime import index_wants, maintenance_line, system_reload

    class _Db:
        def commit(self):
            pass

        def close(self):
            pass

    built, auto = [], []
    monkeypatch.setattr(system_reload, "reloads_after", lambda db, mark: [])
    monkeypatch.setattr(index_wants, "taken", lambda db: [(object(), (NEW, ["business_key_val"], models.KEY_UNIQUE)),
                                                          (object(), ("t", ["s"], models.AUTO_SLOW_SORT))])
    monkeypatch.setattr(event_constants, "mark_processed", lambda row, status: None)
    monkeypatch.setattr(ingestion_worker, "_ensure_business_key_unique_indexes_sync",
                        lambda factory, only=None: built.append(only))
    monkeypatch.setattr(models, "ensure_auto_indexes_sync", lambda factory, wanted, say, decide: auto.append(wanted))
    maintenance_line.poll_once(_Db, 0)
    assert built == [[NEW]], "the start builder, for that table alone"
    assert auto == [[("t", ["s"], models.AUTO_SLOW_SORT)]], "the automatic asks as before - the key ask not among them"
