# -*- coding: utf-8 -*-
"""Lead 11-08 (클라B's range paint): a write past BROADCAST_ITEM_LIMIT sends a count, not its rows - for a table that
declares access.edit_by, the count still says which tables its rows are edits of (`edits_of`, `access.edits_of`),
so a screen knows whether its table was painted. Past BROADCAST_ITEM_LIMIT names: said cut instead.

  doors     data/updates · cells/priority/batch · cells/sources/delete/batch
  sys_looks 1,000 rows over two tables -> edits_of [both] · over 101 tables -> no edits_of, truncated.edits_of cut 101
            a pin or a layer removal on it is refused by name: a shipped table keeps no lines, no history (lead 11-13 ㄴ)
  no edit_by the same doors on rmscope_test_map -> no edits_of, no truncated (as before)
"""
import json

import pytest

import shipped
from database import crud, models
from event_constants import BROADCAST_ITEM_LIMIT

LOOKS = "sys_looks"
PLAIN = "rmscope_test_map"
N = BROADCAST_ITEM_LIMIT + 1
ROWS = 1000                          # a range paint's size


@pytest.fixture
def sent(client, db_session, monkeypatch):
    import main

    assert LOOKS in models.DYNAMIC_TABLES, "CANARY: the shipped look table"
    monkeypatch.setitem(crud.TABLE_CONFIG, LOOKS, shipped.tables()[LOOKS])
    assert crud.TABLE_CONFIG[LOOKS]["access"]["edit_by"] == "look_table", "CANARY: sys_looks declares edit_by"
    assert "edit_by" not in (crud.TABLE_CONFIG[PLAIN].get("access") or {}), "CANARY: the plain table declares none"
    out = []

    async def capture(message):
        out.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", capture)
    yield out
    looks = models.DYNAMIC_TABLES[LOOKS]
    db_session.rollback()
    db_session.query(looks).delete()
    db_session.commit()


def _write(client, table, rows):
    answer = client.put("/tables/%s/data/updates" % table, json={"updates": [
        {"updates": row, "source_name": "user", "updated_by": "probe"} for row in rows]})
    assert answer.status_code == 200, answer.text


def _looks(tables, count):
    return [{"look_table": tables[n % len(tables)], "look_axis": "paint", "look_key": "k%d" % n, "role": "fill"}
            for n in range(count)]


def _plain(count):
    return [{"die_key": "E_%d" % n, "ref_table": "bonding_map", "map_key": "E", "x": n, "y": 0, "val": "1"}
            for n in range(count)]


def _ids(db_session, table):
    model = models.DYNAMIC_TABLES[table]
    return [row_id for (row_id,) in db_session.query(model.row_id).all()]


def _cells(db_session, table, column):
    return [{"row_id": row_id, "column_name": column} for row_id in _ids(db_session, table)]


def _then(client, db_session, sent, door, table, column):
    """The door's write on every row there - the refresh it sent."""
    sent.clear()
    if door == "updates":
        rows = _looks(["t_a", "t_b"], ROWS) if table == LOOKS else _plain(ROWS)
        model = models.DYNAMIC_TABLES[table]
        db_session.query(model).delete()
        db_session.commit()
        _write(client, table, rows)
    elif door == "priority":
        answer = client.put("/tables/%s/cells/priority/batch" % table, json={
            "updates": _cells(db_session, table, column), "source_name": "user", "updated_by": "probe"})
        assert answer.status_code == 200, answer.text
    else:
        answer = client.post("/tables/%s/cells/sources/delete/batch" % table, json={
            "cells": _cells(db_session, table, column), "source_name": "user"})
        assert answer.status_code == 200, answer.text
    refreshes = [m for m in sent if m["event"] == "batch_refresh_required"]
    assert len(refreshes) == 1 and refreshes[0]["change_count"] == ROWS, sent
    return refreshes[0]


def test_a_big_write_to_an_edit_by_table_says_the_tables_its_rows_are_edits_of(client, db_session, sent):
    _write(client, LOOKS, _looks(["t_a", "t_b"], ROWS))
    said = _then(client, db_session, sent, "updates", LOOKS, "role")
    assert said["edits_of"] == ["t_a", "t_b"]
    assert "truncated" not in said


@pytest.mark.parametrize("door", ["priority", "sources_delete"])
def test_a_pin_or_a_layer_removal_on_the_shipped_look_table_is_refused_by_name(client, db_session, sent, door):
    _write(client, LOOKS, _looks(["t_a", "t_b"], 3))
    sent.clear()
    if door == "priority":
        answer = client.put("/tables/%s/cells/priority/batch" % LOOKS, json={
            "updates": _cells(db_session, LOOKS, "role"), "source_name": "user", "updated_by": "probe"})
    else:
        answer = client.post("/tables/%s/cells/sources/delete/batch" % LOOKS, json={
            "cells": _cells(db_session, LOOKS, "role"), "source_name": "user"})
    assert answer.status_code == 422 and "'role' of 'sys_looks' keeps no history" in answer.text, answer.text
    assert [m for m in sent if m["event"] == "batch_refresh_required"] == []


def test_past_the_limit_of_names_it_is_said_cut():
    from event_constants import batch_refresh_message

    names = ["t_%03d" % n for n in range(N)]
    said = batch_refresh_message(LOOKS, 2 * N, edits_of=names)
    assert "edits_of" not in said
    assert said["truncated"]["edits_of"] == {"cut": True, "omitted": N, "reason": "tables beyond BROADCAST_ITEM_LIMIT"}
    assert batch_refresh_message(LOOKS, 2 * N, edits_of=names[:BROADCAST_ITEM_LIMIT])["edits_of"] == \
        names[:BROADCAST_ITEM_LIMIT], "canary: at the limit the names ride"


def test_a_big_write_over_more_tables_than_the_limit_is_said_cut(client, db_session, sent):
    _write(client, LOOKS, _looks(["t_%03d" % n for n in range(N)], N))
    said = [m for m in sent if m["event"] == "batch_refresh_required"]
    assert len(said) == 1 and "edits_of" not in said[0]
    assert said[0]["truncated"]["edits_of"]["omitted"] == N


@pytest.mark.parametrize("door", ["updates", "priority", "sources_delete"])
def test_a_table_declaring_no_edit_by_sends_what_it_did(client, db_session, sent, door):
    _write(client, PLAIN, _plain(ROWS))
    said = _then(client, db_session, sent, door, PLAIN, "val")
    assert "edits_of" not in said and "truncated" not in said
    model = models.DYNAMIC_TABLES[PLAIN]
    db_session.query(model).delete()
    db_session.commit()


def big_looks_mapper(db, payload):
    return {"updates": [{"updates": row, "source_name": "chain_ingestion"} for row in _looks(["t_a", "t_b"], ROWS)]}


def big_plain_mapper(db, payload):
    return {"updates": [{"updates": row, "source_name": "chain_ingestion"} for row in _plain(ROWS)]}


@pytest.mark.anyio
@pytest.mark.parametrize("table, mapper, expected", [(LOOKS, "big_looks_mapper", ["t_a", "t_b"]),
                                                     (PLAIN, "big_plain_mapper", None)])
async def test_the_chain_door_says_it_too(db_session, sent, table, mapper, expected):
    import uuid

    from chain.ingestion_worker import process_chain_transaction_group
    from database.models import DatabaseOutbox

    tx_id = "edits_of_%s" % table
    trigger = DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type="CREATE", table_name="edits_of_trigger",
                             payload={"source_name": "user", "transaction_id": tx_id, "data": {"k": "v"}})
    rule = {"name": "edits_of_rule", "trigger_table": "edits_of_trigger", "target_table": table,
            "mapper_module": "tests.test_a_big_write_says_which_tables_its_edits_are_of",
            "mapper_function": mapper, "enabled": True, "is_batch": False}
    ok, err, msgs = await process_chain_transaction_group(tx_id, [trigger], db_session, [rule])
    assert ok is True and err is None
    refreshes = [m for m in msgs if m.get("event") == "batch_refresh_required"]
    assert len(refreshes) == 1 and refreshes[0]["change_count"] == ROWS, msgs
    assert refreshes[0].get("edits_of") == expected and "truncated" not in refreshes[0]
    if table == PLAIN:
        model = models.DYNAMIC_TABLES[PLAIN]
        db_session.query(model).delete()
        db_session.commit()


@pytest.mark.parametrize("table, blocks, expected", [(LOOKS, lambda: [_looks(["t_a"], 600), _looks(["t_b"], 400)],
                                                      ["t_a", "t_b"]),
                                                     (PLAIN, lambda: [_plain(ROWS)], None)])
def test_a_delete_says_the_tables_its_rows_were_edits_of_read_before_they_went(client, db_session, sent, table,
                                                                                blocks, expected):
    """Both delete doors: the batch - each 500-id message its own rows' tables - and the one row."""
    for rows in blocks():
        _write(client, table, rows)
    ids = sorted(_ids(db_session, table))
    model = models.DYNAMIC_TABLES[table]
    by_id = dict(db_session.query(model.row_id, getattr(model, "look_table" if table == LOOKS else "map_key")).all())
    sent.clear()
    answer = client.post("/tables/%s/rows/batch_delete" % table, json={"row_ids": ids[1:], "user_name": "probe"})
    assert answer.status_code == 200, answer.text
    deletes = [m for m in sent if m["event"] == "batch_row_delete"]
    assert len(deletes) == 2, "canary: 999 ids in two messages"
    if expected:
        assert [m["edits_of"] for m in deletes] == [["t_a"], ["t_a", "t_b"]], "canary: the chunks differ"
    for message in deletes:
        assert message.get("edits_of") == (None if expected is None else
                                           sorted({by_id[row_id] for row_id in message["row_ids"]}))
    assert sorted(set().union(*(m.get("edits_of") or () for m in deletes))) == (expected or [])
    sent.clear()
    assert client.delete("/tables/%s/rows/%s" % (table, ids[0])).status_code == 200
    one = [m for m in sent if m["event"] == "batch_row_delete"]
    assert len(one) == 1 and one[0].get("edits_of") == (None if expected is None else [by_id[ids[0]]])
