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

    views = ()

    def has_table(self, name):
        return True

    def get_columns(self, name):
        return [{"name": "some_source_column"}]

    def get_view_names(self):
        return list(self.views)


class _ViewInspector(_Inspector):
    """The same relation, but the database holds a VIEW under that name."""

    views = ("probe_relation",)


class _EngineThatCountsAlters(_EngineThatCannotAlter):
    """Records every ALTER attempt, so "did not try" is checkable, not assumed."""

    def __init__(self):
        super().__init__()
        self.attempts = 0

    def begin(self):
        self.attempts += 1
        return super().begin()


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


# --------------------------------------------------- a declared relation that is a VIEW

@pytest.fixture
def one_declared_view(monkeypatch):
    monkeypatch.setattr(models, "DYNAMIC_TABLES", {"probe_relation": _Model})
    monkeypatch.setattr(sqlalchemy, "inspect", lambda target: _ViewInspector())
    return "probe_relation"


def test_a_declared_view_is_named_once_instead_of_failing_per_column(
        caplog, one_declared_view):
    """🔴 ONE LINE PER RELATION, NOT ONE PER COLUMN. Measured 2026-09-04: nine declared
    views produced 28 identical failures per boot, which is 28 chances to read the same
    fact and no chance to read it as one.

    And the line has to carry WHY - a view has exactly the columns its own query selects,
    so the declaration's extra ones are not missing, they are unattainable there.
    """
    engine = _EngineThatCountsAlters()
    with caplog.at_level(logging.ERROR, logger="Server"):
        models.sync_dynamic_tables_schema(engine)

    lines = [r.getMessage() for r in caplog.records if "Schema Sync" in r.getMessage()]
    assert len(lines) == 1, lines
    assert "VIEW" in lines[0], lines[0]
    assert "created_at" in lines[0], "the line must say what could not be added"
    assert engine.attempts == 0, (
        "an ALTER was still issued against a view; it can never succeed")


def test_a_declared_view_is_NOT_passed_over_in_silence(caplog, one_declared_view):
    """⛔ Skipping quietly is the defect this whole day was about. The relation is named
    even though nothing can be done about it here."""
    with caplog.at_level(logging.ERROR, logger="Server"):
        models.sync_dynamic_tables_schema(_EngineThatCountsAlters())
    assert any("probe_relation" in r.getMessage() for r in caplog.records)


def test_a_declared_view_is_not_REFUSED_either(one_declared_view):
    """⛔ "a view may not be declared" is a policy, and policy is the owner's. This
    function reports and carries on."""
    models.sync_dynamic_tables_schema(_EngineThatCountsAlters())   # must not raise


def test_a_real_table_still_gets_its_ALTER(caplog, one_unrepairable_table):
    """🔴 NO REGRESSION. The view branch must not swallow the ordinary path: a genuine
    table with a missing column is still attempted, and its failure still speaks."""
    engine = _EngineThatCountsAlters()
    with caplog.at_level(logging.ERROR, logger="Server"):
        models.sync_dynamic_tables_schema(engine)
    assert engine.attempts == 1, "the ordinary repair stopped being attempted"
    assert any("could not add column" in r.getMessage() for r in caplog.records)


class _HealthyViewInspector(_ViewInspector):
    """A declared view whose query DOES select every declared column."""

    def get_columns(self, name):
        return [{"name": "created_at"}]


def test_a_view_that_lacks_nothing_is_said_but_not_cried_about(caplog, monkeypatch):
    """🔴 FOUND BY COUNTING KINDS INSTEAD OF FAILURES. Nine views were visible because
    they produced failing ALTERs; a TENTH is a view too, and invisible that way, because
    its query selects everything the declaration names. Nothing about it is wrong today.

    So it is still SAID - a declared view is worth knowing before its query changes - but
    not at ERROR. A status line that cries wolf about its own bookkeeping is worse than
    none, which this repository has already ruled once.
    """
    monkeypatch.setattr(models, "DYNAMIC_TABLES", {"probe_relation": _Model})
    monkeypatch.setattr(sqlalchemy, "inspect", lambda target: _HealthyViewInspector())

    with caplog.at_level(logging.DEBUG, logger="Server"):
        models.sync_dynamic_tables_schema(_EngineThatCountsAlters())

    said = [r for r in caplog.records if "Schema Sync" in r.getMessage()]
    assert len(said) == 1, [r.getMessage() for r in said]
    assert said[0].levelno == logging.INFO, said[0].levelname
    assert "VIEW" in said[0].getMessage()
