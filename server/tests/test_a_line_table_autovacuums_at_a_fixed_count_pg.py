"""Lead 11-12 나: every declared table's line table autovacuums at a fixed count of dead lines - a fourth source
(«lines», `lines.line_storage`, ingestion_settings.json lines_autovacuum_threshold) of the declared storage line.

  the rule: 50 + 2 % of the rows, capped at the setting's count (autovacuum_vacuum_max_threshold, PG 18)
  built by the start / migrated by the copy   owed -> set -> held, one «[Lines] autovacuum» line, then silent
  set by hand                                 kept (differs), said once
  the setting null                            left alone - no line-table row
  a wrong value                               one line, the default held
"""
import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import MetaData, Table, text
from sqlalchemy.orm import Session, sessionmaker

from database import crud, line_migration, lines
from database.models import CellOverwrite, CellSource, sql_type_of

pytestmark = pytest.mark.pg
T = "lav_t"
CFG = {"column_types": {"lot": "string"}}
REL = lines.lines_relation(T)


@pytest.fixture(name="cells")
def fixture_cells(pg_engine, monkeypatch):
    import ingestion.settings
    from database.database import Base
    from ledger import schema
    from runtime import maintenance_line

    cells = {}
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda path=None: dict(cells))
    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": [], "operating": schema.DEFAULT_WORLD})
    for table in Base.metadata.sorted_tables:                   # the models' own storage is the other test's
        if table.info.get("storage"):
            monkeypatch.setitem(table.info, "storage", {})
    monkeypatch.setattr(crud, "TABLE_CONFIG", {T: CFG})
    monkeypatch.setattr(lines, "_SAID_SETTING", set())
    monkeypatch.setattr(maintenance_line, "_SAID_LINES", {})
    monkeypatch.setattr(maintenance_line, "_SAID_STORAGE", set())
    with pg_engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS "%s"' % REL))
        c.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        Table(T, MetaData(), *lines._data_columns(CFG, sql_type_of, row_id_key=True)).create(c)
    assert lines.ensure_declared(pg_engine, [T]) == {}
    yield cells
    with pg_engine.begin() as c:
        c.execute(text('DROP TABLE IF EXISTS "%s"' % REL))
        c.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        if c.execute(text("SELECT to_regclass('cell_sources')")).scalar():
            c.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})


def migrate(engine):
    """30 rows of t with a layer each, copied into t__lines by the migration's page."""
    with engine.begin() as c:
        CellSource.__table__.create(c, checkfirst=True)
        CellOverwrite.__table__.create(c, checkfirst=True)
        c.execute(text("INSERT INTO \"%s\" (row_id, business_key_val, lot) SELECT 'r' || g, 'k' || g, 'a' || g "
                       "FROM generate_series(1, 30) g" % T))
        c.execute(text("INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value, ingested_at, "
                       "updated_by) SELECT :t, 'r' || g, 'lot', 'f.csv', to_json('a' || g), :at, 'seed' "
                       "FROM generate_series(1, 30) g"), {"t": T, "at": datetime(2026, 11, 1, tzinfo=timezone.utc)})
    with Session(bind=engine) as db:
        after = None
        while True:
            _n, after = line_migration.copy_page(db, T, CFG, after, 10, transaction_id="copy_lines:%s" % T)
            db.commit()
            if after is None:
                break
    with engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM "%s"' % REL)).scalar() == 30     # canary: it was migrated


def held(engine, rel=REL):
    with engine.connect() as c:
        options = c.execute(text("SELECT c.reloptions FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                                 "WHERE c.relname = :r AND n.nspname = current_schema()"), {"r": rel}).scalar()
    return dict(option.split("=", 1) for option in options or ())


def states(engine):
    from runtime import maintenance_line

    db = sessionmaker(bind=engine)()
    try:
        return {r["parameter"]: (r["state"], r["source"]) for r in maintenance_line.storage_states(db)
                if r["table"] == REL}
    finally:
        db.close()


def say(engine, caplog, group="[Lines] autovacuum"):
    from runtime import maintenance_line

    caplog.clear()
    with caplog.at_level(logging.INFO):
        maintenance_line._storage_and_say(sessionmaker(bind=engine))
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(group)]


DECLARED = {"autovacuum_vacuum_scale_factor": "0.02", "autovacuum_vacuum_threshold": "50",
            "autovacuum_vacuum_max_threshold": str(lines.LINES_AUTOVACUUM_DEFAULT),
            "autovacuum_vacuum_cost_limit": str(lines.AUTOVACUUM_COST_LIMIT), "vacuum_truncate": "false"}


@pytest.mark.parametrize("made", ["built by the start", "migrated by the copy"])
def test_a_line_table_is_owed_then_set_then_held_and_said_once(cells, pg_engine, caplog, made):
    if made == "migrated by the copy":
        migrate(pg_engine)
    assert held(pg_engine) == {}
    assert states(pg_engine) == {k: ("owed", "lines") for k in DECLARED}
    said = say(pg_engine, caplog)
    assert len(said) == 1 and "set now 1" in said[0] and "autovacuum_vacuum_max_threshold = %d" % (
        lines.LINES_AUTOVACUUM_DEFAULT) in said[0], said
    assert held(pg_engine) == DECLARED
    assert states(pg_engine) == {k: ("held", "lines") for k in DECLARED}
    assert say(pg_engine, caplog) == []                     # all held: silent


def test_a_threshold_set_by_hand_is_kept_and_said_once(cells, pg_engine, caplog):
    say(pg_engine, caplog)
    with pg_engine.begin() as c:
        c.execute(text('ALTER TABLE "%s" SET (autovacuum_vacuum_max_threshold = 2000)' % REL))
    said = say(pg_engine, caplog)
    assert len(said) == 1 and "by hand 1" in said[0], said
    assert held(pg_engine)["autovacuum_vacuum_max_threshold"] == "2000"
    assert states(pg_engine)["autovacuum_vacuum_max_threshold"] == ("differs", "lines")
    assert say(pg_engine, caplog) == [] and held(pg_engine)["autovacuum_vacuum_max_threshold"] == "2000"


def test_the_setting_null_leaves_the_line_tables_alone(cells, pg_engine, caplog):
    cells[lines.LINES_AUTOVACUUM_SETTING] = None
    assert lines.line_storage() is None
    assert states(pg_engine) == {}
    assert say(pg_engine, caplog) == [] and held(pg_engine) == {}


def test_a_wrong_value_is_said_once_and_the_default_held(cells, pg_engine, caplog):
    cells[lines.LINES_AUTOVACUUM_SETTING] = "many"
    with caplog.at_level(logging.WARNING):
        assert lines.line_storage()["autovacuum_vacuum_max_threshold"] == lines.LINES_AUTOVACUUM_DEFAULT
        lines.line_storage()
    wrong = [r.getMessage() for r in caplog.records if lines.LINES_AUTOVACUUM_SETTING in r.getMessage()]
    assert len(wrong) == 1 and "'many'" in wrong[0], wrong
    say(pg_engine, caplog)
    assert held(pg_engine) == DECLARED


def test_a_set_threshold_is_held():
    """sqlite-free arithmetic of the setting: a whole number from 0 is taken as written."""
    import ingestion.settings

    was = ingestion.settings.read_ingestion_settings
    ingestion.settings.read_ingestion_settings = lambda path=None: {lines.LINES_AUTOVACUUM_SETTING: 7000}
    try:
        assert lines.line_storage()["autovacuum_vacuum_max_threshold"] == 7000
    finally:
        ingestion.settings.read_ingestion_settings = was


T_DECLARED = {"autovacuum_vacuum_scale_factor": "0.02", "autovacuum_vacuum_threshold": "50",
              "autovacuum_vacuum_max_threshold": str(lines.TABLE_AUTOVACUUM_DEFAULT),
              "autovacuum_vacuum_cost_limit": str(lines.AUTOVACUUM_COST_LIMIT), "vacuum_truncate": "false"}


def test_a_declared_table_is_held_at_the_table_default_and_said_once(cells, pg_engine, caplog):
    """Lead 11-13 ga: t itself - the one rule, a pass that finishes, no end truncation."""
    assert held(pg_engine, T) == {}
    said = say(pg_engine, caplog, "[Storage] autovacuum on declared tables")
    assert len(said) == 1 and "set now 1" in said[0], said
    assert held(pg_engine, T) == T_DECLARED
    assert say(pg_engine, caplog, "[Storage] autovacuum on declared tables") == []


def test_a_storage_cell_the_table_names_wins_over_the_default(cells, pg_engine, caplog, monkeypatch):
    monkeypatch.setattr(crud, "TABLE_CONFIG", {T: dict(CFG, storage={"autovacuum_vacuum_max_threshold": 7000,
                                                                      "fillfactor": 90})})
    say(pg_engine, caplog)
    assert held(pg_engine, T) == dict(T_DECLARED, autovacuum_vacuum_max_threshold="7000", fillfactor="90")
    assert held(pg_engine) == DECLARED                     # its line table keeps the line default


def test_the_table_setting_null_leaves_t_alone_and_the_lines_held(cells, pg_engine, caplog):
    cells[lines.TABLE_AUTOVACUUM_SETTING] = None
    assert lines.table_storage() is None
    assert say(pg_engine, caplog, "[Storage] autovacuum on declared tables") == []
    assert held(pg_engine, T) == {} and held(pg_engine) == DECLARED

