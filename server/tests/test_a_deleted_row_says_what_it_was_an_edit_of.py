# -*- coding: utf-8 -*-
"""Lead 11-08 (access QA ③ · ④): the seat that deletes a row writes what it was an edit of, so every batch_row_delete
of an edit_by table carries `edits_of` - the rows' own tables, read before they went - and none of a table without one.

  senders  PUT data/updates (a shell merged by key) · PUT <row>/<col>/priority · PUT cells/priority/batch (a pin that
           moves a key part merges its row away) · the chain worker's group (a shell merged by key) · PUT data/updates
           replace_map (a row its scope no longer claims - purge_map_rows - and a row it adopts from outside)
  tables   edit_probe (access edit_by target) -> edits_of the deleted rows' own targets · plain_probe -> no edits_of
  rows     A (M1|a, T1) · B (M1|b, T2) · C (M2|c, T3): a shell is A merged into B - its target T1, not B's T2
"""
import json
import uuid

import pytest
import uuid6

from conftest import retire_dynamic_model
from database import crud, models

EDIT, PLAIN = "edit_probe", "plain_probe"
COLUMNS = {"m": "string", "k": "string", "target": "string", "v": "string"}
ENTRY = {"business_key": "bk", "composite_key_source": ["m", "k"], "map_key_columns": ["m"], "column_types": COLUMNS}
ENTRIES = {EDIT: {**ENTRY, "access": {"edit_by": "target"}}, PLAIN: ENTRY}
ROWS = {"A": ("M1", "a", "T1"), "B": ("M1", "b", "T2"), "C": ("M2", "c", "T3")}
#: sender -> the deleted rows' targets the message names
SENDERS = {"updates": ["T1"], "pin": ["T1"], "pin_batch": ["T1"], "chain": ["T1"], "replace_map": ["T2", "T3"]}


@pytest.fixture(name="board")
def fixture_board(db_session, client, monkeypatch, request):
    import main

    table = request.param
    for name in ("_undeclared_column_drops", "_undeclared_column_warned", "_undeclared_column_drops_over_budget"):
        monkeypatch.setattr(crud, name, {})
    models.init_dynamic_models({table: ENTRIES[table]})
    monkeypatch.setitem(crud.TABLE_CONFIG, table, ENTRIES[table])
    bind = db_session.get_bind()
    models.DYNAMIC_TABLES[table].__table__.create(bind=bind)
    model = models.DYNAMIC_TABLES[table]
    ids = {name: str(uuid6.uuid7()) for name in ROWS}
    db_session.add_all([model(row_id=ids[name], m=m, k=k, target=target,
                              business_key_val=crud.compose_business_key(table, [m, k], ["m", "k"]))
                        for name, (m, k, target) in ROWS.items()])
    db_session.add(models.CellSource(table_name=table, row_id=ids["A"], column_name="k", source_name="lots.csv",
                                     value="b"))
    db_session.commit()
    sent = []

    async def capture(message):
        sent.append(json.loads(message))
    monkeypatch.setattr(main.manager, "broadcast", capture)
    try:
        yield table, client, ids, sent
    finally:
        db_session.rollback()
        for gone in (models.CellSource, models.CellOverwrite, models.AuditLog):
            db_session.query(gone).filter(gone.table_name == table).delete()
        db_session.commit()
        models.DYNAMIC_TABLES[table].__table__.drop(bind=bind)
        retire_dynamic_model(table)


def shell_mapper(db, payload):
    return {"updates": [{"row_id": payload["data"]["row_id"], "updates": {"k": "b"}, "source_name": "chain_ingestion"}]}


async def _deletes(sender, table, client, db_session, ids, sent):
    """The sender's write; its batch_row_delete messages."""
    if sender == "updates":
        answer = client.put("/tables/%s/data/updates" % table, json={"updates": [
            {"row_id": ids["A"], "updates": {"k": "b"}, "source_name": "user", "updated_by": "kim"}]})
    elif sender == "pin":
        answer = client.put("/tables/%s/%s/k/priority" % (table, ids["A"]), json={"source_name": "lots.csv"})
    elif sender == "pin_batch":
        answer = client.put("/tables/%s/cells/priority/batch" % table, json={
            "updates": [{"row_id": ids["A"], "column_name": "k"}], "source_name": "lots.csv", "updated_by": "kim"})
    elif sender == "replace_map":
        answer = client.put("/tables/%s/data/updates" % table, json={"replace_map": True, "updates": [
            {"updates": {"m": "M1", "k": "a", "target": "T1"}, "source_name": "user", "updated_by": "kim"},
            {"row_id": ids["C"], "updates": {"m": "M1", "k": "c"}, "source_name": "user", "updated_by": "kim"}]})
    else:
        from chain.ingestion_worker import process_chain_transaction_group

        tx = "gone_%s" % uuid.uuid4().hex[:8]
        trigger = models.DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type="CREATE", table_name="gone_trigger",
                                        payload={"source_name": "user", "transaction_id": tx,
                                                 "data": {"row_id": ids["A"]}})
        rule = {"name": "gone_rule", "trigger_table": "gone_trigger", "target_table": table,
                "mapper_module": "tests.test_a_deleted_row_says_what_it_was_an_edit_of",
                "mapper_function": "shell_mapper", "enabled": True, "is_batch": False}
        ok, err, msgs = await process_chain_transaction_group(tx, [trigger], db_session, [rule])
        assert ok is True and err is None, err
        return [m for m in msgs if m.get("event") == "batch_row_delete"]
    assert answer.status_code == 200, answer.text
    return [m for m in sent if m["event"] == "batch_row_delete"]


@pytest.mark.anyio
@pytest.mark.parametrize("board", [EDIT, PLAIN], indirect=True)
@pytest.mark.parametrize("sender", list(SENDERS))
async def test_a_delete_message_names_the_tables_its_rows_were_edits_of(board, db_session, sender):
    table, client, ids, sent = board
    deletes = await _deletes(sender, table, client, db_session, ids, sent)
    assert deletes, "canary: the write deleted a row and said so"
    gone = sorted(row_id for m in deletes for row_id in m["row_ids"])
    assert gone == sorted(ids[n] for n in (("B", "C") if sender == "replace_map" else ("A",))), (gone, ids)
    said = [m.get("edits_of", "absent") for m in deletes]
    assert said == ([SENDERS[sender]] if table == EDIT else ["absent"]), said
