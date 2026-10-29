# -*- coding: utf-8 -*-
"""Lead 10-29 (after a75d4a5fd): the grid save's `dropped` carries `said` - the sentence a file's load says for what it
did not write, made by the same function (`crud.not_written_sentence`), the first refused value in it. The client puts
it in its toast as it comes.

  the write                                   dropped.said
  the same bad values by a file and the grid  one sentence, letter for letter, with the first value refused
  an undeclared column only                   «Next: declare … Not written: undeclared_column zz=1 over 1 row(s).»
  nothing dropped                             no `dropped` at all
  only a drop it has no words for (system)   `dropped` as it was, no `said`
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                        # noqa: E402
from parsers import directory_watcher as dw                      # noqa: E402

REFUSED = ("Next: fix the values their columns' types do not take - the rest of each row was written. "
           "Not written: value_refused target_qty=2 (first 'abc') over 3 row(s).")


def _file_says(monkeypatch, rows):
    import conftest

    monkeypatch.setattr(dw, "SessionLocal", conftest.TestingSessionLocal)
    monkeypatch.setattr(dw.heartbeat, "beat", lambda *a, **k: None)
    handler = dw.IngestionHandler.__new__(dw.IngestionHandler)
    handler.scripts_path = ""
    handler.on_progress_callback = None
    handler.on_refresh_callback = None
    return handler._send_to_upsert(rows, uploader="tester", filename="plan.csv", t_name="production_plan",
                                   table_info={"business_key": "plan_id",
                                               "column_types": {"plan_id": "string", "target_qty": "number"}})


def _grid_says(client, rows):
    reply = client.put("/tables/production_plan/data/updates", json={
        "updates": [{"business_key_val": row["plan_id"], "updates": row} for row in rows],
        "transaction_id": "tx-said"})
    assert reply.status_code == 200, reply.text
    return reply.json()


def test_the_same_bad_values_say_one_sentence_by_a_file_and_by_the_grid(client, db_session, monkeypatch):
    by_file = _file_says(monkeypatch, [{"plan_id": "F1", "target_qty": 1}, {"plan_id": "F2", "target_qty": "abc"},
                                       {"plan_id": "F3", "target_qty": "N/A"}])
    by_grid = _grid_says(client, [{"plan_id": "G1", "target_qty": 1}, {"plan_id": "G2", "target_qty": "abc"},
                                  {"plan_id": "G3", "target_qty": "N/A"}])
    assert by_file == REFUSED
    assert by_grid["dropped"]["said"] == by_file
    assert {key: by_grid["dropped"][key] for key in ("cells", "rows", "columns", "by_reason")} == {
        "cells": 2, "rows": 2, "columns": ["target_qty"], "by_reason": {crud.DROP_VALUE_REFUSED: 2}}, \
        "the other cells of dropped as they were"


def test_an_undeclared_column_alone_is_said_too(client, db_session):
    said = _grid_says(client, [{"plan_id": "G9", "zz": "x"}])["dropped"]
    assert said["by_reason"] == {crud.DROP_UNDECLARED_COLUMN: 1}
    assert said["said"] == ("Next: declare the undeclared columns in table_config.json. "
                            "Not written: undeclared_column zz=1 over 1 row(s).")


def test_nothing_dropped_says_nothing(client, db_session):
    assert "dropped" not in _grid_says(client, [{"plan_id": "G8", "target_qty": 8}])


def test_a_drop_the_sentence_has_no_words_for_is_not_said(client, db_session):
    dropped = _grid_says(client, [{"plan_id": "G7", "target_qty": 7, "updated_at": "2026-10-29"}])["dropped"]
    assert dropped["by_reason"] == {crud.DROP_SYSTEM_COLUMN: 1} and "said" not in dropped


def test_blank_values_are_not_counted_at_either_door(client, db_session, monkeypatch):
    """Lead 10-29: a blank (length 0 after strip = absent) lost nothing, so neither door counts it - the file's count;
    a column of blanks only is still named, at 0."""
    mixed = [{"zz": ""}, {"zz": "   "}, {"zz": "x"}]
    by_file = _file_says(monkeypatch, [dict(row, plan_id="F%d" % n) for n, row in enumerate(mixed)])
    by_grid = _grid_says(client, [dict(row, plan_id="G%d" % n) for n, row in enumerate(mixed)])["dropped"]
    assert by_file == by_grid["said"] == ("Next: declare the undeclared columns in table_config.json. "
                                          "Not written: undeclared_column zz=1 over 3 row(s).")
    assert by_grid["cells"] == 3, "dropped's cells count every dropped cell, as they did"
    blanks = [{"zz": ""}, {"zz": "  "}]
    by_file = _file_says(monkeypatch, [dict(row, plan_id="H%d" % n) for n, row in enumerate(blanks)])
    by_grid = _grid_says(client, [dict(row, plan_id="K%d" % n) for n, row in enumerate(blanks)])["dropped"]
    assert by_file == by_grid["said"] == ("Next: declare the undeclared columns in table_config.json. "
                                          "Not written: undeclared_column zz=0 over 2 row(s).")
