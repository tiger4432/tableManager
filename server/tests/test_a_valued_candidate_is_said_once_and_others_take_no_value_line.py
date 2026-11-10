# -*- coding: utf-8 -*-
"""Lead 10-28: the candidate conditions step said «to be filled» of every candidate no condition was related to - a
quantity the values step had just given a value (two lines for one quantity that disagree), and a structure, a step,
an object no value lands on. With `causes.values` declared the values step alone answers it: to be filled is what that
step left to fill, and nothing else; without it every such candidate is to be filled as before (owner 10-25 «값이 없으면
채워야 한다는 코멘트»). The scene that found it: W2's THK1 12.3, then «THK1: no value … to be filled»."""
import logging

from chain import report_loop, report_reads, report_shape
from test_a_report_reads_the_quantities_values_by_two_walks import CANDIDATES, CAUSES, Reads, ledger  # noqa: F401
from test_the_report_walks_the_static_layer_from_the_seeds_the_model_picks import REQUEST, Model, _clock

import pytest
pytestmark = pytest.mark.usefixtures("stored_walks")   # a stored-only ledger fixture (11-10)

TO_FILL = report_shape.LABELS["to_fill"]


class Related(Reads):
    values_here = report_reads.Report.values_here
    condition_names = report_reads.Report.condition_names
    condition_label = report_reads.Report.condition_label
    conditions_at = []


def _related(report, candidates, values_to_fill, caplog):
    steps = []
    spec = {"layout": [{"kind": "text", "slot": "summary"}], "causes": CAUSES}
    with caplog.at_level(logging.WARNING, logger="Chain"):
        report_loop._related(report, spec, REQUEST, report_loop.Budget(16000), Model({"conditions": {}, "why": "W"}),
                             _clock(), steps, [(1, "read", [])], {}, candidates, values_to_fill=values_to_fill)
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Report] causes to fill")]
    caplog.clear()
    return steps[-1]["read"], said


def test_declared_the_values_step_alone_says_what_is_to_be_filled(ledger, caplog):
    report = Related()
    said = report.values(CANDIDATES)
    own, cd = said["labels"]
    assert said["to_fill"] == [cd] and report.values_here(own)      # canary: one valued, one to fill
    candidates = CANDIDATES + [{"id": n, "type": None, "label": n} for n in (own, cd, "another product's")]
    read, filled = _related(report, candidates, said["to_fill"], caplog)
    assert read == ["%s: %s" % (cd, TO_FILL)], "the via, the valued one, another product's: no line"
    every = said["context"].splitlines() + read
    assert len([line for line in every if line.startswith(own + ":")]) == 1
    assert filled == ["[Report] causes to fill: %s" % cd]


def test_undeclared_every_unrelated_candidate_is_to_be_filled_as_before(ledger, caplog):
    report = Related()
    candidates = CANDIDATES + [{"id": "q", "type": None, "label": "q"}]
    read, filled = _related(report, candidates, None, caplog)
    assert read == ["via: %s" % TO_FILL, "q: %s" % TO_FILL]
    assert filled == ["[Report] causes to fill: via, q"]
