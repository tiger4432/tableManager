# -*- coding: utf-8 -*-
"""Lead 11-13 (TO_MOVE B): boot ANALYZE names its tables through `lines.base_tables` - a declared table, its line
table and nothing undeclared - and asks the statistics view for those names only."""
import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from database import crud

pytestmark = pytest.mark.pg
TABLE = "boot_an_probe"
NAMES = (TABLE, TABLE + "__lines", "boot_an_not_ours")


@pytest.fixture(name="stale")
def fixture_stale(pg_engine, monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, {})
    with pg_engine.begin() as conn:
        for name in NAMES:
            conn.execute(text('CREATE TABLE "%s" (k int)' % name))
            conn.execute(text('INSERT INTO "%s" SELECT g FROM generate_series(1, 300) g' % name))
        conn.execute(text("SELECT pg_stat_force_next_flush()"))     # PG15+: the counters reach the view late
    try:
        yield pg_engine
    finally:
        with pg_engine.begin() as conn:
            for name in NAMES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"' % name))


def test_a_declared_tables_line_table_is_analysed_at_boot_and_an_undeclared_one_is_not(stale, monkeypatch):
    from chain import ingestion_worker as worker
    from parsers import directory_watcher as dw

    with stale.connect() as conn:
        modified = dict(conn.execute(text(
            "SELECT relname, n_mod_since_analyze FROM pg_stat_user_tables WHERE relname = ANY(:n)"),
            {"n": list(NAMES)}).all())
    assert all(modified.get(n, 0) >= 300 for n in NAMES), modified          # canary: all three are stale

    monkeypatch.setattr(dw, "analyze_after_rows", lambda: 100)
    analysed = []
    monkeypatch.setattr(dw, "_analyze_after_load",
                        lambda name, rows, why=None, forced=False: analysed.append(name) or True)

    worker._analyze_stale_tables_sync(sessionmaker(bind=stale))
    assert TABLE in analysed and TABLE + "__lines" in analysed, analysed
    assert "boot_an_not_ours" not in analysed, analysed
