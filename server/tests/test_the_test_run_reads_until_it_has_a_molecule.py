# -*- coding: utf-8 -*-
"""S-44: the test run's sample is MOLECULES, and it reads onward to find them.

🔴 THE HEAD OF A SOURCE IS STRUCTURALLY THE WORST PLACE TO SAMPLE. The grid makes keyless
rows (`create_empty_rows_batch` writes NULL keys) and initial history rows sort first, so
"the first 200 rows" is precisely the window most likely to hold none of the operator's
data. The owner met it head-on: 「꽉 찬 행만 샘플링해야 하는 거 아니야? 빈 행 200개 잡아서
안 도는 것 같은데」.

🔴 WHY THE ENGINE IS A STUB HERE AND NOT `test_ledger_v2_pg.py`'s FIXTURE. That fixture is
opt-in on `ASSY_PG_TEST_DATABASE_URL`, and without it every test in that file SKIPS - a
gate written there is green because it never ran. This stub is a small relation that
honours the paging predicate the reader actually sends, so the loop under test is the real
one; only the rows come from memory.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ledger import backfill                                            # noqa: E402
from ledger.setup import load_setup                                    # noqa: E402


SOURCE = "lot_event"
NOW = pd.Timestamp("2026-08-17T10:00:00+09:00")


def _row(index, *, filled=True):
    """One source row. `filled=False` is the shape the grid leaves behind: the row is
    there, its declared identity is not."""
    return {
        "lot_id": ("P%03d" % index) if filled else None,
        "event_type": "split" if filled else None,
        "slotnumbers": "1" if filled else None,
        "waferids": "W1" if filled else None,
        "parent_lot": "", "child_lot": "",
        "txn_seq": "R%03d" % index,
        "event_time": NOW + pd.Timedelta(seconds=index),
        "row_id": "ROW-%03d" % index,
    }


class _StubCursor:
    def __init__(self, relation, page_key):
        self._relation, self._page_key, self._rows = relation, page_key, []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, query, params=None):
        # The reader composes `... WHERE key > %s ... LIMIT %s`; the stub reads the two
        # values it binds rather than the SQL, and serves the same window a relation would.
        params = list(params or ())
        limit = params[-1] if params else None
        after = params[0] if len(params) > 1 else None
        rows = self._relation
        if after is not None:
            rows = [r for r in rows if r[self._page_key] > after]
        self._rows = rows[:limit] if limit else rows

    @property
    def description(self):
        return [(name,) for name in (self._relation[0].keys() if self._relation else ())]

    def fetchall(self):
        return [tuple(row.values()) for row in self._rows]


class _StubConnection:
    def __init__(self, relation, page_key):
        self._relation, self._page_key = relation, page_key
        self.pages = 0

    def cursor(self):
        self.pages += 1
        return _StubCursor(self._relation, self._page_key)

    def rollback(self):
        pass

    def close(self):
        pass


class _StubEngine:
    def __init__(self, relation, page_key):
        self.connection = _StubConnection(relation, page_key)

    def raw_connection(self):
        return self.connection


@pytest.fixture(scope="module")
def setup():
    return load_setup()


def _read(setup, relation, fetch_rows=4):
    plan = setup.snapshot.source_plans[SOURCE]
    engine = _StubEngine(relation, plan.driver.cursor_columns[0])
    return backfill.preview_first_batch(engine, setup, SOURCE, fetch_rows=fetch_rows)


def test_a_head_of_unusable_rows_does_not_decide_the_answer(setup):
    """㉠ The whole point, end to end on the production declaration. The head compiles no
    molecule and the run keeps reading until one does.

    ⚠️ MEASURED, NOT ASSUMED: on `lot_event` a blank row does NOT become a named refusal.
    Its entity identity columns are `lot` and `wafers`, both PREPARER OUTPUTS, and the
    preparer marks such a row EXCLUDED before molecules exist - so it leaves as
    `rows_read` with no molecule and no refusal. Excluded, refused and absent are three
    states, and this fixture is the first: a head that produces nothing, which is exactly
    the shape the owner hit."""
    relation = [_row(i, filled=False) for i in range(8)] + [_row(i) for i in range(8, 12)]

    reading = _read(setup, relation)

    assert reading.pages > 1, "one page of unusable rows must not be the whole answer"
    assert reading.preview is not None
    assert reading.preview.molecule_count >= 1
    assert reading.rows_read > 8


def test_a_source_with_no_usable_row_answers_with_values_not_an_exception(setup):
    """㉡ Read in full, answered in full. `molecules == 0` beside `rows_read > 0` is an
    ANSWER; raising here would put the operator back where S-41 found them."""
    relation = [_row(i, filled=False) for i in range(6)]

    reading = _read(setup, relation)

    assert reading.rows_read > 0
    assert reading.preview is not None
    assert reading.preview.molecule_count == 0


def test_a_source_whose_head_is_full_is_answered_by_its_first_page(setup):
    """㉢ Nothing changes for the ordinary case: one page in, one page read. The budget
    only spends where the old reading would have answered wrongly."""
    relation = [_row(i) for i in range(6)]

    reading = _read(setup, relation)

    assert reading.pages == 1
    assert reading.preview.molecule_count >= 1
    assert reading.refusals == ()


def test_the_budget_stops_the_walk_rather_than_scanning_the_table(setup):
    """The instrument has a budget and it is a CONSTANT, not a declaration axis - an
    operator does not author how far a probe reads. Without it a source whose rows are all
    blank turns one screen into a full scan."""
    relation = [_row(i, filled=False) for i in range(200)]

    reading = _read(setup, relation, fetch_rows=4)

    assert reading.pages == backfill.PREVIEW_MAX_PAGES
    assert reading.rows_read < len(relation)


def test_the_walk_reads_forward_and_never_re_reads_a_page(setup):
    """The paging predicate is the reader's own `key > after`. A walk that forgot to
    advance would loop on page one forever and still look like it found nothing."""
    relation = [_row(i, filled=False) for i in range(8)] + [_row(i) for i in range(8, 12)]

    reading = _read(setup, relation)

    assert reading.rows_read <= len(relation), "a row was read twice"


# ---------------------------------------------------------------------------
# The walk's own contract, isolated from what any one declaration refuses.
#
# 🔴 THE FIXTURE ABOVE CANNOT PRODUCE A NAMED REFUSAL, and pretending otherwise is how a
# gate ends up green on a path it never walks. `lot_event` excludes its unusable rows
# before molecules exist. The two facts this section pins - the walk stops as soon as a
# page compiles, and refusals ACCUMULATE across every page it walked - are properties of
# the loop, so they are measured against a compiler that says what it compiled.
# ---------------------------------------------------------------------------

class _Refusal:
    def __init__(self, reason):
        self.reason, self.detail, self.rows, self.addresses = reason, "d", 1, ()


class _Compiled:
    def __init__(self, molecules, refusals):
        self.molecule_count, self.refusals = molecules, tuple(refusals)


def _compiler(script):
    """One scripted answer per page, in order."""
    calls = iter(script)

    def compile_one(setup, source, frame, cursor_value, reader, known_registrations=None):
        return next(calls)
    return compile_one


def test_the_walk_stops_at_the_first_page_that_compiles(setup, monkeypatch):
    monkeypatch.setattr("ledger.setup.preview_selected_cursor_batch", _compiler([
        _Compiled(0, [_Refusal("no_identity")]),
        _Compiled(2, []),
        _Compiled(9, []),                      # must never be asked for
    ]))
    reading = _read(setup, [_row(i) for i in range(12)], fetch_rows=4)

    assert reading.pages == 2
    assert reading.preview.molecule_count == 2


def test_refusals_from_the_pages_walked_past_are_not_lost(setup, monkeypatch):
    """The head is part of what this run read. Reporting only the answering page would
    hide exactly the rows the operator has to fix."""
    monkeypatch.setattr("ledger.setup.preview_selected_cursor_batch", _compiler([
        _Compiled(0, [_Refusal("no_identity"), _Refusal("missing_occurred_at")]),
        _Compiled(0, [_Refusal("no_identity")]),
        _Compiled(1, []),
    ]))
    reading = _read(setup, [_row(i) for i in range(12)], fetch_rows=4)

    assert reading.pages == 3
    assert [r.reason for r in reading.refusals] == [
        "no_identity", "missing_occurred_at", "no_identity"]
