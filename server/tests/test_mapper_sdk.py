# -*- coding: utf-8 -*-
"""`mapper_sdk` - the ① and ③ a mapper author should not be writing.

🔴 THE DISCRIMINATING TEST IS THE PAIR OF TABLES. A composite target and a plain one want
OPPOSITE things from the same author code, and both failures are silent:

    composite, key spelled by the mapper   the declaration stops being followed
    plain, key left to the framework       the row lands with NO identity and every run
                                           inserts another copy

So the test writes the SAME author code against both and asserts each comes out right
without the author having said which kind the table is. A fixture with only one of the
two would pass with the rule hardcoded either way.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mapper_sdk
from database import crud


COMPOSITE = "sdk_composite_tbl"
PLAIN = "sdk_plain_tbl"

TABLES = {
    COMPOSITE: {
        "business_key": "cell_key",
        "composite_key_source": ["job", "cx", "cy"],
        "composite_key_separator": "|",
        "column_types": {"cell_key": "string", "job": "string",
                         "cx": "number", "cy": "number", "note": "string"},
    },
    PLAIN: {
        "business_key": "part_no",
        "column_types": {"part_no": "string", "qty": "number", "note": "string"},
    },
}


@pytest.fixture(autouse=True)
def _declared():
    crud.TABLE_CONFIG.update(TABLES)
    yield
    for name in TABLES:
        crud.TABLE_CONFIG.pop(name, None)


def _emit(table, frame):
    """The author's whole contribution: columns in, nothing about keys."""
    return mapper_sdk.df_to_updates(frame, table,
                                    source_name="chain_ingestion", updated_by="test")


# ---------------------------------------------------------------------------
# the pair - one author shape, two declarations
# ---------------------------------------------------------------------------

def test_a_composite_target_gets_no_business_key_val_so_the_declaration_assembles_it():
    """The mapper must NOT spell the key here. `assemble_composite_business_key` returns
    at its first statement when the item already carries one, so a spelled key silently
    replaces the declaration - separator, column order and all."""
    out = _emit(COMPOSITE, pd.DataFrame([{"job": "J1", "cx": 3, "cy": 7, "note": "a"}]))

    item = out["updates"][0]
    assert "business_key_val" not in item, (
        "spelling the key here would stop the declaration from being followed")
    assert item["updates"] == {"job": "J1", "cx": 3, "cy": 7, "note": "a"}


def test_a_plain_target_gets_one_because_nothing_else_will_lift_it():
    """And here the opposite: `_get_or_create_row` reads `row_id`/`business_key_val` only,
    so a key sitting in `updates` gives the write no identity at all."""
    out = _emit(PLAIN, pd.DataFrame([{"part_no": "P1", "qty": 5}]))

    item = out["updates"][0]
    assert item["business_key_val"] == "P1"
    assert item["updates"]["part_no"] == "P1", "the column stays where the author put it"


def test_the_author_writes_the_same_thing_for_both():
    """🔴 THE ROUND'S POINT, AS ONE ASSERTION. The two calls differ only in the table
    name; everything about keys came from the declaration."""
    comp = _emit(COMPOSITE, pd.DataFrame([{"job": "J9", "cx": 1, "cy": 2}]))
    plain = _emit(PLAIN, pd.DataFrame([{"part_no": "P9", "qty": 1}]))

    assert ("business_key_val" in plain["updates"][0]) is True
    assert ("business_key_val" in comp["updates"][0]) is False


# ---------------------------------------------------------------------------
# the values - each kind of absence, separately
# ---------------------------------------------------------------------------

def test_nan_and_nat_become_none_rather_than_the_float_nan():
    """`pd.read_sql` turns SQL NULL into NaN, whose type is float - so a bare
    `to_dict("records")` turns "there was no value" into "the value is nan", and nan is a
    value. Asserted with `is None` because `nan != nan` makes equality no test at all."""
    frame = pd.DataFrame([{"part_no": "P1", "qty": None, "note": pd.NaT}])
    values = _emit(PLAIN, frame)["updates"][0]["updates"]

    assert values["qty"] is None
    assert values["note"] is None
    assert not any(isinstance(v, float) and v != v for v in values.values()), (
        "a NaN survived to the payload")


def test_numpy_scalars_come_out_as_python_values():
    """Fed DIRECTLY, because the frame path does not produce one on this pandas.

    🔴 Measured 2026-09-03: `astype(object).to_dict("records")` hands back int / float /
    bool / Timestamp / str, none of which has `.item()`. So going through a frame cannot
    exercise this conversion, and a test that only went through a frame would be green
    with the conversion deleted - it was, before this was written this way.

    The conversion still belongs: older pandas returned `numpy.int64` from `to_dict`, and
    a `numpy.int64` is not an `int` to everything downstream. What is not allowed is
    shipping it unexercised.
    """
    import numpy as np

    assert mapper_sdk._python_scalar(np.int64(5)) == 5
    assert type(mapper_sdk._python_scalar(np.int64(5))) is int
    assert type(mapper_sdk._python_scalar(np.float64(1.5))) is float
    assert type(mapper_sdk._python_scalar(np.bool_(True))) is bool
    assert mapper_sdk._python_scalar("P1") == "P1", "a str passes through untouched"
    assert mapper_sdk._python_scalar(None) is None

    # and the frame path, whatever pandas hands over, must not leak a numpy type
    frame = pd.DataFrame({"part_no": ["P1"], "qty": [5]})
    assert str(frame["qty"].dtype).startswith("int"), "fixture must give a numpy dtype"
    qty = _emit(PLAIN, frame)["updates"][0]["updates"]["qty"]
    assert type(qty) is int, f"{type(qty)} reached the payload"


def test_an_empty_frame_is_an_intentional_no_op_not_an_error():
    assert _emit(PLAIN, pd.DataFrame()) == {"updates": []}
    assert _emit(PLAIN, None) == {"updates": []}


# ---------------------------------------------------------------------------
# the refusals - both of them are silent if they are not made
# ---------------------------------------------------------------------------

def test_a_missing_composite_source_column_is_refused_by_name():
    """Emitting anyway assembles nothing: the key stays None, the rows insert, and they
    never match again. The gate does not catch it, so this does."""
    with pytest.raises(mapper_sdk.MapperContractError) as raised:
        _emit(COMPOSITE, pd.DataFrame([{"job": "J1", "cx": 3}]))
    assert "cy" in str(raised.value)


def test_a_missing_key_column_on_a_plain_target_is_refused_by_name():
    with pytest.raises(mapper_sdk.MapperContractError) as raised:
        _emit(PLAIN, pd.DataFrame([{"qty": 5}]))
    assert "part_no" in str(raised.value)


def test_a_blank_key_value_on_a_plain_target_is_refused_too():
    """The column being present is not the same as it holding something. A blank one
    lands exactly the identity-less row the missing column would have."""
    with pytest.raises(mapper_sdk.MapperContractError):
        _emit(PLAIN, pd.DataFrame([{"part_no": "  ", "qty": 5}]))
    with pytest.raises(mapper_sdk.MapperContractError):
        _emit(PLAIN, pd.DataFrame([{"part_no": None, "qty": 5}]))


# ---------------------------------------------------------------------------
# step ① - one implementation, two doors
# ---------------------------------------------------------------------------

def test_payloads_to_df_keeps_the_value_and_drops_the_cell_envelope():
    df = mapper_sdk.payloads_to_df([
        {"row_id": "r1", "data": {"part_no": {"value": "P1"}, "qty": {"value": 5}}},
        {"row_id": "r2", "data": {"part_no": "P2", "qty": 7}},   # already flat
    ])
    assert list(df["part_no"]) == ["P1", "P2"]
    assert list(df["row_id"]) == ["r1", "r2"], "identity is not a data column"
    assert mapper_sdk.payloads_to_df([]).empty


# ---------------------------------------------------------------------------
# step ② - sql(db, ...) reads on the CALLER'S session
# ---------------------------------------------------------------------------

def test_the_query_runs_on_the_callers_transaction_not_a_new_connection(db_session):
    """🔴 THE PROPERTY, AND IT IS ONLY OBSERVABLE BEFORE A COMMIT. A chain mapper runs
    inside the worker's transaction and may not commit, so rows the chain has staged are
    visible to that session and to nothing else. A helper that opened its own connection
    would read the database as it was BEFORE this batch - deriving from stale state,
    silently, and only under concurrency.

    The row below is written and NOT committed. Seeing it is the whole assertion.
    """
    from sqlalchemy import text

    db_session.execute(text(
        "CREATE TABLE IF NOT EXISTS sdk_probe (k TEXT, v INTEGER)"))
    db_session.execute(text("DELETE FROM sdk_probe"))
    db_session.execute(text("INSERT INTO sdk_probe (k, v) VALUES ('a', 1)"))
    # deliberately NOT committed

    used = []
    real_connection = db_session.connection

    def spy():
        used.append(1)
        return real_connection()

    db_session.connection = spy
    try:
        got = mapper_sdk.sql(db_session, "SELECT k, v FROM sdk_probe ORDER BY k")
    finally:
        db_session.connection = real_connection

    # 🔴 THE SPY IS THE ASSERTION, AND THE VISIBILITY BELOW IS NOT.
    # Measured 2026-09-03: swapping `db.connection()` for `db.get_bind()` - handing pandas
    # the ENGINE, which is exactly the "opens its own connection" defect - leaves the two
    # assertions below GREEN on this suite, because SQLite hands back the same pooled
    # connection and sees the uncommitted row either way. So the dialect that runs the
    # tests cannot tell the two apart by behaviour, and a test that only looked at rows
    # would pass with the defect in place. It did, before this was written this way.
    assert used, "the query did not go through the session's own connection"
    # Kept underneath because it is what the spy is FOR - on PostgreSQL a second
    # connection cannot see this row at all, and then the meaning and the mechanism agree.
    assert list(got["k"]) == ["a"]
    assert list(got["v"]) == [1]


def test_parameters_are_bound_rather_than_formatted(db_session):
    """A value that would break a formatted string must go through untouched, and a
    parameter must actually narrow - a helper that ignored `params` would return
    everything and look like it worked."""
    from sqlalchemy import text

    db_session.execute(text(
        "CREATE TABLE IF NOT EXISTS sdk_probe2 (k TEXT, v INTEGER)"))
    db_session.execute(text("DELETE FROM sdk_probe2"))
    db_session.execute(text("INSERT INTO sdk_probe2 (k, v) VALUES ('a', 1)"))
    db_session.execute(text("INSERT INTO sdk_probe2 (k, v) VALUES (:k, 2)"),
                       {"k": "it's a value"})

    narrowed = mapper_sdk.sql(db_session, "SELECT v FROM sdk_probe2 WHERE k = :k",
                              {"k": "it's a value"})
    assert list(narrowed["v"]) == [2], "the parameter did not narrow, or the quote broke it"


# ---------------------------------------------------------------------------
# step ③ - @mapper, so ① and ③ leave the author's file
# ---------------------------------------------------------------------------

def test_a_decorated_mapper_takes_payloads_and_returns_the_envelope():
    """The author's function sees a frame and returns a frame; the worker's call shape is
    unchanged, so a decorated mapper drops into `chain_rules.json` where a hand-written
    one did."""
    @mapper_sdk.mapper()
    def double_qty(df, db):
        out = df[["part_no"]].copy()
        out["qty"] = df["qty"] * 2
        return out

    payloads = [{"row_id": "r1", "data": {"part_no": {"value": "P1"},
                                          "qty": {"value": 5}}}]
    got = double_qty(None, payloads, rule={"target_table": PLAIN})

    assert got == {"updates": [{
        "updates": {"part_no": "P1", "qty": 10},
        "source_name": "chain_ingestion", "updated_by": "double_qty",
        "business_key_val": "P1"}]}


def test_the_target_table_comes_from_the_rule_and_the_rule_wins():
    """🔴 `rule["target_table"]` is where that fact already lives. A mapper restating it
    is a second place for it to be wrong, so the decorator's argument is only a fallback -
    and when both are present the RULE wins, because the rule is what an operator edits.
    """
    @mapper_sdk.mapper(COMPOSITE)                     # a wrong guess, on purpose
    def emit(df, db):
        return df

    payloads = [{"row_id": "r1", "data": {"part_no": {"value": "P1"}, "qty": {"value": 1}}}]
    got = emit(None, payloads, rule={"target_table": PLAIN})

    assert "business_key_val" in got["updates"][0], (
        "the decorator's table won over the rule's; the operator's edit lost")


def test_a_mapper_with_no_table_anywhere_is_refused_by_name():
    @mapper_sdk.mapper()
    def emit(df, db):
        return df

    with pytest.raises(mapper_sdk.MapperContractError) as raised:
        emit(None, [{"row_id": "r1", "data": {"part_no": {"value": "P1"}}}], rule={})
    assert "emit" in str(raised.value)


def test_returning_something_that_is_not_a_frame_is_refused_rather_than_guessed():
    """Returning the envelope yourself means the decorator is not what you want, and
    saying so beats half-handling it."""
    @mapper_sdk.mapper()
    def emit(df, db):
        return {"updates": []}

    with pytest.raises(mapper_sdk.MapperContractError):
        emit(None, [{"row_id": "r1", "data": {"part_no": {"value": "P1"}}}],
             rule={"target_table": PLAIN})


def test_an_empty_result_is_the_intentional_no_op_the_worker_reads():
    """`{"updates": []}` is what the worker tests for. `None` from the author is treated
    the same way DELIBERATELY rather than by falling through `if target_payload`."""
    @mapper_sdk.mapper()
    def nothing_to_do(df, db):
        return None

    @mapper_sdk.mapper()
    def empty_frame(df, db):
        return df.iloc[0:0]

    args = ([{"row_id": "r1", "data": {"part_no": {"value": "P1"}}}],)
    assert nothing_to_do(None, *args, rule={"target_table": PLAIN}) == {"updates": []}
    assert empty_frame(None, *args, rule={"target_table": PLAIN}) == {"updates": []}


def test_the_provenance_defaults_to_the_authors_own_function_name():
    """Provenance that has to be typed gets copied from the last mapper and then names
    the wrong one. The function's name cannot drift from the function."""
    @mapper_sdk.mapper()
    def my_specific_derivation(df, db):
        return df

    got = my_specific_derivation(
        None, [{"row_id": "r1", "data": {"part_no": {"value": "P1"}}}],
        rule={"target_table": PLAIN})
    assert got["updates"][0]["updated_by"] == "my_specific_derivation"


# ---------------------------------------------------------------------------
# BaseMapper - moved so its implementation ships, and it must still be ONE class
# ---------------------------------------------------------------------------

def test_base_mapper_is_reachable_by_both_names_and_is_the_same_class():
    """🔴 THE ASSERTION IS `is`, NOT "both work". Two copies would each answer correctly
    and drift the day one is fixed - which is the whole reason the class moved out of
    `mappers/base.py`, a file `.gitignore` keeps on the box that wrote it.

    The old import is what the production mappers use (`from mappers.base import
    BaseMapper`), so it has to keep working; the new one is where the implementation now
    lives. If `mappers/base.py` is absent - a fresh checkout, where it never shipped -
    only the SDK path exists and that is the point of the move, so the old name is
    skipped rather than failed.
    """
    from mapper_sdk import BaseMapper as from_sdk

    try:
        from mappers.base import BaseMapper as from_mappers
    except ImportError:
        pytest.skip("mappers/base.py is not present - it is gitignored and never ships")

    assert from_mappers is from_sdk, (
        "two BaseMapper classes exist; a fix to one would never reach the other")


def test_base_mapper_still_answers_exactly_what_it_did():
    """Same name, same static method, same result - the owner's "leave it alone"."""
    from mapper_sdk import BaseMapper

    payloads = [{"row_id": "r1", "data": {"part_no": {"value": "P1"}, "qty": {"value": 5}}}]
    from_class = BaseMapper.payloads_to_df(payloads)
    from_function = mapper_sdk.payloads_to_df(payloads)

    assert from_class.equals(from_function), "the class re-implemented what it delegates to"
    assert list(from_class["part_no"]) == ["P1"]


def test_base_mapper_keeps_exactly_one_method():
    """Adding to it would make inheritance look like the intended route; new mappers use
    the functions. Asserted so that growing it is a decision rather than a drift."""
    from mapper_sdk import BaseMapper

    public = [n for n in vars(BaseMapper) if not n.startswith("_")]
    assert public == ["payloads_to_df"], f"BaseMapper grew: {public}"
