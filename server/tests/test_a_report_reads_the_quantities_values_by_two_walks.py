# -*- coding: utf-8 -*-
"""Lead 10-27 B-2 (owner 10-26 «걷기 해서 모델링 상 닿는 퀀티티의 각 wf 자재들 매칭해서 표에 추가»): `causes.values` -
the measured values of the quantities the model walk reaches, per wafer, as condition rows.

  model walk    from the cause walk's candidates along `follow` + `order`'s predicate: structures, the quantities that
                describe them, each quantity's measuring step, the steps acting on its structure
  wafer walk    every wafer of the report and its compares at once along `value`'s and `event`'s predicates, bound by its
                transaction qualifier, read to its end page by page
  own           a wafer's own value of the quantity
  est           none: the step acting on the quantity's structure just before its measuring step (`order`'s key) -
                the values of the wafers of the wafer's transaction there - one its value, several their mean and n
  to fill       a quantity the wafers met with no value anywhere; another product's quantity is no row

The route is the walk route's own function in process over an in-memory ledger; the declaration is the committed
sample's (the names A's modeling writes), so a name this file spells and the sample does not is red here.
"""
import io
import json
import os
import uuid
from datetime import datetime, timezone

import pytest

from chain import report_loop, report_reads, report_shape
from ledger import explorer, trace_router
from ledger_api import ledger_subgraph

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "config", "sample", "ledger_config.json.sample")
NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
VALUES = {"follow": ["of_kind", "describes", "acts_on"], "value": "measures:value",
          "event": "processed_at:tx_id", "order": ["measured_at", "step_seq"]}
CAUSES = {"seed_type": "defect_kind", "values": VALUES}


def _sample():
    with io.open(SAMPLE, encoding="utf-8") as handle:
        return json.load(handle)


def _atom(n, subject_type, subject_keys, predicate, object_type, object_keys, **qualifiers):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=n)), subject_type=subject_type, subject_keys=subject_keys, predicate=predicate,
        object_kind="entity_ref", object_payload={"type": object_type, "keys": object_keys, "qualifiers": qualifiers},
        occurred_at=NOW, source_who="fixture", source_translator_ver="v1", source_raw_ref="row:%d" % n,
        supersedes=None, source_event_id=str(uuid.UUID(int=100000 + n)), source_event_state="source_record")


def _step(product, seq):
    return {"product": product, "step_seq": seq}


S_PA, S_PB = {"product": "PA", "structure": "M2/via"}, {"product": "PB", "structure": "M2/via"}
#: the quantities' own keys carry the product's two-digit step prefix, as the ops metro step does - the report reads
#: the step from `measured_at`, never from the key or the measures qualifier (lead 10-27)
THK, CD, THK_B = {"quantity": "PA40-THK"}, {"quantity": "PA60-CD"}, {"quantity": "PB40-THK"}


def _model():
    """via <-of_kind- the structure of PA and of PB; PA's THK measured at 40 and CD at 60, steps 20 · 30 · 50 acting on
    PA's structure (30 is the one just before 40); PB's THK at PB 40 with PB 30 acting - no wafer here is PB's."""
    n, atoms = [0], []

    def add(*args, **qualifiers):
        n[0] += 1
        atoms.append(_atom(n[0], *args, **qualifiers))

    for structure in (S_PA, S_PB):
        add("product_structure", structure, "of_kind", "physical_object", {"physical_object": "via"})
    for quantity, structure, at in ((THK, S_PA, _step("PA", 40)), (CD, S_PA, _step("PA", 60)),
                                    (THK_B, S_PB, _step("PB", 40))):
        add("quantity", quantity, "describes", "product_structure", structure)
        add("quantity", quantity, "measured_at", "process_step", at)
    for step, structure in ((_step("PA", 20), S_PA), (_step("PA", 30), S_PA), (_step("PA", 50), S_PA),
                            (_step("PB", 30), S_PB)):
        add("process_step", step, "acts_on", "product_structure", structure)
    return atoms


def _wafers(own=True):
    """W1 its own 12.3 · W2 T1 at PA 30 with S1 (12.0) · W3 T3 with S3a/b/c (11, 12, 13) and S9 under T9 (99) and S5 at
    PA 50 (50) beside it · W0 (the compare) T0 alone · W1 also through PA 60 (CD: no value anywhere)."""
    n, atoms = [5000], []

    def add(wafer, predicate, object_type, object_keys, **qualifiers):
        n[0] += 1
        atoms.append(_atom(n[0], "wafer", {"wafer": wafer}, predicate, object_type, object_keys, **qualifiers))

    if own:
        add("W1", "measures", "quantity", THK, value=12.3, step="PA40")
    for wafer, tx in (("W1", "T1w"), ("W2", "T1"), ("S1", "T1"), ("W3", "T3"), ("S3a", "T3"), ("S3b", "T3"),
                      ("S3c", "T3"), ("S9", "T9"), ("W0", "T0")):
        add(wafer, "processed_at", "process_step", _step("PA", 30), tx_id=tx)
    add("W3", "processed_at", "process_step", _step("PA", 50), tx_id="T3")
    add("S5", "processed_at", "process_step", _step("PA", 50), tx_id="T3")
    add("W1", "processed_at", "process_step", _step("PA", 60), tx_id="T6")
    for wafer, value in (("S1", 12.0), ("S3a", 11.0), ("S3b", 12.0), ("S3c", 13.0), ("S9", 99.0), ("S5", 50.0)):
        add(wafer, "measures", "quantity", THK, value=value, step="PA40")
    return atoms


@pytest.fixture
def ledger(monkeypatch):
    """The walk route over `held["atoms"]`, the sample's declaration; each walk counted."""
    held = {"atoms": _model() + _wafers(), "walks": []}
    sample = _sample()
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: sample)
    monkeypatch.setattr(trace_router.trace, "relation_exists", lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state", lambda *a, **k: [])
    monkeypatch.setattr(ledger_subgraph, "SqlEvidenceLookup",
                        lambda connection, worlds=None, **window:
                        ledger_subgraph.InMemoryEvidenceLookup(held["atoms"], **window))
    walk = report_reads._walk

    def counted(db, cell, **asked):
        held["walks"].append((cell, asked))
        return walk(db, cell, **asked)

    monkeypatch.setattr(report_reads, "_walk", counted)
    return held


class DB:
    def connection(self):
        return "CONNECTION"


class Reads:
    """The report's values read on a stand-in for the table reads - three wafers of this report, one compare."""

    _causes = report_reads.Report._causes
    values = report_reads.Report.values
    said = report_reads.Report.said

    def __init__(self, causes=CAUSES):
        self.spec = {"causes": causes}
        self.db, self.keys = DB(), ["wafer"]
        self.evaluation = "E1"
        self.groups = {"E1": [("W1",), ("W2",), ("W3",)], "control E0": [("W0",)]}
        self.wafers = {w: {"conditions": {"anneal": "on"}} for members in self.groups.values() for w in members}


VIA = explorer.entity_id("physical_object", {"physical_object": "via"})
CANDIDATES = [{"id": VIA, "type": "physical_object", "label": "via", "path": "void <-leads_to- via"}]


def _cells(report, name):
    return {w[0]: report.wafers[w]["conditions"].get(name) for w in report.wafers}


def test_own_value_one_wafer_estimate_three_wafer_mean_and_none(ledger):
    report = Reads()
    said = report.values(CANDIDATES)
    thk = said["labels"][0]
    cells = _cells(report, thk)
    assert cells["W1"] == "12.3", "its own value"
    assert cells["W2"] == "12 (est · %s · 1 wf)" % _step_label(ledger), "T1's one sibling at PA 30, not 99 of T9"
    assert cells["W3"] == "12 (est · %s · 3 wf)" % _step_label(ledger), "T3's three at PA 30, not S5 at PA 50"
    assert cells["W0"] is None, "T0 alone - nothing to estimate from"
    line = [l for l in said["context"].splitlines() if l.startswith(thk + ":")][0]
    assert line == "%s: wafer W1 12.3 · wafer W2 12 (est, 1 wf) · wafer W3 12 (est, 3 wf) · wafer W0 -" % thk


def _step_label(ledger):
    """The label the walk gives PA 30 - read back, not spelled here."""
    body = ledger_subgraph.subgraph(explorer.entity_id("process_step", _step("PA", 30)),
                                    ledger_subgraph.InMemoryEvidenceLookup(ledger["atoms"]), hops=0)
    return body["nodes"][0]["label"]


def test_a_quantity_met_with_no_value_is_to_fill_and_another_products_is_no_row(ledger):
    report = Reads()
    said = report.values(CANDIDATES)
    labels = said["labels"]
    assert len(labels) == 2, labels
    cd = [label for label in labels if "CD" in label]
    assert said["to_fill"] == cd and all(v is None for v in _cells(report, cd[0]).values())
    assert not any("PB" in label for label in labels), "PB's quantity - no wafer here met PB's steps"
    assert "%s: " % cd[0] in said["context"] and report_shape.LABELS["to_fill"] in said["context"]


def test_two_walks_one_from_the_candidates_one_from_every_wafer(ledger):
    Reads().values(CANDIDATES)
    cells = [cell for cell, _asked in ledger["walks"]]
    assert cells == ["derive.report.causes.values.follow", "derive.report.causes.values"], cells
    model, wafers = ledger["walks"][0][1], ledger["walks"][1][1]
    assert (model["node_id"], model["follow"]) == (VIA, ["of_kind", "describes", "acts_on", "measured_at"])
    seeds = [wafers["node_id"]] + list(wafers["positive"] or ())
    assert seeds == [explorer.entity_id("wafer", {"wafer": w}) for w in ("W1", "W2", "W3", "W0")]
    assert wafers["follow"] == ["measures", "processed_at:tx_id"] and wafers["hops"] == 3


def test_without_own_values_every_cell_is_an_estimate_or_blank(ledger):
    """The estimate is what fills a wafer with no value - with W1's own gone, W1 (T1w alone at PA 30) is blank."""
    ledger["atoms"] = _model() + _wafers(own=False)
    report = Reads()
    thk = report.values(CANDIDATES)["labels"][0]
    cells = _cells(report, thk)
    assert cells["W1"] is None and cells["W2"].endswith("· 1 wf)") and cells["W3"].endswith("· 3 wf)")


@pytest.mark.parametrize("values, said", [
    (dict(VALUES, follow=["of_kind", "nope"]), "names nope - not a predicate the ledger declares"),
    (dict(VALUES, event="processed_at:lot"), "lot is not a qualifier of processed_at (declared: tx_id)"),
    (dict(VALUES, value="measures:weight"), "weight is not a qualifier of measures"),
    (dict(VALUES, order=["measured_at", "seq"]), "seq is not a key of measured_at's step (process_step)"),
    (dict(VALUES, event="processed_at"), 'derive.report.causes.values is {"follow"'),
    (dict(VALUES, extra=1), 'derive.report.causes.values is {"follow"'),
])
def test_a_name_the_ledger_does_not_declare_is_refused_at_save(monkeypatch, values, said):
    sample = _sample()
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: sample)
    assert said in report_shape._causes_refusal({"seed_type": "defect_kind", "values": values})
    assert report_shape._causes_refusal({"seed_type": "defect_kind", "values": VALUES}) is None


SPEC = {"layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}],
        "loop": {"steps": 2, "seconds": 300, "context_tokens": 16000}, "causes": CAUSES}


class Run(Reads):
    """The report loop's view: the cause walk's two reads stood in, the values read the product's."""

    def __init__(self):
        super().__init__()
        self.drawn = []

    def seed_nodes(self):
        return {"context": "1 defect_kind node(s)\nvoid", "nodes": {"void": "id-void"}}

    def causes(self, seeds):
        return {"context": "void: 1 node(s) reached\nphysical_object via: void <-leads_to- via",
                "candidates": CANDIDATES}

    def condition_names(self):
        return ["anneal"]

    def conditions(self, keyword=None):
        return {"context": "3 wafers in E1", "html": None}

    def yield_by(self, wafers=None, by=None, rows=None, also=None):
        self.drawn.append(list(also or ()))
        return {"context": "yield_by", "html": {"info": [(name, []) for name in also or ()], "rows": []}}

    def pareto(self, wafers=None):
        return {"context": "void 9", "html": {"rows": []}}

    def pick_basis(self):
        return []


class Model:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, prompt, usage=None):
        self.prompts.append(prompt)
        return self.answers.pop(0)


def _clock():
    now = [0.0]

    def tick():
        now[0] += 1.0
        return now[0]
    return tick


def test_the_values_are_a_step_before_the_candidates_conditions_and_stand_as_rows(ledger):
    model = Model({"done": {}}, {"seeds": ["void"], "why": "v"}, {"conditions": {}}, {"done": {"summary": "S"}})
    report = Run()
    out = report_loop.run(report, SPEC, {"evaluation": "E1", "sets": [], "note": None}, ask=model, clock=_clock())
    calls = [s["call"] for s in out["steps"]]
    assert calls[calls.index("product seed_nodes()"):] == [
        "product seed_nodes()", 'causes({"seeds": ["void"]})', report_loop.VALUES_CALL, "candidate conditions", "write"]
    values = out["steps"][calls.index(report_loop.VALUES_CALL)]
    assert values["refused"] is None and values["summary"].startswith("1 quantit(ies) with values on these wafers, 1 to")
    labels = [line.split(":")[0] for line in values["read"]]
    assert report.written_rows == labels and report.drawn[1] == labels, "the quantities stand as yield_by rows"
    relate = model.prompts[2]
    assert "step %d: %s" % (values["step"], report_loop.VALUES_CALL) in relate, "the candidates' conditions read it"
    assert "step %d: %s" % (values["step"], report_loop.VALUES_CALL) in model.prompts[3], "and the write"
