# -*- coding: utf-8 -*-
"""Owner 10-22 ㄱ (lead: «에이전트 문맥» [1]..[7]): one rule runs one report - each step hands the model its context in
that order, reads one JSON object back, and the loop stops at its step cap, its time cap or a context over budget.

  context     [1] instructions (the declaration's role, rules, a read's about - the product's when blank) · [2] the
              prompts · [3] the request · [4] the folded conditions · [5] earlier steps a line each · [6] the last
              result as the read summed it up · [7] the budget line - in that order
  budget      [6]'s rows are cut first, then [4]'s; past both the report stops «context over budget»; the counted
              tokens a gateway says correct the reckoning
  stops       steps · seconds · the model refused - each said in the reason; done ends with the texts
  refused     the same call twice · a read that is not one · an argument it does not take - told back to the model
"""
import pytest

from chain import report_loop, report_reads


class FakeReport:
    """The reads the loop calls - a table whose `context` is three lines and whose whole is a hundred."""

    def __init__(self, condition_lines=3):
        self.overlaps, self.embedded, self.used, self.compared = {}, {}, {}, None
        self._conditions = ["3 wafers in E1"] + ["split: value %d" % n for n in range(condition_lines - 1)]

    def conditions(self, keyword=None):
        return {"context": "\n".join(self._conditions), "html": None}

    def compare(self, sets=None):
        self.compared = sets
        return {"context": "compared", "html": None}

    def yield_by(self, wafers=None, by=None):
        whole = ["row %d | 1.0%% (1/100)" % n for n in range(100)]
        return {"context": "\n".join(["[E1] W1 | W2"] + whole[:3]), "html": {"rows": whole}}

    def pareto(self, wafers=None):
        raise report_reads.ReadRefused("a pareto adds fail chips - derive.report.summary.fail is not declared")


SPEC = {"prompts": {"role": "ROLE-TEXT", "select": "pick split A", "functions": {"trend": {"about": "TREND-ABOUT"}}},
        "layout": [{"kind": "text", "slot": "summary"}, {"kind": "table", "fill": "yield_by"}],
        "loop": {"steps": 4, "seconds": 300, "context_tokens": 16000}}
REQUEST = {"evaluation": "E1", "sets": ["baseline"], "note": "look at particle"}


class Model:
    """Answers in turn; keeps every prompt and says it counted `counted` prompt tokens."""

    def __init__(self, *answers, counted=None):
        self.answers, self.prompts, self.counted = list(answers), [], counted

    def __call__(self, prompt, usage=None):
        self.prompts.append(prompt)
        if self.counted is not None:
            usage["prompt_tokens"] = self.counted
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class Clock:
    def __init__(self, step=1.0):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


def test_each_step_hands_the_context_in_its_order_and_done_ends_it():
    model = Model({"call": "yield_by", "args": {"wafers": "all"}}, {"done": {"summary": "Particle rose."}})
    report = FakeReport()
    out = report_loop.run(report, SPEC, REQUEST, ask=model, clock=Clock())
    assert (out["state"], out["reason"], out["texts"]) == ("done", None, {"summary": "Particle rose."})
    assert report.compared == ["baseline"]
    second = model.prompts[1]
    marks = ["ROLE-TEXT", "TREND-ABOUT", '{"done": {"summary": "<text>"}}', "This is step 2 of 4.",
             "Select: pick split A", "Evaluation: E1", "Note: look at particle", "split: value 1",
             "Last result, step 1: yield_by", "row 2 | 1.0% (1/100)", "used ~"]
    places = [second.index(mark) for mark in marks]
    assert places == sorted(places), list(zip(marks, places))
    assert report_loop.RULES in second and report_loop.ABOUT["yield_by"] in second, "blank cells: the product's text"
    assert "row 50" not in second, "[6] is the read's summary - its whole table goes to the HTML only"
    assert out["tables"]["yield_by"]["rows"][50] == "row 50 | 1.0% (1/100)"
    assert [s["call"] for s in out["steps"]] == ['yield_by({"wafers": "all"})', "done"]


def test_earlier_steps_are_a_line_each():
    model = Model({"call": "yield_by", "args": {}}, {"call": "conditions", "args": {"keyword": "A"}},
                  {"done": {"summary": ""}})
    report_loop.run(FakeReport(), SPEC, REQUEST, ask=model, clock=Clock())
    third = model.prompts[2]
    assert "Earlier steps:\nstep 1: yield_by() -> [E1] W1 | W2\nLast result, step 2: conditions(" in third


def test_the_budget_cuts_the_last_result_then_the_conditions_then_stops():
    tight = dict(SPEC, loop={"steps": 4, "seconds": 300, "context_tokens": 400})
    model = Model({"call": "yield_by", "args": {}}, {"done": {"summary": ""}})
    out = report_loop.run(FakeReport(condition_lines=40), tight, REQUEST, ask=model, clock=Clock())
    first = out["steps"][0]["cut"]
    assert set(first) == {"4"} and 1 <= first["4"] < 40, "the first step has no [6] - [4] is cut"
    assert out["steps"][1]["cut"]["6"] < 4 and out["steps"][1]["cut"]["4"] < 40
    starved = dict(SPEC, loop={"steps": 4, "seconds": 300, "context_tokens": 100})
    out = report_loop.run(FakeReport(), starved, REQUEST, ask=Model(), clock=Clock())
    assert (out["state"], out["reason"], out["steps"]) == ("stopped", "context over budget", [])


def test_what_a_gateway_counted_corrects_the_reckoning():
    model = Model({"call": "yield_by", "args": {}}, {"done": {"summary": ""}}, counted=99999)
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=model, clock=Clock())
    assert out["steps"][0]["tokens"] == 99999
    assert out["reason"] == "context over budget", "counted at many times the reckoning, step 2 cannot fit"


@pytest.mark.parametrize("loop, answers, reason", [
    ({"steps": 2, "seconds": 300}, [{"call": "yield_by", "args": {}}, {"call": "conditions", "args": {}}],
     "step cap 2"),
    ({"steps": 8, "seconds": 3}, [{"call": "yield_by", "args": {}}, {"call": "conditions", "args": {}}],
     "time cap 3 s"),
])
def test_the_step_and_time_caps_stop_it_by_name(loop, answers, reason):
    spec = dict(SPEC, loop=dict(loop, context_tokens=16000))
    out = report_loop.run(FakeReport(), spec, REQUEST, ask=Model(*answers), clock=Clock())
    assert (out["state"], out["reason"]) == ("stopped", reason)


def test_a_refused_model_call_stops_it_with_the_gateways_words():
    from utils import llm

    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=Model(llm.LlmRefused("the gateway refused the key")),
                          clock=Clock())
    assert out["reason"] == "the language model call was refused: the gateway refused the key"


def test_what_cannot_be_called_is_told_back_and_the_loop_goes_on():
    model = Model({"call": "yield_by", "args": {}}, {"call": "yield_by", "args": {}}, {"call": "sql", "args": {}},
                  {"call": "yield_by", "args": {"colour": "red"}})
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=model, clock=Clock())
    refused = [s["refused"] for s in out["steps"]]
    assert refused[1] == "the same call as step 1 - its result is above; call another read or answer done"
    assert refused[2].startswith("'sql' is not a read - one of conditions")
    assert refused[3] == "colour is not an argument of yield_by - one of wafers, by"
    assert "refused: the same call as step 1" in model.prompts[2]
    assert out["reason"] == "step cap 4"


def test_a_reads_refusal_is_the_models_next_context():
    model = Model({"call": "pareto", "args": {}}, {"done": {"summary": ""}})
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=model, clock=Clock())
    assert out["steps"][0]["refused"].startswith("a pareto adds fail chips")
    assert "refused: a pareto adds fail chips" in model.prompts[1]
