# -*- coding: utf-8 -*-
"""S-153. A group is one writer's transaction unless a rule says it may be bigger.

🔴 THE HANDLE DID NOT EXIST. A chain group IS whatever transaction the writing side happened
to commit, so the worker had no say in the size of the unit it runs - and size is the biggest
lever there is: the application lane measured 1,000 -> 5,000 rows per group cutting s/1k by
30% (mapper 8.44 -> 4.99, plumbing 2.52 -> 1.88). A performance handle with no handle.

🔴 AND THE DEFAULT CHANGES NOTHING. Declaring no ceiling leaves every group exactly as it
arrived, so this round adds the lever without moving the timing - no-regression is not a hope
here, it is the default, and the first case below is the one that says so.

⚠️ A MERGED UNIT IS ONE UNIT FOR FAILURE TOO. It succeeds or fails together and the HOL guard
sees the group it now is. Splitting a failed merge back apart is S-222 and is deliberately
not here - which is the other reason the default is 「do not merge」.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import chain_bindings                                                # noqa: E402
from chain import ingestion_worker as worker                         # noqa: E402


class _Event:
    """Just enough of an event for grouping: the table it touched and its kind."""

    def __init__(self, table, tx, event_type="CREATE"):
        self.table_name = table
        self.transaction_id = tx
        self.event_type = event_type
        self.source_name = "ingestion"
        self.changed_columns = None


def _rule(name, trigger="t", **cells):
    return dict({"name": name, "trigger_table": trigger, "target_table": "out",
                 "mapper": "m", "enabled": True}, **cells)


def _batch(sizes, table="t"):
    """`sizes` -> (group_order, groups): one transaction per entry, that many rows."""
    order, groups = [], {}
    for index, count in enumerate(sizes):
        tx = "tx%d" % index
        order.append(tx)
        groups[tx] = [_Event(table, tx) for _ in range(count)]
    return order, groups


def _merged(sizes, rules, table="t"):
    order, groups = _batch(sizes, table)
    new_order, new_groups = worker.merge_consecutive_groups(order, groups, rules)
    return [len(new_groups[tx]) for tx in new_order]


# ---------------------------------------------------------------------------
# 🔴 the default: nothing declared, nothing changes
# ---------------------------------------------------------------------------

def test_a_rule_that_declares_nothing_keeps_todays_groups():
    """🔴 THE NO-REGRESSION CASE, and it is the default rather than a promise."""
    assert _merged([3, 4, 5], [_rule("r")]) == [3, 4, 5]


def test_no_rule_at_all_keeps_todays_groups():
    """⚠️ Events nobody wakes are still events; they must not be folded on a signature of
    nothing, or unrelated transactions would be glued together."""
    assert _merged([2, 2], []) == [2, 2]


# ---------------------------------------------------------------------------
# 🔴 declared: consecutive groups fold up to the ceiling
# ---------------------------------------------------------------------------

def test_consecutive_groups_fold_up_to_the_ceiling():
    rules = [_rule("r", max_group_rows=10)]

    assert _merged([3, 4, 2], rules) == [9]


def test_the_fold_stops_at_the_ceiling_rather_than_crossing_it():
    """🔴 A CEILING THAT IS CROSSED ONCE IS NOT A CEILING. The next group starts a new unit
    instead of overflowing the one being built."""
    rules = [_rule("r", max_group_rows=5)]

    assert _merged([3, 3, 3], rules) == [3, 3, 3]
    assert _merged([2, 3, 4], rules) == [5, 4]


def test_a_group_larger_than_the_ceiling_is_left_alone():
    """⚠️ THE WRITER'S TRANSACTION IS NOT SPLIT. This round merges; it never divides - a
    group that already exceeds the ceiling arrives as it is and runs as it is."""
    assert _merged([9], [_rule("r", max_group_rows=5)]) == [9]


# ---------------------------------------------------------------------------
# ⚠️ what may not be folded together
# ---------------------------------------------------------------------------

def test_groups_that_wake_different_rules_are_not_folded():
    """⛔ 「SAME TABLE, SAME RULE」 IS THE UNIT. Two transactions that wake different rules are
    different work, and folding them would run each rule over rows it was never woken for."""
    rules = [_rule("a", trigger="t1", max_group_rows=99),
             _rule("b", trigger="t2", max_group_rows=99)]
    order, groups = [], {}
    for index, table in enumerate(("t1", "t2", "t1")):
        tx = "tx%d" % index
        order.append(tx)
        groups[tx] = [_Event(table, tx)]

    new_order, new_groups = worker.merge_consecutive_groups(order, groups, rules)

    assert [len(new_groups[tx]) for tx in new_order] == [1, 1, 1]


def test_only_adjacent_groups_fold():
    """🔴 ORDER IS PRESERVED BECAUSE ONLY NEIGHBOURS FOLD. Reaching past a group to merge
    with a later one would move work in front of work."""
    rules = [_rule("a", trigger="t1", max_group_rows=99),
             _rule("b", trigger="t2", max_group_rows=99)]
    order = ["x0", "x1", "x2"]
    groups = {"x0": [_Event("t1", "x0")], "x1": [_Event("t2", "x1")],
              "x2": [_Event("t1", "x2")]}

    new_order, _ = worker.merge_consecutive_groups(order, groups, rules)

    assert new_order == ["x0", "x1", "x2"]


def test_the_strictest_rule_decides_when_a_group_wakes_two():
    """🔴 A MERGED UNIT RUNS EVERY RULE IT WOKE, so a ceiling true for only one of them is no
    ceiling for the others. One rule declaring nothing stops the fold entirely."""
    both = [_rule("a", max_group_rows=99), _rule("b")]

    assert _merged([2, 2], both) == [2, 2]

    stricter = [_rule("a", max_group_rows=99), _rule("b", max_group_rows=3)]
    assert _merged([2, 2], stricter) == [2, 2]
    assert _merged([1, 1], stricter) == [2]


# ---------------------------------------------------------------------------
# ⛔ the cell is judged where every other cell is
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("written", ["many", 0, -1, True, 2.5])
def test_a_ceiling_that_is_not_a_positive_number_is_refused(written):
    """⛔ WRITTEN, NOT DEFAULTED. The product's own 「do not merge」 is `NO_GROUP_MERGE`; what
    is refused here is a cell an author actually wrote, because 「merge nothing」 and 「no
    limit」 are opposite readings of the same zero."""
    issues = chain_bindings.rule_refusals(
        _rule("r", max_group_rows=written), "rule",
        mapper_resolvable=lambda name: object(), mapper_params=lambda name: None)

    assert "bad_group_rows" in [i.code for i in issues], written


def test_a_good_ceiling_is_not_refused():
    issues = chain_bindings.rule_refusals(
        _rule("r", max_group_rows=5000), "rule",
        mapper_resolvable=lambda name: object(), mapper_params=lambda name: None)

    assert [i.code for i in issues] == []


def test_the_form_draws_the_cell_without_being_told():
    """🔵 `skeleton()` IS GENERATED FROM THE GRAMMAR, so the chain tab grows the field the
    moment the cell exists - no second list to update, which is the whole reason that
    function exists."""
    fields = {f["key"]: f for f in chain_bindings.skeleton()["root"]["fields"]}

    assert fields["max_group_rows"]["node"]["hint"] == "number"
