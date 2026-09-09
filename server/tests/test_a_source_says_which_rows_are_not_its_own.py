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
    「운영에서는 소스의 `prepare` 에 `exclude_when: [{column: <컬럼>, blank: true}]` 을 적으면
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
from ledger.source_preparation import (                               # noqa: E402
    SOURCE_ROW_EXCLUDED_COLUMN, SourcePreparationError,
    is_blank_source_value)
from test_ledger_setup_bundle import (                                # noqa: E402
    driver_preparation, logical_bundle, logical_catalog,
    validate_bundle_errors)
from ledger.setup_registry import TrustedImplementationCatalog        # noqa: E402
from ledger.source_preparation import locked_select_columns           # noqa: E402
from test_ledger_setup_registry import snapshot                       # noqa: E402
from ledger.source_preparation import (                               # noqa: E402
    DirectJoinSourcePreparer, SourcePreparerImplementationRegistry)
from test_ledger_source_preparation import (                          # noqa: E402
    NOW, base_rows, reader_for)

SOURCE = "input_rows"


def direct_join_trusted():
    """The fixture plant trusts `prepare-input`; `exclude_when` is read only by the
    GENERIC preparer, so driving it end to end needs `direct-join` trusted instead."""
    return TrustedImplementationCatalog.build(
        source_preparers=[("direct-join", 1)],
        mappers=[("map-transition-role", 1)],
    )


def direct_join_registry():
    """The RUNTIME half of the same swap: the shared helper registers the class under the
    fixture's `prepare-input` id, and this clause is only read under `direct-join`."""
    registry = SourcePreparerImplementationRegistry()
    registry.register("direct-join", 1, DirectJoinSourcePreparer)
    return registry.seal()


def _with_exclusion(clauses, bundle=None, direct=False):
    raw = bundle if bundle is not None else logical_bundle()
    prep = driver_preparation(raw)
    prep["exclude_when"] = clauses
    if direct:
        # The fixture ships `prepare-input`; only `direct-join` reads the clause, which is
        # the refusal pinned at the bottom of this file.
        prep["implementation_id"] = "direct-join"
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
        compiled = snapshot(bundle, direct_join_trusted())
        frames = prepare_v2_cursor_batch(compiled, SOURCE, base,
                                         reader_for(base), direct_join_registry())
        return frames, sum(len(frame) for frame in frames)

    plain = _with_exclusion([], direct=True)
    del driver_preparation(plain)["exclude_when"]
    _before, landed_before = run(plain)
    assert landed_before == 3, "precondition: without the clause every row is translated"

    frames, landed = run(_with_exclusion([{"column": "join_id", "blank": True}],
                                         direct=True))

    assert landed == 1, (
        f"two rows leave `join_id` blank and were declared not this source's; got {landed}")
    # ⚠️ THE MARKER COLUMN SURVIVES ON THE FRAME, and asserting otherwise was MY
    # expectation rather than this seam's contract - `_assemble_prepared_frame` filters
    # ROWS and does not drop the column, exactly as it already did for the python preparer
    # that has emitted it for weeks. What is worth pinning is that nothing marked stayed.
    for frame in frames:
        assert not any(frame[SOURCE_ROW_EXCLUDED_COLUMN].tolist()), (
            "a row the declaration excluded is still in the prepared frame")


def test_a_column_named_only_by_the_clause_still_reaches_the_read():
    """🔴 THE QUIET ONE, AND IT IS WHY THIS FILE EXISTS AT ALL.

    The read selects identity, group_by, order_by, cursor, occurred_at, the preparer's and
    mapper's inputs, and `row_id`. A column named ONLY by `exclude_when` is in none of
    those, so without this term the preparer is handed a frame that does not contain the
    column it was told to judge.

    ⚠️ THE OWNER'S OWN CASE WOULD HAVE HIDDEN IT. There the column is `core_x`, an identity
    part, so it arrives by luck - and every column of THIS fixture's relation is selected
    too, which is why the term is asserted on the function rather than through a bundle:
    neither world can show the gap, and a test that cannot fail would just look green.
    """
    without = locked_select_columns(identity=["event_key"])
    assert "kept_only_by_the_clause" not in without

    with_clause = locked_select_columns(
        identity=["event_key"], exclude_when_columns=["kept_only_by_the_clause"])
    assert "kept_only_by_the_clause" in with_clause
    assert set(without) <= set(with_clause), "the term ADDS; it may not take anything away"


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


def test_declaring_it_under_a_preparer_that_cannot_read_it_is_refused():
    """🔴 판정 194 ㉡. Only the generic `direct-join` preparer reads this clause. A source
    that declares it under another implementation would have it silently do nothing - the
    mirror image of the two-paths problem the feature exists to avoid - so setup refuses by
    name instead. A preparer CLASS that wants to exclude rows already emits the marker."""
    raw = _with_exclusion([{"column": "join_id", "blank": True}])
    driver_preparation(raw)["implementation_id"] = "lot-event-role"

    new = paths_of(raw) - paths_of(logical_bundle())
    assert any(path.endswith("prepare.exclude_when") for path in new), sorted(new)
