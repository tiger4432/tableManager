# -*- coding: utf-8 -*-
"""판정 189. The UNIQUE index that makes `business_key_val` an enforced identity.

`models.py` keeps that column NON-unique on purpose — `create_all` does not add indexes to
tables that already exist, so declaring it there is a no-op on exactly the databases where
duplicates accumulate — and says the migration "belongs in the setup sequence and not only in
the upgrade one". Measured 2026-09-09: nothing invoked it. A fresh install enforced nothing,
and ㉡'s identity lookup is about to lean on this index.

⛔ IT IS NOT S-88's ONE-LINER, AND THAT IS THE WHOLE TEST. S-88's ensure only WEAKENS (adds a
column, drops a check) and cannot fail on existing rows. This one STRENGTHENS: on a table
carrying duplicates the build fails, so the surplus is counted FIRST and a table that cannot
take the index is NAMED and left alone. Creating nothing there is the correct outcome.

⚠️ AND AN INVALID LEFTOVER IS NOT "ALREADY DONE". A cancelled CONCURRENTLY build leaves an
index under the right NAME enforcing nothing — so the predicate is 「a VALID unique index on
exactly (business_key_val)」, never 「the name exists」.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                              # noqa: E402


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execution_options(self, **kw):
        return self

    def execute(self, *a, **k):                       # the DDL door's SET / RESET and the leftover probe (none)
        return _Scalar()

    def close(self):
        pass

    def invalidate(self):
        pass

    def rollback(self):                               # the census's read ends before a build
        pass


class _Scalar:
    def scalar(self):
        return 0


class _Engine:
    def __init__(self):
        self.autocommit_asked = False

    def connect(self):
        conn = _Conn()
        engine = self

        def execution_options(**kw):
            if kw.get("isolation_level") == "AUTOCOMMIT":
                engine.autocommit_asked = True
            return conn

        conn.execution_options = execution_options
        return conn


class _Session:
    def __init__(self, engine):
        self._engine = engine

    def get_bind(self):
        return self._engine

    def close(self):
        pass


def run(monkeypatch, *, tables, existing, census, build=("created", "ok")):
    """Drive the ensure with the migration module's four questions stubbed."""
    from migrations import add_business_key_unique_index as uq

    monkeypatch.setattr(uq, "tables_with_business_key", lambda conn: list(tables))
    monkeypatch.setattr(uq, "existing_unique_index", lambda conn, t: existing.get(t))
    monkeypatch.setattr(uq, "duplicate_census",
                        lambda conn, t, **kw: dict(census[t], table=t))
    monkeypatch.setattr(uq, "unique_index_name", lambda t: f"uq_bk_{t}")
    monkeypatch.setattr(uq, "build_index", lambda conn, t, name: build)

    engine = _Engine()
    return worker._ensure_business_key_unique_indexes_sync(
        lambda: _Session(engine)), engine


def test_a_clean_table_gets_its_index(monkeypatch):
    out, engine = run(monkeypatch, tables=["clean"], existing={},
                      census={"clean": {"surplus": 0}})

    assert out["built"] == [("clean", "created", "ok")]
    assert out["refused"] == [] and out["invalid"] == []
    assert engine.autocommit_asked, (
        "CONCURRENTLY cannot run inside a transaction — the build needs AUTOCOMMIT")


def test_a_table_with_duplicates_is_named_and_left_alone(monkeypatch):
    """🔴 THE GUARD. Creating nothing is correct here; the SURPLUS is what an operator needs
    in order to decide whether to clean. A count of refusals would not be actionable."""
    out, engine = run(monkeypatch, tables=["dirty"], existing={},
                      census={"dirty": {"surplus": 7}})

    assert out["refused"] == [("dirty", 7)]
    assert out["built"] == []
    assert not engine.autocommit_asked, "no DDL may be attempted on a table that refused"


def test_a_valid_index_is_left_alone_an_invalid_leftover_is_rebuilt_and_another_name_is_named(monkeypatch):
    """⚠️ 「the name exists」 IS NOT THE PREDICATE. An invalid leftover under the unique name enforces nothing, and
    since 총괄 49792d3f6 A it is the leftover of a build that gave up its wait - dropped and built again here. An
    invalid index under another name is not this build's, and is named."""
    out, _engine = run(
        monkeypatch, tables=["ok", "leftover", "other"],
        existing={"ok": ("uq_bk_ok", True), "leftover": ("uq_bk_leftover", False), "other": ("custom", False)},
        census={"leftover": {"surplus": 0}})

    assert out["built"] == [("leftover", "created", "ok")] and out["refused"] == []
    assert out["invalid"] == [("other", "custom")]


def test_the_scheduler_s_line_builds_it_and_the_chain_start_does_not():
    """소유자 10-15: the chain worker builds no index; the scheduler's line does, a failure a line."""
    import inspect

    from runtime import maintenance_line

    assert "_ensure_business_key_unique_indexes_sync" in inspect.getsource(maintenance_line._start_work)
    assert "business_key" not in inspect.getsource(worker.start_chain_ingestion_worker)
    assert "logger.error" in inspect.getsource(maintenance_line._each), "a failure is named, not fatal"
