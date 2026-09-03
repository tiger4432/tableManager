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
