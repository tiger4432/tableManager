# -*- coding: utf-8 -*-
"""총괄 15a4d8e43 · 9f301f9bc — cause -> phenomenon candidates read out of free text with the
caller's own dictionaries (`utils.text_links`). The Korean here is fixture DATA: the module
itself holds no word of any language."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils import text_links  # noqa: E402

NAMES = [{"node_type": "factor", "node_key": "bond_pressure", "phrase": "본딩 압력"},
         {"node_type": "defect", "node_key": "interface_unfilled", "phrase": "계면 미충진"},
         {"node_type": "defect", "node_key": "void", "phrase": "보이드"},
         {"node_type": "defect", "node_key": "void", "phrase": "void"},
         {"node_type": "factor", "node_key": "wafer_warp", "phrase": "웨이퍼휨"}]
LINKS = [{"phrase": "로 인해", "meaning": "cause", "side": "before"},
         {"phrase": "원인", "meaning": "cause", "side": "after"},
         {"phrase": "무관", "meaning": "cause", "side": "before"},
         {"phrase": "무관", "meaning": "negation", "side": None},
         {"phrase": ",", "meaning": "and", "side": None},
         {"phrase": "과", "meaning": "and", "side": None},
         {"phrase": "추정", "meaning": "suspected", "side": None},
         {"phrase": "확인 필요", "meaning": "suspected", "side": None},
         {"phrase": "확인", "meaning": "confirmed", "side": None}]


def _said(text, names=NAMES, links=LINKS):
    return sorted((r["cause_key"], r["phenomenon_key"], r["polarity"], r["certainty"])
                  for r in text_links.find_links(text, names, links))


@pytest.mark.parametrize("text, expected", [
    ("본딩 압력 저하로 인해 계면 미충진 발생 추정",
     [("bond_pressure", "interface_unfilled", "asserted", "suspected")]),
    # the phenomenon comes first as the topic - only «nearest» keeps it out of the causes
    ("보이드는 본딩 압력 저하로 인해 발생", [("bond_pressure", "void", "asserted", "stated")]),
    ("보이드의 원인은 본딩 압력", [("bond_pressure", "void", "asserted", "stated")]),
    ("보이드는 웨이퍼 휨과 무관 확인", [("wafer_warp", "void", "negated", "confirmed")]),
    ("본딩 압력, 웨이퍼 휨으로 인해 보이드", [("bond_pressure", "void", "asserted", "stated"),
                                       ("wafer_warp", "void", "asserted", "stated")]),
    ("보이드 다수, 웨이퍼 휨 확인 필요", []),
    # spaces on either side: 「계면미충진」 in the text, 「웨이퍼휨」 in the dictionary
    ("본딩압력 저하로 인해 계면미충진 발생", [("bond_pressure", "interface_unfilled", "asserted", "stated")]),
    ("본딩 압력과 웨이퍼 휨으로 인해 계면 미충진 발생",
     [("bond_pressure", "interface_unfilled", "asserted", "stated"),
      ("wafer_warp", "interface_unfilled", "asserted", "stated")]),
    ("본딩 압력으로 인해 보이드 발생 추정 확인", [("bond_pressure", "void", "asserted", "suspected")]),
])
def test_the_gate_table(text, expected):
    assert _said(text) == expected


def test_ascii_case_is_folded_and_the_words_come_back_as_written():
    rows = text_links.find_links("VOID 는 본딩 압력 저하로 인해 발생", NAMES, LINKS)
    assert [(r["cause_key"], r["phenomenon_key"], r["phenomenon_phrase"], r["link"])
            for r in rows] == [("bond_pressure", "void", "VOID", "로 인해")]


def test_an_ascii_phrase_does_not_match_inside_a_longer_word():
    assert _said("avoid 를 위해 본딩 압력 저하로 인해 발생") == []
    assert _said("void. 본딩 압력 저하로 인해 발생") == []          # two sentences, no pair
    assert _said("본딩 압력 저하로 인해 void 발생") == [("bond_pressure", "void", "asserted", "stated")]


def test_both_dictionaries_share_one_longest_match():
    names = NAMES + [{"node_type": "step", "node_key": "check", "phrase": "확인"}]
    assert _said("본딩 압력으로 인해 보이드 확인 필요", names) == [
        ("bond_pressure", "void", "asserted", "suspected")]


def test_sentences_are_numbered_and_a_decimal_point_does_not_split():
    rows = text_links.find_links("본딩 압력 1.5 저하로 인해 보이드 발생. 웨이퍼 휨으로 인해 계면 미충진",
                                 NAMES, LINKS)
    assert [(r["sentence_no"], r["cause_key"], r["phenomenon_key"]) for r in rows] == [
        (1, "bond_pressure", "void"), (2, "wafer_warp", "interface_unfilled")]


def test_an_empty_dictionary_says_nothing_and_blank_phrases_are_absent():
    text = "본딩 압력 저하로 인해 보이드 발생"
    assert text_links.find_links(text, [], []) == []
    blank = [{"node_type": "x", "node_key": k, "phrase": p}
             for k, p in (("none", None), ("nan", float("nan")), ("empty", " "))]
    # a NaN phrase read as the text "nan" would cover that word and drop it from the count
    assert [w["word"] for w in text_links.unknown_words(["nan none"], blank, [])] == ["nan", "none"]
    assert {w["word"] for w in text_links.unknown_words([text], [], [])} >= {"본딩", "보이드"}


def test_the_words_no_phrase_covered_are_counted_across_texts():
    words = text_links.unknown_words(["본딩 압력 저하로 인해 보이드 발생",
                                      "웨이퍼 휨 저하로 인해 보이드 발생"], NAMES, LINKS)
    counts = {w["word"]: w["count"] for w in words}
    assert counts["저하"] == 2 and counts["발생"] == 2
    assert "보이드" not in counts and "압력" not in counts
    assert words[0]["count"] >= words[-1]["count"]


def test_a_link_row_that_cannot_be_read_is_refused_by_name():
    with pytest.raises(ValueError, match="meaning 'because'"):
        text_links.find_links("x", [], [{"phrase": "로 인해", "meaning": "because", "side": "before"}])
    with pytest.raises(ValueError, match="needs side"):
        text_links.find_links("x", [], [{"phrase": "로 인해", "meaning": "cause", "side": None}])
