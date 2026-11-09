"""총괄 53338e99b (소유자 «오토 애널라이즈를 걸면 되지 않나» · «ㅇㅇ»): the ledger partitions'
`autovacuum_analyze_scale_factor` from one setting, `ledger_autoanalyze_scale_factor` (absent 0.02, null: hands off).

  a new one    made with it, where partitions are made (`ensure_partition`)
  the ones there   given it by the scheduler's storage line where theirs differs (lead 11-09 ⓑ, with every table's
               declared storage - `maintenance_line.apply_table_storage`); again: none touched
  null         the factor not written - a new partition and the ones there keep their own
  the line     whether autovacuum runs, said at the ledger process's start (`say_autovacuum_runs`)
  owner 11-09  vacuum_truncate=false on every partition, whatever the setting (a vacuum's end truncation took ACCESS
               EXCLUSIVE in ops); a partition busy past `short_ddl`'s tries is said and taken at the next merge
"""
import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from conftest import PG_TEST_SCHEMA
from ledger import schema
from support import hold_world as hw

pytestmark = pytest.mark.pg
S = PG_TEST_SCHEMA
FAR = datetime(2032, 3, 15, tzinfo=timezone.utc)


@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    # this run's default world only: a world the product ships (abdbdd0cc, `system`) is a schema every run shares
    # (`w_system`), so the setter would set - and these counts would meet - another run's partitions. Every world
    # once is `test_every_world_once_when_a_branch_operates`.
    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": [schema.DEFAULT_WORLD],
                                                          "operating": schema.DEFAULT_WORLD})
    for w in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        hw.push(w, [{"log_id": "L%03d" % i, "dt_job": "J%d" % i, "dt_x": i, "dt_y": 1, "netdie": i} for i in range(3)])
        hw.settle(w)
        yield w
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s".%s' % (S, schema.partition_name(FAR))))


def _settings(monkeypatch, **cells):
    import ingestion.settings
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda path=None: dict(cells))


def _options(engine):
    """{partition: its autovacuum_analyze_scale_factor or None} of the scratch ledger's partitions."""
    with engine.connect() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == S
        rows = conn.execute(text(
            "SELECT c.relname, c.reloptions FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = to_regclass('ledger_events')")).fetchall()
    return {name: next((float(o.split("=", 1)[1]) for o in options or ()
                        if o.startswith("autovacuum_analyze_scale_factor=")), None) for name, options in rows}


def _truncates(engine):
    """{partition: its vacuum_truncate or None} (owner 11-09: no end truncation on a ledger partition)."""
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT c.relname, c.reloptions FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid "
            "WHERE i.inhparent = to_regclass('ledger_events')")).fetchall()
    return {name: next((o.split("=", 1)[1] for o in options or () if o.startswith("vacuum_truncate=")), None)
            for name, options in rows}


def _set(engine):
    """The storage line once -> the partitions it ALTERed (a model table's storage is not these tests')."""
    from sqlalchemy.orm import sessionmaker
    from runtime import maintenance_line

    partitions = set(_options(engine))
    return [name for name, how in maintenance_line.apply_table_storage(sessionmaker(bind=engine)).items()
            if how == "set" and name in partitions]


def _new(engine):
    raw = engine.raw_connection()
    try:
        return schema.ensure_partition(raw, FAR)
    finally:
        raw.close()


def _made_before_this(engine):
    """The partitions as ones made before this setting existed."""
    names = sorted(_options(engine))
    with engine.begin() as conn:
        for name in names:
            conn.execute(text("ALTER TABLE %s RESET (autovacuum_analyze_scale_factor, vacuum_truncate)" % name))
    return names


def test_the_ones_there_take_it_once_and_a_new_one_is_made_with_it(world, monkeypatch, caplog):
    engine = world["engine"]
    assert _made_before_this(engine)
    before = _options(engine)
    assert before and set(before.values()) == {None}, before         # canary: partitions, none set yet
    assert set(_truncates(engine).values()) == {None}
    _settings(monkeypatch)                                            # absent: the default
    caplog.set_level(logging.INFO, logger=schema.logger.name)
    raw = engine.raw_connection()
    try:
        schema.say_autovacuum_runs(raw)
    finally:
        raw.close()
    done = _set(engine)
    assert sorted(done) == sorted(before), done
    assert set(_options(engine).values()) == {schema.AUTOANALYZE_DEFAULT}
    assert set(_truncates(engine).values()) == {"false"}
    assert any("[Ledger] autovacuum " in r.getMessage() and "track_counts=" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]
    assert _set(engine) == [], "again: none touched"
    _settings(monkeypatch, ledger_autoanalyze_scale_factor=0.05)
    assert sorted(_set(engine)) == sorted(before)                     # a different value: each set again
    name = _new(engine)
    assert _options(engine)[name] == 0.05 and _truncates(engine)[name] == "false"


def test_every_world_once_when_a_branch_operates(monkeypatch):
    """총괄 127139997: the default world and each branch, each once, whichever world operates - [None, *worlds()] read
    the operating branch twice and the default never. (No database: the parents asked are the claim.)"""
    asked = []

    class Session:
        def execute(self, sql, params=None):
            if "pg_inherits" in str(sql):
                asked.append(params["parent"])
            return []

        def commit(self):
            pass

    _settings(monkeypatch)
    monkeypatch.setattr(schema, "worlds", lambda: ["b1"])
    monkeypatch.setattr(schema, "operating_world", lambda: "b1")
    from runtime import maintenance_line

    assert maintenance_line._storage_tables(Session()) == []
    assert sorted(asked) == sorted([schema.world_names(schema.DEFAULT_WORLD).ledger,
                                    schema.world_names("b1").ledger]), asked


def test_null_leaves_the_factor_alone_and_still_stops_the_end_truncation(world, monkeypatch):
    engine = world["engine"]
    names = _made_before_this(engine)
    _settings(monkeypatch, ledger_autoanalyze_scale_factor=None)
    assert sorted(_set(engine)) == sorted(names), "vacuum_truncate is every partition's, whatever the setting"
    assert _set(engine) == []
    name = _new(engine)
    assert set(_options(engine).values()) == {None} and name in _options(engine)
    assert set(_truncates(engine).values()) == {"false"}


def test_a_partition_busy_past_the_lock_timeout_is_said_and_the_rest_go_on(world, monkeypatch, caplog):
    """A running vacuum holds SHARE UPDATE EXCLUSIVE; ALTER TABLE SET waits only `short_ddl`'s tries, its [DDL] line
    names that partition and the line goes on - the next merge tries again."""
    from parsers import directory_watcher

    engine = world["engine"]
    names = _made_before_this(engine)
    monkeypatch.setattr(directory_watcher, "ddl_lock_wait", lambda: (0.2, None))   # one try of 0.2 s
    _settings(monkeypatch)
    holder = engine.connect()
    try:
        held = holder.begin()
        holder.execute(text("LOCK TABLE %s IN SHARE UPDATE EXCLUSIVE MODE" % names[0]))
        caplog.set_level(logging.WARNING)
        assert sorted(_set(engine)) == sorted(names[1:])
        held.rollback()
    finally:
        holder.close()
    assert any("[DDL] storage on %s - its lock not had" % names[0] in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records]
    assert _set(engine) == [names[0]], "the next merge takes the one left"
