# -*- coding: utf-8 -*-
"""NaN must not reach a mapper, and a healthy payload must not be touched on the way.

Owner report 2026-09-04, from production: `cannot convert float NaN to integer` out of the
chain. Every custom mapper is called through `execute_custom_mapper`, so the rule lives
there - a rule each mapper has to remember is a trap that fires the first time somebody
forgets, and this tool exists for people who write mappers.

🔴 WHAT THESE CASES DO **NOT** CLAIM: that the NaN error is gone. A mapper that builds its
own frame with pandas can create a NaN inside itself and raise before it returns anything,
and no boundary can see that. What is asserted here is narrower and checkable - a mapper
does not RECEIVE one.

⚠️ AND THE THIRD GROUP IS THE IMPORTANT ONE. A normaliser that rewrites healthy values is
a silent regression, so a payload with nothing missing in it has to come back as the SAME
OBJECT, not an equal copy.
"""
import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import chain_ingestion_worker as worker                            # noqa: E402


def cell(value):
    """The nested shape an outbox payload actually has."""
    return {"value": value, "is_overwrite": False, "updated_by": "system"}


# --------------------------------------------------------------- what comes out

def test_a_nan_deep_inside_the_payload_becomes_none():
    """🔴 DEEP. The value is two dicts down inside a list - a shallow pass would report
    success and leave the NaN exactly where the mapper reads it."""
    payload = [{"row_id": "r1", "data": {"qty": cell(float("nan")),
                                         "part_no": cell("P1")}}]
    got = worker.without_missing(payload)
    assert got[0]["data"]["qty"]["value"] is None
    assert got[0]["data"]["part_no"]["value"] == "P1"


@pytest.mark.parametrize("missing", [
    float("nan"), np.nan, np.float64("nan"), float("inf"), float("-inf"),
    pd.NaT, pd.NA, None,
])
def test_every_marker_the_pipeline_calls_missing_is_missing_here_too(missing):
    """The same rule as `parsers/pipeline_base.py:73-75`, INCLUDING the infinities. Two
    spellings of "no value" would make one source value a number on one path and a blank
    on the other."""
    assert worker.without_missing({"v": missing})["v"] is None


def test_missing_becomes_none_and_never_zero():
    """🔴 A zero is a VALUE. Turning a missing number into 0 would make "we did not
    measure it" and "we measured zero" the same cell, which is the exact confusion this
    repository has been removing all day."""
    got = worker.without_missing({"a": float("nan"), "b": 0, "c": 0.0, "d": False})
    assert got["a"] is None
    assert got["b"] == 0 and got["c"] == 0.0 and got["d"] is False


def test_a_nan_in_the_mappers_RETURN_value_is_cleaned_too(monkeypatch):
    """The write path has integer columns of its own and would hit the same conversion."""
    module = type(sys)("fake_mapper_module")
    module.emit = lambda db, payload: {"updates": [
        {"updates": {"qty": float("nan"), "part_no": "P1"}}]}
    monkeypatch.setitem(sys.modules, "fake_mapper_module", module)

    got = worker.execute_custom_mapper("fake_mapper_module", "emit", None, [])
    assert got["updates"][0]["updates"]["qty"] is None
    assert got["updates"][0]["updates"]["part_no"] == "P1"


def test_the_mapper_receives_the_cleaned_payload(monkeypatch):
    """End to end through the funnel, which is the only claim this round makes."""
    seen = {}
    module = type(sys)("fake_mapper_module2")

    def emit(db, payload):
        seen["payload"] = payload
        return {"updates": []}

    module.emit = emit
    monkeypatch.setitem(sys.modules, "fake_mapper_module2", module)

    worker.execute_custom_mapper(
        "fake_mapper_module2", "emit", None,
        [{"row_id": "r1", "data": {"qty": cell(float("nan"))}}])
    assert seen["payload"][0]["data"]["qty"]["value"] is None


# ------------------------------------------------ what must NOT change (the regression)

def test_a_payload_with_nothing_missing_comes_back_as_the_SAME_OBJECT():
    """🔴 THE ONE THAT MATTERS MOST. Equality would pass even if every dict were rebuilt;
    identity is what proves the healthy path was not touched - and it is also what keeps a
    large batch from paying for a defect that is not in it."""
    payload = [{"row_id": "r1", "data": {"qty": cell(7), "part_no": cell("P1")}}]
    assert worker.without_missing(payload) is payload


def test_values_that_merely_look_odd_are_left_alone():
    """Empty string, zero, False and an empty dict are all VALUES. A guard that swallowed
    them would be the `str(x or "").strip()` mistake in a new place."""
    payload = {"a": "", "b": 0, "c": False, "d": {}, "e": [], "f": "nan"}
    assert worker.without_missing(payload) is payload


def test_a_frame_inside_the_value_is_not_mistaken_for_a_missing_scalar():
    """`pd.isna` answers ELEMENTWISE for a frame, so taking its truth value raises. That
    is how this kind of guard usually fails: loudly, on the one shape nobody tested."""
    frame = pd.DataFrame({"a": [1, float("nan")]})
    got = worker.without_missing({"df": frame})
    assert got["df"] is frame


def test_only_the_branch_that_changed_is_rebuilt():
    """A nested payload with one bad cell rebuilds the path to it and leaves its siblings
    as the objects they were."""
    good = {"part_no": cell("P1")}
    payload = {"rows": [{"data": {"qty": cell(float("nan"))}}, {"data": good}]}
    got = worker.without_missing(payload)
    assert got is not payload
    assert got["rows"][1]["data"] is good
