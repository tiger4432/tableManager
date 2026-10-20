# -*- coding: utf-8 -*-
"""총괄 b5b335f2e ① ② — one seat asks a language model (`mapper_sdk.ask_json`), and
`ask_links` reads a text into `find_links`' rows through it. 총괄 043915ab0 ① — the seat reads
config/llm_config.json on every call and writes two lines a call to llm_requests.log.
A fake `openai` module: no network, no package (this box has none) - what is measured is that the
file's cells reach the client, not what the real client sends.

  the prompt                           every node once: identifier (type): all its phrases ·
                                       shortest noun phrase · one link per cause x effect pair
  two links quoting one sentence       two rows, the same sentence_no
  answer names a listed identifier     type and key of that node, whatever its words
  answer names an unlisted identifier  type and key empty, *_phrase kept, one warning line
  one key under two types              <type>:<key> in the list; the bare key is unlisted
  identifier null, words a phrase      key from the dictionary (`phrase_bag`)
  identifier null, other words         type and key empty, *_phrase kept
  identifier in another case           unlisted - compared as written (총괄 6e251ed32)
  direction up / down / null           kept as written, spaces trimmed · a blank is null
  direction anything else              None, one warning line · find_links rows: None
  dir                                  both said: same "+" · different "-" · a side None: None
  evidence the text does not hold      that link dropped, one warning line · every link: refused by name
  evidence over two sentences          found; sentence = both, sentence_no = the first (소유자 10-11 ㄴ)
  a sentence's end                     . ! ? 。 + whitespace · a blank line - not one line break, not 1.5;
                                       find_links and ask_links say the same
  quote marks · ellipsis               ignored on both sides; a changed word or only marks is dropped
  answer not JSON / no texts list      refused by name
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
KO_TEXT = "본딩 온도가 높았다. 그래서 보이드가 생긴 것으로 보인다.\n작업자는 \"온도가 원인\"이라고 했다."


@pytest.fixture(name="root")
def fixture_root(tmp_path, monkeypatch):
    """config/ and the request log under tmp_path; no retired environment value set."""
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setattr(paths, "DATA_ROOT", str(tmp_path))
    for name in llm.RETIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    # one try per call here - the retries are measured on a stopped clock in
    # test_many_texts_are_asked_in_one_request_and_asked_again_within_a_minute.py (`retrying`)
    monkeypatch.setattr(llm, "CALL_RETRY_WAITS", ())
    (tmp_path / "config").mkdir()
    return tmp_path


def _declare(root, **cells):
    from database import config_watcher

    path = root / "config" / llm.CONFIG_FILE
    path.write_text(json.dumps(cells), encoding="utf-8")
    config_watcher.changed(str(path))           # as the watcher says it (e6a0bdbbd)


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
    """The answer to one text (a str) - its links under its id."""
    return json.dumps({"texts": [{"id": text_links.ONE_TEXT_ID, "links": list(items)}]})


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
    ('{"rows": []}', "no 'texts' list"),
    (_links({"cause": "void", "evidence": "Nothing else."}), "no effect"),
    (_links({"cause": "void", "effect": "void", "evidence": "A sentence nobody wrote."}),
     "evidence the text does not hold"),
])
def test_a_malformed_answer_is_refused_by_name(answer, content, said):
    answer(content)
    with pytest.raises(llm.LlmRefused) as refused:
        text_links.ask_links(TEXT, NAMES)
    assert said in str(refused.value)


def _dropped_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "utils.text_links"]


def test_a_link_whose_evidence_the_text_does_not_hold_is_dropped_and_said(answer, caplog):
    answer(_links({"cause": "본딩 온도", "effect": "보이드", "evidence": "그래서 보이드가 생긴 것으로 보인다."},
                  {"cause": "습도", "effect": "보이드", "evidence": "습도가 높아서 보이드가 생겼다."},
                  {"cause": "온도", "effect": "보이드", "evidence": "본딩 온도가 높았다."}))
    caplog.set_level(logging.WARNING)
    rows = text_links.ask_links(KO_TEXT, NAMES)
    assert [(row["cause_phrase"], row["sentence_no"]) for row in rows] == [("본딩 온도", 2), ("온도", 1)]
    (line,) = _dropped_lines(caplog)
    assert line == ("[LLM] link 2 of 3 quotes evidence the text does not hold - dropped (llm:m-1): "
                    "'습도가 높아서 보이드가 생겼다.'")


def test_every_link_dropped_is_refused_with_the_count(answer, caplog):
    answer(_links({"cause": "습도", "effect": "보이드", "evidence": "습도가 높아서 보이드가 생겼다."},
                  {"cause": "압력", "effect": "보이드", "evidence": "압력이 낮았다."}))
    caplog.set_level(logging.WARNING)
    with pytest.raises(llm.LlmRefused) as refused:
        text_links.ask_links(KO_TEXT, NAMES)
    assert str(refused.value) == ("every link of the answer (2) quotes evidence the text does not hold"
                                  " - link 1: '습도가 높아서 보이드가 생겼다.'")
    assert [line.split(" quotes ")[0] for line in _dropped_lines(caplog)] == [
        "[LLM] link 1 of 2", "[LLM] link 2 of 2"]


@pytest.mark.parametrize("text,evidence,sentence_no,sentence", [
    (KO_TEXT, "본딩 온도가 높았다. 그래서 보이드가", 1, "본딩 온도가 높았다. 그래서 보이드가 생긴 것으로 보인다."),
    (KO_TEXT, "생긴 것으로 보인다.\n작업자는", 2,
     "그래서 보이드가 생긴 것으로 보인다.\n작업자는 \"온도가 원인\"이라고 했다."),
    (TEXT, "we suspect. Nothing else.", 2, "It caused a void, we suspect.\nNothing else."),
], ids=["ko-1-2", "ko-2-3-over-a-line-break", "en-2-3"])
def test_evidence_over_two_sentences_gives_both_sentences_and_the_first_number(
        answer, text, evidence, sentence_no, sentence):
    """소유자 10-11 「LLM 문장 왜 잘라서 읽어?」 ㄴ: the sentence cell is not cut at the quote's first sentence."""
    answer(_links({"cause": "a", "effect": "b", "evidence": evidence}))
    (row,) = text_links.ask_links(text, NAMES)
    assert (row["sentence_no"], row["sentence"], row["evidence"]) == (sentence_no, sentence, evidence)


CAUSED = [{"phrase": "caused", "meaning": "cause", "side": "before"}]
LINKED = "The bond temperature caused a void."


@pytest.mark.parametrize("text,sentence", [
    ("The line was\nslow. The bond temperature\ncaused a void.", "The bond temperature\ncaused a void."),
    ("The line was\r\nslow. The bond temperature\r\ncaused a void.", "The bond temperature\r\ncaused a void."),
    ("The line was slow.\n" + LINKED, LINKED),
    ("The line was slow\n\n" + LINKED, LINKED),
    ("The line was slow\n \t\n" + LINKED, LINKED),
    ("The line was slow\r\n\r\n" + LINKED, LINKED),
    ("The line was 1.5 h slow. " + LINKED, LINKED),
], ids=["one-line-break", "one-crlf", "a-mark-then-a-line-break", "a-blank-line", "a-blank-line-holding-spaces",
        "a-blank-crlf-line", "1.5-stays-whole"])
def test_a_sentence_ends_at_a_mark_or_a_blank_line_and_both_readers_say_so(answer, text, sentence):
    """소유자 10-11 ㄴ: one line break inside a sentence does not end it; `find_links` and `ask_links` number
    and cut it the same way. Every text holds the linking sentence second - a wrapped first sentence
    cut at its line break would make it third."""
    by_rules = text_links.find_links(text, NAMES, CAUSED)
    answer(_links({"cause": "bond temperature", "effect": "void", "evidence": " ".join(sentence.split())}))
    by_model = text_links.ask_links(text, NAMES)
    assert [(row["sentence_no"], row["sentence"]) for row in by_rules + by_model] == [(2, sentence)] * 2


@pytest.mark.parametrize("text,evidence,sentence_no", [
    (KO_TEXT, "“그래서 보이드가 생긴 것으로 보인다.”", 2),
    (KO_TEXT, "«그래서 보이드가 생긴 것으로 보인다»", 2),
    (KO_TEXT, "「본딩 온도가 높았다」", 1),
    (KO_TEXT, "『본딩 온도가 높았다』", 1),
    (KO_TEXT, "‘그래서 보이드가 생긴 것으로…’", 2),
    (KO_TEXT, "그래서 보이드가 생긴 것으로 보인다...", 2),
    (KO_TEXT, "작업자는 온도가 원인이라고 했다.", 3),
    (KO_TEXT, "작업자는 '온도가 원인'이라고 했다.", 3),
    (TEXT, "It caused a void, we suspect…", 2),
], ids=["curly-double", "guillemets", "corner", "white-corner", "curly-single-and-…",
        "trailing-...", "marks-only-in-the-text", "other-marks-than-the-text", "en-…"])
def test_quote_marks_and_ellipsis_are_ignored_on_both_sides(answer, text, evidence, sentence_no):
    answer(_links({"cause": "a", "effect": "b", "evidence": evidence}))
    (row,) = text_links.ask_links(text, NAMES)
    assert row["sentence_no"] == sentence_no


@pytest.mark.parametrize("evidence", [
    "그래서 보이드가 생긴 것으로 보임.", "본딩 온도가 낮았다.", "“…”", "...",
], ids=["ko-ending-changed", "ko-word-changed", "only-marks", "only-ellipsis"])
def test_a_changed_word_or_only_marks_is_still_dropped(answer, caplog, evidence):
    answer(_links({"cause": "a", "effect": "b", "evidence": evidence},
                  {"cause": "c", "effect": "d", "evidence": "본딩 온도가 높았다."}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(KO_TEXT, NAMES)
    assert row["cause_phrase"] == "c"
    (line,) = _dropped_lines(caplog)
    assert line.startswith("[LLM] link 1 of 2 quotes evidence the text does not hold - dropped")


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
        "<<instruction>>", "").replace("<<texts>>", "[1]\n").strip()
    assert not any("가" <= ch <= "힣" for ch in text_links.ASK_LINKS_PROMPT)
    asked.clear()
    text_links.ask_links(TEXT, NAMES, instruction="only the cause of voids")
    prompt = asked[0][1][-1]["content"]
    assert "bond temperature" in prompt and "only the cause of voids" in prompt and TEXT in prompt


KO_NAMES = [{"node_type": "quantity", "node_key": "Q123", "phrase": "계면 미충진"},
            {"node_type": "factor", "node_key": "F1", "phrase": "본딩 온도"},
            {"node_type": "quantity", "node_key": "Q123", "phrase": "underfill void"},
            {"node_type": "defect_kind", "node_key": "D7", "phrase": "보이드"},
            {"node_type": "factor", "node_key": "F2", "phrase": None},
            {"node_type": "quantity", "node_key": "Q123", "phrase": "UF void"}]
KO_EVIDENCE = "그래서 보이드가 생긴 것으로 보인다."


def _prompt(asked):
    return asked[-1][1][-1]["content"]


def test_the_prompt_lists_every_node_once_with_all_its_phrases(answer):
    asked = answer(_links())
    text_links.ask_links(KO_TEXT, KO_NAMES)
    block = ("Q123 (quantity): 계면 미충진 / underfill void / UF void\n"
             "F1 (factor): 본딩 온도\n"
             "D7 (defect_kind): 보이드")
    assert _prompt(asked) == text_links.ASK_LINKS_PROMPT.replace("<<dictionary>>", block).replace(
        "<<instruction>>", "").replace("<<texts>>", "[1]\n" + KO_TEXT)


def test_the_prompt_asks_for_the_shortest_noun_phrase_not_a_sentence(answer):
    """소유자 10-11 「사전에 없는 프레이즈는 너무 주저리 문장으로 뽑네」."""
    asked = answer(_links())
    text_links.ask_links(KO_TEXT, KO_NAMES)
    assert ("- cause, effect: the shortest noun phrase of the text that names the thing, copied from the text"
            " - a few words, never a clause or a whole sentence (the whole sentence goes in evidence)"
            ) in _prompt(asked).splitlines()


def test_one_sentence_with_several_causes_or_effects_gives_one_row_per_pair(answer):
    """소유자 10-11: one link per cause x effect pair, the same evidence allowed."""
    text = "첫 문장이다. 본딩 온도가 높아 보이드와 계면 미충진이 생겼다."
    said = "본딩 온도가 높아 보이드와 계면 미충진이 생겼다."
    asked = answer(_links(
        {"cause": "본딩 온도", "cause_key": "F1", "effect": "보이드", "effect_key": "D7", "evidence": said},
        {"cause": "본딩 온도", "cause_key": "F1", "effect": "계면 미충진", "effect_key": "Q123", "evidence": said}))
    rows = text_links.ask_links(text, KO_NAMES)
    assert [(r["sentence_no"], r["cause_key"], r["phenomenon_key"], r["phenomenon_phrase"]) for r in rows] == [
        (2, "F1", "D7", "보이드"), (2, "F1", "Q123", "계면 미충진")]
    assert ("When one sentence names several causes or effects, list one link for each cause and effect pair"
            " - separate items, which may quote the same evidence.") in _prompt(asked).splitlines()


def test_a_listed_identifier_gives_its_node_whatever_the_words(answer, caplog):
    answer(_links({"cause": "온도", "cause_key": "F1", "effect": "생긴 보이드", "effect_key": "Q123",
                   "evidence": KO_EVIDENCE}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(KO_TEXT, KO_NAMES)
    assert (row["cause_type"], row["cause_key"], row["cause_phrase"]) == ("factor", "F1", "온도")
    assert (row["phenomenon_type"], row["phenomenon_key"], row["phenomenon_phrase"]) == (
        "quantity", "Q123", "생긴 보이드")
    assert _dropped_lines(caplog) == []


@pytest.mark.parametrize("words", ["습도", "본딩 온도"], ids=["other-words", "words-are-a-phrase"])
def test_an_unlisted_identifier_gives_no_node_and_is_said(answer, caplog, words):
    """Not listed is not used - not even when the words are a phrase (총괄 10-11 ③)."""
    answer(_links({"cause": words, "cause_key": "Q999", "effect": "보이드", "effect_key": "D7",
                   "evidence": KO_EVIDENCE}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(KO_TEXT, KO_NAMES)
    assert (row["cause_type"], row["cause_key"], row["cause_phrase"]) == (None, None, words)
    assert (row["phenomenon_type"], row["phenomenon_key"]) == ("defect_kind", "D7")
    assert _dropped_lines(caplog) == [
        "[LLM] link 1 of 1 answers cause_key 'Q999', which the dictionary does not list"
        " - kept with its words only (llm:m-1): %r" % words]


@pytest.mark.parametrize("null", [{}, {"cause_key": None}, {"cause_key": ""}, {"cause_key": "  "}],
                         ids=["missing", "null", "empty", "spaces"])
def test_a_null_identifier_gives_the_node_of_the_phrase_its_words_are(answer, caplog, null):
    answer(_links({"cause": "본딩온도", **null, "effect": "보이드", "effect_key": None,
                   "evidence": KO_EVIDENCE}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(KO_TEXT, KO_NAMES)
    assert (row["cause_type"], row["cause_key"], row["cause_phrase"]) == ("factor", "F1", "본딩온도")
    assert (row["phenomenon_type"], row["phenomenon_key"]) == ("defect_kind", "D7")
    assert _dropped_lines(caplog) == []


def test_an_identifier_is_compared_as_written(answer, caplog):
    """«q123» is not «Q123» - left open at 6e251ed32. Not even when the words are a phrase."""
    answer(_links({"cause": "본딩 온도", "cause_key": "f1", "effect": "계면 미충진", "effect_key": "q123",
                   "evidence": KO_EVIDENCE}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(KO_TEXT, KO_NAMES)
    assert (row["cause_type"], row["cause_key"], row["phenomenon_type"], row["phenomenon_key"]) == (
        None, None, None, None)
    assert [line.split(", which")[0] for line in _dropped_lines(caplog)] == [
        "[LLM] link 1 of 1 answers cause_key 'f1'", "[LLM] link 1 of 1 answers effect_key 'q123'"]


DIRECTION_TEXT = ("본딩 온도가 올라가서 보이드가 늘었다. 본딩 압력이 낮아져 보이드가 늘었다. 습도 때문에 보이드가 생겼다."
                  " 본딩 압력이 낮아져 보이드가 줄었다. 본딩 온도가 올라가서 보이드가 줄었다. 습도 때문에 보이드가 늘었다.")


@pytest.mark.parametrize("said,evidence,expected", [
    ({"cause_direction": "up", "effect_direction": "up"}, "본딩 온도가 올라가서 보이드가 늘었다.", ("up", "up", "+")),
    ({"cause_direction": "down", "effect_direction": "down"}, "본딩 압력이 낮아져 보이드가 줄었다.", ("down", "down", "+")),
    ({"cause_direction": "up", "effect_direction": "down"}, "본딩 온도가 올라가서 보이드가 줄었다.", ("up", "down", "-")),
    ({"cause_direction": "down", "effect_direction": "up"}, "본딩 압력이 낮아져 보이드가 늘었다.", ("down", "up", "-")),
    ({"cause_direction": None, "effect_direction": "up"}, "습도 때문에 보이드가 늘었다.", (None, "up", None)),
    ({"cause_direction": None, "effect_direction": None}, "습도 때문에 보이드가 생겼다.", (None, None, None)),
    ({}, "습도 때문에 보이드가 생겼다.", (None, None, None)),
    ({"cause_direction": " down ", "effect_direction": "  "}, "본딩 압력이 낮아져 보이드가 늘었다.", ("down", None, None)),
], ids=["ko-up-up", "ko-down-down", "ko-up-down", "ko-down-up", "ko-null-up", "ko-null-null", "missing",
        "trimmed-and-blank"])
def test_a_link_carries_the_direction_each_side_moves(answer, caplog, said, evidence, expected):
    """소유자 10-11 「여기 모델링에 증감 방향은 없네」 · dir «같이 움직이나 / 반대로»."""
    answer(_links({"cause": "본딩 온도", "effect": "보이드", "evidence": evidence, **said}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(DIRECTION_TEXT, KO_NAMES)
    assert (row["cause_direction"], row["phenomenon_direction"], row["dir"]) == expected
    assert _dropped_lines(caplog) == []


@pytest.mark.parametrize("side,value", [
    ("cause", "Up"), ("cause", "상승"), ("cause", 1), ("effect", "decreases"), ("effect", True),
], ids=["case", "ko-word", "number", "other-word", "bool"])
def test_a_direction_not_up_or_down_is_none_and_said(answer, caplog, side, value):
    answer(_links({"cause": "본딩 온도", "cause_direction": "down", "effect": "보이드",
                   "effect_direction": "up", side + "_direction": value,
                   "evidence": "본딩 압력이 낮아져 보이드가 늘었다."}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(DIRECTION_TEXT, KO_NAMES)
    assert (row["cause_direction"], row["phenomenon_direction"], row["dir"]) == (
        (None, "up", None) if side == "cause" else ("down", None, None))
    assert _dropped_lines(caplog) == [
        "[LLM] link 1 of 1 answers %s_direction %r, which is not up or down - kept without it"
        " (llm:m-1): %r" % (side, value, "본딩 온도" if side == "cause" else "보이드")]


def test_the_prompt_asks_each_side_for_its_direction(answer):
    asked = answer(_links())
    text_links.ask_links(KO_TEXT, KO_NAMES)
    lines = _prompt(asked).splitlines()
    shape = json.loads(next(line for line in lines if line.startswith('{"texts"')))
    assert {"cause_direction", "effect_direction"} <= set(shape["texts"][0]["links"][0])
    assert ('- cause_direction, effect_direction: "up" when the text says that thing increases, rises or'
            ' grows, "down" when it says it decreases, falls or shrinks, null when it says neither') in lines


def test_a_key_two_types_share_is_listed_and_answered_with_its_type(answer, caplog):
    names = [{"node_type": "quantity", "node_key": "K1", "phrase": "본딩 온도"},
             {"node_type": "defect_kind", "node_key": "K1", "phrase": "보이드"},
             {"node_type": "factor", "node_key": "K2", "phrase": "압력"}]
    asked = answer(_links(
        {"cause": "온도", "cause_key": "quantity:K1", "effect": "생긴 보이드",
         "effect_key": "defect_kind:K1", "evidence": KO_EVIDENCE},
        {"cause": "온도", "cause_key": "K1", "effect": "생긴 보이드", "effect_key": "K2",
         "evidence": KO_EVIDENCE}))
    caplog.set_level(logging.WARNING)
    first, second = text_links.ask_links(KO_TEXT, names)
    assert {"quantity:K1 (quantity): 본딩 온도", "defect_kind:K1 (defect_kind): 보이드",
            "K2 (factor): 압력"} <= set(_prompt(asked).splitlines())
    assert (first["cause_type"], first["cause_key"], first["phenomenon_type"], first["phenomenon_key"]) == (
        "quantity", "K1", "defect_kind", "K1")
    assert (second["cause_type"], second["cause_key"], second["phenomenon_type"], second["phenomenon_key"]) == (
        None, None, "factor", "K2")
    assert [line.split(", which ")[0] for line in _dropped_lines(caplog)] == [
        "[LLM] link 2 of 2 answers cause_key 'K1'"]


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
        sent_again["id"], 503, "RuntimeError: upstream said no · proxy: none (direct)")
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


class APIConnectionError(Exception):
    """openai's own words for a call that never reached the model."""


class APITimeoutError(Exception):
    pass


def _chained(*layers):
    """`layers` outer first, each raised from the next - the shape the client, httpx and the socket hand over."""
    exc = None
    for layer in reversed(layers):
        try:
            raise layer from exc
        except BaseException as raised:                            # noqa: BLE001
            exc = raised
    return exc


@pytest.mark.parametrize("proxy", [None, "http://user:pw@proxy.test:8080"])
@pytest.mark.parametrize("failure,inner", [
    ((APIConnectionError("Connection error."), httpx.ConnectError("[Errno 11001] getaddrinfo failed"),
      OSError(11001, "getaddrinfo failed")), "OSError: [Errno 11001] getaddrinfo failed"),
    ((APIConnectionError("Connection error."), httpx.ConnectError("[WinError 10061] actively refused"),
      ConnectionRefusedError(10061, "actively refused")), "ConnectionRefusedError: [Errno 10061] actively refused"),
    ((APIConnectionError("Connection error."), httpx.ProxyError("407 Proxy Authentication Required")),
     "ProxyError: 407 Proxy Authentication Required"),
    ((APITimeoutError("Request timed out."), httpx.ConnectTimeout("timed out"), TimeoutError("timed out")),
     "TimeoutError: timed out"),
], ids=["name", "refused", "proxy", "timeout"])
def test_a_connection_failure_says_its_innermost_reason_and_the_proxy(answer, root, failure, inner, proxy):
    """총괄 024e3d31f (소유자 「llm api 커넥션 에러 뜨는데」): the client's «Connection error.» named none of the four."""
    _declare(root, **CELLS, **({"proxy": proxy} if proxy else {}))
    answer(_chained(*failure))
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    via = "proxy: none (direct)" if not proxy else "proxy: "
    error = [line for line in _log_lines(root) if "error" in line][-1]["error"]
    for said in (str(refused.value), error):
        assert said.split(" · proxy: ")[0].endswith(inner), said
        assert via in said and "pw" not in said, said


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


def _chain_of(exc):
    said = []
    while exc is not None:
        said.append("%s: %s" % (type(exc).__name__, exc))
        exc = exc.__cause__ if exc.__cause__ is not None else (None if exc.__suppress_context__ else exc.__context__)
    return " <- ".join(said)


@pytest.mark.parametrize("password", ["Zq9/Wx7", "Zq9@Wx7", "Zq9:Wx7"], ids=["slash", "at", "colon"])
@pytest.mark.parametrize("written", ["raw", "escaped"])
def test_a_proxy_password_reaches_no_line_no_refusal_and_no_chain(answer, root, password, written):
    """총괄 93570a1ea (응용 감사): whatever the proxy cell holds, a failure is one received line and one refusal, and none
    of them holds a letter of the password. A raw «/» does not build (httpx read «Invalid port: '<its head>'»); the
    others reach the model and fail there. With no sent line, the received line says where it was going."""
    import re
    from urllib.parse import quote

    escaped = quote(password, safe="")
    _declare(root, **CELLS, proxy="http://op:%s@proxy.test:8080" % (password if written == "raw" else escaped))
    answer(_chained(APIConnectionError("Connection error."), httpx.ProxyError("407 Proxy Authentication Required")))
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    lines = _log_lines(root)
    built = not (written == "raw" and "/" in password)
    assert [("sent" in line, "received" in line) for line in lines] == (
        [(True, False), (False, True)] if built else [(False, True)]), "CANARY: both ways are taken"
    received = lines[-1]
    assert received["error"] and str(refused.value) == "the language model call failed: " + received["error"]
    if not built:
        assert (received["url"], received["proxy"]) == ("http://llm.test/v1/chat/completions",
                                                        "http://<redacted>@proxy.test:8080")
    said = json.dumps(lines, ensure_ascii=False) + str(refused.value) + _chain_of(refused.value)
    assert "proxy.test:8080" in str(refused.value), "CANARY: the proxy is said - by its host"
    assert [piece for piece in re.split(r"[/@:]", password) + [escaped] if piece in said] == [], said


def test_a_failure_raised_while_handling_another_says_both(answer, root):
    """`_why` follows an implicit chain too - raised inside an `except` without `from` (every cell above takes
    `__cause__`, so a cause-only `_why` stayed green)."""
    def raised_while_handling():
        try:
            raise OSError(11001, "getaddrinfo failed")
        except OSError:
            try:
                raise APIConnectionError("Connection error.")
            except APIConnectionError as exc:
                return exc

    answer(raised_while_handling())
    with pytest.raises(llm.LlmRefused) as refused:
        llm.ask_json("anything")
    assert str(refused.value).split(" · proxy: ")[0].endswith(
        "APIConnectionError: Connection error. <- OSError: [Errno 11001] getaddrinfo failed"), str(refused.value)


def test_find_links_rows_say_rules_and_their_sentence():
    (row,) = text_links.find_links("The bond temperature caused a void.", NAMES, [
        {"phrase": "caused", "meaning": "cause", "side": "before"}])
    assert (row["extractor"], row["evidence"]) == ("rules", row["sentence"])
    assert (row["cause_direction"], row["phenomenon_direction"], row["dir"]) == (None, None, None)


def test_the_mapper_door_reaches_the_same_functions():
    assert mapper_sdk.ask_json is llm.ask_json
    assert mapper_sdk.ask_links is text_links.ask_links
    assert mapper_sdk.LlmRefused is llm.LlmRefused


def test_a_listed_identifier_written_with_spaces_is_that_identifier(answer, caplog):
    """총괄 10-11: every «one of the listed» answer goes through `one_of` - spaces trimmed, case kept."""
    answer(_links({"cause": "온도", "cause_key": " F1 ", "effect": "생긴 보이드", "effect_key": "Q123 ",
                   "evidence": KO_EVIDENCE}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(KO_TEXT, KO_NAMES)
    assert (row["cause_key"], row["phenomenon_key"]) == ("F1", "Q123")
    assert _dropped_lines(caplog) == []


@pytest.mark.parametrize("said, kept, lines", [(" confirmed ", "confirmed", 0), ("suspected", "suspected", 0),
                                               (None, "suspected", 0), ("probable", "suspected", 1)],
                         ids=["spaces", "listed", "null", "unlisted"])
def test_a_certainty_is_one_of_the_two_or_said(answer, caplog, said, kept, lines):
    answer(_links({"cause": "온도", "cause_key": "F1", "effect": "생긴 보이드", "effect_key": "Q123",
                   "evidence": KO_EVIDENCE, "certainty": said}))
    caplog.set_level(logging.WARNING)
    (row,) = text_links.ask_links(KO_TEXT, KO_NAMES)
    assert row["certainty"] == kept
    assert _dropped_lines(caplog) == [
        "[LLM] link 1 of 1 answers certainty 'probable', which is not confirmed or suspected - kept as suspected"
        " (llm:m-1): %r" % KO_EVIDENCE][:lines]
