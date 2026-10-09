# -*- coding: utf-8 -*-
"""총괄 b5b335f2e ① ② — one seat asks a language model (`mapper_sdk.ask_json`), and
`ask_links` reads a text into `find_links`' rows through it. 총괄 043915ab0 ① — the seat reads
config/llm_config.json on every call and writes two lines a call to llm_requests.log.
A fake `openai` module: no network, no package (this box has none) - what is measured is that the
file's cells reach the client, not what the real client sends.

  answer names a dictionary phrase     key from the dictionary
  answer names other words             type and key empty, *_phrase kept
  evidence the text does not hold      refused by name
  answer not JSON / no links list      refused by name
  certainty said / unsaid              confirmed · suspected / suspected
  the file's cells                     reach the client · its httpx reads no system proxy
  no file / retired env / bad cell     refused by name
  a changed file                       reaches the next call
  the log                              two lines a call, the key in no line
"""
import json
import logging
import os
import sys
import types
from types import SimpleNamespace

import httpx
import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                     # noqa: E402
import paths                                                          # noqa: E402
from utils import llm, text_links                                     # noqa: E402

KEY = "sk-test-0123456789"
CELLS = {"base_url": "http://llm.test/v1", "model": "m-1", "api_key": KEY}
NAMES = [{"node_type": "quantity", "node_key": "q-temp", "phrase": "bond temperature"},
         {"node_type": "defect_kind", "node_key": "d-void", "phrase": "void"}]
TEXT = "The bond temperature was high. It caused a void, we suspect.\nNothing else."


@pytest.fixture(name="root")
def fixture_root(tmp_path, monkeypatch):
    """config/ and the request log under tmp_path; no retired environment value set."""
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    for name in llm.RETIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "config").mkdir()
    return tmp_path


def _declare(root, **cells):
    (root / "config" / llm.CONFIG_FILE).write_text(json.dumps(cells), encoding="utf-8")


def _log_lines(root):
    path = root / llm.REQUEST_LOG
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


@pytest.fixture(name="answer")
def fixture_answer(root, monkeypatch):
    """`answer(content)` makes the next calls return `content`; the prompts asked are kept.
    `answer.made` holds what each client was built with."""
    _declare(root, **CELLS)
    asked, said, made = [], {}, []

    def create(model, messages):
        asked.append((model, messages))
        if isinstance(said["content"], Exception):
            raise said["content"]
        content = said["content"]
        return SimpleNamespace(status_code=200, text=json.dumps({"choices": [{"message": {"content": content}}]}),
                               parse=lambda: SimpleNamespace(choices=[SimpleNamespace(
                                   message=SimpleNamespace(content=content))]))

    class OpenAI:
        """What the SDK exposes that the seat reads: base_url ends in "/" and default_headers
        carries the key as Authorization."""
        def __init__(self, **kwargs):
            made.append(kwargs)
            self.base_url = kwargs["base_url"].rstrip("/") + "/"
            self.default_headers = {"Authorization": "Bearer " + kwargs["api_key"],
                                    **(kwargs.get("default_headers") or {})}
            self.chat = SimpleNamespace(completions=SimpleNamespace(
                with_raw_response=SimpleNamespace(create=create)))

    module = types.ModuleType("openai")
    module.OpenAI = OpenAI
    monkeypatch.setitem(sys.modules, "openai", module)

    def answer(content):
        said["content"] = content
        return asked
    answer.made = made
    return answer


def _links(*items):
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


@pytest.mark.parametrize("proxy", [None, "http://user:pw@proxy.test:8080"])
def test_the_files_cells_reach_the_client_and_its_httpx_reads_no_system_proxy(answer, root, monkeypatch, proxy):
    seen = []

    class Recorded(httpx.Client):
        def __init__(self, **kwargs):
            seen.append(kwargs)
            super().__init__(**kwargs)
    monkeypatch.setattr(httpx, "Client", Recorded)
    _declare(root, **CELLS, timeout_s=7, headers={"X-Team": "assy"}, proxy=proxy)
    answer('{"ok": 1}')
    assert llm.ask_json("anything") == {"ok": 1}
    (made,) = answer.made
    assert (made["base_url"], made["api_key"], made["timeout"], made["default_headers"]) == (
        "http://llm.test/v1", KEY, 7.0, {"X-Team": "assy"})
    assert seen == [{"proxy": proxy, "trust_env": False}] and made["http_client"].trust_env is False
    sent = _log_lines(root)[0]
    assert sent["proxy"] == (None if proxy is None else "http://<redacted>@proxy.test:8080")
    assert sent["headers"]["X-Team"] == "assy"


@pytest.mark.parametrize("cells,env,said", [
    (None, {}, "no language model is configured - write server/config/llm_config.json (sample: "
               "config/sample/llm_config.json.sample)"),
    (None, {"ASSY_LLM_MODEL": "m-1"}, "ASSY_LLM_* environment variables are not read any more - write "
                                      "server/config/llm_config.json (sample: config/sample/llm_config.json.sample)"),
    ({"base_url": "http://llm.test/v1", "model": "m-1"}, {}, "does not set api_key"),
    ({**CELLS, "timeout_s": "7"}, {}, "timeout_s in config/llm_config.json is not a number"),
    ({**CELLS, "headers": ["X-Team"]}, {}, "headers in config/llm_config.json is not an object"),
    ({**CELLS, "proxy": 8080}, {}, "proxy in config/llm_config.json is not a URL or null"),
])
def test_no_file_a_retired_environment_value_or_a_bad_cell_is_refused_by_name(root, monkeypatch, cells, env, said):
    if cells is not None:
        _declare(root, **cells)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert said in str(refused.value)
    assert _log_lines(root) == [], "nothing was sent"


def test_a_changed_file_reaches_the_next_call(answer, root):
    asked = answer('{"ok": 1}')
    llm.ask_json("one")
    _declare(root, **{**CELLS, "model": "m-2"})
    llm.ask_json("two")
    assert [model for model, _messages in asked] == ["m-1", "m-2"]
    assert llm.model() == "m-2"


def test_a_call_writes_what_it_sent_and_what_came_back(answer, root):
    asked = answer('{"ok": 1}')
    llm.ask_json("anything", system="be brief")
    ((model, messages),) = asked
    failure = RuntimeError("upstream said no")
    failure.status_code = 503
    answer(failure)
    with pytest.raises(llm.LlmRefused):
        llm.ask_json("again")
    sent, back, sent_again, failed = _log_lines(root)
    assert set(sent) == {"sent", "id", "url", "model", "headers", "payload", "proxy"}
    assert (sent["url"], sent["model"], sent["proxy"]) == ("http://llm.test/v1/chat/completions", "m-1", None)
    assert sent["payload"] == {"model": model, "messages": messages}, "the line is what the client was handed"
    assert messages == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "anything"}]
    assert (back["id"], back["status"], back["answer"]) == (
        sent["id"], 200, {"choices": [{"message": {"content": '{"ok": 1}'}}]})
    assert set(back) == {"received", "id", "status", "answer", "ms"}
    assert (failed["id"], failed["status"], failed["error"]) == (
        sent_again["id"], 503, "RuntimeError: upstream said no")
    assert sent_again["id"] != sent["id"]


def test_a_log_that_cannot_be_written_does_not_stop_the_call(answer, root, caplog):
    (root / llm.REQUEST_LOG).mkdir()                       # a folder where the file goes
    answer('{"ok": 1}')
    caplog.set_level(logging.WARNING)
    assert llm.ask_json("anything") == {"ok": 1}
    assert "llm_requests.log not written" in caplog.text


def test_the_key_reaches_no_refusal_and_no_log(answer, root, caplog):
    answer(RuntimeError("401 for key %s at http://llm.test/v1" % KEY))
    caplog.set_level(logging.DEBUG)
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert KEY not in str(refused.value) and "***" in str(refused.value)
    assert refused.value.__suppress_context__, "the client's own exception is not chained"
    assert KEY not in caplog.text
    written = (root / llm.REQUEST_LOG).read_text(encoding="utf-8")
    assert KEY not in written and "Bearer ***" in written


def test_without_the_package_the_refusal_says_how_to_install(root, monkeypatch):
    _declare(root, **CELLS)
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert "pip install openai" in str(refused.value)


def test_an_httpx_without_proxy_is_refused_with_both_versions(answer, monkeypatch):
    monkeypatch.setattr(httpx, "__version__", "0.25.2")
    answer('{"ok": 1}')
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert "httpx 0.25.2 cannot take a proxy - 0.26 or later is needed" in str(refused.value)


def test_find_links_rows_say_rules_and_their_sentence():
    (row,) = text_links.find_links("The bond temperature caused a void.", NAMES, [
        {"phrase": "caused", "meaning": "cause", "side": "before"}])
    assert (row["extractor"], row["evidence"]) == ("rules", row["sentence"])


def test_the_mapper_door_reaches_the_same_functions():
    assert mapper_sdk.ask_json is llm.ask_json
    assert mapper_sdk.ask_links is text_links.ask_links
    assert mapper_sdk.LlmRefused is llm.LlmRefused
