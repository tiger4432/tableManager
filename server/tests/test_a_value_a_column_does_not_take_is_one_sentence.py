# -*- coding: utf-8 -*-
"""총괄 bed890af2 ② · a4cb623e0 ② — a value its column's type does not take is ONE sentence,
in English, naming the row, the column and the value, whichever door wrote it.

Before: the grid answered a Korean sentence with no row; a file load stored the whole
traceback; a chain failure's header named every rule of the group - or `(unknown)` - and
not the one whose write was refused."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                     # noqa: E402
from database import crud                                        # noqa: E402
from parsers import directory_watcher as dw                      # noqa: E402

SENTENCE = "Row %s: column 'target_qty' does not take 'abc' - a number is expected."


def test_the_cast_refuses_by_name():
    with pytest.raises(crud.CellRefused) as refused:
        crud.cast_value_by_type("abc", "number", "target_qty")
    assert str(refused.value) == ("Column 'target_qty' does not take 'abc' - "
                                  "a number is expected.")


def _plan(key, qty):
    return {"business_key_val": key, "updates": {"plan_id": key, "target_qty": qty}}


def test_the_grid_answers_it_with_the_row_it_was_sent(client):
    reply = client.put("/tables/production_plan/data/updates", json={
        "updates": [_plan("P1", 5), _plan("P2", "abc")], "transaction_id": "tx-refusal"})
    assert reply.status_code == 400
    assert reply.json()["detail"] == SENTENCE % 2


def test_a_file_load_names_the_file_row_not_the_batch_row(monkeypatch):
    """The second file row matches no column and never becomes an item, so the bad row is
    the THIRD item of the batch and the FOURTH row of the file."""
    class _Session:
        def execute(self, *a, **k):
            return self

        def scalar(self):
            return 1

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    class _Crud:
        CellRefused = crud.CellRefused
        loadable_columns = staticmethod(crud.loadable_columns)
        unmapped_columns = staticmethod(crud.unmapped_columns)
        row_is_blank = staticmethod(crud.row_is_blank)
        is_blank_value = staticmethod(crud.is_blank_value)
        DROP_UNDECLARED_COLUMN = crud.DROP_UNDECLARED_COLUMN
        DROP_UNMAPPED_COLUMN = crud.DROP_UNMAPPED_COLUMN
        not_written_sentence = staticmethod(crud.not_written_sentence)

        @staticmethod
        def apply_batch_updates(_db, _table, batch, notation_report=None):
            bad = [i for i, item in enumerate(batch.updates, start=1)
                   if item.updates.get("target_qty") == "abc"]
            raise crud.CellRefused("target_qty", "abc", "a number", row=bad[0])

    monkeypatch.setattr(dw, "SessionLocal", _Session)
    monkeypatch.setattr(dw, "crud", _Crud)
    monkeypatch.setattr(dw.heartbeat, "beat", lambda *a, **k: None)
    handler = dw.IngestionHandler.__new__(dw.IngestionHandler)
    handler.scripts_path = ""
    handler.on_progress_callback = None
    handler.on_refresh_callback = None
    rows = [{"plan_id": "P1", "target_qty": 1}, {"unrelated": 1},
            {"plan_id": "P3", "target_qty": 3}, {"plan_id": "P4", "target_qty": "abc"}]
    table_info = {"business_key": "plan_id",
                  "column_types": {"plan_id": "string", "target_qty": "number"}}
    with pytest.raises(crud.CellRefused) as refused:
        handler._send_to_upsert(rows, uploader="tester", filename="plan.csv",
                                t_name="production_plan", table_info=table_info)
    assert str(refused.value) == SENTENCE % 4


def test_a_chain_failure_names_the_rule_and_target_whose_write_was_refused(db_session):
    ok, reason = worker.apply_chain_writes(
        db_session, "tx-refusal", {"name": "r_probe", "target_table": "production_plan"}, 0,
        {"production_plan": {"r_probe"}},
        {"production_plan": [_plan("P1", "abc")]}, [], [],
        {"production_plan": ["r_probe"], "other_target": ["r_other"]}, [])
    assert ok is False
    assert reason == "[rules=r_probe target=production_plan] " + SENTENCE % 1
