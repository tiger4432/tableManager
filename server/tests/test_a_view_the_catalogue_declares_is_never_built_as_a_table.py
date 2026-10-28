# -*- coding: utf-8 -*-
"""A catalogue `kind: view` is mapped and never built (총괄 10-28, C's box): setup's and boot's
`Base.metadata.create_all` built the shipped sample's two views as plain tables, so the ledger's
`CREATE TABLE IF NOT EXISTS` and `CREATE VIEW` stepped over them - ledger_events stayed varchar («->>» refused),
ledger_atom_rows an empty table the grid read in silence.

    seat                                        gate
    Base.metadata (models.VIEW_METADATA)        the sample's views are not built by create_all, and are mapped
    create_missing_dynamic_tables               the runtime loop builds none of them either
    ledger ensure_schema (PG)                   builds ledger_events partitioned ('p') and ledger_atom_rows a view ('v')
    ... another kind stands there (PG)          one line a process (`_built_kinds` · `_say_another_kind`), left alone
"""
import logging

import pytest
from sqlalchemy import create_engine, inspect, text

from database import models
from database.database import Base
from ledger import setup_bundle
from tests.test_ledger_trace_pg import ledger_engine  # noqa: F401 - the shipped ledger schema


def _kind(engine, name):
    with engine.connect() as conn:
        return conn.execute(text("SELECT relkind FROM pg_class WHERE oid = to_regclass(:n)"), {"n": name}).scalar()


def test_a_view_the_catalogue_declares_is_mapped_and_not_built(monkeypatch):
    from tests.support.declaration import use_committed_catalogue

    catalogue = use_committed_catalogue(monkeypatch)
    views = sorted(name for name, entry in catalogue.items() if setup_bundle.catalog_kind(entry) == "view")
    assert views, "the sample declares views - nothing to measure otherwise"
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    created = models.create_missing_dynamic_tables(engine)

    built = set(inspect(engine).get_table_names())
    assert not set(views) & built, "a view the catalogue declares is not this product's to build"
    assert not set(views) & set(created)
    assert "lot_event" in built, "control: a declared table is built"
    assert all(models.DYNAMIC_TABLES[name].__table__.metadata is models.VIEW_METADATA for name in views)


@pytest.mark.pg
def test_the_ledger_builds_its_table_and_its_view(ledger_engine):  # noqa: F811
    assert (_kind(ledger_engine, "ledger_events"), _kind(ledger_engine, "ledger_atom_rows")) == ("p", "v")


def _ensure_twice(pg_engine, caplog):
    """The ledger's ensure_schema twice in one process - what it said, the failure it may stop on (a plain table it
    cannot index is how C's box went on)."""
    from ledger import schema as ledger_schema

    raw = pg_engine.raw_connection()
    failed = None
    try:
        with caplog.at_level(logging.WARNING, logger="Ledger.Schema"):
            for _ in range(2):
                try:
                    ledger_schema.ensure_schema(raw.driver_connection)
                except Exception as exc:                       # noqa: BLE001 - recorded, the line is the gate
                    failed = exc
                    raw.driver_connection.rollback()
    finally:
        raw.close()
    return [r.getMessage() for r in caplog.records if "stands where the ledger's" in r.getMessage()], failed


@pytest.fixture(name="bare")
def fixture_bare(pg_engine, monkeypatch):
    """The scratch schema without the ledger, and the once-a-process memory empty; the ledger dropped after."""
    from ledger import schema as ledger_schema

    monkeypatch.setattr(ledger_schema, "_SAID_ANOTHER_KIND", set())

    def drop():
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS ledger_events CASCADE"))      # its view goes with it
            kind = conn.execute(text("SELECT relkind FROM pg_class WHERE oid = to_regclass('ledger_atom_rows')"))
            kind = kind.scalar()
            if kind:
                conn.execute(text("DROP %s ledger_atom_rows" % ("VIEW" if kind == "v" else "TABLE")))
            conn.execute(text("DROP TABLE IF EXISTS ledger_translator_cursor CASCADE"))
    drop()
    yield pg_engine
    drop()


@pytest.mark.pg
def test_a_table_where_the_view_belongs_is_said_once_and_left(bare, caplog):
    with bare.begin() as conn:
        conn.execute(text("CREATE TABLE ledger_atom_rows (atom_id varchar)"))
    said, _failed = _ensure_twice(bare, caplog)

    assert said == ["ledger_atom_rows: a table stands where the ledger's view belongs - it is not built"]
    assert _kind(bare, "ledger_atom_rows") == "r", "said, not dropped - a person drops it"


@pytest.mark.pg
def test_the_catalogues_plain_ledger_events_is_said_once_and_left(bare, caplog, monkeypatch):
    """C's box: the sample catalogue's ledger_events, built as the grid built it before this round."""
    from tests.support.declaration import use_committed_catalogue

    use_committed_catalogue(monkeypatch)
    models.VIEW_METADATA.tables["ledger_events"].create(bind=bare)
    said, _failed = _ensure_twice(bare, caplog)

    assert said == ["ledger_events: a table stands where the ledger's partitioned table belongs - it is not built"]
    assert _kind(bare, "ledger_events") == "r"
