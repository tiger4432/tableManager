# -*- coding: utf-8 -*-
"""Lead 11-10 (owner «타이틀이 없으면 안 붙네», traced to report_reads): a blank title - «», spaces, NaN - is no title,
folded by the one blank function (crud.is_blank_value). Before, the unit's title read «not in (None, "")» itself, so
spaces or NaN were a title, and the conditions fill kept a first row's «» so a later row's real title never came."""
import math
from types import SimpleNamespace

import pytest

from chain.report_reads import Report

W1, W2 = ("W1",), ("W2",)


@pytest.mark.parametrize("blank", ["", "   ", float("nan"), None])
def test_a_blank_title_says_none_and_a_title_says_itself(blank):
    reads = SimpleNamespace(keys=["wafer"], _report_wafer=lambda w: w,
                            wafers={W1: {"title": blank}, W2: {"title": "split eval"}})
    assert Report._title(reads, W1, ["wafer"]) is None
    assert Report._title(reads, W2, ["wafer"]) == "split eval"


def test_a_later_rows_title_takes_the_place_of_a_blank_one():
    rows = [(W1, ("bond", "1", "")), (W1, ("temp", "2", "split eval")),
            (W2, ("bond", "3", "kept")), (W2, ("temp", "4", "not this"))]
    reads = SimpleNamespace(
        long={"table": "cond", "name": "name", "value": "value", "title": "title"},
        spec={"wafer": {"time": "date"}},
        wafers={W1: {"conditions": {}, "title": None}, W2: {"conditions": {}, "title": None}},
        _matched=lambda role, columns, wafers, where=None: rows)
    Report._long_conditions(reads, [W1, W2])
    assert (reads.wafers[W1]["title"], reads.wafers[W2]["title"]) == ("split eval", "kept")
    assert not any(isinstance(f["title"], float) and math.isnan(f["title"]) for f in reads.wafers.values())
