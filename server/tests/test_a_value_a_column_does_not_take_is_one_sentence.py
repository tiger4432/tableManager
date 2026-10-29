# -*- coding: utf-8 -*-
"""A value its column's type does not take: the cast says it in ONE English sentence (총괄 bed890af2 ②), and since
10-29 no door stops on it - the cell is not entered, the rest is written, the cell is counted by name
(`DROP_VALUE_REFUSED`; owner 10-29 ㄱ)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from chain import ingestion_worker as worker                     # noqa: E402
from database import crud                                        # noqa: E402
from parsers import directory_watcher as dw                      # noqa: E402

def test_the_cast_refuses_by_name():
    with pytest.raises(crud.CellRefused) as refused:
        crud.cast_value_by_type("abc", "number", "target_qty")
    assert str(refused.value) == ("Column 'target_qty' does not take 'abc' - "
                                  "a number is expected.")


def _plan(key, qty):
    return {"business_key_val": key, "updates": {"plan_id": key, "target_qty": qty}}


def _stored(db, key):
    from database import models
    model = models.DYNAMIC_TABLES["production_plan"]
    return db.query(model).filter(model.business_key_val == key).one_or_none()


# 🔴 INVERTED (owner 10-29 «데이터 값은 멈추지 않는다» ㄱ). The three doors below used to refuse the WHOLE write for one
# value - a grid paste answered 400, a file stopped, a chain group failed and counted toward switching its rule off.
# Now that cell is not entered, the rest of its row and every other row is written, and the cell is counted by name.


def test_the_grid_writes_the_rest_and_reports_the_cell(client, db_session):
    reply = client.put("/tables/production_plan/data/updates", json={
        "updates": [_plan("P1", 5), _plan("P2", "abc")], "transaction_id": "tx-refusal"})

    assert reply.status_code == 200, reply.text
    dropped = reply.json()["dropped"]
    assert dropped["by_reason"] == {crud.DROP_VALUE_REFUSED: 1}
    assert dropped["columns"] == ["target_qty"]
    assert _stored(db_session, "P1").target_qty == 5
    p2 = _stored(db_session, "P2")
    assert p2 is not None and p2.target_qty is None, "the row is written, the refused cell is not entered"


def test_a_file_load_writes_the_rest_and_names_the_column_in_its_line(monkeypatch, db_session):
    import conftest

    monkeypatch.setattr(dw, "SessionLocal", conftest.TestingSessionLocal)
    monkeypatch.setattr(dw.heartbeat, "beat", lambda *a, **k: None)
    handler = dw.IngestionHandler.__new__(dw.IngestionHandler)
    handler.scripts_path = ""
    handler.on_progress_callback = None
    handler.on_refresh_callback = None
    rows = [{"plan_id": "P1", "target_qty": 1}, {"plan_id": "P3", "target_qty": 3},
            {"plan_id": "P4", "target_qty": "abc"}, {"plan_id": "P5", "target_qty": "N/A"}]
    table_info = {"business_key": "plan_id",
                  "column_types": {"plan_id": "string", "target_qty": "number"}}

    said = handler._send_to_upsert(rows, uploader="tester", filename="plan.csv",
                                   t_name="production_plan", table_info=table_info)

    db_session.expire_all()
    assert [_stored(db_session, k) is not None for k in ("P1", "P3", "P4", "P5")] == [True] * 4
    assert _stored(db_session, "P3").target_qty == 3
    assert "value_refused target_qty=2" in said, said
    assert crud.NOT_WRITTEN_NEXT[crud.DROP_VALUE_REFUSED] in said, said


def test_a_chain_group_writes_the_rest_and_does_not_fail(db_session):
    ok, reason = worker.apply_chain_writes(
        db_session, "tx-refusal", {"name": "r_probe", "target_table": "production_plan"}, 0,
        {"production_plan": {"r_probe"}},
        {"production_plan": [_plan("P1", "abc"), _plan("P2", 2)]}, [], [],
        {"production_plan": ["r_probe"], "other_target": ["r_other"]}, [])

    assert ok is True and reason is None, reason
    assert _stored(db_session, "P2").target_qty == 2
    assert _stored(db_session, "P1") is not None and _stored(db_session, "P1").target_qty is None
