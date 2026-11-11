# -*- coding: utf-8 -*-
"""총괄 6fa4c5094 (앱 발견, UI 는 영어 상설): the history pane drew «신규 데이터 생성: …» - the line a machine write leaves on
a row it changed. It is written in English now: «New row: …», and a value that is not there reads «empty». Lines
stored before keep their words - the history is not rewritten. The funnel's line is `crud._said_logs` (the old door's
`row_update_line` retired with the lines, 11-11)."""
import re

from database import crud

HANGUL = re.compile(r"[가-힣]")


def _said(change):
    answer = {"changed": {"r1": change}}
    return crud._said_logs("raw_table_1", answer, [{"row_id": "r1", "work": change["work"]}],
                           [({"source_name": "test", "written_by": None}, None)], "tx1", {})


def test_a_new_row_and_a_changed_row_leave_english_lines():
    [made] = _said({"old": None, "new": {"EQP_ID": "E1", "NOTE": None}, "work": "new"})
    assert (made["column_name"], made["new_value"]) == ("ROW_UPDATE", "New row: EQP_ID: E1")
    [changed] = _said({"old": {"NOTE": "x"}, "new": {"NOTE": None}, "work": "write"})
    assert changed["new_value"] == "NOTE: empty"
    [again] = _said({"old": {"NOTE": None}, "new": {"NOTE": "x"}, "work": "write"})
    assert again["new_value"] == "NOTE: x"
    assert not HANGUL.search(made["new_value"] + changed["new_value"] + again["new_value"])
