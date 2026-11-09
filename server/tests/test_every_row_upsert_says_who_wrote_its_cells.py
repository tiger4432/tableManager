# -*- coding: utf-8 -*-
"""Lead 11-08 (클라B's L2): a written_by rule colours a cell by who wrote it, and a screen that did not make the
change learns it from batch_row_upsert - so every sender's item carries the cell's `written_by` as the page read does
(`grid_look.read` over the page's merge, `grid_read.fetch_and_merge_metadata`).

  senders   PUT data/updates · DELETE <row>/<col>/sources/<source> · PUT <row>/<col>/priority ·
            PUT cells/priority/batch · POST cells/sources/delete/batch · the chain worker's group
  rule      written_by rules on «note» -> each item's note cell says what the page read says for that cell
  no rule   (the look table declaring none every table has) no cell says written_by, and the layers' writers are
            never read
"""
import json
import uuid

import pytest

from database import models
import grid_look
from test_a_cell_looks_by_its_colour_rules_and_hand_paint import (  # noqa: F401 - the fixture
    TABLE, _layers, _look, _read, grid)

SENDERS = ["updates", "source_delete", "pin", "pin_batch", "source_delete_batch", "chain"]


@pytest.fixture(name="sent")
def fixture_sent(monkeypatch):
    import main

    out = []

    async def capture(message):
        out.append(json.loads(message))

    monkeypatch.setattr(main.manager, "broadcast", capture)
    return out


def _rule(client):
    """Rules on «note» asking each writer the senders leave there - a cell says only a writer a rule asks (lead 11-09)."""
    for n, writer in enumerate(("person", "file", "chain")):
        _look(client, "rule", "r-who-%s" % writer, position=str(n + 1), role="accent", written_by=writer,
              rule_columns='["note"]')


def note_mapper(db, payload):
    return {"updates": [{"updates": {"lot": lot, "itemid": item, "note": "chain says %s" % payload["data"]["k"],
                                     "value": int(payload["data"]["k"][-6:], 16)}, "source_name": "chain_ingestion"}
                        for lot, item in (("L1", "a"), ("L1", "b"))]}


async def _send(sender, client, db_session, ids, sent):
    """The sender's write on rows of the board; its batch_row_upsert items."""
    sent.clear()
    if sender == "updates":
        answer = client.put("/tables/%s/data/updates" % TABLE, json={"updates": [
            {"row_id": rid, "updates": {"note": "by hand"}, "source_name": "user", "updated_by": "kim"} for rid in ids[:2]]})
    elif sender == "source_delete":
        answer = client.delete("/tables/%s/%s/note/sources/user" % (TABLE, ids[0]))
    elif sender == "pin":
        answer = client.put("/tables/%s/%s/note/priority" % (TABLE, ids[0]), json={"source_name": "lots.csv"})
    elif sender == "pin_batch":
        answer = client.put("/tables/%s/cells/priority/batch" % TABLE, json={
            "updates": [{"row_id": rid, "column_name": "note"} for rid in ids[:2]], "source_name": "lots.csv",
            "updated_by": "kim"})
    elif sender == "source_delete_batch":
        answer = client.post("/tables/%s/cells/sources/delete/batch" % TABLE, json={
            "cells": [{"row_id": rid, "column_name": "note"} for rid in ids[:2]], "source_name": "user"})
    else:
        from chain.ingestion_worker import process_chain_transaction_group

        tx = "who_%s" % uuid.uuid4().hex[:8]
        trigger = models.DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type="CREATE", table_name="who_trigger",
                                        payload={"source_name": "user", "transaction_id": tx, "data": {"k": tx}})
        rule = {"name": "who_rule", "trigger_table": "who_trigger", "target_table": TABLE,
                "mapper_module": "tests.test_every_row_upsert_says_who_wrote_its_cells",
                "mapper_function": "note_mapper", "enabled": True, "is_batch": False}
        ok, err, msgs = await process_chain_transaction_group(tx, [trigger], db_session, [rule])
        assert ok is True and err is None, err
        return [item for m in msgs if m.get("event") == "batch_row_upsert" for item in m["items"]]
    assert answer.status_code == 200, answer.text
    return [item for m in sent if m["event"] == "batch_row_upsert" for item in m["items"]]


def _board(db_session, ids):
    for rid in ids[:2]:
        _layers(db_session, rid, "note", "lots.csv", "user")


@pytest.mark.anyio
@pytest.mark.parametrize("sender", SENDERS)
async def test_each_item_says_who_wrote_the_cell_as_the_page_read_does(grid, db_session, sent, sender):
    client, ids = grid
    _board(db_session, ids)
    _rule(client)
    items = await _send(sender, client, db_session, ids, sent)
    assert items, "canary: the sender broadcast items"
    page = {row["row_id"]: row["data"] for row in _read(client)["data"]}
    said = [(item["row_id"], item["data"]["note"].get("written_by"), page[item["row_id"]]["note"].get("written_by"))
            for item in items]
    assert all(seen for _rid, _item, seen in said), ("canary: the page read names a writer", said)
    assert [item for _rid, item, _seen in said] == [seen for _rid, _item, seen in said], said


@pytest.mark.anyio
@pytest.mark.parametrize("sender", SENDERS)
async def test_without_a_writer_rule_no_cell_says_it_and_no_layer_is_read(grid, db_session, sent, sender, monkeypatch):
    """TURNED (owner 11-08 1ㄱ): the look table declares the rules every table has (person · merge · ai) - without them,
    as before."""
    import grid_order
    from database import crud

    client, ids = grid
    _board(db_session, ids)
    monkeypatch.setitem(crud.TABLE_CONFIG, grid_order.LOOK_TABLE, {
        k: v for k, v in crud.TABLE_CONFIG[grid_order.LOOK_TABLE].items() if k != grid_look.DECLARED})

    def no(*_a, **_k):
        raise AssertionError("the layers' writers were read with no rule asking")

    monkeypatch.setattr(grid_look, "_writers", no)
    items = await _send(sender, client, db_session, ids, sent)
    assert items, "canary: the sender broadcast items"
    assert not any("written_by" in cell for item in items for cell in item["data"].values() if isinstance(cell, dict))


@pytest.mark.anyio
@pytest.mark.parametrize("sender", SENDERS)
async def test_a_cell_pinned_to_a_file_says_file_on_the_page_and_on_every_sender(grid, db_session, sent, sender):
    """Owner 11-08 ㄱ: a pin answers first in the page's merge - the cell pinned to lots.csv is the file's, not the
    person who pinned it."""
    client, ids = grid
    _board(db_session, ids)
    _rule(client)
    pinned = ids[0]
    if sender == "chain":                         # the chain writes rows of its own: pin one it wrote, then again
        pinned = (await _send(sender, client, db_session, ids, sent))[0]["row_id"]
        _layers(db_session, pinned, "note", "lots.csv")
    assert client.put("/tables/%s/%s/note/priority" % (TABLE, pinned), json={"source_name": "lots.csv"}).status_code == 200
    page = {row["row_id"]: row["data"] for row in _read(client)["data"]}
    assert page[pinned]["note"].get("written_by") == "file", "the page read says the pinned layer"
    items = await _send(sender, client, db_session, ids, sent)
    page = {row["row_id"]: row["data"] for row in _read(client)["data"]}
    said = [(item["row_id"], item["data"]["note"].get("written_by"), page[item["row_id"]]["note"].get("written_by"))
            for item in items]
    assert pinned in {rid for rid, _i, _p in said}, ("canary: the pinned row is in the items", said)
    assert [item for _rid, item, _seen in said] == [seen for _rid, _item, seen in said], said
