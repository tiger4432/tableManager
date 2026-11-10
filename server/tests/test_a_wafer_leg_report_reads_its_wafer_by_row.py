# -*- coding: utf-8 -*-
"""Lead 10-28 (ㄴ′): a report whose unit is (wafer, leg) reads the ledger's wafer by `causes.values.row` - the join take
walk's `row`, the same walk - and every leg of a wafer gets that wafer's value. One function makes a row's wafer nodes
for both (`report_reads.wafer_nodes`): a blank value is no node, on either side. Unwritten with a unit the wafer node's
keys do not match, the walk is refused and says to write row; a row naming a column outside wafer.key is refused at
save. The scene that found it: (wafer, leg) is the owner's tables' unit and the ledger's wafer is keyed by wafer alone."""
import copy
import json
import os

import pytest

from chain import join_into, report_reads, report_shape
from ledger import explorer
from support import declaration
from test_a_report_reads_the_quantities_values_by_two_walks import (  # noqa: F401
    CANDIDATES, CAUSES, VALUES, Reads, _step_label, ledger)

pytestmark = pytest.mark.usefixtures("stored_walks")   # a stored-only ledger fixture (11-10)


class LegReads(Reads):
    """Two legs of W1, one of W2, and a leg whose wafer column is blank."""

    def __init__(self, causes):
        super().__init__(causes)
        self.keys = ["wafer", "leg"]
        self.groups = {"E1": [("W1", "L0"), ("W1", "L1"), ("W2", "L0"), ("", "L9")]}
        self.wafers = {w: {"conditions": {}} for members in self.groups.values() for w in members}


def _wafer(name):
    return explorer.entity_id("wafer", {"wafer": name})


def test_every_leg_of_a_wafer_gets_its_value_through_row(ledger):
    report = LegReads(dict(CAUSES, values=dict(VALUES, row=["wafer"])))
    said = report.values(CANDIDATES)
    thk = said["labels"][0]
    cells = {w: report.wafers[w]["conditions"].get(thk) for w in report.wafers}
    assert cells[("W1", "L0")] == cells[("W1", "L1")] == "12.3", "both legs - one wafer, its own value"
    assert cells[("W2", "L0")] == "12 (est · %s · 1 wf)" % _step_label(ledger)
    assert cells[("", "L9")] is None
    seeds = [asked for cell, asked in ledger["walks"] if asked.get("node_id") in (_wafer("W1"), _wafer("W2"))]
    assert seeds, "the wafer walk ran"                    # canary
    walked = {seeds[0]["node_id"], *(seeds[0].get("positive") or ())}
    assert walked == {_wafer("W1"), _wafer("W2")}, "one node a wafer, a blank wafer column none"


def test_without_row_a_unit_the_node_keys_do_not_match_is_refused_and_told_row(ledger):
    with pytest.raises(report_reads.ReadRefused, match=r"write causes\.values\.row"):
        LegReads(CAUSES).values(CANDIDATES)


def test_a_join_row_drops_a_blank_wafer_as_the_report_does(ledger):
    made = join_into.walked(Reads().db, {"fn": "walk", "walk": dict(VALUES), "row": ["wafers"], "why": "why"},
                            ["PA40-THK"], [{"wafers": ["W1", "", None]}])
    assert made["value"](["PA40-THK"], {"wafers": ["W1", "", None]}, {}) == "12.3", "one wafer - its own, no mean"


def test_the_sample_report_writes_row_and_a_row_outside_wafer_key_is_refused(ledger, monkeypatch):
    declaration.use_committed_catalogue(monkeypatch)
    with open(os.path.join(declaration.SAMPLE, "chain_rules.json.sample"), encoding="utf-8") as handle:
        rules = json.load(handle)["rules"]
    spec = copy.deepcopy([r for r in rules if r.get("name") == "wafer_report"][0]["derive"]["report"])
    assert spec["causes"]["values"]["row"] == ["wafer"]
    assert report_shape.refusal(spec, "wafer_report", "wafer_report") is None
    spec["causes"]["values"]["row"] = ["lot"]
    assert "causes.values.row names lot - not a column of derive.report.wafer.key" in report_shape.refusal(
        spec, "wafer_report", "wafer_report")
