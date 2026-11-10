# -*- coding: utf-8 -*-
"""The AI report's prompt and a hub (소유자 10-27 «허브 노드 거쳐 버리면 AI 컨텍스트 꽉 찰 텐데», B probe 51ec2fa68): one report
run - the walk route's own function over an in-memory ledger on the committed sample's declaration, the model a
stand-in - with a hub of 500 product structures is_a one physical object, each described by a quantity.

  one line     `causes.fanout_limit` folds the step: the hub is one line of the prompt (the walk card's line),
               never a candidate, said once; without it the members fill the prompt (the probe: 50,971 characters)
  own tables   the report's own tables (conditions · pareto) are cut last - a narrowed budget cuts the walk's rows first
  said         a cut is said in the prompt, rows kept of rows read
"""
import uuid
from datetime import datetime, timezone

import pytest

from chain import report_loop, report_reads, report_shape
from ledger import trace_router
from ledger_api import ledger_subgraph
from support import declaration

pytestmark = pytest.mark.usefixtures("stored_walks")   # a stored-only ledger fixture (11-10)

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
MEMBERS = 500


def _atom(n, subject_type, subject_keys, predicate, object_type, object_keys):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=n)), subject_type=subject_type, subject_keys=subject_keys, predicate=predicate,
        object_kind="entity_ref", object_payload={"type": object_type, "keys": object_keys, "qualifiers": {}},
        occurred_at=NOW, source_who="fixture", source_translator_ver="v1", source_raw_ref="row:%d" % n,
        supersedes=None, source_event_id=str(uuid.UUID(int=100000 + n)), source_event_state="source_record")


def _atoms(members=MEMBERS):
    """void <-leads_to- wetting -describes-> A/M2 -is_a-> via, and `members` more structures is_a via, each
    described by a quantity of its own. One instant for all, so the read's order is their content (lead 11-07): A/M2,
    the way in, reads after every P - the fold's first 20 are 20 of the P's."""
    n, atoms = [0], []

    def add(*args):
        n[0] += 1
        atoms.append(_atom(n[0], *args))

    add("quantity", {"quantity": "wetting"}, "leads_to", "defect_kind", {"defect_kind": "void"})
    add("quantity", {"quantity": "wetting"}, "describes", "product_structure", {"product": "A", "structure": "M2"})
    add("product_structure", {"product": "A", "structure": "M2"}, "is_a", "physical_object",
        {"physical_object": "via"})
    for i in range(members):
        structure = {"product": "P%03d" % i, "structure": "M2"}
        add("product_structure", structure, "is_a", "physical_object", {"physical_object": "via"})
        add("quantity", {"quantity": "P%03d-THK" % i}, "describes", "product_structure", structure)
    return atoms


@pytest.fixture
def ledger(monkeypatch):
    atoms = _atoms()
    sample = declaration.committed_walk_declaration()
    monkeypatch.setattr(trace_router, "_declaration", lambda world=None: sample)
    monkeypatch.setattr(trace_router.trace, "relation_exists", lambda *a, **k: True)
    monkeypatch.setattr(trace_router, "_subgraph_contract_state", lambda *a, **k: [])
    monkeypatch.setattr(ledger_subgraph, "SqlEvidenceLookup",
                        lambda connection, worlds=None, **window: ledger_subgraph.InMemoryEvidenceLookup(atoms, **window))


class DB:
    def connection(self):
        return "CONNECTION"


class Reads:
    _causes = report_reads.Report._causes
    seed_nodes = report_reads.Report.seed_nodes
    causes = report_reads.Report.causes
    condition_names = report_reads.Report.condition_names
    _condition = report_reads.Report._condition
    values_here = report_reads.Report.values_here
    condition_label = report_reads.Report.condition_label

    def __init__(self, causes):
        self.spec = {"causes": dict(causes)}
        self.db, self.overlaps, self.embedded = DB(), {}, {}
        self.evaluation, self.groups = "E1", {"E1": ["w1"], "control E0": ["w0"]}
        self.conditions_at = []
        self.wafers = {"w1": {"conditions": {"bond_temp": "350"}}, "w0": {"conditions": {"bond_temp": "300"}}}

    def yield_by(self, wafers=None, by=None, rows=None, also=None):
        return {"context": "yield_by", "html": {"info": [], "rows": []}}

    def conditions(self, keyword=None):
        return {"context": "1 wafer in E1", "html": None}

    def pareto(self, wafers=None):
        return {"context": "void 9 (cum 90.0%)\ndelam 1 (cum 100.0%)", "html": {"rows": []}}

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


CAUSES = {"seed_type": "defect_kind", "follow": ["leads_to", "describes", "is_a"], "collect": ["quantity"]}


def _run(causes, tokens=16000):
    spec = {"layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "pareto"}],
            "loop": {"steps": 2, "seconds": 300, "context_tokens": tokens}, "causes": causes}
    model = Model({"done": {}}, {"seeds": ["void"], "why": "w"}, {"conditions": {}}, {"done": {"summary": "S"}})
    out = report_loop.run(Reads(causes), spec, {"evaluation": "E1", "sets": [], "note": None}, ask=model,
                          clock=_clock())
    return out, model


def test_a_hub_is_one_line_never_a_candidate_and_the_tables_stand(ledger):
    folded, model = _run(dict(CAUSES, fanout_limit=20))
    unfolded, plain = _run(CAUSES)
    write = model.prompts[-1]
    hub_lines = [line for line in write.splitlines() if line.startswith("- hub: ")]
    assert len(hub_lines) == 1, hub_lines
    # the 500 structures past the first 20 walk on as a set; their quantities past the first 20 are the hub
    assert "from: product_structure via is_a; " in hub_lines[0], hub_lines
    assert "far_type: quantity; count: %d; " % (MEMBERS - 20 - 20) in hub_lines[0], hub_lines
    walked = next(step for step in folded["steps"] if step["call"].startswith("causes("))
    assert walked["read"].count(hub_lines[0]) == 1 and not any(line.startswith("- hub: ") for line in walked["read"][
        :-1]), "the hub line is the walk's last, after the candidates"
    assert folded["steps"][-1]["cut"] == {} and "void 9 (cum 90.0%)" in write, "the report's own tables stand whole"
    print("write prompt: %d characters folded, %d unfolded (box: in-memory ledger, a stand-in model)" % (
        len(write), len(plain.prompts[-1])))
    assert len(write) < len(plain.prompts[-1]) // 5


def test_the_hub_is_not_handed_to_relate_or_values(ledger, monkeypatch):
    seen = []
    monkeypatch.setattr(report_loop, "_related", lambda report, spec, request, budget, ask, clock, steps, reads,
                        tables, candidates, first=-1, values_to_fill=None: seen.extend(c["id"] for c in candidates))
    _run(dict(CAUSES, fanout_limit=20))
    assert seen and not [c for c in seen if c.startswith(ledger_subgraph.HUB_PREFIX)]


def test_a_narrowed_budget_cuts_the_walks_rows_before_the_reports_own_tables():
    reads = [(0, "conditions()", ["split: value %d" % n for n in range(8)]),
             (2, "product pareto()", ["void %d" % n for n in range(8)]),
             (4, 'causes({"seeds": ["void"]})', ["candidate %d" % n for n in range(400)]),
             (5, report_loop.RELATED_CALL, ["related %d" % n for n in range(400)])]
    prompt, cut = report_loop.compose_write({}, {"evaluation": "E1"}, reads, report_loop.Budget(500))
    assert prompt is not None and set(cut) <= {'step 4 causes({"seeds": ["void"]})', "step 5 candidate conditions"}, cut
    assert "void 7" in prompt and "split: value 7" in prompt, "the report's own tables stand"
    said = [line for line in prompt.splitlines() if line.startswith("Rows cut to fit the context: ")]
    assert said == ["Rows cut to fit the context: " + ", ".join(
        "%s %d of 400" % (name, kept) for name, kept in cut.items())], said


def test_the_fanout_limit_is_a_whole_number_from_one():
    assert report_shape._causes_refusal({"seed_type": "defect_kind", "fanout_limit": 20}) is None
    for bad in (0, "20", 2.5, True):
        assert "fanout_limit" in report_shape._causes_refusal({"seed_type": "defect_kind", "fanout_limit": bad})
