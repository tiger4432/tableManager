# -*- coding: utf-8 -*-
"""Owner 10-26 «응답이 json 이 아니어서 멈추는 경우는 어떻게 할지» (안 ㄱ): an answer that is not one JSON object stops no
report.

  read out    text around the JSON (a sentence, two fences, a brace in a string) -> its first whole object (`llm._object`)
  ask again   no object -> asked once more, told what it said; a call that failed is not asked again
  go on       still none while reading -> the reading ends there, what was read is written (as at the step cap)
  write       still none on the write -> stopped, the answer's first 200 characters in the reason
"""
import pytest

from chain import report_loop
from test_a_report_loop_hands_the_model_its_context_and_stops import REQUEST, SPEC, WRITTEN, Clock, FakeReport
from utils import llm


class Gateway:
    """Answers in turn as the gateway would: a text is read by `llm._object`, an exception raised."""

    def __init__(self, *answers):
        self.answers, self.prompts = list(answers), []

    def __call__(self, prompt, usage=None):
        self.prompts.append(prompt)
        answer = self.answers.pop(0) if self.answers else WRITTEN
        if isinstance(answer, Exception):
            raise answer
        return llm._object(answer, "") if isinstance(answer, str) else answer


PROSE = "I could not decide which read to call next."


@pytest.mark.parametrize("content, read", [
    ('Here it is:\n{"call": "yield_by", "args": {}}\nThat should do.', {"call": "yield_by", "args": {}}),
    ('```json\n{"a": 1}\n```\nor\n```json\n{"b": 2}\n```', {"a": 1}),
    ('Sure - {"why": "a } in a string", "call": "pareto"} done', {"why": "a } in a string", "call": "pareto"}),
])
def test_the_object_in_text_around_it_is_read(content, read, caplog):
    assert llm._object(content, "") == read
    assert any("[LLM] answer had text around its JSON - read the object" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("content, said", [(PROSE, "the answer is not JSON: " + PROSE),
                                           ("[1, 2]", "the answer is JSON but not an object: list")])
def test_no_object_is_refused_with_what_it_said(content, said):
    with pytest.raises(llm.LlmNotAnObject) as refused:
        llm._object(content, "")
    assert (str(refused.value), refused.value.answer) == (said, content)


def test_an_answer_with_text_around_its_json_goes_on_as_it_is():
    gateway = Gateway('Reading the table:\n{"call": "yield_by", "args": {}}', {"done": {}})
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=gateway, clock=Clock())
    assert (out["state"], len(gateway.prompts)) == ("done", 3), "two steps and the write - nothing asked again"
    assert out["steps"][0]["call"] == "yield_by()", "the step is the call the text held"


def test_an_answer_with_no_json_is_asked_once_more_told_what_it_said():
    gateway = Gateway(PROSE, {"call": "yield_by", "args": {}}, {"done": {}})
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=gateway, clock=Clock())
    assert (out["state"], len(gateway.prompts)) == ("done", 4), "one call more"
    assert gateway.prompts[1] == gateway.prompts[0] + report_loop.AGAIN_JSON % PROSE
    assert out["steps"][0]["call"] == "yield_by()"


def test_no_json_twice_ends_the_reading_and_what_was_read_is_written():
    gateway = Gateway({"call": "yield_by", "args": {}}, PROSE, PROSE)
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=gateway, clock=Clock())
    assert (out["state"], out["reason"]) == ("stopped", report_loop.STOP_NO_JSON % (2, PROSE))
    assert out["texts"] == {"summary": "WRITTEN"}, "the write call took what was read"
    assert [s["call"] for s in out["steps"]] == ["yield_by()", "answer", "product yield_by()", "write"]
    assert out["steps"][1]["refused"] == out["reason"], "the Evidence says the step"


def test_no_json_twice_on_the_write_stops_with_what_it_said():
    gateway = Gateway({"done": {}}, PROSE, PROSE)
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=gateway, clock=Clock())
    assert (out["state"], out["reason"]) == ("stopped", report_loop.STOP_MODEL % ("the answer is not JSON: " + PROSE))
    assert out["texts"] == {}


def test_a_call_that_failed_is_not_asked_again():
    gateway = Gateway(llm.LlmCallFailed("the gateway did not answer"))
    out = report_loop.run(FakeReport(), SPEC, REQUEST, ask=gateway, clock=Clock())
    assert (out["state"], out["reason"], len(gateway.prompts)) == (
        "stopped", report_loop.STOP_MODEL % "the gateway did not answer", 1)
    assert out["texts"] == {}, "a gateway that is not answering writes nothing - as before"
