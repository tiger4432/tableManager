# -*- coding: utf-8 -*-
"""Owner 10-25 (lead: the last stage, before the write): with `derive.report.causes` the product lists the declared
type's nodes, the model picks the seed(s) and says why by the tables read, the product walks the static layer from
them with the walk route's own function in process, and the candidates and their paths go to the write call.

  seed_nodes  the walk's described seeds of `causes.seed_type`, no step - a name a line
  causes        names (or ids) of those nodes -> one walk along `follow` (blank: the declaration's static-to-static
                predicates), keeping `collect`, `hops` the walk's own when blank; a candidate a line with its path
  refused       not declared · no seed · a seed not of the type · no follow and none static · the route's refusal,
                each said under derive.report.causes
  run           seed call between the product's reads and the write; its why and the candidates in the Evidence;
                absent cell: no seed call, no walk; a refused seed: the report is written without candidates
  relate        (owner 10-25) one model call relates the candidates to the report's conditions - a name not a
                condition, or not a candidate, dropped and said; the related ones stand as yield_by rows (`also`)
                beside the ones the texts name; each said with its values per column, or to be filled (labels.to_fill)
"""
import functools
import inspect
import logging

import pytest
from fastapi import HTTPException

from chain import report_loop, report_reads
from ledger import trace_router

VOID, DELAM, WET, TEMP = "id-void", "id-delam", "id-wetting", "id-bond-temp"
CAUSES = {"seed_type": "defect_kind", "follow": ["leads_to"], "collect": ["quantity"], "hops": 4}
KINDS = {"nodes": [{"id": DELAM, "type": "defect_kind", "label": "delam"},
                   {"id": VOID, "type": "defect_kind", "label": "void"}], "truncated": {"seeds": 0}}
WALKED = {
    "nodes": [{"id": VOID, "type": "defect_kind", "label": "void"},
              {"id": WET, "type": "quantity", "label": "wetting"},
              {"id": TEMP, "type": "quantity", "label": "bond_temp"}],
    "edges": [{"source": WET, "target": VOID, "predicate": "leads_to"},
              {"source": TEMP, "target": WET, "predicate": "leads_to"}],
    "propagation": {"ranked": [
        {"id": WET, "evidence": [{"hops": [{"id": VOID, "label": "void"},
                                           {"id": WET, "label": "wetting", "predicates": ["leads_to"]}]}]},
        {"id": TEMP, "evidence": [{"hops": [{"id": VOID, "label": "void"},
                                            {"id": WET, "label": "wetting", "predicates": ["leads_to"]},
                                            {"id": TEMP, "label": "bond_temp", "predicates": ["leads_to"]}]}]}]},
    "truncated": {"reason": None},
}
CANDIDATES = ["quantity wetting: void <-leads_to- wetting",
              "quantity bond_temp: void <-leads_to- wetting <-leads_to- bond_temp"]


class Reads:
    """The report's own two cause reads on a stand-in for the table reads."""

    _causes = report_reads.Report._causes
    seed_nodes = report_reads.Report.seed_nodes
    causes = report_reads.Report.causes
    condition_names = report_reads.Report.condition_names
    _condition = report_reads.Report._condition
    values_here = report_reads.Report.values_here
    condition_label = report_reads.Report.condition_label

    def __init__(self, causes=CAUSES):
        self.spec = {"causes": dict(causes)} if causes is not None else {}
        self.db, self.overlaps, self.embedded = "DB", {}, {}
        self.evaluation, self.groups = "E1", {"E1": ["w1"], "control E0": ["w0"]}
        self.conditions_at = []
        self.wafers = {"w1": {"conditions": {"bond_temp": "350", "anneal": None}},
                       "w0": {"conditions": {"bond_temp": "300", "anneal": "on", "chuck": "B"}}}
        self.drawn = []

    def yield_by(self, wafers=None, by=None, rows=None, also=None):
        """Draws the conditions `also` names, a cell a wafer column - the rows the declaration's path adds."""
        self.drawn.append(list(also or ()))
        info = [(name, [{"text": str(self.wafers[w]["conditions"].get(name) or "")} for w in ("w1", "w0")])
                for name in also or ()]
        return {"context": "yield_by", "html": {"info": info, "rows": []}}

    def conditions(self, keyword=None):
        return {"context": "1 wafer in E1", "html": None}

    def pareto(self, wafers=None):
        return {"context": "void 9 (cum 90.0%)\ndelam 1 (cum 100.0%)", "html": {"rows": []}}

    def pick_basis(self):
        return []


@pytest.fixture
def walks(monkeypatch):
    asked = []

    def walk(db, cell, **args):
        asked.append((cell, args))
        return KINDS if args.get("seed_type") else WALKED

    monkeypatch.setattr(report_reads, "_walk", walk)
    return asked


def test_seed_nodes_are_the_declared_types_nodes_a_name_a_line(walks):
    said = Reads().seed_nodes()
    assert walks == [("derive.report.causes.seed_type", {"seed_type": "defect_kind", "hops": 0, "propagation": False})]
    assert said["context"] == "2 defect_kind node(s)\ndelam\nvoid"
    assert said["nodes"] == {"delam": DELAM, "void": VOID}


def test_seed_nodes_say_how_many_the_seed_cap_left_out(monkeypatch):
    monkeypatch.setattr(report_reads, "_walk", lambda db, cell, **a: dict(KINDS, truncated={"seeds": 3}))
    assert Reads().seed_nodes()["context"].splitlines()[0] == "2 defect_kind node(s) - 3 more not listed"


def test_causes_walk_from_the_named_seeds_and_keep_each_candidates_path(walks):
    said = Reads().causes(["void"])
    assert walks[-1] == ("derive.report.causes", {"node_id": VOID, "positive": None, "follow": ["leads_to"],
                                                   "collect": ["quantity"], "propagation": True, "hops": 4})
    assert said["context"].splitlines() == [
        "void: 2 node(s) reached along leads_to, 2 candidate(s) kept (collect: quantity)"] + CANDIDATES
    assert [c["id"] for c in said["candidates"]] == [WET, TEMP], "the seed is not a candidate"


def test_the_declared_worlds_are_every_walks_and_the_static_predicates(walks, monkeypatch):
    """owner 10-26 «보고서 생성 시 걷기 세계 여러 개 지정되게»: causes.worlds reaches the seed list, the walk and the
    blank follow's declaration."""
    asked_worlds = []
    monkeypatch.setattr(trace_router, "_static_step_predicates", lambda world=None: asked_worlds.append(world) or {"leads_to"})
    Reads({"seed_type": "defect_kind", "worlds": ["ops", "lab"]}).causes(["void"])
    assert [w[1].get("world") for w in walks[-2:]] == [["ops", "lab"], ["ops", "lab"]]
    assert asked_worlds == [["ops", "lab"]]


def test_two_seeds_by_name_or_id_walk_once_with_the_second_positive(walks):
    Reads().causes(["void", DELAM, "void"])
    assert (walks[-1][1]["node_id"], walks[-1][1]["positive"]) == (VOID, [DELAM])


def test_a_blank_follow_is_the_declarations_static_predicates_and_a_blank_hops_the_walks(walks, monkeypatch):
    monkeypatch.setattr(trace_router, "_static_step_predicates", lambda world=None: {"leads_to", "a_to"})
    Reads({"seed_type": "defect_kind"}).causes(["void"])
    asked = walks[-1][1]
    assert asked["follow"] == ["a_to", "leads_to"] and asked["collect"] is None and "hops" not in asked
    monkeypatch.setattr(trace_router, "_static_step_predicates", lambda world=None: set())
    with pytest.raises(report_reads.ReadRefused, match="derive.report.causes.follow is blank and the ledger declares "
                                                       "no predicate between two static types"):
        Reads({"seed_type": "defect_kind"}).causes(["void"])


@pytest.mark.parametrize("seeds, said", [
    (["particle"], "particle is not a defect_kind node - one of delam, void"),
    ([], "no seed picked - one or more of the defect_kind nodes: delam, void"),
    ([" "], "no seed picked"),
])
def test_a_seed_not_of_the_type_is_refused_by_name(walks, seeds, said):
    with pytest.raises(report_reads.ReadRefused, match=said):
        Reads().causes(seeds)
    assert all("node_id" not in args for _cell, args in walks), "no walk"


def test_undeclared_the_reads_are_refused_naming_the_cell(walks):
    for read in (lambda r: r.seed_nodes(), lambda r: r.causes(["void"])):
        with pytest.raises(report_reads.ReadRefused, match="derive.report.causes is not declared"):
            read(Reads(causes=None))
    assert walks == []


def test_the_walk_is_the_route_function_called_with_every_argument_and_its_refusal_said(monkeypatch):
    route, got = trace_router.evidence_subgraph, {}

    @functools.wraps(route)
    def stand_in(**kwargs):
        got.update(kwargs)
        if kwargs["follow"] == ["nope"]:
            raise HTTPException(status_code=422, detail={"message": "Not a declared predicate: nope"})
        return {"nodes": []}

    monkeypatch.setattr(trace_router, "evidence_subgraph", stand_in)
    assert report_reads._walk("DB", "derive.report.causes", node_id=VOID, follow=["leads_to"]) == {"nodes": []}
    assert set(got) == set(inspect.signature(route).parameters)
    assert (got["db"], got["node_id"], got["follow"], got["seed_type"], got["response_format"]) == (
        "DB", VOID, ["leads_to"], None, "json")
    sentinels = {name for name, value in got.items() if type(value).__module__.startswith("fastapi")}
    assert sentinels == set(), "a direct call left FastAPI's parameter objects in %s" % sorted(sentinels)
    with pytest.raises(report_reads.ReadRefused, match="derive.report.causes: Not a declared predicate: nope"):
        report_reads._walk("DB", "derive.report.causes", follow=["nope"])


SPEC = {"layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "pareto"}],
        "loop": {"steps": 2, "seconds": 300, "context_tokens": 16000}, "causes": CAUSES}
REQUEST = {"evaluation": "E1", "sets": [], "note": None}


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


def test_the_seed_call_comes_before_the_write_and_the_candidates_go_to_it(walks, caplog):
    model = Model({"done": {}}, {"seeds": ["void"], "why": "void tops the pareto"}, {"conditions": {}},
                  {"done": {"summary": "S"}})
    report = Reads()
    with caplog.at_level(logging.WARNING, logger="Chain"):
        out = report_loop.run(report, SPEC, REQUEST, ask=model, clock=_clock())
    assert (out["state"], out["texts"]) == ("done", {"summary": "S"})
    assert [s["call"] for s in out["steps"]] == ["done", "product pareto()", "product seed_nodes()",
                                                 'causes({"seeds": ["void"]})', "candidate conditions", "write"]
    seed = model.prompts[1]
    assert report_loop.SEEDS % "defect_kind" in seed
    assert seed.index("delam\nvoid") < seed.index("Tables read:") < seed.index("void 9 (cum 90.0%)")
    assert "Write the report" not in seed
    write = model.prompts[3]
    assert "\n".join(['step 4: causes({"seeds": ["void"]})',
                      "void: 2 node(s) reached along leads_to, 2 candidate(s) kept (collect: quantity)"]
                     + CANDIDATES) in write
    walked = out["steps"][3]
    assert (walked["why"], walked["refused"], walked["read"]) == ("void tops the pareto", None, CANDIDATES)
    evidence = report_loop._steps_text(out, report)
    assert "    why: void tops the pareto\n    " + CANDIDATES[0] in evidence
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[report] causes")]
    assert said == ["[report] causes: 2 defect_kind node(s) - delam, void",
                    "[report] causes seeds void - void tops the pareto",
                    "[report] causes walk from void: 2 node(s) reached along leads_to, 2 candidate(s) kept "
                    "(collect: quantity)", "[report] causes conditions: none", "[report] causes to fill: wetting, bond_temp"]


def test_without_the_cell_there_is_no_seed_call_and_no_walk(walks):
    model = Model({"done": {}}, {"done": {"summary": "S"}})
    spec = {k: v for k, v in SPEC.items() if k != "causes"}
    out = report_loop.run(Reads(causes=None), spec, REQUEST, ask=model, clock=_clock())
    assert [s["call"] for s in out["steps"]] == ["done", "product pareto()", "write"]
    assert len(model.prompts) == 2 and walks == []


def test_a_refused_seed_is_its_steps_and_the_report_is_written_without_candidates(walks):
    model = Model({"done": {}}, {"seeds": ["particle"], "why": "w"}, {"done": {"summary": "S"}})
    out = report_loop.run(Reads(), SPEC, REQUEST, ask=model, clock=_clock())
    walked = out["steps"][3]
    assert walked["refused"] == "particle is not a defect_kind node - one of delam, void"
    assert (out["state"], out["steps"][-1]["call"]) == ("done", "write")
    assert "causes(" not in model.prompts[2]


def test_a_seed_the_ontology_has_not_is_left_out_and_said(walks):
    """Owner 10-26 «디펙카인드 없는 거 아예 에러» (안 ㄱ): the known seeds are walked, each unknown one a line of the
    walk's read - the write call's and the Evidence's; every seed unknown is refused as before."""
    model = Model({"done": {}}, {"seeds": ["void", "particle"], "why": "w"}, {"conditions": {}},
                  {"done": {"summary": "S"}})
    report = Reads()
    out = report_loop.run(report, SPEC, REQUEST, ask=model, clock=_clock())
    walked = out["steps"][3]
    said = "particle: no defect_kind node - add it to the ontology"
    assert (walked["call"], walked["refused"], walked["read"]) == (
        'causes({"seeds": ["void", "particle"]})', None, [said] + CANDIDATES), walked
    assert said in model.prompts[3] and said in report_loop._steps_text(out, report)
    assert [args["node_id"] for _cell, args in walks if "node_id" in args] == [VOID]


def test_a_walk_that_fails_stops_its_step_and_the_report_is_written(walks, monkeypatch):
    def fails(self, seeds):
        raise RuntimeError("the graph is gone")
    monkeypatch.setattr(Reads, "causes", fails)
    model = Model({"done": {}}, {"seeds": ["void"], "why": "w"}, {"done": {"summary": "S"}})
    out = report_loop.run(Reads(), SPEC, REQUEST, ask=model, clock=_clock())
    assert out["steps"][3]["refused"] == "the read failed: RuntimeError: the graph is gone"
    assert (out["state"], out["texts"], out["steps"][-1]["call"]) == ("done", {"summary": "S"}, "write")


WITH_TABLE = dict(SPEC, layout=SPEC["layout"] + [{"kind": "table", "fill": "yield_by"}])
TO_FILL = "no value on these wafers - to be filled (measured/recorded)"
RELATED = {"conditions": {"bond_temp": ["Bond_Temp ", "bake"], "wetting": ["anneal"], "ghost": ["x"]}, "why": "W"}


def test_the_candidates_conditions_stand_as_table_rows_and_are_said_with_their_values(walks, caplog):
    model = Model({"done": {}}, {"seeds": ["void"], "why": "v"}, RELATED, {"done": {"summary": "S"}})
    report = Reads()
    with caplog.at_level(logging.WARNING, logger="Chain"):
        out = report_loop.run(report, WITH_TABLE, REQUEST, ask=model, clock=_clock())
    relate, write = model.prompts[2], model.prompts[3]
    assert report_loop.RELATE in relate and "Conditions: bond_temp, anneal, chuck" in relate
    assert relate.index("Tables read:") < relate.index(CANDIDATES[1]), "the walk's read is what it relates"
    assert report.written_rows == ["anneal", "bond_temp"] and report.drawn == [[], ["anneal", "bond_temp"]]
    assert [label for label, _cells in out["tables"]["yield_by"]["info"]] == ["anneal", "bond_temp"]
    lines = ["2 of 2 candidate(s) related to the conditions - not conditions, dropped: bake, ghost",
             "wetting -> anneal: %s - the other columns:  | on" % TO_FILL,
             "bond_temp -> bond_temp: 350 | 300"]
    related = out["steps"][5]
    assert (related["call"], related["why"], [related["summary"]] + related["read"]) == (
        "candidate conditions", "W", lines)
    assert "\n".join(["step 6: candidate conditions"] + lines) in write
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[report] causes ")][-2:]
    assert said == ["[report] causes conditions: wetting -> anneal; bond_temp -> bond_temp (dropped bake, ghost)",
                    "[report] causes to fill: wetting"]


def test_the_conditions_the_texts_name_join_the_related_ones_in_the_table(walks):
    model = Model({"done": {}}, {"seeds": ["void"]}, RELATED, {"done": {"summary": "chuck B mattered"}})
    report = Reads()
    out = report_loop.run(report, WITH_TABLE, REQUEST, ask=model, clock=_clock())
    assert report.drawn[-1] == ["anneal", "bond_temp", "chuck"]
    assert [label for label, _cells in out["tables"]["yield_by"]["info"]] == ["anneal", "bond_temp", "chuck"]


def test_a_candidate_related_to_nothing_is_to_be_filled_in_the_declarations_word(walks):
    model = Model({"done": {}}, {"seeds": ["void"]}, {"conditions": {"bond_temp": ["bond_temp"]}},
                  {"done": {"summary": "S"}})
    out = report_loop.run(Reads(), dict(WITH_TABLE, labels={"to_fill": "TO MEASURE"}), REQUEST, ask=model, clock=_clock())
    assert out["steps"][5]["read"] == ["wetting: TO MEASURE", "bond_temp -> bond_temp: 350 | 300"]


def test_causes_read_is_handed_to_every_walk_as_it_is(walks):
    """Lead 10-27 B-4: `causes.read` beside `causes.worlds` - the route's own `read`, the report only hands it on."""
    report = Reads({"seed_type": "defect_kind", "worlds": ["ops", "lab"], "read": "first", "follow": ["leads_to"]})
    report.causes(["void"])
    assert [(cell, args.get("world"), args.get("read")) for cell, args in walks] == [
        ("derive.report.causes.seed_type", ["ops", "lab"], "first"), ("derive.report.causes", ["ops", "lab"], "first")]
    walks.clear()
    Reads().causes(["void"])
    assert all("read" not in args for _cell, args in walks), "none said: the route's own"


def test_causes_read_reaches_the_route_and_a_word_not_one_of_its_is_refused_at_save(monkeypatch):
    route, got = trace_router.evidence_subgraph, {}

    @functools.wraps(route)
    def stand_in(**kwargs):
        got.update(kwargs)
        return {"nodes": []}

    monkeypatch.setattr(trace_router, "evidence_subgraph", stand_in)
    report_reads._walk("DB", "derive.report.causes", node_id=VOID, read="first")
    assert got["read"] == "first"
    from chain import report_shape
    said = report_shape._causes_refusal({"seed_type": "defect_kind", "read": "last"})
    assert said and '"read": both | first' in said
    assert report_shape._causes_refusal({"seed_type": "defect_kind", "read": "first"}) is None
