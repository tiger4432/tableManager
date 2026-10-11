# -*- coding: utf-8 -*-
"""소유자 10-11 「단어로 맞추기가 쉽지 않네 너무 다양해」 · 「자꾸 수식어 붙여」 · 「워드백 느낌으로」 (plan ㄱ).
A phrase names a node when the bag of its character bigrams holds the whole of a node phrase's bag;
the rows no node took are re-matched without the model, and the model suggests dictionary rows.

  match_phrase   modifiers around the node phrase      that node (score 1.0)
                 exact phrase · spaces · quote marks    that node
                 one node by two of its phrases         that node - not a tie
                 two different nodes side by side       no node, both named (ambiguous) · one phrase on two nodes too
                 a node phrase inside another node's    drops - the longer one wins (총괄 10-11)
                 less than match_at of the phrase       none · 0.8 lets one changed ending bigram through
                 a one-character phrase                 only that character
  rematch_rows   blank key                              filled, and its blank type
                 filled key                             never written
                 filled type of another node            side left as it was
                 nothing found · NaN cells              the row equal to the one handed in
  ask_links      null identifier, words with modifiers  the node of the bag · match_at passed through
                 names handed as a generator            matched all the same
  ask_dictionary listed id · unlisted id · new node     kept · null + one warning line · passed through
                 a phrase the answer skips              no row + one warning line
                 no phrase                              no call · no 'phrases' list: refused by name
"""
import json
import logging
import os
import sys

import pandas as pd
import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from utils import dictionary_suggest, llm, phrase_bag, text_links       # noqa: E402
from test_a_text_is_read_by_a_language_model import (                   # noqa: E402,F401 - the fixtures are used
    _links, fixture_answer, fixture_root)

NAMES = [{"node_type": "quantity", "node_key": "Q-BOND-T", "phrase": "접합 온도"},
         {"node_type": "quantity", "node_key": "Q-BOND-T", "phrase": "본딩 온도"},
         {"node_type": "defect", "node_key": "D-UF", "phrase": "계면 미충진"},
         {"node_type": "defect", "node_key": "D-VOID", "phrase": "보이드"},
         {"node_type": "factor", "node_key": "F-HEAT", "phrase": "열"},
         {"node_type": "factor", "node_key": "F-NONE", "phrase": None}]
EQUIPMENT = {"node_type": "equipment", "node_key": "E-BOND", "phrase": "본딩 설비"}
TEMPERATURE = {"node_type": "quantity", "node_key": "Q-T", "phrase": "온도"}
RISE = [{"node_type": "quantity", "node_key": "Q-RISE", "phrase": "접합 온도 상승"}]


def _node(found):
    return None if found is None else (found["node_type"], found["node_key"])


@pytest.mark.parametrize("answer,node,phrase", [
    ("본딩 설비의 접합 온도 파라미터", ("quantity", "Q-BOND-T"), "접합 온도"),
    ("웨이퍼 계면 미충진 발생", ("defect", "D-UF"), "계면 미충진"),
    ("계면미충진", ("defect", "D-UF"), "계면 미충진"),
    ("“접합 온도”…", ("quantity", "Q-BOND-T"), "접합 온도"),
    ("접합 온도와 본딩 온도", ("quantity", "Q-BOND-T"), "접합 온도"),
], ids=["equipment-and-parameter-around", "wafer-and-occurred-around", "exact-without-space",
        "quote-marks-and-ellipsis", "one-node-by-two-phrases"])
def test_the_node_phrase_held_by_the_answer_names_the_node(answer, node, phrase):
    found = phrase_bag.match_phrase(answer, NAMES)
    assert (_node(found), found["score"], found["phrase"], found["ambiguous"]) == (node, 1.0, phrase, [])


@pytest.mark.parametrize("names,answer", [
    (NAMES + [EQUIPMENT], "본딩 설비의 접합 온도 파라미터"),
    (NAMES + [dict(EQUIPMENT, phrase="접합 온도")], "접합 온도"),
], ids=["two-nodes-side-by-side", "one-phrase-on-two-nodes"])
def test_two_different_nodes_left_at_the_top_give_no_node_and_both_are_named(names, answer):
    found = phrase_bag.match_phrase(answer, names)
    assert (_node(found), found["score"], found["phrase"]) == ((None, None), 1.0, None)
    assert sorted(found["ambiguous"], key=str) == sorted(
        [{"node_type": "equipment", "node_key": "E-BOND"}, {"node_type": "quantity", "node_key": "Q-BOND-T"}],
        key=str)


@pytest.mark.parametrize("answer", ["접합 온도", "본딩 설비의 접합 온도 파라미터"],
                         ids=["a-phrase-inside-another-nodes-phrase", "inside-with-modifiers-around"])
def test_a_phrase_inside_another_nodes_phrase_drops_and_the_longer_wins(answer):
    """총괄 10-11: «온도» and «접합 온도» both held give «접합 온도», as the exact match did."""
    found = phrase_bag.match_phrase(answer, NAMES + [TEMPERATURE])
    assert (_node(found), found["score"], found["phrase"], found["ambiguous"]) == (
        ("quantity", "Q-BOND-T"), 1.0, "접합 온도", [])


@pytest.mark.parametrize("answer", ["접합 압력 파라미터", "온도", "", None, float("nan")],
                         ids=["one-bigram-of-three", "half-of-a-phrase", "empty", "none", "nan"])
def test_less_than_the_whole_phrase_names_no_node(answer):
    assert phrase_bag.match_phrase(answer, NAMES) is None


def test_match_at_lets_one_changed_ending_bigram_through():
    """접합온도상승 has five bigrams; 상향 for 상승 keeps four - 0.8."""
    assert phrase_bag.match_phrase("접합 온도 상향", RISE) is None
    found = phrase_bag.match_phrase("접합 온도 상향", RISE, match_at=0.8)
    assert (_node(found), found["score"]) == (("quantity", "Q-RISE"), 0.8)
    assert phrase_bag.match_phrase("접합 온도 상향", RISE, match_at=None) is None, "None is the default"
    assert phrase_bag.MATCH_AT == 1.0


@pytest.mark.parametrize("answer,node", [("열", ("factor", "F-HEAT")), ("열 변형", None)])
def test_a_one_character_phrase_is_that_character(answer, node):
    assert _node(phrase_bag.match_phrase(answer, NAMES)) == node


CANDIDATES = [
    {"doc_id": "T1", "sentence_no": 1, "cause_phrase": "본딩 설비의 접합 온도 파라미터",
     "cause_type": None, "cause_key": None,
     "phenomenon_phrase": "웨이퍼 계면 미충진 발생", "phenomenon_type": "defect", "phenomenon_key": "D-OLD"},
    {"doc_id": "T1", "sentence_no": 2, "cause_phrase": "보이드 증가", "cause_type": "  ", "cause_key": "",
     "phenomenon_phrase": "습도", "phenomenon_type": None, "phenomenon_key": None},
    {"doc_id": "T2", "sentence_no": 1, "cause_phrase": "접합 온도", "cause_type": "factor", "cause_key": None,
     "phenomenon_phrase": "보이드", "phenomenon_type": None, "phenomenon_key": None},
]


def test_rematch_fills_only_the_blank_keys():
    handed = [dict(row) for row in CANDIDATES]
    first, second, third = phrase_bag.rematch_rows(handed, NAMES)
    assert handed == CANDIDATES, "the rows handed in are not changed"
    assert first == dict(CANDIDATES[0], cause_type="quantity", cause_key="Q-BOND-T"), (
        "the filled phenomenon key D-OLD stays though its phrase holds D-UF's")
    assert second == dict(CANDIDATES[1], cause_type="defect", cause_key="D-VOID")
    assert third == dict(CANDIDATES[2], phenomenon_type="defect", phenomenon_key="D-VOID"), (
        "a filled type of another node keeps its side as it was")


def test_a_row_nothing_was_filled_in_is_equal_to_the_one_handed_in():
    """What a mapper filters on: SQL NULL reaches it as NaN, and NaN != NaN."""
    rows = pd.DataFrame([{"cause_phrase": "습도", "cause_type": None, "cause_key": None,
                          "phenomenon_phrase": None, "phenomenon_type": None, "phenomenon_key": None,
                          "sentence_no": float("nan")},
                         {"cause_phrase": "접합 온도", "cause_type": None, "cause_key": None,
                          "phenomenon_phrase": None, "phenomenon_type": None, "phenomenon_key": None,
                          "sentence_no": 3.0}]).astype({"cause_key": float}).to_dict("records")
    after = phrase_bag.rematch_rows(rows, NAMES)
    assert [a != b for a, b in zip(after, rows)] == [False, True]
    assert after[1]["cause_key"] == "Q-BOND-T"


SENTENCE = "본딩 설비의 접합 온도 파라미터가 높아 웨이퍼 계면 미충진 발생이 늘었다."
TEXT = "첫 문장이다. " + SENTENCE


def test_a_null_identifier_with_modifiers_gets_the_node_of_its_bag(answer):
    answer(_links({"cause": "본딩 설비의 접합 온도 파라미터", "cause_key": None,
                   "effect": "웨이퍼 계면 미충진 발생", "effect_key": None, "evidence": SENTENCE}))
    (row,) = text_links.ask_links(TEXT, NAMES)
    assert (row["cause_type"], row["cause_key"], row["phenomenon_type"], row["phenomenon_key"]) == (
        "quantity", "Q-BOND-T", "defect", "D-UF")
    assert (row["cause_phrase"], row["phenomenon_phrase"]) == ("본딩 설비의 접합 온도 파라미터", "웨이퍼 계면 미충진 발생")


def test_names_handed_as_a_generator_are_matched_all_the_same(answer):
    answer(_links({"cause": "본딩 설비의 접합 온도 파라미터", "effect": "보이드", "evidence": SENTENCE}))
    (row,) = text_links.ask_links(TEXT, (name for name in NAMES))
    assert (row["cause_key"], row["phenomenon_key"]) == ("Q-BOND-T", "D-VOID")


@pytest.mark.parametrize("match_at,key", [(None, None), (0.8, "Q-RISE")])
def test_ask_links_passes_match_at_to_the_bag(answer, match_at, key):
    answer(_links({"cause": "접합 온도 상향", "effect": "보이드", "evidence": SENTENCE}))
    (row,) = text_links.ask_links(TEXT, RISE, match_at=match_at)
    assert row["cause_key"] == key


PHRASES = [{"phrase": "접합 온도 파라미터", "count": 4}, {"phrase": "  ", "count": 9},
           {"phrase": "웨이퍼 휨", "count": 3}, {"phrase": "습도", "count": 2}, {"phrase": "압력", "count": 1}]


def _suggested(answer, caplog, *items, phrases=PHRASES):
    asked = answer('{"phrases": %s}' % json.dumps(list(items), ensure_ascii=False))
    caplog.set_level(logging.WARNING)
    rows = dictionary_suggest.ask_dictionary(phrases, NAMES)
    lines = [r.getMessage() for r in caplog.records if r.name == "utils.dictionary_suggest"]
    return asked, rows, lines


def test_a_listed_node_is_kept_an_unlisted_one_is_said_and_a_new_name_passes(answer, caplog):
    asked, rows, lines = _suggested(
        answer, caplog,
        {"number": 1, "node": "Q-BOND-T", "new_node": None, "reason": "the bond temperature setting"},
        {"number": "2", "node": None, "new_node": "웨이퍼 휨", "reason": "no listed node is a warp"},
        {"number": 3, "node": "Q-HUMID", "new_node": None, "reason": "humidity"})
    assert rows == [
        {"phrase": "접합 온도 파라미터", "count": 4, "suggested_node_type": "quantity",
         "suggested_node_key": "Q-BOND-T", "new_node_name": None, "reason": "the bond temperature setting",
         "extractor": "llm:m-1"},
        {"phrase": "웨이퍼 휨", "count": 3, "suggested_node_type": None, "suggested_node_key": None,
         "new_node_name": "웨이퍼 휨", "reason": "no listed node is a warp", "extractor": "llm:m-1"},
        {"phrase": "습도", "count": 2, "suggested_node_type": None, "suggested_node_key": None,
         "new_node_name": None, "reason": "humidity", "extractor": "llm:m-1"}]
    assert lines == [
        "[LLM] phrase 3 of 4 answers node 'Q-HUMID', which the dictionary does not list"
        " - suggested without a node (llm:m-1): '습도'",
        "[LLM] phrase 4 of 4 has no answer - no suggestion (llm:m-1): '압력'"]
    prompt = asked[-1][1][-1]["content"]
    by_id, block = text_links._listing(NAMES)
    assert prompt == dictionary_suggest.ASK_DICTIONARY_PROMPT.replace("<<dictionary>>", block).replace(
        "<<instruction>>", "").replace("<<phrases>>", "1: 접합 온도 파라미터\n2: 웨이퍼 휨\n3: 습도\n4: 압력")
    assert "Q-BOND-T (quantity): 접합 온도 / 본딩 온도" in block.splitlines()
    assert not any("가" <= ch <= "힣" for ch in dictionary_suggest.ASK_DICTIONARY_PROMPT)


def test_no_phrase_asks_nothing_and_an_answer_without_phrases_is_refused(answer, caplog):
    asked, rows, _lines = _suggested(answer, caplog, phrases=[{"phrase": None}, {"phrase": "  "}])
    assert (rows, asked) == ([], [])
    answer('{"rows": []}')
    with pytest.raises(llm.LlmRefused) as refused:
        dictionary_suggest.ask_dictionary(PHRASES, NAMES)
    assert "the answer has no 'phrases' list" in str(refused.value)


def test_the_operators_instruction_reaches_the_prompt(answer):
    asked = answer('{"phrases": []}')
    dictionary_suggest.ask_dictionary(PHRASES[:1], NAMES, instruction="prefer existing nodes")
    assert "%s\nprefer existing nodes" % text_links.INSTRUCTION_HEADING in asked[-1][1][-1]["content"]
