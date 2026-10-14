"""총괄 53338e99b (소유자 «오토 애널라이즈를 걸면 되지 않나» · «ㅇㅇ»): the ledger partitions'
`autovacuum_analyze_scale_factor` from one setting, `ledger_autoanalyze_scale_factor` (absent 0.02, null: hands off).

  a new one    made with it, where partitions are made (`ensure_partition`)
  the ones there   given it at the ledger process's start where theirs differs; again: none touched
  null         nothing written - a new partition and the ones there keep their own
  the line     whether autovacuum runs, said at the start
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


def _set(engine):
    raw = engine.raw_connection()
    try:
        return schema.set_partitions_autoanalyze(raw)
    finally:
        raw.close()


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
            conn.execute(text("ALTER TABLE %s RESET (autovacuum_analyze_scale_factor)" % name))
    return names


def test_the_ones_there_take_it_once_and_a_new_one_is_made_with_it(world, monkeypatch, caplog):
    engine = world["engine"]
    assert _made_before_this(engine)
    before = _options(engine)
    assert before and set(before.values()) == {None}, before         # canary: partitions, none set yet
    _settings(monkeypatch)                                            # absent: the default
    caplog.set_level(logging.INFO, logger=schema.logger.name)
    done = _set(engine)
    assert sorted(done) == sorted(before), done
    assert set(_options(engine).values()) == {schema.AUTOANALYZE_DEFAULT}
    assert any("[Ledger] autovacuum " in r.getMessage() and "track_counts=" in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]
    assert _set(engine) == [], "again: none touched"
    _settings(monkeypatch, ledger_autoanalyze_scale_factor=0.05)
    assert sorted(_set(engine)) == sorted(before)                     # a different value: each set again
    name = _new(engine)
    assert _options(engine)[name] == 0.05


def test_null_writes_nothing(world, monkeypatch):
    engine = world["engine"]
    _made_before_this(engine)
    _settings(monkeypatch, ledger_autoanalyze_scale_factor=None)
    assert _set(engine) == []
    name = _new(engine)
    assert set(_options(engine).values()) == {None} and name in _options(engine)
