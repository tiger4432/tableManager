# -*- coding: utf-8 -*-
"""총괄 b5b335f2e ① ② — one seat asks a language model (`mapper_sdk.ask_json`), and
`ask_links` reads a text into `find_links`' rows through it. A fake client: no network, no
`openai` package (this box has none).

  answer names a dictionary phrase     key from the dictionary
  answer names other words             type and key empty, *_phrase kept
  evidence the text does not hold      refused by name
  answer not JSON / no links list      refused by name
  certainty said / unsaid              confirmed · suspected / suspected
  the key                              in no refusal and no log line
"""
import logging
import os
import sys
from types import SimpleNamespace

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                     # noqa: E402
from utils import llm, text_links                                     # noqa: E402

KEY = "sk-test-0123456789"
NAMES = [{"node_type": "quantity", "node_key": "q-temp", "phrase": "bond temperature"},
         {"node_type": "defect_kind", "node_key": "d-void", "phrase": "void"}]
TEXT = "The bond temperature was high. It caused a void, we suspect.\nNothing else."


@pytest.fixture(name="answer")
def fixture_answer(monkeypatch):
    """`answer(content)` makes the next calls return `content`; the prompts asked are kept."""
    for name, value in ((llm.BASE_URL_ENV, "http://llm.test/v1"), (llm.MODEL_ENV, "m-1"),
                        (llm.KEY_ENV, KEY), (llm.TIMEOUT_ENV, "")):
        monkeypatch.setenv(name, value)
    asked, said = [], {}

    def create(model, messages):
        asked.append((model, messages))
        if isinstance(said["content"], Exception):
            raise said["content"]
        return SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=said["content"]))])

    monkeypatch.setattr(llm, "_client", lambda base_url, key, timeout: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))

    def answer(content):
        said["content"] = content
        return asked
    return answer


def _links(*items):
    import json
    return json.dumps({"links": list(items)})


def test_a_dictionary_phrase_gets_its_key_and_other_words_keep_their_phrase(answer):
    answer(_links({"cause": "Bond Temperature", "effect": "void", "link": "caused",
                   "evidence": "It caused a void, we suspect.", "certainty": "suspected"},
                  {"cause": "humidity", "effect": "void",
                   "evidence": "The bond temperature was high.", "negated": True,
                   "certainty": "confirmed"}))
    first, second = text_links.ask_links(TEXT, NAMES)
    assert (first["cause_type"], first["cause_key"], first["phenomenon_key"]) == (
        "quantity", "q-temp", "d-void")
    assert (second["cause_type"], second["cause_key"], second["cause_phrase"]) == (
        None, None, "humidity")
    assert (first["sentence_no"], second["sentence_no"]) == (2, 1)
    assert (second["polarity"], second["certainty"]) == ("negated", "confirmed")
    assert {row["extractor"] for row in (first, second)} == {"llm:m-1"}
    (by_rules,) = text_links.find_links("The bond temperature caused a void.", NAMES, [
        {"phrase": "caused", "meaning": "cause", "side": "before"}])
    assert set(first) == set(by_rules), "one row shape"


@pytest.mark.parametrize("certainty,expected", [
    ("confirmed", "confirmed"), ("suspected", "suspected"), (None, "suspected"),
    ("certain", "suspected")])
def test_unsaid_certainty_is_suspected(answer, certainty, expected):
    answer(_links({"cause": "void", "effect": "void", "evidence": "Nothing else.",
                   "certainty": certainty}))
    assert text_links.ask_links(TEXT, NAMES)[0]["certainty"] == expected


@pytest.mark.parametrize("content,said", [
    ("not json at all", "not JSON"),
    ("[1, 2]", "not an object"),
    ('{"rows": []}', "no 'links' list"),
    (_links({"cause": "void", "evidence": "Nothing else."}), "no effect"),
    (_links({"cause": "void", "effect": "void", "evidence": "A sentence nobody wrote."}),
     "evidence the text does not hold"),
])
def test_a_malformed_answer_is_refused_by_name(answer, content, said):
    answer(content)
    with pytest.raises(llm.LlmRefused) as refused:
        text_links.ask_links(TEXT, NAMES)
    assert said in str(refused.value)


def test_a_fenced_answer_is_read(answer):
    answer("```json\n" + _links({"cause": "void", "effect": "void",
                                  "evidence": "Nothing else."}) + "\n```")
    assert len(text_links.ask_links(TEXT, NAMES)) == 1


def test_the_prompt_holds_no_domain_word(answer):
    """Every word past the template is a dictionary row's or the operator's."""
    asked = answer(_links())
    text_links.ask_links("", [], instruction=None)
    (_model, messages), = asked
    prompt = messages[-1]["content"]
    assert prompt.strip() == text_links.ASK_LINKS_PROMPT.replace("<<dictionary>>", "").replace(
        "<<instruction>>", "").replace("<<text>>", "").strip()
    assert not any("가" <= ch <= "힣" for ch in text_links.ASK_LINKS_PROMPT)
    asked.clear()
    text_links.ask_links(TEXT, NAMES, instruction="only the cause of voids")
    prompt = asked[0][1][-1]["content"]
    assert "bond temperature" in prompt and "only the cause of voids" in prompt and TEXT in prompt


def test_the_key_reaches_no_refusal_and_no_log(answer, caplog):
    answer(RuntimeError("401 for key %s at http://llm.test/v1" % KEY))
    caplog.set_level(logging.DEBUG)
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert KEY not in str(refused.value) and "***" in str(refused.value)
    assert refused.value.__suppress_context__, "the client's own exception is not chained"
    assert KEY not in caplog.text


def test_nothing_configured_names_what_to_set(monkeypatch):
    for name in (llm.BASE_URL_ENV, llm.MODEL_ENV, llm.KEY_ENV):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert all(name in str(refused.value) for name in (llm.BASE_URL_ENV, llm.MODEL_ENV, llm.KEY_ENV))


def test_without_the_package_the_refusal_says_how_to_install(monkeypatch):
    monkeypatch.setenv(llm.BASE_URL_ENV, "http://llm.test/v1")
    monkeypatch.setenv(llm.MODEL_ENV, "m-1")
    monkeypatch.setenv(llm.KEY_ENV, KEY)
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert "pip install openai" in str(refused.value)


def test_find_links_rows_say_rules_and_their_sentence():
    (row,) = text_links.find_links("The bond temperature caused a void.", NAMES, [
        {"phrase": "caused", "meaning": "cause", "side": "before"}])
    assert (row["extractor"], row["evidence"]) == ("rules", row["sentence"])


def test_the_mapper_door_reaches_the_same_functions():
    assert mapper_sdk.ask_json is llm.ask_json
    assert mapper_sdk.ask_links is text_links.ask_links
    assert mapper_sdk.LlmRefused is llm.LlmRefused
