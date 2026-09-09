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

import chain_ingestion_worker as worker                              # noqa: E402


class _Conn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execution_options(self, **kw):
        return self


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


def test_a_valid_index_is_left_alone_and_an_invalid_one_is_named(monkeypatch):
    """⚠️ 「the name exists」 IS NOT THE PREDICATE. An invalid leftover holds the name and
    enforces nothing, so treating it as done would ship the silent hole the script exists to
    close — and dropping it belongs to an operator, not to a daemon at startup."""
    out, _engine = run(
        monkeypatch, tables=["ok", "leftover"],
        existing={"ok": ("uq_bk_ok", True), "leftover": ("uq_bk_leftover", False)},
        census={})

    assert out["built"] == [] and out["refused"] == []
    assert out["invalid"] == [("leftover", "uq_bk_leftover")]


def test_the_startup_calls_it_and_survives_it(monkeypatch):
    """A daemon that also does chain work must not fail to start because an index could not
    be built — the same shape S-88 landed for the ledger schema."""
    import inspect

    body = inspect.getsource(worker.start_chain_ingestion_worker)
    assert "_ensure_business_key_unique_indexes_sync" in body
    after = body.split("_ensure_business_key_unique_indexes_sync")[1][:400]
    assert "logger.error" in after, "a failure here is named, not fatal"
