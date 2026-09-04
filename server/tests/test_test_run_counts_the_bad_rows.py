# -*- coding: utf-8 -*-
"""A refusal must say how many rows of how many, and in which column.

Owner, 2026-09-04: the test run refuses with "the time column is empty" on a source whose
time column is filled - and the ontology has not run in production for a month.

Both statements were true. The compile stops at the FIRST row it cannot use, so a page
that is 199 parts fine is reported as a failed declaration. Without a count an operator
cannot separate the two possible actions:

    my declaration is wrong          -> fix the declaration
    one row of my source is blank    -> fix that row, or accept it

"It is empty" supports neither.

⚠️ THE COUNT IS TAKEN ON THE SAME PAGE, WITH THE SAME PREDICATE. Same fetch, same order,
same size as the compile that refused, and `_is_missing` imported from the preparer that
raised rather than respelled - two spellings of "empty" would disagree on exactly the
values this question is about.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import backfill                                      # noqa: E402


class _Plan:
    pass


class _Setup:
    def __init__(self):
        self.snapshot = type("S", (), {"source_plans": {"probe": _Plan()}})()


class _Engine:
    """Hands back one page of rows, the way the real fetch does."""

    def __init__(self, rows):
        self.rows = rows
        self.fetches = 0

    def raw_connection(self):
        engine = self

        class _Conn:
            def rollback(self):
                pass

            def close(self):
                engine.fetches += 1

        return _Conn()


@pytest.fixture
def page(monkeypatch):
    def install(rows):
        monkeypatch.setattr(backfill, "_fetch_v2_lineage_page",
                            lambda connection, plan, after, limit: rows)
        return _Engine(rows)
    return install


def test_it_counts_the_empty_ones_and_the_whole_page(page):
    """🔴 THE TWO NUMBERS THE REFUSAL WAS MISSING. One bad row in two hundred reads very
    differently from two hundred bad rows, and the old message could not tell them apart.
    """
    rows = [{"t": "2026-01-01"} for _ in range(199)] + [{"t": None}]
    missing, read = backfill.count_rows_missing(page(rows), _Setup(), "probe", "t")
    assert (missing, read) == (1, 200)


def test_it_uses_THE_PREPARERS_predicate_and_not_a_local_one(page):
    """🔴 `NaT` IS THE CASE THAT SEPARATES THEM. A locally written "is it None" check would
    call a pandas NaT present, and a NaT is exactly what a datetime column reads as when
    the source has no time - so the count would say zero for the very rows the compile
    refused on. `_is_missing` is imported from the preparer that raised.
    """
    import pandas as pd

    rows = [{"t": "2026-01-01"}, {"t": pd.NaT}, {"t": float("nan")}]
    assert backfill.count_rows_missing(page(rows), _Setup(), "probe", "t") == (2, 3)


def test_a_blank_string_is_empty_too():
    """The preparer treats whitespace as absent, so this must as well - otherwise the
    count would say zero for the very rows that caused the refusal."""
    import pandas as pd
    from ledger.source_preparation import _is_missing
    assert _is_missing(None) and _is_missing(pd.NaT)
    assert not _is_missing("   ")          # the preparer pairs it with a strip() check
    # and the counter applies that pair, which is what this asserts through the count:
    rows = [{"t": "   "}, {"t": "2026-01-01"}]

    class _E:
        def raw_connection(self):
            class _C:
                def rollback(self): pass
                def close(self): pass
            return _C()

    import ledger.backfill as bf
    original = bf._fetch_v2_lineage_page
    bf._fetch_v2_lineage_page = lambda *a, **k: rows
    try:
        missing, read = bf.count_rows_missing(_E(), _Setup(), "probe", "t")
    finally:
        bf._fetch_v2_lineage_page = original
    assert (missing, read) == (1, 2)


def test_a_full_page_counts_zero_and_still_reports_the_size(page):
    """⚠️ Zero missing is an ANSWER, and a useful one: it says the refusal was NOT about
    this column, which sends the operator somewhere else entirely."""
    rows = [{"t": "2026-01-01"} for _ in range(5)]
    assert backfill.count_rows_missing(page(rows), _Setup(), "probe", "t") == (0, 5)


def test_an_empty_relation_is_zero_of_zero(page):
    """Not a division by anything, and not a failure: nothing was read."""
    assert backfill.count_rows_missing(page([]), _Setup(), "probe", "t") == (0, 0)
