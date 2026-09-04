# -*- coding: utf-8 -*-
"""The repair that closes a declaration/database gap must say when it cannot.

`sync_dynamic_tables_schema` is the one thing that adds a column the declaration says a
table has and the database does not. Measured 2026-09-04 on this workstation: it was
failing on 28 statements across 9 relations at EVERY boot and reporting it with a bare
`print` - not a logger, not /health, not any screen. The first anyone heard of it was
`/dashboard/summary` answering 500 much later, which took the two core-value meters with
it.

🔴 THE FOURTH OF THE SAME CLASS TODAY: the beat lived inside the tick, the sweep inside
the worker it protects, the cancel check inside the batch - and the repair's failure
inside a print. This one is the worst, because it is the REPAIR.

⚠️ AND IT STILL MUST NOT RAISE. A boot that dies because one column could not be added is
worse than a boot that says so and carries on; what was missing was the saying.
"""
import logging
import os
import sys

import pytest
import sqlalchemy

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import models                                      # noqa: E402


# A REAL SQLAlchemy column, because the function under test compiles it into DDL - a
# stand-in object would fail inside the compiler and the test would be measuring the
# stand-in rather than the repair.
_PROBE_METADATA = sqlalchemy.MetaData()
_PROBE_TABLE = sqlalchemy.Table(
    "probe_relation", _PROBE_METADATA,
    sqlalchemy.Column("created_at", sqlalchemy.DateTime(timezone=True)))


class _Model:
    __table__ = _PROBE_TABLE


class _EngineThatCannotAlter:
    """An engine whose ALTER always fails - the way one against a VIEW does."""

    def __init__(self):
        self.dialect = sqlalchemy.create_engine("sqlite://").dialect

    def begin(self):
        raise RuntimeError(
            'cannot ALTER ... ADD COLUMN on relation "probe_relation": it is a view')


class _Inspector:
    """Says the relation exists and lacks exactly the declared column."""

    def has_table(self, name):
        return True

    def get_columns(self, name):
        return [{"name": "some_source_column"}]


@pytest.fixture
def one_unrepairable_table(monkeypatch):
    monkeypatch.setattr(models, "DYNAMIC_TABLES", {"probe_relation": _Model})
    monkeypatch.setattr(sqlalchemy, "inspect", lambda target: _Inspector())
    return "probe_relation"


def test_a_repair_that_cannot_run_is_logged_BY_NAME(caplog, one_unrepairable_table):
    """🔴 The relation, the column AND the reason all travel. A line that said only
    "schema sync failed" sends whoever reads it back into the code to find out which of
    forty-four declared tables it meant, and why."""
    with caplog.at_level(logging.ERROR, logger="Server"):
        models.sync_dynamic_tables_schema(_EngineThatCannotAlter())

    said = "\n".join(r.getMessage() for r in caplog.records)
    assert "Schema Sync" in said, said
    assert one_unrepairable_table in said, said
    assert "created_at" in said, said
    assert "view" in said, (
        "the reason itself has to travel - the fact of failure alone is what a print "
        "already gave, and it is not enough to act on")


def test_it_is_logged_at_ERROR_not_swallowed_into_debug(caplog, one_unrepairable_table):
    """A repair that cannot run is not a detail. At DEBUG it is invisible in every
    deployment that does not turn DEBUG on, which is all of them."""
    with caplog.at_level(logging.DEBUG, logger="Server"):
        models.sync_dynamic_tables_schema(_EngineThatCannotAlter())
    assert any(r.levelno >= logging.ERROR for r in caplog.records), \
        [(r.levelname, r.getMessage()) for r in caplog.records]


def test_a_failing_repair_does_not_take_the_boot_down(one_unrepairable_table):
    """🔴 The behaviour that must NOT change. It already carried on; the silence was the
    defect, not the survival."""
    models.sync_dynamic_tables_schema(_EngineThatCannotAlter())    # must not raise
