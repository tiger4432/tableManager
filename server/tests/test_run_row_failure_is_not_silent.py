# -*- coding: utf-8 -*-
"""A run row that cannot be updated is the most expensive silence in this system.

`_mark_run` writes on its own session and swallowed every failure at debug level. When
that update fails the WORK still runs - only the record stops - so the row keeps saying
`queued` with no `started_at` and every screen reads "waiting" while the operation is in
flight. Measured cause 2026-09-05: deploying the `runner` column before its migration
makes each UPDATE raise UndefinedColumn, and nothing above debug would ever say so.

⛔ AND IT STILL MUST NOT RAISE. A bookkeeping failure that kills the run is worse than a
loud one, so it is reported and counted instead - and the count travels with the queue,
because a log line nobody tails is the same silence in a different place.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import retroactive                                               # noqa: E402


@pytest.fixture(autouse=True)
def clean():
    del retroactive._RECORD_FAILURES[:]
    yield
    del retroactive._RECORD_FAILURES[:]


class _Exploding:
    """A session whose UPDATE fails the way a missing column does."""
    def query(self, *a, **k):
        raise RuntimeError("UndefinedColumn: retroactive_runs.runner")

    def rollback(self):
        pass

    def close(self):
        pass


def test_the_failure_is_reported_at_error_not_debug(monkeypatch, caplog):
    monkeypatch.setattr(retroactive, "SessionLocal", _Exploding, raising=False)
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    with caplog.at_level(logging.ERROR):
        retroactive._mark_run("run-1", state="running", started=True)
    said = "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)
    assert "run-1" in said
    assert "migrations" in said, "the message does not point at the likely cause"


def test_the_run_is_not_killed_by_a_bookkeeping_failure(monkeypatch):
    """⛔ The work must survive losing its own record."""
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    retroactive._mark_run("run-2", state="running", started=True)   # must not raise


def test_the_failure_travels_as_a_value(monkeypatch):
    """🔴 A log line nobody tails is the same silence somewhere else."""
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    retroactive._mark_run("run-3", state="running", started=True)
    failures = retroactive.record_failures()
    assert [f["run_id"] for f in failures] == ["run-3"]
    assert "UndefinedColumn" in failures[0]["error"]


def test_no_failure_is_the_normal_empty_answer():
    assert retroactive.record_failures() == []


def test_the_list_is_bounded(monkeypatch):
    """It must not grow without limit while a deployment stays broken."""
    monkeypatch.setattr("database.database.SessionLocal", _Exploding)
    for i in range(40):
        retroactive._mark_run("run-%d" % i, state="running", started=True)
    assert len(retroactive.record_failures()) == 20
