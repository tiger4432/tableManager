"""`to_local_str` is memoised. These tests pin the two things a memo can get wrong.

A value memo is only sound if every input that SHARES A DICT ENTRY renders the same
string. `dict` decides sharing with `hash` + `==`, so the question is not "are these
values similar" but "does `datetime.__eq__` ever unify two inputs this function would
render differently". The answers are pinned below rather than argued, and they are
checked against an ORACLE - a fresh, unmemoised recomputation - instead of against
`to_local_str`'s own earlier answer, which would just be the memo agreeing with itself.

The second thing a memo gets wrong is growing forever. This module is imported by four
long-lived processes, so the bound is asserted, not assumed.
"""
import datetime as dt_pkg
from datetime import datetime, timedelta, timezone

import pytest

from utils import time_format
from utils.time_format import to_local_str

KST = timezone(timedelta(hours=9))
UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))


def oracle(dt):
    """Independent recomputation. Deliberately NOT a call into `to_local_str`."""
    if not dt:
        return ""
    aware = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    return aware.astimezone(time_format.LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


CORPUS = [
    None,
    datetime(2026, 8, 2, 0, 22, 29),                        # naive
    datetime(2026, 8, 2, 0, 22, 29, 440348),                # naive, microseconds
    datetime(2026, 8, 2, 0, 22, 29, tzinfo=UTC),
    datetime(2026, 8, 2, 0, 22, 29, tzinfo=KST),
    datetime(2026, 8, 2, 0, 22, 29, tzinfo=IST),
    datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),              # year boundary
    datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC),
    datetime(2026, 3, 8, 2, 30, 0, tzinfo=UTC),             # US DST switch instant
    datetime(2026, 10, 25, 1, 30, 0, tzinfo=UTC),           # EU DST switch instant
]


@pytest.mark.parametrize("value", CORPUS)
def test_the_memo_answers_what_a_fresh_recomputation_answers(value):
    assert to_local_str(value) == oracle(value)


def test_repeating_a_value_does_not_change_its_answer():
    """The memo's whole point is the second call. It must not be the second answer."""
    for value in CORPUS:
        first = to_local_str(value)
        for _ in range(5):
            assert to_local_str(value) == first
        assert first == oracle(value)


def test_two_aware_values_naming_one_instant_share_an_entry_and_that_is_correct():
    """The sharpest case for a value memo.

    `datetime.__eq__` on aware values compares INSTANTS, so these two are `==` and hash
    equal - they are one dict entry no matter which arrives first. That is sound here
    only because converting an instant to a fixed local offset has one answer, which is
    what this asserts. If `to_local_str` ever grew an output that depended on the input's
    tzinfo rather than on its instant, the memo would start answering with whichever
    spelling was cached first, and this test is what would catch it.
    """
    kst = datetime(2026, 8, 2, 0, 22, 29, tzinfo=KST)
    utc = datetime(2026, 8, 1, 15, 22, 29, tzinfo=UTC)
    assert kst == utc and hash(kst) == hash(utc), "premise: these share a dict entry"

    time_format._LOCAL_STR_MEMO.clear()
    kst_first = to_local_str(kst)
    utc_second = to_local_str(utc)

    time_format._LOCAL_STR_MEMO.clear()
    utc_first = to_local_str(utc)
    kst_second = to_local_str(kst)

    # Order of arrival must not decide the answer.
    assert kst_first == utc_second == utc_first == kst_second == oracle(kst)


def test_a_naive_value_never_shares_an_entry_with_the_aware_one_beside_it():
    """Naive is forced to UTC, aware is not, so they render differently - and they must
    never collide. `datetime.__eq__` returns False across the naive/aware boundary, so
    they cannot; this pins that the two answers stay distinct."""
    naive = datetime(2026, 8, 2, 0, 22, 29)
    aware = datetime(2026, 8, 2, 0, 22, 29, tzinfo=KST)
    assert naive != aware

    time_format._LOCAL_STR_MEMO.clear()
    assert to_local_str(naive) == oracle(naive)
    assert to_local_str(aware) == oracle(aware)
    # KST is +09:00, so forcing the naive value to UTC moves it by 9 hours. If these
    # ever became equal the memo would be masking a conversion bug, not causing one.
    assert to_local_str(naive) != to_local_str(aware)


def test_falsy_input_short_circuits_before_the_memo():
    assert to_local_str(None) == ""
    assert to_local_str(0) == ""
    assert to_local_str("") == ""
    assert None not in time_format._LOCAL_STR_MEMO


def test_the_memo_is_bounded_and_still_correct_after_it_overflows():
    """An unbounded dict keyed on row data is the `TABLE_COUNT_CACHE` defect. Feed it
    more distinct values than the cap and assert both that it stayed bounded and that
    the answers on the far side of the clear are still right."""
    cap = time_format._LOCAL_STR_MEMO_MAX
    time_format._LOCAL_STR_MEMO.clear()

    base = datetime(2026, 8, 2, 0, 0, 0, tzinfo=UTC)
    probes = [base + timedelta(seconds=i) for i in range(cap + 500)]
    for value in probes:
        assert to_local_str(value) == oracle(value)
        assert len(time_format._LOCAL_STR_MEMO) <= cap

    # A value seen before the overflow must still answer correctly afterwards, whether
    # or not it survived the clear.
    assert to_local_str(probes[0]) == oracle(probes[0])
    assert len(time_format._LOCAL_STR_MEMO) <= cap


def test_the_stored_key_is_the_argument_not_the_utc_forced_value():
    """A memo keyed on the converted value would never hit for naive inputs, because a
    naive datetime is never `==` an aware one. That is a silent performance regression
    - the function stays correct while the memo does nothing - so it is pinned here
    rather than left to a profiler to rediscover."""
    naive = datetime(2026, 5, 11, 3, 4, 5)
    time_format._LOCAL_STR_MEMO.clear()
    to_local_str(naive)
    assert naive in time_format._LOCAL_STR_MEMO, (
        "the naive argument itself must be the key, or every naive call is a miss")
    assert naive.replace(tzinfo=UTC) not in time_format._LOCAL_STR_MEMO or (
        naive.replace(tzinfo=UTC) == naive)


def test_the_module_still_imports_nothing_but_the_standard_library():
    """The reason this module exists (see its docstring): a notification path must not
    depend on importing an application module that is allowed to refuse. The memo must
    not have quietly introduced one."""
    import ast
    import inspect

    # AST, not substring matching: this module's own docstring QUOTES the import it
    # exists to prevent, so a text search finds the warning and calls it the crime.
    tree = ast.parse(inspect.getsource(time_format))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])

    assert imported <= {"datetime"}, (
        f"time_format must import nothing but the standard library; found {imported}")
    assert isinstance(time_format.LOCAL_TIMEZONE, dt_pkg.tzinfo)
