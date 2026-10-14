# -*- coding: utf-8 -*-
"""총괄 6fa4c5094 (앱 발견, UI 는 영어 상설): the history pane drew «신규 데이터 생성: …» - the line a machine write leaves on
a row it changed (`crud.row_update_line`). It is written in English now: «New row: …», and a value that is not there
reads «empty». Lines stored before keep their words - the history is not rewritten."""
import re

from database import crud

HANGUL = re.compile(r"[가-힣]")


def test_a_new_row_and_a_changed_row_leave_english_lines(db_session):
    made = crud.row_update_line(db_session, "raw_table_1", "r1", ["EQP_ID", "NOTE"], {"EQP_ID": "E1", "NOTE": None},
                                {}, True, "test", None, "tx1", "E1", add_to_cache=False)
    assert made["old_value"] is None and made["new_value"] == "New row: EQP_ID: E1, NOTE: empty"
    changed = crud.row_update_line(db_session, "raw_table_1", "r1", ["NOTE"], {"NOTE": "x"}, {"NOTE": None},
                                   False, "test", None, "tx2", "E1", add_to_cache=False)
    assert (changed["old_value"], changed["new_value"]) == ("NOTE: empty", "NOTE: x")
    assert not HANGUL.search(made["new_value"] + changed["old_value"] + changed["new_value"])
