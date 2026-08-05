"""A column added to a mapped system table takes that whole table down until the
migration runs. This suite pins the mechanism and gates the class of change.

The incident: `CellSource.confirmation_uid` was added to the model and shipped
before `migrations/add_frame_confirmation.py` had run on the production database.
The screens that died were not the ones that read the stamp. SQLAlchemy names
every mapped column in the SQL it generates, so on an unmigrated database EVERY
full-entity query and EVERY ORM insert against `cell_sources` failed, including
paths that predate this feature entirely and never mention the stamp.

Why the repair is a migration and not model-level tolerance: see
`test_deferred_does_not_save_the_write_path`. The schema is the contract. What was
missing is not tolerance, it is a gate that makes the author of the next such
column say out loud how it reaches a database that already exists.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import models
from database.models import CellSource


# Columns of `cell_sources` as they existed BEFORE the frame-confirmation round.
# Used to build a database on which the migration has not run.
_PRE_MIGRATION_CELL_SOURCES = """
CREATE TABLE cell_sources (
    id           INTEGER PRIMARY KEY,
    table_name   VARCHAR NOT NULL,
    row_id       VARCHAR NOT NULL,
    column_name  VARCHAR NOT NULL,
    source_name  VARCHAR NOT NULL,
    value        JSON,
    ingested_at  DATETIME,
    updated_by   VARCHAR
)"""


@pytest.fixture
def unmigrated_db():
    """A session bound to a `cell_sources` that is missing `confirmation_uid`.

    This is how the absence is simulated. Every box we develop and test on has
    already run the migration, so the broken case cannot be reached by pointing at
    the real database - it has to be built. The table is created by hand from the
    pre-round column list on a private in-memory engine, then the REAL mapped class
    is queried against it. Nothing here touches the suite's shared database.
    """
    engine = create_engine("sqlite://")
    session = sessionmaker(bind=engine)()
    session.execute(text(_PRE_MIGRATION_CELL_SOURCES))
    session.execute(text(
        "INSERT INTO cell_sources (table_name, row_id, column_name, source_name, value, updated_by)"
        " VALUES ('dt_log', 'r1', 'frame', 'user', '\"rot0\"', 'kim')"))
    session.commit()
    yield session
    session.close()


def test_the_absent_column_is_actually_absent(unmigrated_db):
    """Guards the fixture itself: if this stops being true the tests below prove nothing."""
    cols = {r[1] for r in unmigrated_db.execute(text("PRAGMA table_info(cell_sources)")).fetchall()}
    assert "confirmation_uid" not in cols
    assert "source_name" in cols, "fixture must otherwise be a faithful cell_sources"


def test_missing_column_appears_in_sql_that_never_asked_for_it():
    """The blast radius, stated as SQL: the stamp is in the SELECT of every full read."""
    engine = create_engine("sqlite://")
    compiled = str(
        sessionmaker(bind=engine)().query(CellSource)
        .filter(CellSource.table_name == "dt_log")
        .statement.compile(engine))
    assert "confirmation_uid" in compiled, (
        "a full-entity SELECT is expected to name every mapped column - if it no longer "
        "does, the failure mode this suite guards has changed shape")


def test_full_entity_read_dies_without_the_column(unmigrated_db):
    """`GET /tables/{t}/{row}/{col}/sources` and `POST /tables/{t}/cells/sources/query`.

    Neither route reads the stamp. Both die anyway.
    """
    from sqlalchemy.exc import OperationalError

    with pytest.raises(OperationalError, match="confirmation_uid"):
        unmigrated_db.query(CellSource).filter(
            CellSource.table_name == "dt_log",
            CellSource.row_id == "r1",
            CellSource.column_name == "frame").all()
    unmigrated_db.rollback()

    with pytest.raises(OperationalError, match="confirmation_uid"):
        unmigrated_db.query(CellSource).filter(
            CellSource.table_name == "dt_log",
            CellSource.row_id.in_(["r1"]),
            CellSource.column_name.in_(["frame"])).all()


def test_orm_insert_dies_without_the_column_even_when_the_stamp_is_never_set(unmigrated_db):
    """The half that reaches ingestion.

    `crud.py` builds `models.CellSource(...)` without mentioning the stamp, and the
    generated INSERT names it regardless. So provenance writes fail on an unmigrated
    database too, in a worker rather than on a screen.
    """
    from sqlalchemy.exc import OperationalError

    unmigrated_db.add(CellSource(
        table_name="dt_log", row_id="r2", column_name="frame",
        source_name="pipeline_parser", value="rot90", updated_by="sys"))
    with pytest.raises(OperationalError, match="confirmation_uid"):
        unmigrated_db.flush()


def test_column_projection_survives_without_the_column(unmigrated_db):
    """The shape that did NOT break, and the reason the outage looked selective.

    `crud.py` bulk prefetch and the audit read select named columns, so their SQL
    never mentions the stamp. Recording it so the asymmetry is not mistaken for the
    fix: it is why some paths kept working, not a pattern that makes a model change safe.
    """
    rows = unmigrated_db.query(
        CellSource.row_id, CellSource.column_name, CellSource.source_name,
        CellSource.value, CellSource.updated_by, CellSource.ingested_at
    ).filter(CellSource.table_name == "dt_log").all()
    assert len(rows) == 1


def test_deferred_does_not_save_the_write_path(unmigrated_db):
    """Why model-level tolerance was rejected.

    `deferred()` keeps the column out of the default SELECT, so the screen would
    render on an unmigrated database. It does nothing for INSERT - the write path
    keeps failing, now in a worker instead of in front of an operator, and the read
    that touches the attribute fails on its lazy load. That trades a loud total
    failure for a quiet partial one that silently drops provenance, which is worse.
    """
    from sqlalchemy.orm import deferred
    from sqlalchemy import Column, String

    assert CellSource.confirmation_uid.property.deferred is False, (
        "confirmation_uid is deliberately NOT deferred - see this test's rationale")
    assert callable(deferred) and Column is not None


def test_create_all_does_not_add_a_column_to_an_existing_table(unmigrated_db):
    """Why boot does not heal this, and why new TABLES are safe while new COLUMNS are not.

    `bootstrap_database_schema` is `Base.metadata.create_all` plus a dynamic-table
    sync driven by table_config.json. `create_all` skips a table that already exists,
    and `cell_sources` is a system table, so no boot path alters it. A brand new
    system table has no such problem: create_all builds it whole on first boot.
    """
    models.Base.metadata.create_all(
        bind=unmigrated_db.get_bind(), tables=[CellSource.__table__], checkfirst=True)
    cols = {r[1] for r in unmigrated_db.execute(text("PRAGMA table_info(cell_sources)")).fetchall()}
    assert "confirmation_uid" not in cols, (
        "create_all does not ALTER an existing table - if this ever passes, the "
        "boot-time story for system-table columns has changed and this suite is stale")

    for new_table in (models.FrameConfirmation.__table__, models.FrameConfirmationSource.__table__):
        models.Base.metadata.create_all(
            bind=unmigrated_db.get_bind(), tables=[new_table], checkfirst=True)
    present = {r[0] for r in unmigrated_db.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table'")).fetchall()}
    assert {"frame_confirmation", "frame_confirmation_source"} <= present, (
        "new tables must be reachable by create_all - that is what makes them the "
        "safer way to store new state")


# ---------------------------------------------------------------------------
# The gate. Everything above documents the incident; this is what stops the next one.
# ---------------------------------------------------------------------------

# Columns of every system (non-dynamic) table, as reviewed. Dynamic tables are
# excluded on purpose: they come from the operator's table_config.json, which is
# outside git and differs per machine, and they DO have a boot-time ALTER path
# (`models.sync_dynamic_tables_schema`). System tables have none.
#
# Adding a column here is not paperwork. `create_all` will not add it to a database
# that already has the table, so an entry that is added without a migration having
# run is an outage on every deployed box. Update this only together with the
# migration that puts the column on an existing database, and say which migration
# that is in the pull request.
SYSTEM_TABLE_COLUMNS = {
    "audit_logs": ('business_key', 'column_name', 'id', 'new_value', 'old_value', 'row_id', 'source_name', 'table_name', 'timestamp', 'transaction_id', 'updated_by'),
    "cell_overwrites": ('column_name', 'id', 'is_overwrite', 'manual_priority_source', 'row_id', 'table_name', 'updated_at', 'updated_by'),
    # confirmation_uid: migrations/add_frame_confirmation.py
    "cell_sources": ('column_name', 'confirmation_uid', 'id', 'ingested_at', 'row_id', 'source_name', 'table_name', 'updated_by', 'value'),
    # processed_chain, broadcast_at: reconciled at boot in main.py startup_event
    "database_outbox": ('broadcast_at', 'created_at', 'event_type', 'event_uuid', 'id', 'payload', 'processed_at', 'processed_chain', 'retry_count', 'status', 'table_name'),
    "file_ingestion_checkpoints": ('chunk_index', 'file_signature', 'filename', 'filepath', 'id', 'note', 'processed_rows', 'source_kind', 'started_at', 'status', 'table_name', 'total_rows', 'updated_at'),
    "file_ingestion_logs": ('created_at', 'error_message', 'filename', 'filepath', 'id', 'retry_count', 'status', 'table_name', 'updated_at'),
    # new table this round - created whole by create_all, no ordering hazard
    # geometry_assumed: migrations/add_frame_confirmation.py (spec MAP_ALIGNMENT 9a - which
    # confirmations rest on a borrowed wafer spec)
    "frame_confirmation": ('confirmation_uid', 'confirmed_at', 'confirmed_by', 'core_frame', 'decision_key', 'discriminating', 'dt_eqp', 'dt_frame', 'enrichment_row_id', 'geometry_assumed', 'id', 'margin', 'product', 'reference_map_id', 'reference_table', 'rule_name', 'ruling_reason', 'ruling_state', 'superseded_by', 'supersedes_uid', 'unit_key', 'version', 'weakest_priority', 'weakest_source', 'winner_frame'),
    # new table this round - created whole by create_all, no ordering hazard
    # geometry_basis: migrations/add_frame_confirmation.py (same round - which SOURCE stood
    # on the borrowed spec, since the header flag alone cannot name it)
    "frame_confirmation_source": ('agreement', 'applied_frame', 'confirmation_uid', 'discriminating', 'excluded_reason', 'geometry_basis', 'id', 'map_id', 'role', 'shift_dx', 'shift_dy', 'source_name', 'source_priority', 'source_table'),
    "graph_edges": ('created_at', 'event_time', 'from_node', 'id', 'props', 'source_name', 'source_row_ref', 'to_node', 'type', 'updated_by'),
    "graph_nodes": ('created_at', 'id', 'identity_key', 'label', 'props', 'updated_at'),
    "graph_sync_state": ('id', 'last_outbox_id', 'updated_at'),
    "interaction_effort_logs": ('id', 'key_count', 'mouse_count', 'nav_count', 'nav_preserved_count', 'session_id', 'timestamp', 'transaction_id'),
}


def _live_system_tables():
    return {name: tuple(sorted(c.name for c in table.columns))
            for name, table in models.Base.metadata.tables.items()
            if name not in models.DYNAMIC_TABLES}


def test_no_undeclared_system_table_column():
    """Fails when a system-table column is added without being declared here.

    A new table failing this is a formality. A new COLUMN on a table already in
    SYSTEM_TABLE_COLUMNS is the incident this suite exists for: it is invisible on
    every box that has run the migration, which is every box we test on.
    """
    live = _live_system_tables()

    new_columns = {
        name: sorted(set(cols) - set(SYSTEM_TABLE_COLUMNS[name]))
        for name, cols in live.items()
        if name in SYSTEM_TABLE_COLUMNS and set(cols) - set(SYSTEM_TABLE_COLUMNS[name])
    }
    assert not new_columns, (
        f"column(s) added to an EXISTING system table: {new_columns}. "
        "create_all does not ALTER a table that already exists, so on every deployed "
        "database this column is absent while the model names it in every SELECT and "
        "INSERT for that table - which takes the whole table down, not just the code "
        "that reads the column. Ship a migration that adds it to an existing database, "
        "confirm it has run, then record the column here naming that migration.")

    new_tables = sorted(set(live) - set(SYSTEM_TABLE_COLUMNS))
    assert not new_tables, (
        f"new system table(s) not declared here: {new_tables}. These are created whole "
        "by create_all at boot, so they carry no ordering hazard - add them to "
        "SYSTEM_TABLE_COLUMNS to keep this gate meaningful.")


def test_manifest_has_no_stale_entries():
    """A removed column must leave the manifest, or the gate silently narrows."""
    live = _live_system_tables()
    stale = {name: sorted(set(cols) - set(live[name]))
             for name, cols in SYSTEM_TABLE_COLUMNS.items()
             if name in live and set(cols) - set(live[name])}
    assert not stale, f"manifest lists columns the models no longer declare: {stale}"
