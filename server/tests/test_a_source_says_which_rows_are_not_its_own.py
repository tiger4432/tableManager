# -*- coding: utf-8 -*-
"""S-91. A source declares which rows are not its own, in the DECLARATION.

🔴 THE MECHANISM ALREADY EXISTED AND ONLY PYTHON COULD REACH IT. `__source_row_excluded`
has been read by `_assemble_prepared_frame` for weeks - it drops those rows and counts them
- but the only thing that ever emitted it was a preparer CLASS. The shipped `table_config`
sample says so in its own comment: "the only row-exclusion mechanism is emitted by a
preparer implementation -- the live config declares zero `source_preparers`".

So a relation whose EARLY rows leave an identity part blank made no atoms at all, and the
remedy was to write a python preparer. Measured in production 2026-09-09: 995 rows read, 0
molecules, 995 refused for no identity, with the rows that carry one sitting later in cursor
order.

Two lines an operator can act on:
    「운영에서는 소스의 `read` 에 `exclude_when: [{column: <컬럼>, blank: true}]` 을 적으면
      그 컬럼이 빈 행은 «제외»되고 나머지가 들어갑니다.」

⛔ ONE PREDICATE ON PURPOSE. `blank: true` and nothing else - no value comparisons, no SQL
fragment in the declaration, no "skip the first row". A grammar that grows an operator per
question stops being a declaration.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger.backfill import prepare_v2_cursor_batch                   # noqa: E402
from ledger.event_frame import is_blank_source_value                  # noqa: E402
from test_ledger_setup_bundle import (                                # noqa: E402
    logical_bundle, logical_catalog, validate_bundle_errors)
from test_ledger_setup_registry import snapshot                       # noqa: E402
from test_ledger_event_frame import (                                 # noqa: E402
    NOW, base_rows, base_select_columns_of)

SOURCE = "input_rows"


def _with_exclusion(clauses, bundle=None):
    raw = bundle if bundle is not None else logical_bundle()
    raw["sources"][SOURCE]["read"]["exclude_when"] = clauses
    return raw


def paths_of(bundle):
    return {issue.path for issue in
            validate_bundle_errors(bundle, catalog=logical_catalog())}


# ---------------------------------------------------------------- the behaviour

def test_a_declared_blank_column_excludes_that_row_and_the_rest_still_land():
    """🔴 THE HEADLINE. The excluded rows leave, and the ones that carry an identity are
    translated exactly as before."""
    def run(bundle):
        base = base_rows(3)
        base["event_at"] = [NOW, NOW, NOW]
        base["join_id"] = ["", "   ", base["join_id"].tolist()[2]]
        frames = prepare_v2_cursor_batch(snapshot(bundle), SOURCE, base)
        return frames, sum(len(frame) for frame in frames)

    plain = _with_exclusion([])
    del plain["sources"][SOURCE]["read"]["exclude_when"]
    _before, landed_before = run(plain)
    assert landed_before == 3, "precondition: without the clause every row is translated"

    frames, landed = run(_with_exclusion([{"column": "join_id", "blank": True}]))

    assert landed == 1, (
        f"two rows leave `join_id` blank and were declared not this source's; got {landed}")
    assert [frame["source_id"].tolist() for frame in frames] == [["IN-0002"]], (
        "the row that landed must be the one whose `join_id` is filled")


def test_a_column_named_only_by_the_clause_still_reaches_the_read():
    """🔴 THE QUIET ONE. A column named ONLY by `exclude_when` is neither an identity, a
    cursor column, nor anybody's declared input, so nothing else would select it and the
    preparer would be handed a frame without the column it was told to judge.

    ⚠️ THIS ASSERTION COULD NOT FAIL UNTIL 판정 204. Every physical column of this fixture's
    relation was already pulled into the read by something, so there was no column whose
    ABSENCE the test could observe - it passed whatever the code did. `unselected_note` is
    declared in the catalogue and selected by nothing, which is what makes the mutation
    below real.
    """
    from ledger.event_frame import bound_select_columns

    plain = bound_select_columns(snapshot(logical_bundle()).source_plans[SOURCE])
    assert "unselected_note" not in plain, "precondition: nothing else names it"

    compiled = snapshot(_with_exclusion([{"column": "unselected_note", "blank": True}]))

    assert "unselected_note" in bound_select_columns(compiled.source_plans[SOURCE]), (
        "a column named only by the clause is named")
    assert "unselected_note" in base_select_columns_of(compiled, SOURCE)


def test_blank_is_spelled_once_for_the_clause_and_for_the_census():
    """판정 194 ㉢. `count_rows_missing` and this clause ask the SAME question, so they call
    the same function - two spellings would disagree about exactly the values in dispute."""
    assert is_blank_source_value(None)
    assert is_blank_source_value("")
    assert is_blank_source_value("   ")
    assert not is_blank_source_value("0")
    assert not is_blank_source_value(0)


# ---------------------------------------------------------------- the refusals

def test_a_column_the_relation_does_not_have_is_refused_by_name():
    before = paths_of(logical_bundle())
    after = paths_of(_with_exclusion([{"column": "not_a_column", "blank": True}]))

    new = after - before
    assert any("exclude_when[0].column" in path for path in new), sorted(new)


def test_a_predicate_other_than_blank_is_refused():
    """⛔ The grammar does not grow an operator because a source wanted one. `blank: false`
    is refused too: "keep only the blanks" is a different feature and has to be asked for."""
    before = paths_of(logical_bundle())

    other = paths_of(_with_exclusion([{"column": "join_id", "equals": "X"}])) - before
    assert other, "an unknown predicate must not be accepted"

    negated = paths_of(_with_exclusion([{"column": "join_id", "blank": False}])) - before
    assert any("blank" in path for path in negated), sorted(negated)


# ⚰️ RETIRED with the preparer (setup_version 6): `test_declaring_it_under_a_preparer_that_
# cannot_read_it_is_refused` (판정 194 ㉡). The clause is applied by the event frame on every
# source now, so there is no implementation under which it could silently do nothing.
